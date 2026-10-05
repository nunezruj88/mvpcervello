import csv
import io
import unittest
import test_app
import app
from openpyxl import Workbook
from importer import parse, ImportError


class CategoryTests(unittest.TestCase):
    setUp = test_app.Tests.setUp
    tearDown = test_app.Tests.tearDown
    call = test_app.Tests.call
    payload = test_app.Tests.payload

    def with_category(self):
        rows = list(csv.reader(io.StringIO(self.data.decode('utf-8-sig')), delimiter=';'))
        rows[0].append('Categoria_equipo')
        for row in rows[1:]:
            row.append('Mini masculí')
        return rows

    def csv_bytes(self, rows):
        out = io.StringIO(newline='')
        csv.writer(out, delimiter=';').writerows(rows)
        return out.getvalue().encode('utf-8-sig')

    def test_category_preview_persistence_and_export(self):
        self.data = self.csv_bytes(self.with_category())
        preview = self.call('/api/import', 'POST', self.payload(preview=True))
        self.assertEqual(preview['status'], '200 OK')
        self.assertEqual(preview['json']['events'][0]['category'], 'Mini masculí')
        self.assertEqual(len(app.matches()), 0)
        self.assertEqual(self.call('/api/import', 'POST', self.payload())['status'], '201 Created')
        self.assertEqual(app.matches()[0]['events'][0]['category'], 'Mini masculí')
        exported = self.call('/api/export')['body']
        rows = list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(rows[0]['Categoria_equipo'], 'Mini masculí')
        match = parse('export.csv', exported)
        self.assertTrue(all(e['category'] == 'Mini masculí' for e in match['events']))

    def test_category_xlsx(self):
        book = Workbook()
        for row in self.with_category():
            book.active.append(row)
        out = io.BytesIO()
        book.save(out)
        match = parse('category.xlsx', out.getvalue())
        self.assertEqual(match['events'][0]['category'], 'Mini masculí')

    def test_optional_and_old_stored_events(self):
        self.assertEqual(parse('old.csv', self.data)['events'][0]['category'], '')
        rows = self.with_category()
        rows[1][-1] = ''
        match = parse('blank.csv', self.csv_bytes(rows))
        self.assertEqual(match['events'][0]['category'], '')
        self.assertEqual(match['events'][1]['category'], 'Mini masculí')
        self.call('/api/import', 'POST', self.payload())
        # Simulate records saved before the category field was introduced.
        import json
        with app.connect() as con:
            for record in app.matches():
                for event in record['events']:
                    event.pop('category', None)
                con.execute('UPDATE matches SET body=? WHERE id=?', (json.dumps(record), record['id']))
        self.assertEqual(self.call('/api/export')['status'], '200 OK')

    def test_duplicate_header_is_explicit(self):
        rows = self.with_category()
        rows[0][-1] = 'Equipo'
        with self.assertRaisesRegex(ImportError, 'Equipo.*Categoria_equipo'):
            parse('duplicate.csv', self.csv_bytes(rows))

    def test_reject_mixed_own_categories(self):
        rows = self.with_category()
        own = [r for r in rows[1:] if r[6] == 'MVP CERVELLÓ']
        self.assertGreater(len(own), 1)
        own[0][-1] = 'Infantil'
        with self.assertRaisesRegex(ImportError, 'una sola categoría'):
            parse('mixed.csv', self.csv_bytes(rows))
        own[0][-1] = ''
        with self.assertRaisesRegex(ImportError, 'una sola categoría'):
            parse('missing.csv', self.csv_bytes(rows))
