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
        # One vocabulary (9.2): Meta's impressions are "views" everywhere a person reads them.
        self.assertEqual(found[1]["lines"], ["No views 30 hours after it went live."])

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

    def test_settings_alerts_open_the_settings_section_they_name(self):
        y, d2 = TODAY - timedelta(days=1), TODAY - timedelta(days=2)
        found = alerts.evaluate(snap(meta_leads={y: 2, d2: 1}, inbox_leads={}, last_pull_age_h=4,
                                     tracking={"state": "quiet", "headline": "Nothing for two days."}), RULES, TODAY)
        self.assertEqual(sorted((a["rule"], a["href"]) for a in found),
                         [("events_quiet", "/settings.html#tracking"), ("stale_data", "/settings.html#meta"),
                          ("tracking", "/settings.html#meta")])


class MeasureTests(unittest.TestCase):
    """Each alert keeps the figure its rule judged, so a snooze can tell "clearly worse" (W1)."""

    def test_spending_limit_percent_used(self):
        found = alerts.evaluate(snap(cap={"limit_cents": 15000, "spent_cents": 12300}), RULES, TODAY)
        self.assertEqual([(a["rule"], a["measure"]) for a in found], [("spend_cap", 82.0)])

    def test_cost_per_lead_in_cents_and_spend_when_there_are_none(self):
        target = alerts.rules_with({"cpl_high": {"target_cents": 1500}})
        # 7 days at $20 a day: one lead a day is $20 each (over 1.3 × $15), none at all is the $140 spent.
        found = [alerts.evaluate(snap(camp_days={"c1": days(7, spend_cents=2000, leads=n)}), target, TODAY) for n in (1, 0)]
        self.assertEqual([[(a["rule"], a["measure"]) for a in f if a["rule"] == "cpl_high"] for f in found],
                         [[("cpl_high", 2000)], [("cpl_high", 14000)]])

    def test_rejected_is_two_and_issues_one(self):
        ads = [{"id": "a1", "name": "N1", "campaign_id": "c1", "effective_status": "DISAPPROVED", "age_hours": 50},
               {"id": "a2", "name": "N2", "campaign_id": "c1", "effective_status": "WITH_ISSUES", "age_hours": 50}]
        self.assertEqual([(a["entity_id"], a["measure"]) for a in alerts.evaluate(snap(ads=ads), RULES, TODAY)], [("a1", 2), ("a2", 1)])

    def test_rules_without_a_figure_carry_none(self):
        found = alerts.evaluate(snap(tracking={"state": "quiet", "headline": "Nothing for two days."}), RULES, TODAY)
        self.assertEqual([(a["rule"], a["measure"]) for a in found], [("events_quiet", None)])


class DryStreakTests(unittest.TestCase):
    def test_days_in_a_row_ending_yesterday_with_spend_and_no_lead(self):
        rows = days(7, spend_cents=2000, leads=1)[:2] + days(5, spend_cents=2000, leads=0)
        self.assertEqual(alerts._dry_streak(rows, TODAY), 5)

    def test_a_day_without_spend_or_a_missing_day_ends_the_streak(self):
        no_spend = days(4, spend_cents=2000, leads=0)
        no_spend[1] = {**no_spend[1], "spend_cents": 0}
        gap = days(4, spend_cents=2000, leads=0)
        del gap[2]
        self.assertEqual([alerts._dry_streak(no_spend, TODAY), alerts._dry_streak(gap, TODAY), alerts._dry_streak([], TODAY)], [2, 1, 0])

    def test_no_leads_names_the_streak_and_judges_it(self):
        rows = days(7, spend_cents=2000, leads=1)[:2] + days(5, spend_cents=2000, leads=0)
        found = [a for a in alerts.evaluate(snap(camp_days={"c1": rows}), RULES, TODAY) if a["rule"] == "no_leads"]
        self.assertEqual([(a["title"], a["measure"], a["lines"]) for a in found],
                         [("No leads for 5 days in “Leads”", 5, ["$100 spent since Nov 4 and not one lead. Check the form and the ads."])])

    def test_a_streak_shorter_than_the_rule_raises_nothing(self):
        rows = days(7, spend_cents=2000, leads=1)[:5] + days(2, spend_cents=2000, leads=0)
        self.assertEqual(rules_of(alerts.evaluate(snap(camp_days={"c1": rows}), RULES, TODAY)), [])


