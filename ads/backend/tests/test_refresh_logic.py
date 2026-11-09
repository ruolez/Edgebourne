import unittest

import refresh_api

GAP = refresh_api.MIN_GAP_SECONDS


class RefreshDueTests(unittest.TestCase):
    def test_runs_when_never_refreshed_or_gap_passed(self):
        now = 1_000_000.0
        self.assertEqual(
            [refresh_api.refresh_due(None, now), refresh_api.refresh_due(now - GAP, now), refresh_api.refresh_due(now - GAP - 30, now)],
            [True, True, True])

    def test_skips_inside_the_gap_and_on_clock_skew(self):
        now = 1_000_000.0
        self.assertEqual(
            [refresh_api.refresh_due(now - 1, now), refresh_api.refresh_due(now - GAP + 1, now), refresh_api.refresh_due(now + 300, now)],
            [False, False, False])

    def test_bad_stored_value_counts_as_never(self):
        self.assertTrue(refresh_api.refresh_due("not a number", 1_000_000.0))


class LastUpdatedTests(unittest.TestCase):
    def test_newest_of_manual_refresh_and_hourly_sync(self):
        sync = "2026-11-09T18:00:00Z"  # 1794247200
        self.assertEqual(
            [refresh_api.last_updated(None, None), refresh_api.last_updated("1794250000", sync),
             refresh_api.last_updated("1794240000", sync), refresh_api.last_updated("junk", sync)],
            [None, 1794250000.0, 1794247200.0, 1794247200.0])
