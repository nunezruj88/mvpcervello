import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
import app
from standings import parse_standings, StandingsError, scope, fetch_standings

HTML = '''<h2 id="titleCategory">C.t. Pre-infantil Masculí</h2>
<div id="subTitle">Primera Fase - Nivell C - 10</div>
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

    def test_label_variations_reuse_saved_scope(self):
        expected = scope('Preinfantil', 'Primera fase - Nivel C - 1', '2026-10-01')
        for name in ['Primera Fase - Nivell C - 10', 'Primera fase - Nivel C - 01', 'Primera fase – Nivel C – 1']:
            self.assertEqual(scope('Preinfantil', name, '2026-10-01'), expected)
        with self.assertRaises(StandingsError):
            scope('Preinfantil', 'Primera fase - Nivel C - 2', '2026-10-01')

    def test_junior_group_names_share_scope(self):
        names = ['Primera Fase - Nivell C - 08', 'Primera fase - Nivel C - 8']
        keys = [scope('Junior masculí', name, '2026-10-01') for name in names]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0][2], 'PRIMERA FASE-NIVEL C-08')

    def test_group_11_uses_own_category_and_source(self):
        mini = HTML.replace('Pre-infantil', 'Mini').replace('Nivell C - 10', 'Nivell C - 11')
        parsed = parse_standings(mini, 'PRIMERA FASE-NIVEL C-11')
        self.assertTrue(parsed['source_url'].endswith('/24360'))
        self.assertTrue(parsed['group'].endswith('11'))
        with self.assertRaises(StandingsError):
            parse_standings(HTML, 'PRIMERA FASE-NIVEL C-11')
        with self.assertRaises(StandingsError):
            parse_standings(mini)

    @patch('app.fetch_standings')
    def test_both_competitions_keep_independent_saved_data(self, fetch):
        fetch.return_value = parse_standings(HTML)
        first = self.call('POST')['body']['standings']
        params = self.params | {'competition':'Primera fase - Nivel C - 11'}
        self.assertIsNone(self.call(params=params)['body']['standings'])
        mini = HTML.replace('Pre-infantil', 'Mini').replace('Nivell C - 10', 'Nivell C - 11')
        fetch.return_value = parse_standings(mini, 'PRIMERA FASE-NIVEL C-11')
        second = self.call('POST', params)['body']['standings']
        fetch.assert_called_with('PRIMERA FASE-NIVEL C-11')
        self.assertEqual(self.call()['body']['standings'], first)
        self.assertEqual(self.call(params=params)['body']['standings'], second)

    @patch('standings.urlopen')
    def test_refresh_requests_only_configured_url_for_group_11(self, urlopen):
        mini = HTML.replace('Pre-infantil', 'Mini').replace('Nivell C - 10', 'Nivell C - 11')
        response = urlopen.return_value.__enter__.return_value
        response.geturl.return_value = 'https://www.basquetcatala.cat/competicions/resultats/24360'
        response.read.return_value = mini.encode()
        result = fetch_standings('PRIMERA FASE-NIVEL C-11')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, result['source_url'])

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
        fetch.assert_called_once_with('PRIMERA FASE-NIVEL C-1')

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
