import unittest
from datetime import date, timedelta

import alerts
import pacing

TODAY = date(2026, 11, 10)  # 9 complete days in November, 21 left including today


def month(n, cents):
    return [(date(2026, 11, 1) + timedelta(days=i), cents) for i in range(n)]


class PaceTests(unittest.TestCase):
    def test_projects_the_month_from_the_last_week_and_finds_the_daily_spend_for_the_target(self):
        p = pacing.pace(TODAY, month(9, 2000), [2000] * 7, 2000, 60000, 10000, today_so_far_cents=700)
        self.assertEqual(p, {
            "month": "November", "days_done": 9, "days_left": 21, "mtd_cents": 18700, "rate_cents": 2000,
            "projected_cents": 18000 + 2000 * 21, "target_cents": 60000, "needed_daily_cents": round((60000 - 18000) / 21),
            "vs_target_pct": 0, "cap_days": 5, "cap_date": "2026-11-15"})

    def test_without_history_it_paces_on_the_daily_budget_and_without_target_or_limit_leaves_them_out(self):
        p = pacing.pace(date(2026, 11, 1), [], [], 2000, None, None)
        self.assertEqual((p["rate_cents"], p["projected_cents"], p["needed_daily_cents"], p["cap_days"], p["days_left"]),
                         (2000, 2000 * 30, None, None, 30))

    def test_the_week_counts_days_without_delivery_as_zero(self):
        # Off for 5 of the last 7 days, $30 on the other two: $8.57 a day, not $30 (audit A3-62).
        spent = {TODAY - timedelta(days=1): 3000, TODAY - timedelta(days=4): 3000}
        days7 = pacing.last_days(spent, TODAY, first_day=date(2026, 9, 1))
        self.assertEqual((days7, pacing.pace(TODAY, [], days7, 2000, None, None)["rate_cents"]),
                         ([0, 0, 0, 3000, 0, 0, 3000], 857))

    def test_an_account_younger_than_a_week_averages_the_days_since_its_first_spend(self):
        spent = {TODAY - timedelta(days=2): 2000, TODAY - timedelta(days=1): 1000}
        self.assertEqual([pacing.last_days(spent, TODAY, first_day=TODAY - timedelta(days=2)), pacing.last_days({}, TODAY, None)],
                         [[2000, 1000], []])

    def test_a_target_already_spent_needs_nothing_more(self):
        p = pacing.pace(TODAY, month(9, 8000), [8000] * 7, 2000, 60000, None)
        self.assertEqual((p["needed_daily_cents"], p["vs_target_pct"]), (0, 300))


class PacingAlertTests(unittest.TestCase):
    def base(self, **pace):
        return {"ads": [], "ad_days": {}, "campaigns": [], "camp_days": {}, "today_spend": {}, "cap": None, "inbox_leads": {},
                "meta_leads": {}, "last_pull_age_h": 0.1, "connected": True, "pacing": {"cap_days": None, "vs_target_pct": None, **pace}}

    def test_limit_running_out_soon_and_month_over_target(self):
        rules = alerts.rules_with({})
        found = [sorted(a["rule"] for a in alerts.evaluate(self.base(**p), rules, TODAY))
                 for p in ({"cap_days": 2, "cap_date": "2026-11-12"}, {"cap_days": 9, "cap_date": "2026-11-19"},
                           {"vs_target_pct": 20, "projected_cents": 72000, "target_cents": 60000}, {"vs_target_pct": 5})]
        self.assertEqual(found, [["cap_soon"], [], ["pace_over"], []])
