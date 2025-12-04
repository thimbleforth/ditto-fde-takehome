# edge_app.py
import os, requests, datetime, jwt
import random # this is purely for random #'s in the demo data
import logging
import database_manager

PRIVATE_KEY_PATH = os.getenv("PRIVATE_KEY_PATH", "private.pem")
CLOUD_URL = os.getenv("CLOUD_URL", "http://cloud:8443")
EDGE_USER = os.getenv("EDGE_USER")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "/app/data/edge.log")

JWT_ALGORITHM = "RS256"
# asymmetric encryption with RSA keys
# works better for NIST compliance

_PRIVATE_KEY = None

# Configure logging
def setup_logging():
    """Configure logging with file handler and console handler."""
    # Create logger
    logger = logging.getLogger('edge_app')
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(component)s] - %(message)s',
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

def log_info(component, message):
    """Log info message with component context."""
    logger.info(message, extra={'component': component})

def log_error(component, message):
    """Log error message with component context."""
    logger.error(message, extra={'component': component})

def log_warning(component, message):
    """Log warning message with component context."""
    logger.warning(message, extra={'component': component})

def _load_private_key():
    """Load private key from file (lazy loading for testability)."""
    global _PRIVATE_KEY
    if _PRIVATE_KEY is None:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            _PRIVATE_KEY = f.read()
    return _PRIVATE_KEY

def issue_token():
    # create a token valid for 30 minutes
    payload = {
        "user": EDGE_USER,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, _load_private_key(), algorithm=JWT_ALGORITHM)
    log_info("AUTH", f"Generated JWT token for user: {EDGE_USER}")
    return token


def sync_single_report(report):
    """
    Handle individual report transmission to cloud server.
    
    Args:
        report: Dictionary containing report data
    
    Returns:
        dict: Result with status and optional error message
    """
    payload = {
        "report_id": report["report_id"],
        "title": report["title"],
        "content": report["content"],
        "classification": report["classification"],
        "updated_at": report["updated_at"],
        "updated_by": report["updated_by"]
    }
    
    # Add is_deleted flag if present
    if report.get("is_deleted"):
        payload["is_deleted"] = report["is_deleted"]
    
    log_info("SYNC", f"Attempting to sync report: {report['report_id']}")
    
    token = issue_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.post(f"{CLOUD_URL}/api/sync", json=payload, headers=headers, timeout=30)
        
        if r.status_code == 200:
            log_info("SYNC", f"Successfully synced report: {report['report_id']}")
            return {
                "status": "success",
                "report_id": report["report_id"],
                "db_id": report["id"]
            }
        else:
            log_error("SYNC", f"Failed to sync report {report['report_id']}: HTTP {r.status_code} - {r.text}")
            return {
                "status": "failed",
                "report_id": report["report_id"],
                "error": f"HTTP {r.status_code}: {r.text}"
            }
    except requests.exceptions.ConnectionError as e:
        log_error("SYNC", f"Connection failed for report {report['report_id']}: {str(e)}")
        return {
            "status": "failed",
            "report_id": report["report_id"],
            "error": f"Connection failed: {str(e)}"
        }
    except requests.exceptions.Timeout as e:
        log_error("SYNC", f"Request timeout for report {report['report_id']}: {str(e)}")
        return {
            "status": "failed",
            "report_id": report["report_id"],
            "error": f"Request timeout: {str(e)}"
        }
    except Exception as e:
        log_error("SYNC", f"Unexpected error syncing report {report['report_id']}: {str(e)}")
        return {
            "status": "failed",
            "report_id": report["report_id"],
            "error": f"Unexpected error: {str(e)}"
        }


