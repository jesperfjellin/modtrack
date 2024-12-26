import boto3
import json

def setup_local_secrets():
    secrets_client = boto3.client(
        'secretsmanager',
        endpoint_url='http://localstack:4566',
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )

    # Database secrets
    try:
        secrets_client.get_secret_value(SecretId='modtrack/database')
        print("Database secrets already exist")
    except secrets_client.exceptions.ResourceNotFoundException:
        secrets_client.create_secret(
            Name='modtrack/database',
            SecretString=json.dumps({
                'username': 'postgres',
                'password': 'postgres',
                'host': 'postgres',
                'port': 5432,
                'dbname': 'postgres'
            })
        )
        print("Created database secrets")

    # API secrets
    try:
        secrets_client.get_secret_value(SecretId='modtrack/api')
        print("API secrets already exist")
    except secrets_client.exceptions.ResourceNotFoundException:
        secrets_client.create_secret(
            Name='modtrack/api',
            SecretString=json.dumps({
                'api_key': 'test_key',
                'api_url': 'http://mock-api:8000'  # Changed from mock-apiapp:8000
            })
        )
        print("Created API secrets")