import logging
from fastapi import FastAPI
from .monitor import start_monitoring
from .local_secrets import setup_local_secrets
from .config import Config, Environment
from .mock_api.app import app as mock_api
from .dashboard.routes import router as dashboard
import uvicorn
import threading

# Create the main FastAPI application
app = FastAPI()

# Mount both applications
app.mount("/api", mock_api)
app.mount("/dashboard", dashboard)

def run_monitoring():
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

def main():
    # Start the monitoring in a separate thread
    monitoring_thread = threading.Thread(target=run_monitoring, daemon=True)
    monitoring_thread.start()

    # Run the FastAPI application
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()