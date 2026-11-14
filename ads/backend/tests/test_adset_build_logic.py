import unittest

import adset_build as ab

# The live ad set as Meta's API returned it on 2026-11-09 (pins trimmed to two).
LIVE = {"id": "120252672227950312", "optimization_goal": "LEAD_GENERATION", "billing_event": "IMPRESSIONS",
        "destination_type": "ON_AD", "promoted_object": {"pixel_id": None},
        "targeting": {"age_min": 25, "age_max": 65, "age_range": {"0": 30, "1": 64},
                      "geo_locations": {"custom_locations": [
                          {"latitude": 32.7157, "longitude": -117.1611, "radius": 50, "distance_unit": "mile", "primary_city_id": 2421830},
                          {"latitude": 33.9533, "longitude": -117.3962, "radius": 50, "distance_unit": "mile"}],
                          "location_types": ["home", "recent"]},
                      "flexible_spec": [{"interests": [{"id": 6003371567474, "name": "Entrepreneurship"}],
                                         "behaviors": [{"id": 6002714898572, "name": "Small business owners"}]}],
                      "targeting_automation": {"advantage_audience": 1}}}
CBO = {"id": "c1", "daily_budget_cents": 2000}
ABO = {"id": "c2", "daily_budget_cents": None}


class SpecFromTests(unittest.TestCase):
    def test_the_live_ad_set_becomes_builder_defaults(self):
        s = ab.spec_from(LIVE)
        self.assertEqual(s, {"locations": [
            {"kind": "pin", "latitude": 32.7157, "longitude": -117.1611, "radius": 50, "name": None, "city_id": "2421830"},
            {"kind": "pin", "latitude": 33.9533, "longitude": -117.3962, "radius": 50, "name": None}],
            "age_min": 25, "age_max": 65, "suggest_min": 30, "suggest_max": 64, "advantage": True,
            "hints": ["Entrepreneurship", "Small business owners"], "keep_hints": True})


class PayloadTests(unittest.TestCase):
    def spec(self, **kw):
        return {**ab.spec_from(LIVE), "name": "Inland Empire", **kw}

    def test_a_copy_of_the_live_ad_set_in_a_campaign_budget_campaign_is_paused_with_no_budget(self):
        p = ab.payload(self.spec(), LIVE, CBO, "1404203629446490")
        self.assertEqual({k: p[k] for k in p if k != "targeting"}, {
            "name": "Inland Empire", "campaign_id": "c1", "status": "PAUSED", "optimization_goal": "LEAD_GENERATION",
            "billing_event": "IMPRESSIONS", "destination_type": "ON_AD", "promoted_object": {"page_id": "1404203629446490"}})
        self.assertEqual(p["targeting"], {
            "geo_locations": {"location_types": ["home", "recent"], "custom_locations": [
                {"latitude": 32.7157, "longitude": -117.1611, "radius": 50, "distance_unit": "mile"},
                {"latitude": 33.9533, "longitude": -117.3962, "radius": 50, "distance_unit": "mile"}]},
            "age_min": 25, "age_max": 65, "targeting_automation": {"advantage_audience": 1}, "age_range": [30, 64],
            "flexible_spec": [{"interests": [{"id": "6003371567474", "name": "Entrepreneurship"}],
                               "behaviors": [{"id": "6002714898572", "name": "Small business owners"}]}]})

    def test_an_ad_set_budget_campaign_needs_a_budget_and_bid_strategy(self):
        p = ab.payload(self.spec(daily_budget_cents=1500), LIVE, ABO, "p")
        self.assertEqual((p["daily_budget"], p["bid_strategy"]), (1500, "LOWEST_COST_WITHOUT_CAP"))

    def test_cities_regions_and_zips_and_no_hints(self):
        locs = [{"kind": "city", "key": "2421696", "name": "Riverside, CA", "radius": 25}, {"kind": "region", "key": "3847", "name": "California"},
                {"kind": "zip", "key": "US:92335", "name": "92335"}]
        t = ab.targeting({**self.spec(), "locations": locs, "keep_hints": False, "advantage": False})
        self.assertEqual(t, {"geo_locations": {"location_types": ["home", "recent"],
                                               "cities": [{"key": "2421696", "radius": 25, "distance_unit": "mile"}],
                                               "regions": [{"key": "3847"}], "zips": [{"key": "US:92335"}]},
                             "age_min": 25, "age_max": 65, "targeting_automation": {"advantage_audience": 0}})


class DraftHintTests(unittest.TestCase):
    """AM-B: an Ads Manager draft's audience hints (spec flexible_spec) only apply when the ad set starts from scratch."""
    DRAFT_HINTS = [{"interests": [{"id": "6003", "name": "Entrepreneurship"}]}]

    def spec(self):
        return {**ab.spec_from(LIVE), "keep_hints": True, "flexible_spec": self.DRAFT_HINTS}

    def test_from_scratch_the_draft_hints_are_sent(self):
        self.assertEqual(ab.targeting(self.spec(), None)["flexible_spec"], [{"interests": [{"id": "6003", "name": "Entrepreneurship"}]}])

    def test_a_template_without_hints_never_borrows_the_draft_hints(self):
        no_hints = {k: v for k, v in LIVE["targeting"].items() if k != "flexible_spec"}
        self.assertNotIn("flexible_spec", ab.targeting(self.spec(), no_hints))

    def test_a_template_with_hints_keeps_its_own(self):
        self.assertEqual(ab.targeting(self.spec(), LIVE["targeting"])["flexible_spec"],
                         [{"interests": [{"id": "6003371567474", "name": "Entrepreneurship"}],
                           "behaviors": [{"id": "6002714898572", "name": "Small business owners"}]}])


class ProblemTests(unittest.TestCase):
    def test_the_live_copy_has_no_problems(self):
        self.assertEqual(ab.problems({**ab.spec_from(LIVE), "name": "x"}, 2000), [])

    def test_each_problem_names_its_field(self):
        bad = {"name": "", "locations": [{"kind": "city", "key": "1", "name": "Fontana", "radius": 5}], "age_min": 30, "age_max": 65,
               "advantage": True, "suggest_min": 35, "suggest_max": 64, "start": "2026-11-12T06:00:00-08:00", "end": "2026-11-11T06:00:00-08:00"}
        self.assertEqual(ab.problems(bad, None), [
            ("name", "Give the ad set a name"), ("locations", "Fontana: the radius has to be 10 to 50 miles"),
            ("age", "With Advantage+ audience the minimum age can be at most 25; use the suggested ages for older people"),
            ("end", "The end has to come after the start"),
            ("budget", "Give it a daily budget of at least $1 (the campaign has no budget of its own)")])

    def test_suggested_ages_must_sit_inside_the_limits_and_somewhere_to_show_is_required(self):
        s = {"name": "x", "locations": [], "age_min": 18, "age_max": 50, "advantage": True, "suggest_min": 30, "suggest_max": 60}
        self.assertEqual(ab.problems(s, 2000), [("locations", "Add at least one place"), ("age", "The suggested ages have to sit inside the age limits")])

    def test_local_start_time_in_the_account_zone(self):
        self.assertEqual(ab.iso_local("2026-11-12", 6, "America/Los_Angeles"), "2026-11-12T06:00:00-08:00")


if __name__ == "__main__":
    unittest.main()
