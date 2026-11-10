import unittest

import forms

GOOD = {
    "name": "Free intro call v2", "intro_title": "Get a free 20-minute intro call",
    "intro_bullets": ["We look at how you work today", "You leave with one thing to fix first"],
    "standard": ["COMPANY_NAME"], "higher_intent": True, "privacy_url": "https://edgebourne.com/privacy",
    "custom": [{"label": "What kind of business do you run?", "options": ["Trades", "Retail", "Services", "Other"]},
               {"label": "What should we look at first?", "options": []}],
    "thanks_title": "Thanks, we'll call you today", "thanks_body": "Expect a call from Eugene.",
    "thanks_button": "website", "thanks_button_text": "See our work", "thanks_url": "https://edgebourne.com",
}


class PayloadTests(unittest.TestCase):
    def test_a_full_form_becomes_metas_request(self):
        p = forms.payload(GOOD)
        self.assertEqual(p["questions"], [
            {"type": "FULL_NAME", "key": "full_name"}, {"type": "EMAIL", "key": "email"}, {"type": "PHONE", "key": "phone"},
            {"type": "COMPANY_NAME", "key": "company_name"},
            {"type": "CUSTOM", "key": "question_1", "label": "What kind of business do you run?",
             "options": [{"value": "Trades", "key": "q1_option_1"}, {"value": "Retail", "key": "q1_option_2"},
                         {"value": "Services", "key": "q1_option_3"}, {"value": "Other", "key": "q1_option_4"}]},
            {"type": "CUSTOM", "key": "question_2", "label": "What should we look at first?"}])
        self.assertEqual((p["context_card"]["style"], p["context_card"]["content"], p["is_optimized_for_quality"]),
                         ("LIST_STYLE", GOOD["intro_bullets"], True))
        self.assertEqual((p["thank_you_page"]["button_type"], p["thank_you_page"]["website_url"], p["follow_up_action_url"]),
                         ("VIEW_WEBSITE", "https://edgebourne.com", "https://edgebourne.com"))

    def test_without_a_button_the_thank_you_page_has_none(self):
        p = forms.payload({**GOOD, "thanks_button": "none"})
        self.assertEqual((p["thank_you_page"]["button_type"], "follow_up_action_url" in p), ("NONE", False))

    def test_a_copied_form_round_trips(self):
        meta = {**forms.payload(GOOD), "privacy_policy_url": "https://edgebourne.com/privacy"}
        back = forms.spec_from_meta(meta)
        self.assertEqual({k: back[k] for k in GOOD if k != "name"}, {k: GOOD[k] for k in GOOD if k != "name"} | {"custom": [
            {"label": "What kind of business do you run?", "options": ["Trades", "Retail", "Services", "Other"]},
            {"label": "What should we look at first?", "options": []}]})
        self.assertEqual(back["name"], "Free intro call v2 (copy)")


class CheckTests(unittest.TestCase):
    def test_a_clean_form_has_no_problems(self):
        self.assertEqual((forms.problems(GOOD), forms.policy_problems(GOOD)), ([], []))

    def test_prohibited_questions_are_named_with_the_reason(self):
        cases = {
            "What is your annual income?": "financial details",
            "Do you have any medical conditions?": "health information",
            "Who is your insurance provider?": "insurance details",
            "What's your SSN?": "a government ID",
            "Have you ever been arrested?": "criminal history",
            "Which party do you vote for?": "politics",
        }
        for label, why in cases.items():
            with self.subTest(label=label):
                got = forms.policy_problems({**GOOD, "custom": [{"label": label, "options": []}]})
                self.assertEqual([(w, why in m) for w, m in got], [("Question 1", True)])

    def test_business_size_and_timeline_questions_are_fine(self):
        ok = [{"label": "How many people work at your company?", "options": ["1-5", "6-20", "21+"]},
              {"label": "When do you want to start?", "options": ["This month", "Next 3 months", "Just looking"]}]
        self.assertEqual(forms.policy_problems({**GOOD, "custom": ok}), [])

    def test_repeating_a_prefilled_field_is_flagged(self):
        got = forms.policy_problems({**GOOD, "custom": [{"label": "What is your email?", "options": []}]})
        self.assertEqual(len(got), 1)
        self.assertIn("repeats a prefilled field", got[0][1])

    def test_privacy_policy_must_be_a_secure_web_page(self):
        for url in ("http://edgebourne.com/privacy", "https://edgebourne.com/privacy.pdf", ""):
            with self.subTest(url=url):
                self.assertEqual([w for w, _ in forms.policy_problems({**GOOD, "privacy_url": url})], ["Privacy policy"])

    def test_missing_and_too_long_values_point_at_their_field(self):
        bad = {**GOOD, "name": " ", "intro_title": "x" * 61, "custom": [{"label": "Pick one", "options": ["Only"]},
               {"label": "Dupes", "options": ["A", "a"]}], "thanks_url": "edgebourne.com"}
        self.assertEqual(forms.problems(bad), [
            ("name", "Give the form a name (only you see it)"), ("intro_title", "Keep it to 60 characters"),
            ("custom", "Question 1: give 2 to 6 answers to pick from, or none for a typed answer"),
            ("custom", "Question 2: two answers are the same"),
            ("thanks_url", "Give the page the button opens, starting with https://")])

    def test_at_most_three_questions_of_your_own(self):
        many = [{"label": f"Q{i}", "options": []} for i in range(4)]
        self.assertIn(("custom", "At most 3 questions of your own"), forms.problems({**GOOD, "custom": many}))


if __name__ == "__main__":
    unittest.main()
