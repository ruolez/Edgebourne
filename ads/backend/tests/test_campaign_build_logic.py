import unittest

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

    def test_duplicate_ad_names(self):
        self.assertEqual(cb.problems({**SPEC, "ads": [AD, {**AD}]}, {"f1"}, {"t1"}), [("ads", "Two ads have the same name")])


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
