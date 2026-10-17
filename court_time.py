"""Count only court intervals supported by recorded substitutions."""
import re


def clock_seconds(value):
    if not re.fullmatch(r'\d{2}:[0-5]\d', str(value or '')):
        return None
    minutes, seconds = map(int, value.split(':'))
    return minutes * 60 + seconds


def playing_time(matches, team, player, normalize, identity):
    total, known, issues, relevant = 0, False, [], False
    player = identity(player)
    for match in matches:
        events = match['events']
        own = lambda e: normalize(e['team']) == normalize(team) and identity(e['player']) == player
        if not any(own(e) for e in events):
            continue
        relevant = True
        label = match.get('date', match.get('id', 'Partido'))
        def warn(message):
            text = f'{label}: {message}'
            if text not in issues:
                issues.append(text)
        duration = match.get('period_seconds')
        if duration is None:
            duration = clock_seconds(events[0].get('clock')) if events else None
        if not isinstance(duration, int) or duration <= 0:
            warn('duración del período desconocida')
            continue
        periods = sorted({int(e['period'][1:]) for e in events})
        state, last_period = None, 0
        if not match.get('complete'):
            warn('archivo parcial; el tiempo representa solo los intervalos confirmados')
        for period in periods:
            if period != last_period + 1:
                warn('faltan períodos anteriores')
                state = None
            last_period = period
            rows = [e for e in events if e['period'] == f'P{period}']
            bench_start_known = state is False
            changes = [e for e in rows if own(e) and normalize(e['action']).startswith(('ENTRA', 'SURT'))]
            start = duration if state is True else None
            previous = duration
            for event in changes:
                clock = clock_seconds(event.get('clock'))
                entering = normalize(event['action']).startswith('ENTRA')
                if clock is None or clock > duration or clock > previous:
                    warn(f'P{period}: reloj de cambios ausente o inconsistente')
                    state, start = None, None
                    if clock is None or clock > duration:
                        continue
                    previous = clock
                    # A valid later entry can start a new confirmed interval.
                    if entering:
                        state, start = True, clock
                    else:
                        state = False
                    continue
                previous = clock
                if entering:
                    if state is True:
                        if clock == duration:
                            # Reaffirmation of a starter, not a second stint.
                            start = duration
                            continue
                        warn(f'P{period}: entrada sin salida previa')
                    elif state is None and clock != duration:
                        warn(f'P{period}: no se conoce el estado antes de la primera entrada')
                    state, start = True, clock
                else:
                    if state is True:
                        total += start - clock
                        known = True
                    elif state is None:
                        if clock == duration:
                            known = True
                        else:
                            warn(f'P{period}: salida sin entrada conocida; no se supone titularidad')
                    else:
                        if clock != duration:
                            warn(f'P{period}: salida repetida sin entrada')
                    state, start = False, None
            ended = period < periods[-1] or match.get('complete') or any(
                normalize(e['action']).startswith('FINAL') for e in rows)
            if state is True:
                if ended:
                    total += start
                    known = True
                else:
                    warn(f'P{period}: intervalo abierto sin salida ni fin de período')
                    state = None
            elif state is False:
                if bench_start_known and ended:
                    known = True
            else:
                warn(f'P{period}: no hay entradas o salidas suficientes')
    return dict(playing_seconds=total if known else None,
                playing_time_complete=relevant and known and not issues,
                playing_time_issues=issues)
