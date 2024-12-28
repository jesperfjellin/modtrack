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
async def home(request: Request, page: int = 1, limit: int = 20):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        #
        # All-time stats
        #
        cur.execute("""
            SELECT
                COUNT(*) as total_predictions,
                ROUND(AVG(v.difference)::numeric, 2) as avg_difference,
                ROUND(MAX(v.difference)::numeric, 2) as max_difference,
                ROUND(MIN(v.difference)::numeric, 2) as min_difference,
                COUNT(v.id) as validated_count
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
        """)
        stats = cur.fetchone()
        
        # success rate
        if stats['total_predictions'] > 0:
            stats['success_rate'] = round(
                (stats['validated_count'] / stats['total_predictions']) * 100, 1
            )
        else:
            stats['success_rate'] = 0

        #
        # All-time reservoir stats
        #
        cur.execute("""
            SELECT
                p.reservoir_id,
                COUNT(*) as prediction_count,
                ROUND(AVG(v.difference)::numeric, 2) as avg_difference
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            GROUP BY p.reservoir_id
            ORDER BY p.reservoir_id
        """)
        reservoir_stats = cur.fetchall()

        #
        # Pagination: Retrieve records
        #
        # 1) total count
        cur.execute("SELECT COUNT(*) as total FROM predictions")
        row = cur.fetchone()
        total_predictions = row["total"]

        # 2) limit/offset logic
        page = max(page, 1)
        limit = max(limit, 1)
        offset = (page - 1) * limit

        query = f"""
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
            LIMIT {limit} OFFSET {offset}
        """
        cur.execute(query)
        records = cur.fetchall()

        # 3) total pages
        total_pages = (total_predictions + limit - 1) // limit

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "stats": stats,
                "reservoir_stats": reservoir_stats,
                "records": records,
                "current_time": datetime.now(timezone.utc),
                "timedelta": timedelta,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "total_predictions": total_predictions
            }
        )
    except Exception as e:
        print(f"Error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error_message": "Failed to load data"}
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

@router.get("/api/predictions/{prediction_id}")
async def get_prediction_detail(prediction_id: str):
    """
    Return JSON for a single prediction, including e.g. file_name, difference over time, 
    or anything else you'd like to show in the modal.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Example query to get a single record with extra fields
        cur.execute("""
            SELECT
                p.id,
                p.reservoir_id,
                p.predicted_level,
                p.file_name,
                p.prediction_timestamp,
                p.validation_time,
                v.actual_level,
                v.difference,
                v.validated_at
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            WHERE p.id::text = %s
        """, [prediction_id])

        record = cur.fetchone()
        if not record:
            return {"error": f"Prediction {prediction_id} not found"}

        return record
    finally:
        cur.close()
        conn.close()

@router.get("/api/filter-predictions")
async def filter_predictions(
    reservoir_id: str = None,
    start_date: str = None,
    end_date: str = None
):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT
                p.id,
                p.reservoir_id,
                p.predicted_level,
                p.prediction_timestamp,
                p.validation_time,
                v.actual_level,
                v.difference
            FROM predictions p
            LEFT JOIN validations v ON p.id = v.prediction_id
            WHERE 1=1
        """
        params = []

        if reservoir_id:
            query += " AND p.reservoir_id = %s"
            params.append(reservoir_id)

        if start_date:
            query += " AND p.prediction_timestamp >= %s"
            params.append(start_date)

        if end_date:
            # Make it inclusive to the entire end date
            query += " AND p.prediction_timestamp < (%s::date + INTERVAL '1 day')"
            params.append(end_date)

        query += " ORDER BY p.prediction_timestamp DESC"

        cur.execute(query, params)
        rows = cur.fetchall()

        return rows  # List[dict], thanks to RealDictCursor in get_db_connection
    except Exception as e:
        print("Filter Error:", e)
        return []
    finally:
        cur.close()
        conn.close()

@router.get("/api/filter-accuracy-data")
async def filter_accuracy_data(
    reservoir_id: str = None,
    start_date: str = None,
    end_date: str = None
):
    """
    Return the same structure as /api/accuracy-data, but filtered.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        base_query = """
            SELECT
                p.reservoir_id,
                v.validated_at as timestamp,
                v.actual_level - p.predicted_level as deviation
            FROM predictions p
            JOIN validations v ON p.id = v.prediction_id
            WHERE 1=1
        """
        params = []
        if reservoir_id:
            base_query += " AND p.reservoir_id = %s"
            params.append(reservoir_id)
        if start_date:
            base_query += " AND p.prediction_timestamp >= %s"
            params.append(start_date)
        if end_date:
            base_query += " AND p.prediction_timestamp < (%s::date + INTERVAL '1 day')"
            params.append(end_date)

        base_query += " ORDER BY v.validated_at ASC"

        cur.execute(base_query, params)
        rows = cur.fetchall()

        # Group them just like in get_accuracy_data():
        reservoirs = {}
        for row in rows:
            rid = row["reservoir_id"]
            if rid not in reservoirs:
                reservoirs[rid] = {"timestamps": [], "deviations": []}
            reservoirs[rid]["timestamps"].append(row["timestamp"].isoformat())
            reservoirs[rid]["deviations"].append(float(row["deviation"]))

        return reservoirs
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
