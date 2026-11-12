import unittest

import creative_build as cr

GOOD = {"adset_id": "s1", "template_ad_id": "t1", "name": "N6 - Payroll", "body": "Stop retyping hours.", "title": "Payroll in one click",
        "cta_type": "SIGN_UP", "media": {"kind": "same"}, "form_id": None}
CTAS = ("SIGN_UP", "LEARN_MORE")


class NewAdProblemTests(unittest.TestCase):
    """9.4e: the New ad page marks every field at once, before anything is sent to Meta."""
    def test_a_complete_ad_has_none(self):
        self.assertEqual(cr.problems(GOOD, CTAS), [])

    def test_every_missing_field_in_the_order_the_page_shows_them(self):
        bad = {**GOOD, "adset_id": "", "name": " ", "body": "", "title": "", "media": None, "cta_type": "SHOP_NOW"}
        self.assertEqual(cr.problems(bad, CTAS), [
            ("adset_id", "Pick the ad set it goes in"), ("media", "Choose an image or video"), ("body", "Write the primary text"),
            ("title", "Write a headline"), ("cta_type", "Pick a button from the list"), ("name", "Name the ad (only you see the name)")])

    def test_media_needs_its_id(self):
        for media, ok in (({"kind": "image", "hash": "h"}, True), ({"kind": "video", "video_id": "9"}, True),
                          ({"kind": "image"}, False), ({"kind": "video", "hash": "h"}, False), ({"kind": "gif", "hash": "h"}, False)):
            with self.subTest(media=media):
                self.assertEqual(cr.problems({**GOOD, "media": media}, CTAS) == [], ok)

    def test_from_scratch_needs_its_own_media_and_a_form(self):
        scratch = {**GOOD, "template_ad_id": "", "form_id": ""}
        self.assertEqual(cr.problems(scratch, CTAS), [("form_id", "Pick the lead form the button opens"),
                                                      ("media", "Choose an image or video (it doesn't start from another ad)")])
        self.assertEqual(cr.problems({**scratch, "form_id": "123", "media": {"kind": "image", "hash": "h"}}, CTAS), [])

    def test_a_form_id_must_be_a_meta_id(self):
        self.assertEqual(cr.problems({**GOOD, "form_id": "12x"}, CTAS), [("form_id", "Unknown lead form")])

    def test_an_empty_button_keeps_the_starting_ads(self):
        self.assertEqual(cr.problems({**GOOD, "cta_type": ""}, CTAS), [])


if __name__ == "__main__":
    unittest.main()
