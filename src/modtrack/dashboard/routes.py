from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from ..aws_utils import SecretsManager

router = FastAPI()
templates = Jinja2Templates(directory="src/modtrack/dashboard/templates")
router.mount("/static", StaticFiles(directory="src/modtrack/dashboard/static"), name="static")

def get_db_connection():
    secrets = SecretsManager()
    db_secrets = secrets.get_secret("modtrack/database")
    return psycopg2.connect(
        dbname=db_secrets['dbname'],
        user=db_secrets['username'],
        password=db_secrets['password'],
        host=db_secrets['host'],
        port=db_secrets['port'],
        cursor_factory=RealDictCursor
    )

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get recent predictions with their validations
        cur.execute("""
            SELECT 
                p.id,
                p.reservoir_id,
                p.predicted_level,
                p.prediction_timestamp,
                p.validation_time,
                v.actual_level,
                v.difference,
                v.validated_at
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            ORDER BY p.prediction_timestamp DESC
            LIMIT 50
        """)
        records = cur.fetchall()
        
        # Calculate statistics for the last 24 hours
        cur.execute("""
            SELECT 
                COUNT(*) as total_predictions,
                ROUND(AVG(v.difference)::numeric, 2) as avg_difference,
                ROUND(MAX(v.difference)::numeric, 2) as max_difference,
                ROUND(MIN(v.difference)::numeric, 2) as min_difference,
                COUNT(v.id) as validated_count
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            WHERE p.prediction_timestamp >= NOW() - INTERVAL '24 hours'
        """)
        stats = cur.fetchone()

        # Get validation success rate
        if stats['total_predictions'] > 0:
            stats['success_rate'] = round(
                (stats['validated_count'] / stats['total_predictions']) * 100, 1
            )
        else:
            stats['success_rate'] = 0

        # Get reservoir-specific statistics
        cur.execute("""
            SELECT 
                p.reservoir_id,
                COUNT(*) as prediction_count,
                ROUND(AVG(v.difference)::numeric, 2) as avg_difference
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            WHERE p.prediction_timestamp >= NOW() - INTERVAL '24 hours'
            GROUP BY p.reservoir_id
            ORDER BY p.reservoir_id
        """)
        reservoir_stats = cur.fetchall()

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "records": records,
                "stats": stats,
                "reservoir_stats": reservoir_stats,
                "current_time": datetime.now(timezone.utc),  # Make timezone-aware
                "timedelta": timedelta  # Pass timedelta to template
            }
        )

    except Exception as e:
        # Log the error and return an error page
        print(f"Error accessing database: {e}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_message": "Failed to load dashboard data"
            }
        )
    finally:
        cur.close()
        conn.close()

@router.get("/api/predictions", response_class=HTMLResponse)
async def get_predictions(
    request: Request,
    reservoir_id: str = None,
    days: int = 1
):
    """API endpoint for filtered prediction data"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        query = """
            SELECT 
                p.id,
                p.reservoir_id,
                p.predicted_level,
                p.prediction_timestamp,
                v.actual_level,
                v.difference
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            WHERE p.prediction_timestamp >= NOW() - INTERVAL '%s days'
        """
        params = [days]

        if reservoir_id:
            query += " AND p.reservoir_id = %s"
            params.append(reservoir_id)

        query += " ORDER BY p.prediction_timestamp DESC"
        
        cur.execute(query, params)
        predictions = cur.fetchall()

        return predictions

    except Exception as e:
        print(f"Error accessing database: {e}")
        return {"error": "Failed to load prediction data"}
    finally:
        cur.close()
        conn.close()

@router.get("/api/accuracy-data")
async def get_accuracy_data():
    """API endpoint for prediction accuracy time-series data"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                p.reservoir_id,
                v.validated_at as timestamp,
                v.actual_level - p.predicted_level as deviation
            FROM predictions p
            JOIN validations v ON p.id = v.prediction_id
            WHERE v.validated_at >= NOW() - INTERVAL '24 hours'
            ORDER BY v.validated_at ASC
        """)
        data = cur.fetchall()

        # Group by reservoir
        reservoirs = {}
        for row in data:
            reservoir_id = row["reservoir_id"]
            if reservoir_id not in reservoirs:
                reservoirs[reservoir_id] = {
                    "timestamps": [],
                    "deviations": []
                }
            reservoirs[reservoir_id]["timestamps"].append(row["timestamp"].isoformat())
            reservoirs[reservoir_id]["deviations"].append(float(row["deviation"]))

        return reservoirs
    finally:
        cur.close()
        conn.close()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}