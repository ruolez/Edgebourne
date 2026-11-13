"""FU-C: today's numbers read live from Meta for screens, at most every 90 s per account, never waited on twice
when Meta is slow, and never read while someone else is reading them."""
import unittest
from contextlib import contextmanager
from datetime import date
from unittest import mock

import account_ctx
import insights
import meta_client

ACCOUNT = 4747
DAY = date(2026, 11, 12)
SLOW = meta_client.MetaError("Meta didn't answer in time. Try again in a minute.", code="network")


class TodayFreshTests(unittest.TestCase):
    NOW = 1_000_000.0

    def test_fresh_for_ninety_seconds(self):
        self.assertEqual([insights.today_fresh(self.NOW - age, self.NOW) for age in (0, 89, 91)], [True, True, False])

    def test_never_read_or_unreadable_is_not_fresh(self):
        self.assertEqual([insights.today_fresh(v, self.NOW) for v in (None, "", "x")], [False, False, False])

    def test_a_stamp_from_the_future_is_not_fresh(self):
        self.assertFalse(insights.today_fresh(self.NOW + 600, self.NOW))


class TodaySnapshotTests(unittest.TestCase):
    def test_per_campaign_sums_of_todays_ad_rows_with_the_day(self):
        rows = [{"day": "2026-11-12", "campaign_id": "c1", "spend_cents": 250, "leads": 1},
                {"day": "2026-11-12", "campaign_id": "c1", "spend_cents": 100, "leads": 0},
                {"day": "2026-11-12", "campaign_id": "c2", "spend_cents": 75, "leads": 2},
                {"day": "2026-11-11", "campaign_id": "c1", "spend_cents": 999, "leads": 9}]
        self.assertEqual(insights.today_snapshot_from(rows, DAY, 5.0),
                         {"at": 5.0, "day": "2026-11-12", "campaigns": {"c1": {"spend_cents": 350, "leads": 1},
                                                                         "c2": {"spend_cents": 75, "leads": 2}}})


class ReadTodayTests(unittest.TestCase):
    NOW = 2_000_000.0

    def setUp(self):
        meta_client._read_failed.clear()
        self.stored = {"today_ads_at": None, "meta_ad_account_id": "123", "meta_system_token": "t"}
        self.writes = []

    def run_read(self, reads, force=False, lock=True, stamp=None, timeout=None):
        if stamp is not None:
            self.stored["today_ads_at"] = str(stamp)

        @contextmanager
        def holding(_acct, wait=0.0):
            yield lock

        def fake_read(since, until, timeout=None):
            self.reads.append((since, until, timeout))
            nxt = reads.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        self.reads = []
        with mock.patch.object(insights.settings_store, "get", side_effect=lambda k, d=None: self.stored.get(k, d)), \
                mock.patch.object(insights.settings_store, "set", side_effect=lambda k, v: self.stored.__setitem__(k, v)), \
                mock.patch.object(insights, "read_days", side_effect=fake_read), \
                mock.patch.object(insights.db, "execute", side_effect=lambda sql, p=None: self.writes.append(p)), \
                mock.patch.object(insights.account_info, "today", return_value=DAY), \
                mock.patch("refresh_api.holding_pull_lock", holding), account_ctx.use(ACCOUNT):
            return insights.read_today(force=force, now=self.NOW, **({} if timeout is None else {"timeout": timeout}))

    ROW = {**{c: 0 for c in insights.DAILY_COLUMNS}, "day": "2026-11-12", "ad_id": "a1", "campaign_id": "c1", "spend_cents": 750, "leads": 1}

    def test_reads_todays_ad_rows_stores_them_and_stamps_the_read(self):
        out = self.run_read([[self.ROW]])
        self.assertEqual((out, self.reads, len(self.writes), self.stored["today_ads_at"]),
                         ({"as_of": self.NOW, "read": True, "error": None}, [(DAY, DAY, meta_client.READ_TIMEOUT)], 1, str(self.NOW)))

    def test_a_read_under_ninety_seconds_old_is_used_as_it_is(self):
        out = self.run_read([], stamp=self.NOW - 60)
        self.assertEqual((out, self.reads), ({"as_of": self.NOW - 60, "read": False, "error": None}, []))

    def test_refresh_reads_again_even_when_fresh(self):
        out = self.run_read([[self.ROW]], force=True, stamp=self.NOW - 10)
        self.assertEqual((out["read"], len(self.reads)), (True, 1))

    def test_someone_reading_now_means_the_stored_rows_stand(self):
        out = self.run_read([], lock=False, stamp=self.NOW - 300)
        self.assertEqual((out, self.reads, self.writes), ({"as_of": self.NOW - 300, "read": False, "error": None}, [], []))

    def test_a_slow_meta_is_asked_once_then_the_stored_numbers_stand(self):
        first = self.run_read([SLOW], stamp=self.NOW - 300)
        again = self.run_read([], stamp=self.NOW - 300)
        self.assertEqual((first["read"], bool(first["error"]), again["read"], bool(again["error"]), len(self.reads), self.writes),
                         (False, True, False, True, 0, []))

    def test_reads_within_the_time_a_page_has_left(self):
        self.run_read([[self.ROW]], timeout=3.5)
        self.assertEqual(self.reads, [(DAY, DAY, 3.5)])

    def test_no_time_left_reads_nothing_and_remembers_no_failure(self):
        out = self.run_read([], timeout=0.4, stamp=self.NOW - 300)
        self.assertEqual((out, self.reads, meta_client.recently_failed("today_ads")),
                         ({"as_of": self.NOW - 300, "read": False, "error": None, "skipped": True}, [], None))

    def test_refresh_flag_reads_again_once_while_the_old_time_stays_for_the_wording(self):
        self.stored["today_ads_force"] = "1"
        first = self.run_read([[self.ROW]], stamp=self.NOW - 10)
        first_reads = len(self.reads)
        again = self.run_read([], stamp=self.NOW - 5)
        self.assertEqual((first["read"], first_reads, self.stored["today_ads_force"], again["read"], len(self.reads)), (True, 1, None, False, 0))

    def test_refresh_flag_waits_while_someone_else_reads(self):
        self.stored["today_ads_force"] = "1"
        out = self.run_read([], lock=False, stamp=self.NOW - 10)
        self.assertEqual((out["as_of"], out["read"], self.stored["today_ads_force"]), (self.NOW - 10, False, "1"))

    def test_not_connected_reads_nothing(self):
        self.stored["meta_ad_account_id"] = None
        out = self.run_read([])
        self.assertEqual((out, self.reads), ({"as_of": None, "read": False, "error": None}, []))


