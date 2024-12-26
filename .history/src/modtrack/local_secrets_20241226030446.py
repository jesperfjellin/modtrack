import boto3
import json

def setup_local_secrets():
    secrets_client = boto3.client(
        'secretsmanager',
        endpoint_url='http://localhost:4566',
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )

    secret_config = {
        'username': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': 5432,
        'database': 'postgres'
    }

    try:
        # Try to get existing secret
        secrets_client.get_secret_value(SecretId='modtrack/database')
        # If it exists, update it
        secrets_client.update_secret(
            SecretId='modtrack/database',
            SecretString=json.dumps(secret_config)
        )
        print("Updated database secrets")
    except secrets_client.exceptions.ResourceNotFoundException:
        # If it doesn't exist, create it
        secrets_client.create_secret(
            Name='modtrack/database',
            SecretString=json.dumps(secret_config)
        )
        print("Created database secrets")
    except Exception as e:
        print(f"Warning: Could not manage secrets: {e}")
        print("Continuing with default configuration...")

if __name__ == "__main__":
    setup_local_secrets()