import unittest
from datetime import date

import ranges

TODAY = date(2026, 11, 10)


class WindowTests(unittest.TestCase):
    def test_last_n_days_end_yesterday(self):
        self.assertEqual(ranges.window("7", TODAY), (date(2026, 11, 3), date(2026, 11, 9)))
        self.assertEqual(ranges.window("14", TODAY), (date(2026, 10, 27), date(2026, 11, 9)))

    def test_month_to_date_and_last_month(self):
        self.assertEqual(ranges.window("mtd", TODAY), (date(2026, 11, 1), date(2026, 11, 9)))
        self.assertEqual(ranges.window("lastmonth", TODAY), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_month_to_date_on_the_first_is_last_month(self):
        self.assertEqual(ranges.window("mtd", date(2026, 12, 1)), (date(2026, 11, 1), date(2026, 11, 30)))

    def test_custom_is_clamped_to_complete_days_and_ordered(self):
        self.assertEqual(ranges.window("custom", TODAY, "2026-11-20", "2026-11-01"), (date(2026, 11, 1), date(2026, 11, 9)))

    def test_unknown_or_bad_falls_back_to_seven_days(self):
        self.assertEqual(ranges.window("nonsense", TODAY), ranges.window("7", TODAY))
        self.assertEqual(ranges.window("custom", TODAY, "x", None), ranges.window("7", TODAY))

    def test_custom_is_at_most_a_year(self):
        start, end = ranges.window("custom", TODAY, "2020-01-01", "2026-11-09")
        self.assertEqual(((end - start).days + 1, end), (366, date(2026, 11, 9)))


class PreviousTests(unittest.TestCase):
    def test_previous_is_the_same_length_just_before(self):
        self.assertEqual(ranges.previous(date(2026, 10, 27), date(2026, 11, 9), "14"), (date(2026, 10, 13), date(2026, 10, 26)))

    def test_previous_of_a_calendar_month_is_the_month_before(self):
        self.assertEqual(ranges.previous(date(2026, 10, 1), date(2026, 10, 31), "lastmonth"), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_previous_of_month_to_date_is_the_same_days_last_month(self):
        self.assertEqual(ranges.previous(date(2026, 11, 1), date(2026, 11, 9), "mtd"), (date(2026, 10, 1), date(2026, 10, 9)))

    def test_month_to_date_on_the_first_compares_the_whole_month_before(self):
        self.assertEqual(ranges.previous(*ranges.window("mtd", date(2026, 12, 1)), "mtd"), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_day_windows_that_start_on_the_first_compare_with_the_days_just_before(self):
        # Nov 8: the last 7 days are Nov 1-7; Nov 15: the last 14 are Nov 1-14 (audit A3-14).
        cases = [("7", date(2026, 11, 8)), ("14", date(2026, 11, 15)), ("30", date(2026, 12, 1))]
        self.assertEqual([ranges.previous(*ranges.window(k, t), k) for k, t in cases],
                         [(date(2026, 10, 25), date(2026, 10, 31)), (date(2026, 10, 18), date(2026, 10, 31)),
                          (date(2026, 10, 2), date(2026, 10, 31))])

    def test_a_custom_window_on_the_first_compares_with_the_days_just_before(self):
        start, end = ranges.window("custom", TODAY, "2026-11-01", "2026-11-09")
        self.assertEqual(ranges.previous(start, end, "custom"), (date(2026, 10, 23), date(2026, 10, 31)))


if __name__ == "__main__":
    unittest.main()


class DailySeriesTests(unittest.TestCase):
    KEYS = ("spend_cents", "leads")

    def test_every_day_of_the_window_in_order_with_missing_days_as_zero(self):
        rows = {"2026-11-02": {"spend_cents": 150, "leads": 1}, "2026-11-04": {"spend_cents": 90, "leads": None}}
        self.assertEqual(ranges.daily_series(rows, date(2026, 11, 1), date(2026, 11, 4), self.KEYS), [
            {"day": "2026-11-01", "spend_cents": 0, "leads": 0},
            {"day": "2026-11-02", "spend_cents": 150, "leads": 1},
            {"day": "2026-11-03", "spend_cents": 0, "leads": 0},
            {"day": "2026-11-04", "spend_cents": 90, "leads": 0},
        ])

    def test_days_outside_the_window_are_left_out(self):
        rows = {"2026-10-31": {"spend_cents": 5, "leads": 5}, "2026-11-05": {"spend_cents": 7, "leads": 7}}
        self.assertEqual(ranges.daily_series(rows, date(2026, 11, 1), date(2026, 11, 1), self.KEYS),
                         [{"day": "2026-11-01", "spend_cents": 0, "leads": 0}])

    def test_a_month_window_has_one_entry_per_day(self):
        start, end = ranges.window("lastmonth", TODAY)
        series = ranges.daily_series({}, start, end, self.KEYS)
        self.assertEqual((len(series), series[0]["day"], series[-1]["day"]), (31, "2026-10-01", "2026-10-31"))


# ---------------------------------------------------------------- FU-C: numbers through now, judgments on complete days

NOV12 = date(2026, 11, 12)


def d(day, month=11):
    return date(2026, month, day)


class LiveWindowTests(unittest.TestCase):
    def test_the_default_is_still_complete_days(self):
        self.assertEqual(ranges.window("7", NOV12), (d(5), d(11)))

    def test_live_last_n_days_end_today(self):
        self.assertEqual([ranges.window(k, NOV12, live=True) for k in ("7", "14", "30")],
                         [(d(6), d(12)), (d(30, 10), d(12)), (d(14, 10), d(12))])

    def test_today_is_today_live_and_yesterday_alone_for_a_judgment(self):
        self.assertEqual((ranges.window("today", NOV12, live=True), ranges.window("today", NOV12)),
                         ((d(12), d(12)), (d(11), d(11))))

    def test_this_month_on_the_first(self):
        self.assertEqual((ranges.window("mtd", d(1), live=True), ranges.window("mtd", d(1))),
                         ((d(1), d(1)), (d(1, 10), d(31, 10))))

    def test_this_month_live_runs_to_today(self):
        self.assertEqual(ranges.window("mtd", NOV12, live=True), (d(1), d(12)))

    def test_last_month_is_the_same_live_or_not(self):
        self.assertEqual(ranges.window("lastmonth", NOV12, live=True), (d(1, 10), d(31, 10)))

    def test_custom_may_end_today_only_when_live(self):
        self.assertEqual((ranges.window("custom", NOV12, "2026-11-10", "2026-11-12", live=True),
                          ranges.window("custom", NOV12, "2026-11-10", "2026-11-12")),
                         ((d(10), d(12)), (d(10), d(11))))

    def test_custom_never_reaches_past_today(self):
        self.assertEqual(ranges.window("custom", NOV12, "2026-11-10", "2026-11-20", live=True), (d(10), d(12)))

    def test_today_is_a_key(self):
        self.assertEqual(("today" in ranges.KEYS, "today" in ranges.LIVE_KEYS, "lastmonth" in ranges.LIVE_KEYS), (True, True, False))


class SettledTests(unittest.TestCase):
    def test_the_complete_day_part_of_a_window(self):
        self.assertEqual((ranges.settled(d(6), d(12), NOV12), ranges.settled(d(12), d(12), NOV12),
                          ranges.settled(d(1, 10), d(31, 10), NOV12)),
                         ((d(6), d(11)), None, (d(1, 10), d(31, 10))))

    def test_includes_today(self):
        self.assertEqual((ranges.includes_today(d(6), d(12), NOV12), ranges.includes_today(d(5), d(11), NOV12)), (True, False))


class ComparePlanTests(unittest.TestCase):
    def test_today_compares_with_yesterday_by_the_hour(self):
        self.assertEqual(ranges.compare_plan("today", d(12), d(12), NOV12),
                         {"mode": "hours", "now": (d(12), d(12)), "before": (d(11), d(11)), "note": None})

    def test_a_custom_window_of_just_today_is_compared_by_the_hour_too(self):
        self.assertEqual(ranges.compare_plan("custom", d(12), d(12), NOV12)["mode"], "hours")

    def test_a_window_with_today_compares_its_complete_days_with_as_many_before(self):
        self.assertEqual(ranges.compare_plan("7", d(6), d(12), NOV12),
                         {"mode": "days", "now": (d(6), d(11)), "before": (d(31, 10), d(5)), "note": "complete days"})

    def test_this_month_with_today_compares_the_same_complete_days_of_last_month(self):
        self.assertEqual(ranges.compare_plan("mtd", d(1), d(12), NOV12),
                         {"mode": "days", "now": (d(1), d(11)), "before": (d(1, 10), d(11, 10)), "note": "complete days"})

    def test_a_past_window_is_compared_as_before(self):
        self.assertEqual(ranges.compare_plan("lastmonth", d(1, 10), d(31, 10), NOV12),
                         {"mode": "days", "now": (d(1, 10), d(31, 10)), "before": (d(1, 9), d(30, 9)), "note": None})


def hour_row(h, spend, leads=0, campaign="c1"):
    acts = [{"action_type": "onsite_conversion.lead_grouped", "value": str(leads)}] if leads else []
    return {"hourly_stats_aggregated_by_advertiser_time_zone": f"{h:02d}:00:00 - {h:02d}:59:59", "spend": str(spend),
            "impressions": "100", "inline_link_clicks": "2", "actions": acts, "campaign_id": campaign}


class SameHoursTests(unittest.TestCase):
    def test_sums_the_hours_up_to_and_including_the_hour(self):
        rows = [hour_row(0, 1.00), hour_row(9, 2.50, 1), hour_row(13, 0.25, 2), hour_row(14, 9.00, 5), hour_row(23, 4.00)]
        self.assertEqual(ranges.same_hours(rows, 13), {"spend_cents": 375, "leads": 3, "impressions": 300, "link_clicks": 6})

    def test_no_rows_is_zero(self):
        self.assertEqual(ranges.same_hours([], 23), {"spend_cents": 0, "leads": 0, "impressions": 0, "link_clicks": 0})

    def test_a_row_without_a_readable_hour_is_left_out(self):
        bad = {**hour_row(1, 5.00), "hourly_stats_aggregated_by_advertiser_time_zone": "soon"}
        self.assertEqual(ranges.same_hours([bad], 23)["spend_cents"], 0)


class LiveLabelTests(unittest.TestCase):
    def test_a_window_ending_today_says_today(self):
        self.assertEqual((ranges.label(d(6), d(12), today=NOV12), ranges.label(d(12), d(12), today=NOV12),
                          ranges.label(d(5), d(11), today=NOV12), ranges.label(d(5), d(11))),
                         ("Nov 6 – today", "Today", "Nov 5 – Nov 11", "Nov 5 – Nov 11"))

    def test_the_hour_a_same_hours_comparison_runs_to(self):
        self.assertEqual([ranges.by_hour_words(h) for h in (0, 11, 12, 14, 23)], ["1 AM", "noon", "1 PM", "3 PM", "midnight"])


class PartialSeriesTests(unittest.TestCase):
    def test_todays_point_is_flagged_partial(self):
        rows = {"2026-11-12": {"spend_cents": 40, "leads": 0}}
        self.assertEqual(ranges.daily_series(rows, d(11), d(12), ("spend_cents",), today=NOV12),
                         [{"day": "2026-11-11", "spend_cents": 0}, {"day": "2026-11-12", "spend_cents": 40, "partial": True}])

    def test_without_today_no_point_is_flagged(self):
        self.assertNotIn(True, [p.get("partial") for p in ranges.daily_series({}, d(10), d(11), ("leads",), today=NOV12)])


class WithLiveTests(unittest.TestCase):
    FIELDS = ("spend_cents", "leads")

    def test_judgments_and_order_from_complete_days_figures_from_now(self):
        judged = [{"key": "b", "spend_cents": 100, "leads": 2, "enough": True}, {"key": "a", "spend_cents": 50, "leads": 0, "enough": False}]
        live = [{"key": "a", "spend_cents": 900, "leads": 9, "enough": True}, {"key": "b", "spend_cents": 130, "leads": 2, "enough": True}]
        self.assertEqual(ranges.with_live(judged, live, "key", self.FIELDS, {"enough": False}),
                         [{"key": "b", "spend_cents": 130, "leads": 2, "enough": True},
                          {"key": "a", "spend_cents": 900, "leads": 9, "enough": False}])

    def test_a_row_only_today_has_comes_last_with_nothing_judged(self):
        live = [{"key": "new", "spend_cents": 75, "leads": 4, "enough": True, "best": True}]
        self.assertEqual(ranges.with_live([], live, "key", self.FIELDS, {"enough": False, "best": False}),
                         [{"key": "new", "spend_cents": 75, "leads": 4, "enough": False, "best": False}])

    def test_a_judged_row_with_nothing_now_keeps_its_figures(self):
        judged = [{"key": "x", "spend_cents": 10, "leads": 1, "enough": False}]
        self.assertEqual(ranges.with_live(judged, [], "key", self.FIELDS, {}), judged)


class LiveRatchetTests(unittest.TestCase):
    """Today's numbers are partial: only screens may show them. A judgment (alerts, Did it work?, tests, Claude's
    snapshot, money rules, the numbers check, reports, snoozes) wired to a live window or a live read fails here."""
    import os as _os
    HERE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    DISPLAY = {"performance_api.py", "ads_api.py", "entities_api.py", "gallery_api.py", "concepts_api.py", "home_api.py", "accounts_api.py"}
    JUDGMENTS = ("alerts.py", "change_checks.py", "change_checks_db.py", "experiments.py", "experiments_api.py", "meta_tests.py",
                 "numbers_check.py", "report_logic.py", "reports_api.py", "desk_api.py", "money_rules.py", "snooze.py")

    def source(self, name):
        with open(self._os.path.join(self.HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_only_display_endpoints_ask_for_a_live_window(self):
        using = {n for n in self._os.listdir(self.HERE) if n.endswith(".py") and "live=True" in self.source(n)}
        self.assertEqual(using, self.DISPLAY)

    PARTIAL = ("read_today(", "pull_today(", "live_window(", "compare_plan(", "stamp_today_from_stored(", "with_live(")

    def partial_reads(self, text):
        """What in this source pulls in today's partial numbers: a live read, a live window, or a call's keyword
        live=<anything but None> (a variable of its own called live is fine)."""
        import re
        return [p for p in self.PARTIAL if p in text] + re.findall(r"[(,]\s*live\s*=\s*(?!None\b)\w+", text)

    def test_the_scanner_catches_every_way_in(self):
        samples = ["insights.read_today()", "insights.pull_today(timeout=3)", "ads_api.live_window(args)",
                   "ranges.compare_plan(k, a, b, t)", "insights.stamp_today_from_stored()", "ranges.with_live(a, b, 'id', f, u)",
                   "overview_data(user, a, b, live=flag)", "ranges.window(k, t, live=True)", "window(k, t,\n    live = x)"]
        self.assertEqual([bool(self.partial_reads(s)) for s in samples], [True] * len(samples))

    def test_the_scanner_lets_a_default_of_none_and_other_names_pass(self):
        self.assertEqual(self.partial_reads("def source(a, live=None):\n    live = live or {}\n    f(alive=1, delivered=2)"), [])

    def test_judgments_never_read_today(self):
        found = {n: self.partial_reads(self.source(n)) for n in self.JUDGMENTS}
        self.assertEqual({n: f for n, f in found.items() if f}, {})
