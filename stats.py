"""Only aggregate events actually recorded in an imported match."""
import re
import unicodedata
from collections import defaultdict

TEAM = 'MVP CERVELLÓ'

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value)) if not unicodedata.combining(c)).upper().strip()

def is_team(value):
    return norm(value) == norm(TEAM)

def player_key(value):
    return re.sub(r'[^\w]', '', norm(value))

def team_matches(matches, team):
    return [m for m in matches if norm(team) in (norm(m['home']), norm(m['away']))]

def competition_matches(matches, competition=None, start=None):
    if competition is None:
        return matches
    return [m for m in matches if norm(m.get('competition', '')) == norm(competition)
            and m.get('competition_date', '') == (start or '')]

def scoreboard(match):
    return dict(home=match['home'], away=match['away'], complete=match['complete'],
                home_points=sum(e['points'] for e in match['events'] if norm(e['team']) == norm(match['home'])),
                away_points=sum(e['points'] for e in match['events'] if norm(e['team']) == norm(match['away'])))

def team_names(matches):
    names = {}
    for m in matches:
        for name in (m['home'], m['away']):
            names.setdefault(norm(name), name)
    return sorted(names.values(), key=norm)

def player_names(matches, team):
    names = {}
    for m in team_matches(matches, team):
        for e in m['events']:
            if norm(e['team']) == norm(team) and e['player'] and player_key(e['player']) != 'EQUIPO':
                names.setdefault(player_key(e['player']), e['player'])
    return [dict(id=k, name=v) for k, v in sorted(names.items(), key=lambda item: norm(item[1]))]

TRACKED_PLAYERS = [dict(id='MNL', name='M.N.L.'), dict(id='ELN', name='E.L.N.')]

def category_names(matches):
    names = {}
    for m in team_matches(matches, TEAM):
        for e in m['events']:
            if is_team(e['team']):
                value = str(e.get('category', '')).strip()
                names.setdefault(norm(value), value)
    return sorted(names.values(), key=norm)

def category_matches(matches, category):
    result = []
    for m in team_matches(matches, TEAM):
        own = [e for e in m['events'] if is_team(e['team'])]
        if not any(norm(e.get('category', '')) == norm(category) for e in own):
            continue
        # Keep only this category's MVP actions. Opponent actions are retained
        # for the selected match and cannot contribute to MVP statistics.
        events = [e for e in m['events'] if not is_team(e['team']) or norm(e.get('category', '')) == norm(category)]
        reduced = any(norm(e.get('category', '')) != norm(category) for e in own)
        result.append(dict(m, events=events, complete=m['complete'] and not reduced))
    return result

def mvp_score(stats):
    """Shared rating for the MVP selection and every player's table row."""
    made = sum(stats[f'made{n}'] for n in (1, 2, 3))
    missed = sum(stats[f'attempts{n}'] for n in (1, 2, 3)) - made
    return stats['points'] + made - missed - stats['fouls']


def event_stats(events):
    result = dict(points=0, fouls=0, made1=0, missed1=0, made2=0, missed2=0,
                  made3=0, missed3=0, rebounds=0, assists=0, steals=0, turnovers=0, blocks=0, timeouts=0, events=0)
    for e in events:
        a = norm(e['action'])
        result['events'] += 1
        if a == 'TEMPS MORT': result['timeouts'] += 1
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
    result['mvp_score'] = mvp_score(result)
    return result

def playing_time(matches, team, player):
    from court_time import playing_time as calculate
    return calculate(matches, team, player, norm, player_key)


def playing_seconds(matches, team, player):
    """Confirmed intervals, including P1 when initial entries are recorded."""
    return playing_time(matches, team, player)['playing_seconds']


def select_mvp(players):
    """Custom recorded-data rating, not an official basketball valuation."""
    candidates = []
    for p in players:
        made = sum(p[f'made{n}'] for n in (1, 2, 3))
        attempts = sum(p[f'attempts{n}'] for n in (1, 2, 3))
        if not attempts:
            continue
        score = mvp_score(p)
        efficiency = made / attempts
        candidates.append((score, efficiency, p['points'], -p['fouls'], p))
    if not candidates:
        return None
    best = max(c[:4] for c in candidates)
    winners = sorted([c[4] for c in candidates if c[:4] == best], key=lambda p: norm(p['name']))
    p = winners[0]
    return dict(players=[p['name'] for p in winners], score=best[0], points=p['points'],
                shooting_percent=round(best[1] * 100, 1), fouls=p['fouls'])


def summarize(matches, team=TEAM, player='MNL'):
    matches = team_matches(matches, team)
    events = [dict(e, match_id=m['id'], date=m['date'], opponent=m['away'] if norm(m['home']) == norm(team) else m['home'])
              for m in matches for e in m['events'] if norm(e['team']) == norm(team)]
    players = defaultdict(list)
    for e in events:
        if e['player'] and player_key(e['player']) != 'EQUIPO':
            players[player_key(e['player'])].append(e)
    ranking = []
    for key, es in players.items():
        numbers = sorted({e['number'] for e in es if e['number'] is not None})
        ranking.append(dict(id=key, number=numbers[0] if len(numbers) == 1 else None,
                            numbers=numbers, name=es[0]['player'], **playing_time(matches, team, key), **event_stats(es)))
    ranking.sort(key=lambda p: (-p['points'], p['name']))
    # The name identifies the player; jersey numbers can change or be reused.
    focus = [e for e in events if player_key(e['player']) == player_key(player)]
    trend = []
    for m in matches:
        es = [e for e in events if e['match_id'] == m['id']]
        fs = [e for e in focus if e['match_id'] == m['id']]
        opponent = m['away'] if norm(m['home']) == norm(team) else m['home']
        rival_stats = event_stats([e for e in m['events'] if norm(e['team']) == norm(opponent)])
        match_players = defaultdict(list)
        for e in es:
            if e['player'] and player_key(e['player']) != 'EQUIPO':
                match_players[player_key(e['player'])].append(e)
        match_mvp = select_mvp([dict(name=rows[0]['player'], **event_stats(rows)) for rows in match_players.values()])
        trend.append(dict(team_fouls=event_stats(es)['fouls'], opponent_fouls=rival_stats['fouls'],
                          opponent_points=rival_stats['points'], mvp=match_mvp,
                          id=m['id'], date=m['date'], opponent=m['away'] if norm(m['home']) == norm(team) else m['home'],
                          complete=m['complete'], team_points=sum(e['points'] for e in es),
                          focus_points=sum(e['points'] for e in fs)))
    periods = []
    opponent_events = [e for m in matches for e in m['events']
                       if norm(e['team']) == norm(m['away'] if norm(m['home']) == norm(team) else m['home'])]
    for p in sorted({e['period'] for e in events + opponent_events}, key=lambda v: int(v[1:])):
        es = [e for e in events if e['period'] == p]
        fs = [e for e in focus if e['period'] == p]
        periods.append(dict(period=p, team_points=sum(e['points'] for e in es),
                            opponent_points=sum(e['points'] for e in opponent_events if e['period'] == p),
                            focus_points=sum(e['points'] for e in fs)))
    return dict(team=event_stats(events), opponent=event_stats(opponent_events), players=ranking, mvp=select_mvp(ranking), focus=dict(event_stats(focus), **playing_time(matches, team, player)), focus_events=focus,
                periods=periods, trend=trend, matches=len(matches), partial=sum(not m['complete'] for m in matches))


