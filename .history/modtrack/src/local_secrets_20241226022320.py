import boto3
import json

def setup_local_secrets():
    secrets_client = boto3.client(
        'secretsmanager',
        endpoint_url='http://localhost:4566',
        aws_access_key_id='test',
        aws_secret_access_key='test',
        region_name='us-east-1'
    )

    # Create database secrets
    secrets_client.create_secret(
        Name='modtrack/database',
        SecretString=json.dumps({
            "username": "postgres",
            "password": "postgres",
            "host": "postgres",  # service name in docker-compose
            "port": "5432",
            "dbname": "modtrack"
        })
    )

    # Create API secrets
    secrets_client.create_secret(
        Name='modtrack/api',
        SecretString=json.dumps({
            "api_key": "test_key",
            "api_url": "http://localhost:8000"
        })
    )

if __name__ == "__main__":
    setup_local_secrets()