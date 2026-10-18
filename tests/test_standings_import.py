import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
import app
from test_standings import HTML

MINI_HTML = HTML.replace('Pre-infantil', 'Mini').replace('Nivell C - 10', 'Nivell C -  11')
JUNIOR_HTML = HTML.replace('C.t. Pre-infantil Masculí', 'C.t. Júnior Masculí Promoció').replace('Nivell C - 10', 'Nivell C -  08')

class StandingsImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_archive = app.DB, app.ARCHIVE_DIR
        app.DB = Path(self.temp.name)/'test.sqlite3'
        app.ARCHIVE_DIR = Path(self.temp.name)/'partidos'
        self.destination = dict(category='Mini masculí', competition='Primera fase - Nivel C - 11', competition_date='2026-10-01')
        self.preinfantil = self.destination | {'category':'Preinfantil masculí', 'competition':'Primera fase - Nivel C - 1'}
        with app.connect() as con:
            for index, d in enumerate([self.destination, self.preinfantil]):
                match = dict(id=str(index), home='MVP CERVELLÓ', away='Rival', date='2026-10-17', competition=d['competition'], competition_date=d['competition_date'], events=[dict(team='MVP CERVELLÓ', category=d['category'])])
                con.execute('INSERT INTO matches VALUES (?,?)', (match['id'], json.dumps(match)))
        self.network = patch('standings.urlopen', side_effect=AssertionError('Manual import must not access the network'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        app.DB, app.ARCHIVE_DIR = self.old_db, self.old_archive
        self.temp.cleanup()

    def call(self, path='/api/standings/import', method='POST', payload=None, query=None):
        raw = json.dumps(payload or {}).encode()
        env = dict(REQUEST_METHOD=method, PATH_INFO=path, CONTENT_LENGTH=str(len(raw)), HTTP_HOST='localhost', QUERY_STRING=urlencode(query or {}))
        env['wsgi.input'] = io.BytesIO(raw)
        result = {}
        def start(status, headers): result.update(status=status)
        result['body'] = json.loads(b''.join(app.application(env, start)))
        return result

    def payload(self, **extra):
        return self.destination | dict(filename='clasificacion.html', data=base64.b64encode(MINI_HTML.encode()).decode()) | extra

    def saved(self, destination=None):
        return self.call('/api/standings', 'GET', query=destination or self.destination)['body']['standings']

    def test_options_use_all_local_categories(self):
        options = self.call('/api/standings/options', 'GET')['body']['options']
        self.assertEqual(len(options), 3)
        self.assertIn(self.destination, options)
        self.assertIn(self.preinfantil, options)

    def test_junior_destination_available_without_matches_and_saved_separately(self):
        options = self.call('/api/standings/options', 'GET')['body']['options']
        junior = next(o for o in options if o['competition'].endswith('08'))
        self.assertEqual(junior['category'], 'Junior masculí')
        raw = base64.b64encode(JUNIOR_HTML.encode()).decode()
        result = self.call(payload=junior | dict(filename='junior.html', data=raw, preview=True))
        self.assertEqual(result['status'], '200 OK')
        self.assertTrue(result['body']['standings']['source_url'].endswith('/23926'))
        self.assertEqual(self.call(payload=junior | dict(filename='junior.html', data=raw))['status'], '201 Created')
        self.assertEqual(self.saved(junior)['group'], 'Primera fase · Nivel C · Grupo 08')
        self.assertIsNone(self.saved())
        self.assertIsNone(self.saved(self.preinfantil))

    def test_existing_junior_match_destination_is_reused_without_duplicate(self):
        match = dict(id='junior', date='2026-10-03', home='MVP CERVELLÓ', away='Rival', competition='Primera fase - Nivel C - 8', competition_date='2026-10-01', events=[dict(team='MVP CERVELLÓ', category='Júnior masculí')])
        with app.connect() as con:
            con.execute('INSERT INTO matches VALUES (?,?)', (match['id'], json.dumps(match)))
        options = self.call('/api/standings/options', 'GET')['body']['options']
        self.assertEqual(len(options), 3)
        self.assertEqual(sum(o['competition'] == 'Primera fase - Nivel C - 8' for o in options), 1)

    def test_mini_html_cannot_replace_junior_classification(self):
        junior = dict(category='Junior masculí', competition='Primera Fase - Nivell C - 08', competition_date='2026-10-01')
        result = self.call(payload=self.payload(**junior, preview=True))
        self.assertEqual(result['status'], '400 Bad Request')

    def test_preview_never_persists_or_archives(self):
        result = self.call(payload=self.payload(preview=True))
        self.assertEqual(result['status'], '200 OK')
        self.assertEqual(result['body']['standings']['round'], 3)
        self.assertEqual(len(result['body']['standings']['rows']), 2)
        self.assertFalse(result['body']['exists'])
        self.assertIsNone(self.saved())
        self.assertFalse(app.ARCHIVE_DIR.exists())

    def test_save_and_confirmed_replacement_archive_exact_originals(self):
        self.assertEqual(self.call(payload=self.payload())['status'], '201 Created')
        first = self.saved()
        self.assertEqual(first['import_method'], 'html')
        self.assertEqual((app.ARCHIVE_DIR/first['archived_filename']).read_bytes(), MINI_HTML.encode())
        self.assertTrue(self.call(payload=self.payload(preview=True))['body']['exists'])
        self.assertEqual(self.call(payload=self.payload())['status'], '409 Conflict')
        self.assertEqual(self.saved(), first)
        changed = MINI_HTML.replace('<div>155</div>', '<div>157</div>')
        result = self.call(payload=self.payload(replace=True, data=base64.b64encode(changed.encode()).decode()))
        self.assertEqual(result['status'], '201 Created')
        self.assertEqual(self.saved()['rows'][1]['points_for'], 157)
        self.assertEqual(len(list(app.ARCHIVE_DIR.iterdir())), 2)

    def test_mismatched_file_and_bad_requests_preserve_existing_data(self):
        self.call(payload=self.payload())
        first = self.saved()
        for extra in [dict(data=base64.b64encode(HTML.encode()).decode()), dict(filename='bad.csv'), dict(data='invalid!'), dict(data=''), dict(preview='yes'), dict(category='Unknown')]:
            result = self.call(payload=self.payload(replace=True, **extra))
            self.assertEqual(result['status'], '400 Bad Request', result)
            self.assertEqual(self.saved(), first)
        self.assertIsNone(self.saved(self.preinfantil))
        self.assertEqual(len(list(app.ARCHIVE_DIR.iterdir())), 1)

    def test_write_failure_preserves_previous_snapshot(self):
        self.call(payload=self.payload())
        first = self.saved()
        with patch('app.archive_upload', side_effect=OSError('disk full')):
            result = self.call(payload=self.payload(replace=True))
        self.assertEqual(result['status'], '500 Internal Server Error')
        self.assertEqual(self.saved(), first)

    def test_sql_failure_rolls_back_and_removes_new_original(self):
        with app.connect() as con:
            con.execute("CREATE TRIGGER deny_standings BEFORE INSERT ON standings BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with patch('traceback.print_exc'):
            result = self.call(payload=self.payload())
        self.assertEqual(result['status'], '500 Internal Server Error')
        self.assertIsNone(self.saved())
        self.assertEqual(list(app.ARCHIVE_DIR.iterdir()), [])

    def test_windows_encoding_and_script_content(self):
        raw = ('<script>Classificació a la jornada 99</script>' + MINI_HTML).encode('cp1252')
        result = self.call(payload=self.payload(data=base64.b64encode(raw).decode(), preview=True))
        self.assertEqual(result['status'], '200 OK')
        self.assertEqual(result['body']['standings']['round'], 3)

    def test_group_is_read_from_subtitle_not_dropdown_options(self):
        wrong_group = MINI_HTML.replace('Nivell C -  11', 'Nivell C -  12')
        wrong_group = '<select><option>Primera Fase - Nivell C - 11</option></select>' + wrong_group
        result = self.call(payload=self.payload(data=base64.b64encode(wrong_group.encode()).decode(), preview=True))
        self.assertEqual(result['status'], '400 Bad Request')
        self.assertIsNone(self.saved())