def quality(worked=12, qualified=2, leads=None, junk=None, by_ad=None):
    """One campaign's lead quality in the window, as alerts.snapshot gives it (W1b)."""
    return {"c1": {"name": "Leads", "leads": worked if leads is None else leads, "worked": worked, "qualified": qualified,
                   "junk": junk, "by_ad": by_ad or []}}


def lq_alerts(lq, rules=RULES):
    return [a for a in alerts.evaluate(snap(lead_quality=lq), rules, TODAY) if a["rule"] in ("qualified_low", "junk_high")]


class QualifiedLowTests(unittest.TestCase):
    """Few of the leads the team worked (14 days ending 2 days ago) reached Qualified (W1b)."""

    def test_two_of_twelve_worked_fires_with_the_lowest_ad(self):
        n3 = {"ad_id": "a3", "ad_name": "N3", "leads": 7, "worked": 7, "qualified": 0, "junk": None}
        found = lq_alerts(quality(by_ad=[n3]))
        self.assertEqual([(a["rule"], a["entity_id"], a["campaign_id"], a["level"], a["measure"], a["title"], a["lines"], a["href"]) for a in found],
                         [("qualified_low", "c1", "c1", "warn", 16.7, "Only 17% of leads from “Leads” qualify",
                           ["2 of 12 leads the team worked in the last 14 days were qualified. You're alerted below 20%.",
                            "Lowest: “N3”, 0 of 7 qualified.", "Cheap leads that don't qualify cost more than they look."],
                           "/leads.html?campaign=c1")])

    def test_at_the_threshold_nothing(self):
        self.assertEqual(lq_alerts(quality(qualified=3)), [])

    def test_too_few_worked_leads_nothing(self):
        self.assertEqual(lq_alerts(quality(worked=9, qualified=0)), [])

    def test_one_qualified_is_said_in_the_singular(self):
        self.assertEqual(lq_alerts(quality(qualified=1))[0]["lines"][0],
                         "1 of 12 leads the team worked in the last 14 days was qualified. You're alerted below 20%.")

    def test_a_half_percent_rounds_up_in_the_title(self):
        found = lq_alerts(quality(worked=24, qualified=3))
        self.assertEqual([(a["title"], a["measure"]) for a in found], [("Only 13% of leads from “Leads” qualify", 12.5)])

    def test_the_lowest_ad_needs_five_worked_leads_and_is_not_named_when_it_is_every_lead(self):
        small = {"ad_id": "a3", "ad_name": "N3", "leads": 4, "worked": 4, "qualified": 0, "junk": 0}
        whole = {"ad_id": "a1", "ad_name": "N1", "leads": 12, "worked": 12, "qualified": 2, "junk": 0}
        self.assertEqual([lq_alerts(quality(by_ad=[small]))[0]["lines"], lq_alerts(quality(by_ad=[whole]))[0]["lines"]],
                         [["2 of 12 leads the team worked in the last 14 days were qualified. You're alerted below 20%.",
                           "Cheap leads that don't qualify cost more than they look."]] * 2)

    def test_the_lowest_rate_wins_over_the_most_leads(self):
        n1 = {"ad_id": "a1", "ad_name": "N1", "leads": 6, "worked": 6, "qualified": 1, "junk": 0}
        n2 = {"ad_id": "a2", "ad_name": "N2", "leads": 5, "worked": 5, "qualified": 0, "junk": 0}
        self.assertEqual(lq_alerts(quality(worked=13, by_ad=[n1, n2]))[0]["lines"][1], "Lowest: “N2”, 0 of 5 qualified.")

    def test_switched_off_and_own_thresholds(self):
        off = alerts.rules_with({"qualified_low": {"on": False}})
        stricter = alerts.rules_with({"qualified_low": {"percent": 30, "min_leads": 20}})
        looser = alerts.rules_with({"qualified_low": {"percent": 30, "min_leads": 5}})
        self.assertEqual([rules_of(lq_alerts(quality(qualified=3), r)) for r in (off, stricter, looser)], [[], [], ["qualified_low"]])


