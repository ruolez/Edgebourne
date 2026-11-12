import unittest
from datetime import date

import ranges

TODAY = date(2026, 11, 10)


class WindowTests(unittest.TestCase):
    def test_last_n_days_end_yesterday(self):
        self.assertEqual(ranges.window("7", TODAY), (date(2026, 11, 3), date(2026, 11, 9)))
        self.assertEqual(ranges.window("14", TODAY), (date(2026, 10, 27), date(2026, 11, 9)))

    def test_month_to_date_and_last_month(self):
        self.assertEqual(ranges.window("mtd", TODAY), (date(2026, 11, 1), date(2026, 11, 9)))
        self.assertEqual(ranges.window("lastmonth", TODAY), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_month_to_date_on_the_first_is_last_month(self):
        self.assertEqual(ranges.window("mtd", date(2026, 12, 1)), (date(2026, 11, 1), date(2026, 11, 30)))

    def test_custom_is_clamped_to_complete_days_and_ordered(self):
        self.assertEqual(ranges.window("custom", TODAY, "2026-11-20", "2026-11-01"), (date(2026, 11, 1), date(2026, 11, 9)))

    def test_unknown_or_bad_falls_back_to_seven_days(self):
        self.assertEqual(ranges.window("nonsense", TODAY), ranges.window("7", TODAY))
        self.assertEqual(ranges.window("custom", TODAY, "x", None), ranges.window("7", TODAY))

    def test_custom_is_at_most_a_year(self):
        start, end = ranges.window("custom", TODAY, "2020-01-01", "2026-11-09")
        self.assertEqual(((end - start).days + 1, end), (366, date(2026, 11, 9)))


class PreviousTests(unittest.TestCase):
    def test_previous_is_the_same_length_just_before(self):
        self.assertEqual(ranges.previous(date(2026, 10, 27), date(2026, 11, 9), "14"), (date(2026, 10, 13), date(2026, 10, 26)))

    def test_previous_of_a_calendar_month_is_the_month_before(self):
        self.assertEqual(ranges.previous(date(2026, 10, 1), date(2026, 10, 31), "lastmonth"), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_previous_of_month_to_date_is_the_same_days_last_month(self):
        self.assertEqual(ranges.previous(date(2026, 11, 1), date(2026, 11, 9), "mtd"), (date(2026, 10, 1), date(2026, 10, 9)))

    def test_month_to_date_on_the_first_compares_the_whole_month_before(self):
        self.assertEqual(ranges.previous(*ranges.window("mtd", date(2026, 12, 1)), "mtd"), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_day_windows_that_start_on_the_first_compare_with_the_days_just_before(self):
        # Nov 8: the last 7 days are Nov 1-7; Nov 15: the last 14 are Nov 1-14 (audit A3-14).
        cases = [("7", date(2026, 11, 8)), ("14", date(2026, 11, 15)), ("30", date(2026, 12, 1))]
        self.assertEqual([ranges.previous(*ranges.window(k, t), k) for k, t in cases],
                         [(date(2026, 10, 25), date(2026, 10, 31)), (date(2026, 10, 18), date(2026, 10, 31)),
                          (date(2026, 10, 2), date(2026, 10, 31))])

    def test_a_custom_window_on_the_first_compares_with_the_days_just_before(self):
        start, end = ranges.window("custom", TODAY, "2026-11-01", "2026-11-09")
        self.assertEqual(ranges.previous(start, end, "custom"), (date(2026, 10, 23), date(2026, 10, 31)))


if __name__ == "__main__":
    unittest.main()


class DailySeriesTests(unittest.TestCase):
    KEYS = ("spend_cents", "leads")

    def test_every_day_of_the_window_in_order_with_missing_days_as_zero(self):
        rows = {"2026-11-02": {"spend_cents": 150, "leads": 1}, "2026-11-04": {"spend_cents": 90, "leads": None}}
        self.assertEqual(ranges.daily_series(rows, date(2026, 11, 1), date(2026, 11, 4), self.KEYS), [
            {"day": "2026-11-01", "spend_cents": 0, "leads": 0},
            {"day": "2026-11-02", "spend_cents": 150, "leads": 1},
            {"day": "2026-11-03", "spend_cents": 0, "leads": 0},
            {"day": "2026-11-04", "spend_cents": 90, "leads": 0},
        ])

    def test_days_outside_the_window_are_left_out(self):
        rows = {"2026-10-31": {"spend_cents": 5, "leads": 5}, "2026-11-05": {"spend_cents": 7, "leads": 7}}
        self.assertEqual(ranges.daily_series(rows, date(2026, 11, 1), date(2026, 11, 1), self.KEYS),
                         [{"day": "2026-11-01", "spend_cents": 0, "leads": 0}])

    def test_a_month_window_has_one_entry_per_day(self):
        start, end = ranges.window("lastmonth", TODAY)
        series = ranges.daily_series({}, start, end, self.KEYS)
        self.assertEqual((len(series), series[0]["day"], series[-1]["day"]), (31, "2026-10-01", "2026-10-31"))
