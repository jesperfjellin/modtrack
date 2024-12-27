import psycopg2
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def init_db_schema(conn: psycopg2.extensions.connection) -> None:
    """Initialize database schema if it doesn't exist"""
    with conn.cursor() as cur:
        # Create predictions table

        cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id UUID PRIMARY KEY,
                reservoir_id VARCHAR(50) NOT NULL,
                predicted_level DECIMAL(10,2) NOT NULL,
                prediction_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                validation_time TIMESTAMP WITH TIME ZONE NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create validations table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS validations (
                id UUID PRIMARY KEY,
                prediction_id UUID REFERENCES predictions(id),
                actual_level DECIMAL(10,2) NOT NULL,
                difference DECIMAL(10,2) NOT NULL,
                validated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prediction_id) REFERENCES predictions(id)
            )
        """)
        conn.commit()
        logger.info("Database schema initialized successfully")