# cloud_app.py
import os
import logging
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from data_models import Report, Base
import jwt
import datetime
import sqlite3

CLOUD_DB_PATH = os.getenv("CLOUD_DB_PATH", "/app/data/cloud_db.sqlite")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "/app/data/cloud.log")

app = Flask(__name__)

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
engine = create_engine(f"sqlite:///{CLOUD_DB_PATH}")   # swap for Postgres in production, sqlitedb is fine for now
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

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
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
        log_info("AUTH", payload.get('user', 'unknown'), "JWT token verified successfully")
        return payload
    except jwt.ExpiredSignatureError:
        log_warning("AUTH", "unknown", "Authentication failed: Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        log_warning("AUTH", "unknown", f"Authentication failed: Invalid token - {str(e)}")
        return None
    

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
    if not claims:
        log_warning("/api/sync", user, "Authentication failed: Invalid token")
        return jsonify({"error": "Invalid token"}), 401
    
    user = claims.get('user', 'unknown')
    log_info("/api/sync", user, f"Sync request received from user: {user}")

    # Validate request data
    data = request.json
    if not data:
        log_warning("/api/sync", user, "Invalid request: Request body is required")
        return jsonify({"error": "Invalid request", "details": "Request body is required"}), 400
    
    required_fields = ["report_id", "title", "content", "classification", "updated_at", "updated_by"]
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        log_warning("/api/sync", user, f"Invalid request: Missing required field(s): {', '.join(missing_fields)}")
        return jsonify({
            "error": "Invalid request",
            "details": f"Missing required field(s): {', '.join(missing_fields)}"
        }), 400

    # Sync logic: append new record to ledger
    session = Session()

    try:
        data["updated_at"] = fix_timestamp(data)

        new_report = Report(
            report_id=data["report_id"],
            title=data["title"],
            content=data["content"],
            classification=data["classification"],
            updated_at=data["updated_at"],
            updated_by=data["updated_by"],
            is_deleted=data.get("is_deleted", 0)
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
    return jsonify({
        "status": "running",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

@app.route("/api/reports", methods=["GET"])
def get_reports():
    session = Session()
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
    return jsonify(report_list)

@app.route("/api/reports/latest", methods=["GET"])
def get_latest_reports():
    session = Session()
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

    return jsonify(report_list)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8443)
