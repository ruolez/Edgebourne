import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import links
import words

LA = ZoneInfo("America/Los_Angeles")


class MoneyTests(unittest.TestCase):
    def test_amounts_in_the_account_currency(self):
        cases = [((2000, "USD"), "$20.00"), ((123450, "EUR"), "€1,234.50"), ((2500, "CAD"), "25.00 CAD"),
                 ((None, "USD"), "—")]
        self.assertEqual([words.money(*args) for args, _ in cases], [want for _, want in cases])

    def test_whole_leaves_the_cents_out(self):
        self.assertEqual(words.money(3000, "GBP", whole=True), "£30")


class DayTests(unittest.TestCase):
    def test_dates_read_the_same_everywhere(self):
        self.assertEqual([words.day(date(2026, 11, 9)), words.weekday(date(2026, 11, 13)),
                          words.day_time(datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc), LA)],
                         ["Nov 9", "Fri, Nov 13", "Thu, Nov 12, 2:00 PM"])

    def test_a_time_is_read_in_the_account_zone(self):
        self.assertEqual(words.day_time(datetime(2026, 11, 13, 7, 59, tzinfo=timezone.utc), LA), "Thu, Nov 12, 11:59 PM")


class AgoTests(unittest.TestCase):
    NOW = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)

    def test_how_long_ago(self):
        cases = {timedelta(minutes=20): "today", timedelta(hours=1): "1 hour ago", timedelta(hours=5): "5 hours ago",
                 timedelta(hours=24): "1 day ago", timedelta(hours=47): "1 day ago", timedelta(days=2): "2 days ago"}
        self.assertEqual({d: words.ago(self.NOW - d, self.NOW) for d in cases}, cases)


class HistoryHrefTests(unittest.TestCase):
    def test_each_page_keeps_its_tab_where_its_code_reads_it(self):
        self.assertEqual([links.history_href("campaign", "C1"), links.history_href("adset", "S1"),
                          links.history_href("ad", "A1"), links.history_href("campaign", "C1", check=7),
                          links.history_href("ad", "A1", check=7)],
                         ["/campaign.html?id=C1&tab=history", "/adset.html?id=S1&tab=history", "/ad.html?id=A1#tab=history",
                          "/campaign.html?id=C1&tab=history&check=7", "/ad.html?id=A1&check=7#tab=history"])

    def test_ids_are_escaped(self):
        self.assertEqual(links.history_href("campaign", "a&b"), "/campaign.html?id=a%26b&tab=history")


if __name__ == "__main__":
    unittest.main()
