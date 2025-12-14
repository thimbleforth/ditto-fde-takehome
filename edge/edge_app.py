# edge_app.py
import os, requests, datetime, jwt
import random # this is purely for random #'s in the demo data
import logging
import threading
import time
import database_manager
import argparse

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


def sync_single_report(report, retry_auth=True):
    """
    Handle individual report transmission to cloud server.
    
    Args:
        report: Dictionary containing report data
        retry_auth: Whether to retry once with new token on 401 error (default: True)
    
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
        elif r.status_code == 401 and retry_auth:
            # Authentication failed - try regenerating token and retry once
            log_warning("SYNC", f"Authentication failed for report {report['report_id']}, regenerating token and retrying")
            
            try:
                error_data = r.json()
                error_type = error_data.get("error", "unknown")
                error_details = error_data.get("details", "Unknown authentication error")
                log_info("SYNC", f"Authentication error type: {error_type} - {error_details}")
            except Exception:
                log_warning("SYNC", "Could not parse authentication error response")
            
            # Regenerate token and retry (with retry_auth=False to prevent infinite loop)
            log_info("SYNC", f"Retrying sync for report {report['report_id']} with new token")
            return sync_single_report(report, retry_auth=False)
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
    skipped = []
    
    # Sync each report individually
    for report in unsync_reports:
        # Check if report has exceeded retry limit
        if report.get("retry_count", 0) >= 5:
            log_warning("SYNC", f"Report {report['report_id']} has exceeded retry limit (5 attempts)")
            skipped.append({
                "status": "skipped",
                "report_id": report["report_id"],
                "error": "Exceeded maximum retry attempts (5)"
            })
            continue
        
        result = sync_single_report(report)
        
        if result["status"] == "success":
            # Mark as synchronized in database and reset retry counter
            database_manager.mark_as_synchronized(result["db_id"])
            successful.append(result)
        else:
            # Increment retry counter for failed sync
            database_manager.increment_retry_count(result["db_id"])
            failed.append(result)
    
    # Build sync summary
    summary = {
        "total": len(unsync_reports),
        "successful": len(successful),
        "failed": len(failed),
        "skipped": len(skipped),
        "reports": successful + failed + skipped
    }
    
    log_info("SYNC", f"Sync operation completed: {len(successful)} successful, {len(failed)} failed, {len(skipped)} skipped")
    
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
    if summary.get("skipped", 0) > 0:
        print(f"Skipped (retry limit exceeded): {summary['skipped']}")
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
    
    # Display skipped reports
    if summary.get("skipped", 0) > 0:
        print("\nSKIPPED REPORTS (RETRY LIMIT EXCEEDED):")
        for report in summary["reports"]:
            if report["status"] == "skipped":
                print(f"  ⊘ {report['report_id']}")
                print(f"    Reason: {report['error']}")
    
    print("="*60 + "\n")


def retry_failed_reports():
    """
    Attempt to resync failed reports that are eligible for retry.
    Uses exponential backoff based on retry count.
    
    Returns:
        dict: Retry summary with counts and detailed results
    """
    # Get failed reports eligible for retry
    failed_reports = database_manager.get_failed_reports_for_retry()
    
    if not failed_reports:
        log_info("RETRY", "No failed reports eligible for retry")
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "reports": []
        }
    
    log_info("RETRY", f"Found {len(failed_reports)} failed reports eligible for retry")
    
    successful = []
    failed = []
    skipped = []
    
    for report in failed_reports:
        retry_count = report.get("retry_count", 0)
        last_retry_at = report.get("last_retry_at")
        
        # Calculate backoff delay
        backoff_delay = database_manager.calculate_backoff_delay(retry_count)
        
        # Check if enough time has passed since last retry
        if last_retry_at:
            try:
                last_retry_time = datetime.datetime.fromisoformat(last_retry_at)
                current_time = datetime.datetime.now(datetime.timezone.utc)
                time_since_retry = (current_time - last_retry_time).total_seconds()
                
                if time_since_retry < backoff_delay:
                    log_info("RETRY", f"Skipping report {report['report_id']} - backoff delay not met ({time_since_retry:.0f}s < {backoff_delay}s)")
                    skipped.append({
                        "status": "skipped",
                        "report_id": report["report_id"],
                        "error": f"Backoff delay not met (waiting {backoff_delay - time_since_retry:.0f}s)"
                    })
                    continue
            except (ValueError, TypeError) as e:
                log_warning("RETRY", f"Could not parse last_retry_at for report {report['report_id']}: {e}")
        
        # Attempt to sync the report
        log_info("RETRY", f"Retrying report {report['report_id']} (attempt {retry_count + 1}/5)")
        result = sync_single_report(report)
        
        if result["status"] == "success":
            # Mark as synchronized and reset retry counter
            database_manager.mark_as_synchronized(result["db_id"])
            successful.append(result)
            log_info("RETRY", f"Successfully synced report {report['report_id']} on retry")
        else:
            # Increment retry counter
            database_manager.increment_retry_count(result["db_id"])
            failed.append(result)
            log_warning("RETRY", f"Retry failed for report {report['report_id']}: {result.get('error', 'Unknown error')}")
    
    summary = {
        "total": len(failed_reports),
        "successful": len(successful),
        "failed": len(failed),
        "skipped": len(skipped),
        "reports": successful + failed + skipped
    }
    
    log_info("RETRY", f"Retry operation completed: {len(successful)} successful, {len(failed)} failed, {len(skipped)} skipped")
    
    return summary


def retry_scheduler(interval_seconds=300, stop_event=None):
    """
    Background thread that periodically checks for failed reports and retries them.
    
    Args:
        interval_seconds: Time between retry checks (default 300 = 5 minutes)
        stop_event: Threading event to signal shutdown
    """
    log_info("RETRY_SCHEDULER", f"Starting retry scheduler with {interval_seconds}s interval")
    
    while True:
        if stop_event and stop_event.is_set():
            log_info("RETRY_SCHEDULER", "Retry scheduler stopping")
            break
        
        try:
            # Wait for the interval or until stop event is set
            if stop_event:
                if stop_event.wait(interval_seconds):
                    break
            else:
                time.sleep(interval_seconds)
            
            # Attempt to retry failed reports
            log_info("RETRY_SCHEDULER", "Running scheduled retry check")
            summary = retry_failed_reports()
            
            # Log summary if there were any reports processed
            if summary["total"] > 0:
                log_info("RETRY_SCHEDULER", 
                        f"Retry check completed: {summary['successful']} successful, "
                        f"{summary['failed']} failed, {summary['skipped']} skipped")
        
        except Exception as e:
            log_error("RETRY_SCHEDULER", f"Error in retry scheduler: {str(e)}")
            # Continue running even if there's an error


def start_retry_scheduler(interval_seconds=300):
    """
    Start the retry scheduler in a background thread.
    
    Args:
        interval_seconds: Time between retry checks (default 300 = 5 minutes)
    
    Returns:
        tuple: (thread, stop_event) for controlling the scheduler
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=retry_scheduler,
        args=(interval_seconds, stop_event),
        daemon=True,
        name="RetryScheduler"
    )
    thread.start()
    log_info("RETRY_SCHEDULER", "Retry scheduler thread started")
    return thread, stop_event


if __name__ == "__main__":
    # create the local edge device database
    database_manager.init_db()
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", action="store_true", help="Run interactive CLI instead of demo mode")
    args = parser.parse_args()

    # Start the retry scheduler in the background (checks every 5 minutes)
    retry_thread, stop_event = start_retry_scheduler(interval_seconds=300)

    # If CLI flag is set, import CLI module and run interactive menu
    if args.cli:
        from cli_interface import run_cli_loop
        run_cli_loop()
        # Ensure background scheduler stops
        stop_event.set()
        retry_thread.join(timeout=5)
        log_info("MAIN", "CLI session ended; exiting.")
        raise SystemExit(0)

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
    
    # Keep the main thread alive to allow retry scheduler to run
    # In a real application, this would be part of a long-running service
    log_info("MAIN", "Edge application running with retry scheduler. Press Ctrl+C to exit.")
    try:
        # Keep main thread alive
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log_info("MAIN", "Shutting down edge application")
        stop_event.set()
        retry_thread.join(timeout=5)