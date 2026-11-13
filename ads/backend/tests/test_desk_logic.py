import unittest

import desk_api

FULL = {"kind": "budget", "title": "Raise the ad set budget", "entity_type": "adset", "entity_id": "120",
        "entity_name": "SoCal business owners", "field": "daily_budget", "current_value": "$20/day",
        "proposed_value": "$24/day", "rationale": "7-day CPL $31 vs $60 target", "expected": "more leads",
        "rollback": "$20/day"}


class CleanProposalTests(unittest.TestCase):
    def test_keeps_every_known_field_trimmed(self):
        padded = {k: f"  {v}  " for k, v in FULL.items()}
        self.assertEqual(desk_api.clean_proposal(padded), {**FULL, "payload": None, "expect": None})

    def test_d3_a_structured_expectation_is_kept(self):
        out = desk_api.clean_proposal({**FULL, "expect": {"metric": "cpl", "op": "<", "cents": 4000, "days": 14}})
        self.assertEqual(out["expect"], {"metric": "cpl", "op": "<", "cents": 4000, "days": 14})

    def test_d3_without_one_the_expected_text_is_read(self):
        out = desk_api.clean_proposal({**FULL, "expected": "CPL under $40 within 7 days", "expect": {"metric": "roas"}})
        self.assertEqual(out["expect"], {"metric": "cpl", "op": "<", "cents": 4000, "days": 7})

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


class ClaimRefusalTests(unittest.TestCase):
    """A Claude run carries the pass of the request it was started for (audit A3-7)."""
    RUN = {"id": 5, "status": "running", "account_id": 2}

    def test_a_run_may_use_its_own_request_even_after_it_finished(self):
        bound = [self.RUN, {**self.RUN, "status": "done"}, {**self.RUN, "status": "cancelled"}]
        self.assertEqual([desk_api.claim_refusal("task", 5, b, True) for b in bound], [None, None, None])

    def test_a_run_cannot_touch_another_request_or_pick_up_work(self):
        cases = [("task", 6, False), ("task", 6, True), ("pick", None, False)]
        self.assertEqual([desk_api.claim_refusal(r, p, self.RUN, locked) is not None for r, p, locked in cases], [True, True, True])

    def test_account_wide_calls_only_while_the_run_is_open(self):
        statuses = ["claimed", "running", "done", "failed", "cancelled", "queued"]
        self.assertEqual([desk_api.claim_refusal("account", None, {**self.RUN, "status": s}, False) is None for s in statuses],
                         [True, True, False, False, False, False])

    def test_without_a_pass_a_request_a_run_holds_is_closed(self):
        cases = [("task", 7, False), ("task", 7, True), ("account", None, False), ("pick", None, False)]
        self.assertEqual([desk_api.claim_refusal(r, p, None, locked) is None for r, p, locked in cases], [True, False, True, True])


class ClaimSkipTests(unittest.TestCase):
    VERSIONS = [(0, 0), (1, 6), (1, 7), (1, 9), (2, 0)]

    def test_an_older_mac_helper_leaves_advice_runs_and_follow_ups_in_line(self):
        skips = [desk_api.claim_skip(v) for v in self.VERSIONS]
        self.assertEqual([("kind <> 'advice'" in s, "options->>'reply' IS NULL" in s) for s in skips],
                         [(True, True), (True, True), (False, True), (False, False), (False, False)])

    def test_a_helper_without_passes_runs_only_what_the_owners_wrote(self):
        """Before 2.0 a run has no pass and the Mac's full file and web access, so a teammate's or a
        client admin's words wait for the update (review of audit A3-7)."""
        skips = [desk_api.claim_skip(v) for v in self.VERSIONS]
        self.assertEqual(["NOT EXISTS" in s and "COALESCE(q.thread_id, q.id)" in s and "u.role = 'admin'" in s for s in skips],
                         [True, True, True, True, False])


if __name__ == "__main__":
    unittest.main()


class RunsByKeyTests(unittest.TestCase):
    """desk_api.latest_runs: the newest run per problem (or per piece of advice) wins, with its waiting count."""

    def test_the_newest_run_per_key_wins_and_rows_without_a_key_are_skipped(self):
        rows = [{"id": 9, "status": "queued", "k": "no_leads:c1", "waiting": 0},
                {"id": 7, "status": "done", "k": "no_leads:c1", "waiting": 2},
                {"id": 6, "status": "done", "k": "fatigue:a3", "waiting": 1},
                {"id": 5, "status": "done", "k": None, "waiting": 0}]
        self.assertEqual(desk_api.runs_by_key(rows), {"no_leads:c1": {"id": 9, "status": "queued", "waiting": 0},
                                                      "fatigue:a3": {"id": 6, "status": "done", "waiting": 1}})


