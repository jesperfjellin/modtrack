import boto3
import json

def setup_local_secrets():
    secrets_client = boto3.client(
        'secretsmanager',
        endpoint_url='http://localhost:4566',  # LocalStack endpoint
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )

    # First check if secret exists
    try:
        secrets_client.get_secret_value(SecretId='modtrack/database')
        print("Database secrets already exist, skipping creation")
        return
    except secrets_client.exceptions.ResourceNotFoundException:
        # Only create if secret doesn't exist
        secrets_client.create_secret(
            Name='modtrack/database',
            SecretString=json.dumps({
                'username': 'postgres',
                'password': 'postgres',
                'host': 'localhost',  # Changed from 'postgres' to 'localhost'
                'port': 5432,
                'database': 'postgres'
            })
        )
        print("Created database secrets")

if __name__ == "__main__":
    setup_local_secrets()