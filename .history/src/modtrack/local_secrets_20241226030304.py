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

    # Update existing secret
    try:
        secrets_client.update_secret(
            SecretId='modtrack/database',
            SecretString=json.dumps({
                'username': 'postgres',
                'password': 'postgres',
                'host': 'localhost',  # Changed from 'postgres' to 'localhost'
                'port': 5432,
                'database': 'postgres'
            })
        )
        print("Updated database secrets")
    except Exception as e:
        print(f"Error updating secret: {e}")

if __name__ == "__main__":
    setup_local_secrets()