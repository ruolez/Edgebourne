"""AM-B: Ads Manager drafts, pure logic (what Meta's answer becomes, the tree, what's missing, whether the console can
finish a draft, the builders' prefill, a staged edit's rows, the Inbox items, the words)."""
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import adsets_api
import am_drafts
import builds_api
import campaign_build
import creative_build
import money_rules

LA = ZoneInfo("America/Los_Angeles")
PAGE = "1404203629446490"
FORM = "1132280359202136"
LIVE_CAMPAIGN = "120252638288040312"
LIVE_ADSET = "120252672227950312"
HASH = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
VIDEO = "120252700000000001"
T0 = 1794594897
TODAY = date(2026, 11, 13)

# The real answer read on 2026-11-13, verbatim.
REAL = {"ad_drafts": [{"ad_object_id": "120252756936450312", "ad_object_type": "campaign", "parent_ad_object_id": None, "action": "add",
                       "status": "EDITING", "validation_status": "VALIDATED", "source": "mcp_campaign_creation", "time_updated": 1794594897,
                       "values": {"bid_strategy": {"new": "LOWEST_COST_WITHOUT_CAP"}, "buying_type": {"new": "AUCTION"}, "daily_budget": {"new": 2000},
                                  "is_odax_campaign_group": {"new": True}, "name": {"new": "Edge Bourne - Dashboards with AI - Leads"},
                                  "objective": {"new": "OUTCOME_LEADS"}, "special_ad_categories": {"new": []}, "status": {"new": "ACTIVE"}},
                       "active_errors": [], "publish_error": None}]}

RIVERSIDE = {"geo_locations": {"cities": [{"key": "2421696", "name": "Riverside, CA", "radius": 25, "distance_unit": "mile"}]},
             "age_min": 25, "age_max": 65, "targeting_automation": {"advantage_audience": 1}}


def raw(oid, kind, values, parent=None, action="add", at=T0, errors=None, publish_error=None):
    return {"ad_object_id": oid, "ad_object_type": kind, "parent_ad_object_id": parent, "action": action, "status": "EDITING",
            "validation_status": "VALIDATED", "source": "ads_manager", "time_updated": at, "values": {k: {"new": v} for k, v in values.items()},
            "active_errors": errors or [], "publish_error": publish_error}


def campaign(oid, name="Edge Bourne - Order portal - Leads", budget=2000, at=T0, **more):
    return raw(oid, "campaign", {"name": name, "objective": "OUTCOME_LEADS", "buying_type": "AUCTION", "daily_budget": budget,
                                 "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "special_ad_categories": [], **more}, at=at)


def adset(oid, parent, name="Order portal - Riverside", page=PAGE, targeting=RIVERSIDE, **more):
    values = {"name": name, "optimization_goal": "LEAD_GENERATION", "billing_event": "IMPRESSIONS", "destination_type": "ON_AD",
              "targeting": targeting, **more}
    if page:
        values["promoted_object"] = {"page_id": page}
    return raw(oid, "adset", values, parent=parent, at=T0 + 10)


def image_ad(oid, parent, name="Portal 1 - Orders at 2 AM", page=PAGE, form=FORM, image=HASH, cta="SIGN_UP"):
    link = {"message": "Customers order any time.", "name": "Orders that come in on their own", "image_hash": image,
            "call_to_action": {"type": cta, "value": {"lead_gen_form_id": form} if form else {}}}
    story = {"link_data": link, **({"page_id": page} if page else {})}
    return raw(oid, "ad", {"name": name, "creative": {"object_story_spec": story}}, parent=parent, at=T0 + 20)


def video_ad(oid, parent, name="Portal 2 - Email orders", video=VIDEO, form=FORM):
    data = {"message": "Email orders get read in automatically.", "title": "No more retyping orders", "video_id": video,
            "image_hash": HASH, "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": form}}}
    return raw(oid, "ad", {"name": name, "creative": {"object_story_spec": {"page_id": PAGE, "video_data": data}}}, parent=parent, at=T0 + 30)


