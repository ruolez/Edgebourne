import unittest
from datetime import datetime, timedelta, timezone

import inbox

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def alert(i, rule, mins, level="bad", campaign="c1"):
    return {"id": i, "rule": rule, "level": level, "title": f"t{i}", "lines": ["l"], "href": f"/ad.html?id=a{i}",
            "entity_id": f"a{i}", "campaign_id": campaign, "created_at": NOW - timedelta(minutes=mins), "resolved_at": None}


class CategoryTests(unittest.TestCase):
    def test_rules_land_in_plain_groups(self):
        self.assertEqual([inbox.category(r) for r in ("ad_rejected", "ad_approved", "learning_limited", "no_delivery",
                                                       "fatigue", "changed_outside", "spend_cap", "cpl_high", "tracking")],
                         ["status", "status", "status", "status", "status", "status", "money", "money", "system"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.alerts = [alert(1, "ad_rejected", 5), alert(2, "spend_cap", 600, "warn", None)]
        self.leads = [{"id": 9, "full_name": "Dana", "ad_name": "N4", "created_time": NOW - timedelta(minutes=3), "status": "new"}]
        self.proposals = [{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}]

    def test_newest_first_with_keys_and_unread(self):
        got = inbox.build(self.alerts, self.leads, self.proposals, read_keys={"alert:2"})
        self.assertEqual([(i["key"], i["category"], i["unread"]) for i in got],
                         [("lead:9", "leads", True), ("alert:1", "status", True), ("proposal:4", "claude", True),
                          ("alert:2", "money", False)])

    def test_a_lead_no_longer_new_is_read(self):
        got = inbox.build([], [dict(self.leads[0], status="contacted")], [], read_keys=set())
        self.assertEqual([i["unread"] for i in got], [False])

    def test_filters(self):
        items = inbox.build(self.alerts, self.leads, self.proposals, read_keys={"alert:2"})
        self.assertEqual([i["key"] for i in inbox.pick(items, "unread", "all")], ["lead:9", "alert:1", "proposal:4"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "money")], ["alert:2"])
        self.assertEqual(inbox.counts(items), {"unread": 3, "status": 1, "leads": 1, "claude": 1, "money": 0, "system": 0})


if __name__ == "__main__":
    unittest.main()
