import unittest

import compare


def m(spend, leads, qualified=0, impressions=4000, reach=2800, clicks=44, v3=1200, thru=300, video_impressions=None):
    return {"spend_cents": spend, "leads": leads, "qualified": qualified, "impressions": impressions, "reach": reach,
            "link_clicks": clicks, "video_3s": v3, "thruplays": thru,
            "video_impressions": impressions if video_impressions is None else video_impressions}


class RatesTests(unittest.TestCase):
    def test_rates_from_totals(self):
        r = compare.rates(m(4645, 11, 3, impressions=4084, reach=2900, clicks=44, v3=1213, thru=400))
        self.assertEqual((r["cpl_cents"], r["cpq_cents"], round(r["ctr"], 4), round(r["hook"], 4), round(r["frequency"], 2), r["cpm_cents"]),
                         (422, 1548, 0.0108, 0.297, 1.41, 1137))

    def test_hook_rate_counts_only_video_impressions_and_images_have_none(self):
        mixed, image = m(1000, 1, impressions=8000, v3=1200, video_impressions=4000), m(1000, 1, impressions=4000, v3=0, thru=0, video_impressions=0)
        self.assertEqual((compare.rates(mixed)["hook"], compare.rates(image)["hook"]), (0.3, None))

    def test_hold_is_labelled_hold_rate_like_the_video_tab(self):
        # The Video tab's "Watched to the end" is a different number (p100 ÷ impressions; audit A3-39).
        self.assertEqual({k: label for k, label, _ in compare.ROWS}["hold"], "Hold rate")

    def test_no_leads_means_no_cost_per_lead(self):
        self.assertEqual(compare.rates(m(500, 0))["cpl_cents"], None)


class ShapeTests(unittest.TestCase):
    def items(self, spends):
        return [{"id": f"a{i}", "m": m(s, l, q)} for i, (s, l, q) in enumerate(spends)]

    def test_best_per_row_respects_direction(self):
        out = compare.shape(self.items([(4645, 11, 3), (5017, 10, 2), (5100, 9, 2)]), target_cents=6000)
        rows = {r["key"]: r["best"] for r in out["rows"]}
        self.assertEqual((rows["cpl_cents"], rows["leads"], rows["spend_cents"]), (0, 0, None))

    def test_too_early_until_every_ad_has_twice_the_target_and_three_results(self):
        out = compare.shape(self.items([(4645, 11, 3), (5017, 10, 2)]), target_cents=6000)
        self.assertEqual((out["verdict"]["ready"], out["verdict"]["need_spend_cents"]), (False, 12000))

    def test_ready_names_the_leader_on_cost_per_qualified_lead(self):
        out = compare.shape(self.items([(13000, 30, 4), (12500, 25, 3)]), target_cents=6000)
        self.assertEqual((out["verdict"]["ready"], out["verdict"]["leader"], out["verdict"]["metric"]), (True, "a0", "cpq_cents"))

    def test_without_qualified_target_judges_on_cost_per_lead_with_three_leads(self):
        out = compare.shape(self.items([(3000, 3, 0), (3000, 6, 0)]), target_cents=None, lead_target_cents=1000)
        self.assertEqual((out["verdict"]["ready"], out["verdict"]["leader"], out["verdict"]["metric"]), (True, "a1", "cpl_cents"))

    def test_ties_mark_no_best(self):
        out = compare.shape(self.items([(1000, 2, 0), (1000, 2, 0)]), target_cents=6000)
        self.assertEqual({r["key"]: r["best"] for r in out["rows"]}["leads"], None)

    def test_change_vs_previous_window(self):
        items = [{"id": "a", "m": m(4645, 11, 3), "prev": m(4382, 8, 2)}]
        row = next(r for r in compare.shape(items, target_cents=6000)["rows"] if r["key"] == "leads")
        self.assertEqual(row["cells"][0]["delta_pct"], 38)


if __name__ == "__main__":
    unittest.main()
