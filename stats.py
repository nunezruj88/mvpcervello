"""Only aggregate events actually recorded in an imported match."""
import re
import unicodedata
from collections import defaultdict

TEAM = 'MVP CERVELLÓ'

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value)) if not unicodedata.combining(c)).upper().strip()

def is_team(value):
    return norm(value) == norm(TEAM)

def event_stats(events):
    result = dict(points=0, fouls=0, made1=0, missed1=0, made2=0, missed2=0,
                  made3=0, missed3=0, rebounds=0, assists=0, steals=0, turnovers=0, blocks=0, events=0)
    for e in events:
        a = norm(e['action'])
        result['events'] += 1
        result['points'] += e['points']
        for n in (1, 2, 3):
            if a == f'CISTELLA DE {n}': result[f'made{n}'] += 1
            if a == f'INTENT FALLAT DE {n}': result[f'missed{n}'] += 1
        # The ordinal in "1a falta" is not a count to sum.
        if a.startswith('PERSONAL') or a.startswith('FALTA'): result['fouls'] += 1
        for prefix, field in [('REBOT', 'rebounds'), ('ASSISTENCIA', 'assists'),
                              ('RECUPERACIO', 'steals'), ('PERDUA', 'turnovers'), ('TAP', 'blocks')]:
            if a.startswith(prefix): result[field] += 1
    for n in (1, 2, 3):
        attempted = result[f'made{n}'] + result[f'missed{n}']
        result[f'attempts{n}'] = attempted
        result[f'percent{n}'] = round(100 * result[f'made{n}'] / attempted, 1) if attempted else None
    return result

def summarize(matches):
    events = [dict(e, match_id=m['id'], date=m['date'], opponent=m['away'] if is_team(m['home']) else m['home'])
              for m in matches for e in m['events'] if is_team(e['team'])]
    players = defaultdict(list)
    for e in events:
        if e['player']:
            players[(e['number'], norm(e['player']))].append(e)
    ranking = [dict(number=k[0], name=v[0]['player'], **event_stats(v)) for k, v in players.items()]
    ranking.sort(key=lambda p: (-p['points'], p['name']))
    # Scope #12 to this team. Accept M.N.L. aliases even if the dorsal changes.
    focus = [e for e in events if re.sub(r'[^A-Z]', '', norm(e['player'])) == 'MNL' or e['number'] == 12]
    trend = []
    for m in matches:
        es = [e for e in events if e['match_id'] == m['id']]
        fs = [e for e in focus if e['match_id'] == m['id']]
        trend.append(dict(id=m['id'], date=m['date'], opponent=m['away'] if is_team(m['home']) else m['home'],
                          complete=m['complete'], team_points=sum(e['points'] for e in es),
                          focus_points=sum(e['points'] for e in fs)))
    periods = []
    for p in sorted({e['period'] for e in events}, key=lambda v: int(v[1:])):
        es = [e for e in events if e['period'] == p]
        fs = [e for e in focus if e['period'] == p]
        periods.append(dict(period=p, team_points=sum(e['points'] for e in es), focus_points=sum(e['points'] for e in fs)))
    return dict(team=event_stats(events), players=ranking, focus=event_stats(focus), focus_events=focus,
                periods=periods, trend=trend, matches=len(matches), partial=sum(not m['complete'] for m in matches))
