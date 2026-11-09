import unittest

import ads_api
import sync

FORM_CTA = {"type": "BOOK_TRAVEL", "value": {"lead_gen_form_id": "1132280359202136"}}
VIDEO_TEMPLATE = {"page_id": "1404203629446490", "instagram_user_id": "178",
                  "video_data": {"video_id": "old", "image_url": "old.jpg", "message": "old", "title": "old",
                                 "call_to_action": FORM_CTA}}
CAMPAIGN = {"id": "c1", "daily_budget_cents": 2000}
AD = {"id": "a1", "daily_budget_cents": None}


class ParseDollarsTests(unittest.TestCase):
    def test_reads_the_amounts_people_write(self):
        cases = {"$24/day": 2400, "24": 2400, "$1,250.50 per day": 125050, "about $19.99": 1999, "$0.5": 50}
        self.assertEqual({k: ads_api.parse_dollars(k) for k in cases}, cases)

    def test_no_amount_gives_none(self):
        self.assertEqual([ads_api.parse_dollars(v) for v in (None, "", "keep it")], [None, None, None])


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
        cases = [self.prop(kind="creative"), self.prop(proposed_value="ARCHIVED"), self.prop(entity_id=None),
                 self.prop(kind="budget", proposed_value="$0.50/day")]
        self.assertEqual([ads_api.proposal_action(p, CAMPAIGN) for p in cases], [None] * 4)

    def test_no_entity_means_no_action(self):
        self.assertIsNone(ads_api.proposal_action(self.prop(), None))


class CreativeProposalTests(unittest.TestCase):
    def test_creative_payload_becomes_a_create_action(self):
        payload = {"template_ad_id": "a1", "title": "T", "body": "B", "media": {"kind": "same"}}
        self.assertEqual(ads_api.proposal_action({"kind": "creative", "payload": payload, "entity_id": None}, None),
                         ("create", payload))

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


if __name__ == "__main__":
    unittest.main()
