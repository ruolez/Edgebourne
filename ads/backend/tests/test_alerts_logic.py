import unittest
from datetime import date, timedelta

import alerts

TODAY = date(2026, 11, 9)
RULES = alerts.rules_with({})


def days(n, **row):
    """n complete days ending yesterday, oldest first."""
    return [{"day": TODAY - timedelta(days=n - i), **row} for i in range(n)]


def snap(**kw):
    base = {"ads": [], "ad_days": {}, "campaigns": [{"id": "c1", "name": "Leads", "daily_budget_cents": 2000}],
            "camp_days": {"c1": days(7, spend_cents=2000, leads=3)}, "today_spend": {}, "cap": None,
            "inbox_leads": {}, "meta_leads": {}, "last_pull_age_h": 0.2, "connected": True}
    base.update(kw)
    return base


def rules_of(found):
    return sorted(a["rule"] for a in found)


class QuietTests(unittest.TestCase):
    def test_a_healthy_account_raises_nothing(self):
        self.assertEqual(alerts.evaluate(snap(), RULES, TODAY), [])


class AdRuleTests(unittest.TestCase):
    def test_rejected_ad_and_ad_with_no_impressions(self):
        ads = [{"id": "a1", "name": "N1", "campaign_id": "c1", "effective_status": "DISAPPROVED", "age_hours": 50},
               {"id": "a2", "name": "N2", "campaign_id": "c1", "effective_status": "ACTIVE", "age_hours": 30},
               {"id": "a3", "name": "N3", "campaign_id": "c1", "effective_status": "ACTIVE", "age_hours": 10}]
        found = alerts.evaluate(snap(ads=ads, ad_days={"a2": days(2, impressions=0, reach=0, link_clicks=0, spend_cents=0, leads=0)}), RULES, TODAY)
        self.assertEqual([(a["rule"], a["entity_id"], a["key"]) for a in found],
                         [("ad_rejected", "a1", "ad_rejected:a1:2026-11-09"), ("no_delivery", "a2", "no_delivery:a2:2026-11-09")])

    def test_an_ad_first_seen_today_is_not_called_unseen(self):
        # Live for 30 hours, nothing on the complete days, 600 impressions so far today (audit A3-63).
        ad = {"id": "a2", "name": "N2", "campaign_id": "c1", "effective_status": "ACTIVE", "age_hours": 30}
        quiet = {"a2": days(1, impressions=0, reach=0, link_clicks=0, spend_cents=0, leads=0)}
        found = [rules_of(alerts.evaluate(snap(ads=[{**ad, "today_impressions": n}], ad_days=quiet), RULES, TODAY)) for n in (600, 0)]
        self.assertEqual(found, [[], ["no_delivery"]])

    def test_alert_amounts_are_in_the_account_currency(self):
        found = alerts.evaluate(snap(today_spend={"c1": 4000}, currency="EUR"), RULES, TODAY)
        self.assertEqual([a["title"] for a in found], ["€40 spent today on a €20 daily budget"])

    def test_fatigue_needs_high_frequency_and_falling_clicks_and_rising_cost(self):
        first = days(21, impressions=1000, reach=800, link_clicks=20, spend_cents=1000, leads=1)[:7]
        tired = days(7, impressions=1000, reach=800, link_clicks=10, spend_cents=1500, leads=0)
        fresh = days(7, impressions=1000, reach=800, link_clicks=20, spend_cents=1000, leads=1)
        gap = days(14, impressions=0, reach=0, link_clicks=0, spend_cents=0, leads=0)[:7]
        ad = [{"id": "a1", "name": "N1", "campaign_id": "c1", "effective_status": "ACTIVE", "age_hours": 600}]
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(ads=ad, ad_days={"a1": first + gap + tired}, reach_7d={"a1": 1800}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(ads=ad, ad_days={"a1": first + fresh}, reach_7d={"a1": 1800}), RULES, TODAY))],
            [["fatigue"], []])

    def test_fatigue_frequency_is_views_per_unique_person_not_per_summed_daily_reach(self):
        # 7,000 views to 1,800 different people is 3.9 a week, although the daily reach adds up to 5,600.
        first = days(21, impressions=1000, reach=800, link_clicks=20, spend_cents=1000, leads=1)[:7]
        gap = days(14, impressions=0, reach=0, link_clicks=0, spend_cents=0, leads=0)[:7]
        tired = days(7, impressions=1000, reach=800, link_clicks=10, spend_cents=1500, leads=0)
        ad = [{"id": "a1", "name": "N1", "campaign_id": "c1", "effective_status": "ACTIVE", "age_hours": 600}]
        found = [alerts.evaluate(snap(ads=ad, ad_days={"a1": first + gap + tired}, reach_7d=r), RULES, TODAY)
                 for r in ({"a1": 1800}, {"a1": 5600}, None, {})]
        self.assertEqual([rules_of(f) for f in found], [["fatigue"], [], [], []])
        self.assertIn("about 3.9 times a week", found[0][0]["lines"][0])


