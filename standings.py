"""Official standings: fetched only by the explicit refresh endpoint."""
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import URLError
from stats import norm

DEFAULT_COMPETITION = 'PRIMERA FASE-NIVEL C-1'
SOURCES = {
    DEFAULT_COMPETITION: dict(url='https://www.basquetcatala.cat/competicions/resultats/24222', category='C.T. PRE-INFANTIL MASCULI', group=10),
    'PRIMERA FASE-NIVEL C-11': dict(url='https://www.basquetcatala.cat/competicions/resultats/24360', category='C.T. MINI MASCULI', group=11),
}

class StandingsError(Exception):
    pass

def scope(category, competition, start):
    if not all(isinstance(v, str) for v in (category, competition, start)):
        raise StandingsError('Selección de competición inválida.')
    name = re.sub(r'\s*[-–—]\s*', '-', norm(competition)).replace('NIVELL', 'NIVEL')
    if re.fullmatch(r'PRIMERA FASE-NIVEL C-(?:0?1|10)', name):
        name = DEFAULT_COMPETITION
    if start != '2026-10-01' or name not in SOURCES:
        raise StandingsError('Esta competición no tiene una fuente de clasificación configurada.')
    return [norm(category), start, name]

class ClassificationParser(HTMLParser):
    def __init__(self, source):
        self.source = source
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.active = False
        self.row_depth = None
        self.parts = []
        self.rows = []
        self.heading = False
        self.title = []
        self.correct_group = False
        self.subtitle_depth = None
        self.subtitle = []
        self.round = None
        self.ignore = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.ignore += 1
        if tag in {'br','img','input','hr','meta','link','source','wbr','area','base','embed','param','track'}:
            return
        self.stack.append(tag)
        if attrs.get('id') == 'subTitle':
            self.subtitle_depth = len(self.stack)
            self.subtitle = []
        if attrs.get('id') == 'titleCategory':
            self.heading = True
        if tag == 'footer' or attrs.get('id') == 'nexround' or 'nexround' in attrs.get('class', '').split():
            self.active = False
        if self.active and (attrs.get('id') == 'fila' or 'fila' in attrs.get('class', '').split()) and self.row_depth is None:
            self.row_depth = len(self.stack)
            self.parts = []

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignore = max(0, self.ignore - 1)
        if not self.stack or tag not in self.stack:
            return
        if self.subtitle_depth == len(self.stack):
            subtitle = ' '.join(norm(' '.join(self.subtitle)).split())
            self.correct_group = subtitle == f"PRIMERA FASE - NIVELL C - {self.source['group']}"
            self.subtitle_depth = None
        if self.row_depth == len(self.stack):
            self.rows.append(self.parts)
            self.row_depth = None
        if tag == 'h2':
            self.heading = False
        while self.stack:
            if self.stack.pop() == tag:
                break

    def handle_data(self, text):
        if self.ignore:
            return
        text = text.strip()
        if self.subtitle_depth is not None and text:
            self.subtitle.append(text)
        if self.heading and text:
            self.title.append(text)
        if 'CLASSIFICACIO A LA JORNADA' in ' '.join(norm(text).split()):
            self.active = True
            found = re.search(r'JORNADA\s*(\d+)', norm(text))
            self.round = int(found[1]) if found else None
        if self.row_depth is not None and text:
            self.parts.append(text)

def parse_standings(html, competition=DEFAULT_COMPETITION):
    source = SOURCES[competition]
    parser = ClassificationParser(source)
    parser.feed(html)
    rows = []
    for parts in parser.rows:
        if len(parts) < 9 or not all(re.fullmatch(r'\d+', v) for v in [parts[0], *parts[-7:]]):
            raise StandingsError('La web ha devuelto una tabla de clasificación no reconocida.')
        values = list(map(int, parts[-7:]))
        row = dict(zip(['played','won','lost','not_played','points_for','points_against','points'], values))
        row.update(position=int(parts[0]), team=' '.join(parts[1:-7]))
        if not row['team'] or row['position'] != len(rows)+1 or row['played'] != sum(values[1:4]):
            raise StandingsError('La clasificación recibida no es válida.')
        rows.append(row)
    title = ' '.join(parser.title)
    if not rows or not parser.correct_group or source['category'] != norm(title):
        raise StandingsError('No se ha podido leer la clasificación oficial. Puede haber una verificación de seguridad. Se conserva la copia anterior.')
    return dict(rows=rows, round=parser.round, source_url=source['url'], title=title, group=f"Primera fase · Nivel C · Grupo {source['group']}")

def fetch_standings(competition=DEFAULT_COMPETITION):
    source_url = SOURCES[competition]['url']
    try:
        with urlopen(Request(source_url, headers={'User-Agent':'MVP-Cervello/1.0', 'Accept':'text/html'}), timeout=12) as response:
            if response.geturl().split('?')[0] != source_url:
                raise StandingsError('La web ha redirigido la consulta, posiblemente a una verificación de seguridad. Se conserva la copia anterior.')
            raw = response.read(2*1024*1024+1)
            if len(raw) > 2*1024*1024:
                raise StandingsError('La respuesta de la web es demasiado grande.')
            return parse_standings(raw.decode('utf-8'), competition)
    except (URLError, TimeoutError, OSError, UnicodeError) as exc:
        raise StandingsError('No se ha podido consultar la web oficial. Se conserva la copia anterior.') from exc
