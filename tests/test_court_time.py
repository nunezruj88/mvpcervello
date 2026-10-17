import unittest
from stats import playing_time, summarize


def event(clock, action, period='P1', player='M.N.L.', team='MVP CERVELLÓ'):
    return dict(clock=clock, action=action, period=period, player=player,
                team=team, points=0, number=12)


def match(events, complete=True, duration=360):
    return dict(id='one', date='2026-10-17', home='MVP CERVELLÓ', away='RIVAL',
                complete=complete, period_seconds=duration, events=events)


class CourtTimeTests(unittest.TestCase):
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

    def test_entry_midperiod_retains_only_confirmed_interval(self):
        s = self.calculate([event('04:00', 'Entra al camp'), event('02:00', 'Surt del camp')])
        self.assertEqual(s['playing_seconds'], 120)
        self.assertFalse(s['playing_time_complete'])

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
