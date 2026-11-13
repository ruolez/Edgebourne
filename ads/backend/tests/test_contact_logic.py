import unittest

import contact


class EmailKeyTest(unittest.TestCase):
    def test_keys_and_placeholders(self):
        cases = {
            " Maria@LopezBakery.COM ": "maria@lopezbakery.com",
            "a.b+c@gmail.com": "a.b+c@gmail.com",  # dots and +tags are never folded (no false merges)
            "test@example.com": None,
            "x@mailinator.com": None,
            "dan@kimhvac.example": None,
            "asdf@realshop.com": None,
            "someone@shop.test": None,
            "": None,
            None: None,
            "not-an-email": None,
            "two@@at.com": None,
        }
        self.assertEqual({k: contact.email_key(k) for k in cases}, cases)

    def test_test_and_throwaway_are_told_apart(self):
        self.assertEqual([(contact.is_test_email(e), contact.is_throwaway_email(e)) for e in
                          ("test@test.com", "maria.l@yopmail.com", "maria@lopezbakery.com", "no@shop.com", "")],
                         [(True, False), (False, True), (False, False), (True, False), (False, False)])


class PhoneKeyTest(unittest.TestCase):
    def test_keys(self):
        cases = {
            "+1 (619) 555-7788": "6195557788",
            "619.555.7788": "6195557788",
            "16195557788": "6195557788",
            "+44 20 7946 0958": "2079460958",
            "612345678": "612345678",       # 9 digits kept whole
            "61234567": "61234567",         # 8 digits kept whole
            "6123456": None,                # under 8 digits: no key
            "12345": None,
            "1111111111": None,
            "0000000": None,
            "1234567890": None,
            "0123456789": None,
            "9876543210": None,
            "+15550001111": None,           # area code 555
            "(619) 555-0142": None,         # 555-0100..0199 is fictional
            "(019) 444-7788": None,         # area codes never start with 0 or 1
            "(119) 444-7788": None,
            None: None,
            "": None,
        }
        self.assertEqual({k: contact.phone_key(k) for k in cases}, cases)

    def test_formats_of_one_number_share_a_key(self):
        keys = {contact.phone_key(p) for p in ("+1 (619) 555-7788", "619.555.7788", "16195557788", "619 555 7788")}
        self.assertEqual(keys, {"6195557788"})

    def test_fake_phone_needs_a_number(self):
        self.assertEqual([contact.is_fake_phone(p) for p in (None, "", "+16195557788", "12345", "555-0100")],
                         [False, False, False, True, True])


if __name__ == "__main__":
    unittest.main()
