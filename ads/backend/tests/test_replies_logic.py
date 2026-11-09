import unittest

import replies

LEAD = {"full_name": "Maria Lopez", "business_type": "Wholesale bakery", "phone": "+15551234567", "email": "maria@example.com"}
SENDER = {"name": "Eugene", "email": "eugene@edgebourne.com"}


class ValuesTests(unittest.TestCase):
    def test_takes_names_and_contact_details_from_the_lead_and_the_sender(self):
        self.assertEqual(replies.values(LEAD, SENDER, "https://cal.com/eugene"), {
            "first_name": "Maria", "full_name": "Maria Lopez", "business": "Wholesale bakery", "phone": "(555) 123-4567",
            "my_name": "Eugene", "my_email": "eugene@edgebourne.com", "booking_link": "https://cal.com/eugene"})

    def test_friendly_fallbacks_when_the_form_left_things_out(self):
        v = replies.values({"full_name": None, "business_type": "", "phone": None}, SENDER, None)
        self.assertEqual((v["first_name"], v["full_name"], v["business"], v["phone"], v["booking_link"]),
                         ("there", "there", "your business", "", ""))


class FillTests(unittest.TestCase):
    TEMPLATE = "Hi {first_name},\n\nThanks for asking about {business}.\n\nBook a time: {booking_link}\n\nOr call me back at {my_email}.\n{unknown} stays as typed"

    def test_replaces_every_placeholder(self):
        v = replies.values(LEAD, SENDER, "https://cal.com/eugene")
        self.assertEqual(replies.fill(self.TEMPLATE, v),
                         "Hi Maria,\n\nThanks for asking about Wholesale bakery.\n\nBook a time: https://cal.com/eugene\n\nOr call me back at eugene@edgebourne.com.\n{unknown} stays as typed")

    def test_drops_a_line_whose_value_is_missing_and_keeps_one_blank_line(self):
        v = replies.values(LEAD, SENDER, None)
        self.assertEqual(replies.fill(self.TEMPLATE, v),
                         "Hi Maria,\n\nThanks for asking about Wholesale bakery.\n\nOr call me back at eugene@edgebourne.com.\n{unknown} stays as typed")


class AutoEligibleTests(unittest.TestCase):
    def test_only_real_leads_with_an_email_while_the_switch_is_on(self):
        lead = {"is_test": False, "email": "maria@example.com"}
        self.assertEqual(
            [replies.auto_reason(lead, True), replies.auto_reason(lead, False), replies.auto_reason({**lead, "is_test": True}, True),
             replies.auto_reason({**lead, "email": None}, True), replies.auto_reason({**lead, "email": "not-an-email"}, True)],
            [None, "off", "test lead", "no email", "no email"])


class PhoneDisplayTests(unittest.TestCase):
    def test_writes_us_numbers_the_way_people_read_them_and_leaves_others(self):
        self.assertEqual([replies.phone_display(p) for p in ("+15551234567", "555-123-4567", "(555) 123 4567", "+44 20 7946 0958", None)],
                         ["(555) 123-4567", "(555) 123-4567", "(555) 123-4567", "+44 20 7946 0958", ""])
