import unittest

import placements as pl

PAGE, IG, FORM = "61596354777753", "17841400000000000", "1132280359202136"
FEED_VIDEO, VERTICAL_VIDEO = "2015174525716800", "2015174525716803"
# The shape of the running Edge Bourne ads: single video, Instant Form behind "Book now".
STORY = {"page_id": PAGE, "instagram_user_id": IG,
         "video_data": {"video_id": FEED_VIDEO, "image_url": "https://x/feed.jpg", "message": "Your tools don't talk.",
                        "title": "One simple system", "link_description": "Free intro call",
                        "call_to_action": {"type": "BOOK_NOW", "value": {"lead_gen_form_id": FORM, "link": "http://fb.me/"}}}}
VERTICAL = {"video_id": VERTICAL_VIDEO, "thumbnail_url": "https://x/vertical.jpg"}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.story, self.feed = pl.build(STORY, VERTICAL)

    def test_the_story_keeps_only_the_page_and_instagram_identity(self):
        self.assertEqual(self.story, {"page_id": PAGE, "instagram_user_id": IG})

    def test_both_videos_are_labelled_with_their_thumbnails(self):
        self.assertEqual(self.feed["videos"], [
            {"video_id": FEED_VIDEO, "thumbnail_url": "https://x/feed.jpg", "adlabels": [{"name": pl.FEED}]},
            {"video_id": VERTICAL_VIDEO, "thumbnail_url": "https://x/vertical.jpg", "adlabels": [{"name": pl.VERTICAL}]}])

    def test_words_and_form_button_are_carried_over_unchanged(self):
        self.assertEqual((self.feed["bodies"], self.feed["titles"], self.feed["descriptions"], self.feed["call_to_action_types"],
                          self.feed["call_to_actions"], self.feed["link_urls"]),
                         ([{"text": "Your tools don't talk."}], [{"text": "One simple system"}], [{"text": "Free intro call"}], ["BOOK_NOW"],
                          [{"type": "BOOK_NOW", "value": {"lead_gen_form_id": FORM, "link": "http://fb.me/"}}],
                          [{"website_url": "http://fb.me/"}]))

    def test_reels_and_stories_get_the_vertical_video_first_and_everything_else_the_feed_video(self):
        rules = self.feed["asset_customization_rules"]
        self.assertEqual([(r["priority"], r["video_label"]["name"], r["customization_spec"]) for r in rules], [
            (1, pl.VERTICAL, {"publisher_platforms": ["facebook", "instagram"], "facebook_positions": ["story", "facebook_reels"],
                              "instagram_positions": ["story", "reels"]}),
            (2, pl.FEED, {"publisher_platforms": ["facebook", "instagram", "messenger", "audience_network"]})])

    def test_it_is_a_placement_customized_single_video(self):
        self.assertEqual((self.feed["ad_formats"], self.feed["optimization_type"]), (["SINGLE_VIDEO"], "PLACEMENT"))


class RefusalTests(unittest.TestCase):
    def test_an_image_ad_is_refused(self):
        with self.assertRaisesRegex(ValueError, "video"):
            pl.build({"page_id": PAGE, "link_data": {"image_hash": "h"}}, VERTICAL)

    def test_the_same_video_twice_is_refused(self):
        with self.assertRaisesRegex(ValueError, "same video"):
            pl.build(STORY, {"video_id": FEED_VIDEO})

    def test_a_creative_that_already_has_placement_media_is_refused(self):
        self.assertEqual((pl.has_placements({"asset_feed_spec": {"videos": []}}), pl.has_placements({"object_story_spec": STORY})),
                         (True, False))


class ReadBackTests(unittest.TestCase):
    def made(self, **over):
        _, feed = pl.build(STORY, VERTICAL)
        feed = {**feed, **over}
        return {"object_story_spec": {"page_id": PAGE}, "asset_feed_spec": feed}

    def test_a_faithful_copy_passes(self):
        self.assertIsNone(pl.readback_problem(STORY, self.made(), VERTICAL_VIDEO))

    def test_a_copy_without_the_lead_form_is_caught(self):
        self.assertRegex(pl.readback_problem(STORY, self.made(call_to_actions=[{"type": "BOOK_NOW"}]), VERTICAL_VIDEO), "form")

    def test_a_copy_with_another_form_is_caught(self):
        other = [{"type": "BOOK_NOW", "value": {"lead_gen_form_id": "999"}}]
        self.assertRegex(pl.readback_problem(STORY, self.made(call_to_actions=other), VERTICAL_VIDEO), "form")

    def test_a_copy_missing_the_vertical_video_is_caught(self):
        self.assertRegex(pl.readback_problem(STORY, self.made(videos=[{"video_id": FEED_VIDEO}]), VERTICAL_VIDEO), "9:16")

    def test_an_ad_without_a_form_needs_none(self):
        story = {**STORY, "video_data": {**STORY["video_data"], "call_to_action": {"type": "LEARN_MORE", "value": {"link": "https://e.com"}}}}
        _, feed = pl.build(story, VERTICAL)
        self.assertIsNone(pl.readback_problem(story, {"asset_feed_spec": feed}, VERTICAL_VIDEO))

    def test_form_ids_are_found_anywhere_in_a_spec(self):
        self.assertEqual(pl.form_ids({"a": [{"b": {"lead_gen_form_id": 7}}], "c": {"lead_gen_form_id": "8"}}), {"7", "8"})


class DescribeTests(unittest.TestCase):
    def test_says_what_meta_stored_for_the_videos(self):
        made = {"id": "9", "asset_feed_spec": {"videos": [{"video_id": "1", "thumbnail_url": "x"}], "bodies": [{"text": "hi"}]}, "object_story_spec": {"page_id": "2"}}
        self.assertEqual(pl.describe(made), 'feed keys: bodies, videos; videos: [{"thumbnail_url": "x", "video_id": "1"}]; story keys: page_id')

    def test_says_when_meta_stored_no_feed_at_all(self):
        self.assertEqual(pl.describe({"id": "9"}), "feed keys: none; videos: []; story keys: none")


if __name__ == "__main__":
    unittest.main()
