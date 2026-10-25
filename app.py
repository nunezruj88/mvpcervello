"""WSGI application; Gunicorn behind authenticated Nginx in production."""
import base64
import hashlib
import csv
import io
import json
import os
import sqlite3
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from wsgiref.simple_server import make_server
from contextlib import contextmanager
from datetime import datetime, timezone
from standings import scope as standings_scope, fetch_standings, parse_standings, StandingsError, SOURCES
from importer import parse, ImportError
from stats import summarize, norm, TEAM, team_matches, team_names, player_names, player_key, category_names, category_matches, TRACKED_PLAYERS, is_team
from stats import competition_matches, scoreboard

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('MVP_DB', ROOT / 'data' / 'mvp.sqlite3'))
ARCHIVE_DIR = Path(os.environ.get('MVP_IMPORT_DIR', ROOT / 'partidos'))

def archive_upload(name, data, match):
    """Keep the original bytes in a private, unique file; never trust a path."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem = re.sub(r'[^a-zA-Z0-9_-]+', '_', Path(name).stem)[:80] or 'partido'
    fd, filename = tempfile.mkstemp(prefix=f"{match['date']}_{stem}_", suffix=Path(name).suffix.lower(), dir=ARCHIVE_DIR)
    path = Path(filename)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path

@contextmanager
def import_storage():
    archived = []
    try:
        with connect() as con:
            yield con, archived
    except BaseException:
        for path in archived:
            path.unlink(missing_ok=True)
        raise

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=20)
    con.execute('CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS standings (scope TEXT PRIMARY KEY, body TEXT NOT NULL)')
    try:
        with con:
            yield con
    finally:
        con.close()

def matches():
    with connect() as con:
        return sorted([json.loads(r[0]) for r in con.execute('SELECT body FROM matches')], key=lambda m: (m['date'], m['id']))

def brief(m):
    return {k:v for k,v in m.items() if k != 'events'} | {'event_count':len(m['events'])}

def standings_import_options():
    """Local destinations, independent of the current player or screen filters."""
    options = {}
    for match in matches():
        for category in category_names([match]):
            destination = dict(category=category, competition=match.get('competition', ''), competition_date=match.get('competition_date', ''))
            try:
                key = json.dumps(standings_scope(category, destination['competition'], destination['competition_date']))
            except StandingsError:
                continue
            options.setdefault(key, destination)
    # Make the newly configured junior destination available before its first match.
    for competition, source in SOURCES.items():
        if source.get('import_category') and not any(json.loads(key)[2] == competition for key in options):
            destination = dict(category=source['import_category'], competition=source['import_competition'], competition_date='2026-10-01')
            key = json.dumps(standings_scope(destination['category'], destination['competition'], destination['competition_date']))
            options[key] = destination
    return sorted(options.values(), key=lambda v: (norm(v['category']), v['competition_date'], norm(v['competition'])))

def application(env, start_response):
    method, path = env['REQUEST_METHOD'], env.get('PATH_INFO', '/')
    qs = parse_qs(env.get('QUERY_STRING',''), keep_blank_values=True)
    headers = [('X-Content-Type-Options','nosniff'), ('Cache-Control','no-store'),
               ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")]
    def reply(body, status='200 OK', mime='application/json; charset=utf-8', extra=None):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        start_response(status, headers + [('Content-Type',mime),('Content-Length',str(len(body)))] + (extra or []))
        return [body]
    try:
        if method == 'POST':
            origin = env.get('HTTP_ORIGIN')
            if origin and urlsplit(origin).netloc != env.get('HTTP_HOST'):
                return reply({'error':'Origen de la petición no permitido.'}, '403 Forbidden')
            length = int(env.get('CONTENT_LENGTH') or 0)
            if not 0 < length <= 15 * 1024 * 1024: return reply({'error':'Carga vacía o demasiado grande.'}, '413 Payload Too Large')
            try: payload = json.loads(env['wsgi.input'].read(length))
            except (ValueError, UnicodeDecodeError): raise ImportError('Petición inválida.')
        if path == '/health' and method == 'GET': return reply({'status':'ok'})
        if path == '/api/matches' and method == 'GET':
            with connect() as con:
                saved = con.execute('SELECT body FROM matches').fetchall()
            result = []
            for (body,) in saved:
                m = json.loads(body)
                result.append(brief(m) | dict(
                    category=m.get('category') or next(iter(category_names([m])), ''),
                    players=[p['id'] for p in player_names([m], TEAM) if p['id'] in {'MNL', 'ELN'}],
                    revision=hashlib.sha256(body.encode()).hexdigest()))
            return reply({'matches': sorted(result, key=lambda m: (m['date'], m['id']), reverse=True)})
        if path == '/api/matches/delete' and method == 'POST':
            if not isinstance(payload, dict) or payload.get('confirm') is not True:
                raise ImportError('Confirma el partido que quieres borrar.')
            match_id, revision = payload.get('id'), payload.get('revision')
            if not isinstance(match_id, str) or not re.fullmatch(r'[0-9a-f]{24}', match_id):
                raise ImportError('Identificador de partido inválido.')
            if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{64}', revision):
                raise ImportError('Vuelve a cargar la lista antes de borrar.')
            with connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute('SELECT body FROM matches WHERE id=?', (match_id,)).fetchone()
                if not row:
                    return reply({'error': 'El partido ya no existe. Actualiza la lista.'}, '404 Not Found')
                if hashlib.sha256(row[0].encode()).hexdigest() != revision:
                    return reply({'error': 'El partido ha cambiado. Revisa la lista y confirma de nuevo.'}, '409 Conflict')
                con.execute('CREATE TABLE IF NOT EXISTS deleted_matches (id INTEGER PRIMARY KEY, match_id TEXT NOT NULL, body TEXT NOT NULL, deleted_at TEXT NOT NULL)')
                con.execute('INSERT INTO deleted_matches (match_id,body,deleted_at) VALUES (?,?,?)',
                            (match_id, row[0], datetime.now(timezone.utc).isoformat()))
                con.execute('DELETE FROM matches WHERE id=?', (match_id,))
            return reply({'deleted': match_id})
        if path == '/api/standings/options' and method == 'GET':
            return reply({'options': standings_import_options()})
        if path == '/api/standings/import' and method == 'POST':
            if not isinstance(payload, dict): raise ImportError('Petición inválida.')
            if not isinstance(payload.get('preview', False), bool) or not isinstance(payload.get('replace', False), bool):
                raise ImportError('Indicador de revisión o reemplazo inválido.')
            try:
                destination = {k: payload.get(k, '') for k in ('category', 'competition', 'competition_date')}
                scope = standings_scope(destination['category'], destination['competition'], destination['competition_date'])
                available = [standings_scope(o['category'], o['competition'], o['competition_date']) for o in standings_import_options()]
                if scope not in available:
                    raise ImportError('Selecciona una categoría y competición de los partidos importados.')
                name = str(payload.get('filename', '')).replace('\\', '/').split('/')[-1]
                if Path(name).suffix.lower() not in ('.html', '.htm'):
                    raise ImportError('Selecciona una página guardada en formato HTML o HTM.')
                try:
                    raw = base64.b64decode(payload.get('data', ''), validate=True)
                except (ValueError, TypeError):
                    raise ImportError('Archivo HTML inválido.')
                if not raw or len(raw) > 10 * 1024 * 1024:
                    raise ImportError('El archivo HTML está vacío o supera 10 MB.')
                try:
                    html = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    html = raw.decode('cp1252')
                snapshot = parse_standings(html, scope[2])
            except (StandingsError, UnicodeError) as exc:
                raise ImportError(str(exc)) from exc
            key = json.dumps(scope)
            with import_storage() as (con, archived):
                if not payload.get('preview', False): con.execute('BEGIN IMMEDIATE')
                existing = con.execute('SELECT body FROM standings WHERE scope=?', (key,)).fetchone()
                if payload.get('preview', False):
                    return reply(dict(standings=snapshot, destination=destination, exists=bool(existing)))
                if existing and not payload.get('replace', False):
                    return reply({'error': 'Ya hay una clasificación guardada. Confirma reemplazar para actualizarla.'}, '409 Conflict')
                now = datetime.now(timezone.utc)
                try:
                    archived.append(archive_upload('clasificacion_' + name, raw, {'date': now.date().isoformat()}))
                except OSError:
                    return reply({'error': 'No se ha podido guardar la copia HTML. Revisa permisos y espacio en partidos. La clasificación anterior se conserva.'}, '500 Internal Server Error')
                snapshot.update(updated_at=now.isoformat(), import_method='html', filename=name, archived_filename=archived[-1].name)
                con.execute('INSERT OR REPLACE INTO standings VALUES (?,?)', (key, json.dumps(snapshot, ensure_ascii=False)))
            return reply(dict(standings=snapshot, destination=destination), '201 Created')
        if path == '/api/standings' and method in ('GET', 'POST'):
            params = payload if method == 'POST' else {k: v[0] for k, v in qs.items()}
            key = json.dumps(standings_scope(params.get('category', ''), params.get('competition', ''), params.get('competition_date', '')))
            if method == 'POST':
                snapshot = fetch_standings(json.loads(key)[2])
                snapshot['updated_at'] = datetime.now(timezone.utc).isoformat()
                with connect() as con:
                    con.execute('INSERT OR REPLACE INTO standings VALUES (?,?)', (key, json.dumps(snapshot, ensure_ascii=False)))
                return reply({'standings': snapshot})
            with connect() as con:
                saved = con.execute('SELECT body FROM standings WHERE scope=?', (key,)).fetchone()
            return reply({'standings': json.loads(saved[0]) if saved else None})
        if path == '/api/data' and method == 'GET':
            all_matches = matches()
            hierarchy = qs.get('hierarchy', [''])[0] == '1'
            players = [p for p in player_names(all_matches, TEAM) if p['id'] in {'MNL', 'ELN'}] if hierarchy else TRACKED_PLAYERS
            player = player_key(qs.get('player', ['MNL'])[0])
            if player not in {p['id'] for p in players}:
                player = players[0]['id'] if players else ''
            player_matches = [m for m in all_matches if any(is_team(e['team']) and player_key(e['player']) == player for e in m['events'])] if hierarchy else all_matches
            categories = category_names([dict(m, events=[e for e in m['events'] if not is_team(e['team']) or player_key(e['player']) == player]) for m in player_matches]) if hierarchy else category_names(all_matches)
            requested = qs.get('category', [None])[0]
            category = next((c for c in categories if norm(c) == norm(requested)), requested) if requested is not None else (categories[0] if categories else '')
            if hierarchy and category not in categories:
                category = categories[0] if categories else ''
            scoped_matches = category_matches(player_matches, category)
            if hierarchy:
                scoped_matches = [m for m in scoped_matches if any(is_team(e['team']) and player_key(e['player']) == player for e in m['events'])]
            selected = qs.get('match', [''])[0]
            competition_scope = competition_matches(scoped_matches, qs.get('competition', [None])[0], qs.get('competition_date', [''])[0])
            if hierarchy and not competition_scope:
                competition_scope = scoped_matches
            if hierarchy and selected and not any(m['id'] == selected for m in competition_scope):
                selected = ''
            chosen = [m for m in competition_scope if not selected or m['id'] == selected]
            selected_scope = selected
            if not selected and 'competition' in qs and competition_matches(scoped_matches, qs['competition'][0], qs.get('competition_date', [''])[0]):
                selected_scope = 'competition:' + json.dumps([qs.get('competition_date', [''])[0], qs['competition'][0]], ensure_ascii=False, separators=(',', ':'))
            return reply(dict(categories=categories, selected_category=category, selected_team=TEAM,
                              players=players, selected_player=player, selected_scope=selected_scope,
                              matches=[brief(m) for m in scoped_matches], summary=summarize(chosen, TEAM, player),
                              scoreboard=scoreboard(chosen[0]) if selected and len(chosen) == 1 else None,
                              events=[dict(e, match_id=m['id'], date=m['date']) for m in chosen for e in m['events'] if is_team(e['team'])]))
        if path == '/api/import' and method == 'POST':
            name = str(payload.get('filename','')).replace('\\','/').split('/')[-1]
            if not isinstance(payload.get('complete',False),bool): raise ImportError('Indicador de partido completo inválido.')
            try: data = base64.b64decode(payload.get('data',''), validate=True)
            except (ValueError, TypeError): raise ImportError('Archivo inválido.')
            match = parse(name, data, payload.get('complete',False))
            with import_storage() as (con, archived):
                if not payload.get('preview', False):
                    con.execute('BEGIN IMMEDIATE')
                existing = con.execute('SELECT body FROM matches WHERE id=?',(match['id'],)).fetchone()
                legacy = None
                if not existing and match.get('legacy_id') != match['id']:
                    candidate = con.execute('SELECT body FROM matches WHERE id=?', (match['legacy_id'],)).fetchone()
                    if candidate and not any(e.get('category') for e in json.loads(candidate[0])['events'] if is_team(e['team'])):
                        legacy = match['legacy_id']
                        existing = candidate
                if payload.get('preview',False):
                    return reply(dict(match=brief(match), summary=summarize([match]), exists=bool(existing),
                                      events=match['events'][:100]))
                if existing and not payload.get('replace',False):
                    return reply({'error':'Este partido ya existe. Activa reemplazar para actualizarlo.'}, '409 Conflict')
                try:
                    archived.append(archive_upload(name, data, match))
                except OSError:
                    return reply({'error':'No se ha podido guardar la copia del fichero. Revisa permisos y espacio en la carpeta partidos. La importación no se ha guardado.'}, '500 Internal Server Error')
                match['archived_filename'] = archived[-1].name
                # Transactional replacement, never appends a second copy of this match.
                if legacy:
                    con.execute('DELETE FROM matches WHERE id=?', (legacy,))
                con.execute('INSERT OR REPLACE INTO matches VALUES (?,?)',(match['id'],json.dumps(match,ensure_ascii=False)))
            return reply({'match':brief(match)}, '201 Created')
        if path == '/api/export' and method == 'GET':
            selected = qs.get('match',[''])[0]
            team = qs.get('team',[''])[0]
            category = qs.get('category', [None])[0]
            result = category_matches(matches(), category) if category is not None else (team_matches(matches(), team) if team else matches())
            if qs.get('hierarchy', [''])[0] == '1':
                player = player_key(qs.get('player', [''])[0])
                result = [m for m in result if any(is_team(e['team']) and player_key(e['player']) == player for e in m['events'])]
            result = competition_matches(result, qs.get('competition', [None])[0], qs.get('competition_date', [''])[0])
            result = [m for m in result if not selected or m['id']==selected]
            out = io.StringIO(newline='')
            w = csv.writer(out, delimiter=';')
            w.writerow(['Orden','Fecha_partido','Local','Visitante','Periodo','Tiempo_restante','Equipo','Dorsal','Jugador','Accion_original','Puntos_accion','Observaciones','Partido_completo','Categoria_equipo','Competicion','Fecha_competicion'])
            def safe(v):
                if isinstance(v,str) and v.startswith(('=','+','-','@')): return "'"+v
                return v
            for m in result:
                for e in m['events']:
                    w.writerow([safe(v) for v in [e['order'],m['date'],m['home'],m['away'],e['period'],e['clock'],e['team'],e['number'],e['player'],e['action'],e['points'],e['notes'],'Sí' if m['complete'] else 'No',e.get('category',''),m.get('competition',''),m.get('competition_date','')]])
            return reply(out.getvalue().encode('utf-8-sig'), mime='text/csv; charset=utf-8',
                         extra=[('Content-Disposition','attachment; filename="mvp-cervello-acciones.csv"')])
        if method=='GET' and path in ('/','/app.js','/style.css','/plantilla.csv'):
            files={'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'),
                   '/style.css':('style.css','text/css; charset=utf-8'), '/plantilla.csv':('plantilla.csv','text/csv; charset=utf-8')}
            name,mime=files[path]
            return reply((ROOT/'static'/name).read_bytes(),mime=mime)
        return reply({'error':'Página no encontrada.'}, '404 Not Found')
    except StandingsError as exc: return reply({'error':str(exc)}, '502 Bad Gateway')
    except ImportError as exc: return reply({'error':str(exc)}, '400 Bad Request')
    except (ValueError, TypeError, KeyError): return reply({'error':'Formato de petición inválido.'}, '400 Bad Request')
    except Exception:
        import traceback
        traceback.print_exc()
        return reply({'error':'No se ha podido completar la operación. Los datos anteriores se conservan.'}, '500 Internal Server Error')

if __name__=='__main__':
    port=int(os.environ.get('MVP_PORT','8092'))
    print(f'MVP Cervelló: http://127.0.0.1:{port}',flush=True)
    with make_server('127.0.0.1',port,application) as server: server.serve_forever()


