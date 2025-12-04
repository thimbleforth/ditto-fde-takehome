# test_retry_logic.py
import unittest
import os
import tempfile
import datetime
import time
from database_manager import (
    init_db,
    create_report,
    mark_as_synchronized,
    increment_retry_count,
    get_failed_reports_for_retry,
    calculate_backoff_delay
)


class TestRetryLogic(unittest.TestCase):
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['EDGE_DB_PATH'] = self.temp_db.name
        init_db()
    
    def tearDown(self):
        """Clean up the temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff calculation for different retry counts."""
        # Test backoff delays
        self.assertEqual(calculate_backoff_delay(0), 0)
        self.assertEqual(calculate_backoff_delay(1), 1)   # 2^0 = 1
        self.assertEqual(calculate_backoff_delay(2), 2)   # 2^1 = 2
        self.assertEqual(calculate_backoff_delay(3), 4)   # 2^2 = 4
        self.assertEqual(calculate_backoff_delay(4), 8)   # 2^3 = 8
        self.assertEqual(calculate_backoff_delay(5), 16)  # 2^4 = 16
        self.assertEqual(calculate_backoff_delay(6), 32)  # 2^5 = 32
        self.assertEqual(calculate_backoff_delay(7), 60)  # 2^6 = 64, capped at 60
        self.assertEqual(calculate_backoff_delay(10), 60) # Should be capped at 60
    
    def test_retry_limit_enforcement(self):
        """Test that retry limit of 5 is enforced."""
        # Create a report
        report_id = create_report("test-retry-001", "Title", "Content", "IL4", "analyst1")
        
        # Increment retry count 5 times
        for i in range(5):
            increment_retry_count(report_id)
        
        # Report should not appear in failed reports for retry (limit exceeded)
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 0)
    
    def test_retry_counter_reset_after_success(self):
        """Test that retry counter is reset after successful sync."""
        # Create a report
        report_id = create_report("test-retry-002", "Title", "Content", "IL4", "analyst1")
        
        # Increment retry count a few times
        increment_retry_count(report_id)
        increment_retry_count(report_id)
        increment_retry_count(report_id)
        
        # Verify retry count is 3
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 1)
        self.assertEqual(failed_reports[0]['retry_count'], 3)
        
        # Mark as synchronized (should reset retry counter)
        mark_as_synchronized(report_id)
        
        # Verify report is no longer in failed reports
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 0)
    
    def test_increment_retry_count(self):
        """Test that increment_retry_count properly increments the counter."""
        # Create a report
        report_id = create_report("test-retry-003", "Title", "Content", "IL4", "analyst1")
        
        # Increment retry count
        increment_retry_count(report_id)
        
        # Verify retry count is 1
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 1)
        self.assertEqual(failed_reports[0]['retry_count'], 1)
        self.assertIsNotNone(failed_reports[0]['last_retry_at'])
        
        # Increment again
        increment_retry_count(report_id)
        
        # Verify retry count is 2
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 1)
        self.assertEqual(failed_reports[0]['retry_count'], 2)
    
    def test_get_failed_reports_for_retry_excludes_never_tried(self):
        """Test that get_failed_reports_for_retry excludes reports that have never been tried."""
        # Create reports
        report_id1 = create_report("test-retry-004", "Title 1", "Content 1", "IL4", "analyst1")
        report_id2 = create_report("test-retry-005", "Title 2", "Content 2", "IL5", "analyst2")
        
        # Increment retry count for only one report
        increment_retry_count(report_id1)
        
        # Only the report with retry_count > 0 should be returned
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 1)
        self.assertEqual(failed_reports[0]['report_id'], "test-retry-004")
    
    def test_get_failed_reports_for_retry_excludes_synchronized(self):
        """Test that get_failed_reports_for_retry excludes synchronized reports."""
        # Create a report
        report_id = create_report("test-retry-006", "Title", "Content", "IL4", "analyst1")
        
        # Increment retry count
        increment_retry_count(report_id)
        
        # Verify it appears in failed reports
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 1)
        
        # Mark as synchronized
        mark_as_synchronized(report_id)
        
        # Should no longer appear in failed reports
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 0)
    
    def test_get_failed_reports_for_retry_excludes_exceeded_limit(self):
        """Test that reports exceeding retry limit are excluded."""
        # Create reports with different retry counts
        report_id1 = create_report("test-retry-007", "Title 1", "Content 1", "IL4", "analyst1")
        report_id2 = create_report("test-retry-008", "Title 2", "Content 2", "IL5", "analyst2")
        report_id3 = create_report("test-retry-009", "Title 3", "Content 3", "CUI", "analyst3")
        
        # Set different retry counts
        for i in range(2):
            increment_retry_count(report_id1)  # retry_count = 2
        
        for i in range(4):
            increment_retry_count(report_id2)  # retry_count = 4
        
        for i in range(5):
            increment_retry_count(report_id3)  # retry_count = 5 (exceeded)
        
        # Only reports with retry_count < 5 should be returned
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 2)
        
        report_ids = [r['report_id'] for r in failed_reports]
        self.assertIn("test-retry-007", report_ids)
        self.assertIn("test-retry-008", report_ids)
        self.assertNotIn("test-retry-009", report_ids)
    
    def test_last_retry_at_timestamp_updated(self):
        """Test that last_retry_at timestamp is updated on each retry."""
        # Create a report
        report_id = create_report("test-retry-010", "Title", "Content", "IL4", "analyst1")
        
        # First increment
        increment_retry_count(report_id)
        failed_reports = get_failed_reports_for_retry()
        first_timestamp = failed_reports[0]['last_retry_at']
        self.assertIsNotNone(first_timestamp)
        
        # Wait a moment
        time.sleep(0.1)
        
        # Second increment
        increment_retry_count(report_id)
        failed_reports = get_failed_reports_for_retry()
        second_timestamp = failed_reports[0]['last_retry_at']
        
        # Timestamps should be different
        self.assertNotEqual(first_timestamp, second_timestamp)
        self.assertGreater(second_timestamp, first_timestamp)
    
    def test_multiple_failed_reports_ordering(self):
        """Test that failed reports are ordered by last_retry_at."""
        # Create multiple reports
        report_id1 = create_report("test-retry-011", "Title 1", "Content 1", "IL4", "analyst1")
        report_id2 = create_report("test-retry-012", "Title 2", "Content 2", "IL5", "analyst2")
        report_id3 = create_report("test-retry-013", "Title 3", "Content 3", "CUI", "analyst3")
        
        # Increment in specific order with delays
        increment_retry_count(report_id2)
        time.sleep(0.1)
        increment_retry_count(report_id1)
        time.sleep(0.1)
        increment_retry_count(report_id3)
        
        # Get failed reports (should be ordered by last_retry_at ASC)
        failed_reports = get_failed_reports_for_retry()
        self.assertEqual(len(failed_reports), 3)
        
        # First should be the oldest retry
        self.assertEqual(failed_reports[0]['report_id'], "test-retry-012")
        self.assertEqual(failed_reports[1]['report_id'], "test-retry-011")
        self.assertEqual(failed_reports[2]['report_id'], "test-retry-013")


if __name__ == '__main__':
    unittest.main()
