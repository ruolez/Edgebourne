import unittest

import bulk

CAP = 10000
SECRET = "s" * 32


class StatusTests(unittest.TestCase):
    ROWS = [{"id": "a1", "name": "N1", "status": "PAUSED"}, {"id": "a2", "name": "N2", "status": "PAUSED"},
            {"id": "a3", "name": "N3", "status": "ACTIVE"}, {"id": "a4", "name": "N4", "status": "ARCHIVED"}]

    def test_turning_on_counts_each_budget_once(self):
        leads = {"daily_cents": 3100, "lifetime_cents": None, "where": "the campaign “Leads”", "holder": "c1"}
        lines, totals = bulk.status_lines(self.ROWS, "ACTIVE", {"a1": leads, "a2": dict(leads)})
        self.assertEqual([(l["id"], l["skip"]) for l in lines],
                         [("a1", None), ("a2", None), ("a3", "Already on"), ("a4", "Archived: it can't be turned on again")])
        self.assertEqual(totals, {"count": 2, "daily_cents": 3100, "lifetime_cents": 0, "budgets": ["the campaign “Leads”"]})

    def test_two_budgets_with_the_same_name_are_both_counted(self):
        # A3-25: two campaigns both named "EB - Payroll - Leads" at $15/day spend $30/day together.
        ctx = {"a1": {"daily_cents": 1500, "lifetime_cents": None, "where": "the campaign “EB - Payroll - Leads”", "holder": "c1"},
               "a2": {"daily_cents": 1500, "lifetime_cents": None, "where": "the campaign “EB - Payroll - Leads”", "holder": "c2"}}
        _, totals = bulk.status_lines(self.ROWS, "ACTIVE", ctx)
        self.assertEqual((totals["daily_cents"], len(totals["budgets"])), (3000, 2))

    def test_lifetime_budgets_are_totalled_on_their_own(self):
        ctx = {"a1": {"daily_cents": 1500, "lifetime_cents": None, "where": "the ad set “A”", "holder": "s1"},
               "a2": {"daily_cents": None, "lifetime_cents": 150000, "where": "the campaign “B”", "holder": "c2"}}
        _, totals = bulk.status_lines(self.ROWS, "ACTIVE", ctx)
        self.assertEqual((totals["daily_cents"], totals["lifetime_cents"]), (1500, 150000))

    def test_something_meta_reports_no_budget_for_is_skipped(self):
        none = {"daily_cents": None, "lifetime_cents": None, "where": None, "holder": None}
        idle = {**none, "idle": True}
        lines, totals = bulk.status_lines(self.ROWS[:2], "ACTIVE", {"a1": none, "a2": idle})
        self.assertEqual(([bool(l["skip"]) for l in lines], totals["count"]), ([True, False], 1))

    def test_the_total_for_apply_counts_each_holder_once(self):
        ctx = {"daily_cents": 2000, "lifetime_cents": None, "where": "the campaign “L”", "holder": "c1"}
        self.assertEqual(bulk.spend_totals([ctx, dict(ctx), {**ctx, "holder": "c2", "daily_cents": 500}]),
                         {"daily_cents": 2500, "lifetime_cents": 0, "budgets": ["the campaign “L”", "the campaign “L”"]})

    def test_turning_off_needs_no_money_confirmation(self):
        lines, totals = bulk.status_lines(self.ROWS, "PAUSED", {})
        self.assertEqual(([l["id"] for l in lines if not l["skip"]], totals["daily_cents"]), (["a3"], 0))


class BudgetTests(unittest.TestCase):
    ROWS = [{"id": "c1", "name": "Leads"}, {"id": "c2", "name": "Payroll"}, {"id": "c3", "name": "No budget"}]
    LIVE = {"c1": 3100, "c2": 1500, "c3": None}

    def test_percent_change_with_ceiling_and_big_steps(self):
        lines, totals = bulk.budget_lines(self.ROWS, "pct", 30, self.LIVE, CAP)
        self.assertEqual([(l["id"], l["from"], l["to"], l["big"], l["skip"]) for l in lines],
                         [("c1", 3100, 4030, True, None), ("c2", 1500, 1950, True, None),
                          ("c3", None, None, False, "No daily budget of its own (it's set one level up)")])
        self.assertEqual(totals, {"count": 2, "from_cents": 4600, "to_cents": 5980, "big": True})

    def test_above_the_ceiling_is_skipped_not_capped(self):
        lines, _ = bulk.budget_lines(self.ROWS[:1], "set", 20000, self.LIVE, CAP)
        self.assertTrue(lines[0]["skip"].startswith("That's above this account's ceiling"))

    def test_a_cut_is_never_big(self):
        lines, totals = bulk.budget_lines(self.ROWS[:2], "pct", -50, self.LIVE, CAP)
        self.assertEqual(([l["to"] for l in lines], totals["big"]), ([1550, 750], False))

    def test_deleted_or_archived_ones_are_skipped(self):
        rows = [{"id": "c1", "name": "Old", "status": "DELETED"}, {"id": "c2", "name": "Shelved", "status": "ARCHIVED"}]
        lines, totals = bulk.budget_lines(rows, "set", 2000, self.LIVE, CAP)
        self.assertEqual(([l["skip"] for l in lines], totals["count"]),
                         (["Deleted or archived: its budget can't be changed"] * 2, 0))

    def test_below_one_dollar_is_skipped(self):
        lines, _ = bulk.budget_lines([{"id": "c2", "name": "Payroll"}], "set", 50, self.LIVE, CAP)
        self.assertEqual(lines[0]["skip"], "The new daily budget must be at least 1.00")


class ArchiveTests(unittest.TestCase):
    def test_only_ads_that_are_off(self):
        rows = [{"id": "a1", "name": "N1", "status": "PAUSED"}, {"id": "a2", "name": "N2", "status": "ACTIVE"},
                {"id": "a3", "name": "N3", "status": "ARCHIVED"}]
        lines, totals = bulk.archive_lines(rows)
        self.assertEqual([(l["id"], l["skip"]) for l in lines],
                         [("a1", None), ("a2", "Turn it off first"), ("a3", "Already archived")])
        self.assertEqual(totals, {"count": 1})


class TokenTests(unittest.TestCase):
    PLAN = {"action": "status", "level": "ad", "value": "PAUSED", "user": 1, "lines": [{"id": "a3", "from": "ACTIVE", "to": "PAUSED"}]}

    def test_round_trip(self):
        token = bulk.sign(self.PLAN, SECRET, now=1000)
        self.assertEqual(bulk.verify(token, SECRET, now=1200), self.PLAN)

    def test_expired_or_tampered_is_refused(self):
        token = bulk.sign(self.PLAN, SECRET, now=1000)
        self.assertIsNone(bulk.verify(token, SECRET, now=1000 + 301))
        body, sig = token.rsplit(".", 1)
        self.assertIsNone(bulk.verify(body + "x." + sig, SECRET, now=1001))
        self.assertIsNone(bulk.verify(token, "t" * 32, now=1001))


if __name__ == "__main__":
    unittest.main()
