"""AM-D: audiences (audience_rules, pure): Meta's create bodies, what is refused, plain words, sizes, where used, pickers."""
import json
import unittest

import audience_rules as ar
import status_history as sh

PIXEL, PAGE, IG, FORM, VIDEO = "1821497329119793", "1404203629446490", "17841400000000001", "1132280359202136", "120252700000000011"
DAY = 86400


def row(**over):
    base = {"id": "23850000000000001", "kind": "custom", "subtype": "ENGAGEMENT", "name": "Lead form openers", "size_lower": 1200,
            "size_upper": 1500, "ready": "ready", "status_words": "Ready", "retention_days": 90, "source_kind": "lead_form",
            "who": "lead_generation_opened", "detail": None, "source_id": FORM, "lookalike": None, "made_here": False, "description": None}
    return {**base, **over}


KNOWN = {"pixel": PIXEL, "page": PAGE, "instagram": IG, "forms": {FORM: "Free intro call"}, "videos": {VIDEO: "N1.mp4"},
         "countries": ["US"],
         "audiences": {"23850000000000001": row(),
                       "23850000000000002": row(id="23850000000000002", name="Website 30 days", source_kind="website", subtype="WEBSITE",
                                                size_lower=12000, size_upper=15000),
                       "23850000000000003": row(id="23850000000000003", name="Newsletter", source_kind="customer_list", subtype="CUSTOM",
                                                size_lower=800, size_upper=1000),
                       "23850000000000004": row(id="23850000000000004", name="Old list", source_kind="customer_list", subtype="CUSTOM",
                                                size_lower=40, size_upper=60, ready="too_small"),
                       "23850000000000005": row(id="23850000000000005", name="New website", source_kind="website", subtype="WEBSITE",
                                                size_lower=None, size_upper=None, ready="filling"),
                       "23850000000000006": row(id="23850000000000006", name="People like openers", kind="lookalike", subtype="LOOKALIKE",
                                                source_kind="lookalike", size_lower=2_000_000, size_upper=2_400_000)}}


def spec(kind, **over):
    base = {"website": {"name": "Website visitors", "days": 30, "who": "all_visitors", "source_id": PIXEL},
            "page": {"name": "Page fans", "days": 365, "who": "page_engaged", "source_id": PAGE},
            "instagram": {"name": "IG fans", "days": 365, "who": "ig_business_profile_all", "source_id": IG},
            "lead_form": {"name": "Form senders", "days": 90, "who": "lead_generation_submitted", "source_id": FORM},
            "video": {"name": "Watchers", "days": 365, "who": "video_view_50_percent", "source_id": VIDEO},
            "lookalike": {"name": "People like openers", "origin_id": "23850000000000001", "country": "US", "ratio": 0.01}}[kind]
    return ar.clean(kind, {**base, **over})


def fields(found):
    return [f for f, _ in found]


class CreateParamsTests(unittest.TestCase):
    def rule(self, body):
        return body["rule"]["inclusions"]["rules"][0]

    def test_website_30_days_every_visitor(self):
        body = ar.create_params("website", spec("website"))
        r = self.rule(body)
        self.assertEqual((body["subtype"], body["prefill"], body["retention_days"], r["event_sources"], r["retention_seconds"], body["rule"]["inclusions"]["operator"]),
                         ("WEBSITE", True, 30, [{"id": PIXEL, "type": "pixel"}], 2592000, "or"))

    def test_website_a_page_address_and_a_lead_filter_differently(self):
        url = self.rule(ar.create_params("website", spec("website", who="visited_url", url="pricing")))["filter"]["filters"]
        lead = self.rule(ar.create_params("website", spec("website", who="lead_event")))["filter"]["filters"]
        self.assertEqual((url, lead), ([{"field": "url", "operator": "i_contains", "value": "pricing"}], [{"field": "event", "operator": "eq", "value": "Lead"}]))

    def test_lead_form_senders_90_days(self):
        body = ar.create_params("lead_form", spec("lead_form"))
        r = self.rule(body)
        self.assertEqual((body["subtype"], r["event_sources"], r["retention_seconds"], r["filter"]["filters"]),
                         ("ENGAGEMENT", [{"id": FORM, "type": "lead"}], 90 * DAY,
                          [{"field": "event", "operator": "eq", "value": "lead_generation_submitted"}]))

    def test_each_engagement_source_has_its_type(self):
        types = [self.rule(ar.create_params(k, spec(k)))["event_sources"][0]["type"] for k in ("page", "instagram", "video")]
        self.assertEqual(types, ["page", "ig_business", "video"])

    def test_lookalike_one_percent_us(self):
        body = ar.create_params("lookalike", spec("lookalike"))
        self.assertEqual((body["subtype"], body["origin_audience_id"], body["lookalike_spec"], "rule" in body),
                         ("LOOKALIKE", "23850000000000001", {"type": "similarity", "country": "US", "ratio": 0.01}, False))

    def test_the_body_never_carries_contact_data_keys(self):
        for kind in ar.KINDS:
            self.assertEqual({"schema", "payload", "data", "users"} & set(ar.create_params(kind, spec(kind))), set())


