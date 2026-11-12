import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import schedules

LA = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc


def utc(*a):
    return datetime(*a, tzinfo=UTC)


class NextRunTests(unittest.TestCase):
    def test_every_day_later_today_or_tomorrow(self):
        rule = {"every": "day", "at": "08:30"}
        self.assertEqual(
            [schedules.next_run(rule, utc(2026, 11, 10, 15, 0), LA), schedules.next_run(rule, utc(2026, 11, 10, 17, 0), LA)],
            [utc(2026, 11, 10, 16, 30), utc(2026, 11, 11, 16, 30)])

    def test_keeps_local_time_across_the_daylight_saving_change(self):
        rule = {"every": "day", "at": "08:30"}
        # 8:30 PDT on Oct 31 is 15:30 UTC; the clocks go back on Nov 1, so 8:30 PST is 16:30 UTC.
        self.assertEqual(schedules.next_run(rule, utc(2026, 10, 31, 16, 0), LA), utc(2026, 11, 1, 16, 30))

    def test_every_few_days_counts_from_the_last_run(self):
        rule = {"every": "days", "days": 3, "at": "09:00"}
        last = utc(2026, 11, 9, 17, 0)  # Nov 9, 9:00 PST
        self.assertEqual(
            [schedules.next_run(rule, utc(2026, 11, 9, 17, 5), LA, last), schedules.next_run(rule, utc(2026, 11, 20, 0, 0), LA, last),
             schedules.next_run(rule, utc(2026, 11, 9, 17, 5), LA)],
            [utc(2026, 11, 12, 17, 0), utc(2026, 11, 21, 17, 0), utc(2026, 11, 10, 17, 0)])

    def test_weekly_and_monthly(self):
        monday = {"every": "week", "weekday": 0, "at": "08:00"}
        first = {"every": "month", "monthday": 1, "at": "09:00"}
        self.assertEqual(
            [schedules.next_run(monday, utc(2026, 11, 9, 15, 0), LA), schedules.next_run(monday, utc(2026, 11, 9, 17, 0), LA),
             schedules.next_run(first, utc(2026, 11, 9, 17, 0), LA), schedules.next_run(first, utc(2026, 12, 31, 20, 0), LA)],
            [utc(2026, 11, 9, 16, 0), utc(2026, 11, 16, 16, 0), utc(2026, 12, 1, 17, 0), utc(2027, 1, 1, 17, 0)])


class DescribeTests(unittest.TestCase):
    def test_reads_like_a_sentence(self):
        self.assertEqual(
            [schedules.describe(r) for r in ({"every": "day", "at": "08:30"}, {"every": "days", "days": 3, "at": "09:00"},
                                             {"every": "week", "weekday": 0, "at": "08:00"}, {"every": "month", "monthday": 1, "at": "13:15"})],
            ["Every day at 8:30 AM", "Every 3 days at 9:00 AM", "Mondays at 8:00 AM", "The 1st of each month at 1:15 PM"])


class CleanRuleTests(unittest.TestCase):
    def test_accepts_good_rules_and_names_the_bad_field(self):
        self.assertEqual(
            [schedules.clean_rule({"every": "days", "days": "3", "at": "9:05"}), schedules.clean_rule({"every": "day", "at": "25:00"}),
             schedules.clean_rule({"every": "days", "days": 0, "at": "09:00"}), schedules.clean_rule({"every": "month", "monthday": 31, "at": "09:00"}),
             schedules.clean_rule({"every": "hourly", "at": "09:00"})],
            [({"every": "days", "days": 3, "at": "09:05"}, None), (None, "at"), (None, "days"), (None, "monthday"), (None, "every")])


class TimeZoneWordsTests(unittest.TestCase):
    """Schedules say whose clock they run on (9.4e)."""
    def test_the_zone_in_plain_words(self):
        self.assertEqual([schedules.tz_label(n) for n in ("America/Chicago", "America/Los_Angeles", "America/Argentina/Buenos_Aires", "UTC")],
                         ["Chicago time", "Los Angeles time", "Buenos Aires time", "UTC"])

    def test_a_run_reads_in_the_account_zone_with_its_abbreviation_across_the_clock_change(self):
        chicago = ZoneInfo("America/Chicago")
        self.assertEqual([schedules.local_when(utc(2026, 10, 31, 13, 30), chicago), schedules.local_when(utc(2026, 11, 2, 14, 30), chicago),
                          schedules.local_when(utc(2026, 11, 16, 5, 5), LA), schedules.local_when(None, LA)],
                         ["Sat Oct 31, 8:30 AM CDT", "Mon Nov 2, 8:30 AM CST", "Sun Nov 15, 9:05 PM PST", None])
