import unittest

import account_info


class MoneyTests(unittest.TestCase):
    def test_amounts_are_written_in_the_account_currency(self):
        cents = 123456
        self.assertEqual([account_info.money(cents, c) for c in ("USD", "eur", "GBP", "CAD")],
                         ["$1,234.56", "€1,234.56", "£1,234.56", "1,234.56 CAD"])

    def test_whole_leaves_the_cents_out_and_nothing_is_a_dash(self):
        self.assertEqual((account_info.money(2000, "USD", whole=True), account_info.money(2049, "EUR", whole=True),
                          account_info.money(None, "USD")), ("$20", "€20", "—"))


if __name__ == "__main__":
    unittest.main()