class ResolveTests(unittest.TestCase):
    """Open condition alerts close when their condition is gone, but not when Meta couldn't tell us (audit A3-12)."""

    def test_an_open_fatigue_alert_stays_open_while_meta_does_not_answer_reach(self):
        opened = [{"id": 1, "rule": "fatigue", "entity_id": "a1"}, {"id": 2, "rule": "no_delivery", "entity_id": "a2"},
                  {"id": 3, "rule": "fatigue", "entity_id": "a3"}]
        found = [{"rule": "fatigue", "entity_id": "a3"}]
        self.assertEqual([alerts.to_resolve(opened, found, snap(reach_7d=r)) for r in (None, {}, {"a1": 900})],
                         [[2], [1, 2], [1, 2]])


class SpendRuleTests(unittest.TestCase):
    def test_overspend_today_and_over_the_week(self):
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(today_spend={"c1": 3600}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(today_spend={"c1": 3400}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(camp_days={"c1": days(7, spend_cents=2100, leads=3)}), RULES, TODAY))],
            [["day_overspend"], [], ["week_overspend"]])

    def test_spending_limit_warns_at_the_threshold_and_is_bad_when_reached(self):
        found = [alerts.evaluate(snap(cap={"limit_cents": 15000, "spent_cents": s}), RULES, TODAY) for s in (11000, 12000, 15000)]
        self.assertEqual([[(a["rule"], a["level"]) for a in f] for f in found], [[], [("spend_cap", "warn")], [("spend_cap", "bad")]])


class ResultRuleTests(unittest.TestCase):
    def test_cost_per_lead_is_judged_only_against_a_set_target_with_enough_spend(self):
        with_target = alerts.rules_with({"cpl_high": {"target_cents": 1500}})
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(camp_days={"c1": days(7, spend_cents=2000, leads=1)}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(camp_days={"c1": days(7, spend_cents=2000, leads=1)}), with_target, TODAY)),
             rules_of(alerts.evaluate(snap(camp_days={"c1": days(7, spend_cents=500, leads=1)}), alerts.rules_with({"cpl_high": {"target_cents": 1500}}), TODAY))],
            [[], ["cpl_high"], []])

    def test_no_leads_for_days_while_spending(self):
        dry = days(4, spend_cents=2000, leads=2)[:1] + days(3, spend_cents=2000, leads=0)
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(camp_days={"c1": dry}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(camp_days={"c1": days(3, spend_cents=0, leads=0)}), RULES, TODAY))],
            [["no_leads"], []])

    def test_tracking_break_when_meta_counts_leads_the_inbox_never_got(self):
        y, d2 = TODAY - timedelta(days=1), TODAY - timedelta(days=2)
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(meta_leads={y: 2, d2: 1}, inbox_leads={}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(meta_leads={y: 2, d2: 1}, inbox_leads={y: 1}), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(meta_leads={y: 1}, inbox_leads={}), RULES, TODAY))],
            [["tracking"], [], []])

    def test_stale_data_and_switched_off_rules(self):
        self.assertEqual(
            [rules_of(alerts.evaluate(snap(last_pull_age_h=4), RULES, TODAY)),
             rules_of(alerts.evaluate(snap(last_pull_age_h=4), alerts.rules_with({"stale_data": {"on": False}}), TODAY)),
             rules_of(alerts.evaluate(snap(last_pull_age_h=4, connected=False), RULES, TODAY))],
            [["stale_data"], [], []])


class RulesWithTests(unittest.TestCase):
    def test_saved_values_override_defaults_and_unknown_keys_are_dropped(self):
        r = alerts.rules_with({"no_leads": {"days": 5}, "bogus": {"on": True}, "spend_cap": {"percent": "90"}})
        self.assertEqual((r["no_leads"], r["spend_cap"]["percent"], "bogus" in r), ({"on": True, "days": 5}, 90, False))
