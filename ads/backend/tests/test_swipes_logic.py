import unittest
from datetime import date

import swipes as sw


class LibraryIdTests(unittest.TestCase):
    def test_links_and_bare_ids(self):
        self.assertEqual([sw.library_id("https://www.facebook.com/ads/library/?id=1234567890123&foo=1"),
                          sw.library_id("https://www.facebook.com/ads/library/?active_status=all&id=998877665544"),
                          sw.library_id(" 1234567 "), sw.library_id("hello"), sw.library_id(None)],
                         ["1234567890123", "998877665544", "1234567", None, None])


class RunningTests(unittest.TestCase):
    def test_days_count_both_ends_and_long_runs_are_called_out(self):
        self.assertEqual([sw.days_running(date(2026, 11, 1), date(2026, 11, 1)), sw.days_running(date(2026, 10, 1), date(2026, 11, 9)),
                          sw.days_running(None, date(2026, 11, 9))], [1, 40, None])
        self.assertEqual([sw.label(1), sw.label(29), sw.label(30)],
                         ["Running 1 day", "Running 29 days", "Running 30 days: likely working"])

    def test_a_stopped_ad_counts_to_the_day_it_stopped(self):
        v = sw.view({"library_id": "123456", "started_on": date(2026, 9, 1), "stopped_on": date(2026, 9, 10)}, date(2026, 11, 9))
        self.assertEqual((v["days_running"], v["still_running"], v["long_running"], v["library_url"]),
                         (10, False, False, "https://www.facebook.com/ads/library/?id=123456"))


class CleanTests(unittest.TestCase):
    def test_a_link_and_a_page_are_enough(self):
        f, err = sw.clean({"link": "https://www.facebook.com/ads/library/?id=5550001112223", "page_name": "  Acme   Software ",
                           "started_on": "2026-09-01", "media_url": "http://insecure.example/x.jpg", "tags": {"hook": " question ", "bogus": "x"}})
        self.assertEqual((err, f["library_id"], f["page_name"], f["started_on"], f["media_url"], f["tags"]),
                         (None, "5550001112223", "Acme Software", date(2026, 9, 1), None, {"hook": "question"}))

    def test_problems(self):
        self.assertEqual([sw.clean({"page_name": "X"})[1], sw.clean({"link": "123456789"})[1]],
                         ["Paste the Ad Library link, or the ad's text", "Say whose ad it is (the Page name)"])


if __name__ == "__main__":
    unittest.main()
