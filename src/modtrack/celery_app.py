# celery_app.py
import os
from celery import Celery
from .aws_utils import SecretsManager
from .config import Config
import psycopg2
import httpx
import uuid
from datetime import datetime, timezone

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

celery_app = Celery(
    "modtrack_tasks",
    broker=BROKER_URL,
    include=["src.modtrack.celery_app"]
)

@celery_app.task(name="modtrack.celery_app.validate_prediction_task")
def validate_prediction_task(prediction_id: str, reservoir_id: str, predicted_level: float):
    """
    A Celery task to perform the validation step.
    This is the 'heavy' or 'concurrent' work we want to offload.
    """
    try:
        # 1. Connect to DB via secrets
        secrets = SecretsManager()
        api_secrets = secrets.get_secret(Config.API_SECRET_NAME)
        db_secrets = secrets.get_secret(Config.DB_SECRET_NAME)

        conn = psycopg2.connect(
            dbname=db_secrets['dbname'],
            user=db_secrets['username'],
            password=db_secrets['password'],
            host=db_secrets['host'],
            port=db_secrets['port']
        )
        cur = conn.cursor()

        # 2. Call external API
        api_client = httpx.Client(timeout=10.0)
        response = api_client.get(
            f"{api_secrets['api_url']}/water-level/{reservoir_id}",
            headers={"Authorization": f"Bearer {api_secrets['api_key']}"}
        )
        response.raise_for_status()
        data = response.json()
        actual_level = data["water_level"]

        # 3. Calculate difference and insert validation record
        difference = abs(actual_level - predicted_level)
        cur.execute("""
            INSERT INTO validations
            (id, prediction_id, actual_level, difference, validated_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            prediction_id,
            actual_level,
            difference,
            datetime.now(timezone.utc)
        ))
        conn.commit()

        cur.close()
        conn.close()
        return {"status": "success", "difference": difference}

    except Exception as e:
        print(f"Error validating prediction: {str(e)}")
        return {"status": "error", "message": str(e)}
