import argparse
from pathlib import Path
from .monitor import start_monitoring
from .local_secrets import setup_local_secrets
from .config import Config, Environment

def main():
    parser = argparse.ArgumentParser(description='ModTrack - Model Results Tracker')
    parser.add_argument('--directory', '-d', required=True,
                       help='Directory to monitor for model results')
    
    args = parser.parse_args()
    
    # If in local environment, ensure secrets are set up
    if Config.ENV == Environment.LOCAL:
        setup_local_secrets()
    
    # Start monitoring
    start_monitoring(args.directory)

if __name__ == "__main__":
    main()