class LookalikeSizeTests(unittest.TestCase):
    def test_a_known_country_gives_a_rough_count_and_another_a_share(self):
        self.assertEqual((ar.lookalike_size_words("US", 0.01), ar.lookalike_size_words("US", 0.1), ar.lookalike_size_words("NZ", 0.02)),
                         ("Meta picks the 1 % of people in the US most like your source: roughly 2 million people.",
                          "Meta picks the 10 % of people in the US most like your source: roughly 20 million people.",
                          "Meta picks the 2 % of people in NZ most like your source."))


class CleanTests(unittest.TestCase):
    def test_names_are_cut_ids_are_digits_and_ratios_numbers(self):
        s = ar.clean("lookalike", {"name": "x" * 500, "origin_id": "238<script>", "country": "us ", "ratio": "0.02"})
        self.assertEqual((len(s["name"]), s["origin_id"], s["country"], s["ratio"]), (200, "", "US", 0.02))

    def test_bad_numbers_become_none(self):
        s = ar.clean("website", {"name": "W", "days": "lots", "who": "all_visitors"})
        self.assertEqual(s["days"], None)


class ProblemsTests(unittest.TestCase):
    def p(self, kind, **over):
        return ar.problems(kind, spec(kind, **over), KNOWN)

    def test_every_kind_as_built_passes(self):
        self.assertEqual({k: self.p(k) for k in ar.KINDS}, {k: [] for k in ar.KINDS})

    def test_website_181_days_lead_form_91_days(self):
        self.assertEqual((fields(self.p("website", days=181)), fields(self.p("lead_form", days=91)), fields(self.p("page", days=0))),
                         (["days"], ["days"], ["days"]))

    def test_unknown_form_and_video(self):
        self.assertEqual((fields(self.p("lead_form", source_id="999")), fields(self.p("video", source_id="999"))), (["source"], ["source"]))

    def test_a_url_fragment_of_one_letter_or_another_scheme(self):
        self.assertEqual((fields(self.p("website", who="visited_url", url="a")), fields(self.p("website", who="visited_url", url="ftp://x.example/a")),
                          self.p("website", who="visited_url", url="https://edgebourne.com/pricing")),
                         (["url"], ["url"], []))

    def test_no_pixel_and_no_instagram_say_where_to_set_them(self):
        none = {**KNOWN, "pixel": None, "instagram": None}
        found = ar.problems("website", spec("website", source_id=""), none) + ar.problems("instagram", spec("instagram", source_id=""), none)
        self.assertEqual([(f, "Settings → Meta" in m or "Instagram" in m) for f, m in found], [("source", True), ("source", True)])

    def test_who_must_be_one_of_the_kinds_choices(self):
        self.assertEqual(fields(self.p("page", who="lead_generation_opened")), ["who"])

    def test_a_name_is_needed(self):
        self.assertEqual(fields(self.p("video", name="  ")), ["name"])

    def test_lookalike_from_80_people_a_filling_source_another_account_and_ratio_007(self):
        small = {**KNOWN, "audiences": {**KNOWN["audiences"], "23850000000000001": row(size_lower=80, size_upper=100)}}
        self.assertEqual((fields(ar.problems("lookalike", spec("lookalike"), small)),
                          fields(self.p("lookalike", origin_id="23850000000000005")),
                          fields(self.p("lookalike", origin_id="99990000000000001")),
                          fields(self.p("lookalike", ratio=0.07))),
                         (["origin"], ["origin"], ["origin"], ["ratio"]))

    def test_the_small_source_message_names_metas_minimum(self):
        small = {**KNOWN, "audiences": {**KNOWN["audiences"], "23850000000000001": row(size_lower=80, size_upper=100)}}
        self.assertIn(str(ar.MIN_SOURCE), ar.problems("lookalike", spec("lookalike"), small)[0][1])

    def test_lookalike_from_a_customer_list_of_800_is_allowed_from_60_refused(self):
        self.assertEqual((self.p("lookalike", origin_id="23850000000000003"), fields(self.p("lookalike", origin_id="23850000000000004"))), ([], ["origin"]))

    def test_no_lookalike_of_a_lookalike_and_no_country_outside_the_accounts(self):
        self.assertEqual((fields(self.p("lookalike", origin_id="23850000000000006")), fields(self.p("lookalike", country="FR"))), (["origin"], ["country"]))

    def test_an_unknown_kind(self):
        self.assertEqual(fields(ar.problems("customer_list", {"name": "x"}, KNOWN)), ["kind"])


