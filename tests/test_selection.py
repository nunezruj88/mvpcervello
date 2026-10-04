import csv
import io
import json
import unittest
from urllib.parse import urlencode
import test_app
import app
from importer import parse
from stats import summarize


class SelectionTests(unittest.TestCase):
    call = test_app.Tests.call
    tearDown = test_app.Tests.tearDown

    def setUp(self):
        test_app.Tests.setUp(self)
        header = 'Fecha_partido;Local;Visitante;Periodo;Tiempo_restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_accion\n'
        fixtures = [
            ('2026-10-01', 'MVP CERVELLÓ', 'RIVAL A', [('M.N.L.', 12, 2), ('SEGUNDO', 9, 3), ('OTRO', 12, 1)]),
            ('2026-10-02', 'EQUIPO B', 'RIVAL B', [('MNL', 8, 3), ('SEGUNDO', 12, 2)]),
            ('2026-10-03', 'MVP CERVELLÓ', 'RIVAL A', [('MNL', 7, 3)]),
        ]
        self.fixture_matches = []
        for dt, team, rival, players in fixtures:
            rows = ''.join(f'{dt};{team};{rival};P1;05:00;{team};{number};{name};Cistella de {points};{points}\n'
                           for name, number, points in players)
            m = parse('fixture.csv', (header + rows).encode())
            self.fixture_matches.append(m)
            with app.connect() as con:
                con.execute('INSERT INTO matches VALUES (?,?)', (m['id'], json.dumps(m)))

    def test_team_and_player_isolation(self):
        a = self.call('/api/data', query=urlencode(dict(team='MVP CERVELLÓ', player='MNL')))['json']
        b = self.call('/api/data', query=urlencode(dict(team='EQUIPO B', player='M.N.L.')))['json']
        self.assertEqual(a['summary']['team']['points'], 9)
        self.assertEqual(a['summary']['focus']['points'], 5)
        self.assertEqual(a['summary']['matches'], 2)
        self.assertEqual(b['summary']['team']['points'], 5)
        self.assertEqual(b['summary']['focus']['points'], 3)
        self.assertEqual(b['summary']['matches'], 1)
        self.assertEqual({e['team'] for e in b['events']}, {'EQUIPO B'})
        mnl = next(p for p in a['summary']['players'] if p['id'] == 'MNL')
        self.assertEqual(mnl['numbers'], [7, 12])
        self.assertEqual(mnl['points'], 5)
        for team, points in [('MVP CERVELLÓ', 3), ('EQUIPO B', 2)]:
            data = self.call('/api/data', query=urlencode(dict(team=team, player='SEGUNDO')))['json']
            self.assertEqual(data['summary']['focus']['points'], points)

    def test_match_filter_and_export(self):
        m = self.fixture_matches[0]
        data = self.call('/api/data', query=urlencode(dict(team='MVP CERVELLÓ', player='MNL', match=m['id'])))['json']
        self.assertEqual(data['summary']['focus']['points'], 2)
        self.assertEqual(len(data['matches']), 2)
        self.assertEqual(len(data['players']), 3)
        out = self.call('/api/export', query=urlencode(dict(team='EQUIPO B')))['body']
        rows = list(csv.DictReader(io.StringIO(out.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual({r['Equipo'] for r in rows}, {'EQUIPO B'})
        self.assertEqual(summarize([parse('export.csv', out)], 'EQUIPO B')['team']['points'], 5)

    def test_unknown_selection_returns_no_mixed_data(self):
        data = self.call('/api/data', query='team=DESCONOCIDO&player=MNL')['json']
        self.assertEqual(data['summary']['matches'], 0)
        self.assertEqual(data['events'], [])
        data = self.call('/api/data', query='team=EQUIPO+B&player=DESCONOCIDO')['json']
        self.assertEqual(data['summary']['focus']['points'], 0)

    def test_name_required_for_focus_not_number(self):
        m = self.fixture_matches[0]
        self.assertEqual(summarize([m])['focus']['points'], 2)
        self.assertEqual(summarize([m], player='OTRO')['focus']['points'], 1)
