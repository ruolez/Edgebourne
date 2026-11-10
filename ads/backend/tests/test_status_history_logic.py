import unittest
from datetime import datetime, timedelta, timezone

import status_history as sh

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
REJECTED = {"global": {"PERSONAL_ATTRIBUTES": "Ads can't imply knowledge of personal attributes."}}


def ad(**kw):
    base = {"id": "a1", "status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE",
            "ad_review_feedback": None, "issues_info": None}
    base.update(kw)
    return base


class SnapshotTests(unittest.TestCase):
    def test_meta_row_and_stored_row_reduce_to_the_same_snapshot(self):
        meta = sh.snapshot("ad", ad(effective_status="DISAPPROVED", ad_review_feedback=REJECTED))
        stored = sh.stored_snapshot("ad", {"status": "ACTIVE", "configured_status": None, "effective_status": "DISAPPROVED",
                                           "review_feedback": REJECTED, "issues": None})
        self.assertEqual(meta, stored)

    def test_review_reasons_are_order_independent(self):
        a = sh.review_summary({"global": {"B": "x", "A": "y"}, "placement_specific": {"instagram": {"C": "z"}}})
        b = sh.review_summary({"placement_specific": {"instagram": {"C": "z"}}, "global": {"A": "y", "B": "x"}})
        self.assertEqual(a, b)
        self.assertEqual(a, "A; B; instagram: C")

    def test_learning_reads_the_stage_status(self):
        self.assertEqual(sh.snapshot("adset", {"effective_status": "ACTIVE", "learning_stage_info": {"status": "FAIL"}})["learning"], "FAIL")


class DiffTests(unittest.TestCase):
    def test_no_change_no_event(self):
        snap = sh.snapshot("ad", ad())
        self.assertEqual(sh.diff("ad", snap, snap, NOW, created_time=None), [])

    def test_review_to_rejected_gives_status_and_review_events(self):
        before = sh.snapshot("ad", ad(effective_status="IN_PROCESS"))
        after = sh.snapshot("ad", ad(effective_status="DISAPPROVED", ad_review_feedback=REJECTED))
        self.assertEqual(sh.diff("ad", before, after, NOW, created_time=None), [
            {"field": "effective_status", "old": "IN_PROCESS", "new": "DISAPPROVED", "backfill": False},
            {"field": "review", "old": None, "new": "PERSONAL_ATTRIBUTES", "backfill": False},
        ])

    def test_first_sighting_of_a_new_ad_is_created(self):
        after = sh.snapshot("ad", ad(effective_status="IN_PROCESS"))
        self.assertEqual(sh.diff("ad", None, after, NOW, created_time=NOW - timedelta(hours=2)),
                         [{"field": "created", "old": None, "new": "IN_PROCESS", "backfill": False}])

    def test_first_sighting_of_an_old_ad_is_backfill(self):
        after = sh.snapshot("ad", ad())
        self.assertEqual(sh.diff("ad", None, after, NOW, created_time=NOW - timedelta(days=5)),
                         [{"field": "effective_status", "old": None, "new": "ACTIVE", "backfill": True}])

    def test_a_field_tracked_for_the_first_time_is_not_a_change(self):
        # Rows stored before the migration have no configured_status: the old status column stands in.
        before = sh.stored_snapshot("ad", {"status": "PAUSED", "configured_status": None, "effective_status": "PAUSED",
                                           "review_feedback": None, "issues": None})
        after = sh.snapshot("ad", ad(status="PAUSED", configured_status="PAUSED", effective_status="PAUSED"))
        self.assertEqual(sh.diff("ad", before, after, NOW, created_time=None), [])

    def test_learning_limited_on_an_ad_set(self):
        before = sh.stored_snapshot("adset", {"status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE",
                                              "learning_stage": "LEARNING", "learning": None, "issues": None})
        after = sh.snapshot("adset", {"status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE",
                                      "learning_stage_info": {"status": "FAIL", "conversions": 9}})
        self.assertEqual(sh.diff("adset", before, after, NOW, created_time=None),
                         [{"field": "learning", "old": "LEARNING", "new": "FAIL", "backfill": False}])

    def test_issues_appear_on_a_campaign(self):
        before = sh.stored_snapshot("campaign", {"status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE", "issues": None})
        after = sh.snapshot("campaign", {"status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "WITH_ISSUES",
                                         "issues_info": [{"error_summary": "Payment method failed", "error_code": 1487}]})
        self.assertEqual(sh.diff("campaign", before, after, NOW, created_time=None), [
            {"field": "effective_status", "old": "ACTIVE", "new": "WITH_ISSUES", "backfill": False},
            {"field": "issues", "old": None, "new": "Payment method failed", "backfill": False},
        ])


