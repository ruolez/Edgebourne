import unittest
from datetime import datetime, timezone

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
                         {"from": 2000, "to": 2400, "pct": 20, "big": False, "over_cap": False, "cap": self.CAP,
                          "recent": False, "rollback": False, "last": None})

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


def t(d, h):
    return datetime(2026, 11, d, h, tzinfo=timezone.utc)


def last(at, old, new, where="outside", by="Ads Manager"):
    return {"at": at, "field": "daily_budget", "old": old, "new": new, "by": by, "where": where, "proposal_id": None}


class RecentChangeTest(unittest.TestCase):
    """Rule 6: one budget change at least 3 days apart. A raise sooner needs a knowing yes; a cut or going back
    to the exact previous budget never does."""
    CAP = 10000
    LAST = last(t(9, 15), 2000, 2400)

    def test_the_latest_real_change_wins(self):
        rows = [last(t(7, 10), 1600, 2000, "console", "Eugene"), self.LAST, last(t(10, 9), 2400, 2400)]
        self.assertEqual(mr.last_budget_change(rows), self.LAST)

    def test_nothing_to_go_on(self):
        self.assertEqual((mr.last_budget_change([]), mr.recency(None, t(11, 15), 2400, 2600)), (None, None))

    def test_a_raise_inside_three_days(self):
        self.assertEqual(mr.recency(self.LAST, t(11, 15), 2400, 2600),
                         {"recent": True, "raise": True, "rollback": False, "hours": 48, "ok_after": t(12, 15)})

    def test_exactly_seventy_two_hours_later_is_not_recent(self):
        self.assertEqual([mr.recency(self.LAST, now, 2400, 2600)["recent"]
                          for now in (datetime(2026, 11, 12, 14, 59, 59, tzinfo=timezone.utc), t(12, 15))], [True, False])

    def test_going_back_to_the_budget_before_the_last_change_is_never_recent(self):
        rec = mr.recency(self.LAST, t(11, 15), 2400, 2000)
        change = mr.budget_change(2400, 2000, self.CAP, self.LAST, t(11, 15))
        self.assertEqual((rec["rollback"], change["recent"], change["rollback"]), (True, False, True))

    def test_a_rollback_that_raises_is_not_recent_either(self):
        cut = last(t(10, 9), 2400, 2000)
        self.assertEqual(mr.budget_change(2000, 2400, self.CAP, cut, t(11, 15))["recent"], False)

    def test_a_cut_is_never_recent(self):
        change = mr.budget_change(2400, 2200, self.CAP, self.LAST, t(11, 15))
        self.assertEqual((mr.recency(self.LAST, t(11, 15), 2400, 2200)["raise"], change["recent"],
                          mr.change_problem(change, False)), (False, False, None))

    def test_a_recent_raise_is_refused_without_the_knowing_yes(self):
        change = mr.budget_change(2400, 2600, self.CAP, self.LAST, t(11, 15))
        self.assertEqual(mr.change_problem(change, accept_big=False),
                         "The budget last changed 2 days ago (20.00 → 24.00 a day). Raising it again this soon "
                         "makes results hard to read: confirm it knowingly.")
        self.assertIsNone(mr.change_problem(change, accept_big=False, accept_recent=True))

    def test_big_and_recent_need_both_yeses(self):
        change = mr.budget_change(2400, 3200, self.CAP, self.LAST, t(11, 15))
        self.assertIn("more than +20%", mr.change_problem(change, False, False))
        self.assertIn("last changed", mr.change_problem(change, True, False))
        self.assertIsNone(mr.change_problem(change, True, True))

    def test_the_ceiling_is_still_checked_first(self):
        change = mr.budget_change(2400, 20000, self.CAP, self.LAST, t(11, 15))
        self.assertIn("ceiling", mr.change_problem(change, True, True))

    def test_without_history_nothing_changes(self):
        change = mr.budget_change(2000, 2400, self.CAP)
        self.assertEqual((change["recent"], change["last"], mr.change_problem(change, False)), (False, None, None))

    def test_hours_when_under_a_day(self):
        change = mr.budget_change(2400, 2600, self.CAP, last(t(11, 10), 2000, 2400), t(11, 15))
        self.assertIn("last changed 5 hours ago", mr.change_problem(change, False))

    def test_under_an_hour(self):
        change = mr.budget_change(2400, 2600, self.CAP, last(datetime(2026, 11, 11, 14, 30, tzinfo=timezone.utc), 2000, 2400), t(11, 15))
        self.assertIn("last changed less than an hour ago", mr.change_problem(change, False))
