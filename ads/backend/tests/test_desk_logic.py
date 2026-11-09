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

    def test_payload_only_kept_on_creative_proposals(self):
        self.assertIsNone(desk_api.clean_proposal({"kind": "budget", "title": "x", "payload": dict(self.BASE)})["payload"])


class KeyHashTests(unittest.TestCase):
    def test_hash_is_stable_and_not_the_key(self):
        token = "ebdesk_example"
        self.assertEqual((desk_api.key_hash(token) == desk_api.key_hash(token), token in desk_api.key_hash(token)),
                         (True, False))


if __name__ == "__main__":
    unittest.main()
