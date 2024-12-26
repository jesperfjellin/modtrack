import boto3
import json
from .config import Config, Environment

class AWSClients:
    def __init__(self):
        self.environment = Config.ENV
        
        # Common boto3 args for LocalStack
        self.boto3_args = {}
        if self.environment == Environment.LOCAL:
            self.boto3_args.update({
                'endpoint_url': Config.LOCALSTACK_ENDPOINT,
                'aws_access_key_id': 'test',
                'aws_secret_access_key': 'test',
                'region_name': Config.AWS_REGION
            })

    def get_secrets_client(self):
        return boto3.client('secretsmanager', **self.boto3_args)
    
    def get_events_client(self):
        return boto3.client('events', **self.boto3_args)

class SecretsManager:
    def __init__(self):
        self.client = AWSClients().get_secrets_client()

    def get_secret(self, secret_name: str) -> dict:
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            if Config.ENV == Environment.LOCAL:
                # Return dummy secrets for local development
                if secret_name == Config.DB_SECRET_NAME:
                    return {
                        "username": "postgres",
                        "password": "postgres",
                        "host": "localhost",
                        "port": "5432",
                        "dbname": "modtrack"
                    }
                elif secret_name == Config.API_SECRET_NAME:
                    return {
                        "api_key": "test_key",
                        "api_url": "http://localhost:8000"
                    }
            raise e

class EventBridge:
    def __init__(self):
        self.client = AWSClients().get_events_client()
        self.rule_prefix = "modtrack-validation-"

    def schedule_validation(self, prediction_id: str, target_timestamp: str):
        """Schedule a validation check using EventBridge"""
        try:
            rule_name = f"{self.rule_prefix}{prediction_id}"
            
            # Create the rule
            self.client.put_rule(
                Name=rule_name,
                ScheduleExpression=f"at({target_timestamp})",
                State='ENABLED'
            )
            
            # Add target (Lambda function that will handle validation)
            self.client.put_targets(
                Rule=rule_name,
                Targets=[{
                    'Id': f"ValidationTarget-{prediction_id}",
                    'Arn': 'arn:aws:lambda:region:account:function:validation-function',
                    'Input': json.dumps({'prediction_id': prediction_id})
                }]
            )
        except Exception as e:
            if Config.ENV == Environment.LOCAL:
                # In local development, log but don't fail
                print(f"Warning: EventBridge scheduling failed (expected in local dev): {str(e)}")
            else:
                raise