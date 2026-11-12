import random
import unittest
from datetime import datetime, timedelta, timezone

import reminders
import today

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)


def lead(mins, status="new", contacted=False, test=False, i=1):
    return {"id": i, "status": status, "is_test": test, "created_time": NOW - timedelta(minutes=mins),
            "first_contacted_at": NOW - timedelta(minutes=1) if contacted else None}


def row(key, group, mins, level="warn", bucket=0):
    return {"key": key, "group": group, "level": level, "bucket": bucket, "at": NOW - timedelta(minutes=mins)}


class UrgencyTests(unittest.TestCase):
    def test_a_new_lead_nobody_tried_is_fresh_then_warm_then_late(self):
        ages = [0, 4.99, 5, 59.99, 60, 60 * 24 * 3]
        self.assertEqual([today.urgency(lead(m), NOW) for m in ages], ["fresh", "fresh", "warm", "warm", "late", "late"])

    def test_a_lead_someone_reached_or_a_test_lead_is_not_waiting(self):
        cases = [lead(90, status="contacted"), lead(90, contacted=True), lead(90, test=True), lead(90, status="lost")]
        self.assertEqual([today.urgency(c, NOW) for c in cases], ["done"] * 4)

    def test_the_steps_are_the_reminders_steps(self):
        # Today, Leads and the reminders agree: green until the 5-minute nudge, late from the hour one.
        self.assertEqual([s for _, s in reminders.STEPS], [timedelta(minutes=today.FRESH_MINUTES), timedelta(minutes=today.LATE_MINUTES)])

    def test_reminders_nudge_exactly_the_leads_today_calls_waiting(self):
        cases = [lead(90), lead(90, status="contacted"), lead(90, contacted=True), lead(90, test=True), lead(90, status="lost")]
        self.assertEqual([bool(reminders.due(c, NOW)) for c in cases], [today.waiting(c) for c in cases])
        self.assertEqual([bool(reminders.due(c, NOW)) for c in cases], [True, False, False, False, False])

    def test_first_hour_leads_come_before_older_ones(self):
        self.assertEqual([today.lead_bucket(lead(m), NOW) for m in (1, 59, 60, 3000)], [0, 0, 2, 2])


class GroupTests(unittest.TestCase):
    def test_each_kind_lands_in_its_group(self):
        cases = [("status", "ad_rejected", "bad"), ("system", "tracking", "bad"), ("system", "events_quiet", "warn"),
                 ("money", "spend_cap", "warn"), ("claude", "proposal", "claude"), ("system", "report_review", "warn"),
                 ("leads", "new_lead", "lead"), ("claude", "mac_offline", "warn"), ("claude", "desk_done", "info")]
        self.assertEqual([today.group_of(c, r, l) for c, r, l in cases],
                         ["problems", "problems", "system", "money", "decide", "decide", "call", "system", "system"])


class LeadGroupTests(unittest.TestCase):
    def test_follow_up_rows_land_in_their_groups(self):
        rules = ["new_lead", "meeting_soon", "followup_overdue", "meeting_check", "followup_today"]
        self.assertEqual([today.group_of("leads", r, "warn") for r in rules], ["call", "call", "follow", "follow", "later"])


class RankTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            row("alert:9", "system", 5, "warn"),
            row("proposal:4", "decide", 30, "claude"),
            row("alert:2", "problems", 120, "warn"),
            row("lead:old", "call", 3000, "late", bucket=2),
            row("alert:1", "problems", 600, "bad"),
            row("alert:3", "money", 10, "warn"),
            row("lead:new", "call", 3, "fresh", bucket=0),
            row("alert:5", "problems", 10, "bad"),
            row("lead:older", "call", 5000, "late", bucket=2),
        ]

    def test_groups_in_order_and_each_group_in_its_own_order(self):
        # Calls: the first hour first, then the longest wait. Problems: worst first, then newest.
        self.assertEqual([i["key"] for i in today.rank(self.items)],
                         ["lead:new", "lead:older", "lead:old", "alert:5", "alert:1", "alert:2", "proposal:4", "alert:3", "alert:9"])

    def test_one_thing_shows_once(self):
        twice = self.items + [row("lead:new", "call", 3, "fresh", bucket=2), row("alert:5", "system", 1, "warn")]
        got = today.rank(twice)
        self.assertEqual([i["key"] for i in got], [i["key"] for i in today.rank(self.items)])
        self.assertEqual([i["group"] for i in got if i["key"] in ("lead:new", "alert:5")], ["call", "problems"])

    def test_an_unknown_group_goes_last(self):
        got = today.rank([row("x", "mystery", 1), row("alert:9", "system", 5)])
        self.assertEqual([i["key"] for i in got], ["alert:9", "x"])

    def test_order_does_not_depend_on_the_order_items_came_in(self):
        rng = random.Random(7)
        expected = [i["key"] for i in today.rank(self.items)]
        for _ in range(50):
            shuffled = self.items[:]
            rng.shuffle(shuffled)
            self.assertEqual([i["key"] for i in today.rank(shuffled)], expected)

    def test_ranking_twice_changes_nothing(self):
        once = today.rank(self.items)
        self.assertEqual(today.rank(once), once)

    def test_an_item_without_a_time_sorts_after_those_with_one(self):
        got = today.rank([{"key": "a", "group": "problems", "level": "warn", "at": None}, row("b", "problems", 9999)])
        self.assertEqual([i["key"] for i in got], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
