import unittest

from datetime import datetime, timezone

import campaign_build as cb

ADSET = {"name": "SoCal", "locations": [{"kind": "city", "key": "1", "name": "Riverside, California", "radius": 25}],
         "age_min": 25, "age_max": 65, "advantage": True, "suggest_min": 30, "suggest_max": 64}
AD = {"name": "N6 - Payroll", "title": "Payroll in one click", "body": "Stop retyping hours.\nFree intro call.",
      "template_ad_id": "t1", "media": {"kind": "same"}, "cta_type": "SIGN_UP"}
SPEC = {"name": "EB - Payroll - Leads", "daily_budget_cents": 2000, "adset": ADSET, "form_id": "f1", "ads": [AD]}


class ProblemTests(unittest.TestCase):
    def test_a_complete_spec_has_none(self):
        self.assertEqual(cb.problems(SPEC, {"f1"}, {"t1"}, 2000), [])

    def test_each_step_reports_its_own_problems(self):
        bad = {**SPEC, "name": "", "daily_budget_cents": 50, "form_id": "nope",
               "ads": [{**AD, "template_ad_id": "x", "cta_type": "SHOP_NOW", "media": {"kind": "image"}}, {**AD, "title": "", "name": "N7"}]}
        self.assertEqual([s for s, _ in cb.problems(bad, {"f1"}, {"t1"})], ["goal", "budget", "form", "ads", "ads", "ads", "ads"])

    def test_a_budget_three_times_what_runs_now_is_refused(self):
        self.assertEqual(cb.problems({**SPEC, "daily_budget_cents": 6100}, {"f1"}, {"t1"}, 2000),
                         [("budget", "$61.00 a day is more than 3 times what runs now ($20.00); start lower and raise it in steps")])

    def test_ad_set_problems_come_through_under_its_step(self):
        self.assertEqual(cb.problems({**SPEC, "adset": {**ADSET, "locations": []}}, {"f1"}, {"t1"}), [("adset", "Add at least one place")])

    def test_a_missing_campaign_budget_is_reported_once_under_budget_not_under_who_sees_it(self):
        for missing in (None, 0):
            self.assertEqual(cb.problems({**SPEC, "daily_budget_cents": missing}, {"f1"}, {"t1"}),
                             [("budget", "Give it a daily budget of at least $1")])

    def test_duplicate_ad_names(self):
        self.assertEqual(cb.problems({**SPEC, "ads": [AD, {**AD}]}, {"f1"}, {"t1"}), [("ads", "Two ads have the same name")])


class FieldProblemTests(unittest.TestCase):
    """9.4e: each problem also names the input it is about, so the wizard can mark that field."""
    def test_each_problem_points_at_its_input(self):
        bad = {**SPEC, "name": " ", "daily_budget_cents": 50, "form_id": "nope",
               "adset": {**ADSET, "name": "", "locations": [], "age_min": 40, "age_max": 30, "suggest_min": None, "suggest_max": None},
               "ads": [{**AD, "template_ad_id": "x", "cta_type": "SHOP_NOW", "media": {"kind": "image"}},
                       {**AD, "name": "N7", "body": "", "title": ""}, {**AD, "name": "n7"}]}
        self.assertEqual([(s, f) for s, f, _ in cb.field_problems(bad, {"f1"}, {"t1"})], [
            ("goal", "name"), ("budget", "budget"), ("adset", "adset"), ("adset", "locations"), ("adset", "age"), ("form", "form"),
            ("ads", "ad0-template"), ("ads", "ad0-cta"), ("ads", "ad0-media"), ("ads", "ad1-body"), ("ads", "ad2-name")])

    def test_a_missing_headline_points_at_the_headline_when_the_text_is_there(self):
        spec = {**SPEC, "ads": [{**AD, "title": ""}]}
        self.assertEqual(cb.field_problems(spec, {"f1"}, {"t1"}), [("ads", "ad0-title", "Ad 1: give it a name, primary text and a headline")])

    def test_from_scratch_same_media_points_at_the_media(self):
        spec = {**SPEC, "ads": [{**AD, "template_ad_id": "", "media": {"kind": "same"}}]}
        self.assertEqual([f for _, f, _ in cb.field_problems(spec, {"f1"}, set())], ["ad0-media"])

    def test_problems_without_an_input_name_none(self):
        self.assertEqual([cb.field_problems({**SPEC, "ads": []}, {"f1"}, {"t1"}), cb.field_problems({**SPEC, "ads": [AD] * 7}, {"f1"}, {"t1"})[0]],
                         [[("ads", None, "Add at least one ad")], ("ads", None, "Start with at most 6 ads")])

    def test_problems_is_the_same_list_without_the_inputs(self):
        bad = {**SPEC, "name": "", "ads": [{**AD, "title": ""}, {**AD}]}
        self.assertEqual(cb.problems(bad, {"f1"}, {"t1"}), [(s, m) for s, _, m in cb.field_problems(bad, {"f1"}, {"t1"})])


