# test_logging.py
import unittest
import os
import tempfile
import logging
import json
from unittest.mock import patch, MagicMock, Mock
from cloud_app import app, setup_logging, log_info, log_error, log_warning


class TestCloudLogging(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment with mock handler and database."""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['CLOUD_DB_PATH'] = self.temp_db.name
        
        # Configure Flask app for testing
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Clear any existing handlers and set up mock handler
        self.logger = logging.getLogger('cloud_app')
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
    
    def get_log_endpoints(self):
        """Get all logged endpoints."""
        return [getattr(record, 'endpoint', None) for record in self.log_records]
    
    def get_log_users(self):
        """Get all logged users."""
        return [getattr(record, 'user', None) for record in self.log_records]
    
    def test_log_entries_created(self):
        """Test that log entries are created for key operations."""
        # Write a log entry
        log_info("/test", "test_user", "Test message")
        
        # Verify log was created
        messages = self.get_log_messages()
        self.assertEqual(len(messages), 1)
        self.assertIn("Test message", messages[0])
        
        # Verify endpoint and user were set
        endpoints = self.get_log_endpoints()
        users = self.get_log_users()
        self.assertEqual(endpoints[0], "/test")
        self.assertEqual(users[0], "test_user")
    
    def test_log_format_compliance(self):
        """Test that log entries include required components."""
        # Write log entries
        log_info("/api/sync", "user1", "Info message")
        log_error("/api/sync", "user2", "Error message")
        log_warning("/api/health", "user3", "Warning message")
        
        # Verify all logs were created
        self.assertEqual(len(self.log_records), 3)
        
        # Verify log levels
        self.assertEqual(self.log_records[0].levelname, "INFO")
        self.assertEqual(self.log_records[1].levelname, "ERROR")
        self.assertEqual(self.log_records[2].levelname, "WARNING")
        
        # Verify endpoints
        self.assertEqual(self.log_records[0].endpoint, "/api/sync")
        self.assertEqual(self.log_records[1].endpoint, "/api/sync")
        self.assertEqual(self.log_records[2].endpoint, "/api/health")
        
        # Verify users
        self.assertEqual(self.log_records[0].user, "user1")
        self.assertEqual(self.log_records[1].user, "user2")
        self.assertEqual(self.log_records[2].user, "user3")
        
        # Verify messages
        self.assertIn("Info message", self.log_records[0].getMessage())
        self.assertIn("Error message", self.log_records[1].getMessage())
        self.assertIn("Warning message", self.log_records[2].getMessage())
    
    @patch('cloud_app.jwt.decode')
    def test_authentication_attempt_logging(self, mock_jwt_decode):
        """Test that authentication attempts are logged."""
        # Setup mock to return valid claims
        mock_jwt_decode.return_value = {"user": "edge1"}
        
        # Make sync request
        response = self.client.post(
            '/api/sync',
            headers={'Authorization': 'Bearer fake_token'},
            json={
                "report_id": "test-001",
                "title": "Test",
                "content": "Content",
                "classification": "IL4",
                "updated_at": "2024-12-03T10:00:00+00:00",
                "updated_by": "edge1"
            }
        )
        
        # Verify authentication is logged
        messages = self.get_log_messages()
        endpoints = self.get_log_endpoints()
        all_messages = " ".join(messages)
        
        self.assertIn("AUTH", endpoints)
        self.assertIn("JWT token verified successfully", all_messages)
        self.assertIn("edge1", all_messages)
    
    def test_authentication_failure_logging(self):
        """Test that authentication failures are logged."""
        # Make sync request without auth header
        response = self.client.post(
            '/api/sync',
            json={
                "report_id": "test-002",
                "title": "Test",
                "content": "Content",
                "classification": "IL4",
                "updated_at": "2024-12-03T10:00:00+00:00",
                "updated_by": "edge1"
            }
        )
        
        # Verify authentication failure is logged
        messages = self.get_log_messages()
        endpoints = self.get_log_endpoints()
        all_messages = " ".join(messages)
        
        # Check for WARNING level log
        warning_logs = [r for r in self.log_records if r.levelname == "WARNING"]
        self.assertGreater(len(warning_logs), 0)
        
        self.assertIn("/api/sync", endpoints)
        self.assertIn("Authentication failed", all_messages)
    
    @patch('cloud_app.verify_token')
    def test_sync_request_logging(self, mock_verify):
        """Test that sync requests are logged with source user."""
        # Setup mock
        mock_verify.return_value = {"user": "edge2"}
        
        # Make sync request
        response = self.client.post(
            '/api/sync',
            headers={'Authorization': 'Bearer fake_token'},
            json={
                "report_id": "test-003",
                "title": "Test Report",
                "content": "Test Content",
                "classification": "IL5",
                "updated_at": "2024-12-03T10:00:00+00:00",
                "updated_by": "edge2"
            }
        )
        
        # Verify sync request is logged with user
        messages = self.get_log_messages()
        endpoints = self.get_log_endpoints()
        users = self.get_log_users()
        all_messages = " ".join(messages)
        
        self.assertIn("/api/sync", endpoints)
        self.assertIn("edge2", users)
        self.assertIn("Sync request received", all_messages)
    
    @patch('cloud_app.verify_token')
    def test_successful_sync_logging(self, mock_verify):
        """Test that successful syncs are logged."""
        # Setup mock
        mock_verify.return_value = {"user": "edge1"}
        
        # Make sync request
        response = self.client.post(
            '/api/sync',
            headers={'Authorization': 'Bearer fake_token'},
            json={
                "report_id": "test-004",
                "title": "Test",
                "content": "Content",
                "classification": "CUI",
                "updated_at": "2024-12-03T10:00:00+00:00",
                "updated_by": "edge1"
            }
        )
        
        # Verify successful sync is logged
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        self.assertIn("Successfully stored report", all_messages)
        self.assertIn("test-004", all_messages)
    
    @patch('cloud_app.verify_token')
    def test_validation_error_logging(self, mock_verify):
        """Test that validation errors are logged."""
        # Setup mock
        mock_verify.return_value = {"user": "edge1"}
        
        # Make sync request with missing fields
        response = self.client.post(
            '/api/sync',
            headers={'Authorization': 'Bearer fake_token'},
            json={
                "report_id": "test-005",
                "title": "Test"
                # Missing required fields
            }
        )
        
        # Verify validation error is logged
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        # Check for WARNING level log
        warning_logs = [r for r in self.log_records if r.levelname == "WARNING"]
        self.assertGreater(len(warning_logs), 0)
        
        self.assertIn("Invalid request", all_messages)
        self.assertIn("Missing required field", all_messages)
    
    @patch('cloud_app.verify_token')
    @patch('cloud_app.Session')
    def test_database_error_logging(self, mock_session_class, mock_verify):
        """Test that database errors are logged."""
        # Setup mocks
        mock_verify.return_value = {"user": "edge1"}
        
        # Mock session to raise exception
        mock_session = MagicMock()
        mock_session.add.side_effect = Exception("Database connection failed")
        mock_session_class.return_value = mock_session
        
        # Make sync request
        response = self.client.post(
            '/api/sync',
            headers={'Authorization': 'Bearer fake_token'},
            json={
                "report_id": "test-006",
                "title": "Test",
                "content": "Content",
                "classification": "IL4",
                "updated_at": "2024-12-03T10:00:00+00:00",
                "updated_by": "edge1"
            }
        )
        
        # Verify database error is logged
        messages = self.get_log_messages()
        users = self.get_log_users()
        all_messages = " ".join(messages)
        
        # Check for ERROR level log
        error_logs = [r for r in self.log_records if r.levelname == "ERROR"]
        self.assertGreater(len(error_logs), 0)
        
        self.assertIn("Database error", all_messages)
        self.assertIn("edge1", users)
    
    @patch('cloud_app.verify_token')
    def test_multiple_sync_requests_logged(self, mock_verify):
        """Test that multiple sync requests are logged correctly."""
        # Setup mock
        mock_verify.return_value = {"user": "edge1"}
        
        # Make multiple sync requests
        for i in range(3):
            self.client.post(
                '/api/sync',
                headers={'Authorization': 'Bearer fake_token'},
                json={
                    "report_id": f"test-{100+i}",
                    "title": f"Test {i}",
                    "content": f"Content {i}",
                    "classification": "IL4",
                    "updated_at": "2024-12-03T10:00:00+00:00",
                    "updated_by": "edge1"
                }
            )
        
        # Verify all requests are logged
        messages = self.get_log_messages()
        all_messages = " ".join(messages)
        
        self.assertIn("test-100", all_messages)
        self.assertIn("test-101", all_messages)
        self.assertIn("test-102", all_messages)
        
        # Count sync request log entries
        sync_count = all_messages.count("Sync request received")
        self.assertEqual(sync_count, 3)
    
    def test_log_levels_are_correct(self):
        """Test that different log levels are used appropriately."""
        # Write different log levels
        log_info("/test", "user1", "This is info")
        log_warning("/test", "user2", "This is warning")
        log_error("/test", "user3", "This is error")
        
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
