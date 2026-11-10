import unittest

import experiments as ex


def arm(label, spend=0, leads=0, impressions=0, clicks=0, views=0, qualified=0):
    return {"label": label, "spend_cents": spend, "leads": leads, "impressions": impressions,
            "link_clicks": clicks, "video_3s": views, "qualified": qualified}


class ConfidenceTests(unittest.TestCase):
    def test_equal_spend_and_equal_leads_means_no_evidence_of_a_difference(self):
        self.assertEqual(ex.confidence("cpl", arm("A", 10000, 10), arm("B", 10000, 10)), 0)

    def test_a_lopsided_lead_split_on_equal_spend_is_near_certain(self):
        # 20 leads vs 4 on the same spend: exact binomial two-sided p ≈ 0.0015
        self.assertEqual(ex.confidence("cpl", arm("A", 10000, 20), arm("B", 10000, 4)), 99)

    def test_spend_is_the_exposure_so_twice_the_spend_for_twice_the_leads_is_even(self):
        self.assertEqual(ex.confidence("cpl", arm("A", 20000, 12), arm("B", 10000, 6)), 0)

    def test_click_rate_uses_a_two_proportion_test(self):
        # 2.0% vs 1.0% on 5,000 impressions each: z ≈ 4.04
        self.assertEqual(ex.confidence("ctr", arm("A", impressions=5000, clicks=100), arm("B", impressions=5000, clicks=50)), 99)


class JudgeTests(unittest.TestCase):
    def test_too_early_names_what_each_arm_still_needs(self):
        j = ex.judge("cpl", [arm("A", 3000, 2), arm("B", 9000, 3)], target_cents=2000, days_run=5)
        self.assertEqual((j["state"], j["needs"]), ("early", {"A": "$10 more spend and 1 more lead"}))

    def test_nothing_is_judged_before_three_full_days(self):
        j = ex.judge("cpl", [arm("A", 10000, 20), arm("B", 10000, 4)], target_cents=1000, days_run=2)
        self.assertEqual((j["state"], j["note"].startswith("Too early to call: it needs 1 more full day")), ("early", True))

    def test_a_clear_difference_with_enough_data_calls_the_cheaper_arm_the_winner(self):
        j = ex.judge("cpl", [arm("A", 10000, 4), arm("B", 10000, 20)], target_cents=1000, days_run=7)
        self.assertEqual((j["state"], j["leader"], j["diff_pct"], j["note"]), ("winner", "B", 80, "B wins: 80% cheaper, 99% sure."))

    def test_a_small_difference_is_not_called(self):
        j = ex.judge("cpl", [arm("A", 10000, 10), arm("B", 10000, 12)], target_cents=1000, days_run=7)
        self.assertEqual((j["state"], j["leader"], j["note"]),
                         ("even", "B", "No clear difference yet: B is 17% cheaper so far, which could easily be chance."))

    def test_without_a_target_the_pooled_cost_sets_the_spend_bar(self):
        # pooled $50 a lead → each arm needs $100 spent
        j = ex.judge("cpl", [arm("A", 6000, 1), arm("B", 14000, 3)], days_run=7)
        self.assertEqual((j["target_cents"], j["needs"]), (5000, {"A": "$40 more spend and 2 more leads"}))

    def test_an_arm_without_leads_ranks_last_on_cost(self):
        j = ex.judge("cpl", [arm("A", 20000, 0), arm("B", 20000, 9)], target_cents=2000, days_run=7)
        self.assertEqual((j["leader"], j["runner_up"], j["needs"]), ("B", "A", {"A": "3 more leads"}))

    def test_rates_rank_the_higher_share_first(self):
        j = ex.judge("hook", [arm("A", impressions=4000, views=800), arm("B", impressions=4000, views=1200)], days_run=7)
        self.assertEqual((j["state"], j["leader"], j["diff_pct"]), ("winner", "B", 50))

    def test_one_arm_cannot_be_compared(self):
        self.assertEqual(ex.judge("cpl", [arm("A", 1000, 1)], days_run=7)["note"], "Add a second arm to compare.")


if __name__ == "__main__":
    unittest.main()
