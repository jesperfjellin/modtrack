import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
from datetime import datetime, timezone
import schedule
from .aws_utils import SecretsManager, EventBridge
from .config import Config

class ModelResultsHandler(FileSystemEventHandler):
    def __init__(self, target_directory: Path):
        self.target_directory = target_directory
        self.processed_files = set()
        
        # Initialize AWS services
        secrets = SecretsManager()
        db_secrets = secrets.get_secret(Config.DB_SECRET_NAME)
        api_secrets = secrets.get_secret(Config.API_SECRET_NAME)
        
        # Initialize database connection and API client with secrets
        self.db_connection = self.init_db_connection(db_secrets)
        self.api_client = self.init_api_client(api_secrets)
        
        # Initialize EventBridge
        self.event_bridge = EventBridge()
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)

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
        self.logger.info(f"Processing file: {file_path}")

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

def scan_directory(directory: Path, handler: ModelResultsHandler):
    """Scan the directory for any files that haven't been processed yet"""
    for file_path in directory.glob('*'):  # Adjust pattern based on your file types
        if file_path.is_file() and file_path not in handler.processed_files:
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

    # Schedule regular scans every 5 minutes
    schedule.every(5).minutes.do(scan_directory, target_dir, handler)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    # Replace with your actual directory path
    MODEL_RESULTS_DIR = "/path/to/model/results"
    start_monitoring(MODEL_RESULTS_DIR)