def rows_of(*drafts):
    return am_drafts.normalize({"ad_drafts": list(drafts)})


def complete_draft(**camp):
    """Draft 2: a campaign, its ad set and two ads (an image and a video), ready to create."""
    return rows_of(campaign("900", **camp), adset("901", "900"), image_ad("902", "901"), video_ad("903", "901"))


def root(rows):
    return am_drafts.tree(rows)[0]


class NormalizeTests(unittest.TestCase):
    def test_the_real_answer_becomes_one_campaign_row_with_its_fields_whitelisted(self):
        self.assertEqual(am_drafts.normalize(REAL), [{
            "draft_id": "120252756936450312", "object_type": "campaign", "parent_id": None, "action": "add", "meta_status": "EDITING",
            "validation_status": "VALIDATED", "source": "mcp_campaign_creation",
            "time_updated": datetime.fromtimestamp(1794594897, timezone.utc),
            "fields": {"bid_strategy": {"new": "LOWEST_COST_WITHOUT_CAP"}, "buying_type": {"new": "AUCTION"}, "daily_budget": {"new": 2000},
                       "name": {"new": "Edge Bourne - Dashboards with AI - Leads"}, "objective": {"new": "OUTCOME_LEADS"},
                       "special_ad_categories": {"new": []}, "status": {"new": "ACTIVE"}},
            "other_fields": ["is_odax_campaign_group"], "problems": []}])

    def test_meta_text_stays_text_and_is_cut_and_odd_rows_are_dropped(self):
        markup = "<img src=x onerror=alert(1)>" + "x" * 300
        rows = am_drafts.normalize({"ad_drafts": [
            raw("5", "ad_set", {"name": markup}, parent="4", errors=[{"message": "m" * 9000, "field": "targeting"}]),
            raw("6", "ad_creative", {"name": "unknown kind"}),
            raw("act_7", "campaign", {"name": "not digits"}),
            "not a draft"]})
        self.assertEqual([(r["draft_id"], r["object_type"], r["fields"]["name"]["new"], r["problems"]) for r in rows],
                         [("5", "adset", markup[:200], [{"message": "m" * 300, "field": "targeting"}])])

    def test_an_answer_of_another_shape_is_refused(self):
        for bad in ("not json", {"surprise": 1}, {"ad_drafts": "many"}, None, 7):
            self.assertIsNone(am_drafts.normalize(bad), repr(bad))
        self.assertEqual(len(am_drafts.normalize(REAL["ad_drafts"])), 1)  # a bare list of drafts is the same answer

    def test_only_listed_targeting_and_creative_keys_are_kept(self):
        targeting = {"age_min": 30, "foo": 1, "geo_locations": {"cities": [{"key": "1", "radius": 25, "evil": "x"}], "planets": ["mars"]},
                     "flexible_spec": [{"interests": [{"id": "6003", "name": "Entrepreneurship", "audience_size": 9}], "moods": [{"id": "1"}]}]}
        creative = {"object_story_spec": {"page_id": PAGE, "link_data": {"message": "Hi", "image_hash": HASH, "picture": "http://evil",
                                                                        "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": FORM, "app": "x"}}}},
                    "url_tags": "utm=1"}
        rows = rows_of(raw("1", "adset", {"targeting": targeting}), raw("2", "ad", {"creative": creative}, parent="1"))
        self.assertEqual((rows[0]["fields"]["targeting"]["new"], rows[1]["fields"]["creative"]["new"]), (
            {"age_min": 30, "geo_locations": {"cities": [{"key": "1", "radius": 25}]},
             "flexible_spec": [{"interests": [{"id": "6003", "name": "Entrepreneurship"}]}]},
            {"object_story_spec": {"page_id": PAGE, "link_data": {"message": "Hi", "image_hash": HASH,
                                                                  "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": FORM}}}}}))

    def test_amounts_are_whole_cents_and_a_value_of_the_wrong_kind_is_only_named(self):
        r = am_drafts.normalize({"ad_drafts": [{**raw("1", "campaign", {}), "values": {
            "daily_budget": {"new": "2500", "old": 2000}, "spend_cap": {"new": "20.5"}, "name": {"new": {"nested": 1}}, "status": "ACTIVE"}}]})[0]
        self.assertEqual((r["fields"], r["other_fields"]), ({"daily_budget": {"new": 2500, "old": 2000}}, ["name", "spend_cap", "status"]))

    def test_problems_come_from_active_errors_and_the_publish_error(self):
        r = rows_of(raw("1", "campaign", {}, errors=[{"error_summary": "Choose a Page", "error_message": "Pick the Facebook Page."}, {"weird": 1}],
                        publish_error={"message": "Couldn't publish: no ad set"}))[0]
        self.assertEqual(r["problems"], [{"message": "Pick the Facebook Page.", "field": None},
                                         {"message": "Couldn't publish: no ad set", "field": None}])
        self.assertEqual(rows_of(raw("1", "campaign", {}, publish_error="Payment failed"))[0]["problems"],
                         [{"message": "Payment failed", "field": None}])

    def test_a_read_is_complete_only_when_no_page_was_left(self):
        self.assertEqual([am_drafts.is_complete(x) for x in (
            {"ad_drafts": [], "complete": True}, {"ad_drafts": [], "complete": False}, {"ad_drafts": []},
            {"ad_drafts": [], "paging": {"cursors": {"after": "25"}, "next": "https://…"}}, {"ad_drafts": [], "paging": {"cursors": {"after": "25"}}})],
            [True, False, True, False, True])


