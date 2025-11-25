# cloud_app.py
import os
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from data_models import Report, Base
import jwt
import datetime
import sqlite3

CLOUD_DB_PATH = os.getenv("CLOUD_DB_PATH", "/app/data/cloud_db.sqlite")

app = Flask(__name__)
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
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
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
    # Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401
    token = auth_header.split(" ")[1]
    claims = verify_token(token)
    if not claims:
        return jsonify({"error": "Invalid token"}), 401

    # Sync logic: append new record to ledger
    data = request.json
    session = Session()

    data["updated_at"] = fix_timestamp(data)

    new_report = Report(
        report_id=data["report_id"],
        title=data["title"],
        content=data["content"],
        classification=data.get("classification", "CUI"),
        updated_at=data["updated_at"],
        updated_by=claims.get("user", "unknown")
    )
    session.add(new_report)
    session.commit()

    return jsonify({"status": "ok"})

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

@app.route("/api/reports", methods=["GET"])
def get_reports():
    session = Session()
    reports = session.query(Report).all()
    report_list = []
    for report in reports:
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

@app.route("/api/reports/latest", methods=["GET"])
def get_latest_reports():
    session = Session()
    # Get all reports ordered by report_id and updated_at in descending order
    reports = session.query(Report).order_by(Report.report_id, desc(Report.updated_at)).all()

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