def sync_to_cloud():
    """
    Synchronize all unsynchronized reports to the cloud server.
    
    Returns:
        dict: Sync summary with counts and detailed results
    """
    # Get all unsynchronized reports from database
    unsync_reports = database_manager.get_unsynchronized_reports()
    
    log_info("SYNC", f"Starting sync operation with {len(unsync_reports)} unsynchronized reports")
    
    if not unsync_reports:
        log_info("SYNC", "No reports to synchronize")
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "reports": []
        }
    
    successful = []
    failed = []
    
    # Sync each report individually
    for report in unsync_reports:
        result = sync_single_report(report)
        
        if result["status"] == "success":
            # Mark as synchronized in database
            database_manager.mark_as_synchronized(result["db_id"])
            successful.append(result)
        else:
            failed.append(result)
    
    # Build sync summary
    summary = {
        "total": len(unsync_reports),
        "successful": len(successful),
        "failed": len(failed),
        "reports": successful + failed
    }
    
    log_info("SYNC", f"Sync operation completed: {len(successful)} successful, {len(failed)} failed")
    
    return summary


def display_sync_summary(summary):
    """
    Print sync results to console with detailed information.
    
    Args:
        summary: Dictionary containing sync summary with counts and report details
    """
    print("\n" + "="*60)
    print("SYNCHRONIZATION SUMMARY")
    print("="*60)
    
    if summary["total"] == 0:
        print("No reports to synchronize.")
        print("="*60 + "\n")
        return
    
    print(f"Total reports processed: {summary['total']}")
    print(f"Successfully synchronized: {summary['successful']}")
    print(f"Failed synchronizations: {summary['failed']}")
    print("-"*60)
    
    # Display successfully synchronized reports
    if summary["successful"] > 0:
        print("\nSUCCESSFULLY SYNCHRONIZED REPORTS:")
        for report in summary["reports"]:
            if report["status"] == "success":
                print(f"  ✓ {report['report_id']}")
    
    # Display failed synchronizations with error details
    if summary["failed"] > 0:
        print("\nFAILED SYNCHRONIZATIONS:")
        for report in summary["reports"]:
            if report["status"] == "failed":
                print(f"  ✗ {report['report_id']}")
                print(f"    Error: {report['error']}")
    
    print("="*60 + "\n")

if __name__ == "__main__":
    # create the local edge device database
    database_manager.init_db()

    # simulate some report creation and syncing
    # example report from edge1:
    if EDGE_USER == "edge1":
        rand_suffix = random.randint(1000, 9999)
        report1 = {
            "title": f"Edge Report {rand_suffix}",
            "report_id": f"edge1-report-{rand_suffix}",
            "content": "This is a report created at edge device #1.",
            "classification": "IL4",
            "updated_by": EDGE_USER
        }

        database_manager.create_report(
            report1["report_id"],
            report1["title"],
            report1["content"],
            report1["classification"],
            report1["updated_by"]
        )
        summary = sync_to_cloud()
        display_sync_summary(summary)
    elif EDGE_USER == "edge2":
        rand_suffix = random.randint(1000, 9999)
        report2 = {
            "title": f"Edge Report {rand_suffix}",
            "report_id": f"edge2-report-{rand_suffix}",
            "content": "This is a report created at edge device #2.",
            "classification": "CUI",
            "updated_by": EDGE_USER
        }

        database_manager.create_report(
            report2["report_id"],
            report2["title"],
            report2["content"],
            report2["classification"],
            report2["updated_by"]
        )
        summary = sync_to_cloud()
        display_sync_summary(summary)
    
    # and now, for two edge devices to edit the same report ID separately, report 050.
    if EDGE_USER == "edge1":
        database_manager.create_report(
            f"shared-report-050",
            "Shared Report from Edge 1",
            "This is the version from edge device #1.",
            "IL5",
            EDGE_USER
        )
        summary = sync_to_cloud()
        display_sync_summary(summary)

    if EDGE_USER == "edge2":
        database_manager.create_report(
            f"shared-report-050",
            "Shared Report from Edge 2",
            "This is the version from edge device #2.",
            "IL5",
            EDGE_USER
        )
        summary = sync_to_cloud()
        display_sync_summary(summary)

    # these containers are running this exact same logic at the exact same time when they spawn... so whoever gets there first is a matter of fractions of a second. It probably won't be the same every time.

    # ergo: just like in the real world, we have a conflict! Both edge devices created a report with the same report_id but different content.
    
    # right now, the cloud app will store both versions as separate records so you have history; but that's because the DB is doubling as a log server for the sake of this demo. In a real-world app, you'd toss the older change and move on with your day.