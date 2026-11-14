import unittest

import ads_api
import sync

FORM_CTA = {"type": "BOOK_TRAVEL", "value": {"lead_gen_form_id": "1132280359202136"}}
VIDEO_TEMPLATE = {"page_id": "1404203629446490", "instagram_user_id": "178",
                  "video_data": {"video_id": "old", "image_url": "old.jpg", "message": "old", "title": "old",
                                 "call_to_action": FORM_CTA}}
CAMPAIGN = {"id": "c1", "daily_budget_cents": 2000}
AD = {"id": "a1", "daily_budget_cents": None}


class ProposalActionTests(unittest.TestCase):
    def prop(self, **kw):
        return {"kind": "status", "entity_id": "a1", "proposed_value": "PAUSED", **kw}

    def test_status_words_map_to_meta_statuses(self):
        values = {"PAUSED": "PAUSED", "paused": "PAUSED", "off": "PAUSED", "On": "ACTIVE", "ACTIVE": "ACTIVE"}
        self.assertEqual({v: ads_api.proposal_action(self.prop(proposed_value=v), AD) for v in values},
                         {v: ("status", s) for v, s in values.items()})

    def test_budget_applies_only_where_the_budget_lives(self):
        p = self.prop(kind="budget", proposed_value="$24/day")
        self.assertEqual((ads_api.proposal_action(p, CAMPAIGN), ads_api.proposal_action(p, AD)), (("budget", 2400), None))

    def test_things_the_dashboard_cannot_apply_return_none(self):
        cases = [self.prop(kind="creative"), self.prop(proposed_value="ARCHIVED"), self.prop(entity_id=None)]
        self.assertEqual([ads_api.proposal_action(p, CAMPAIGN) for p in cases], [None] * 3)

    def test_budget_reads_the_new_amount_not_the_first_number(self):
        values = ["+20% to $24/day", "from $20 to $24", "$20 → $24"]
        self.assertEqual([ads_api.proposal_action(self.prop(kind="budget", proposed_value=v), CAMPAIGN) for v in values],
                         [("budget", 2400)] * 3)

    def test_an_unclear_budget_is_flagged_not_applied(self):
        kind, why = ads_api.proposal_action(self.prop(kind="budget", proposed_value="Raise 2x or more"), CAMPAIGN)
        self.assertEqual((kind, "isn't one clear amount" in why), ("unclear", True))

    def test_a_structured_amount_is_used_when_the_words_agree(self):
        p = self.prop(kind="budget", proposed_value="Set to 2x ($40/day)", payload={"proposed_cents": 4000})
        self.assertEqual(ads_api.proposal_action(p, CAMPAIGN), ("budget", 4000))

    def test_a_structured_amount_the_words_disagree_with_is_refused(self):
        p = self.prop(kind="budget", proposed_value="+20% to $24/day", payload={"proposed_cents": 2300})
        self.assertEqual(ads_api.proposal_action(p, CAMPAIGN)[0], "unclear")

    def test_a_creative_proposal_is_checked_against_the_ad_it_changes(self):
        # A3-49/A3-78: entity_id may point at another campaign's ad set; the write goes to template_ad_id.
        cases = [({"kind": "creative", "entity_id": "s9", "payload": {"template_ad_id": "a1"}}, "a1"),
                 ({"kind": "budget", "entity_id": "c1", "payload": {"proposed_cents": 2400}}, "c1"),
                 ({"kind": "creative", "entity_id": None, "payload": None}, None)]
        self.assertEqual([ads_api.proposal_target_id(p) for p, _ in cases], [want for _, want in cases])

    def test_no_entity_means_no_action(self):
        self.assertIsNone(ads_api.proposal_action(self.prop(), None))


