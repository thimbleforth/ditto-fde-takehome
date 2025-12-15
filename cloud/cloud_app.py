# cloud_app.py
import os
import logging
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from data_models import Report, Base
import jwt
import re
import time
import datetime
import sqlite3

CLOUD_DB_PATH = os.getenv("CLOUD_DB_PATH", "/app/data/cloud_db.sqlite")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "/app/data/cloud.log")

app = Flask(__name__)

# Expose a `Session` symbol so tests can monkeypatch it (inmemory_test_runner also
# sets this when running the in-memory checks). It may be set to a callable that
# returns a session instance.
Session = None

# Configure logging
def setup_logging():
    """Configure logging with file handler and console handler."""
    # Create logger
    logger = logging.getLogger('cloud_app')
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(endpoint)s] - [User: %(user)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    try:
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE_PATH)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file handler: {e}")
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

def log_info(endpoint, user, message):
    """Log info message with endpoint and user context."""
    logger.info(message, extra={'endpoint': endpoint, 'user': user})

def log_error(endpoint, user, message):
    """Log error message with endpoint and user context."""
    logger.error(message, extra={'endpoint': endpoint, 'user': user})

def log_warning(endpoint, user, message):
    """Log warning message with endpoint and user context."""
    logger.warning(message, extra={'endpoint': endpoint, 'user': user})
# Yes we're using a SQLite DB for simplicity here
# and a Flask server for quick prototyping, that isn't a production-ready WSGI server
# I only had 90 minutes for this, fite me

# --- Database setup ---
def _get_engine():
    # Read the DB path at call time so tests can set CLOUD_DB_PATH per-module.
    # Prefer a per-app config value when running under a test client.
    db_path = app.config.get('CLOUD_DB_PATH') or os.getenv("CLOUD_DB_PATH", CLOUD_DB_PATH)
    return create_engine(f"sqlite:///{db_path}")


def get_session():
    """Create a new SQLAlchemy session bound to the configured DB.

    Ensures the database schema exists by calling create_all on the engine.
    """
    # Allow tests to override the Session factory at module level.
    # If `Session` is provided and callable, use it (may raise to simulate errors).
    if 'Session' in globals() and callable(globals().get('Session')):
        return globals().get('Session')()

    engine = _get_engine()
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()

