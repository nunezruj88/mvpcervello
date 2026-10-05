import csv
import io
import json
import unittest
from urllib.parse import urlencode
import test_app
import app
from importer import parse
from stats import summarize, category_matches


class SelectionTests(unittest.TestCase):
    call = test_app.Tests.call
    tearDown = test_app.Tests.tearDown

    def setUp(self):
        test_app.Tests.setUp(self)
        self.fixture_matches = []
        header = 'Fecha_partido;Local;Visitante;Periodo;Tiempo_restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_accion;Categoria_equipo\n'
        for category, mnl, eln in [('Mini masculí', 2, 3), ('Infantil', 3, 1)]:
            rows = ''.join(f'2026-10-03;CB BEGUES;MVP CERVELLÓ;P1;05:00;MVP CERVELLÓ;12;{name};Cistella de {points};{points};{category}\n'
                           for name, points in [('M.N.L.', mnl), ('E.L.N.', eln), ('OTRO', 2)])
            match = parse('fixture.csv', (header + rows).encode())
            self.fixture_matches.append(match)
            with app.connect() as con:
                con.execute('INSERT INTO matches VALUES (?,?)', (match['id'], json.dumps(match)))

    def test_category_and_player_isolation(self):
        self.assertNotEqual(self.fixture_matches[0]['id'], self.fixture_matches[1]['id'])
        for category, mnl, eln in [('Mini masculí', 2, 3), ('Infantil', 3, 1)]:
            for player, expected in [('MNL', mnl), ('E.L.N.', eln)]:
                data = self.call('/api/data', query=urlencode(dict(category=category, player=player)))['json']
                self.assertEqual(data['summary']['focus']['points'], expected)
                self.assertEqual(data['summary']['matches'], 1)
                self.assertEqual({p['id'] for p in data['players']}, {'MNL', 'ELN'})
                self.assertEqual(len(data['matches']), 1)
                self.assertEqual(data['selected_team'], 'MVP CERVELLÓ')

    def test_category_export(self):
        out = self.call('/api/export', query=urlencode(dict(category='Mini masculí')))['body']
        match = parse('export.csv', out)
        self.assertEqual(match['id'], self.fixture_matches[0]['id'])
        self.assertEqual(summarize([match])['focus']['points'], 2)

    def test_dynamic_player_category_match_relationship(self):
        match=dict(self.fixture_matches[0],id='new-player',competition='Liga junior',competition_date='2026-09-01')
        match['events']=[dict(match['events'][0],player='NUEVO',category='Junior')]
        with app.connect() as con:
            con.execute('INSERT INTO matches VALUES (?,?)',(match['id'],json.dumps(match)))
        data=self.call('/api/data',query='hierarchy=1&player=NUEVO&category=Junior&match=invalid')['json']
        self.assertEqual({p['id'] for p in data['players']},{'MNL','ELN'})
        self.assertIn(data['selected_player'],{'MNL','ELN'})
        self.assertNotIn('Junior',data['categories'])
        self.assertEqual(data['selected_scope'],'')
        self.assertNotIn('new-player',[m['id'] for m in data['matches']])
        with app.connect() as con:
            con.execute('DELETE FROM matches')
        empty=self.call('/api/data',query='hierarchy=1')['json']
        self.assertEqual(empty['players'],[])
        self.assertEqual(empty['categories'],[])
        self.assertEqual(empty['matches'],[])

    def test_unknown_and_uncategorized(self):
        data = self.call('/api/data', query='category=DESCONOCIDA')['json']
        self.assertEqual(data['summary']['matches'], 0)
        self.assertEqual(data['events'], [])
        self.assertEqual(category_matches(self.fixture_matches, ''), [])

    def test_legacy_categorized_replacement(self):
        rows = list(csv.reader(io.StringIO(self.data.decode('utf-8-sig')), delimiter=';'))
        rows[0].append('Categoria_equipo')
        for row in rows[1:]:
            row.append('Cadet')
        self.call('/api/import', 'POST', self.payload())
        original_count = len(app.matches())
        out = io.StringIO(newline='')
        csv.writer(out, delimiter=';').writerows(rows)
        self.data = out.getvalue().encode()
        preview = self.call('/api/import', 'POST', self.payload(preview=True))['json']
        self.assertTrue(preview['exists'])
        self.assertEqual(self.call('/api/import', 'POST', self.payload())['status'], '409 Conflict')
        self.assertEqual(self.call('/api/import', 'POST', self.payload(replace=True))['status'], '201 Created')
        self.assertEqual(len(app.matches()), original_count)

    payload = test_app.Tests.payload
