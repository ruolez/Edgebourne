import unittest
from datetime import date

import performance_api


class PeriodTests(unittest.TestCase):
    def test_the_last_7_complete_days_and_the_7_before_them(self):
        self.assertEqual(performance_api.periods(date(2026, 11, 9), 7),
                         ((date(2026, 11, 2), date(2026, 11, 8)), (date(2026, 10, 26), date(2026, 11, 1))))

    def test_a_30_day_period_crosses_the_month_and_the_one_before_does_not_overlap(self):
        (start, end), (prev_start, prev_end) = performance_api.periods(date(2026, 3, 1), 30)
        self.assertEqual((start, end, prev_start, prev_end),
                         (date(2026, 1, 30), date(2026, 2, 28), date(2025, 12, 31), date(2026, 1, 29)))


class LiveReadTests(unittest.TestCase):
    """FU-C: overview_data reads today from Meta only for a screen (live) whose window has today; Claude's snapshot
    (live off) never does, so a partial day can't reach a judgment."""
    TODAY = date(2026, 11, 12)

    def run_overview(self, span, live):
        from unittest import mock
        calls = []

        def query(sql, params=None, one=False):
            return {"spend_cents": 0, "leads": 0, "qualified": 0, "booked": 0} if one else []
        with mock.patch.object(performance_api.insights, "read_today", side_effect=lambda **k: calls.append(k) or {"as_of": 1.0, "read": True, "error": None}), \
                mock.patch.object(performance_api.account_info, "today", return_value=self.TODAY), \
                mock.patch.object(performance_api.account_info, "yesterday", return_value=date(2026, 11, 11)), \
                mock.patch.object(performance_api.account_info, "tz_name", return_value="America/Los_Angeles"), \
                mock.patch.object(performance_api, "visible_campaign_ids", return_value=None), \
                mock.patch.object(performance_api, "window_totals", return_value={"spend_cents": 0, "impressions": 0, "link_clicks": 0, "leads": 0}), \
                mock.patch.object(performance_api.db, "query", side_effect=query), \
                mock.patch.object(performance_api.followup, "tracks_bookings", return_value=False), \
                mock.patch.object(performance_api.settings_store, "get", return_value=None), \
                mock.patch("numbers_check.source", return_value={"meta": {}}):
            days = (span[0][1] - span[0][0]).days + 1 if span else 7
            out = performance_api.overview_data({"id": None, "role": "teammate"}, days, span=span, live=live)
        return len(calls), out["series"][-1]

    def test_the_snapshot_never_reads_today(self):
        week = ((date(2026, 11, 6), date(2026, 11, 12)), (date(2026, 10, 30), date(2026, 11, 5)))
        self.assertEqual(self.run_overview(None, False)[0], 0)
        self.assertEqual(self.run_overview(week, False)[0], 0)

    def test_a_screen_with_today_reads_it_and_flags_todays_point(self):
        week = ((date(2026, 11, 6), date(2026, 11, 12)), (date(2026, 10, 30), date(2026, 11, 5)))
        self.assertEqual(self.run_overview(week, True), (1, {"day": "2026-11-12", "spend_cents": 0, "leads": 0, "partial": True}))

    def test_a_past_window_on_a_screen_reads_nothing(self):
        past = ((date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(self.run_overview(past, True), (0, {"day": "2026-10-31", "spend_cents": 0, "leads": 0}))


if __name__ == "__main__":
    unittest.main()
