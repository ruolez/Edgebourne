import unittest

import desk_api

FULL = {"kind": "budget", "title": "Raise the ad set budget", "entity_type": "adset", "entity_id": "120",
        "entity_name": "SoCal business owners", "field": "daily_budget", "current_value": "$20/day",
        "proposed_value": "$24/day", "rationale": "7-day CPL $31 vs $60 target", "expected": "more leads",
        "rollback": "$20/day"}


class CleanProposalTests(unittest.TestCase):
    def test_keeps_every_known_field_trimmed(self):
        padded = {k: f"  {v}  " for k, v in FULL.items()}
        self.assertEqual(desk_api.clean_proposal(padded), {**FULL, "payload": None})

    def test_unknown_kind_becomes_other_and_extra_keys_are_dropped(self):
        out = desk_api.clean_proposal({"kind": "delete_everything", "title": "x", "sql": "DROP TABLE"})
        self.assertEqual((out["kind"], "sql" in out), ("other", False))

    def test_blank_values_become_none(self):
        self.assertIsNone(desk_api.clean_proposal({"title": "x", "rationale": "   "})["rationale"])

    def test_long_title_is_cut_to_200(self):
        self.assertEqual(len(desk_api.clean_proposal({"title": "a" * 500})["title"]), 200)


class CleanPayloadTests(unittest.TestCase):
    BASE = {"template_ad_id": "123", "title": "Type it once", "body": "Your books and shop software don't talk."}

    def test_creative_payload_defaults_to_same_media(self):
        out = desk_api.clean_proposal({"kind": "creative", "title": "New headline", "payload": dict(self.BASE)})
        self.assertEqual(out["payload"], {**self.BASE, "adset_id": None, "name": None, "cta_type": None,
                                          "media": {"kind": "same"}, "preview_url": None})

    def test_new_video_media_is_kept(self):
        out = desk_api.clean_payload({**self.BASE, "media": {"kind": "video", "video_id": "987"}})
        self.assertEqual(out["media"], {"kind": "video", "video_id": "987"})

    def test_media_without_its_id_falls_back_to_same(self):
        self.assertEqual(desk_api.clean_payload({**self.BASE, "media": {"kind": "image"}})["media"], {"kind": "same"})

    def test_payload_without_words_is_dropped(self):
        self.assertIsNone(desk_api.clean_payload({"template_ad_id": "123", "title": "x"}))

    def test_update_payload_needs_no_words_only_the_ad_and_its_vertical_video(self):
        raw = {"template_ad_id": "120252690325970312", "update_ad": True, "vertical": {"video_id": "2015174525716803", "x": 1},
               "name": "N1 · 9:16 for Reels", "title": "ignored", "media": {"kind": "video", "video_id": "1"}}
        self.assertEqual(desk_api.clean_payload(raw), {"template_ad_id": "120252690325970312", "update_ad": True,
                                                       "vertical": {"video_id": "2015174525716803"}, "name": "N1 · 9:16 for Reels"})

    def test_a_vertical_cover_keeps_a_real_image_hash_and_drops_a_malformed_one(self):
        good, bad = "0123456789abcdef0123456789abcdef", "../x?y=1"
        out = [desk_api.clean_payload({"template_ad_id": "1", "update_ad": True, "vertical": {"video_id": "2", "image_hash": h}})["vertical"]
               for h in (good, bad)]
        self.assertEqual(out, [{"video_id": "2", "image_hash": good}, {"video_id": "2"}])

    def test_update_payload_with_a_bad_video_id_is_dropped(self):
        self.assertEqual([desk_api.clean_payload({"template_ad_id": "1", "update_ad": True, "vertical": v})
                          for v in ({"video_id": "abc"}, {}, "2015")], [None, None, None])

    def test_update_flag_must_be_a_real_true(self):
        self.assertIsNone(desk_api.clean_payload({"template_ad_id": "1", "update_ad": "yes", "vertical": {"video_id": "2"}}))

    def test_words_can_update_the_ad_instead_of_making_a_new_one(self):
        self.assertEqual(desk_api.clean_payload({**self.BASE, "update_ad": True})["update_ad"], True)

    def test_a_plain_payload_carries_no_update_or_new_ad_flag(self):
        out = desk_api.clean_payload(dict(self.BASE))
        self.assertEqual(("update_ad" in out, "new_ad" in out), (False, False))

    def test_new_ad_flag_is_kept_when_claude_means_a_separate_ad(self):
        self.assertEqual(desk_api.clean_payload({**self.BASE, "new_ad": True})["new_ad"], True)

    def test_a_polish_or_render_of_an_ad_updates_that_ad(self):
        payload = {"template_ad_id": "a1", "title": "T", "body": "B"}
        for kind in ("polish", "render"):
            self.assertEqual(desk_api.stamp_update(dict(payload), {"kind": kind, "options": {"ad_id": "a1"}}), {**payload, "update_ad": True})

    def test_other_runs_and_other_ads_and_separate_ads_are_left_alone(self):
        payload = {"template_ad_id": "a1", "title": "T", "body": "B"}
        cases = [(payload, {"kind": "creative", "options": {"ad_id": "a1"}}),
                 (payload, {"kind": "polish", "options": {"ad_id": "other"}}),
                 (payload, {"kind": "polish", "options": None}),
                 ({**payload, "new_ad": True}, {"kind": "render", "options": {"ad_id": "a1"}})]
        self.assertEqual([desk_api.stamp_update(dict(p), t) for p, t in cases], [p for p, _ in cases])

    def test_stamping_leaves_an_empty_payload_empty(self):
        self.assertIsNone(desk_api.stamp_update(None, {"kind": "polish", "options": {"ad_id": "a1"}}))

    def test_a_budget_proposal_keeps_its_amount_in_cents(self):
        cases = [(2400, {"proposed_cents": 2400}), ("2400", {"proposed_cents": 2400}), (24.5, None), ("$24", None), (0, None), (True, None)]
        self.assertEqual([desk_api.clean_proposal({"kind": "budget", "title": "x", "payload": {"proposed_cents": c}})["payload"] for c, _ in cases],
                         [want for _, want in cases])

    def test_payload_only_kept_on_creative_proposals(self):
        self.assertIsNone(desk_api.clean_proposal({"kind": "budget", "title": "x", "payload": dict(self.BASE)})["payload"])


class KeyHashTests(unittest.TestCase):
    def test_hash_is_stable_and_not_the_key(self):
        token = "ebdesk_example"
        self.assertEqual((desk_api.key_hash(token) == desk_api.key_hash(token), token in desk_api.key_hash(token)),
                         (True, False))


if __name__ == "__main__":
    unittest.main()
