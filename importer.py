import base64
import csv
import hashlib
import io
import re
import zipfile
from datetime import date, datetime, time
from openpyxl import load_workbook
from stats import norm, is_team

HEADERS = ['Orden', 'Fecha_partido', 'Local', 'Visitante', 'Periodo', 'Tiempo_restante', 'Equipo',
           'Dorsal', 'Jugador', 'Accion_original', 'Puntos_Begues_periodo', 'Puntos_Cervello_periodo', 'Puntos_accion', 'Observaciones', 'Categoria_equipo']
REQUIRED = ['Fecha_partido','Local','Visitante','Periodo','Tiempo_restante','Equipo','Dorsal','Jugador','Accion_original','Puntos_accion']
MAX_BYTES = 10 * 1024 * 1024

class ImportError(ValueError):
    pass

def read_rows(name, data):
    if len(data) > MAX_BYTES: raise ImportError('El archivo supera 10 MB.')
    if name.lower().endswith('.xlsx'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > 50 * 1024 * 1024 or len(z.infolist()) > 1000:
                    raise ImportError('El Excel descomprimido es demasiado grande.')
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
            sheet = book.worksheets[0]
            if (sheet.max_row or 0) > 20001 or (sheet.max_column or 0) > 50:
                book.close()
                raise ImportError('Máximo 20.000 filas y 50 columnas.')
            values = []
            for row in sheet.iter_rows():
                if len(values) > 20000: raise ImportError('Máximo 20.000 filas.')
                if len(row) > 50: raise ImportError('Máximo 50 columnas.')
                if any(c.data_type == 'f' for c in row): raise ImportError('Usa valores, no fórmulas, en el Excel.')
                values.append([c.value for c in row])
            book.close()
        except ImportError: raise
        except Exception as exc: raise ImportError('No se puede leer este Excel. Usa .xlsx sin contraseña.') from exc
    elif name.lower().endswith('.csv'):
        try: text = data.decode('utf-8-sig')
        except UnicodeDecodeError: text = data.decode('cp1252')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=';,\t')
            values = list(csv.reader(io.StringIO(text), dialect))
        except csv.Error as exc: raise ImportError('No se puede reconocer el separador del CSV.') from exc
        if len(values) > 20001: raise ImportError('Máximo 20.000 filas.')
    else: raise ImportError('Selecciona un archivo .xlsx o .csv.')
    if not values: raise ImportError('El archivo está vacío.')
    headers = [str(v or '').strip() for v in values[0]]
    repeated = sorted({h for h in headers if headers.count(h) > 1})
    if repeated: raise ImportError('Hay cabeceras repetidas: ' + ', '.join(repeated) + '. Usa Equipo para el club y Categoria_equipo para la categoría.')
    missing = [h for h in REQUIRED if h not in headers]
    if missing: raise ImportError('Faltan columnas: ' + ', '.join(missing))
    result = []
    for i, row in enumerate(values[1:], 2):
        if not any(v is not None and str(v).strip() for v in row): continue
        if len(row) > len(headers): raise ImportError(f'Fila {i}: más valores que cabeceras.')
        r = dict(zip(headers, row + [''] * (len(headers) - len(row))))
        r['_line'] = i
        result.append(r)
    if not result: raise ImportError('No hay acciones en el archivo.')
    return result

def text(v): return '' if v is None else str(v).strip()

def integer(v, field, line, blank=False):
    if blank and text(v) == '': return None
    try:
        n = float(v)
        if not n.is_integer() or n < 0 or n > 999: raise ValueError()
        return int(n)
    except (ValueError, TypeError, OverflowError): raise ImportError(f'Fila {line}: {field} debe ser un entero positivo o cero.')