class SpendLimitProposalTests(unittest.TestCase):
    """FU-B: a spend_limit suggestion must aim at this account's own ad account and carry a clean amount."""
    BASE = {"kind": "spend_limit", "title": "Raise the account spending limit to $200", "entity_type": "account",
            "entity_id": "act_1025", "proposed_value": "$200"}

    def clean(self, **kw):
        return desk_api.clean_proposal({**self.BASE, **kw}, ad_account="1025")

    def test_this_accounts_limit_keeps_its_kind_and_cents(self):
        out = self.clean(payload={"proposed_cents": "20000"})
        self.assertEqual((out["kind"], out["entity_type"], out["entity_id"], out["payload"]), ("spend_limit", "account", "act_1025", {"proposed_cents": 20000}))

    def test_a_removal_needs_literal_true(self):
        self.assertEqual([(o["kind"], o["payload"]) for o in (self.clean(payload={"remove": True}), self.clean(payload={"remove": "yes"}))],
                         [("spend_limit", {"remove": True}), ("other", None)])

    def test_another_ad_account_or_a_bad_payload_becomes_other(self):
        cases = [self.clean(entity_id="act_999", payload={"proposed_cents": 20000}),
                 desk_api.clean_proposal({**self.BASE, "payload": {"proposed_cents": 20000}}, ad_account=None),
                 self.clean(payload={"proposed_cents": 0}), self.clean(payload={"proposed_cents": 200.5}), self.clean(payload=None),
                 self.clean(payload={"proposed_cents": 20000, "remove": True})]
        self.assertEqual([c["kind"] for c in cases], ["other"] * 6)


class ProposalKindsMatchTheDatabaseTests(unittest.TestCase):
    """Every kind clean_proposal keeps must be one the newest desk_proposals_kind_check migration allows (a kind
    the database refuses would fail the Mac's whole batch of suggestions)."""

    def test_the_newest_constraint_lists_exactly_the_kinds(self):
        import os
        import re
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
        latest = None
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                m = re.search(r"desk_proposals_kind_check\s+CHECK \(kind IN \(([^)]*)\)\)", f.read())
            latest = m.group(1) if m else latest
        self.assertEqual(sorted(re.findall(r"'([a-z_]+)'", latest)), sorted(desk_api.PROPOSAL_KINDS))


class AttachmentSniffTests(unittest.TestCase):
    """FU-D: a preview's type comes from its bytes, never from its name or the type the Mac says."""
    PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + b"\x00" * 40
    JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 40
    WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8X" + b"\x00" * 40
    FTYP = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp41"

    def test_the_four_kinds_it_takes(self):
        import attachments
        got = [attachments.sniff(b) for b in (self.PNG, self.JPEG, self.WEBP, self.FTYP + b"\x00\x00\x00\x08moov" + b"\x00" * 20,
                                              self.FTYP + b"\x00\x00\x00\x08free" + b"\x00" * 20)]
        self.assertEqual(got, ["image/png", "image/jpeg", "image/webp", "video/mp4", "video/mp4"])

    def test_anything_else_is_refused(self):
        import attachments
        mov = b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  \x00\x00\x00\x08moov"
        html_in_mp4 = self.FTYP + b"<!doctype html><script>alert(1)</script>"
        cases = [b"GIF89a\x01\x00\x01\x00", b"<!doctype html><html>", b"<svg xmlns='http://www.w3.org/2000/svg'>", mov, html_in_mp4,
                 b"RIFF\x24\x00\x00\x00WAVEfmt ", b"\x00\x00\x00\x18ftyp", b"", b"\x89PNG"]
        self.assertEqual([attachments.sniff(b) for b in cases], [None] * len(cases))

    def test_size_rule_per_kind(self):
        import attachments
        mb = 1024 * 1024
        self.assertEqual([attachments.too_big("image", 10 * mb) is None, attachments.too_big("image", 10 * mb + 1) is None,
                          attachments.too_big("video", 60 * mb) is None, attachments.too_big("video", 61 * mb) is None],
                         [True, False, True, False])


class CleanReplyTests(unittest.TestCase):
    """A reply's body: the words, and what it is about (a suggestion or a preview) only as whole numbers."""

    def test_about_a_preview_is_kept_only_as_an_int(self):
        cases = [7, "7", " 12 ", True, False, 3.5, "x", None, [7], {"id": 7}, -1, 0]
        self.assertEqual([desk_api.clean_reply({"prompt": "Change it", "about_attachment": c})["about_attachment"] for c in cases],
                         [7, 7, 12, None, None, None, None, None, None, None, None, None])

    def test_the_rest_of_the_reply(self):
        self.assertEqual(desk_api.clean_reply({"prompt": "  Bigger headline  ", "about_proposal": "5", "stop_first": 1, "full": True,
                                               "options": {"access": "full"}}),
                         {"prompt": "Bigger headline", "about_proposal": 5, "about_attachment": None, "stop_first": True})
