# edge_app.py
import os, requests, datetime, jwt,sqlite3
import random # this is purely for random #'s in the demo data

PRIVATE_KEY_PATH = os.getenv("PRIVATE_KEY_PATH", "private.pem")
CLOUD_URL = os.getenv("CLOUD_URL", "http://cloud:8443")
EDGE_USER = os.getenv("EDGE_USER")
EDGE_DB_PATH = os.getenv("EDGE_DB_PATH", "/app/data/edge_db.sqlite")

with open(PRIVATE_KEY_PATH, "rb") as f:
    PRIVATE_KEY = f.read()

JWT_ALGORITHM = "RS256"
# asymmetric encryption with RSA keys
# works better for NIST compliance

def issue_token():
    # create a token valid for 30 minutes
    payload = {
        "user": EDGE_USER,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, PRIVATE_KEY, algorithm=JWT_ALGORITHM)
    return token

# including this here just to create the DB schema on the edge device
def init_db():
    conn = sqlite3.connect(EDGE_DB_PATH)
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


def create_report(report_id, title, content, classification, analyst):
    conn = sqlite3.connect(EDGE_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reports (report_id, title, content, classification, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
        (report_id, title, content, classification,
         datetime.datetime.now(datetime.timezone.utc).isoformat(), analyst)
    )
    conn.commit()

def sync_to_cloud():
    # this sync runs through the whole sqlitedb and sends each record to the cloud app
    # in a real-world app, you'd want to track what had already been sent
    # and that would be another flag you put down in data_models.py

    conn = sqlite3.connect(EDGE_DB_PATH)
    cur = conn.cursor()
    for row in cur.execute("SELECT report_id, title, content, classification, updated_at, updated_by FROM reports"):
        payload = {
            "report_id": row[0],
            "title": row[1],
            "content": row[2],
            "classification": row[3],
            "updated_at": row[4],
            "updated_by": row[5]
        }
        token = issue_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.post(f"{CLOUD_URL}/api/sync", json=payload, headers=headers)
            print("Sync result:", r.json())
        except Exception as e:
            print("Sync failed:", e)

if __name__ == "__main__":
    # create the local edge device database
    init_db()

    # simulate some report creation and syncing
    # example report from edge1:
    if EDGE_USER == "edge1":
        rand_suffix = random.randint(1000, 9999)
        report1 = {
            "title": f"Edge Report {rand_suffix}",
            "report_id": f"edge1-report-{rand_suffix}",
            "content": "This is a report created at edge device #1.",
            "classification": "IL4",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_by": EDGE_USER
        }

        create_report(
            report1["report_id"],
            report1["title"],
            report1["content"],
            report1["classification"],
            report1["updated_by"]
        )
        sync_to_cloud()
    elif EDGE_USER == "edge2":
        rand_suffix = random.randint(1000, 9999)
        report2 = {
            "title": f"Edge Report {rand_suffix}",
            "report_id": f"edge2-report-{rand_suffix}",
            "content": "This is a report created at edge device #2.",
            "classification": "CUI",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_by": EDGE_USER
        }

        create_report(
            report2["report_id"],
            report2["title"],
            report2["content"],
            report2["classification"],
            report2["updated_by"]
        )
        sync_to_cloud()
    
    # and now, for two edge devices to edit the same report ID separately, report 050.
    if EDGE_USER == "edge1":
        create_report(
            f"shared-report-050",
            "Shared Report from Edge 1",
            "This is the version from edge device #1.",
            "IL5",
            EDGE_USER
        )
        sync_to_cloud()

    if EDGE_USER == "edge2":
        create_report(
            f"shared-report-050",
            "Shared Report from Edge 2",
            "This is the version from edge device #2.",
            "IL5",
            EDGE_USER
        )
        sync_to_cloud()

    # these containers are running this exact same logic at the exact same time when they spawn... so whoever gets there first is a matter of fractions of a second. It probably won't be the same every time.

    # ergo: just like in the real world, we have a conflict! Both edge devices created a report with the same report_id but different content.
    
    # right now, the cloud app will store both versions as separate records so you have history; but that's because the DB is doubling as a log server for the sake of this demo. In a real-world app, you'd toss the older change and move on with your day.