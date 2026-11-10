import unittest

import advice as ad

# The live account's answer on 2026-11-09 (shape from the Ads MCP), plus Meta's documented sample.
LIVE = {"type": "reels_pc_recommendation", "object_ids": ["120252672227950312"], "recommendation_stage": "mid_flight_recommendation",
        "recommendation_content": {"lift_estimate": "You could get 8% lower cost per result by optimizing your Reels format",
                                   "body": "Including a fullscreen vertical video (9:16) with audio in your Reels ads can improve performance.",
                                   "opportunity_score_lift": "4"}, "url": "https://adsmanager.facebook.com/x"}
SCALE = {"type": "SCALE_GOOD_CAMPAIGN", "recommendation_signature": "s1", "object_ids": ["c1"],
         "recommendation_data": {"additional_budget": 600}, "opportunity_score_lift": "9", "recommendation_content": {"body": "b"}}


class ReadTests(unittest.TestCase):
    def test_both_shapes_flatten_to_one_list(self):
        self.assertEqual(len(ad.flatten({"data": [{"recommendations": [LIVE, SCALE]}]})), 2)
        self.assertEqual(len(ad.flatten({"data": [{"ad_account_id": "1", "recommendations": [LIVE]}]})), 1)
        self.assertEqual(ad.flatten([LIVE]), [LIVE])

    def test_the_live_reels_advice_reads_plainly_and_is_not_applied_here(self):
        r = ad.normalize(LIVE)
        self.assertEqual((r["type"], r["label"], r["points"], r["can_apply"], r["note"]),
                         ("REELS_PC_RECOMMENDATION", "Add a vertical 9:16 video for Reels", 4, False,
                          "Needs a new 9:16 video with sound; make one, then add it to the ad."))

    def test_unknown_types_are_humanized_and_a_version_suffix_dropped(self):
        self.assertEqual(ad.normalize({"type": "something_new_v2"})["label"], "Something new")


class BudgetTests(unittest.TestCase):
    def test_a_step_over_20_percent_is_marked_big(self):
        self.assertEqual(ad.normalize(SCALE, {"c1": 2000})["budget"], {"from": 2000, "add": 600, "to": 2600, "pct": 30, "big": True})

    def test_a_small_step_is_not(self):
        self.assertEqual(ad.normalize(SCALE, {"c1": 4000})["budget"]["big"], False)

    def test_without_the_current_budget_nothing_is_guessed(self):
        self.assertEqual(ad.normalize(SCALE, {})["budget"], {"from": None, "add": 600, "to": None, "pct": None, "big": None})


class RankTests(unittest.TestCase):
    def test_most_points_first_and_only_signed_known_types_apply(self):
        r = ad.ranked([LIVE, SCALE], {"c1": 2000})
        self.assertEqual([(x["type"], x["can_apply"]) for x in r], [("SCALE_GOOD_CAMPAIGN", True), ("REELS_PC_RECOMMENDATION", False)])
        self.assertEqual(ad.extra_data(r[0]), {"object_selection": "c1"})


if __name__ == "__main__":
    unittest.main()
