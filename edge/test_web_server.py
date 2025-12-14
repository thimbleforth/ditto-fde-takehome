import unittest
import os
import tempfile
import json
from unittest.mock import patch

import database_manager
from web_server import app as webapp


class TestWebServer(unittest.TestCase):
    def setUp(self):
        # Create a temporary database for each test
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['EDGE_DB_PATH'] = self.temp_db.name
        database_manager.init_db()
        self.client = webapp.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_get_reports_returns_all_reports(self):
        # Create some reports
        database_manager.create_report("r-001", "T1", "C1", "IL4", "u1")
        database_manager.create_report("r-002", "T2", "C2", "IL5", "u2")

        resp = self.client.get('/api/reports')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

    def test_post_creates_report_with_validation(self):
        payload = {
            "report_id": "new-001",
            "title": "New Report",
            "content": "Some content",
            "classification": "CUI",
            "updated_by": "tester"
        }
        resp = self.client.post('/api/reports', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertIn('id', data)

        # Verify in DB
        record = database_manager.read_report('new-001')
        self.assertIsNotNone(record)
        self.assertEqual(record['report_id'], 'new-001')

    def test_put_updates_report(self):
        db_id = database_manager.create_report("up-001", "Old", "Old content", "IL4", "u1")
        # Update the report
        payload = {"title": "Updated", "content": "Updated content", "classification": "IL4", "updated_by": "webtest"}
        resp = self.client.put(f'/api/reports/{db_id}', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')

        # Latest record should have updated title
        record = database_manager.read_report('up-001')
        self.assertEqual(record['title'], 'Updated')

    def test_delete_soft_deletes_report(self):
        db_id = database_manager.create_report("del-001", "ToDelete", "X", "IL5", "u1")
        resp = self.client.delete(f'/api/reports/{db_id}', json={"updated_by": "webtest"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')

        # Latest should be marked as deleted
        rec = database_manager.read_report('del-001')
        self.assertIsNotNone(rec)
        self.assertEqual(rec.get('is_deleted'), 1)

    @patch('edge_app.sync_to_cloud')
    def test_post_sync_triggers_synchronization(self, mock_sync):
        mock_sync.return_value = {"total": 1, "successful": 1, "failed": 0, "reports": []}
        resp = self.client.post('/api/sync')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('total'), 1)

    def test_invalid_input_returns_400(self):
        # Missing report_id
        payload = {"title": "NoID", "content": "X", "classification": "IL4", "updated_by": "u"}
        resp = self.client.post('/api/reports', json=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get('error'), 'invalid_request')


if __name__ == '__main__':
    unittest.main()
