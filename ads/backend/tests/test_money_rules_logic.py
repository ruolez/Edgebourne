import unittest

import money_rules as mr


class ParseBudgetTextTest(unittest.TestCase):
    def test_the_amount_after_to_is_the_new_budget(self):
        cases = {"$24/day": 2400, "24": 2400, "from $20 to $24": 2400, "+20% to $24/day": 2400,
                 "$20 → $24": 2400, "$1,250.50 per day": 125050, "raise to 30": 3000}
        self.assertEqual({t: mr.parse_budget_text(t) for t in cases}, cases)

    def test_unclear_amounts_are_refused_not_guessed(self):
        unclear = ["Raise 2x to $40 or $50", "Raise 2x", "$20 or $24", "from $20 to $24 to $30", "+20%", "", None,
                   "double it"]
        self.assertEqual([mr.parse_budget_text(t) for t in unclear], [None] * len(unclear))

    def test_the_audit_cases_now_read_the_new_amount(self):
        # Before: "+20% to $24/day" → $20.00 and "Raise 2x to $40" → $2.00.
        self.assertEqual([mr.parse_budget_text("+20% to $24/day"), mr.parse_budget_text("Raise 2x to $40")], [2400, 4000])


class BudgetChangeTest(unittest.TestCase):
    CAP = 10000

    def test_a_twenty_percent_step_is_not_big(self):
        self.assertEqual(mr.budget_change(2000, 2400, self.CAP),
                         {"from": 2000, "to": 2400, "pct": 20, "big": False, "over_cap": False, "cap": self.CAP})

    def test_more_than_twenty_percent_needs_confirming(self):
        change = mr.budget_change(2000, 2500, self.CAP)
        self.assertEqual((change["big"], mr.change_problem(change, False) is not None, mr.change_problem(change, True)),
                         (True, True, None))

    def test_above_the_ceiling_is_refused_even_when_confirmed(self):
        change = mr.budget_change(9000, 10100, self.CAP)
        self.assertIn("ceiling", mr.change_problem(change, True))

    def test_lowering_is_always_fine(self):
        self.assertIsNone(mr.change_problem(mr.budget_change(5000, 1000, self.CAP), False))

    def test_under_one_unit_is_refused(self):
        self.assertIsNotNone(mr.change_problem(mr.budget_change(2000, 50, self.CAP), True))


class CeilingTest(unittest.TestCase):
    def test_saved_value_or_the_default(self):
        self.assertEqual([mr.ceiling("25000"), mr.ceiling(None), mr.ceiling("abc"), mr.ceiling("10")],
                         [25000, mr.MAX_DAILY_DEFAULT, mr.MAX_DAILY_DEFAULT, mr.MAX_DAILY_DEFAULT])


class RecommendationAmountTest(unittest.TestCase):
    def test_only_whole_cents_are_trusted(self):
        cases = [(500, 500), ("500", 500), ("50.00", None), (20, None), (None, None), ({"amount": 5}, None),
                 (True, None), (-500, None)]
        self.assertEqual([mr.recommendation_amount(v) for v, _ in cases], [want for _, want in cases])


if __name__ == "__main__":
    unittest.main()
