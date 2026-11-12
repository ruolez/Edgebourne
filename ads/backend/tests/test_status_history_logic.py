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
            ({"field": "effective_status", "old": "PENDING_REVIEW", "new": "DISAPPROVED"}, "Rejected"),
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


# ---------------------------------------------------------------- D2: budget, bid, dates and audience
from zoneinfo import ZoneInfo  # noqa: E402

import sync  # noqa: E402
import words  # noqa: E402

LA = ZoneInfo("America/Los_Angeles")
usd = lambda c: words.money(c, "USD")  # noqa: E731
SEEN = datetime(2026, 11, 1, tzinfo=timezone.utc)


def meta_campaign(**kw):
    base = {"id": "C", "name": "Leads", "status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE",
            "daily_budget": "2000", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "stop_time": "2026-11-30T23:59:00-0800",
            "start_time": "2026-11-01T09:00:00-0700", "_fields": sync.CAMPAIGN_FIELDS}
    base.update(kw)
    return base


def stored_campaign(**kw):
    base = {"status": "ACTIVE", "configured_status": "ACTIVE", "effective_status": "ACTIVE", "issues": None,
            "daily_budget_cents": 2000, "lifetime_budget_cents": None, "spend_cap_cents": None,
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "start_time": datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc),
            "stop_time": datetime(2026, 12, 1, 7, 59, tzinfo=timezone.utc), "setup_seen_at": SEEN}
    base.update(kw)
    return base


class SetupSnapshotTests(unittest.TestCase):
    def test_setup_fields_are_read_only_when_they_were_asked_for(self):
        snap = sh.snapshot("campaign", meta_campaign())
        self.assertEqual({k: snap[k] for k in ("daily_budget", "lifetime_budget", "end_time", "start_time", "bid_strategy")},
                         {"daily_budget": 2000, "lifetime_budget": None, "end_time": "2026-12-01T07:59Z",
                          "start_time": "2026-11-01T16:00Z", "bid_strategy": "LOWEST_COST_WITHOUT_CAP"})

    def test_the_older_field_set_compares_no_setup_fields(self):
        snap = sh.snapshot("campaign", meta_campaign(_fields=sync.CAMPAIGN_FIELDS_PLAIN))
        self.assertEqual(set(snap) & set(sh.SETUP["campaign"]), set())

    def test_the_first_full_read_records_nothing(self):
        before = sh.stored_snapshot("campaign", stored_campaign(setup_seen_at=None, daily_budget_cents=1500))
        self.assertEqual(sh.diff("campaign", before, sh.snapshot("campaign", meta_campaign()), NOW, None), [])

    def test_a_budget_raised_elsewhere_is_one_event(self):
        before = sh.stored_snapshot("campaign", stored_campaign())
        after = sh.snapshot("campaign", meta_campaign(daily_budget="3000"))
        self.assertEqual(sh.diff("campaign", before, after, NOW, None),
                         [{"field": "daily_budget", "old": 2000, "new": 3000, "backfill": False}])

    def test_zero_from_meta_is_no_budget(self):
        before = sh.stored_snapshot("campaign", stored_campaign(daily_budget_cents=None))
        self.assertEqual(sh.diff("campaign", before, sh.snapshot("campaign", meta_campaign(daily_budget="0")), NOW, None), [])

    def test_the_same_time_in_another_offset_is_no_change(self):
        before = sh.stored_snapshot("campaign", stored_campaign())
        self.assertEqual(sh.diff("campaign", before, sh.snapshot("campaign", meta_campaign(stop_time="2026-12-01T07:59:00+0000")), NOW, None), [])

    def test_an_end_date_meta_leaves_out_was_removed(self):
        before = sh.stored_snapshot("campaign", stored_campaign())
        meta = meta_campaign()
        del meta["stop_time"]
        self.assertEqual(sh.diff("campaign", before, sh.snapshot("campaign", meta), NOW, None),
                         [{"field": "end_time", "old": "2026-12-01T07:59Z", "new": None, "backfill": False}])

    def test_minute_utc(self):
        self.assertEqual([sh.minute_utc("2026-11-30T23:59:00-0800"), sh.minute_utc(datetime(2026, 12, 1, 7, 59, 30, tzinfo=timezone.utc)),
                          sh.minute_utc(None), sh.minute_utc("")], ["2026-12-01T07:59Z", "2026-12-01T07:59Z", None, None])


