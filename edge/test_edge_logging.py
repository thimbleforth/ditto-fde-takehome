# test_edge_logging.py
import unittest
import os
import tempfile
import logging
from unittest.mock import patch, MagicMock, Mock
import database_manager
from edge_app import (
    setup_logging,
    log_info,
    log_error,
    log_warning,
    sync_single_report,
    sync_to_cloud,
    issue_token
)


class TestEdgeLogging(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment with mock handler and database."""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['EDGE_DB_PATH'] = self.temp_db.name
        os.environ['EDGE_USER'] = 'test_user'
        database_manager.init_db()
        
        # Clear any existing handlers and set up mock handler
        self.logger = logging.getLogger('edge_app')
        self.logger.handlers.clear()
        self.logger.setLevel(logging.INFO)
        
        # Create mock handler to capture log records
        self.mock_handler = Mock(spec=logging.Handler)
        self.mock_handler.level = logging.INFO
        self.log_records = []
        
        def handle_log(record):
            self.log_records.append(record)
        
        self.mock_handler.handle = handle_log
        self.logger.addHandler(self.mock_handler)
    
    def tearDown(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
        self.logger.handlers.clear()
    
    def get_log_messages(self):
        """Get all logged messages."""
        return [record.getMessage() for record in self.log_records]
    
    def get_log_components(self):
        """Get all logged components."""
        return [getattr(record, 'component', None) for record in self.log_records]
    
    def test_log_entries_created(self):
        """Test that log entries are created for key operations."""
        # Write a log entry
        log_info("TEST", "Test message")
        
        # Verify log was created
        messages = self.get_log_messages()
        self.assertEqual(len(messages), 1)
        self.assertIn("Test message", messages[0])
        
        # Verify component was set
        components = self.get_log_components()
        self.assertEqual(components[0], "TEST")
    
    def test_log_format_compliance(self):
        """Test that log entries include required components."""
        # Write log entries
        log_info("COMPONENT1", "Info message")
        log_error("COMPONENT2", "Error message")
        log_warning("COMPONENT3", "Warning message")
        
        # Verify all logs were created
        self.assertEqual(len(self.log_records), 3)
        
        # Verify log levels
        self.assertEqual(self.log_records[0].levelname, "INFO")
        self.assertEqual(self.log_records[1].levelname, "ERROR")
        self.assertEqual(self.log_records[2].levelname, "WARNING")
        
        # Verify components
        self.assertEqual(self.log_records[0].component, "COMPONENT1")
        self.assertEqual(self.log_records[1].component, "COMPONENT2")
        self.assertEqual(self.log_records[2].component, "COMPONENT3")
        
        # Verify messages
        self.assertIn("Info message", self.log_records[0].getMessage())
        self.assertIn("Error message", self.log_records[1].getMessage())
        self.assertIn("Warning message", self.log_records[2].getMessage())
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_attempt_logging(self, mock_post, mock_token):
        """Test that sync attempts are logged."""
        # Setup mocks
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Create and sync a report
        database_manager.create_report("test-001", "Title", "Content", "IL4", "analyst1")
        sync_to_cloud()
        
        # Verify sync logs were created
        messages = self.get_log_messages()
        components = self.get_log_components()
        
        # Check for SYNC component
        self.assertIn("SYNC", components)
        
        # Check for sync-related messages
        all_messages = " ".join(messages)
        self.assertIn("Starting sync operation", all_messages)
        self.assertIn("Attempting to sync report", all_messages)
        self.assertIn("test-001", all_messages)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_success_logging(self, mock_post, mock_token):
        """Test that successful syncs are logged."""
        # Setup mocks
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Create and sync a report
        database_manager.create_report("test-002", "Title", "Content", "IL4", "analyst1")
        sync_to_cloud()
        
        # Verify success logs
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        self.assertIn("Successfully synced report", all_messages)
        self.assertIn("test-002", all_messages)
        self.assertIn("Sync operation completed", all_messages)
        self.assertIn("1 successful", all_messages)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_failure_logging(self, mock_post, mock_token):
        """Test that sync failures are logged."""
        # Setup mocks to simulate failure
        mock_token.return_value = "fake_token"
        mock_post.side_effect = Exception("Connection refused")
        
        # Create and sync a report
        database_manager.create_report("test-003", "Title", "Content", "IL4", "analyst1")
        sync_to_cloud()
        
        # Verify failure logs
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        # Check for ERROR level log
        error_logs = [r for r in self.log_records if r.levelname == "ERROR"]
        self.assertGreater(len(error_logs), 0)
        
        self.assertIn("test-003", all_messages)
        self.assertIn("1 failed", all_messages)
    
    @patch('edge_app.jwt.encode')
    @patch('edge_app._load_private_key')
    @patch('edge_app.EDGE_USER', 'test_user')
    def test_token_generation_logging(self, mock_load_key, mock_jwt_encode):
        """Test that authentication token generation is logged."""
        # Setup mocks
        mock_load_key.return_value = b"fake_private_key_data_for_testing_purposes_only"
        mock_jwt_encode.return_value = "fake_jwt_token"
        
        # Generate token
        issue_token()
        
        # Verify token generation logs
        messages = self.get_log_messages()
        components = self.get_log_components()
        all_messages = " ".join(messages)
        
        self.assertIn("AUTH", components)
        self.assertIn("Generated JWT token", all_messages)
        self.assertIn("test_user", all_messages)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_multiple_sync_operations_logged(self, mock_post, mock_token):
        """Test that multiple sync operations are logged correctly."""
        # Setup mocks
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Create multiple reports
        database_manager.create_report("test-004", "Title 1", "Content 1", "IL4", "analyst1")
        database_manager.create_report("test-005", "Title 2", "Content 2", "IL5", "analyst2")
        database_manager.create_report("test-006", "Title 3", "Content 3", "CUI", "analyst3")
        
        # Sync all reports
        sync_to_cloud()
        
        # Verify all reports are logged
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        self.assertIn("test-004", all_messages)
        self.assertIn("test-005", all_messages)
        self.assertIn("test-006", all_messages)
        
        # Verify sync summary
        self.assertIn("3 unsynchronized reports", all_messages)
        self.assertIn("3 successful", all_messages)
    
    def test_log_levels_are_correct(self):
        """Test that different log levels are used appropriately."""
        # Write different log levels
        log_info("TEST", "This is info")
        log_warning("TEST", "This is warning")
        log_error("TEST", "This is error")
        
        # Verify correct log levels
        self.assertEqual(len(self.log_records), 3)
        
        self.assertEqual(self.log_records[0].levelname, "INFO")
        self.assertIn("This is info", self.log_records[0].getMessage())
        
        self.assertEqual(self.log_records[1].levelname, "WARNING")
        self.assertIn("This is warning", self.log_records[1].getMessage())
        
        self.assertEqual(self.log_records[2].levelname, "ERROR")
        self.assertIn("This is error", self.log_records[2].getMessage())


if __name__ == '__main__':
    unittest.main()
