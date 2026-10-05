"""WSGI application; Gunicorn behind authenticated Nginx in production."""
import base64
import csv
import io
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from wsgiref.simple_server import make_server
from contextlib import contextmanager
from importer import parse, ImportError
from stats import summarize, norm, TEAM, team_matches, team_names, player_names, player_key, category_names, category_matches, TRACKED_PLAYERS, is_team
from stats import competition_matches, scoreboard

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('MVP_DB', ROOT / 'data' / 'mvp.sqlite3'))

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=20)
    con.execute('CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
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
        if path == '/api/data' and method == 'GET':
            all_matches = matches()
            categories = category_names(all_matches)
            requested = qs.get('category', [None])[0]
            category = next((c for c in categories if norm(c) == norm(requested)), requested) if requested is not None else (categories[0] if categories else '')
            player = player_key(qs.get('player', ['MNL'])[0])
            if player not in {'MNL', 'ELN'}:
                player = 'MNL'
            scoped_matches = category_matches(all_matches, category)
            selected = qs.get('match', [''])[0]
            competition_scope = competition_matches(scoped_matches, qs.get('competition', [None])[0], qs.get('competition_date', [''])[0])
            chosen = [m for m in competition_scope if not selected or m['id'] == selected]
            return reply(dict(categories=categories, selected_category=category, selected_team=TEAM,
                              players=TRACKED_PLAYERS, selected_player=player,
                              matches=[brief(m) for m in scoped_matches], summary=summarize(chosen, TEAM, player),
                              scoreboard=scoreboard(chosen[0]) if selected and len(chosen) == 1 else None,
                              events=[dict(e, match_id=m['id'], date=m['date']) for m in chosen for e in m['events'] if is_team(e['team'])]))
        if path == '/api/import' and method == 'POST':
            name = str(payload.get('filename','')).replace('\\','/').split('/')[-1]
            if not isinstance(payload.get('complete',False),bool): raise ImportError('Indicador de partido completo inválido.')
            try: data = base64.b64decode(payload.get('data',''), validate=True)
            except (ValueError, TypeError): raise ImportError('Archivo inválido.')
            match = parse(name, data, payload.get('complete',False))
            with connect() as con:
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
