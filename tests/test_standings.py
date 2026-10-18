import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
import app
from standings import parse_standings, StandingsError

HTML = '''<h2 id="titleCategory">C.t. Pre-infantil Masculí</h2>
<div>Primera Fase - Nivell C - 10</div>
<div id="fila">Un partido, no la clasificación</div>
<div>Classificació a la jornada&nbsp;3</div>
<div id="fila"><div><div>1</div><a>CB ABRERA</a></div><div>3</div><div>3</div><div>0</div><div>0</div><div>188</div><div>99</div><div>6</div></div>
<div id="fila"><div><div>2</div><a>MVP CERVELLÓ</a></div><div>2</div><div>2</div><div>0</div><div>0</div><div>155</div><div>87</div><div>4</div></div>
<div id="nexround"><div id="fila">Próximo partido</div></div>'''

class StandingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = app.DB
        app.DB = Path(self.temp.name)/'stats.sqlite3'
        self.params = dict(category='Preinfantil masculí', competition='Primera fase - Nivel C - 1', competition_date='2026-10-01')

    def tearDown(self):
        app.DB = self.previous
        self.temp.cleanup()

    def call(self, method='GET', params=None):
        params = self.params if params is None else params
        raw = json.dumps(params).encode()
        env = dict(REQUEST_METHOD=method, PATH_INFO='/api/standings', QUERY_STRING=urlencode(params), CONTENT_LENGTH=str(len(raw)), HTTP_HOST='localhost')
        env['wsgi.input'] = io.BytesIO(raw)
        result = {}
        def start(status, headers): result['status'] = status
        result['body'] = json.loads(b''.join(app.application(env, start)))
        return result

    def test_parse_official_columns_and_ignore_matches(self):
        rows = parse_standings(HTML)['rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['team'], 'MVP CERVELLÓ')
        self.assertEqual(rows[1]['points_for'], 155)
        self.assertEqual(rows[1]['points'], 4)

    def test_reject_empty_challenge_wrong_category_and_bad_values(self):
        for html in ['Verificació de seguretat', HTML.replace('Pre-infantil', 'Júnior'), HTML.replace('<div>155</div>', '<div>—</div>')]:
            with self.assertRaises(StandingsError): parse_standings(html)

    @patch('app.fetch_standings')
    def test_get_never_fetches_even_without_saved_data(self, fetch):
        self.assertIsNone(self.call()['body']['standings'])
        fetch.assert_not_called()

    @patch('app.fetch_standings')
    def test_manual_refresh_persists_and_isolated_by_category(self, fetch):
        fetch.return_value = parse_standings(HTML)
        saved = self.call('POST')['body']['standings']
        self.assertIn('updated_at', saved)
        self.assertEqual(self.call()['body']['standings'], saved)
        self.assertIsNone(self.call(params=self.params | {'category':'Otra categoría'})['body']['standings'])
        fetch.assert_called_once_with()

    @patch('app.fetch_standings')
    def test_failed_refresh_preserves_previous_snapshot(self, fetch):
        fetch.return_value = parse_standings(HTML)
        saved = self.call('POST')['body']['standings']
        fetch.side_effect = StandingsError('Error de la fuente')
        self.assertEqual(self.call('POST')['status'], '502 Bad Gateway')
        self.assertEqual(self.call()['body']['standings'], saved)

    @patch('app.fetch_standings')
    def test_other_competition_cannot_fetch_source(self, fetch):
        result = self.call('POST', self.params | {'competition':'Otra liga'})
        self.assertNotEqual(result['status'], '200 OK')
        fetch.assert_not_called()
