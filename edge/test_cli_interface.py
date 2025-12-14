import unittest
import tempfile
import os
from unittest.mock import MagicMock

import database_manager
import cli_interface


class TestCLIInterface(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
        self.temp_db.close()
        os.environ['EDGE_DB_PATH'] = self.temp_db.name
        os.environ['EDGE_USER'] = 'test_cli_user'
        database_manager.init_db()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_validate_report_id(self):
        self.assertTrue(cli_interface.validate_report_id('abc-123'))
        self.assertFalse(cli_interface.validate_report_id('invalid id'))
        self.assertFalse(cli_interface.validate_report_id(''))

    def test_validate_classification(self):
        self.assertTrue(cli_interface.validate_classification('CUI'))
        self.assertTrue(cli_interface.validate_classification('IL4'))
        self.assertFalse(cli_interface.validate_classification('PUBLIC'))

    def test_validate_length(self):
        self.assertTrue(cli_interface.validate_length('short', 10))
        self.assertFalse(cli_interface.validate_length('x' * 3000, 2000))

    def test_handle_create_report_success(self):
        inputs = iter(['rpt-1', 'Title', 'Content', 'IL4'])
        created_id = None

        def fake_input(prompt=''):
            return next(inputs)

        def fake_print(msg=''):
            # keep simple, no-op
            pass

        # Use real DB to verify creation
        result = cli_interface.handle_create_report(input_fn=fake_input, print_fn=fake_print, db=database_manager)
        self.assertTrue(result)

        # Confirm record exists
        rec = database_manager.read_report('rpt-1')
        self.assertIsNotNone(rec)
        self.assertEqual(rec['report_id'], 'rpt-1')

    def test_handle_create_report_invalid_id(self):
        inputs = iter(['invalid id', 'Title', 'Content', 'IL4'])

        def fake_input(prompt=''):
            return next(inputs)

        messages = []

        def fake_print(msg=''):
            messages.append(msg)

        result = cli_interface.handle_create_report(input_fn=fake_input, print_fn=fake_print, db=database_manager)
        self.assertFalse(result)
        self.assertIn('Invalid report_id', ' '.join(messages))

    def test_handle_view_reports(self):
        database_manager.create_report('view-1', 'A Title', 'Some content', 'IL4', 'analyst')
        outputs = []

        def fake_print(msg=''):
            outputs.append(str(msg))

        cli_interface.handle_view_reports(print_fn=fake_print, db=database_manager)
        joined = '\n'.join(outputs)
        self.assertIn('view-1', joined)
        self.assertIn('A Title', joined)

    def test_handle_update_report(self):
        database_manager.create_report('u-1', 'Old Title', 'Old content', 'IL4', 'analyst')
        inputs = iter(['u-1', '', '', ''])

        def fake_input(prompt=''):
            return next(inputs)

        messages = []

        def fake_print(msg=''):
            messages.append(str(msg))

        result = cli_interface.handle_update_report(input_fn=fake_input, print_fn=fake_print, db=database_manager)
        self.assertTrue(result)
        self.assertTrue(any('new DB id' in m.lower() or 'new db id' in m.lower() for m in messages))

    def test_handle_delete_report_confirm_no(self):
        database_manager.create_report('d-1', 'Title', 'Content', 'IL4', 'analyst')
        inputs = iter(['d-1', 'n'])

        def fake_input(prompt=''):
            return next(inputs)

        messages = []

        def fake_print(msg=''):
            messages.append(str(msg))

        result = cli_interface.handle_delete_report(input_fn=fake_input, print_fn=fake_print, db=database_manager)
        self.assertFalse(result)
        self.assertIn('Delete cancelled', ' '.join(messages))

    def test_handle_delete_report_confirm_yes(self):
        database_manager.create_report('d-2', 'Title', 'Content', 'IL4', 'analyst')
        inputs = iter(['d-2', 'y'])

        def fake_input(prompt=''):
            return next(inputs)

        messages = []

        def fake_print(msg=''):
            messages.append(str(msg))

        result = cli_interface.handle_delete_report(input_fn=fake_input, print_fn=fake_print, db=database_manager)
        self.assertTrue(result)
        self.assertIn('soft-deleted', ' '.join(messages))

    def test_handle_sync_calls_edge_app(self):
        # Patch edge_app.sync_to_cloud via monkeypatching the module attribute
        import edge_app
        original_sync = edge_app.sync_to_cloud
        original_display = edge_app.display_sync_summary

        called = {'sync': False, 'display': False}

        def fake_sync():
            called['sync'] = True
            return {'total': 0, 'successful': 0, 'failed': 0, 'reports': []}

        def fake_display(s):
            called['display'] = True

        edge_app.sync_to_cloud = fake_sync
        edge_app.display_sync_summary = fake_display

        try:
            cli_interface.handle_sync(print_fn=lambda *a, **k: None, db=database_manager)
            self.assertTrue(called['sync'])
            self.assertTrue(called['display'])
        finally:
            edge_app.sync_to_cloud = original_sync
            edge_app.display_sync_summary = original_display


if __name__ == '__main__':
    unittest.main()
