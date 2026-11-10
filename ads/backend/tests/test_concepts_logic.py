import unittest

import concepts as c


def ad(i, spend, leads, imp=1000, v3=300, thru=60, q=0):
    return {"id": i, "spend_cents": spend, "leads": leads, "impressions": imp, "video_3s": v3, "thruplays": thru, "qualified": q}


ADS = [ad("n1", 2600, 5), ad("n2", 2900, 6, q=1), ad("n3", 3000, 5), ad("n4", 2800, 4), ad("n5", 3000, 7), ad("x", 500, 0)]
TAGS = {"n1": {"hook": "Statement of pain"}, "n2": {"hook": "Outcome promise"}, "n3": {"hook": "Command"},
        "n4": {"hook": "Question"}, "n5": {"hook": "Outcome promise"}}


class GroupTests(unittest.TestCase):
    def test_values_are_summed_and_the_cheapest_judged_group_is_marked(self):
        r = c.group(ADS, TAGS, "hook", target_cents=500)
        rows = [(g["value"], g["ads"], g["spend_cents"], g["leads"], g["cpl_cents"], g["enough"], g["best"]) for g in r["groups"]]
        self.assertEqual(rows, [
            ("Outcome promise", 2, 5900, 13, 454, True, True),
            ("Statement of pain", 1, 2600, 5, 520, True, False),
            ("Command", 1, 3000, 5, 600, True, False),
            ("Question", 1, 2800, 4, 700, True, False),
            ("Not tagged", 1, 500, 0, None, False, False)])

    def test_the_cheapest_group_says_how_sure_it_is(self):
        r = c.group(ADS, TAGS, "hook", target_cents=500)
        # 13 leads on $59 vs 5 on $26: rates per dollar nearly equal, so far from sure
        self.assertEqual((r["best"], r["best_is_clear"], r["best_confidence"] < 50), ("Outcome promise", False, True))

    def test_rates_are_shares_of_the_right_base(self):
        g = c.group([ad("a", 1000, 4, imp=2000, v3=500, thru=100, q=1)], {"a": {"hook": "Q"}}, "hook")["groups"][0]
        self.assertEqual((g["hook_rate"], g["hold_rate"], g["qualified_rate"]), (0.25, 0.2, 0.25))

    def test_without_a_target_the_average_cost_sets_the_spend_bar(self):
        # 17 leads on $140 → $8.24 a lead → a group needs $16.47 and 3 leads
        r = c.group([ad("a", 1500, 3), ad("b", 12500, 14)], {"a": {"angle": "A"}, "b": {"angle": "B"}}, "angle")
        self.assertEqual((r["target_cents"], [(g["value"], g["enough"]) for g in r["groups"]], r["best"]), (824, [("B", True), ("A", False)], None))

    def test_one_judged_group_is_not_called_best(self):
        r = c.group([ad("a", 5000, 9), ad("b", 100, 0)], {"a": {"offer": "Call"}, "b": {"offer": "Guide"}}, "offer", 500)
        self.assertEqual(r["best"], None)


class MergeTests(unittest.TestCase):
    def test_unchanged_after_tidying_is_skipped_new_is_added_empty_removes(self):
        up, down = c.merge({"hook": "Question", "angle": "Reports"}, {"hook": "  question  ", "angle": "", "persona": "ops managers", "bogus": "x"}, "manual")
        self.assertEqual((up, down), ([("persona", "Ops managers", "manual")], ["angle"]))


if __name__ == "__main__":
    unittest.main()
