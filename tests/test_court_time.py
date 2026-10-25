import unittest
from stats import playing_time, summarize


def event(clock, action, period='P1', player='M.N.L.', team='MVP CERVELLÓ'):
    return dict(clock=clock, action=action, period=period, player=player,
                team=team, points=0, number=12)


def match(events, complete=True, duration=360):
    return dict(id='one', date='2026-10-17', home='MVP CERVELLÓ', away='RIVAL',
                complete=complete, period_seconds=duration, events=events)


class CourtTimeTests(unittest.TestCase):
    def final_period_events(self, last):
        events = [event('06:00', 'Entra al camp'), event('06:00', 'Surt del camp')]
        events += [event('', 'Final de període', f'P{p}', player='', team='')
                   for p in range(1, last)]
        events.append(event('02:30', 'Entra al camp', f'P{last}'))
        return events

    def test_p4_and_p8_open_entry_runs_to_buzzer_without_incomplete(self):
        for last in (4, 8):
            with self.subTest(last=last):
                s = self.calculate(self.final_period_events(last), complete=False)
                self.assertEqual(s['playing_seconds'], 150)
                self.assertTrue(s['playing_time_complete'])
                self.assertEqual(s['playing_time_issues'], [])

    def test_final_period_explicit_exit_stops_time(self):
        for last in (4, 8):
            events = self.final_period_events(last)
            events.append(event('00:30', 'Surt del camp', f'P{last}'))
            s = self.calculate(events, complete=False)
            self.assertEqual(s['playing_seconds'], 120)
            self.assertTrue(s['playing_time_complete'])

    def test_final_period_multiple_stints_close_only_last_entry(self):
        events = self.final_period_events(4)
        events += [event('02:00', 'Surt del camp', 'P4'),
                   event('01:00', 'Entra al camp', 'P4')]
        s = self.calculate(events, complete=False)
        self.assertEqual(s['playing_seconds'], 90)
        self.assertTrue(s['playing_time_complete'])

    def test_final_period_preserves_missing_history_and_bad_changes(self):
        s = self.calculate([event('02:30', 'Entra al camp', 'P8')], complete=False)
        self.assertEqual(s['playing_seconds'], 150)
        self.assertFalse(s['playing_time_complete'])
        self.assertTrue(any('faltan períodos' in issue for issue in s['playing_time_issues']))
        events = self.final_period_events(4) + [event('01:00', 'Entra al camp', 'P4')]
        s = self.calculate(events, complete=False)
        self.assertFalse(s['playing_time_complete'])
        self.assertTrue(any('entrada sin salida' in issue for issue in s['playing_time_issues']))

    def test_p4_with_later_period_does_not_imply_end_of_match(self):
        events = self.final_period_events(4) + [event('04:00', 'Surt del camp', 'P5')]
        s = self.calculate(events, complete=False)
        self.assertEqual(s['playing_seconds'], 270)
        self.assertFalse(s['playing_time_complete'])

    def test_open_overtime_still_requires_end(self):
        s = self.calculate(self.final_period_events(5), complete=False)
        self.assertEqual(s['playing_seconds'], 0)
        self.assertFalse(s['playing_time_complete'])
        self.assertTrue(any('intervalo abierto' in issue for issue in s['playing_time_issues']))

    def test_final_period_rule_reaches_focus_and_player_table(self):
        s = summarize([match(self.final_period_events(8), complete=False)])
        for row in (s['focus'], s['players'][0]):
            self.assertEqual(row['playing_seconds'], 150)
            self.assertTrue(row['playing_time_complete'])
        self.assertEqual(s['partial'], 1)

    def calculate(self, events, **kwargs):
        return playing_time([match(events, **kwargs)], 'MVP CERVELLÓ', 'MNL')

    def test_initial_entry_and_exit_include_p1(self):
        s = self.calculate([event('06:00', 'Entra al camp'), event('02:30', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 210)
        self.assertTrue(s['playing_time_complete'])

    def test_first_exit_is_not_assumed_starter(self):
        s = self.calculate([event('03:00', 'Surt del camp')])
        self.assertIsNone(s['playing_seconds'])
        self.assertFalse(s['playing_time_complete'])

    def test_first_entry_midperiod_implies_bench_start(self):
        s = self.calculate([event('04:00', 'Entra al camp'), event('02:00', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 120)
        self.assertTrue(s['playing_time_complete'])

    def test_actions_before_first_entry_keep_missing_interval_warning(self):
        s = self.calculate([event('05:00', 'Cistella de 2'),
                            event('04:00', 'Entra al camp'), event('02:00', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 120)
        self.assertFalse(s['playing_time_complete'])
        self.assertTrue(any('acciones anteriores' in issue for issue in s['playing_time_issues']))

    def test_eln_stints_across_four_periods_are_complete(self):
        events = [event('05:52', 'Entra al camp'),
                  event('10:00', 'Surt del camp', 'P2'),
                  event('07:00', 'Entra al camp', 'P2'),
                  event('02:00', 'Personal, 2a falta', 'P2'),
                  event('10:00', 'Surt del camp', 'P3'),
                  event('04:49', 'Entra al camp', 'P4'),
                  event('01:39', 'Cistella de 2', 'P4')]
        s = self.calculate(events, duration=600, complete=False)
        self.assertEqual(s['playing_seconds'], 5*60+52 + 7*60 + 4*60+49)
        self.assertTrue(s['playing_time_complete'])
        self.assertEqual(s['playing_time_issues'], [])

    def test_multiple_stints_and_match_aggregation(self):
        m = match([event('06:00', 'Entra al camp'), event('04:00', 'Surt del camp'),
                   event('03:00', 'Entra al camp'), event('01:30', 'Surt del camp')])
        s = playing_time([m, dict(m, id='two')], 'MVP CERVELLÓ', 'M.N.L.')
        self.assertEqual(s['playing_seconds'], 420)
        self.assertTrue(s['playing_time_complete'])

    def test_carries_state_without_counting_breaks(self):
        s = self.calculate([event('06:00', 'Entra al camp'),
                            event('04:00', 'Surt del camp', 'P2')])
        self.assertEqual(s['playing_seconds'], 480)
        self.assertTrue(s['playing_time_complete'])

    def test_open_interval_requires_period_end(self):
        events = [event('06:00', 'Entra al camp')]
        s = self.calculate(events, complete=False)
        self.assertIsNone(s['playing_seconds'])
        events.append(event('', 'Final de període', player='', team=''))
        s = self.calculate(events, complete=False)
        self.assertEqual(s['playing_seconds'], 360)
        self.assertFalse(s['playing_time_complete'])

    def test_missing_period_resets_state(self):
        s = self.calculate([event('06:00', 'Entra al camp'),
                            event('03:00', 'Surt del camp', 'P3')])
        self.assertEqual(s['playing_seconds'], 360)
        self.assertFalse(s['playing_time_complete'])

    def test_inconsistent_changes_preserve_other_intervals(self):
        s = self.calculate([event('06:00', 'Entra al camp'), event('05:00', 'Surt del camp'),
                            event('04:00', 'Entra al camp'), event('03:00', 'Entra al camp'),
                            event('02:00', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 120)
        self.assertFalse(s['playing_time_complete'])

    def test_bad_clocks_do_not_add_negative_time(self):
        for clock in ('', '07:00', '05:00'):
            s = self.calculate([event('04:00', 'Entra al camp'), event(clock, 'Surt del camp')])
            self.assertIsNone(s['playing_seconds'])
            self.assertFalse(s['playing_time_complete'])

    def test_other_team_same_name_is_excluded(self):
        s = self.calculate([event('06:00', 'Entra al camp', team='RIVAL'),
                            event('00:00', 'Surt del camp', team='RIVAL')])
        self.assertIsNone(s['playing_seconds'])

    def test_focus_and_table_have_same_time(self):
        s = summarize([match([event('06:00', 'Entra al camp'), event('00:00', 'Surt del camp')])])
        self.assertEqual(s['focus']['playing_seconds'], 360)
        self.assertEqual(s['players'][0]['playing_seconds'], 360)
        self.assertTrue(s['focus']['playing_time_complete'])

    def test_duration_and_player_change(self):
        s = self.calculate([event('10:00', 'Entra al camp', player='MNL'),
                            event('07:00', 'Surt del camp')], duration=600)
        self.assertEqual(s['playing_seconds'], 180)

    def test_zero_at_start_is_not_missing(self):
        s = self.calculate([event('06:00', 'Entra al camp'), event('06:00', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 0)
        self.assertTrue(s['playing_time_complete'])

    def test_partial_match_marks_aggregate_incomplete(self):
        events = [event('06:00', 'Entra al camp'), event('05:00', 'Surt del camp')]
        s = playing_time([match(events), match(events, complete=False)], 'MVP CERVELLÓ', 'MNL')
        self.assertEqual(s['playing_seconds'], 120)
        self.assertFalse(s['playing_time_complete'])

