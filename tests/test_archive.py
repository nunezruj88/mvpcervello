import base64
import io
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
import app
import test_app


class ArchiveTests(unittest.TestCase):
    setUp = test_app.Tests.setUp
    tearDown = test_app.Tests.tearDown
    call = test_app.Tests.call
    payload = test_app.Tests.payload

    def files(self):
        return list(app.ARCHIVE_DIR.glob('*')) if app.ARCHIVE_DIR.exists() else []

    def test_confirmed_import_preserves_original_bytes(self):
        response = self.call('/api/import', 'POST', self.payload())
        self.assertEqual(response['status'], '201 Created')
        self.assertEqual(len(self.files()), 1)
        saved = self.files()[0]
        self.assertEqual(saved.read_bytes(), self.data)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertEqual(app.matches()[0]['archived_filename'], saved.name)
        self.assertEqual(self.call('/partidos/' + saved.name)['status'], '404 Not Found')

    def test_preview_invalid_and_unconfirmed_duplicate_do_not_archive(self):
        self.call('/api/import', 'POST', self.payload(preview=True))
        self.assertEqual(self.files(), [])
        bad = self.payload(data_unused='ignored')
        bad['data'] = base64.b64encode(b'invalid csv').decode()
        self.assertEqual(self.call('/api/import', 'POST', bad)['status'], '400 Bad Request')
        self.assertEqual(self.files(), [])
        self.call('/api/import', 'POST', self.payload())
        self.assertEqual(self.call('/api/import', 'POST', self.payload())['status'], '409 Conflict')
        self.assertEqual(len(self.files()), 1)

    def test_replacements_keep_both_versions_even_with_same_name(self):
        self.call('/api/import', 'POST', self.payload())
        first = self.files()[0]
        self.data += b'\n'
        self.assertEqual(self.call('/api/import', 'POST', self.payload(replace=True))['status'], '201 Created')
        self.assertEqual(len(self.files()), 2)
        self.assertEqual(first.read_bytes(), self.data[:-1])
        self.assertEqual(len(app.matches()), 1)

    def test_names_cannot_escape_archive_directory(self):
        payload = self.payload()
        payload['filename'] = '../../evil name.csv'
        self.assertEqual(self.call('/api/import', 'POST', payload)['status'], '201 Created')
        self.assertEqual(self.files()[0].parent, app.ARCHIVE_DIR)
        self.assertNotIn(' ', self.files()[0].name)

    def test_archive_failure_preserves_database(self):
        self.call('/api/import', 'POST', self.payload())
        before = app.matches()
        with patch.object(app, 'archive_upload', side_effect=OSError('disk full')):
            response = self.call('/api/import', 'POST', self.payload(replace=True, complete=True))
        self.assertEqual(response['status'], '500 Internal Server Error')
        self.assertEqual(app.matches(), before)
        self.assertEqual(len(self.files()), 1)

    def test_database_failure_removes_new_archive(self):
        self.call('/api/import', 'POST', self.payload())
        before = app.matches()
        with app.connect() as con:
            con.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON matches BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with patch('traceback.print_exc'):
            response = self.call('/api/import', 'POST', self.payload(replace=True))
        self.assertEqual(response['status'], '500 Internal Server Error')
        self.assertEqual(app.matches(), before)
        self.assertEqual(len(self.files()), 1)

    def test_original_excel_is_also_preserved(self):
        import csv
        book = Workbook()
        for row in csv.reader(io.StringIO(self.data.decode('utf-8-sig')), delimiter=';'):
            book.active.append(row)
        out = io.BytesIO()
        book.save(out)
        payload = dict(filename='partido.xlsx', data=base64.b64encode(out.getvalue()).decode())
        self.assertEqual(self.call('/api/import', 'POST', payload)['status'], '201 Created')
        self.assertEqual(self.files()[0].suffix, '.xlsx')
        self.assertEqual(self.files()[0].read_bytes(), out.getvalue())
