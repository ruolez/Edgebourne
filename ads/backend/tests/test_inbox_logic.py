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

    def test_a_fixed_problem_is_resolved_but_an_approval_is_not(self):
        fixed = dict(alert(1, "ad_rejected", 5), kind="condition", resolved_at=NOW)
        approved = dict(alert(2, "ad_approved", 4, "ok"), kind="event", resolved_at=NOW)
        got = inbox.build([fixed, approved], [], [], read_keys=set())
        self.assertEqual([(i["key"], i["resolved"]) for i in got], [("alert:2", False), ("alert:1", True)])

    def test_a_lead_no_longer_new_is_read(self):
        got = inbox.build([], [dict(self.leads[0], status="contacted")], [], read_keys=set())
        self.assertEqual([i["unread"] for i in got], [False])

    def test_filters(self):
        items = inbox.build(self.alerts, self.leads, self.proposals, read_keys={"alert:2"})
        self.assertEqual([i["key"] for i in inbox.pick(items, "unread", "all")], ["lead:9", "alert:1", "proposal:4"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "money")], ["alert:2"])
        self.assertEqual(inbox.counts(items), {"unread": 3, "status": 1, "leads": 1, "claude": 1, "money": 0, "system": 0,
                                               "need": 4, "need_unread": 3, "fyi": 0, "fyi_unread": 0})


class TriageTests(unittest.TestCase):
    """Needs action = open problems, open warn/bad events, waiting suggestions, leads nobody has tried. The rest is FYI."""

    def build(self, alerts=(), leads=(), proposals=(), read=()):
        return inbox.build(list(alerts), list(leads), list(proposals), set(read))

    def test_what_needs_a_person_and_what_is_for_information(self):
        items = self.build(
            alerts=[dict(alert(1, "ad_rejected", 5), kind="condition"),
                    dict(alert(2, "ad_rejected", 6), kind="condition", entity_id="a2b", resolved_at=NOW),
                    dict(alert(3, "ad_approved", 7, "ok"), kind="event", resolved_at=NOW),
                    dict(alert(4, "report_review", 8, "warn"), kind="event"),
                    dict(alert(5, "changed_outside", 9, "info"), kind="event"),
                    dict(alert(6, "learning_limited", 10, "warn"), kind="event", resolved_at=NOW)],
            leads=[{"id": 9, "full_name": "Dana", "ad_name": "N4", "created_time": NOW - timedelta(minutes=3), "status": "new", "first_contacted_at": None},
                   {"id": 8, "full_name": "Eli", "ad_name": "N4", "created_time": NOW - timedelta(minutes=4), "status": "new", "first_contacted_at": NOW},
                   {"id": 7, "full_name": "Fay", "ad_name": "N4", "created_time": NOW - timedelta(minutes=11), "status": "contacted", "first_contacted_at": NOW}],
            proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}])
        self.assertEqual({i["key"]: i["need"] for i in items},
                         {"alert:1": True, "alert:2": False, "alert:3": False, "alert:4": True, "alert:5": False, "alert:6": False,
                          "lead:9": True, "lead:8": False, "lead:7": False, "proposal:4": True})

    def test_the_same_problem_open_on_two_days_needs_action_once(self):
        items = self.build(alerts=[dict(alert(1, "spend_cap", 60 * 24, "warn", None), kind="condition", entity_id="account"),
                                   dict(alert(2, "spend_cap", 5, "warn", None), kind="condition", entity_id="account")])
        self.assertEqual([(i["key"], i["need"]) for i in items], [("alert:2", True), ("alert:1", False)])

    def test_boxes_and_counts(self):
        items = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition"),
                                   dict(alert(3, "ad_approved", 7, "ok"), kind="event", resolved_at=NOW)],
                           proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}],
                           read={"proposal:4"})
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "all", "need")], ["alert:1", "proposal:4"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "all", "fyi")], ["alert:3"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "unread", "claude", "need")], [])
        got = inbox.counts(items)
        self.assertEqual({k: got[k] for k in ("unread", "need", "need_unread", "fyi", "fyi_unread")},
                         {"unread": 2, "need": 2, "need_unread": 1, "fyi": 1, "fyi_unread": 1})

    def test_a_problem_fixed_since_leaves_the_needs_action_count(self):
        open_ = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition")])
        fixed = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition", resolved_at=NOW)])
        self.assertEqual([inbox.counts(open_)["need_unread"], inbox.counts(fixed)["need_unread"], inbox.counts(fixed)["unread"]], [1, 0, 1])

    def test_a_suggestion_names_itself_for_the_accept_sheet(self):
        items = self.build(proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW, "entity_name": "Leads"}])
        self.assertEqual(items[0]["proposal_id"], 4)


class SubjectTests(unittest.TestCase):
    def test_an_item_about_a_known_campaign_ad_set_or_ad_names_it_with_a_link_target(self):
        items = [{"key": "alert:1", "entity_id": "a1"}, {"key": "alert:2", "entity_id": "c1"},
                 {"key": "alert:3", "entity_id": "gone"}, {"key": "lead:9", "entity_id": None}]
        known = {"a1": {"level": "ad", "name": "N1 - pain"}, "c1": {"level": "campaign", "name": "Free intro call"}}
        got = inbox.with_subjects(items, known)
        self.assertEqual([i["subject"] for i in got], [{"level": "ad", "id": "a1", "name": "N1 - pain"},
                                                        {"level": "campaign", "id": "c1", "name": "Free intro call"}, None, None])


if __name__ == "__main__":
    unittest.main()
