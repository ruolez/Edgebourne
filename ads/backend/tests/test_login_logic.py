import unittest

import auth

GOOD_EMAIL = "eugene@edgebourne.com"
GOOD_PASSWORD = "any password at all"


def fields(problems):
    return [p["field"] for p in problems]


class LoginProblemsTests(unittest.TestCase):
    def test_a_filled_in_form_has_no_problems_whatever_the_password(self):
        self.assertEqual([auth.login_problems(GOOD_EMAIL, GOOD_PASSWORD), auth.login_problems(" Eugene@EdgeBourne.com ", "x")], [[], []])

    def test_each_missing_field_is_named_on_its_own(self):
        self.assertEqual([fields(auth.login_problems("", GOOD_PASSWORD)), fields(auth.login_problems(GOOD_EMAIL, "")),
                          fields(auth.login_problems("  ", ""))],
                         [["email"], ["password"], ["email", "password"]])

    def test_an_email_needs_a_name_one_at_sign_and_a_domain_but_a_local_domain_is_fine(self):
        self.assertEqual(auth.login_problems("eugene@localhost", GOOD_PASSWORD), [])
        for bad in ["eugene", "eugene@", "@edgebourne.com", "eu gene@edgebourne.com", "a@b@c.com"]:
            with self.subTest(bad=bad):
                self.assertEqual(fields(auth.login_problems(bad, GOOD_PASSWORD)), ["email"])

    def test_the_messages_say_what_to_do_in_plain_words(self):
        by_field = {p["field"]: p["message"] for p in auth.login_problems("eugene", "")}
        self.assertEqual(by_field, {"email": "Check the email: it looks like name@example.com.", "password": "Type your password."})
        self.assertEqual(auth.login_problems("", GOOD_PASSWORD), [{"field": "email", "message": "Type the email you sign in with."}])


if __name__ == "__main__":
    unittest.main()
