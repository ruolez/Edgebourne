import unittest
from datetime import datetime, timezone

import tracking as tr

NOW = datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc)
CRM_OK = {"pending": 0, "sent": 12, "failed": 0}


class ParseTests(unittest.TestCase):
    def test_times_and_the_epoch_meaning_never(self):
        # The live dataset on 2026-11-09 reported 1969-12-31T16:00:00-0800: never fired.
        self.assertEqual([tr.parse_time("1969-12-31T16:00:00-0800"), tr.parse_time(None), tr.parse_time("0"),
                          tr.parse_time("2026-11-09T19:00:00-0800"), tr.parse_time(1794276000)],
                         [None, None, None, datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc), datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc)])

    def test_counts_sum_the_buckets_and_sources_split_server_from_browser(self):
        body = {"data": [{"start_time": "a", "data": [{"value": "Lead", "count": 3}, {"value": "Qualified", "count": 1}]},
                         {"start_time": "b", "data": [{"value": "Lead", "count": "2"}]}]}
        self.assertEqual(tr.counts(body), {"Lead": 5, "Qualified": 1})
        src = {"data": [{"data": [{"value": "SERVER", "count": 6}, {"value": "BROWSER", "count": 2}]}]}
        self.assertEqual(tr.sources(src), {"server": 6, "browser": 2})

    def test_quality_reads_emq_per_channel(self):
        q = {"web": [], "crm": [{"event_name": "Lead", "event_match_quality": {"composite_score": 7.36}}]}
        self.assertEqual(tr.quality(q), [{"channel": "crm", "event": "Lead", "emq": 7.4}])


class AssessTests(unittest.TestCase):
    def test_the_live_dataset_today_reads_not_set_up_and_says_what_to_do(self):
        a = tr.assess({"last_fired_time": "1969-12-31T16:00:00-0800", "server_last_fired_time": "1969-12-31T16:00:00-0800"},
                      {}, {"server": 0, "browser": 0}, [], {"failed": 0}, NOW, crm_on=False)
        self.assertEqual((a["state"], a["todo"]), ("not_set_up", ["Turn on Settings → Lead stages to Meta, so Meta learns which leads become clients."]))

    def test_quiet_after_two_days(self):
        a = tr.assess({"server_last_fired_time": "2026-11-07T00:00:00+0000"}, {"Lead": 4}, {"server": 4, "browser": 0}, [], CRM_OK, NOW, True)
        self.assertEqual((a["state"], a["headline"][:30]), ("quiet", "Nothing has arrived for 3 days"))

    def test_low_match_quality_is_weak_with_the_fix(self):
        a = tr.assess({"server_last_fired_time": "2026-11-10T03:00:00+0000"}, {"Lead": 9}, {"server": 9, "browser": 0},
                      [{"channel": "crm", "event": "Lead", "emq": 4.2}], CRM_OK, NOW, True)
        self.assertEqual((a["state"], a["server_share"], a["todo"][0][:30]), ("weak", 100, "Match quality is 4.2/10 for Le"))

    def test_healthy(self):
        a = tr.assess({"server_last_fired_time": "2026-11-10T03:00:00+0000"}, {"Lead": 9}, {"server": 6, "browser": 2},
                      [{"channel": "crm", "event": "Lead", "emq": 8.1}], CRM_OK, NOW, True)
        self.assertEqual((a["state"], a["server_share"], a["todo"]), ("ok", 75, []))


if __name__ == "__main__":
    unittest.main()
