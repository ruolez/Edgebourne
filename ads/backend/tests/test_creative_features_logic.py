import unittest

import creative_features as cf

DOF = {"creative_features_spec": {
    "standard_enhancements": {"enroll_status": "OPT_OUT"},
    "video_filtering": {"enroll_status": "OPT_IN"},
    "inline_comment": {"enroll_status": "OPT_OUT"},
    "image_touchups": {"enroll_status": "OPT_IN", "customizations": {"x": 1}},
    "brand_new_thing": {"enroll_status": "OPT_IN"},
}}


class ReadTests(unittest.TestCase):
    def test_features_read_in_plain_words_on_first_and_the_retired_switch_left_out(self):
        self.assertEqual([(f["key"], f["on"], f["advice"]) for f in cf.read(DOF)], [
            ("image_touchups", True, "fine"), ("video_filtering", True, "off"), ("brand_new_thing", True, None),
            ("inline_comment", False, "off")])
        self.assertEqual(cf.read(DOF)[2]["label"], "Brand new thing")

    def test_nothing_stated_reads_as_nothing(self):
        self.assertEqual((cf.read(None), cf.read({})), ([], []))

    def test_against_advice_names_only_rewriting_or_generating_features_that_are_on(self):
        self.assertEqual(cf.against_advice(cf.read(DOF)), ["Video filters"])


class ChangeTests(unittest.TestCase):
    def test_switching_one_keeps_the_rest_and_its_customizations(self):
        new = cf.with_change(DOF, "image_touchups", False)
        self.assertEqual(new["creative_features_spec"]["image_touchups"], {"enroll_status": "OPT_OUT", "customizations": {"x": 1}})
        self.assertEqual({k: v for k, v in new["creative_features_spec"].items() if k != "image_touchups"},
                         {k: v for k, v in DOF["creative_features_spec"].items() if k != "image_touchups"})
        self.assertEqual(DOF["creative_features_spec"]["image_touchups"]["enroll_status"], "OPT_IN")

    def test_a_feature_not_stated_yet_can_be_switched_off(self):
        self.assertEqual(cf.with_change({}, "text_optimizations", False), {"creative_features_spec": {"text_optimizations": {"enroll_status": "OPT_OUT"}}})


if __name__ == "__main__":
    unittest.main()