class JunkHighTests(unittest.TestCase):
    """Many counted leads in the window look like junk (lead_quality.is_junk, W1b)."""

    def test_four_of_twelve_fires(self):
        found = lq_alerts(quality(worked=6, qualified=3, leads=12, junk=4))
        self.assertEqual([(a["rule"], a["entity_id"], a["level"], a["measure"], a["title"], a["lines"], a["href"]) for a in found],
                         [("junk_high", "c1", "warn", 33.3, "33% of leads from “Leads” look like junk",
                           ["4 of 12 leads in the last 14 days look like junk (marked spam or fake, or fake-looking details and never contacted)."],
                           "/leads.html?campaign=c1&status=all&junk=1")])

    def test_two_junk_leads_are_never_enough(self):
        self.assertEqual(lq_alerts(quality(worked=6, qualified=3, leads=6, junk=2), alerts.rules_with({"junk_high": {"min_leads": 5}})), [])

    def test_at_the_threshold_or_with_too_few_leads_nothing(self):
        self.assertEqual([lq_alerts(quality(worked=6, qualified=3, leads=10, junk=3)), lq_alerts(quality(worked=5, qualified=3, leads=9, junk=4))],
                         [[], []])

    def test_the_ad_with_the_most_junk_is_named(self):
        n3 = {"ad_id": "a3", "ad_name": "N3", "leads": 6, "worked": 2, "qualified": 1, "junk": 3}
        n1 = {"ad_id": "a1", "ad_name": "N1", "leads": 6, "worked": 4, "qualified": 2, "junk": 1}
        self.assertEqual(lq_alerts(quality(worked=6, qualified=3, leads=12, junk=4, by_ad=[n1, n3]))[0]["lines"][1],
                         "Highest: “N3”, 3 of 6 look like junk.")


class LeadQualityGroupTests(unittest.TestCase):
    """The snapshot's rows grouped by campaign and ad: worked = past New or Lost, qualified = highest stage, junk = is_junk."""

    def row(self, ad="a1", stage="new", status="new", reason=None, flags=(), dismissed=False):
        return {"campaign_id": "c1", "campaign_name": "Leads", "ad_id": ad, "ad_name": {"a1": "N1", "a3": "N3"}.get(ad),
                "max_stage": stage, "status": status, "lost_reason": reason, "junk_flags": list(flags), "junk_dismissed": dismissed}

    def test_counts_by_campaign_and_ad(self):
        rows = [self.row(stage="qualified", status="qualified"), self.row(stage="won", status="won"),
                self.row(stage="contacted", status="contacted"), self.row(status="lost", reason="no_response"),
                self.row(ad="a3"), self.row(ad="a3", status="lost", reason="spam"),
                self.row(ad="a3", flags=["fake_phone"]), self.row(ad="a3", flags=["fake_phone"], dismissed=True),
                self.row(ad=None, stage="qualified", status="lost", reason="price")]
        self.assertEqual(alerts.lead_quality_groups(rows), {"c1": {
            "name": "Leads", "leads": 9, "worked": 6, "qualified": 3, "junk": 2,
            "by_ad": [{"ad_id": "a1", "ad_name": "N1", "leads": 4, "worked": 4, "qualified": 2, "junk": 0},
                      {"ad_id": "a3", "ad_name": "N3", "leads": 4, "worked": 1, "qualified": 0, "junk": 2}]}})

    def test_no_rows_no_campaigns(self):
        self.assertEqual(alerts.lead_quality_groups([]), {})


