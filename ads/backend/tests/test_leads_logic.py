import hashlib
import hmac
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("WORKERS_ENABLED", "0")

import leads  # noqa: E402
import meta_client  # noqa: E402


class SignatureValidTest(unittest.TestCase):
    SECRET = "app-secret"
    BODY = b'{"object":"page","entry":[]}'

    def sign(self, body, secret=SECRET):
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_accepts_meta_signature(self):
        self.assertTrue(meta_client.signature_valid(self.BODY, self.sign(self.BODY), self.SECRET))

    def test_rejects_wrong_secret_tampered_body_and_missing_parts(self):
        cases = [
            (self.BODY, self.sign(self.BODY, "other"), self.SECRET),
            (self.BODY + b" ", self.sign(self.BODY), self.SECRET),
            (self.BODY, None, self.SECRET),
            (self.BODY, self.sign(self.BODY), ""),
            (self.BODY, self.sign(self.BODY).replace("sha256=", "sha1="), self.SECRET),
        ]
        self.assertEqual([meta_client.signature_valid(*c) for c in cases], [False] * len(cases))


class ParseFieldDataTest(unittest.TestCase):
    def test_maps_contact_fields_and_first_custom_answer(self):
        field_data = [
            {"name": "full_name", "values": ["Maria Lopez"]},
            {"name": "email", "values": ["maria@example.com"]},
            {"name": "phone_number", "values": ["+16195550101"]},
            {"name": "what_kind_of_business_do_you_run?", "values": ["Wholesale bakery"]},
            {"name": "second_question", "values": ["ignored for business_type"]},
        ]
        self.assertEqual(leads.parse_field_data(field_data), {
            "full_name": "Maria Lopez", "email": "maria@example.com",
            "phone": "+16195550101", "business_type": "Wholesale bakery",
        })

    def test_joins_first_and_last_name_when_full_name_missing(self):
        field_data = [{"name": "first_name", "values": ["Ann"]}, {"name": "last_name", "values": ["Lee"]}]
        self.assertEqual(leads.parse_field_data(field_data)["full_name"], "Ann Lee")

    def test_empty_and_missing_values_become_none(self):
        self.assertEqual(leads.parse_field_data([{"name": "email", "values": [""]}, {"name": "x"}]),
                         {"full_name": None, "email": None, "phone": None, "business_type": None})

    def test_handles_no_field_data(self):
        self.assertEqual(leads.parse_field_data(None)["business_type"], None)


class RenderEmailTest(unittest.TestCase):
    LEAD = {"id": 7, "full_name": "Maria <b>Lopez</b>", "phone": "+16195550101",
            "email": "maria@example.com", "business_type": "Bakery", "ad_name": "N2 - Order portal",
            "is_test": False}

    def test_subject_names_person_and_business(self):
        subject, _text, _html = leads.render_email(self.LEAD)
        self.assertEqual(subject, "New lead: Maria <b>Lopez</b>, Bakery")

    def test_html_escapes_lead_input(self):
        _s, _t, body = leads.render_email(self.LEAD)
        self.assertNotIn("<b>Lopez</b>", body)
        self.assertIn("Maria &lt;b&gt;Lopez&lt;/b&gt;", body)

    def test_test_leads_are_labelled(self):
        subject, _t, _h = leads.render_email(dict(self.LEAD, is_test=True))
        self.assertTrue(subject.startswith("New lead (test lead):"))


class EventGivesUpTest(unittest.TestCase):
    NOW = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
    HOUR = timedelta(hours=1)
    NOT_FOUND = 100
    NO_PERMISSION = 10

    def test_stops_when_meta_says_the_lead_does_not_exist(self):
        self.assertTrue(leads.event_gives_up(self.NOT_FOUND, self.NOW, self.NOW))

    def test_keeps_retrying_fixable_errors_for_a_day(self):
        cases = [(self.NO_PERMISSION, self.NOW - 23 * self.HOUR), (None, self.NOW - self.HOUR)]
        self.assertEqual([leads.event_gives_up(code, t, self.NOW) for code, t in cases], [False, False])

    def test_stops_any_error_after_a_day(self):
        self.assertTrue(leads.event_gives_up(self.NO_PERMISSION, self.NOW - 25 * self.HOUR, self.NOW))


if __name__ == "__main__":
    unittest.main()