class DescribeTests(unittest.TestCase):
    def test_plain_sentences_for_each_kind(self):
        names = {FORM: "Free intro call", VIDEO: "N1.mp4", "23850000000000001": "Lead form openers"}
        got = [ar.describe(row(source_kind="website", who="all_visitors", retention_days=30), names),
               ar.describe(row(source_kind="website", who="visited_url", detail="pricing", retention_days=30), names),
               ar.describe(row(source_kind="lead_form", who="lead_generation_submitted", retention_days=90), names),
               ar.describe(row(source_kind="lead_form", who="lead_generation_dropoff", retention_days=30), names),
               ar.describe(row(source_kind="page", who="page_engaged", retention_days=365), names),
               ar.describe(row(source_kind="video", who="video_view_50_percent", source_id=VIDEO, retention_days=365), names),
               ar.describe(row(kind="lookalike", source_kind="lookalike", source_id="23850000000000001", lookalike={"country": "US", "ratio": 0.01}), names),
               ar.describe(row(source_kind="customer_list", subtype="CUSTOM"), names)]
        self.assertEqual(got, ["People who visited your website in the last 30 days",
                               "People who visited a page whose address contains “pricing” in the last 30 days",
                               "People who sent your lead form “Free intro call” in the last 90 days",
                               "People who opened your lead form “Free intro call” and didn't send it in the last 30 days",
                               "People who engaged with your Facebook Page in the last 365 days",
                               "People who watched at least half of your video “N1.mp4” in the last 365 days",
                               "People like “Lead form openers” (1 %, US)",
                               "A customer list uploaded to Meta"])

    def test_a_console_made_audience_keeps_its_own_words(self):
        self.assertEqual(ar.describe(row(made_here=True, description="People who sent the Nov form")), "People who sent the Nov form")

    def test_without_names_it_still_reads(self):
        self.assertEqual(ar.describe(row(source_kind="lead_form", who="lead_generation_opened", retention_days=90)),
                         "People who opened your lead form in the last 90 days")


class ReadinessTests(unittest.TestCase):
    def test_none_small_ready_and_metas_error(self):
        self.assertEqual([ar.readiness(None, None, {"code": 200}, None)[0], ar.readiness(400, 600, {"code": 200}, None)[0],
                          ar.readiness(12000, 15000, {"code": 200}, {"code": 200})[0],
                          ar.readiness(12000, 15000, {"code": 400, "description": "This audience was deleted"}, None)],
                         ["filling", "too_small", "ready", ("problem", "This audience was deleted")])

    def test_metas_minus_one_for_no_size_is_filling(self):
        self.assertEqual(ar.readiness(-1, -1, None, None)[0], "filling")

    def test_size_words(self):
        self.assertEqual([ar.size_words(row(size_lower=12000, size_upper=15000)), ar.size_words(row(ready="filling", size_lower=None, size_upper=None)),
                          ar.size_words(row(ready="too_small", size_lower=40, size_upper=60))],
                         ["12,000–15,000 people", "Still filling", "40–60 people"])