class FingerprintTests(unittest.TestCase):
    BASE = {"age_min": 25, "geo_locations": {"countries": ["US"]}}

    def test_reordered_keys_and_meta_defaults_are_the_same_audience(self):
        noisy = {"geo_locations": {"countries": ["US"]}, "targeting_relaxation_types": {"lookalike": 1},
                 "age_range": [25, 65], "age_min": 25}
        self.assertEqual(sh.targeting_fingerprint(self.BASE), sh.targeting_fingerprint(noisy))

    def test_a_real_change_is_a_different_audience(self):
        self.assertNotEqual(sh.targeting_fingerprint(self.BASE), sh.targeting_fingerprint({**self.BASE, "age_min": 30}))

    def test_list_order_does_not_matter(self):
        a = {"flexible_spec": [{"interests": [{"id": "2", "name": "B"}, {"id": "1", "name": "A"}]}]}
        b = {"flexible_spec": [{"interests": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]}]}
        self.assertEqual(sh.targeting_fingerprint(a), sh.targeting_fingerprint(b))

    def test_no_audience_no_fingerprint(self):
        self.assertEqual([sh.targeting_fingerprint(None), sh.targeting_fingerprint({})], [None, None])


class ExplainedBudgetTests(unittest.TestCase):
    def change(self, **kw):
        base = {"id": 7, "entity_id": "C", "action": "budget", "new_value": "2600", "ok": True, "created_at": NOW - timedelta(minutes=3)}
        base.update(kw)
        return [base]

    def test_our_own_budget_write_explains_the_change(self):
        ev = {"field": "daily_budget", "new": 2600}
        self.assertEqual([sh.explained_by_console("C", ev, self.change(), NOW),
                          sh.explained_by_console("C", ev, self.change(new_value="2500"), NOW)], [7, None])

    def test_metas_advice_applied_here_explains_any_amount(self):
        ev = {"field": "daily_budget", "new": 3100}
        self.assertEqual([sh.explained_by_console("C", ev, self.change(action="recommendation", new_value="Raise"), NOW),
                          sh.explained_by_console("C", ev, self.change(action="recommendation", created_at=NOW - timedelta(minutes=11)), NOW)],
                         [7, None])


class SetupHeadlineTests(unittest.TestCase):
    def h(self, field, old, new, **kw):
        return sh.headline({"field": field, "old": old, "new": new, **kw}, money=usd, tz=LA)

    def test_every_new_field_in_plain_words(self):
        cases = [
            (("daily_budget", "2000", "2400"), "Budget $20.00 → $24.00 a day"),
            (("daily_budget", None, "1000"), "Daily budget set: $10.00 a day"),
            (("lifetime_budget", "50000", "70000"), "Lifetime budget $500.00 → $700.00"),
            (("spend_cap", None, "30000"), "Campaign spending limit set: $300.00"),
            (("spend_cap", "30000", None), "Campaign spending limit removed"),
            (("bid_strategy", "LOWEST_COST_WITHOUT_CAP", "COST_CAP"), "Bid strategy: Highest volume → Cost per result goal"),
            (("bid_strategy", None, "SOMETHING_NEW"), "Bid strategy: Something New"),
            (("bid_amount", "4000", "3500"), "Bid amount $40.00 → $35.00"),
            (("start_time", None, "2026-11-12T17:00Z"), "Start moved to Nov 12, 9:00 AM"),
            (("end_time", "2026-12-01T07:59Z", None), "End date removed: runs until turned off"),
            (("end_time", None, "2026-12-01T07:59Z"), "End date set: Nov 30"),
            (("end_time", "2026-12-01T07:59Z", "2026-12-16T07:59Z"), "End date moved: Nov 30 → Dec 15"),
        ]
        self.assertEqual([self.h(*args) for args, _ in cases], [want for _, want in cases])

    def test_removing_a_daily_budget_says_where_the_budget_went(self):
        self.assertEqual([sh.headline({"field": "daily_budget", "old": "2000", "new": None, "level": lvl}, money=usd)
                          for lvl in ("campaign", "adset")],
                         ["Daily budget removed: the ad sets have their own now",
                          "Daily budget removed: the campaign's budget is shared now"])

    def test_audience_says_what_changed(self):
        detail = {"before": "Ages 25–65+ · US", "after": "Ages 30–65+ · US"}
        self.assertEqual([self.h("targeting", "a", "b", detail=detail),
                          self.h("targeting", "a", "b", detail={"before": "Same", "after": "Same"})],
                         ["Audience changed: Ages 25–65+ · US → Ages 30–65+ · US",
                          "Audience settings changed (see Ads Manager for the detail)"])

    def test_outside_fields_cover_the_switch_and_every_setup_field(self):
        self.assertEqual(set(sh.OUTSIDE_FIELDS), {"configured_status"} | set(sh.SETUP["campaign"]) | set(sh.SETUP["adset"]))