class PayloadAndOrderTests(unittest.TestCase):
    def test_the_campaign_is_a_paused_leads_campaign_with_its_budget_in_cents(self):
        self.assertEqual(cb.campaign_payload(SPEC), {"name": "EB - Payroll - Leads", "objective": "OUTCOME_LEADS", "buying_type": "AUCTION",
                                                     "special_ad_categories": [], "daily_budget": 2000,
                                                     "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "status": "PAUSED"})

    def test_a_resumed_build_only_makes_what_is_missing(self):
        self.assertEqual([cb.next_steps({}, 2), cb.next_steps({"campaign_id": "c", "adset_id": "s", "ads": {"0": "a0"}}, 3)],
                         [["campaign", "adset", "ad:0", "ad:1"], ["ad:1", "ad:2"]])

    def test_publishing_turns_the_campaign_on_last(self):
        made = {"campaign_id": "c", "adset_id": "s", "ads": {"1": "a1", "0": "a0", "10": "a10"}}
        self.assertEqual(cb.publish_order(made), [("ad", "a0"), ("ad", "a1"), ("ad", "a10"), ("adset", "s"), ("campaign", "c")])


class ReviewTests(unittest.TestCase):
    def test_review_reads_in_dollars_with_the_month(self):
        r = cb.review(SPEC, "Free intro call", {"t1": "N1 - One simple system"})
        self.assertEqual((r["campaign"], r["adset"]), (
            "EB - Payroll - Leads · Leads (Instant Form) · $20.00 a day (about $608.00 a month), lowest cost",
            "SoCal · Riverside, California + 25 mi · ages 25–65 · Advantage+ audience · Advantage+ placements"))
        self.assertEqual(r["ads"], [{"name": "N6 - Payroll", "title": "Payroll in one click", "starts_from": "N1 - One simple system",
                                     "media": "same media as that ad", "warnings": []}])

    def test_review_and_problems_use_the_account_currency(self):
        r = cb.review(SPEC, "Free intro call", {"t1": "N1 - One simple system"}, currency="EUR")
        p = cb.problems({**SPEC, "daily_budget_cents": 6100}, {"f1"}, {"t1"}, 2000, currency="EUR")
        self.assertEqual((r["campaign"], p), (
            "EB - Payroll - Leads · Leads (Instant Form) · €20.00 a day (about €608.00 a month), lowest cost",
            [("budget", "€61.00 a day is more than 3 times what runs now (€20.00); start lower and raise it in steps")]))

    def test_copy_warnings(self):
        w = cb.copy_warnings({"title": "x" * 41, "body": "Are you struggling with paperwork? " + "y" * 100})
        self.assertEqual(len(w), 3)


if __name__ == "__main__":
    unittest.main()


class FromScratchTest(unittest.TestCase):
    """Audit A17: a new account's first campaign needs no ad set or ad to copy."""
    SPEC = {"name": "C", "daily_budget_cents": 2000, "form_id": "f1",
            "adset": {"name": "S", "locations": [{"kind": "region", "key": "3847", "name": "California"}], "age_min": 25, "age_max": 65,
                      "advantage": True, "template_adset_id": ""},
            "ads": [{"name": "A", "title": "T", "body": "B", "template_ad_id": "", "cta_type": "SIGN_UP", "media": {"kind": "image", "hash": "h"}}]}

    def test_an_ad_with_its_own_media_and_no_template_is_fine(self):
        self.assertEqual(cb.problems(self.SPEC, {"f1"}, set()), [])

    def test_without_a_template_same_media_is_refused(self):
        spec = {**self.SPEC, "ads": [{**self.SPEC["ads"][0], "media": {"kind": "same"}}]}
        self.assertEqual([m for _, m in cb.problems(spec, {"f1"}, set())], ["Ad 1: choose its image or video (it doesn't start from another ad)"])


class AdoptableTest(unittest.TestCase):
    """A3-71/A3-72: after Meta didn't answer, only something this build could have made is adopted."""
    SINCE = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    def found(self, oid, created, status="PAUSED", name="EB - Payroll - Leads", parent=None):
        return {"id": oid, "name": name, "status": status, "created_time": created, "campaign_id": parent, "adset_id": parent}

    def test_only_a_paused_one_made_since_the_build_started_and_not_taken(self):
        found = [self.found("old", "2026-11-01T10:00:00+0000"), self.found("on", "2026-11-10T12:00:30+0000", status="ACTIVE"),
                 self.found("taken", "2026-11-10T12:01:00+0000"), self.found("other", "2026-11-10T12:01:00+0000", name="Other"),
                 self.found("new", "2026-11-10T12:00:05+0000"), self.found("no-time", None)]
        self.assertEqual(cb.adoptable(found, "EB - Payroll - Leads", None, self.SINCE, {"taken"}), "new")

    def test_an_ad_set_or_ad_must_be_under_the_same_parent(self):
        found = [self.found("elsewhere", "2026-11-10T12:00:05+0000", parent="p2"), self.found("here", "2026-11-10T12:00:06+0000", parent="p1")]
        self.assertEqual([cb.adoptable(found, "EB - Payroll - Leads", "p1", self.SINCE, set()),
                          cb.adoptable(found[:1], "EB - Payroll - Leads", "p1", self.SINCE, set())], ["here", None])

