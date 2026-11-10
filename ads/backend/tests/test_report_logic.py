import unittest
from datetime import date

import report_logic as rl

TODAY = date(2026, 11, 10)  # a Tuesday


class PeriodTests(unittest.TestCase):
    def test_last_complete_week_and_month_and_the_ones_before(self):
        self.assertEqual(rl.period("week", TODAY), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(rl.period("month", TODAY), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(rl.previous(date(2026, 11, 2), date(2026, 11, 8), "week"), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(rl.previous(date(2026, 3, 1), date(2026, 3, 31), "month"), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_a_chosen_start_snaps_to_its_week_or_month(self):
        self.assertEqual(rl.period("week", TODAY, start=date(2026, 11, 5)), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(rl.period("month", TODAY, start=date(2026, 2, 14)), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_only_finished_periods_are_complete(self):
        self.assertEqual((rl.complete(date(2026, 11, 8), TODAY), rl.complete(date(2026, 11, 10), TODAY)), (True, False))


class ContentTests(unittest.TestCase):
    def test_funnel_rates_are_shares_of_the_step_before(self):
        self.assertEqual([(s["step"], s["n"], s["rate"]) for s in rl.funnel(40, 30, 6, 2)],
                         [("Leads", 40, None), ("Contacted", 30, 75), ("Qualified", 6, 20), ("Won", 2, 33)])

    def test_headline_uses_qualified_leads_when_there_are_any_and_says_when_it_is_thin(self):
        h = rl.headline({"spend_cents": 14000, "leads": 30, "qualified": 2}, {"spend_cents": 14000, "leads": 25, "qualified": 1}, 6000)
        self.assertEqual(h, "Cost per qualified lead was $70.00 against the $60.00 target (over by $10.00), down from $140.00 the period before. "
                            "2 qualified leads from $140.00 spent; at this volume the number is directional.")

    def test_headline_falls_back_to_leads_and_to_spend(self):
        self.assertEqual(rl.headline({"spend_cents": 9000, "leads": 18, "qualified": 0}, {"spend_cents": 0, "leads": 0}),
                         "Cost per lead was $5.00. 18 leads from $90.00 spent.")
        self.assertEqual(rl.headline({"spend_cents": 500, "leads": 0, "qualified": 0}, {"spend_cents": 0, "leads": 0}),
                         "$5.00 spent and no leads yet. 0 leads from $5.00 spent.")

    def test_the_measurement_change_footnote_only_when_the_period_spans_it(self):
        self.assertEqual([len(rl.footnotes(date(2026, 11, 2), date(2026, 11, 8))), len(rl.footnotes(date(2026, 11, 9), date(2026, 11, 15)))], [2, 3])


class ShareTests(unittest.TestCase):
    def test_a_signed_link_round_trips_and_tampering_or_expiry_fails(self):
        t = rl.sign("s3cret", {"a": 2, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"})
        self.assertEqual(rl.verify("s3cret", t, TODAY), {"a": 2, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"})
        body, mac = t.rsplit(".", 1)
        forged = rl.sign("other", {"a": 1, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"}).rsplit(".", 1)[0] + "." + mac
        self.assertEqual([rl.verify("wrong", t, TODAY), rl.verify("s3cret", forged, TODAY), rl.verify("s3cret", t, date(2027, 3, 1)),
                          rl.verify("s3cret", "garbage", TODAY)], [None, None, None, None])


if __name__ == "__main__":
    unittest.main()
