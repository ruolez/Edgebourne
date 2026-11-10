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


class AutoMinutesTests(unittest.TestCase):
    def test_keeps_an_allowed_choice_and_falls_back_to_the_default(self):
        default = refresh_api.DEFAULT_AUTO_MINUTES
        self.assertEqual(
            [refresh_api.auto_minutes(m) for m in ("5", "30", 60, None, "", "7", "junk", "-15")],
            [5, 30, 60, default, default, default, default, default])


class AutoDueTests(unittest.TestCase):
    NOW = 1_000_000.0

    def test_due_once_the_interval_has_passed_since_the_last_pull(self):
        now, every = self.NOW, 15
        self.assertEqual(
            [refresh_api.auto_due(None, None, now, every),
             refresh_api.auto_due(str(now - 15 * 60), None, now, every),
             refresh_api.auto_due(str(now - 15 * 60 + 1), None, now, every)],
            [True, True, False])

    def test_a_failed_try_waits_before_the_next_one(self):
        now, every = self.NOW, 15
        gap = refresh_api.AUTO_RETRY_SECONDS
        self.assertEqual(
            [refresh_api.auto_due(None, now - gap + 1, now, every), refresh_api.auto_due(None, now - gap, now, every)],
            [False, True])

    def test_a_pull_stamped_in_the_future_does_not_stop_automatic_refresh(self):
        self.assertTrue(refresh_api.auto_due(str(self.NOW + 3600), None, self.NOW, 15))


class WorkerHealthTest(unittest.TestCase):
    NOW = 1_800_000_000.0

    def test_a_recent_pass_is_healthy(self):
        import jobs
        self.assertFalse(jobs.worker_stale("2027-01-15T07:59:00+00:00", jobs.synced_at("2027-01-15T08:00:00+00:00"), booted=0))

    def test_no_pass_for_ten_minutes_is_stale(self):
        import jobs
        now = jobs.synced_at("2027-01-15T08:20:00+00:00")
        self.assertEqual([jobs.worker_stale("2027-01-15T08:00:00+00:00", now, booted=0), jobs.worker_stale(None, now, booted=0)],
                         [True, True])

    def test_a_fresh_start_gets_grace(self):
        import jobs
        self.assertFalse(jobs.worker_stale(None, self.NOW, booted=self.NOW - 60))