class ConsoleTests(unittest.TestCase):
    CHANGES = [{"id": 7, "entity_id": "a1", "action": "status", "new_value": "PAUSED", "ok": True,
                "created_at": NOW - timedelta(minutes=3)},
               {"id": 8, "entity_id": "a1", "action": "status", "new_value": "ACTIVE", "ok": True,
                "created_at": NOW - timedelta(minutes=30)}]

    def test_our_own_status_write_explains_the_change(self):
        ev = {"field": "configured_status", "old": "ACTIVE", "new": "PAUSED"}
        self.assertEqual(sh.explained_by_console("a1", ev, self.CHANGES, NOW), 7)

    def test_effective_status_follows_our_write(self):
        ev = {"field": "effective_status", "old": "ACTIVE", "new": "PAUSED"}
        self.assertEqual(sh.explained_by_console("a1", ev, self.CHANGES, NOW), 7)

    def test_an_old_write_explains_nothing(self):
        ev = {"field": "configured_status", "old": "PAUSED", "new": "ACTIVE"}
        self.assertIsNone(sh.explained_by_console("a1", ev, self.CHANGES, NOW))

    def test_leaving_a_rejection_is_metas_even_after_our_switch(self):
        ev = {"field": "effective_status", "old": "DISAPPROVED", "new": "ACTIVE"}
        changes = [dict(self.CHANGES[1], created_at=NOW - timedelta(minutes=2))]
        self.assertIsNone(sh.explained_by_console("a1", ev, changes, NOW))

    def test_review_changes_are_never_ours(self):
        ev = {"field": "effective_status", "old": "IN_PROCESS", "new": "DISAPPROVED"}
        self.assertIsNone(sh.explained_by_console("a1", ev, self.CHANGES, NOW))


class TimelineWordsTests(unittest.TestCase):
    def test_plain_words_for_review_steps(self):
        cases = [
            ({"field": "created", "old": None, "new": "IN_PROCESS"}, "Created · in review"),
            ({"field": "effective_status", "old": "IN_PROCESS", "new": "ACTIVE"}, "Approved · delivering"),
            ({"field": "effective_status", "old": "PENDING_REVIEW", "new": "DISAPPROVED"}, "Rejected by Meta"),
            ({"field": "effective_status", "old": "ACTIVE", "new": "WITH_ISSUES"}, "Has issues"),
            ({"field": "effective_status", "old": "ACTIVE", "new": "PAUSED"}, "Turned off"),
            ({"field": "learning", "old": "LEARNING", "new": "FAIL"}, "Learning limited"),
            ({"field": "learning", "old": "LEARNING", "new": "SUCCESS"}, "Finished learning"),
            ({"field": "review", "old": None, "new": "PERSONAL_ATTRIBUTES; instagram: PERSONAL_ATTRIBUTES"},
             "Meta's reason: Personal attributes (also on Instagram)"),
            ({"field": "review", "old": None, "new": "instagram: TEXT_OVERLAY"}, "Meta's reason: Text overlay (Instagram)"),
        ]
        self.assertEqual([sh.headline(ev) for ev, _ in cases], [want for _, want in cases])


if __name__ == "__main__":
    unittest.main()


