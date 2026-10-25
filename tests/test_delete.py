import io
import json
import tempfile
import unittest
from pathlib import Path
import app


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = Path(self.temp.name) / 'test.sqlite3'
        self.original = Path(self.temp.name) / 'original.csv'
        self.original.write_text('original')
        with app.connect() as con:
            for key, category in [('a'*24, ''), ('b'*24, 'Junior masculí')]:
                event = dict(order=1, period='P1', clock='10:00', team='MVP CERVELLÓ',
                             number=12, player='M.N.L.', action='Cistella de 2', points=2,
                             notes='', category=category)
                match = dict(id=key, date='2026-10-25', home='MVP CERVELLÓ', away='RIVAL',
                             category=category, complete=False, events=[event], filename='original.csv',
                             archived_filename=str(self.original), period_seconds=600)
                con.execute('INSERT INTO matches VALUES (?,?)', (key, json.dumps(match)))
            con.execute('INSERT INTO standings VALUES (?,?)', ('league', '{}'))

    def tearDown(self):
        app.DB = self.old_db
        self.temp.cleanup()

    def call(self, path, method='GET', payload=None, origin=None, query=''):
        raw = json.dumps(payload).encode()
        env = dict(REQUEST_METHOD=method, PATH_INFO=path, QUERY_STRING=query,
                   HTTP_HOST='localhost', CONTENT_LENGTH=str(len(raw)))
        env['wsgi.input'] = io.BytesIO(raw)
        if origin: env['HTTP_ORIGIN'] = origin
        response = {}
        def start(status, headers): response['status'] = status
        response['body'] = json.loads(b''.join(app.application(env, start)))
        return response

    def request(self):
        rows = self.call('/api/matches', query='category=Junior&player=ELN')['body']['matches']
        self.assertEqual(len(rows), 2)
        row = next(m for m in rows if not m['category'])
        return dict(id=row['id'], revision=row['revision'], confirm=True)

    def test_delete_only_selected_duplicate_and_keep_backup(self):
        request = self.request()
        self.assertEqual(self.call('/api/matches/delete', 'POST', request)['status'], '200 OK')
        self.assertEqual([m['id'] for m in app.matches()], ['b'*24])
        with app.connect() as con:
            body = json.loads(con.execute('SELECT body FROM deleted_matches').fetchone()[0])
            self.assertEqual(body['id'], 'a'*24)
            self.assertEqual(con.execute('SELECT count(*) FROM standings').fetchone()[0], 1)
        self.assertEqual(self.original.read_text(), 'original')
        data = self.call('/api/data', query='hierarchy=1&player=MNL&category=')['body']
        self.assertEqual(data['categories'], ['Junior masculí'])
        self.assertEqual(data['summary']['team']['points'], 2)
        self.assertEqual(self.call('/api/matches/delete', 'POST', request)['status'], '404 Not Found')

    def test_requires_confirmation_and_same_origin(self):
        req = self.request()
        for bad in (None, [], {}, dict(req, confirm=False), dict(req, id='../bad'), dict(req, revision='')):
            self.assertEqual(self.call('/api/matches/delete', 'POST', bad)['status'], '400 Bad Request')
        self.assertEqual(self.call('/api/matches/delete', 'POST', req, 'https://other.example')['status'], '403 Forbidden')
        self.assertEqual(len(app.matches()), 2)

    def test_changed_match_is_not_deleted(self):
        req = self.request()
        with app.connect() as con:
            con.execute('UPDATE matches SET body=body || ? WHERE id=?', (' ', req['id']))
        self.assertEqual(self.call('/api/matches/delete', 'POST', req)['status'], '409 Conflict')
        self.assertEqual(len(app.matches()), 2)

    def test_delete_last_match_leaves_empty_selectors(self):
        for row in self.call('/api/matches')['body']['matches']:
            self.call('/api/matches/delete', 'POST', dict(id=row['id'], revision=row['revision'], confirm=True))
        data = self.call('/api/data', query='hierarchy=1&player=MNL')['body']
        self.assertEqual(data['categories'], [])
        self.assertEqual(data['matches'], [])
        self.assertEqual(data['players'], [])