def parse(name, data, complete=False):
    rows = read_rows(name, data)
    events, identities = [], set()
    unknown = set()
    for r in rows:
        line = r['_line']
        dt = r['Fecha_partido']
        try:
            if isinstance(dt, (date, datetime)): dt = dt.strftime('%Y-%m-%d')
            else:
                dt = text(dt)
                dt = datetime.strptime(dt, '%d/%m/%Y').strftime('%Y-%m-%d') if '/' in dt else date.fromisoformat(dt).isoformat()
        except ValueError: raise ImportError(f'Fila {line}: fecha inválida; usa AAAA-MM-DD o DD/MM/AAAA.')
        home, away = text(r['Local']), text(r['Visitante'])
        if not home or not away or norm(home) == norm(away): raise ImportError(f'Fila {line}: equipos inválidos.')
        identities.add((dt, norm(home), norm(away)))
        p = norm(r['Periodo'])
        if not re.fullmatch(r'P(?:[1-9]|[1-9][0-9])', p): raise ImportError(f'Fila {line}: período inválido, usa P1, P2…')
        clock = r['Tiempo_restante']
        if isinstance(clock, time): clock = clock.strftime('%M:%S')
        clock = text(clock)
        if clock and not re.fullmatch(r'\d{2}:[0-5]\d', clock): raise ImportError(f'Fila {line}: tiempo inválido, usa MM:SS.')
        team, player, action = text(r['Equipo']), text(r['Jugador']), text(r['Accion_original'])
        if not action: raise ImportError(f'Fila {line}: falta la acción.')
        if team and norm(team) not in (norm(home), norm(away)): raise ImportError(f'Fila {line}: equipo de la acción desconocido.')
        if team and (not player or not clock): raise ImportError(f'Fila {line}: falta jugador o tiempo de la acción.')
        number = integer(r['Dorsal'], 'Dorsal', line, True)
        points = integer(r['Puntos_accion'], 'Puntos_accion', line, True)
        points = 0 if points is None else points
        expected = re.fullmatch(r'CISTELLA DE ([123])', norm(action))
        if points > 3 or (expected and points != int(expected[1])) or (not expected and points):
            raise ImportError(f'Fila {line}: puntos incompatibles con la acción.')
        if not norm(action).startswith(('CISTELLA','INTENT FALLAT','PERSONAL','FALTA','SALT','FINAL','SURT','ENTRA','REBOT','ASSISTENCIA','RECUPERACIO','PERDUA','TAP')):
            unknown.add(action)
        events.append(dict(order=len(events)+1, period=p, clock=clock, team=team, number=number, player=player,
                           action=action, points=points, notes=text(r.get('Observaciones')),
                           category=text(r.get('Categoria_equipo'))))
    if len(identities) != 1: raise ImportError('Cada archivo debe contener un solo partido.')
    dt, h, a = next(iter(identities))
    categories = {norm(e.get('category', '')) for e in events if is_team(e['team']) and e.get('category')}
    if len(categories) > 1:
        raise ImportError('Cada archivo debe contener una sola categoría del MVP Cervelló.')
    category_key = next(iter(categories), '')
    identity = f'{dt}|{h}|{a}' + (f'|{category_key}' if category_key else '')
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    legacy_id = hashlib.sha256(f'{dt}|{h}|{a}'.encode()).hexdigest()[:24]
    warnings = ['El marcador de cada tarjeta corresponde al período, no al acumulado del partido.']
    if not complete: warnings.append('Importación parcial: las estadísticas solo representan las acciones subidas.')
    if unknown: warnings.append('Acciones conservadas sin clasificación estadística: ' + ', '.join(sorted(unknown)))
    # Remove overlaps only across recordings before exporting. Identical actions may be legitimate.
    duplicates = len(events) - len({(e['period'],e['clock'],norm(e['team']),e['number'],norm(e['action'])) for e in events})
    if duplicates: warnings.append(f'{duplicates} acciones coinciden en período, tiempo, jugador y tipo. Revisar: se han conservado.')
    return dict(id=key, date=dt, home=text(rows[0]['Local']), away=text(rows[0]['Visitante']), complete=bool(complete),
                filename=name, legacy_id=legacy_id, events=events, warnings=warnings, source_hash=hashlib.sha256(data).hexdigest())
