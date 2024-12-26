import os
from enum import Enum

class Environment(Enum):
    LOCAL = "local"
    PRODUCTION = "production"

class Config:
    ENV = Environment(os.getenv("ENVIRONMENT", "local"))
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    
    # LocalStack endpoint if running locally
    LOCALSTACK_ENDPOINT = "http://localhost:4566"
    
    # Secrets
    DB_SECRET_NAME = "modtrack/database"
    API_SECRET_NAME = "modtrack/api"