class LeadQualityDefaultsTests(unittest.TestCase):
    def test_both_rules_are_on_with_the_spec_numbers_and_there_is_no_follow_up_rule(self):
        self.assertEqual((RULES["qualified_low"], RULES["junk_high"], "followups_overdue" in alerts.DEFAULTS),
                         ({"on": True, "percent": 20, "min_leads": 10}, {"on": True, "percent": 30, "min_leads": 10}, False))

    def test_a_healthy_account_with_no_lead_quality_raises_nothing(self):
        self.assertEqual(alerts.evaluate(snap(lead_quality={}), RULES, TODAY), [])


class RulesWithTests(unittest.TestCase):
    def test_saved_values_override_defaults_and_unknown_keys_are_dropped(self):
        r = alerts.rules_with({"no_leads": {"days": 5}, "bogus": {"on": True}, "spend_cap": {"percent": "90"}})
        self.assertEqual((r["no_leads"], r["spend_cap"]["percent"], "bogus" in r), ({"on": True, "days": 5}, 90, False))


class NumbersOffTests(unittest.TestCase):
    """D1: our stored days differ from Ads Manager's own totals after a night's pull (or a pull by hand)."""
    OFF = {"state": "off", "off_days": ["2026-10-14", "2026-10-20"], "spend_off_cents": 30, "leads_off": 1,
           "off": [{"day": "2026-10-14", "meta_spend_cents": 1234, "meta_leads": 3, "here_spend_cents": 1204, "here_leads": 2},
                   {"day": "2026-10-20", "meta_spend_cents": 500, "meta_leads": 0, "here_spend_cents": 500, "here_leads": 0}]}

    def found(self, summary, kind="nightly", off_runs=1, rules=RULES):
        got = alerts.evaluate(snap(numbers={"summary": summary, "kind": kind, "off_runs": off_runs}), rules, TODAY)
        return [a for a in got if a["rule"] == "numbers_off"]

    def test_one_night_off_is_for_information(self):
        got = self.found(self.OFF)
        self.assertEqual([(a["level"], a["title"], a["lines"], a["href"], a["entity_id"], a["measure"]) for a in got],
                         [("info", "Numbers differ from Ads Manager on Oct 14 and Oct 20",
                           ["Ads Manager says $12.34 and 3 leads for Oct 14; we have $12.04 and 2.",
                            "We pull these days again every night."], "/settings.html#numbers", "account", 2)])

    def test_two_runs_in_a_row_need_action(self):
        self.assertEqual([a["level"] for a in self.found(self.OFF, off_runs=2)], ["warn"])
        self.assertEqual([a["level"] for a in self.found(self.OFF, kind="pull", off_runs=3)], ["warn"])

    def test_nothing_when_it_matches_when_unchecked_or_when_the_rule_is_off(self):
        off_rule = alerts.rules_with({"numbers_off": {"on": False}})
        self.assertEqual([self.found({"state": "match"}), self.found({"state": "unchecked"}), self.found(self.OFF, rules=off_rule),
                          self.found(None)], [[], [], [], []])

    def test_a_check_now_neither_raises_nor_closes_it(self):
        self.assertEqual(self.found(self.OFF, kind="check"), [])
        opened = [{"id": 7, "rule": "numbers_off", "entity_id": "account"}]
        self.assertEqual(alerts.to_resolve(opened, [], snap(numbers={"summary": self.OFF, "kind": "check", "off_runs": 1})), [])
        self.assertEqual(alerts.to_resolve(opened, [], snap(numbers={"summary": {"state": "match"}, "kind": "check", "off_runs": 0})), [7])
