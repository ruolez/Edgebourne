"""AM-C: editing campaigns and ad sets after they are made (edit_rules, pure)."""
import json
import unittest
from datetime import datetime, timedelta, timezone

import edit_rules as er
import status_history as sh

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)
START = "2026-11-03T09:00:00-0800"
PINS = [{"latitude": 33.9533, "longitude": -117.3962, "radius": 50, "distance_unit": "mile", "primary_city_id": 2421696}]
META_ADSET = {
    "id": "S1", "name": "SoCal owners", "status": "ACTIVE", "campaign_id": "C1", "optimization_goal": "LEAD_GENERATION",
    "destination_type": "ON_AD", "billing_event": "IMPRESSIONS", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "start_time": START,
    "attribution_spec": [{"event_type": "CLICK_THROUGH", "window_days": 7}, {"event_type": "VIEW_THROUGH", "window_days": 1}],
    "targeting": {"age_min": 25, "age_max": 65, "age_range": [30, 64],
                  "geo_locations": {"custom_locations": PINS, "location_types": ["home", "recent"]},
                  "flexible_spec": [{"interests": [{"id": "6003371567474", "name": "Entrepreneurship"}],
                                     "behaviors": [{"id": "6002714898572", "name": "Small business owners"}]}],
                  "targeting_automation": {"advantage_audience": 1}, "targeting_relaxation_types": {"lookalike": 1}},
}
META_CAMPAIGN = {"id": "C1", "name": "Free intro call", "status": "ACTIVE", "objective": "OUTCOME_LEADS", "daily_budget": "2000",
                 "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "special_ad_categories": [], "start_time": START}
CBO = {"daily_budget": 2000, "lifetime_budget": None, "bid_strategy": "LOWEST_COST_WITHOUT_CAP"}


def adset(**over):
    return {**er.current("adset", META_ADSET), **over}


def campaign(**over):
    return {**er.current("campaign", META_CAMPAIGN), **over}


def ctx(**over):
    return {"delivered": True, "now": NOW, "campaign": CBO, "special": [], "adsets": [], **over}


def fields(chs):
    return [c["field"] for c in chs]


class CurrentTests(unittest.TestCase):
    def test_an_ad_set_reads_in_the_forms_words(self):
        live = adset()
        t = live["targeting"]
        self.assertEqual((live["name"], live["start_time"], live["end_time"], live["bid_amount"], live["placements"],
                          live["attribution_spec"], live["frequency_control_specs"], t["age_min"], t["age_max"], t["advantage"],
                          t["suggest_min"], t["genders"], [(i["type"], i["id"]) for i in t["include"]], len(t["locations"])),
                         ("SoCal owners", "2026-11-03T17:00Z", None, None, {"auto": True}, "7d_click_1d_view", None, 25, 65, True,
                          30, [], [("behaviors", "6002714898572"), ("interests", "6003371567474")], 1))

    def test_a_campaign_spend_cap_at_metas_no_cap_value_is_none(self):
        self.assertEqual([campaign()["spend_cap"], er.current("campaign", {**META_CAMPAIGN, "spend_cap": "922337203685478"})["spend_cap"],
                          er.current("campaign", {**META_CAMPAIGN, "spend_cap": "50000"})["spend_cap"]], [None, None, 50000])

    def test_manual_placements_read_as_platforms_and_positions(self):
        meta = {**META_ADSET, "targeting": {**META_ADSET["targeting"], "publisher_platforms": ["instagram", "facebook"],
                                            "instagram_positions": ["story", "stream"]}}
        self.assertEqual(er.current("adset", meta)["placements"],
                         {"auto": False, "platforms": ["facebook", "instagram"], "facebook_positions": [], "instagram_positions": ["story", "stream"]})


class EditableTests(unittest.TestCase):
    GOALS = ("optimization_goal", "destination_type", "attribution_spec", "billing_event")

    def test_goal_fields_only_while_the_ad_set_never_delivered(self):
        never = er.editable("adset", adset(), ctx(delivered=False))
        ran = er.editable("adset", adset(), ctx(delivered=True))
        self.assertEqual(([never[f] for f in self.GOALS], [bool(ran[f]) and "after the ad set has delivered" in ran[f] for f in self.GOALS]),
                         ([None] * 4, [True] * 4))

    def test_campaign_objective_never_spend_cap_always_stop_time_only_with_a_lifetime_budget(self):
        daily = er.editable("campaign", campaign(), ctx())
        lifetime = er.editable("campaign", campaign(daily_budget=None, lifetime_budget=30000), ctx())
        self.assertEqual((bool(daily["objective"]), daily["spend_cap"], bool(daily["stop_time"]), lifetime["stop_time"]),
                         (True, None, True, None))

    def test_a_start_that_has_passed_cant_move_and_bidding_follows_the_budget(self):
        later = adset(start_time="2026-11-20T17:00Z")
        e = er.editable("adset", adset(), ctx())
        self.assertEqual((bool(e["start_time"]), er.editable("adset", later, ctx())["start_time"], bool(e["bid_strategy"]),
                          er.editable("adset", adset(), ctx(campaign={**CBO, "daily_budget": None}))["bid_strategy"]),
                         (True, None, True, None))

    def test_frequency_only_for_reach_goals(self):
        self.assertEqual((bool(er.editable("adset", adset(), ctx())["frequency_control_specs"]),
                          er.editable("adset", adset(optimization_goal="REACH"), ctx())["frequency_control_specs"]), (True, None))


class ChangesTests(unittest.TestCase):
    def test_the_same_targeting_in_another_order_is_no_change(self):
        live = adset()
        t = json.loads(json.dumps(live["targeting"]))
        t["include"].reverse()
        t["genders"] = []
        self.assertEqual(er.changes("adset", live, {"targeting": t}), [])

    def test_cents_as_strings_and_a_time_in_another_zone_are_no_change(self):
        live = adset(bid_amount=1200, end_time="2026-12-01T07:59Z")
        self.assertEqual(er.changes("adset", live, {"bid_amount": "1200", "end_time": "2026-11-30T23:59:00-0800"}), [])

    def test_only_real_differences_named_once(self):
        live = adset()
        t = {**live["targeting"], "age_min": 30}
        self.assertEqual(fields(er.changes("adset", live, {"name": "SoCal owners", "targeting": t, "bogus": 1})), ["targeting"])

    def test_a_pins_display_name_is_no_change(self):
        live = adset()
        t = json.loads(json.dumps(live["targeting"]))
        t["locations"][0]["name"] = "Riverside area"
        self.assertEqual(er.changes("adset", live, {"targeting": t}), [])


class ProblemsTests(unittest.TestCase):
    def p(self, level, live, wanted, c=None):
        return er.problems(level, live, er.changes(level, live, wanted), c or ctx())

    def test_end_before_start(self):
        live = adset(start_time="2026-11-20T17:00Z")
        self.assertEqual([f for f, _ in self.p("adset", live, {"end_time": "2026-11-19T17:00Z"})], ["end_time"])

    def test_an_end_in_the_past(self):
        self.assertEqual([f for f, _ in self.p("adset", adset(), {"end_time": "2026-11-12T17:00Z"})], ["end_time"])

    def test_a_lifetime_budget_needs_an_end(self):
        live = adset(lifetime_budget=30000, end_time="2026-11-30T17:00Z")
        c = ctx(campaign={**CBO, "daily_budget": None})
        self.assertEqual([f for f, _ in self.p("adset", live, {"end_time": None}, c)], ["end_time"])

    def test_advantage_audience_minimum_age_at_most_25(self):
        live = adset()
        found = self.p("adset", live, {"targeting": {**live["targeting"], "age_min": 30}})
        self.assertEqual([(f, "at most 25" in m) for f, m in found], [("targeting", True)])

    def test_ages_30_to_65_without_advantage_audience_are_fine(self):
        live = adset()
        self.assertEqual(self.p("adset", live, {"targeting": {**live["targeting"], "age_min": 30, "advantage": False}}), [])

    def test_a_radius_outside_metas_range(self):
        live = adset()
        t = json.loads(json.dumps(live["targeting"]))
        t["locations"][0]["radius"] = 60
        self.assertEqual([(f, "1 to 50 miles" in m) for f, m in self.p("adset", live, {"targeting": t})], [("targeting", True)])

    def test_manual_placements_need_at_least_one_place(self):
        self.assertEqual([f for f, _ in self.p("adset", adset(), {"placements": {"auto": False, "platforms": []}})], ["placements"])

    def test_a_goal_after_delivery_is_refused(self):
        self.assertEqual([f for f, _ in self.p("adset", adset(), {"optimization_goal": "QUALITY_LEAD"})], ["optimization_goal"])

    def test_a_bid_amount_without_a_capped_strategy(self):
        self.assertEqual([f for f, _ in self.p("adset", adset(), {"bid_amount": 1500})], ["bid_amount"])

    def test_a_bid_amount_under_the_campaigns_cost_cap_is_fine(self):
        c = ctx(campaign={**CBO, "bid_strategy": "COST_CAP"})
        self.assertEqual(self.p("adset", adset(), {"bid_amount": 1500}, c), [])

    def test_a_cost_cap_on_the_campaign_needs_every_ad_sets_amount(self):
        c = ctx(adsets=[{"id": "S1", "name": "SoCal owners", "bid_amount": None}, {"id": "S2", "name": "LA", "bid_amount": None}])
        found = self.p("campaign", campaign(), {"bid_strategy": "COST_CAP", "adset_bids": {"S1": 1200}}, c)
        self.assertEqual([(f, "LA" in m) for f, m in found], [("adset_bids", True)])

    def test_a_goal_for_an_ad_set_outside_the_campaign_is_refused(self):
        c = ctx(adsets=[{"id": "S1", "name": "SoCal owners", "bid_amount": 1200}])
        live = campaign(bid_strategy="COST_CAP", adset_bids={"S1": 1200})
        found = self.p("campaign", live, {"adset_bids": {"S1": 1300, "999FOREIGN": 19900}}, c)
        self.assertEqual([(f, "999FOREIGN" in m) for f, m in found], [("adset_bids", True)])

    def test_custom_audiences_cant_change_here_yet(self):
        live = adset()
        added = {**live["targeting"], "custom_audiences": [{"id": "777"}]}
        excluded = {**live["targeting"], "excluded_custom_audiences": [{"id": "778"}]}
        self.assertEqual([[f for f, _ in self.p("adset", live, {"targeting": added})], [f for f, _ in self.p("adset", live, {"targeting": excluded})],
                          self.p("adset", live, {"targeting": {**live["targeting"], "age_min": 30, "advantage": False}})],
                         [["targeting"], ["targeting"], []])

    def test_the_lookalike_rule_reads_metas_audiences_not_the_forms(self):
        meta = {**META_ADSET, "targeting": {**META_ADSET["targeting"], "age_min": 18, "age_range": None, "flexible_spec": [],
                                            "targeting_automation": {"advantage_audience": 0},
                                            "custom_audiences": [{"id": "9", "name": "Similar people", "subtype": "LOOKALIKE"}]}}
        meta["targeting"]["geo_locations"] = {"custom_locations": PINS}
        live = er.current("adset", meta)
        stripped = {**live["targeting"], "age_max": 64, "custom_audiences": [{"id": "9"}]}
        found = self.p("adset", live, {"targeting": stripped}, ctx(special=["HOUSING"]))
        self.assertEqual(sum("lookalike" in m for _, m in found), 1)

    def test_frequency_outside_reach_goals(self):
        self.assertEqual([f for f, _ in self.p("adset", adset(), {"frequency_control_specs": {"max": 2, "days": 7}})],
                         ["frequency_control_specs"])

    def test_removing_a_special_category_is_ads_managers(self):
        self.assertEqual([f for f, _ in self.p("campaign", campaign(special_ad_categories=["HOUSING"]), {"special_ad_categories": []})],
                         ["special_ad_categories"])


class SpecialCategoryTests(unittest.TestCase):
    def audience(self, **over):
        t = {**adset()["targeting"], "age_min": 18, "age_max": 65, "advantage": False, "include": [], **over}
        return {"id": "S1", "name": "SoCal owners", "targeting": t}

    def found(self, a):
        live = campaign()
        return [m for _, m in er.problems("campaign", live, er.changes("campaign", live, {"special_ad_categories": ["HOUSING"]}),
                                          ctx(adsets=[a]))]

    def test_a_compliant_audience_passes(self):
        self.assertEqual(self.found(self.audience()), [])

    def test_a_ten_mile_radius_ages_25_65_and_a_lookalike_each_have_a_message(self):
        small = self.audience()
        small["targeting"]["locations"] = [{**small["targeting"]["locations"][0], "radius": 10}]
        look = self.audience(custom_audiences=[{"id": "9", "name": "Lookalike (US, 1%)", "subtype": "LOOKALIKE"}])
        self.assertEqual([len(self.found(small)), len(self.found(self.audience(age_min=25))), len(self.found(look))], [1, 1, 1])

    def test_an_ad_set_edit_in_a_special_campaign_keeps_the_rules(self):
        live = adset()
        t = {**live["targeting"], "age_min": 25, "advantage": False, "include": []}
        found = er.problems("adset", live, er.changes("adset", live, {"targeting": t}), ctx(special=["EMPLOYMENT"]))
        self.assertEqual([f for f, _ in found], ["targeting"])


class MetaParamsTests(unittest.TestCase):
    def test_targeting_and_name_only_targeting_as_json(self):
        live = adset()
        chs = er.changes("adset", live, {"name": "SoCal 30+", "targeting": {**live["targeting"], "age_min": 30, "advantage": False}})
        out = er.meta_params("adset", chs, META_ADSET["targeting"])
        sent = json.loads(out["targeting"])
        self.assertEqual((sorted(out), out["name"], sent["age_min"], sent["targeting_automation"], sent["geo_locations"]["location_types"],
                          sent["targeting_relaxation_types"], "age_range" in sent),
                         (["name", "targeting"], "SoCal 30+", 30, {"advantage_audience": 0}, ["home", "recent"], {"lookalike": 1}, False))

    def test_placements_go_inside_targeting_with_the_audience_kept(self):
        chs = er.changes("adset", adset(), {"placements": {"auto": False, "platforms": ["instagram"]}})
        sent = json.loads(er.meta_params("adset", chs, META_ADSET["targeting"])["targeting"])
        self.assertEqual((sent["publisher_platforms"], sent["age_min"], sent["flexible_spec"] == META_ADSET["targeting"]["flexible_spec"]),
                         (["instagram"], 25, True))

    def test_advantage_placements_drop_every_placement_key(self):
        manual = {**META_ADSET["targeting"], "publisher_platforms": ["instagram"], "instagram_positions": ["stream"]}
        live = er.current("adset", {**META_ADSET, "targeting": manual})
        sent = json.loads(er.meta_params("adset", er.changes("adset", live, {"placements": {"auto": True}}), manual)["targeting"])
        self.assertEqual([k for k in ("publisher_platforms", "instagram_positions") if k in sent], [])

    def test_no_end_date_is_zero_and_times_are_metas(self):
        chs = er.changes("adset", adset(end_time="2026-12-01T07:59Z"), {"end_time": None})
        later = er.changes("adset", adset(), {"end_time": "2026-12-01T07:59Z"})
        self.assertEqual([er.meta_params("adset", chs), er.meta_params("adset", later)],
                         [{"end_time": "0"}, {"end_time": "2026-12-01T07:59:00+0000"}])

    def test_removing_the_campaign_cap_uses_metas_no_cap_value(self):
        chs = er.changes("campaign", campaign(spend_cap=50000), {"spend_cap": None})
        self.assertEqual(er.meta_params("campaign", chs), {"spend_cap": er.NO_SPEND_CAP})

    def test_attribution_and_frequency_are_metas_lists(self):
        live = adset(optimization_goal="REACH")
        chs = er.changes("adset", live, {"attribution_spec": "1d_click", "frequency_control_specs": {"max": 2, "days": 7}})
        out = er.meta_params("adset", chs)
        self.assertEqual((json.loads(out["attribution_spec"]), json.loads(out["frequency_control_specs"])),
                         ([{"event_type": "CLICK_THROUGH", "window_days": 1}], [{"event": "IMPRESSIONS", "interval_days": 7, "max_frequency": 2}]))


class ReadbackTests(unittest.TestCase):
    def test_meta_kept_another_age(self):
        live = adset()
        chs = er.changes("adset", live, {"name": "New", "targeting": {**live["targeting"], "age_min": 20}})
        fresh = adset(name="New", targeting={**live["targeting"], "age_min": 21})
        self.assertEqual(er.readback_ok(chs, fresh), ["targeting"])

    def test_what_was_sent_reads_back(self):
        live = adset()
        chs = er.changes("adset", live, {"bid_strategy": "COST_CAP", "bid_amount": 1200})
        self.assertEqual(er.readback_ok(chs, adset(bid_strategy="COST_CAP", bid_amount="1200")), [])


class MoneyTests(unittest.TestCase):
    MCTX = {"cap": 10000, "target_cpl": 1500, "spent": 9000, "last_bid": {}, "last_budget": None, "now": NOW}

    def codes(self, level, live, wanted, **over):
        return [(q["field"], q["code"]) for q in er.money(level, live, er.changes(level, live, wanted), {**self.MCTX, **over})]

    def test_a_bid_raise_over_twenty_percent_is_a_knowing_yes(self):
        self.assertEqual(self.codes("adset", adset(bid_strategy="COST_CAP", bid_amount=1200), {"bid_amount": 1500}), [("bid_amount", "big")])

    def test_a_bid_above_the_ceiling_is_refused(self):
        self.assertEqual(self.codes("adset", adset(bid_strategy="COST_CAP", bid_amount=9000), {"bid_amount": 10500}),
                         [("bid_amount", "refused")])

    def test_removing_a_cap_is_a_big_raise(self):
        self.assertEqual(self.codes("adset", adset(bid_strategy="COST_CAP", bid_amount=1200), {"bid_strategy": "LOWEST_COST_WITHOUT_CAP"}),
                         [("bid_strategy", "big")])

    def test_a_new_cost_cap_on_the_campaigns_ad_sets(self):
        live = campaign()
        self.assertEqual(self.codes("campaign", live, {"bid_strategy": "COST_CAP", "adset_bids": {"S1": 5000}}), [("adset_bids", "high")])

    def test_a_spend_cap_below_spent_is_refused_and_removal_is_danger(self):
        self.assertEqual([self.codes("campaign", campaign(spend_cap=20000), {"spend_cap": 8000}),
                          self.codes("campaign", campaign(spend_cap=20000), {"spend_cap": None}),
                          self.codes("campaign", campaign(spend_cap=20000), {"spend_cap": 22000})],
                         [[("spend_cap", "refused")], [("spend_cap", "danger")], []])

    def test_an_earlier_end_with_a_lifetime_budget_raises_the_pace(self):
        live = adset(lifetime_budget=30000, end_time=(NOW + timedelta(days=10)).strftime("%Y-%m-%dT%H:%MZ"))
        self.assertEqual(self.codes("adset", live, {"end_time": (NOW + timedelta(days=5)).strftime("%Y-%m-%dT%H:%MZ")}, spent=10000),
                         [("end_time", "big")])

    def test_an_earlier_start_on_an_ad_set_that_is_on_asks_for_the_spend(self):
        live = adset(start_time="2026-11-20T17:00Z", status="ACTIVE")
        self.assertEqual(self.codes("adset", live, {"start_time": "2026-11-15T17:00Z"}), [("start_time", "spend")])

    def test_a_new_end_on_an_ended_ad_set_asks_for_the_spend(self):
        ended = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ")
        self.assertEqual([self.codes("adset", adset(end_time=ended, status="ACTIVE"), {"end_time": None}),
                          self.codes("adset", adset(end_time=ended, status="PAUSED"), {"end_time": None})],
                         [[("end_time", "spend")], []])

    def test_extending_an_ended_lifetime_campaign_past_the_ceiling_is_refused(self):
        live = campaign(daily_budget=None, lifetime_budget=1000000, stop_time=(NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ"))
        got = self.codes("campaign", live, {"stop_time": (NOW + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%MZ")}, spent=100000, cap=20000)
        self.assertEqual(got, [("stop_time", "refused"), ("stop_time", "spend")])

    def test_a_later_start_on_an_unstarted_lifetime_ad_set_is_refused(self):
        live = adset(lifetime_budget=300000, start_time=(NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ"),
                     end_time=(NOW + timedelta(days=30)).strftime("%Y-%m-%dT%H:%MZ"))
        got = self.codes("adset", live, {"start_time": (NOW + timedelta(days=29)).strftime("%Y-%m-%dT%H:%MZ")}, spent=0, cap=20000)
        self.assertEqual(got, [("start_time", "refused")])

    def test_removing_a_cap_soon_after_a_raise_asks_both(self):
        last = {"at": NOW - timedelta(hours=48), "old": 1200, "new": 1400}
        self.assertEqual(self.codes("adset", adset(bid_strategy="COST_CAP", bid_amount=1400), {"bid_strategy": "LOWEST_COST_WITHOUT_CAP"},
                                    last_bid={"self": last}), [("bid_strategy", "big"), ("bid_strategy", "recent")])

    def test_removing_the_campaign_cap_asks_recent_when_an_ad_set_goal_was_just_raised(self):
        c = campaign(bid_strategy="COST_CAP", adset_bids={"S1": 1400, "S2": 1200})
        last = {"at": NOW - timedelta(hours=10), "old": 1200, "new": 1400}
        got = self.codes("campaign", c, {"bid_strategy": "LOWEST_COST_WITHOUT_CAP"}, last_bid={"S1": last},
                         adsets=[{"id": "S1", "name": "A", "bid_amount": 1400}, {"id": "S2", "name": "B", "bid_amount": 1200}])
        self.assertEqual(got, [("bid_strategy", "big"), ("bid_strategy", "recent")])

    def test_money_problem_is_the_first_question_not_accepted(self):
        qs = [{"field": "bid_amount", "code": "big"}, {"field": "bid_amount", "code": "recent"}]
        self.assertEqual([er.money_problem(qs, {"big": True})["code"], er.money_problem(qs, {"big": True, "recent": True}),
                          er.money_problem([{"field": "x", "code": "refused"}], {"refused": True})["code"]],
                         ["recent", None, "refused"])


class ChangeTextTests(unittest.TestCase):
    def test_history_values_match_what_the_sync_records(self):
        merged = {**META_ADSET["targeting"], "age_min": 30}
        self.assertEqual([er.change_text("end_time", "2026-12-01T07:59Z"), er.change_text("end_time", None),
                          er.change_text("stop_time", "2026-12-01T07:59Z"), er.change_text("bid_amount", 1500),
                          er.change_text("targeting", None, merged).split(" ")[0], er.change_text("special_ad_categories", ["HOUSING"])],
                         ["end 2026-12-01T07:59Z", "end none", "end 2026-12-01T07:59Z", "1500",
                          "fp:" + sh.targeting_fingerprint(merged), "HOUSING"])


class ReviewTests(unittest.TestCase):
    def test_old_and_new_in_plain_words_with_the_learning_note(self):
        live = adset()
        rows = er.review("adset", live, er.changes("adset", live, {"targeting": {**live["targeting"], "age_min": 30, "advantage": False}}),
                         "America/Los_Angeles")
        self.assertEqual([(r["label"], r["old_words"], r["new_words"], "learning" in (r["note"] or "")) for r in rows],
                         [("Ages", "25–65", "30–65", False), ("Advantage+ audience", "on", "off", False),
                          ("Suggested ages", "30–64", "none", True)])
        self.assertEqual(er.history_words(rows, "targeting"), "Ages 25–65 → 30–65; Advantage+ audience on → off; Suggested ages 30–64 → none")

    def test_a_bid_in_dollars(self):
        live = adset(bid_strategy="COST_CAP", bid_amount=1200)
        rows = er.review("adset", live, er.changes("adset", live, {"bid_amount": 1500}), "America/Los_Angeles")
        self.assertEqual([(r["label"], r["old_words"], r["new_words"]) for r in rows], [("Cost per result goal", "$12.00", "$15.00")])


if __name__ == "__main__":
    unittest.main()
