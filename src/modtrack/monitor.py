import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from datetime import datetime, timezone, timedelta
import schedule
import csv
from .aws_utils import SecretsManager, EventBridge
from .config import Config
from .db import init_db_schema
import psycopg2
from typing import Optional
import os
import json
import httpx
import uuid

class ModelResultsHandler(FileSystemEventHandler):
    PROCESSED_FILES_CSV = 'processed_files.csv'
    
    def __init__(self, target_directory: Path):
        # Initialize logger first
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        self.target_directory = target_directory
        self.processed_files = set()
        
        # Path to the .csv file
        self.processed_files_path = self.target_directory / self.PROCESSED_FILES_CSV
        
        # Initialize with retries
        self.db_connection = None
        self.api_client = None
        self.event_bridge = None
        
        # Try to initialize connections with retries
        self._initialize_with_retries()
        
        # Load processed files from the CSV
        self._load_processed_files()

        # Initialize database schema
        init_db_schema(self.db_connection)

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

    def _load_processed_files(self):
        """Load processed files from the CSV into the in-memory set."""
        if not self.processed_files_path.exists():
            # If the CSV doesn't exist, create it
            self.processed_files_path.touch()
            self.logger.info(f"Created new processed files tracking CSV at {self.processed_files_path}")
            return
        
        try:
            with self.processed_files_path.open(mode='r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                self.processed_files = {row[0] for row in reader if row}
            self.logger.info(f"Loaded {len(self.processed_files)} processed files from CSV.")
        except Exception as e:
            self.logger.error(f"Failed to load processed files from CSV: {e}")
            raise

    def mark_file_as_processed(self, file_name: str):
        """Append the processed file to the CSV and update the in-memory set."""
        try:
            with self.processed_files_path.open(mode='a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([file_name])
            self.processed_files.add(file_name)
            self.logger.debug(f"Marked file as processed in CSV: {file_name}")
        except Exception as e:
            self.logger.error(f"Failed to mark file as processed in CSV: {e}")
            raise

    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        file_name = file_path.name
        if file_name not in self.processed_files:
            self.logger.info(f"New file detected: {file_name}")
            try:
                self.process_file(file_path)
                self.mark_file_as_processed(file_name)
            except Exception as e:
                self.logger.error(f"Error processing file {file_name}: {e}")

    def process_file(self, file_path: Path) -> None:
        self.logger.info(f"New file found: {file_path.name}")

        try:
            with open(file_path) as f:
                data = json.load(f)

            # Process each prediction
            for prediction in data["predictions"]:
                prediction_id = str(uuid.uuid4())  # Convert UUID to string
                reservoir_id = prediction["reservoir_id"]
                predicted_level = prediction["predicted_level"]
                prediction_timestamp = datetime.fromisoformat(data["timestamp"].replace('Z', '+00:00'))
                validation_time = datetime.fromisoformat(prediction["validation_time"].replace('Z', '+00:00'))

                # Store prediction in database
                with self.db_connection.cursor() as cur:
                    cur.execute("""
                        INSERT INTO predictions
                        (id, reservoir_id, predicted_level, prediction_timestamp,
                        validation_time, file_name)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        prediction_id,  # Now a string
                        reservoir_id,
                        predicted_level,
                        prediction_timestamp,
                        validation_time,
                        file_path.name
                    ))
                    self.db_connection.commit()

                # Schedule the validation check
                schedule.every().day.at(validation_time.strftime("%H:%M")).do(
                    self.validate_prediction,
                    prediction_id=prediction_id,
                    reservoir_id=reservoir_id,
                    predicted_level=predicted_level
                )
                self.logger.info(f"Scheduled validation for reservoir {reservoir_id} at {validation_time}")

            self.logger.info(f"Successfully processed file: {file_path.name}")

        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            return
    
    def validate_prediction(self, prediction_id: str, reservoir_id: str, predicted_level: float) -> None:
        try:
            self.logger.info(f"Attempting to validate prediction {prediction_id} for reservoir {reservoir_id}")
            self.logger.info(f"Using API URL: {self.api_secrets['api_url']}")
            
            # Get actual water level from API
            response = self.api_client.get_water_level(reservoir_id)
            actual_level = response["water_level"]

            self.logger.info(f"Received response from API: {response}")
            # Get actual water level from API
            response = self.api_client.get_water_level(reservoir_id)
            actual_level = response["water_level"]

            # Calculate difference
            difference = abs(actual_level - predicted_level)

            # Store validation result
            with self.db_connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO validations
                    (id, prediction_id, actual_level, difference, validated_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    str(uuid.uuid4()),  # Convert UUID to string
                    prediction_id,      # Already a string from process_file
                    actual_level,
                    difference,
                    datetime.now(timezone.utc)
                ))
                self.db_connection.commit()

            self.logger.info(
                f"Validation for {reservoir_id}:\n"
                f"  Predicted: {predicted_level:.2f}m\n"
                f"  Actual: {actual_level:.2f}m\n"
                f"  Difference: {difference:.2f}m"
            )

        except Exception as e:
            self.logger.error(f"Error validating prediction for {reservoir_id}: {str(e)}")
            self.logger.error(f"Full error details: ", exc_info=True)

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
    
    def cleanup_stale_predictions(self):
        """Clean up predictions that are stuck in pending state"""
        try:
            with self.db_connection.cursor() as cur:
                # Find and update predictions that are:
                # 1. More than 5 minutes past their validation_time
                # 2. Don't have a corresponding validation record
                cur.execute("""
                    INSERT INTO validations (id, prediction_id, actual_level, difference, validated_at)
                    SELECT 
                        uuid_generate_v4(),
                        p.id,
                        0,  -- placeholder actual_level
                        0,  -- placeholder difference
                        NOW()
                    FROM predictions p
                    LEFT JOIN validations v ON p.id = v.prediction_id
                    WHERE 
                        v.id IS NULL  -- no validation record exists
                        AND p.validation_time < NOW() - INTERVAL '5 minutes'
                    RETURNING prediction_id;
                """)
                
                stale_count = cur.rowcount
                if stale_count > 0:
                    self.logger.info(f"Marked {stale_count} stale predictions as failed")
                
                self.db_connection.commit()
        except Exception as e:
            self.logger.error(f"Error cleaning up stale predictions: {e}")

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
        try:
            return APIClient(api_secrets['api_url'], api_secrets['api_key'])
        except Exception as e:
            self.logger.error(f"Failed to initialize API client: {e}")
            return None

        
class APIClient:
    def __init__(self, url, api_key):
        self.url = url
        self.headers = {'Authorization': f'Bearer {api_key}'}
        self.client = httpx.Client(timeout=10.0)  # Add timeout
        
        # Test connection on init
        try:
            response = self.client.get(f"{self.url}/")
            response.raise_for_status()
            print(f"Successfully connected to API at {self.url}")
        except Exception as e:
            print(f"Warning: Could not connect to API at {self.url}: {e}")

    def get_water_level(self, reservoir_id: str) -> dict:
        try:
            response = self.client.get(
                f"{self.url}/water-level/{reservoir_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting water level: {e}")
            raise

class ScanScheduler:
    def __init__(self, directory: Path, handler: ModelResultsHandler, interval_minutes: int = 1):
        self.directory = directory
        self.handler = handler
        self.interval = interval_minutes
        
        # Schedule regular scans
        self.scan_job = schedule.every(self.interval).minutes.do(self.scan_and_log)
        
        # Schedule cleanup every 5 minutes
        self.cleanup_job = schedule.every(5).minutes.do(self.cleanup_stale_predictions)

        # Calculate the initial next_run_time
        self.next_run_time = datetime.now(timezone.utc) + timedelta(minutes=self.interval)
        self.log_next_run(initial=True)

    def cleanup_stale_predictions(self):
        """Run the cleanup for stale predictions"""
        self.handler.cleanup_stale_predictions()

    def scan_and_log(self):
        """Perform the scan and log the next scheduled run."""
        try:
            scan_directory(self.directory, self.handler)
            self.handler.logger.info("Scan completed successfully.")
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
        if file_path.is_file():
            file_name = file_path.name
            if file_name not in handler.processed_files:
                handler.logger.info(f"New file found: {file_name}")
                try:
                    handler.process_file(file_path)
                    handler.mark_file_as_processed(file_name)
                except Exception as e:
                    handler.logger.error(f"Error processing file {file_name}: {e}")

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
