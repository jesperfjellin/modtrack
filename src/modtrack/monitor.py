import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from datetime import datetime, timezone, timedelta
import schedule
from .aws_utils import SecretsManager, EventBridge
from .config import Config
import psycopg2
from typing import Optional
import os

class ModelResultsHandler(FileSystemEventHandler):
    def __init__(self, target_directory: Path):
        # Initialize logger first
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        self.target_directory = target_directory
        self.processed_files = set()
        
        # Initialize with retries
        self.db_connection = None
        self.api_client = None
        self.event_bridge = None
        
        # Try to initialize connections with retries
        self._initialize_with_retries()

    def _initialize_with_retries(self, max_retries=5, delay=2):
        """Initialize connections with retries"""
        for attempt in range(max_retries):
            try:
                # Initialize AWS services and get secrets first
                secrets = SecretsManager()
                self.db_secrets = secrets.get_secret(Config.DB_SECRET_NAME)
                self.api_secrets = secrets.get_secret(Config.API_SECRET_NAME)
                
                # Initialize connections using secrets
                self.db_connection = self.init_db_connection(self.db_secrets)
                self.api_client = self.init_api_client(self.api_secrets)
                
                # Initialize EventBridge
                self.event_bridge = EventBridge()
                
                self.logger.info("Successfully initialized all connections")
                return
            except Exception as e:
                self.logger.warning(f"Initialization attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    self.logger.error("Failed to initialize after all retries")
                    raise

    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        if file_path not in self.processed_files:
            self.logger.info(f"New file detected: {file_path}")
            self.process_file(file_path)
            self.processed_files.add(file_path)

    def process_file(self, file_path: Path):
        """
        Process the newly detected file.
        This is where you'll add the logic to:
        1. Extract data from the model results
        2. Store it in the database
        """
        # TODO: Implement file processing logic
        pass

    def schedule_validations(self, predictions):
        """Schedule validation checks using EventBridge"""
        for pred in predictions:
            # Convert timestamp to ISO 8601 format
            iso_timestamp = pred['target_timestamp'].astimezone(timezone.utc).isoformat()
            
            self.event_bridge.schedule_validation(
                prediction_id=pred['id'],
                target_timestamp=iso_timestamp
            )
            
            self.logger.info(f"Scheduled validation for prediction {pred['id']} at {iso_timestamp}")

    def init_db_connection(self, secrets_dict=None):
        """Initialize database connection."""
        if secrets_dict is None:
            # Default connection settings if no secrets provided
            secrets_dict = {
                'username': 'postgres',
                'password': 'postgres',
                'host': 'postgres',  # Changed from localhost to postgres
                'port': 5432,
                'dbname': 'postgres'
            }

        try:
            conn = psycopg2.connect(
                dbname=secrets_dict.get('dbname', 'postgres'),
                user=secrets_dict.get('username', 'postgres'),
                password=secrets_dict.get('password', 'postgres'),
                host=secrets_dict.get('host', 'postgres'),  # Changed default from localhost to postgres
                port=secrets_dict.get('port', 5432)
            )
            self.logger.info("Successfully connected to database")
            return conn
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise

    def init_api_client(self, api_secrets):
        """Initialize API client using secrets"""
        # TODO: Implement proper API client
        class APIClient:
            def __init__(self, url, api_key):
                self.url = url
                self.headers = {'Authorization': f'Bearer {api_key}'}
                
            def get_water_level(self, reservoir_id, timestamp):
                # TODO: Implement actual API call
                pass
        
        return APIClient(api_secrets['api_url'], api_secrets['api_key'])

class ScanScheduler:
    def __init__(self, directory: Path, handler: ModelResultsHandler, interval_minutes: int = 1):
        self.directory = directory
        self.handler = handler
        self.interval = interval_minutes
        self.job = schedule.every(self.interval).minutes.do(self.scan_and_log)
        
        # Calculate the initial next_run_time
        self.next_run_time = datetime.now(timezone.utc) + timedelta(minutes=self.interval)
        self.log_next_run(initial=True)

    def scan_and_log(self):
        """Perform the scan and log the next scheduled run."""
        try:
            scan_directory(self.directory, self.handler)
        except Exception as e:
            self.handler.logger.error(f"Error during scan: {e}")
        
        # Calculate the next run time manually
        self.next_run_time = datetime.now(timezone.utc) + timedelta(minutes=self.interval)
        self.log_next_run()

    def log_next_run(self, initial=False):
        """Log the next scheduled scan time."""
        run_time_str = self.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        if initial:
            self.handler.logger.info(f"Scheduled first scan: {run_time_str}")
        else:
            self.handler.logger.info(f"Scheduled next scan: {run_time_str}")

def scan_directory(directory: Path, handler: ModelResultsHandler):
    """Scan the directory for any files that haven't been processed yet"""
    handler.logger.info("Scanning...")
    for file_path in directory.glob('*'):
        if file_path.is_file() and file_path not in handler.processed_files:
            handler.logger.info(f"New file found: {file_path.name}")
            handler.process_file(file_path)
            handler.processed_files.add(file_path)

def start_monitoring(directory_path: str):
    target_dir = Path(directory_path)
    if not target_dir.exists():
        raise ValueError(f"Directory does not exist: {directory_path}")

    handler = ModelResultsHandler(target_dir)
    observer = Observer()
    observer.schedule(handler, str(target_dir), recursive=False)
    observer.start()

    try:
        # Run first scan immediately
        scan_directory(target_dir, handler)
        handler.logger.info("Initial scan completed.")

        # Initialize the scheduler
        scheduler = ScanScheduler(target_dir, handler, interval_minutes=1)

        # Main loop to run scheduled jobs
        while True:
            schedule.run_pending()
            time.sleep(1)  # Sleep to prevent high CPU usage
    except KeyboardInterrupt:
        handler.logger.info("Stopping monitoring due to keyboard interrupt.")
        observer.stop()
    except Exception as e:
        handler.logger.error(f"An error occurred: {e}")
        observer.stop()
    observer.join()