class KeepOwnTests(unittest.TestCase):
    def test_edits_and_children_of_objects_this_account_doesnt_hold_are_left_out(self):
        rows = rows_of(raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update"),
                       raw("555", "campaign", {"daily_budget": 2500}, action="update"),
                       adset("901", "900"), campaign("900"), adset("902", LIVE_CAMPAIGN), adset("903", "777"))
        kept, dropped = am_drafts.keep_own(rows, {LIVE_CAMPAIGN, LIVE_ADSET})
        self.assertEqual(([r["draft_id"] for r in kept], dropped), ([LIVE_CAMPAIGN, "901", "900", "902"], 2))


class TreeTests(unittest.TestCase):
    def test_a_campaign_holds_its_ad_set_and_ads_and_a_child_of_a_live_object_stands_alone(self):
        rows = complete_draft() + rows_of(image_ad("950", LIVE_ADSET), raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update", at=T0 + 99))
        roots = am_drafts.tree(rows)
        self.assertEqual([(r["draft_id"], r.get("parent_live"), [(s["draft_id"], [a["draft_id"] for a in s["ads"]]) for s in r["adsets"]],
                           [a["draft_id"] for a in r["ads"]]) for r in roots],
                         [(LIVE_CAMPAIGN, None, [], []), ("950", LIVE_ADSET, [], []), ("900", None, [("901", ["902", "903"])], [])])

    def test_edits_never_nest_under_another_draft(self):
        rows = rows_of(raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update"),
                       raw(LIVE_ADSET, "adset", {"name": "wider"}, parent=LIVE_CAMPAIGN, action="update", at=T0 + 5))
        self.assertEqual([r["draft_id"] for r in am_drafts.tree(rows)], [LIVE_ADSET, LIVE_CAMPAIGN])


class ShownRowsTests(unittest.TestCase):
    """Which stored rows the cards show: `shown` comes from SQL (open, or finished in the last 7 days). A finished draft that
    Ads Manager later dropped keeps what it held when it was finished, never children removed from it before."""
    FINISHED = datetime(2026, 11, 13, 10, tzinfo=timezone.utc)

    def stored(self, gone=None, child_gone=None, finished=FINISHED):
        rows = complete_draft()
        for r in rows:
            r.update(gone_at=gone, finished_at=None, shown=gone is None)
        rows[0].update(finished_at=finished, shown=True)
        for r in rows[1:]:
            r.update(gone_at=child_gone or gone, shown=(child_gone or gone) is None)
        return rows

    def ids(self, rows):
        return sorted(r["draft_id"] for r in am_drafts.shown_rows(rows))

    def test_a_finished_draft_gone_from_ads_manager_keeps_its_ad_set_and_ads(self):
        later = self.FINISHED + timedelta(hours=2)
        self.assertEqual(self.ids(self.stored(gone=later)), ["900", "901", "902", "903"])

    def test_a_child_removed_before_it_was_finished_stays_out(self):
        self.assertEqual(self.ids(self.stored(gone=self.FINISHED + timedelta(hours=2), child_gone=self.FINISHED - timedelta(hours=1))), ["900"])

    def test_a_gone_draft_never_finished_shows_nothing(self):
        rows = self.stored(gone=self.FINISHED, finished=None)
        rows[0]["shown"] = False
        self.assertEqual(self.ids(rows), [])

    def test_open_drafts_are_all_shown_and_a_gone_child_of_an_open_draft_is_not(self):
        rows = self.stored(finished=None)
        rows[3].update(gone_at=self.FINISHED, shown=False)
        self.assertEqual(self.ids(rows), ["900", "901", "902"])


class MissingTests(unittest.TestCase):
    def test_the_real_draft_with_its_ad_set_lacks_only_ads(self):
        self.assertEqual(am_drafts.missing(root(am_drafts.normalize(REAL) + rows_of(adset("313", "120252756936450312")))), ["No ads yet"])

    def test_a_complete_draft_lacks_nothing(self):
        self.assertEqual(am_drafts.missing(root(complete_draft())), [])

    def test_no_page_anywhere_is_named(self):
        rows = rows_of(campaign("900"), adset("901", "900", page=None), image_ad("902", "901", page=None))
        self.assertEqual(am_drafts.missing(root(rows)), ["No Facebook Page"])

    def test_each_gap_in_plain_words(self):
        self.assertEqual(am_drafts.missing(root(rows_of(campaign("900", budget=None)))), ["No daily budget", "No ad set yet", "No ads yet"])
        rows = rows_of(campaign("900"), adset("901", "900", targeting={}), image_ad("902", "901", form=None), image_ad("903", "901", image=None))
        self.assertEqual(am_drafts.missing(root(rows)), ["No places or ages for the ad set", "Ad 1 has no lead form", "Ad 2 has no picture or video"])

    def test_a_staged_edit_lacks_nothing(self):
        self.assertEqual(am_drafts.missing(root(rows_of(raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update")))), [])


class FinishableTests(unittest.TestCase):
    def test_only_daily_budget_auction_lead_campaigns_with_an_instant_form_are_finished_here(self):
        sales = rows_of(raw("1", "campaign", {"name": "Store", "objective": "OUTCOME_SALES", "daily_budget": 3000}))
        lifetime = rows_of(raw("1", "campaign", {"objective": "OUTCOME_LEADS", "lifetime_budget": 90000}))
        housing = rows_of(raw("1", "campaign", {"objective": "OUTCOME_LEADS", "daily_budget": 2000, "special_ad_categories": ["HOUSING"]}))
        reach = rows_of(raw("1", "campaign", {"objective": "OUTCOME_LEADS", "daily_budget": 2000, "buying_type": "RESERVED"}))
        site = rows_of(campaign("900"), adset("901", "900", destination_type="WEBSITE"))
        self.assertEqual([am_drafts.finishable(root(r)) for r in (sales, lifetime, housing, reach, site, complete_draft())], [
            "This draft's goal is Sales; the console builds lead campaigns only.",
            "This draft has a lifetime budget; the console sets daily budgets.",
            "This draft is in a special ad category (housing); finish it in Ads Manager.",
            "This draft buys reach and frequency; the console builds auction campaigns only.",
            "This draft's ad set sends people to a website, not an Instant Form; the console builds Instant Form ads only.",
            None])

    def test_a_staged_edit_is_applied_not_finished(self):
        self.assertEqual(am_drafts.finishable(root(rows_of(raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update")))),
                         "This draft changes something that's already running: apply it below.")


class CampaignSpecTests(unittest.TestCase):
    def spec(self, rows, forms=(FORM,), page=PAGE):
        return am_drafts.to_campaign_spec(root(rows), set(forms), page, LA)

    def test_a_complete_draft_fills_every_step_and_the_wizard_takes_it_as_typed(self):
        spec, notes = self.spec(complete_draft())
        self.assertEqual((spec, notes), ({
            "name": "Edge Bourne - Order portal - Leads", "daily_budget_cents": 2000, "form_id": FORM,
            "adset": {"template_adset_id": "", "name": "Order portal - Riverside",
                      "locations": [{"kind": "city", "key": "2421696", "name": "Riverside, CA", "radius": 25}],
                      "age_min": 25, "age_max": 65, "suggest_min": None, "suggest_max": None, "advantage": True,
                      "keep_hints": False, "hints": [], "flexible_spec": [], "start_day": None, "start_hour": 0, "end_day": None, "end_hour": 23},
            "ads": [{"name": "Portal 1 - Orders at 2 AM", "title": "Orders that come in on their own", "body": "Customers order any time.",
                     "cta_type": "SIGN_UP", "template_ad_id": "", "media": {"kind": "image", "hash": HASH}},
                    {"name": "Portal 2 - Email orders", "title": "No more retyping orders", "body": "Email orders get read in automatically.",
                     "cta_type": "SIGN_UP", "template_ad_id": "", "media": {"kind": "video", "video_id": VIDEO}}]}, []))
        cleaned = builds_api.clean(spec)
        self.assertEqual((cleaned["daily_budget_cents"], cleaned["form_id"], [a["media"] for a in cleaned["ads"]], cleaned["adset"]["locations"]),
                         (2000, FORM, [{"kind": "image", "hash": HASH}, {"kind": "video", "video_id": VIDEO}], spec["adset"]["locations"]))
        self.assertEqual(campaign_build.field_problems(cleaned, {FORM}, set(), 2000), [])

    def test_an_unknown_lead_form_is_left_for_the_person_to_pick(self):
        spec, notes = self.spec(complete_draft(), forms=())
        self.assertEqual((spec["form_id"], notes), ("", [f"The draft's lead form ({FORM}) isn't one of this account's forms: pick one in the Lead form step."]))
        self.assertIn(("form", "form", "Pick the lead form people fill in"), campaign_build.field_problems(builds_api.clean(spec), set(), set(), 2000))

    def test_a_bid_cap_is_named_and_left_to_ads_manager(self):
        rows = rows_of(campaign("900", bid_strategy="COST_CAP"), adset("901", "900", bid_amount=1200), image_ad("902", "901"))
        self.assertEqual(self.spec(rows)[1], ["Cost cap of $12.00: this page uses lowest cost. Set the cap in Ads Manager after creating."])

    def test_interests_are_kept_as_hints(self):
        hints = {**RIVERSIDE, "flexible_spec": [{"interests": [{"id": "6003371567474", "name": "Entrepreneurship"}],
                                                 "behaviors": [{"id": "6002714898572", "name": "Small business owners"}]}]}
        spec, _ = self.spec(rows_of(campaign("900"), adset("901", "900", targeting=hints), image_ad("902", "901")))
        self.assertEqual((spec["adset"]["keep_hints"], spec["adset"]["hints"], spec["adset"]["flexible_spec"]),
                         (True, ["Entrepreneurship", "Small business owners"], hints["flexible_spec"]))
        cleaned = builds_api.clean(spec)["adset"]
        self.assertEqual((cleaned["keep_hints"], cleaned["flexible_spec"]), (True, hints["flexible_spec"]))

    def test_a_budget_over_the_ceiling_is_kept_so_the_wizard_refuses_it(self):
        spec, _ = self.spec(complete_draft(budget=50000))
        self.assertEqual(spec["daily_budget_cents"], 50000)
        self.assertGreater(spec["daily_budget_cents"], money_rules.ceiling(None))
        self.assertIn("budget", [step for step, _, _ in campaign_build.field_problems(builds_api.clean(spec), {FORM}, set(), 2000)])

    def test_a_budget_kept_on_the_ad_set_moves_to_the_campaign(self):
        rows = rows_of(campaign("900", budget=None), adset("901", "900", daily_budget=1500), image_ad("902", "901"))
        spec, notes = self.spec(rows)
        self.assertEqual((spec["daily_budget_cents"], notes), (1500, ["The draft keeps its $15.00 daily budget on the ad set; this page puts it on the campaign."]))

    def test_another_page_more_ads_and_a_button_without_a_form_are_named(self):
        ads = [image_ad(str(910 + i), "901", name=f"Ad {i}", cta="SHOP_NOW" if i == 0 else "SIGN_UP") for i in range(8)]
        spec, notes = self.spec(rows_of(campaign("900"), adset("901", "900", page="999"), *ads), page=PAGE)
        self.assertEqual((len(spec["ads"]), spec["ads"][0]["cta_type"], notes), (6, "SIGN_UP", [
            "The draft names another Facebook Page (999); the console uses this account's Page.",
            "The draft has 8 ads; this page makes the first 6. Add the rest with New ad after creating.",
            "Ad 1's button (SHOP_NOW) doesn't open a lead form; it's set to Sign up."]))

    def test_dates_are_the_account_days_and_a_start_in_the_past_is_dropped(self):
        rows = rows_of(campaign("900"), adset("901", "900", start_time="2026-11-01T09:00:00-0800", end_time="2026-12-24T23:00:00-0800"),
                       image_ad("902", "901"))
        spec, notes = am_drafts.to_campaign_spec(root(rows), {FORM}, PAGE, LA, today=TODAY)
        self.assertEqual((spec["adset"]["start_day"], spec["adset"]["end_day"], notes),
                         (None, "2026-12-24", ["The draft's start date has passed; it starts when you publish."]))


class AdsetAndAdSpecTests(unittest.TestCase):
    def test_an_ad_set_draft_under_a_live_campaign_fills_new_ad_set(self):
        node = root(rows_of(adset("960", LIVE_CAMPAIGN, name="SoCal owners - Orange County")))
        body, notes = am_drafts.to_adset_spec(node, {"id": LIVE_CAMPAIGN, "daily_budget_cents": 2000}, LA)
        self.assertEqual((body["campaign_id"], body["template_adset_id"], body["spec"]["name"], body["spec"]["daily_budget_cents"], notes),
                         (LIVE_CAMPAIGN, "", "SoCal owners - Orange County", None, []))
        cleaned = adsets_api.clean(body["spec"])
        self.assertEqual(__import__("adset_build").problems(cleaned, 2000), [])

    def test_an_ad_draft_under_a_live_ad_set_fills_new_ad(self):
        payload, notes = am_drafts.to_ad_spec(root(rows_of(video_ad("970", LIVE_ADSET))), {FORM})
        self.assertEqual((payload, notes), ({"adset_id": LIVE_ADSET, "template_ad_id": "", "name": "Portal 2 - Email orders",
                                             "title": "No more retyping orders", "body": "Email orders get read in automatically.",
                                             "cta_type": "SIGN_UP", "form_id": FORM, "media": {"kind": "video", "video_id": VIDEO}}, []))
        self.assertEqual(creative_build.problems(payload, ["SIGN_UP"]), [])


class EditRowsTests(unittest.TestCase):
    def node(self, values):
        return root(am_drafts.normalize({"ad_drafts": [{**raw(LIVE_CAMPAIGN, "campaign", {}, action="update"), "values": values}]}))

    LIVE = {"daily_budget_cents": 2000, "name": "Edge Bourne - Free intro call - Leads", "status": "ACTIVE"}

    def test_a_budget_and_a_name_staged_in_ads_manager(self):
        node = self.node({"daily_budget": {"old": 2000, "new": 2500}, "name": {"old": "Edge Bourne - Free intro call - Leads", "new": "Intro call (Nov)"}})
        self.assertEqual(am_drafts.edit_rows(node, self.LIVE), [
            {"field": "daily_budget", "label": "Daily budget", "kind": "money", "old": 2000, "new": 2500, "now": 2000, "stale": False, "apply": "budget", "applied": None},
            {"field": "name", "label": "Name", "kind": "text", "old": "Edge Bourne - Free intro call - Leads", "new": "Intro call (Nov)",
             "now": "Edge Bourne - Free intro call - Leads", "stale": False, "apply": "edit", "applied": None}])

    def test_a_budget_changed_since_the_draft_is_stale(self):
        node = self.node({"daily_budget": {"old": 2000, "new": 2500}})
        self.assertEqual([(r["now"], r["stale"]) for r in am_drafts.edit_rows(node, {**self.LIVE, "daily_budget_cents": 2200})], [(2200, True)])

    def test_how_each_setting_is_applied(self):
        node = self.node({"status": {"old": "ACTIVE", "new": "PAUSED"}, "name": {"new": "x"}, "daily_budget": {"new": 2500},
                          "bid_strategy": {"new": "COST_CAP"}})
        self.assertEqual({r["field"]: r["apply"] for r in am_drafts.edit_rows(node, {**self.LIVE, "daily_budget_cents": None}, edit_fields={"name"})},
                         {"status": "status", "name": "edit", "daily_budget": "manager", "bid_strategy": "manager"})

    def test_rows_keep_a_fixed_order_whatever_order_the_fields_were_stored_in(self):
        node = self.node({"name": {"new": "x"}, "status": {"new": "PAUSED"}, "daily_budget": {"new": 2500}})
        self.assertEqual([r["field"] for r in am_drafts.edit_rows(node, self.LIVE)], ["daily_budget", "name", "status"])

    def test_a_staged_edit_is_named_by_what_it_changes(self):
        node = self.node({"name": {"old": "Intro call", "new": "Intro call (Nov)"}})
        self.assertEqual((am_drafts.name_of(node), am_drafts.name_of(self.node({"daily_budget": {"new": 1}}), "Live name"),
                          am_drafts.name_of(root(rows_of(campaign("900", name="Brand new"))))), ("Intro call", "Live name", "Brand new"))

    def test_an_applied_setting_carries_its_change(self):
        node = {**self.node({"daily_budget": {"old": 2000, "new": 2500}}), "applied": {"daily_budget": 41}}
        self.assertEqual(am_drafts.edit_rows(node, self.LIVE)[0]["applied"], 41)


class InboxEventsTests(unittest.TestCase):
    RULES = {"draft_new": {"on": True}, "draft_problems": {"on": True}}

    def events(self, before, after, complete=True, rules=None):
        return am_drafts.inbox_events({r["draft_id"]: r for r in before}, after, complete, rules or self.RULES, TODAY, LA)

    def test_a_new_draft_is_one_fyi_item_once(self):
        d = am_drafts.normalize(REAL)
        found, resolve = self.events([], d)
        self.assertEqual(([(a["rule"], a["entity_id"], a["key"], a["level"], a["kind"], a["title"], a["href"]) for a in found], resolve),
                         ([("draft_new", "120252756936450312", "draft_new:120252756936450312", "info", "event",
                            "New draft in Ads Manager: “Edge Bourne - Dashboards with AI - Leads”",
                            "/ads.html?level=campaign&view=drafts#draft=120252756936450312")], []))
        self.assertEqual(self.events(d, d), ([], []))

    def test_a_draft_the_console_finished_or_a_rule_switched_off_raises_nothing(self):
        d = [{**am_drafts.normalize(REAL)[0], "finished_at": datetime(2026, 11, 13, tzinfo=timezone.utc)}]
        self.assertEqual(self.events([], d), ([], []))
        self.assertEqual(self.events([], am_drafts.normalize(REAL), rules={"draft_new": {"on": False}, "draft_problems": {"on": True}}), ([], []))

    def test_problems_are_a_condition_until_they_clear_or_the_draft_is_gone(self):
        bad = rows_of(raw("9", "campaign", {"name": "Weekly"}, errors=[{"message": "Choose a Facebook Page for this ad."}, {"message": "Add an ad"}]))
        found, _ = self.events(bad, bad)
        self.assertEqual([(a["rule"], a["kind"], a["key"], a["title"], a["lines"]) for a in found],
                         [("draft_problems", "condition", "draft_problems:9:2026-11-13", "Meta has problems with your draft “Weekly”",
                           ["Choose a Facebook Page for this ad.", "+1 more"])])
        cleared = rows_of(raw("9", "campaign", {"name": "Weekly"}))
        self.assertEqual(self.events(bad, cleared), ([], ["9"]))
        self.assertEqual(self.events(bad, [], complete=True), ([], ["9"]))

    def test_one_item_per_draft_with_the_problems_of_everything_under_it(self):
        rows = rows_of(campaign("900", name="Weekly"), adset("901", "900"), image_ad("902", "901"))
        rows[2]["problems"] = [{"message": "Pick a Page for this ad", "field": None}]
        found, _ = self.events([], rows)
        self.assertEqual([(a["rule"], a["entity_id"], a["lines"][0] if a["rule"] == "draft_problems" else "") for a in found],
                         [("draft_new", "900", ""), ("draft_problems", "900", "Pick a Page for this ad")])
        self.assertEqual(am_drafts.root_problems(rows), {"900": [{"message": "Pick a Page for this ad", "field": None}]})

    def test_a_partial_read_never_calls_a_draft_gone(self):
        bad = rows_of(raw("9", "campaign", {"name": "Weekly"}, errors=[{"message": "Choose a Page"}]))
        self.assertEqual(self.events(bad, [], complete=False), ([], []))


class WordsTests(unittest.TestCase):
    def test_what_a_draft_is_and_what_it_holds(self):
        node = root(am_drafts.normalize(REAL) + rows_of(adset("313", "120252756936450312")))
        self.assertEqual((am_drafts.what_words(node, "USD"), am_drafts.holds_words(node)),
                         ("New campaign · Leads · $20.00 a day · lowest cost", "1 ad set · Riverside, CA + 25 mi, ages 25–65 · 0 ads"))

    def test_an_edit_and_a_standalone_ad_set(self):
        edit = root(rows_of(raw(LIVE_CAMPAIGN, "campaign", {"daily_budget": 2500}, action="update")))
        alone = root(rows_of(adset("960", LIVE_CAMPAIGN)))
        self.assertEqual((am_drafts.what_words(edit, "USD"), am_drafts.what_words(alone, "USD"), am_drafts.holds_words(alone)),
                         ("Changes to a campaign that's running", "New ad set in a running campaign", "Riverside, CA + 25 mi, ages 25–65 · 0 ads"))

    def test_ads_manager_links_are_built_from_digits_only(self):
        self.assertEqual([am_drafts.manager_url("1025971549903293", "campaign", "900"), am_drafts.manager_url("1025971549903293", "adset", "901"),
                          am_drafts.manager_url("1025971549903293", "ad", "902"), am_drafts.manager_url("1025", "campaign", "9 OR 1"),
                          am_drafts.manager_url("act_x", "ad", "1")], [
            "https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=1025971549903293&selected_campaign_ids=900",
            "https://adsmanager.facebook.com/adsmanager/manage/adsets?act=1025971549903293&selected_adset_ids=901",
            "https://adsmanager.facebook.com/adsmanager/manage/ads?act=1025971549903293&selected_ad_ids=902", None, None])


if __name__ == "__main__":
    unittest.main()
