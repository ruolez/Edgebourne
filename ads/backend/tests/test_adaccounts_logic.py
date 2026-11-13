import unittest

import account_info
import adaccounts

EB, MASHA, TOKYO, OLD = "1025971549903293", "2223334445556667", "4445556667778889", "5556667778889990"
NAMES = {1: "Edge Bourne", 3: "Old Shop QA", 7: "Masha Fontana Studio"}


def row(account_id, name, currency="USD", status=1, business=None):
    out = {"account_id": account_id, "id": f"act_{account_id}", "name": name, "currency": currency,
           "account_status": status, "timezone_name": "America/Chicago"}
    if business:
        out["business"] = {"id": "999", "name": business}
    return out


def item(account_id, name="Some business", currency="USD", status=1, used_by=None):
    return {"id": account_id, "name": name, "currency": currency, "status": status, "used_by": used_by}


class ActDigitsTests(unittest.TestCase):
    def test_takes_the_digits_from_an_act_id_or_a_bare_number_and_refuses_anything_else(self):
        got = [adaccounts.act_digits(v) for v in ("act_2223", " 2223 ", " act_2223 ", "act_22x3", "", None, "act_", "22 23", 2223)]
        self.assertEqual(got, ["2223", "2223", "2223", None, None, None, None, None, "2223"])


class MergeTests(unittest.TestCase):
    def test_one_entry_per_ad_account_sorted_by_name_with_every_list_it_came_from(self):
        a, b, c = row(EB, "edge Bourne Consulting", business="Edge Bourne"), row(MASHA, "Masha Fontana Studio"), row(OLD, "Old Shop", status=101)
        got = adaccounts.merge({"assigned": [a, b], "owned": [a], "client": [c]})
        self.assertEqual([(i["id"], i["via"]) for i in got], [(EB, ["assigned", "owned"]), (MASHA, ["assigned"]), (OLD, ["client"])])
        self.assertEqual(got[0], {"id": EB, "name": "edge Bourne Consulting", "currency": "USD", "status": 1, "status_words": "Active",
                                  "timezone": "America/Chicago", "business_name": "Edge Bourne", "business_id": "999",
                                  "via": ["assigned", "owned"]})

    def test_the_same_id_twice_in_one_list_is_one_entry_named_once(self):
        got = adaccounts.merge({"assigned": [row(MASHA, "Masha"), row(MASHA, "Masha")]})
        self.assertEqual([(i["id"], i["via"]) for i in got], [(MASHA, ["assigned"])])

    def test_a_row_without_account_id_takes_the_digits_of_its_act_id_and_a_row_without_either_is_dropped(self):
        got = adaccounts.merge({"assigned": [{"id": f"act_{TOKYO}", "name": "Tokyo"}, {"name": "No id"}]})
        self.assertEqual([i["id"] for i in got], [TOKYO])

    def test_an_unknown_status_reads_as_unknown_and_the_currency_is_upper_case(self):
        got = adaccounts.merge({"assigned": [{**row(MASHA, "Masha", currency="usd"), "account_status": 55}]})[0]
        self.assertEqual((got["currency"], got["status_words"]), ("USD", "Unknown"))


class MarkUsedTests(unittest.TestCase):
    def test_names_the_console_account_that_already_holds_each_ad_account(self):
        items = [item(EB), item(OLD), item(MASHA)]
        got = adaccounts.mark_used(items, [(1, False, EB), (3, True, f"act_{OLD}")], NAMES)
        self.assertEqual([i["used_by"] for i in got], [{"account_id": 1, "name": "Edge Bourne", "closed": False},
                                                       {"account_id": 3, "name": "Old Shop QA", "closed": True}, None])


class BlockedTests(unittest.TestCase):
    def test_an_ad_account_an_open_console_account_holds(self):
        used = {"account_id": 1, "name": "Edge Bourne", "closed": False}
        self.assertEqual(adaccounts.blocked(item(EB, used_by=used), account_info.currency_problem), "Already in the console as Edge Bourne.")

    def test_an_ad_account_a_closed_console_account_holds(self):
        used = {"account_id": 3, "name": "Old Shop QA", "closed": True}
        self.assertEqual(adaccounts.blocked(item(OLD, used_by=used), account_info.currency_problem),
                         "Old Shop QA (a closed account) still holds it: reopen that account instead.")

    def test_a_currency_without_cents_says_why_in_the_currency_check_s_own_words(self):
        self.assertEqual(adaccounts.blocked(item(TOKYO, currency="JPY"), account_info.currency_problem), account_info.currency_problem("JPY"))

    def test_a_closed_or_disabled_ad_account(self):
        self.assertEqual([adaccounts.blocked(item(OLD, status=s), account_info.currency_problem) for s in (101, 2, 100, 202)],
                         ["Meta says this ad account is Closed.", "Meta says this ad account is Disabled.",
                          "Meta says this ad account is Closing.", "Meta says this ad account is Closed."])

    def test_a_payment_problem_or_review_can_still_be_added(self):
        self.assertEqual([adaccounts.blocked(item(MASHA, status=s), account_info.currency_problem) for s in (1, 3, 7, 8, 9, 201)], [None] * 6)

    def test_a_status_meta_did_not_send_is_not_a_reason_to_refuse(self):
        self.assertIsNone(adaccounts.blocked(item(MASHA, status=None), account_info.currency_problem))

    def test_being_held_is_said_before_the_currency(self):
        used = {"account_id": 1, "name": "Edge Bourne", "closed": False}
        self.assertEqual(adaccounts.blocked(item(TOKYO, currency="JPY", used_by=used), account_info.currency_problem), "Already in the console as Edge Bourne.")


class DefaultNameTests(unittest.TestCase):
    def test_meta_s_name_trimmed_or_the_last_four_digits(self):
        self.assertEqual([adaccounts.default_name(i) for i in (item(MASHA, name="  Masha  Fontana Studio "), item(MASHA, name=""),
                                                             item(MASHA, name=None), item(MASHA, name="x" * 200))],
                         ["Masha Fontana Studio", "Ad account 6667", "Ad account 6667", "x" * 120])