class CreativeProposalTests(unittest.TestCase):
    def test_creative_payload_becomes_a_create_action(self):
        payload = {"template_ad_id": "a1", "title": "T", "body": "B", "media": {"kind": "same"}}
        self.assertEqual(ads_api.proposal_action({"kind": "creative", "payload": payload, "entity_id": None}, None),
                         ("create", payload))

    def test_update_payload_becomes_a_vertical_action_on_the_ad(self):
        payload = {"template_ad_id": "a1", "update_ad": True, "vertical": {"video_id": "77"}}
        self.assertEqual(ads_api.proposal_action({"kind": "creative", "payload": payload, "entity_id": None}, AD),
                         ("vertical", payload))

    def test_update_payload_with_words_becomes_an_update_of_that_ad(self):
        payload = {"template_ad_id": "a1", "update_ad": True, "title": "T", "body": "B", "media": {"kind": "same"}}
        self.assertEqual(ads_api.proposal_action({"kind": "creative", "payload": payload, "entity_id": None}, AD),
                         ("update", payload))

    def test_either_kind_can_be_applied_the_other_way(self):
        words = {"template_ad_id": "a1", "title": "T", "body": "B", "media": {"kind": "same"}}
        update, new = {**words, "update_ad": True}, words
        cases = [(update, "new", "create"), (new, "update", "update"), (update, "update", "update"), (new, "new", "create"),
                 (update, None, "update"), (new, None, "create"), (new, "nonsense", "create")]
        self.assertEqual([ads_api.proposal_action({"kind": "creative", "payload": p, "entity_id": None}, AD, a)[0] for p, a, _ in cases],
                         [want for _, _, want in cases])

    def test_a_vertical_update_cannot_become_a_new_ad(self):
        payload = {"template_ad_id": "a1", "update_ad": True, "vertical": {"video_id": "77"}}
        self.assertEqual(ads_api.proposal_action({"kind": "creative", "payload": payload, "entity_id": None}, AD, "new"),
                         ("vertical", payload))

    def test_creative_without_payload_is_not_applied(self):
        self.assertIsNone(ads_api.proposal_action({"kind": "creative", "payload": None, "entity_id": "a1"}, AD))


class TemplateMediaTests(unittest.TestCase):
    def test_reads_video_and_image_from_a_story_spec(self):
        image_spec = {"link_data": {"image_hash": "h9"}}
        self.assertEqual((ads_api.template_media(VIDEO_TEMPLATE), ads_api.template_media(image_spec), ads_api.template_media({})),
                         ({"kind": "video", "video_id": "old", "thumbnail_url": "old.jpg"}, {"kind": "image", "hash": "h9"}, None))


class BuildStorySpecTests(unittest.TestCase):
    def test_video_keeps_page_identity_and_lead_form(self):
        spec = ads_api.build_story_spec(VIDEO_TEMPLATE, {"kind": "video", "video_id": "v2", "thumbnail_url": "t.jpg"},
                                        "New body", "New title")
        self.assertEqual(spec, {"page_id": "1404203629446490", "instagram_user_id": "178",
                                "video_data": {"video_id": "v2", "image_url": "t.jpg", "message": "New body",
                                               "title": "New title", "call_to_action": FORM_CTA}})

    def test_image_from_a_video_template_becomes_link_data_with_the_same_button(self):
        spec = ads_api.build_story_spec(VIDEO_TEMPLATE, {"kind": "image", "hash": "h1"}, "B", "T", "SIGN_UP")
        self.assertEqual(spec["link_data"], {"image_hash": "h1", "message": "B", "name": "T", "link": "http://fb.me/",
                                             "call_to_action": {"type": "SIGN_UP", "value": FORM_CTA["value"]}})

    def test_a_chosen_form_replaces_the_templates_form_and_keeps_the_rest_of_the_button(self):
        spec = ads_api.build_story_spec(VIDEO_TEMPLATE, {"kind": "video", "video_id": "v2"}, "B", "T", form_id="555")
        self.assertEqual(spec["video_data"]["call_to_action"],
                         {**FORM_CTA, "value": {**FORM_CTA["value"], "lead_gen_form_id": "555"}})
        self.assertNotEqual(FORM_CTA["value"].get("lead_gen_form_id"), "555")

    def test_template_is_not_modified(self):
        before = repr(VIDEO_TEMPLATE)
        ads_api.build_story_spec(VIDEO_TEMPLATE, {"kind": "image", "hash": "h"}, "B", "T", "SIGN_UP")
        self.assertEqual(repr(VIDEO_TEMPLATE), before)


class PreviewParsingTests(unittest.TestCase):
    def test_reads_src_and_size_from_metas_iframe(self):
        body = '<iframe src="https://www.facebook.com/ads/api/preview_iframe.php?d=AQ&amp;t=AQ" width="274" height="690"></iframe>'
        self.assertEqual((ads_api.preview_src(body), ads_api.preview_size(body)),
                         ("https://www.facebook.com/ads/api/preview_iframe.php?d=AQ&t=AQ", (274, 690)))