class FromMetaTests(unittest.TestCase):
    def test_a_website_audience_read_back(self):
        raw = {"id": "238001", "name": "Web 30", "subtype": "WEBSITE", "approximate_count_lower_bound": 12000, "approximate_count_upper_bound": 15000,
               "delivery_status": {"code": 200, "description": "Ready"}, "operation_status": {"code": 200}, "retention_days": 30,
               "rule": json.dumps({"inclusions": {"operator": "or", "rules": [{"event_sources": [{"id": PIXEL, "type": "pixel"}], "retention_seconds": 30 * DAY,
                                                                                "filter": {"operator": "and", "filters": [{"field": "url", "operator": "i_contains", "value": "pricing"}]}}]}}),
               "time_created": 1794500000}
        r = ar.from_meta(raw)
        self.assertEqual({k: r[k] for k in ("id", "kind", "source_kind", "who", "detail", "source_id", "retention_days", "ready", "size_lower")},
                         {"id": "238001", "kind": "custom", "source_kind": "website", "who": "visited_url", "detail": "pricing", "source_id": PIXEL,
                          "retention_days": 30, "ready": "ready", "size_lower": 12000})

    def test_a_lookalike_and_a_customer_list(self):
        look = ar.from_meta({"id": "238002", "name": "Like openers", "subtype": "LOOKALIKE",
                             "lookalike_spec": {"country": "US", "ratio": 0.01, "origin": [{"id": "238001", "name": "Openers"}]}})
        cust = ar.from_meta({"id": "238003", "name": "Clients", "subtype": "CUSTOM", "approximate_count_lower_bound": 800, "approximate_count_upper_bound": 1000})
        self.assertEqual(((look["kind"], look["source_id"], look["lookalike"]), (cust["kind"], cust["source_kind"], cust["ready"])),
                         (("lookalike", "238001", {"country": "US", "ratio": 0.01}), ("custom", "customer_list", "ready")))

    def test_metas_text_is_cut_and_a_bad_id_dropped(self):
        self.assertEqual((len(ar.from_meta({"id": "238004", "name": "n" * 900, "description": "d" * 900})["name"]),
                          len(ar.from_meta({"id": "238004", "name": "n", "description": "d" * 900})["description"]), ar.from_meta({"id": "x1", "name": "n"})),
                         (200, 300, None))

    def test_a_saved_audience_keeps_only_whitelisted_targeting(self):
        r = ar.saved_from_meta({"id": "238005", "name": "SoCal owners 30-60",
                                "targeting": json.dumps({"age_min": 30, "age_max": 60, "geo_locations": {"cities": [{"key": "2421696", "radius": 25}]},
                                                         "something_else": 1})})
        self.assertEqual((r["kind"], sorted(r["targeting"])), ("saved", ["age_max", "age_min", "geo_locations"]))


class WhereUsedTests(unittest.TestCase):
    def test_included_excluded_and_deleted_left_out(self):
        sets = [{"id": "1", "name": "A", "effective_status": "ACTIVE", "audience_ids": ["9"], "excluded_audience_ids": []},
                {"id": "2", "name": "B", "effective_status": "PAUSED", "audience_ids": [], "excluded_audience_ids": ["9"]},
                {"id": "3", "name": "C", "effective_status": "DELETED", "audience_ids": ["9"], "excluded_audience_ids": []},
                {"id": "4", "name": "D", "effective_status": "ACTIVE", "audience_ids": ["8"], "excluded_audience_ids": []}]
        used = ar.where_used("9", sets)
        self.assertEqual(([a["id"] for a in used["include"]], [a["id"] for a in used["exclude"]], ar.used_words(used)), (["1"], ["2"], "In 1 ad set · left out of 1"))

    def test_words_when_unused_and_several(self):
        self.assertEqual((ar.used_words({"include": [], "exclude": []}), ar.used_words({"include": [{}, {}], "exclude": []})), ("Not used yet", "In 2 ad sets"))


