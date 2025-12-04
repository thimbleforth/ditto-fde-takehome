# test_database_manager.py
import unittest
import os
import tempfile
import sqlite3
from database_manager import (
    init_db,
    create_report,
    read_report,
    read_all_reports,
    update_report,
    delete_report,
    get_unsynchronized_reports,
    mark_as_synchronized
)


class TestDatabaseManager(unittest.TestCase):
    
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
    
    def test_create_report_with_valid_data(self):
        """Test report creation with valid data."""
        report_id = create_report(
            report_id="test-001",
            title="Test Report",
            content="Test content",
            classification="IL4",
            analyst="analyst1"
        )
        
        self.assertIsNotNone(report_id)
        self.assertGreater(report_id, 0)
        
        # Verify the report was created
        report = read_report("test-001")
        self.assertIsNotNone(report)
        self.assertEqual(report['report_id'], "test-001")
        self.assertEqual(report['title'], "Test Report")
        self.assertEqual(report['content'], "Test content")
        self.assertEqual(report['classification'], "IL4")
        self.assertEqual(report['updated_by'], "analyst1")
        self.assertEqual(report['is_deleted'], 0)
        self.assertEqual(report['is_synchronized'], 0)
    
    def test_read_report_retrieves_single_report(self):
        """Test report retrieval by report_id."""
        create_report("test-002", "Title", "Content", "CUI", "analyst1")
        
        report = read_report("test-002")
        self.assertIsNotNone(report)
        self.assertEqual(report['report_id'], "test-002")
    
    def test_read_report_returns_none_for_nonexistent(self):
        """Test that read_report returns None for non-existent report_id."""
        report = read_report("nonexistent")
        self.assertIsNone(report)
    
    def test_read_all_reports_retrieves_all(self):
        """Test retrieval of all reports including from other analysts."""
        create_report("test-003", "Title 1", "Content 1", "IL4", "analyst1")
        create_report("test-004", "Title 2", "Content 2", "IL5", "analyst2")
        create_report("test-005", "Title 3", "Content 3", "CUI", "analyst3")
        
        reports = read_all_reports()
        self.assertEqual(len(reports), 3)
        
        # Verify all reports are present
        report_ids = [r['report_id'] for r in reports]
        self.assertIn("test-003", report_ids)
        self.assertIn("test-004", report_ids)
        self.assertIn("test-005", report_ids)
    
    def test_update_creates_new_version(self):
        """Test that update creates a new version with updated timestamp."""
        # Create initial report
        create_report("test-006", "Original Title", "Original Content", "IL4", "analyst1")
        
        # Update the report
        new_id = update_report("test-006", "Updated Title", "Updated Content", "IL5", "analyst1")
        
        self.assertIsNotNone(new_id)
        self.assertGreater(new_id, 0)
        
        # Verify new version exists
        report = read_report("test-006")
        self.assertEqual(report['title'], "Updated Title")
        self.assertEqual(report['content'], "Updated Content")
        self.assertEqual(report['classification'], "IL5")
        
        # Verify both versions exist in database
        all_reports = read_all_reports()
        test_006_reports = [r for r in all_reports if r['report_id'] == "test-006"]
        self.assertEqual(len(test_006_reports), 2)
    
    def test_soft_delete_functionality(self):
        """Test soft delete marks report as deleted."""
        # Create a report
        create_report("test-007", "Title", "Content", "CUI", "analyst1")
        
        # Delete the report
        deleted_id = delete_report("test-007", "analyst1")
        
        self.assertIsNotNone(deleted_id)
        self.assertGreater(deleted_id, 0)
        
        # Verify deleted version exists
        all_reports = read_all_reports()
        test_007_reports = [r for r in all_reports if r['report_id'] == "test-007"]
        self.assertEqual(len(test_007_reports), 2)  # Original + deleted version
        
        # Verify the latest version is marked as deleted
        latest = read_report("test-007")
        self.assertEqual(latest['is_deleted'], 1)
    
    def test_get_unsynchronized_reports(self):
        """Test retrieval of unsynchronized reports."""
        # Create multiple reports
        id1 = create_report("test-008", "Title 1", "Content 1", "IL4", "analyst1")
        id2 = create_report("test-009", "Title 2", "Content 2", "IL5", "analyst2")
        id3 = create_report("test-010", "Title 3", "Content 3", "CUI", "analyst3")
        
        # Mark one as synchronized
        mark_as_synchronized(id2)
        
        # Get unsynchronized reports
        unsync_reports = get_unsynchronized_reports()
        
        # Should have 2 unsynchronized reports
        self.assertEqual(len(unsync_reports), 2)
        
        unsync_ids = [r['report_id'] for r in unsync_reports]
        self.assertIn("test-008", unsync_ids)
        self.assertIn("test-010", unsync_ids)
        self.assertNotIn("test-009", unsync_ids)
    
    def test_mark_as_synchronized_updates_status(self):
        """Test synchronization status tracking."""
        # Create a report
        report_id = create_report("test-011", "Title", "Content", "IL4", "analyst1")
        
        # Verify it's unsynchronized
        report = read_report("test-011")
        self.assertEqual(report['is_synchronized'], 0)
        
        # Mark as synchronized
        mark_as_synchronized(report_id)
        
        # Verify it's now synchronized
        report = read_report("test-011")
        self.assertEqual(report['is_synchronized'], 1)
    
    def test_multiple_versions_same_report_id(self):
        """Test handling of multiple versions of the same report_id."""
        # Create initial version
        create_report("test-012", "Version 1", "Content 1", "IL4", "analyst1")
        
        # Create second version
        update_report("test-012", "Version 2", "Content 2", "IL5", "analyst1")
        
        # Create third version
        update_report("test-012", "Version 3", "Content 3", "CUI", "analyst2")
        
        # Verify read_report returns the latest version
        latest = read_report("test-012")
        self.assertEqual(latest['title'], "Version 3")
        self.assertEqual(latest['content'], "Content 3")
        self.assertEqual(latest['classification'], "CUI")
        self.assertEqual(latest['updated_by'], "analyst2")
        
        # Verify all versions exist
        all_reports = read_all_reports()
        test_012_reports = [r for r in all_reports if r['report_id'] == "test-012"]
        self.assertEqual(len(test_012_reports), 3)


if __name__ == '__main__':
    unittest.main()