class SummarizeTargetingTests(unittest.TestCase):
    def test_edge_bourne_style_targeting(self):
        t = {"age_min": 25, "age_max": 65,
             "geo_locations": {"custom_locations": [{"radius": 50, "distance_unit": "mile"}] * 4},
             "flexible_spec": [{"interests": [{"name": "Small business owners"}], "behaviors": [{"name": "Business page admins"}]}],
             "targeting_automation": {"advantage_audience": 1}}
        self.assertEqual(sync.summarize_targeting(t),
                         "Ages 25–65+ · 4 areas (50 miles) · Hints: Small business owners, Business page admins · Advantage+ audience")

    def test_country_only_and_empty(self):
        self.assertEqual((sync.summarize_targeting({"geo_locations": {"countries": ["US"]}}), sync.summarize_targeting(None)),
                         ("US", None))

    def test_budget_strings_from_meta(self):
        self.assertEqual([sync.cents(v) for v in ("2000", "0", None, "")], [2000, None, None, None])


class RemovalProblemTest(unittest.TestCase):
    OFF = {"name": "TEST e - N3 image upload", "status": "PAUSED", "effective_status": "PAUSED"}
    ADMIN, TEAMMATE = {"role": "admin"}, {"role": "member"}

    def test_admin_may_archive_an_ad_that_is_off(self):
        self.assertIsNone(ads_api.removal_problem(self.ADMIN, self.OFF, "archive", None))

    def test_delete_needs_the_exact_name_typed(self):
        cases = [(self.OFF["name"], None), ("  " + self.OFF["name"] + " ", None),
                 ("TEST e", "Type the ad's name exactly to delete it"), (None, "Type the ad's name exactly to delete it")]
        for typed, expected in cases:
            self.assertEqual(ads_api.removal_problem(self.ADMIN, self.OFF, "delete", typed), expected, typed)

    def test_refused_cases(self):
        on = {**self.OFF, "status": "ACTIVE", "effective_status": "ACTIVE"}
        archived = {**self.OFF, "status": "ARCHIVED", "effective_status": "ARCHIVED"}
        deleted = {**self.OFF, "status": "DELETED", "effective_status": "DELETED"}
        cases = [
            (self.TEAMMATE, self.OFF, "archive", "Only an admin can archive or delete ads"),
            (self.ADMIN, on, "archive", "Switch the ad off first"),
            (self.ADMIN, on, "delete", "Switch the ad off first"),
            (self.ADMIN, archived, "archive", "It's already archived"),
            (self.ADMIN, deleted, "delete", "It's already deleted"),
            (self.ADMIN, deleted, "archive", "It's already deleted"),
            (self.ADMIN, self.OFF, "rename", "Unknown action"),
        ]
        for user, row, action, expected in cases:
            self.assertEqual(ads_api.removal_problem(user, row, action, row["name"]), expected, (action, row["status"]))

    def test_an_archived_ad_can_still_be_deleted(self):
        archived = {**self.OFF, "status": "ARCHIVED", "effective_status": "ARCHIVED"}
        self.assertIsNone(ads_api.removal_problem(self.ADMIN, archived, "delete", archived["name"]))

    def test_campaigns_and_ad_sets_follow_the_same_rules_in_their_own_words(self):
        on = {**self.OFF, "status": "ACTIVE"}
        self.assertEqual([ads_api.removal_problem(self.ADMIN, on, "archive", None, "campaign"),
                          ads_api.removal_problem(self.ADMIN, self.OFF, "delete", "wrong", "adset"),
                          ads_api.removal_problem(self.TEAMMATE, self.OFF, "delete", self.OFF["name"], "campaign"),
                          ads_api.removal_problem(self.ADMIN, self.OFF, "delete", self.OFF["name"], "adset")],
                         ["Switch the campaign off first", "Type the ad set's name exactly to delete it",
                          "Only an admin can archive or delete campaigns", None])


if __name__ == "__main__":
    unittest.main()


class SpendLimitActionTests(unittest.TestCase):
    """FU-B: accepting a spend_limit suggestion: words and cents must agree; per day reads as a budget."""

    def act(self, words, payload):
        return ads_api.proposal_action({"kind": "spend_limit", "entity_id": "act_1025", "proposed_value": words, "payload": payload}, None)

    def test_agreeing_amount(self):
        self.assertEqual(self.act("$200", {"proposed_cents": 20000}), ("spend_limit", 20000))

    def test_daily_words_and_disagreement_are_unclear(self):
        daily, wrong = self.act("$200/day", {"proposed_cents": 20000}), self.act("$200", {"proposed_cents": 25000})
        self.assertEqual((daily[0], "daily budget" in daily[1], wrong[0], "isn't what its words say" in wrong[1]), ("unclear", True, "unclear", True))
