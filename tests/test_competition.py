import csv
import io
import unittest
from openpyxl import Workbook
import test_app
from importer import parse, ImportError


class CompetitionTests(unittest.TestCase):
    setUp = test_app.Tests.setUp
    tearDown = test_app.Tests.tearDown
    call = test_app.Tests.call
    payload = test_app.Tests.payload

    def rows(self):
        rows = list(csv.reader(io.StringIO(self.data.decode('utf-8-sig')), delimiter=';'))
        rows[0] += ['Competicion', 'Fecha_competicion']
        for row in rows[1:]:
            row += ['Liga escolar', '01/09/2026']
        return rows

    def encode(self, rows):
        out = io.StringIO(newline='')
        csv.writer(out, delimiter=';').writerows(rows)
        return out.getvalue().encode('utf-8-sig')

    def test_preview_save_api_and_export(self):
        original_id = parse('old.csv', self.data)['id']
        self.data = self.encode(self.rows())
        preview = self.call('/api/import', 'POST', self.payload(preview=True))['json']['match']
        self.assertEqual(preview['competition'], 'Liga escolar')
        self.assertEqual(preview['competition_date'], '2026-09-01')
        self.assertEqual(preview['id'], original_id)
        self.assertEqual(self.call('/api/import', 'POST', self.payload())['status'], '201 Created')
        match = self.call('/api/data')['json']['matches'][0]
        self.assertEqual(match['competition'], 'Liga escolar')
        exported = self.call('/api/export')['body']
        rows = list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')), delimiter=';'))
        self.assertTrue(all(r['Competicion'] == 'Liga escolar' and r['Fecha_competicion'] == '2026-09-01' for r in rows))
        self.assertEqual(parse('export.csv', exported)['competition_date'], '2026-09-01')

    def test_optional_sparse_and_xlsx_date(self):
        from datetime import datetime
        self.assertEqual(parse('old.csv', self.data)['competition'], '')
        rows = self.rows()
        for row in rows[2:]:
            row[-2:] = ['', '']
        self.assertEqual(parse('sparse.csv', self.encode(rows))['competition_date'], '2026-09-01')
        rows[1][-1] = datetime(2026, 9, 1)
        book = Workbook()
        for row in rows:
            book.active.append(row)
        out = io.BytesIO()
        book.save(out)
        self.assertEqual(parse('test.xlsx', out.getvalue())['competition_date'], '2026-09-01')

    def test_invalid_or_inconsistent_metadata(self):
        for column, value, message in [(-1, '31/02/2026', 'Fecha_competicion inválida'),
                                       (-1, '2026-10-01', 'una sola competición'),
                                       (-2, 'Otra liga', 'una sola competición')]:
            rows = self.rows()
            rows[1][column] = value
            with self.assertRaisesRegex(ImportError, message):
                parse('invalid.csv', self.encode(rows))
        rows = self.rows()
        for row in rows[1:]:
            row[-1] = ''
        with self.assertRaisesRegex(ImportError, 'juntas'):
            parse('missing.csv', self.encode(rows))