class OutsideEditAlertTests(unittest.TestCase):
    RULES = {"outside_edit": {"on": True}, "changed_outside": {"on": True}}
    CAMP = {"id": "C", "name": "Leads"}
    BEFORE = {"at": NOW - timedelta(days=2), "field": "daily_budget", "old": 1600, "new": 2000, "by": "Eugene",
              "where": "console", "proposal_id": None}

    def found(self, events, context=None, rules=None, level="campaign", entity=None):
        return sh.transitions(level, entity or self.CAMP, events, rules or self.RULES, NOW, NOW.date(),
                              money=usd, context=context or {"cap_cents": 10000, "last_budget": None}, tz=LA)

    def ev(self, field="daily_budget", old=2000, new=3000, source="poll", **kw):
        return {"field": field, "old": old, "new": new, "source": source, "entity_id": "C", **kw}

    def test_a_raise_that_breaks_two_rules_is_a_warning_to_act_on(self):
        got = self.found([self.ev()], {"cap_cents": 10000, "last_budget": self.BEFORE})
        self.assertEqual([(a["rule"], a["level"], a["kind"], a["resolved"], a["title"], a["href"], a["key"]) for a in got],
                         [("outside_edit", "warn", "event", False, "Budget changed in Ads Manager: $20.00 → $30.00 a day",
                           "/campaign.html?id=C&tab=history", "outside_edit:C:2026-11-10T18:00")])
        self.assertEqual(got[0]["lines"],
                         ["Campaign “Leads”", "That's +50%, more than the +20% step the console allows at once.",
                          "The budget had changed only 2 days before (Nov 8, $16.00 → $20.00).",
                          "Made outside this console (Ads Manager, or Claude on the Mac). Nothing to do if that was you."])

    def test_a_small_raise_with_no_history_is_for_information(self):
        got = self.found([self.ev(new=2200)])
        self.assertEqual([(a["level"], a["resolved"], len(a["lines"])) for a in got], [("info", True, 2)])

    def test_a_cut_above_a_ceiling_lowered_since_is_a_warning(self):
        got = self.found([self.ev(old=3000, new=2800)], {"cap_cents": 2500, "last_budget": None})
        self.assertEqual((got[0]["level"], got[0]["lines"][1]), ("warn", "It's above the highest daily budget set in Settings ($25.00)."))

    def test_several_outside_changes_are_one_item(self):
        got = self.found([self.ev(new=2200), self.ev(field="end_time", old=None, new="2026-12-01T07:59Z")])
        self.assertEqual([(a["title"], a["lines"][1:3]) for a in got],
                         [("Campaign “Leads” changed in Ads Manager", ["Budget $20.00 → $22.00 a day", "End date set: Nov 30"])])

    def test_single_change_titles(self):
        cases = [(self.ev(field="end_time", old=None, new="2026-12-01T07:59Z"), "End date set in Ads Manager: Nov 30"),
                 (self.ev(field="end_time", old="2026-12-01T07:59Z", new=None), "End date removed in Ads Manager"),
                 (self.ev(field="end_time", old="2026-12-01T07:59Z", new="2026-12-16T07:59Z"), "End date moved in Ads Manager: Nov 30 → Dec 15"),
                 (self.ev(field="targeting", old="a", new="b"), "Audience changed in Ads Manager"),
                 (self.ev(field="bid_strategy", old="LOWEST_COST_WITHOUT_CAP", new="COST_CAP"),
                  "Bid strategy changed in Ads Manager: Highest volume → Cost per result goal"),
                 (self.ev(field="lifetime_budget", old=50000, new=70000), "Lifetime budget changed in Ads Manager: $500.00 → $700.00"),
                 (self.ev(field="daily_budget", old=None, new=1000), "Daily budget set in Ads Manager: $10.00 a day"),
                 (self.ev(field="daily_budget", old=2000, new=None), "Daily budget removed in Ads Manager")]
        adset = {"id": "S", "name": "SoCal", "campaign_id": "C"}
        self.assertEqual([self.found([e], level="adset", entity=adset)[0]["title"] for e, _ in cases], [t for _, t in cases])

    def test_console_and_first_sightings_never_alert(self):
        self.assertEqual(self.found([self.ev(source="console"), self.ev(source="backfill")]), [])

    def test_the_rule_can_be_switched_off(self):
        self.assertEqual(self.found([self.ev()], rules={"outside_edit": {"on": False}}), [])

    def test_the_switch_alert_still_fires_and_links_to_history(self):
        got = self.found([{"field": "configured_status", "old": "ACTIVE", "new": "PAUSED", "source": "poll"}])
        self.assertEqual([(a["rule"], a["href"]) for a in got], [("changed_outside", "/campaign.html?id=C&tab=history")])

    def test_an_ad_set_links_to_its_own_history(self):
        got = self.found([self.ev()], level="adset", entity={"id": "S", "name": "SoCal", "campaign_id": "C"})
        self.assertEqual((got[0]["href"], got[0]["lines"][0], got[0]["campaign_id"]), ("/adset.html?id=S&tab=history", "Ad set “SoCal”", "C"))
