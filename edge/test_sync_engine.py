# test_sync_engine.py
import unittest
import os
import tempfile
import json
from unittest.mock import patch, MagicMock
import database_manager
from edge_app import sync_to_cloud, sync_single_report, display_sync_summary


class TestSyncEngine(unittest.TestCase):
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['EDGE_DB_PATH'] = self.temp_db.name
        os.environ['EDGE_USER'] = 'test_user'
        database_manager.init_db()
    
    def tearDown(self):
        """Clean up the temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_successful_sync_of_multiple_reports(self, mock_post, mock_token):
        """Test successful synchronization of multiple reports."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response
        
        # Create multiple unsynchronized reports
        database_manager.create_report("test-001", "Title 1", "Content 1", "IL4", "analyst1")
        database_manager.create_report("test-002", "Title 2", "Content 2", "IL5", "analyst2")
        database_manager.create_report("test-003", "Title 3", "Content 3", "CUI", "analyst3")
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify summary
        self.assertEqual(summary['total'], 3)
        self.assertEqual(summary['successful'], 3)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(summary['reports']), 3)
        
        # Verify all reports marked as successful
        for report in summary['reports']:
            self.assertEqual(report['status'], 'success')
        
        # Verify reports are marked as synchronized in database
        unsync_reports = database_manager.get_unsynchronized_reports()
        self.assertEqual(len(unsync_reports), 0)
        
        # Verify API was called 3 times
        self.assertEqual(mock_post.call_count, 3)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_handling_of_network_failures(self, mock_post, mock_token):
        """Test handling of network failures during sync."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock to raise ConnectionError
        mock_post.side_effect = Exception("Connection refused")
        
        # Create unsynchronized reports
        database_manager.create_report("test-004", "Title 4", "Content 4", "IL4", "analyst1")
        database_manager.create_report("test-005", "Title 5", "Content 5", "IL5", "analyst2")
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify summary shows failures
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['successful'], 0)
        self.assertEqual(summary['failed'], 2)
        
        # Verify all reports marked as failed
        for report in summary['reports']:
            self.assertEqual(report['status'], 'failed')
            self.assertIn('error', report)
        
        # Verify reports remain unsynchronized in database
        unsync_reports = database_manager.get_unsynchronized_reports()
        self.assertEqual(len(unsync_reports), 2)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_partial_sync_success(self, mock_post, mock_token):
        """Test sync with some successes and some failures."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock to succeed for first call, fail for second
        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"status": "ok"}
        
        mock_post.side_effect = [mock_success, Exception("Network error")]
        
        # Create unsynchronized reports
        database_manager.create_report("test-006", "Title 6", "Content 6", "IL4", "analyst1")
        database_manager.create_report("test-007", "Title 7", "Content 7", "IL5", "analyst2")
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify summary
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['successful'], 1)
        self.assertEqual(summary['failed'], 1)
        
        # Verify one report is synchronized, one is not
        unsync_reports = database_manager.get_unsynchronized_reports()
        self.assertEqual(len(unsync_reports), 1)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_summary_generation(self, mock_post, mock_token):
        """Test sync summary structure and content."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response
        
        # Create unsynchronized reports
        database_manager.create_report("test-008", "Title 8", "Content 8", "IL4", "analyst1")
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify summary structure
        self.assertIn('total', summary)
        self.assertIn('successful', summary)
        self.assertIn('failed', summary)
        self.assertIn('reports', summary)
        
        # Verify summary content
        self.assertEqual(summary['total'], 1)
        self.assertEqual(summary['successful'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(summary['reports']), 1)
        
        # Verify report details in summary
        report_result = summary['reports'][0]
        self.assertEqual(report_result['status'], 'success')
        self.assertEqual(report_result['report_id'], 'test-008')
        self.assertIn('db_id', report_result)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_synchronization_status_updates(self, mock_post, mock_token):
        """Test that synchronization status is correctly updated."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response
        
        # Create unsynchronized report
        report_id = database_manager.create_report("test-009", "Title 9", "Content 9", "IL4", "analyst1")
        
        # Verify initially unsynchronized
        report = database_manager.read_report("test-009")
        self.assertEqual(report['is_synchronized'], 0)
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify sync was successful
        self.assertEqual(summary['successful'], 1)
        
        # Verify report is now marked as synchronized
        report = database_manager.read_report("test-009")
        self.assertEqual(report['is_synchronized'], 1)
    
    def test_sync_with_no_unsynchronized_reports(self):
        """Test sync when there are no unsynchronized reports."""
        # Don't create any reports
        
        # Perform sync
        summary = sync_to_cloud()
        
        # Verify summary shows no reports
        self.assertEqual(summary['total'], 0)
        self.assertEqual(summary['successful'], 0)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(summary['reports']), 0)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_single_report_success(self, mock_post, mock_token):
        """Test sync_single_report function with successful sync."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response
        
        # Create a report dict
        report = {
            "id": 1,
            "report_id": "test-010",
            "title": "Title 10",
            "content": "Content 10",
            "classification": "IL4",
            "updated_at": "2024-12-03T10:00:00+00:00",
            "updated_by": "analyst1",
            "is_deleted": 0
        }
        
        # Sync single report
        result = sync_single_report(report)
        
        # Verify result
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['report_id'], 'test-010')
        self.assertEqual(result['db_id'], 1)
    
    @patch('edge_app.issue_token')
    @patch('edge_app.requests.post')
    def test_sync_single_report_http_error(self, mock_post, mock_token):
        """Test sync_single_report function with HTTP error."""
        # Setup mock token
        mock_token.return_value = "fake_token"
        
        # Setup mock response with error status
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        # Create a report dict
        report = {
            "id": 1,
            "report_id": "test-011",
            "title": "Title 11",
            "content": "Content 11",
            "classification": "IL4",
            "updated_at": "2024-12-03T10:00:00+00:00",
            "updated_by": "analyst1",
            "is_deleted": 0
        }
        
        # Sync single report
        result = sync_single_report(report)
        
        # Verify result shows failure
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['report_id'], 'test-011')
        self.assertIn('error', result)
        self.assertIn('500', result['error'])
    
    @patch('builtins.print')
    def test_display_sync_summary_with_results(self, mock_print):
        """Test display_sync_summary function with successful and failed syncs."""
        # Create summary with mixed results
        summary = {
            "total": 3,
            "successful": 2,
            "failed": 1,
            "reports": [
                {"status": "success", "report_id": "test-012"},
                {"status": "success", "report_id": "test-013"},
                {"status": "failed", "report_id": "test-014", "error": "Connection timeout"}
            ]
        }
        
        # Display summary
        display_sync_summary(summary)
        
        # Verify print was called (basic check that function executes)
        self.assertTrue(mock_print.called)
        
        # Verify key information was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        output = ' '.join(print_calls)
        
        self.assertIn('3', output)  # Total
        self.assertIn('2', output)  # Successful
        self.assertIn('1', output)  # Failed
    
    @patch('builtins.print')
    def test_display_sync_summary_with_no_reports(self, mock_print):
        """Test display_sync_summary function with no reports."""
        # Create empty summary
        summary = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "reports": []
        }
        
        # Display summary
        display_sync_summary(summary)
        
        # Verify print was called
        self.assertTrue(mock_print.called)


if __name__ == '__main__':
    unittest.main()