class YesterdayHoursTests(unittest.TestCase):
    REFUSED = meta_client.MetaError("(#100) breakdowns is not valid", code=100)

    def setUp(self):
        meta_client._read_failed.clear()

    def test_after_meta_left_todays_read_unanswered_the_page_does_not_wait_again(self):
        meta_client.remember_failure("today_ads", SLOW)
        asked = []
        out, _ = self.run_hours(lambda key, ttl, fetch: asked.append(key) or [])
        self.assertEqual((out, asked), (None, []))

    def run_hours(self, cached):
        stored = []
        with mock.patch.object(insights.settings_store, "get", side_effect=lambda k, d=None: {"meta_ad_account_id": "123"}.get(k, d)), \
                mock.patch.object(insights.account_info, "yesterday", return_value=date(2026, 11, 11)), \
                mock.patch("insights_api.cached", side_effect=cached), \
                mock.patch("insights_api.store", side_effect=lambda k, v: stored.append((k, v))):
            return insights.yesterday_hours("campaign"), stored

    def raise_(self, exc):
        def go(*_a, **_k):
            raise exc
        return go

    def test_a_refusal_is_kept_for_an_hour_so_meta_is_not_asked_on_every_open(self):
        out, stored = self.run_hours(self.raise_(self.REFUSED))
        self.assertEqual((out, [k for k, _ in stored], all(isinstance(v, dict) and v.get("refused") for _, v in stored)),
                         (None, ["hourly:2026-11-11:campaign"], True))

    def test_a_kept_refusal_reads_as_not_compared(self):
        out, stored = self.run_hours(lambda key, ttl, fetch: {"refused": "(#100) breakdowns is not valid"})
        self.assertEqual((out, stored), (None, []))

    def test_a_slow_meta_is_not_kept_as_a_refusal(self):
        out, stored = self.run_hours(self.raise_(SLOW))
        self.assertEqual((out, stored), (None, []))

    def test_hour_rows_come_back_as_meta_gave_them(self):
        rows = [{"campaign_id": "c1", "spend": "1.00"}]
        out, _ = self.run_hours(lambda key, ttl, fetch: rows)
        self.assertEqual(out, rows)


if __name__ == "__main__":
    unittest.main()
