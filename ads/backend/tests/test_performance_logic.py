import unittest
from datetime import date

import performance_api


class PeriodTests(unittest.TestCase):
    def test_the_last_7_complete_days_and_the_7_before_them(self):
        self.assertEqual(performance_api.periods(date(2026, 11, 9), 7),
                         ((date(2026, 11, 2), date(2026, 11, 8)), (date(2026, 10, 26), date(2026, 11, 1))))

    def test_a_30_day_period_crosses_the_month_and_the_one_before_does_not_overlap(self):
        (start, end), (prev_start, prev_end) = performance_api.periods(date(2026, 3, 1), 30)
        self.assertEqual((start, end, prev_start, prev_end),
                         (date(2026, 1, 30), date(2026, 2, 28), date(2025, 12, 31), date(2026, 1, 29)))


if __name__ == "__main__":
    unittest.main()
