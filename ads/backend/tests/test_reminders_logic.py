import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import reminders

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
LA = ZoneInfo("America/Los_Angeles")


def lead(minutes_ago, **kw):
    return {"id": kw.pop("id", 1), "created_time": NOW - timedelta(minutes=minutes_ago), "status": "new", "is_test": False,
            "first_contacted_at": None, "notes": 0, **kw}


class DueTests(unittest.TestCase):
    def test_five_minutes_then_an_hour_for_a_lead_nobody_touched(self):
        self.assertEqual(
            [reminders.due(lead(m), NOW) for m in (4, 5, 59, 60, 23 * 60)],
            [[], ["5m"], ["5m"], ["5m", "1h"], ["5m", "1h"]])

    def test_nothing_once_someone_acted_or_for_tests_and_old_leads(self):
        self.assertEqual(
            [reminders.due(lead(90, status="contacted"), NOW), reminders.due(lead(90, first_contacted_at=NOW), NOW),
             reminders.due(lead(90, is_test=True), NOW), reminders.due(lead(25 * 60), NOW)],
            [[], [], [], []])


    def test_a_note_alone_no_longer_stops_reminders(self):
        self.assertEqual(reminders.due(lead(90, notes=1), NOW), ["5m", "1h"])

    def test_a_booked_call_stops_them(self):
        self.assertEqual([reminders.due(lead(90, meeting_status="scheduled"), NOW), reminders.due(lead(90, meeting_status="canceled"), NOW)],
                         [[], ["5m", "1h"]])


class DigestTests(unittest.TestCase):
    def test_once_a_day_from_eight_in_the_morning_local_time(self):
        at = lambda h, m=0: datetime(2026, 11, 10, h, m, tzinfo=LA)  # noqa: E731
        self.assertEqual(
            [reminders.digest_due(at(7, 59), None), reminders.digest_due(at(8), None),
             reminders.digest_due(at(8), "2026-11-10"), reminders.digest_due(at(9), "2026-11-09")],
            [False, True, False, True])


class ResponseStatsTests(unittest.TestCase):
    def test_median_first_contact_and_share_within_five_minutes(self):
        rows = [{"wait_minutes": m} for m in (2, 4, 30, 120)] + [{"wait_minutes": None}]
        self.assertEqual(reminders.response_stats(rows), {"leads": 5, "contacted": 4, "median_minutes": 17, "within_5": 2, "untouched": 1})

    def test_no_leads_means_no_numbers(self):
        self.assertEqual(reminders.response_stats([]), {"leads": 0, "contacted": 0, "median_minutes": None, "within_5": 0, "untouched": 0})


class TextTests(unittest.TestCase):
    def test_says_who_is_waiting_and_how_long(self):
        l = {**lead(62), "full_name": "Maria Lopez", "business_type": "Wholesale bakery", "phone": "+15551234567"}
        self.assertEqual(reminders.reminder_text(l, "1h", NOW), ("Maria Lopez has waited 1 h for a call",
                                                               ["Wholesale bakery", "Phone: (555) 123-4567"]))
        self.assertEqual(reminders.reminder_text({**l, "full_name": None}, "5m", NOW)[0], "Nobody has called Someone yet (5 min)")

