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


class AuditThreeParseTest(unittest.TestCase):
    """A3-23: numbers that aren't a daily amount (2x, 7-day, 3 ad sets) were read as the new budget."""

    def test_numbers_that_are_not_a_daily_amount_are_never_the_new_budget(self):
        cases = ["Set to 2x ($40/day)", "Move to 7-day attribution, $24/day", "Scale to 3 ad sets at $20/day",
                 "Raise to 1.5x the current budget", "Keep $26/day, shift to 30-day window", "Raise to $24 x 2"]
        self.assertEqual({t: mr.parse_budget_text(t) for t in cases}, {t: None for t in cases})

    def test_a_lone_number_that_counts_something_else_is_not_an_amount(self):
        cases = ["Move to 7-day attribution", "Use a 7-day window", "Scale to 3 ad sets", "Raise to 2x"]
        self.assertEqual({t: mr.parse_budget_text(t) for t in cases}, {t: None for t in cases})

    def test_money_written_after_to_is_still_the_new_budget(self):
        cases = {"Lower to $15/day": 1500, "to 24/day": 2400, "raise it to $30": 3000, "Cut from $31 to $24.": 2400,
                 "Raise to $24, then wait": 2400}
        self.assertEqual({t: mr.parse_budget_text(t) for t in cases}, cases)


class ProposalCentsTest(unittest.TestCase):
    def test_without_a_structured_amount_the_words_decide(self):
        self.assertEqual(mr.proposal_cents("$24/day", None), (2400, None))
        cents, why = mr.proposal_cents("Raise 2x or more", None)
        self.assertEqual((cents, "isn't one clear amount" in why), (None, True))

    def test_a_structured_amount_is_used_when_the_words_name_it(self):
        cases = [("$24/day", 2400), ("Set to 2x ($40/day)", 4000), ("from $20 to $24", 2400)]
        self.assertEqual([mr.proposal_cents(t, c) for t, c in cases], [(c, None) for _, c in cases])

    def test_a_structured_amount_the_words_disagree_with_is_refused(self):
        cases = [("+20% to $24/day", 2300), ("Raise it a bit", 2400), ("$24/day", True), ("$24/day", 0), ("$24/day", 24.0),
                 ("Move to 7-day attribution", 700), ("Raise to 2x", 200), ("Scale to 3 ad sets", 300),
                 ("Cut from $31 to $24.", 3100), ("Set to 2x ($40/day) from $20/day", 4000)]
        out = [mr.proposal_cents(t, c) for t, c in cases]
        self.assertEqual([(cents, bool(why)) for cents, why in out], [(None, True)] * len(cases))


class TurnOnProblemTest(unittest.TestCase):
    DAILY = {"daily_cents": 2000, "lifetime_cents": None, "holder": "c1"}
    LIFETIME = {"daily_cents": None, "lifetime_cents": 150000, "holder": "c1"}

    def test_a_daily_budget_must_be_echoed(self):
        self.assertEqual([mr.turn_on_problem(self.DAILY, 2000, None) is None, mr.turn_on_problem(self.DAILY, 1999, None) is None,
                          mr.turn_on_problem(self.DAILY, None, None) is None], [True, False, False])

    def test_a_lifetime_budget_must_be_echoed_too(self):
        self.assertEqual([mr.turn_on_problem(self.LIFETIME, None, 150000) is None, mr.turn_on_problem(self.LIFETIME, None, None) is None,
                          mr.turn_on_problem(self.LIFETIME, 150000, None) is None], [True, False, False])

    def test_both_kinds_together_need_both_echoed(self):
        both = {"daily_cents": 2000, "lifetime_cents": 150000, "holder": "c1/adsets"}
        self.assertEqual([mr.turn_on_problem(both, 2000, 150000) is None, mr.turn_on_problem(both, 2000, None) is None],
                         [True, False])

    def test_no_budget_meta_reports_is_refused_not_skipped(self):
        self.assertIn("no budget", mr.turn_on_problem({"daily_cents": None, "lifetime_cents": None, "holder": None}, None, None))

    def test_a_campaign_with_nothing_on_inside_spends_nothing_yet(self):
        self.assertIsNone(mr.turn_on_problem({"daily_cents": None, "lifetime_cents": None, "holder": None, "idle": True}, None, None))


if __name__ == "__main__":
    unittest.main()
