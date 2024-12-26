import logging
from .monitor import start_monitoring
from .local_secrets import setup_local_secrets
from .config import Config, Environment

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # If in local environment, ensure secrets are set up
    if Config.ENV == Environment.LOCAL:
        setup_local_secrets()
    
    # Use the Docker volume path
    directory = "/data/model_results"
    logger.info(f"Starting monitoring of directory: {directory}")
    
    # Use the start_monitoring function from monitor.py
    start_monitoring(directory)

if __name__ == "__main__":
    main()