class TransitionTests(unittest.TestCase):
    RULES = {"ad_rejected": {"on": True}, "ad_approved": {"on": True}, "learning_limited": {"on": True},
             "changed_outside": {"on": True}}
    AD = {"id": "a1", "name": "N1 · v2", "campaign_id": "c1", "adset_id": "s1",
          "ad_review_feedback": {"global": {"PERSONAL_ATTRIBUTES": "Ads can't imply knowledge of personal attributes."}}}
    TODAY = NOW.date()

    def found(self, level, entity, events, rules=None):
        return sh.transitions(level, entity, events, rules or self.RULES, NOW, self.TODAY)

    def test_leaving_review_is_an_approval(self):
        ev = [{"field": "effective_status", "old": "IN_PROCESS", "new": "ACTIVE", "source": "poll"}]
        got = self.found("ad", self.AD, ev)
        self.assertEqual([(a["rule"], a["level"], a["kind"], a["resolved"], a["title"], a["href"]) for a in got],
                         [("ad_approved", "ok", "event", True, "Meta approved “N1 · v2”", "/ad.html?id=a1")])

    def test_a_new_ad_seen_already_live_is_an_approval(self):
        ev = [{"field": "created", "old": None, "new": "ACTIVE", "source": "poll"}]
        self.assertEqual([a["rule"] for a in self.found("ad", self.AD, ev)], ["ad_approved"])

    def test_turning_an_approved_ad_back_on_is_not_an_approval(self):
        ev = [{"field": "effective_status", "old": "PAUSED", "new": "ACTIVE", "source": "console"}]
        self.assertEqual(self.found("ad", self.AD, ev), [])

    def test_rejection_shares_the_polled_rule_key_and_names_the_reason(self):
        ev = [{"field": "effective_status", "old": "IN_PROCESS", "new": "DISAPPROVED", "source": "webhook"},
              {"field": "review", "old": None, "new": "PERSONAL_ATTRIBUTES", "source": "webhook"}]
        got = self.found("ad", self.AD, ev)
        self.assertEqual([(a["rule"], a["key"], a["kind"], a["resolved"]) for a in got],
                         [("ad_rejected", "ad_rejected:a1:2026-11-10", "condition", False)])
        self.assertEqual(got[0]["lines"][0], "Reason: Personal attributes. Ads can't imply knowledge of personal attributes.")

    def test_learning_limited_on_an_ad_set(self):
        ev = [{"field": "learning", "old": "LEARNING", "new": "FAIL", "source": "poll"}]
        got = self.found("adset", {"id": "s1", "name": "SoCal", "campaign_id": "c1",
                                   "learning_stage_info": {"status": "FAIL", "conversions": 9}}, ev)
        self.assertEqual([(a["rule"], a["key"], a["level"]) for a in got], [("learning_limited", "learning_limited:s1:2026-11-10", "warn")])
        self.assertIn("9 results", got[0]["lines"][0])

    def test_switch_outside_the_console(self):
        ev = [{"field": "configured_status", "old": "ACTIVE", "new": "PAUSED", "source": "poll"}]
        got = self.found("campaign", {"id": "c1", "name": "Leads"}, ev)
        self.assertEqual([(a["rule"], a["level"], a["title"]) for a in got],
                         [("changed_outside", "info", "Campaign “Leads” was switched off outside this console")])

    def test_our_own_switch_raises_nothing(self):
        ev = [{"field": "configured_status", "old": "ACTIVE", "new": "PAUSED", "source": "console"}]
        self.assertEqual(self.found("campaign", {"id": "c1", "name": "Leads"}, ev), [])

    def test_backfill_and_switched_off_rules_raise_nothing(self):
        ev = [{"field": "effective_status", "old": "IN_PROCESS", "new": "ACTIVE", "source": "poll"}]
        self.assertEqual(self.found("ad", self.AD, ev, dict(self.RULES, ad_approved={"on": False})), [])
        self.assertEqual(self.found("ad", self.AD, [{"field": "effective_status", "old": None, "new": "ACTIVE",
                                                     "source": "backfill", "backfill": True}]), [])
