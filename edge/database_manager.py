# database_manager.py
import sqlite3
import datetime
import os


def _get_db_path():
    """Get the database path from environment or use default."""
    return os.getenv("EDGE_DB_PATH", "/app/data/edge_db.sqlite")


def init_db():
    """Initialize the database schema with synchronization tracking."""
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            classification TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            is_synchronized INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            last_retry_at TEXT
        )
    """)
    # Create indexes for query performance
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_report_id ON reports(report_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_synchronized ON reports(is_synchronized)
    """)
    conn.commit()
    conn.close()


def create_report(report_id, title, content, classification, analyst):
    """
    Insert a new report with sync status set to unsynchronized.
    
    Args:
        report_id: Unique identifier for the report
        title: Report title
        content: Report content
        classification: Security classification (CUI, IL4, IL5)
        analyst: Analyst identifier
    
    Returns:
        int: The database ID of the created report
    """
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        """INSERT INTO reports 
           (report_id, title, content, classification, updated_at, updated_by, is_deleted, is_synchronized, retry_count) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (report_id, title, content, classification, timestamp, analyst, 0, 0, 0)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def read_report(report_id):
    """
    Retrieve a single report by report_id.
    
    Args:
        report_id: The report_id to retrieve
    
    Returns:
        dict: Report data or None if not found
    """
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT id, report_id, title, content, classification, updated_at, updated_by, 
                  is_deleted, is_synchronized, retry_count, last_retry_at 
           FROM reports 
           WHERE report_id = ? 
           ORDER BY updated_at DESC 
           LIMIT 1""",
        (report_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def read_all_reports():
    """
    Retrieve all reports including from other analysts.
    
    Returns:
        list[dict]: List of all report records
    """
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT id, report_id, title, content, classification, updated_at, updated_by, 
                  is_deleted, is_synchronized, retry_count, last_retry_at 
           FROM reports 
           ORDER BY updated_at DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def update_report(report_id, title, content, classification, analyst):
    """
    Update a report by creating a new version with updated timestamp.
    
    Args:
        report_id: The report_id to update
        title: New title
        content: New content
        classification: New classification
        analyst: Analyst making the update
    
    Returns:
        int: The database ID of the new version
    """
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        """INSERT INTO reports 
           (report_id, title, content, classification, updated_at, updated_by, is_deleted, is_synchronized, retry_count) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (report_id, title, content, classification, timestamp, analyst, 0, 0, 0)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def delete_report(report_id, analyst):
    """
    Soft delete a report with deletion timestamp.
    
    Args:
        report_id: The report_id to delete
        analyst: Analyst performing the deletion
    
    Returns:
        int: The database ID of the deleted version
    """
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Create a new version marked as deleted
    cur.execute(
        """INSERT INTO reports 
           (report_id, title, content, classification, updated_at, updated_by, is_deleted, is_synchronized, retry_count) 
           SELECT report_id, title, content, classification, ?, ?, 1, 0, 0
           FROM reports 
           WHERE report_id = ? 
           ORDER BY updated_at DESC 
           LIMIT 1""",
        (timestamp, analyst, report_id)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_unsynchronized_reports():
    """
    Query reports where is_synchronized = 0.
    
    Returns:
        list[dict]: List of unsynchronized report records
    """
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT id, report_id, title, content, classification, updated_at, updated_by, 
                  is_deleted, is_synchronized, retry_count, last_retry_at 
           FROM reports 
           WHERE is_synchronized = 0 
           ORDER BY updated_at ASC"""
    )
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def mark_as_synchronized(report_id):
    """
    Update sync status for a report after successful synchronization.
    
    Args:
        report_id: The database ID (not report_id) to mark as synchronized
    """
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    cur.execute(
        """UPDATE reports 
           SET is_synchronized = 1, retry_count = 0, last_retry_at = NULL 
           WHERE id = ?""",
        (report_id,)
    )
    conn.commit()
    conn.close()


def increment_retry_count(report_id):
    """
    Increment the retry counter for a failed synchronization attempt.
    
    Args:
        report_id: The database ID (not report_id) to increment retry count
    """
    conn = sqlite3.connect(_get_db_path())
    cur = conn.cursor()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur.execute(
        """UPDATE reports 
           SET retry_count = retry_count + 1, last_retry_at = ? 
           WHERE id = ?""",
        (timestamp, report_id)
    )
    conn.commit()
    conn.close()


def get_failed_reports_for_retry():
    """
    Query reports that have failed sync but haven't exceeded retry limit.
    
    Returns:
        list[dict]: List of failed report records eligible for retry
    """
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT id, report_id, title, content, classification, updated_at, updated_by, 
                  is_deleted, is_synchronized, retry_count, last_retry_at 
           FROM reports 
           WHERE is_synchronized = 0 AND retry_count > 0 AND retry_count < 5
           ORDER BY last_retry_at ASC"""
    )
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def calculate_backoff_delay(retry_count):
    """
    Calculate exponential backoff delay in seconds.
    
    Args:
        retry_count: Number of retry attempts
    
    Returns:
        int: Delay in seconds (1s, 2s, 4s, 8s, max 60s)
    """
    if retry_count <= 0:
        return 0
    
    # Exponential backoff: 2^(retry_count-1) seconds
    delay = 2 ** (retry_count - 1)
    
    # Cap at 60 seconds
    return min(delay, 60)