# including this here just to create the DB schema on the edge device
def init_db():
    conn = sqlite3.connect(CLOUD_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT,
            title TEXT,
            content TEXT,
            classification TEXT,
            updated_at TEXT,
            updated_by TEXT
        )
    """)
    conn.commit()
    conn.close()


# --- JWT setup ---
# Cloud only needs the public key to verify tokens
# Here is where you'd normally grab the crypto from AWS or Azure KV, or KeyCloak, what-have-you
# instead of a local file
PUBLIC_KEY_PATH = "keys/public.pem"
with open(PUBLIC_KEY_PATH, "rb") as f:
    PUBLIC_KEY = f.read()

JWT_ALGORITHM = "RS256"

def verify_token(token):
    """
    Verify JWT token and return payload or error information.
    
    Args:
        token: JWT token string to verify
    
    Returns:
        dict: Either payload with user claims or error dict with 'error' and 'details' keys
    """
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
        log_info("AUTH", payload.get('user', 'unknown'), "JWT token verified successfully")
        return payload
    except jwt.ExpiredSignatureError:
        log_warning("AUTH", "unknown", "Authentication failed: Token has expired")
        return {
            "error": "expired_token",
            "details": "Token has expired"
        }
    except jwt.InvalidSignatureError:
        log_warning("AUTH", "unknown", "Authentication failed: Invalid token signature")
        return {
            "error": "invalid_signature",
            "details": "Token signature verification failed"
        }
    except jwt.DecodeError as e:
        log_warning("AUTH", "unknown", f"Authentication failed: Token decode error - {str(e)}")
        return {
            "error": "decode_error",
            "details": f"Token could not be decoded: {str(e)}"
        }
    except jwt.InvalidTokenError as e:
        log_warning("AUTH", "unknown", f"Authentication failed: Invalid token - {str(e)}")
        return {
            "error": "invalid_token",
            "details": f"Invalid token: {str(e)}"
        }
    

# Validation helpers
VALID_CLASSIFICATIONS = {"CUI", "IL4", "IL5"}
REPORT_ID_REGEX = re.compile(r"^[A-Za-z0-9\-]+$")

def validate_report_data(data):
    """
    Validate incoming report data and return (is_valid, details)
    """
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object"

    required_fields = ["report_id", "title", "content", "classification", "updated_at", "updated_by"]
    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        return False, f"Missing required field(s): {', '.join(missing_fields)}"

    # Validate report_id format
    if not REPORT_ID_REGEX.match(data.get("report_id", "")):
        return False, "Invalid report_id format: only alphanumeric and hyphens allowed"

    # Validate classification
    if data.get("classification") not in VALID_CLASSIFICATIONS:
        return False, f"Invalid classification: must be one of {', '.join(sorted(VALID_CLASSIFICATIONS))}"

    # Validate title/content lengths
    title = data.get("title", "")
    content = data.get("content", "")
    if not title or len(title) > 255:
        return False, "Title is required and must be 1-255 characters"
    if not content or len(content) > 2000:
        return False, "Content is required and must be 1-2000 characters"

    # Validate updated_by
    if not data.get("updated_by"):
        return False, "updated_by is required"

    # Validate is_deleted if present
    if "is_deleted" in data:
        try:
            flag = int(data.get("is_deleted"))
            if flag not in (0, 1):
                return False, "is_deleted must be 0 or 1"
        except Exception:
            return False, "is_deleted must be an integer 0 or 1"

    # Validate updated_at parseability
    try:
        _ = datetime.datetime.fromisoformat(data.get("updated_at"))
    except Exception:
        try:
            _ = datetime.datetime.strptime(data.get("updated_at"), "%Y-%m-%dT%H:%M:%S.%f%z")
        except Exception:
            return False, "updated_at must be a valid ISO8601 timestamp"

    return True, "ok"


# Simple in-memory rate limiter (per-user/token or per-IP fallback)
RATE_LIMIT = int(os.getenv("CLOUD_RATE_LIMIT", "100"))
RATE_WINDOW = int(os.getenv("CLOUD_RATE_WINDOW", "60"))  # seconds
_rate_cache = {}

def _rate_limit_key_from_request(req, claims=None):
    if claims and isinstance(claims, dict) and claims.get("user"):
        return f"user:{claims.get('user')}"
    # fallback to IP
    return f"ip:{req.remote_addr or 'unknown'}"

def check_rate_limit(req, claims=None):
    key = _rate_limit_key_from_request(req, claims)
    now = int(time.time())
    window_start = now - RATE_WINDOW
    hits = _rate_cache.get(key, [])
    # Remove old timestamps
    hits = [t for t in hits if t >= window_start]
    if len(hits) >= RATE_LIMIT:
        # store updated list and return False
        _rate_cache[key] = hits
        return False
    # record hit
    hits.append(now)
    _rate_cache[key] = hits
    return True
    

def fix_timestamp(data):
    # Change the timestamp from string to datetime
    raw_ts = data["updated_at"]
    try:
        # parse ISO 8601 string into datetime
        # this should be all you have to do
        ts = datetime.datetime.fromisoformat(raw_ts)
    except Exception:
        # fallback: if string includes 'Z' or other formats
        ts = datetime.datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M:%S.%f%z")
    return ts


# --- Routes ---
@app.route("/api/sync", methods=["POST"])
def sync():
    user = "unknown"
    
    # Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        log_warning("/api/sync", user, "Authentication failed: Missing or invalid Authorization header")
        return jsonify({"error": "Unauthorized"}), 401
    
    token = auth_header.split(" ")[1]
    claims = verify_token(token)
    
    # Check if verification returned an error
    if "error" in claims:
        log_warning("/api/sync", user, f"Authentication failed: {claims['details']}")
        return jsonify({
            "error": claims["error"],
            "details": claims["details"]
        }), 401
    
    user = claims.get('user', 'unknown')
    # Rate limiting check
    if not check_rate_limit(request, claims):
        log_warning("/api/sync", user, "Rate limit exceeded")
        return jsonify({"error": "rate_limit_exceeded", "details": f"Rate limit of {RATE_LIMIT} requests per {RATE_WINDOW}s exceeded"}), 429
    log_info("/api/sync", user, f"Sync request received from user: {user}")

    # Validate request data
    data = request.json
    if not data:
        log_warning("/api/sync", user, "Invalid request: Request body is required")
        return jsonify({"error": "Invalid request", "details": "Request body is required"}), 400
    
    # Field validation
    valid, details = validate_report_data(data)
    if not valid:
        log_warning("/api/sync", user, f"Invalid request: {details}")
        return jsonify({"error": "Invalid request", "details": details}), 400

    # Sync logic: append new record to ledger
    session = get_session()

    try:
        data["updated_at"] = fix_timestamp(data)

        new_report = Report(
            report_id=data["report_id"],
            title=data["title"],
            content=data["content"],
            classification=data["classification"],
            updated_at=data["updated_at"],
            updated_by=data["updated_by"],
            is_deleted=int(data.get("is_deleted", 0))
        )
        session.add(new_report)
        session.commit()
        session.close()

        log_info("/api/sync", user, f"Successfully stored report: {data['report_id']}")
        return jsonify({"status": "ok"})
    
    except Exception as e:
        session.rollback()
        session.close()
        log_error("/api/sync", user, f"Database error during sync: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": "Failed to store report"
        }), 500

@app.route("/api/health", methods=["GET"])
def health():
    """
    Health check endpoint with database connectivity and statistics.
    Returns HTTP 503 if database is unreachable.
    """
    health_data = {
        "status": "running",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    # Check database connectivity and gather statistics
    try:
        session = get_session()
        
        # Test database connectivity by executing a simple query
        total_reports = session.query(Report).count()
        health_data["database_status"] = "connected"
        health_data["total_reports"] = total_reports
        
        # Get last sync timestamp (most recent updated_at)
        latest_report = session.query(Report).order_by(desc(Report.updated_at)).first()
        if latest_report:
            health_data["last_sync_timestamp"] = latest_report.updated_at.isoformat()
        else:
            health_data["last_sync_timestamp"] = None
        
        session.close()
        return jsonify(health_data), 200
        
    except Exception as e:
        # Database is unreachable or error occurred
        health_data["status"] = "degraded"
        health_data["database_status"] = "unreachable"
        health_data["error"] = str(e)
        return jsonify(health_data), 503

@app.route("/api/reports", methods=["GET"])
def get_reports():
    session = get_session()
    # Check for include_deleted query parameter (default: false)
    include_deleted = request.args.get("include_deleted", "false").lower() == "true"
    
    if include_deleted:
        reports = session.query(Report).all()
    else:
        reports = session.query(Report).filter(Report.is_deleted == 0).all()
    
    report_list = []
    for report in reports:
        report_list.append({
            "id": report.id,
            "report_id": report.report_id,
            "title": report.title,
            "content": report.content,
            "classification": report.classification,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            "updated_by": report.updated_by,
            "is_deleted": report.is_deleted
        })
    session.close()
    return jsonify(report_list)

@app.route("/api/reports/latest", methods=["GET"])
def get_latest_reports():
    session = get_session()
    # Get all non-deleted reports ordered by report_id and updated_at in descending order
    reports = session.query(Report).filter(Report.is_deleted == 0).order_by(Report.report_id, desc(Report.updated_at)).all()

    latest_by_id = {}
    for r in reports:
        if r.report_id not in latest_by_id:
            latest_by_id[r.report_id] = r  # first one we see is the latest, forget the rest

    report_list = []
    # spool up the latest reports only
    for report in latest_by_id.values():
        report_list.append({
            "id": report.id,
            "report_id": report.report_id,
            "title": report.title,
            "content": report.content,
            "classification": report.classification,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            "updated_by": report.updated_by
        })

    session.close()
    return jsonify(report_list)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8443)