class TargetingWithTests(unittest.TestCase):
    T = {"age_min": 25, "age_max": 65, "geo_locations": {"cities": [{"key": "2421696", "radius": 25}]}, "targeting_automation": {"advantage_audience": 1}}

    def test_only_the_two_audience_keys_change(self):
        out = ar.targeting_with(self.T, ["11", "12"], ["13"])
        self.assertEqual(({k: v for k, v in out.items() if k not in ("custom_audiences", "excluded_custom_audiences")}, out["custom_audiences"], out["excluded_custom_audiences"]),
                         (self.T, [{"id": "11"}, {"id": "12"}], [{"id": "13"}]))
        self.assertNotEqual(sh.targeting_fingerprint(out), sh.targeting_fingerprint(self.T))

    def test_empty_lists_drop_the_keys_and_the_input_is_untouched(self):
        start = {**self.T, "custom_audiences": [{"id": "11"}]}
        self.assertEqual((ar.targeting_with(start, [], []), start["custom_audiences"]), (self.T, [{"id": "11"}]))


class PickerTests(unittest.TestCase):
    AUD = {k: v for k, v in KNOWN["audiences"].items()}

    def test_a_lookalike_in_a_special_category_campaign_says_why(self):
        look = KNOWN["audiences"]["23850000000000006"]
        self.assertEqual((bool(ar.picker_refusal({"special_ad_categories": ["HOUSING"]}, look)), ar.picker_refusal({"special_ad_categories": []}, look),
                          ar.picker_refusal({"special_ad_categories": ["HOUSING"]}, KNOWN["audiences"]["23850000000000001"])), (True, None, None))

    def test_an_audience_with_a_problem_is_refused(self):
        self.assertIn("deleted", ar.picker_refusal({}, row(ready="problem", status_words="This audience was deleted")))

    def test_pick_problems(self):
        ok = ar.pick_problems(["23850000000000001"], ["23850000000000002"], self.AUD, [])
        foreign = ar.pick_problems(["99990000000000001"], [], self.AUD, [])
        both = ar.pick_problems(["23850000000000001"], ["23850000000000001"], self.AUD, [])
        many = ar.pick_problems([str(i) for i in range(21)], [], {str(i): row(id=str(i)) for i in range(21)}, [])
        special = ar.pick_problems(["23850000000000006"], [], self.AUD, ["HOUSING"])
        self.assertEqual([ok, fields(foreign), fields(both), fields(many), fields(special)], [[], ["audiences"], ["audiences"], ["audiences"], ["audiences"]])
        self.assertEqual(foreign[0][1], "That audience isn't in this account")

    def test_one_already_on_the_ad_set_may_stay_even_if_not_listed_yet(self):
        self.assertEqual(ar.pick_problems(["99990000000000001"], [], self.AUD, [], keep={"99990000000000001"}), [])

    def test_clean_ids_keeps_digits_once_in_order(self):
        self.assertEqual(ar.clean_ids(["12", 12, "x", "13", None, {"id": "14"}]), ["12", "13", "14"])


class AdoptMatchTests(unittest.TestCase):
    """An audience found on Meta after an unanswered create is adopted only when it is the one this form asked for."""
    def made(self, kind, **over):
        body = ar.create_params(kind, spec(kind))
        raw = {"id": "23859999999999999", **{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in body.items()}}
        if kind == "lookalike":
            raw["lookalike_spec"] = json.dumps({"country": "US", "ratio": 0.01, "origin": [{"id": spec(kind)["origin_id"]}]})
        return {**raw, **over}

    def test_the_same_kind_source_and_name_matches(self):
        self.assertEqual([ar.adopt_match(k, spec(k), self.made(k)) for k in ("website", "video", "lookalike")], [True, True, True])

    def test_a_different_type_source_or_name_does_not(self):
        other_source = json.dumps(ar.create_params("video", spec("video", source_id="120252700000000099"))["rule"])
        self.assertEqual([ar.adopt_match("website", spec("website"), self.made("website", subtype="CUSTOM")),
                          ar.adopt_match("video", spec("video"), self.made("video", rule=other_source)),
                          ar.adopt_match("lookalike", spec("lookalike"), self.made("lookalike", lookalike_spec=json.dumps({"origin": [{"id": "1"}]}))),
                          ar.adopt_match("website", spec("website"), self.made("website", name="Website visitors 2"))],
                         [False, False, False, False])

    def test_ids_beyond_the_limit_are_kept_when_asked(self):
        ids = [str(1000 + i) for i in range(ar.MAX_PICKED + 10)]
        self.assertEqual((len(ar.clean_ids(ids)), ar.clean_ids(ids, cap=False)), (ar.MAX_PICKED + 5, ids))


if __name__ == "__main__":
    unittest.main()
