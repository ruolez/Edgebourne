"""Audit 3 performance cluster (A3-46, A3-121, A3-123, A3-126, A3-130, A3-131): pages don't wait on Meta
one read after another, a Meta that doesn't answer is not asked again on every load, and lists don't run
a query per row."""
import threading
import time
import unittest
from datetime import date, datetime, timezone
from unittest import mock

import account_ctx
import ads_api
import bulk_api
import experiments as ex
import home_api
import inbox
import insights
import insights_api
import meta_client

ACCOUNT = 4343
SLOW = meta_client.MetaError("Meta didn't answer in time. Try again in a minute.", code="network")
REFUSED = meta_client.MetaError("Invalid parameter", code=100, status=400)


def forget_failures():
    meta_client._read_failed.clear()


class FailureMemoryTests(unittest.TestCase):
    def setUp(self):
        forget_failures()

    def test_a_read_meta_left_unanswered_is_remembered_for_a_while(self):
        with account_ctx.use(ACCOUNT):
            meta_client.remember_failure("reach:ad:x", SLOW, now=1000)
            seen = [bool(meta_client.recently_failed("reach:ad:x", now=1000 + s)) for s in (1, meta_client.FAIL_SECONDS - 1,
                                                                                            meta_client.FAIL_SECONDS + 1)]
        self.assertEqual(seen, [True, True, False])

    def test_a_refusal_is_an_answer_and_is_not_remembered(self):
        with account_ctx.use(ACCOUNT):
            meta_client.remember_failure("reach:ad:x", REFUSED, now=1000)
            self.assertIsNone(meta_client.recently_failed("reach:ad:x", now=1001))

    def test_one_accounts_failure_never_holds_back_another(self):
        with account_ctx.use(ACCOUNT):
            meta_client.remember_failure("reach:ad:x", SLOW, now=1000)
        with account_ctx.use(ACCOUNT + 1):
            self.assertIsNone(meta_client.recently_failed("reach:ad:x", now=1001))


class CachedTests(unittest.TestCase):
    """insights_api.cached: one wait per couple of minutes when Meta is slow, the last answer when allowed."""

    def setUp(self):
        forget_failures()

    def run_cached(self, row, fetch, stale_ok=False, times=2):
        out = []
        with mock.patch.object(insights_api.db, "query", return_value=row), \
                mock.patch.object(insights_api.db, "execute"), account_ctx.use(ACCOUNT):
            for _ in range(times):
                try:
                    out.append(insights_api.cached("k", 60, fetch, stale_ok=stale_ok))
                except meta_client.MetaError as exc:
                    out.append(type(exc).__name__)
        return out

    def test_a_slow_meta_is_asked_once_then_left_alone(self):
        fetch = mock.Mock(side_effect=SLOW)
        out = self.run_cached(None, fetch)
        self.assertEqual((out, fetch.call_count), (["MetaError", "MetaError"], 1))

    def test_the_last_stored_answer_stands_in_when_allowed(self):
        fetch = mock.Mock(side_effect=SLOW)
        out = self.run_cached({"data": {"reach": 7}, "age": 999}, fetch, stale_ok=True)
        self.assertEqual((out, fetch.call_count), ([{"reach": 7}, {"reach": 7}], 1))

    def test_a_stored_answer_older_than_a_day_is_not_served_as_current(self):
        fetch = mock.Mock(side_effect=SLOW)
        out = self.run_cached({"data": {"reach": 7}, "age": insights_api.STALE_MAX + 60}, fetch, stale_ok=True, times=1)
        self.assertEqual(out, ["MetaError"])

    def test_a_fresh_answer_needs_no_meta_call(self):
        fetch = mock.Mock(return_value={"reach": 1})
        self.assertEqual((self.run_cached({"data": {"reach": 9}, "age": 5}, fetch, times=1), fetch.call_count), ([{"reach": 9}], 0))


class ReadManyTests(unittest.TestCase):
    def test_reads_run_side_by_side_on_the_callers_account_with_the_short_timeout(self):
        seen = []
        together = threading.Barrier(3, timeout=3)  # only passes when all three reads are in flight at once

        def request(method, url, params=None, timeout=None, **kw):
            together.wait()
            seen.append((account_ctx.current(), timeout))
            return mock.Mock(status_code=200, json=lambda: {"data": [{"n": url.rsplit("/", 1)[-1]}]})
        with mock.patch.object(meta_client.requests, "request", side_effect=request), \
                mock.patch.object(meta_client, "system_token", return_value="t"), \
                mock.patch.object(meta_client, "_base", return_value="http://fake"), \
                mock.patch.object(meta_client, "_note_success"), account_ctx.use(ACCOUNT):
            out = meta_client.read_many([("a", {}), ("b", {}), ("c", {})])
        self.assertEqual((out, seen), ([[{"n": "a"}], [{"n": "b"}], [{"n": "c"}]], [(ACCOUNT, meta_client.READ_TIMEOUT)] * 3))

    def test_a_failed_read_comes_back_as_its_error_and_the_rest_still_answer(self):
        def request(method, url, params=None, timeout=None, **kw):
            if url.endswith("/b"):
                raise meta_client.requests.Timeout("slow")
            return mock.Mock(status_code=200, json=lambda: {"data": [1]})
        with mock.patch.object(meta_client.requests, "request", side_effect=request), \
                mock.patch.object(meta_client, "system_token", return_value="t"), \
                mock.patch.object(meta_client, "_base", return_value="http://fake"), \
                mock.patch.object(meta_client, "_note_success"), account_ctx.use(ACCOUNT):
            a, b = meta_client.read_many([("a", {}), ("b", {})])
        self.assertEqual((a, type(b).__name__, b.code), ([1], "MetaError", "network"))

    def test_a_read_still_running_at_the_deadline_counts_as_unanswered(self):
        release = threading.Event()

        def request(method, url, params=None, timeout=None, **kw):
            if url.endswith("/hangs"):
                release.wait(5)
            return mock.Mock(status_code=200, json=lambda: {"data": [1]})
        with mock.patch.object(meta_client.requests, "request", side_effect=request), \
                mock.patch.object(meta_client, "system_token", return_value="t"), \
                mock.patch.object(meta_client, "_base", return_value="http://fake"), \
                mock.patch.object(meta_client, "_note_success"), account_ctx.use(ACCOUNT):
            began = time.monotonic()
            quick, hung = meta_client.read_many([("quick", {}), ("hangs", {})], timeout=0.2)
            took = time.monotonic() - began
        release.set()
        self.assertEqual((quick, hung.code, took < 2), ([1], "network", True))

    def test_every_read_of_a_full_page_runs_at_once_so_a_slow_meta_that_answers_is_not_cut(self):
        # The Ads page asks up to 16 windows; each answers in 0.8 x timeout. Queued behind a smaller pool,
        # the second half would end past the deadline (timeout + 1 s) and be thrown away as unanswered.
        limit = 2.5

        def request(method, url, params=None, timeout=None, **kw):
            time.sleep(0.8 * limit)
            return mock.Mock(status_code=200, json=lambda: {"data": [url.rsplit("/", 1)[-1]]})
        names = [f"r{i}" for i in range(16)]
        with mock.patch.object(meta_client.requests, "request", side_effect=request), \
                mock.patch.object(meta_client, "system_token", return_value="t"), \
                mock.patch.object(meta_client, "_base", return_value="http://fake"), \
                mock.patch.object(meta_client, "_note_success"), account_ctx.use(ACCOUNT):
            out = meta_client.read_many([(n, {}) for n in names], timeout=limit)
        self.assertEqual(out, [[n] for n in names])

    def test_a_read_that_never_started_before_the_deadline_is_not_held_against_meta(self):
        forget_failures()
        release = threading.Event()

        def request(method, url, params=None, timeout=None, **kw):
            release.wait(5)
            return mock.Mock(status_code=200, json=lambda: {"data": [1]})
        with mock.patch.object(meta_client.requests, "request", side_effect=request), \
                mock.patch.object(meta_client, "system_token", return_value="t"), \
                mock.patch.object(meta_client, "_base", return_value="http://fake"), \
                mock.patch.object(meta_client, "_note_success"), account_ctx.use(ACCOUNT):
            hung, unasked = meta_client.read_many([("hangs", {}), ("queued", {})], timeout=0.2, workers=1)
            meta_client.remember_failure("hangs", hung)
            meta_client.remember_failure("queued", unasked)
            remembered = (bool(meta_client.recently_failed("hangs")), bool(meta_client.recently_failed("queued")))
        release.set()
        self.assertEqual((hung.code, isinstance(unasked, meta_client.MetaError), remembered), ("network", True, (True, False)))


class ReachManyTests(unittest.TestCase):
    D1, D2 = date(2026, 11, 1), date(2026, 11, 7)

    def setUp(self):
        forget_failures()

    def run_reach(self, stored, answers, wanted, stale_ok=True):
        reads = []

        def read_many(rs, timeout=None):
            reads.extend(rs)
            return [answers.pop(0) for _ in rs]
        with mock.patch.object(insights.settings_store, "get", return_value="123"), \
                mock.patch.object(insights_api, "cache_rows", return_value=stored), \
                mock.patch.object(insights_api, "store") as store, \
                mock.patch.object(insights.meta_client, "read_many", side_effect=read_many), account_ctx.use(ACCOUNT):
            out = insights.reach_many(wanted, stale_ok=stale_ok)
        return out, reads, store

    def test_fresh_windows_come_from_the_cache_and_the_rest_in_one_parallel_batch(self):
        fresh = insights.reach_key("ad", self.D1, self.D2)
        out, reads, store = self.run_reach(
            {fresh: ({"a1": 5}, 10)}, [[{"adset_id": "s1", "reach": "40"}], [{"account_id": "1", "reach": "90"}]],
            {"ad": ("ad", self.D1, self.D2, None, 1800), "adset": ("adset", self.D1, self.D2, None, 1800),
             "acct": ("account", None, None, "maximum", 1800)})
        self.assertEqual((out, [r[1]["level"] for r in reads], store.call_count),
                         ({"ad": {"a1": 5}, "adset": {"s1": 40}, "acct": {"account": 90}}, ["adset", "account"], 2))

    def test_the_same_window_asked_twice_is_read_once(self):
        out, reads, _ = self.run_reach({}, [[{"ad_id": "a1", "reach": "3"}]],
                                       {"x": ("ad", self.D1, self.D2, None, 600), "y": ("ad", self.D1, self.D2, None, 1800)})
        self.assertEqual((out, len(reads)), ({"x": {"a1": 3}, "y": {"a1": 3}}, 1))

    def test_a_window_meta_doesnt_answer_keeps_its_last_answer_on_a_page_and_none_elsewhere(self):
        key = insights.reach_key("ad", self.D1, self.D2)
        page, _, _ = self.run_reach({key: ({"a1": 4}, 3600)}, [SLOW], {"x": ("ad", self.D1, self.D2, None, 1800)})
        forget_failures()
        worker, _, _ = self.run_reach({key: ({"a1": 4}, 3600)}, [SLOW], {"x": ("ad", self.D1, self.D2, None, 1800)}, stale_ok=False)
        self.assertEqual((page, worker), ({"x": {"a1": 4}}, {"x": None}))

    def test_a_stored_answer_older_than_a_day_never_stands_in(self):
        # Since-it-started reach kept for weeks would sit next to today's views and understate both: a page
        # gets None (daily sum, marked as such) instead.
        key = insights.reach_key("ad", preset="maximum")
        old, recent = insights_api.STALE_MAX + 60, insights_api.STALE_MAX - 60
        cut, _, _ = self.run_reach({key: ({"a1": 4}, old)}, [SLOW], {"ever": ("ad", None, None, "maximum", 1800)})
        again, reads, _ = self.run_reach({key: ({"a1": 4}, old)}, [], {"ever": ("ad", None, None, "maximum", 1800)})
        forget_failures()
        kept, _, _ = self.run_reach({key: ({"a1": 4}, recent)}, [SLOW], {"ever": ("ad", None, None, "maximum", 1800)})
        self.assertEqual((cut, again, reads, kept), ({"ever": None}, {"ever": None}, [], {"ever": {"a1": 4}}))

    def test_after_a_failure_the_next_load_doesnt_wait_on_meta_again(self):
        self.run_reach({}, [SLOW], {"x": ("ad", self.D1, self.D2, None, 1800)})
        out, reads, _ = self.run_reach({}, [], {"x": ("ad", self.D1, self.D2, None, 1800)})
        self.assertEqual((out, reads), ({"x": None}, []))


class TodayTests(unittest.TestCase):
    def setUp(self):
        forget_failures()

    def test_when_meta_doesnt_answer_today_serves_what_it_has_and_says_so(self):
        # How often Meta is asked (90 s, once per two minutes when slow) is tests/test_live_today_logic.ReadTodayTests.
        snap = {"at": 1.0, "day": "2026-11-11", "campaigns": {"c1": {"spend_cents": 500, "leads": 1}}}
        with mock.patch.object(home_api.insights, "stored_today", return_value=snap), \
                mock.patch.object(home_api.insights, "read_today", return_value={"as_of": 1.0, "read": False, "error": "Meta didn't answer"}), \
                account_ctx.use(ACCOUNT):
            out = home_api.today_by_campaign()
        self.assertEqual(out, {**snap, "error": "Meta didn't answer"})


class BulkReadTests(unittest.TestCase):
    def test_live_values_for_a_selection_come_in_one_read(self):
        with mock.patch.object(bulk_api.meta_client, "get", return_value={"a1": {"status": "PAUSED"}, "a2": {"status": "ACTIVE"}}) as get:
            out = bulk_api.live_nodes(["a1", "a2"], "status")
        self.assertEqual((out, get.call_count, get.call_args.kwargs), ({"a1": {"status": "PAUSED"}, "a2": {"status": "ACTIVE"}}, 1,
                                                                       {"ids": "a1,a2", "fields": "status"}))

    def test_an_id_meta_leaves_out_fails_the_read_rather_than_using_the_stored_value(self):
        with mock.patch.object(bulk_api.meta_client, "get", return_value={"a1": {"status": "PAUSED"}}):
            with self.assertRaises(meta_client.MetaError):
                bulk_api.live_nodes(["a1", "a2"], "status")

    def test_ads_in_one_ad_set_read_its_budget_once(self):
        nodes = {"a1": {"adset_id": "s1", "campaign_id": "c1"}, "a2": {"adset_id": "s1", "campaign_id": "c1"}}
        budgets = {"s1": {"daily_budget": "2000"}}
        calls = []

        def get(eid, fields=None, **kw):
            calls.append(eid)
            return nodes.get(eid) or budgets[eid]
        memo = {}
        with mock.patch.object(ads_api.meta_client, "get", side_effect=get), \
                mock.patch.object(ads_api, "entity", return_value={"name": "Set 1"}):
            out = [ads_api.spend_context("ad", {"id": i}, memo) for i in ("a1", "a2")]
        self.assertEqual(([o["daily_cents"] for o in out], [o["holder"] for o in out], calls), ([2000, 2000], ["s1", "s1"], ["a1", "s1", "a2"]))


    def test_a_campaign_budget_is_read_with_stop_time_not_end_time(self):
        nodes = {"a1": {"adset_id": "s1", "campaign_id": "c1"}, "s1": {},
                 "c1": {"lifetime_budget": "50000", "stop_time": "2026-12-01T07:59:00-0800"}}
        asked = []

        def get(eid, fields=None, **kw):
            asked.append((eid, fields))
            if eid == "c1" and "end_time" in fields:
                raise meta_client.MetaError("(#100) Tried accessing nonexisting field (end_time)")
            return nodes[eid]
        with mock.patch.object(ads_api.meta_client, "get", side_effect=get), \
                mock.patch.object(ads_api, "entity", return_value={"name": "Camp"}):
            out = ads_api.spend_context("ad", {"id": "a1"})
        self.assertEqual(((out["lifetime_cents"], out["end_time"], out["holder"]), asked[1:]),
                         ((50000, "2026-12-01T07:59:00-0800", "c1"),
                          [("s1", "daily_budget,lifetime_budget,end_time"), ("c1", "daily_budget,lifetime_budget,stop_time")]))


class ArmSumsTests(unittest.TestCase):
    ROWS = [{"ad_id": "a1", "adset_id": "s1", "spend_cents": 100, "impressions": 10, "link_clicks": 1, "leads": 1, "video_3s": 2},
            {"ad_id": "a2", "adset_id": "s1", "spend_cents": 50, "impressions": 5, "link_clicks": 0, "leads": 0, "video_3s": 1},
            {"ad_id": "a3", "adset_id": "s2", "spend_cents": 7, "impressions": 3, "link_clicks": 2, "leads": 2, "video_3s": 0}]
    LEADS = [{"ad_id": "a1", "adset_id": "s1", "qualified": 2}, {"ad_id": None, "adset_id": "s2", "qualified": 1}]

    def test_each_arm_sums_the_rows_of_its_ads_or_ad_sets_once(self):
        arms = [{"ad_ids": ["a1"], "adset_ids": ["s1"]}, {"ad_ids": ["a3", "a1"]}, {"adset_ids": ["s2"]}, {}]
        out = ex.arm_sums(arms, self.ROWS, self.LEADS)
        self.assertEqual([(o["spend_cents"], o["impressions"], o["leads"], o["video_3s"], o["qualified"]) for o in out],
                         [(150, 15, 1, 3, 2), (107, 13, 3, 2, 2), (7, 3, 2, 0, 1), (0, 0, 0, 0, 0)])

    def test_arms_sharing_rows_each_count_them_and_a_lead_without_an_ad_counts_for_its_ad_set(self):
        # Worked by hand from ROWS / LEADS: arm 1 = a1 + a2; arm 2 = every row, both leads (2 + 1);
        # arm 3 = a3 plus s1 (a1, a2), but not the s2 lead, which has no ad and an ad set outside the arm.
        arms = [{"ad_ids": ["a1", "a2"]}, {"adset_ids": ["s1", "s2"]}, {"ad_ids": ["a3"], "adset_ids": ["s1"]}]
        out = ex.arm_sums(arms, self.ROWS, self.LEADS)
        self.assertEqual([(o["spend_cents"], o["impressions"], o["link_clicks"], o["leads"], o["video_3s"], o["qualified"]) for o in out],
                         [(150, 15, 1, 1, 3, 2), (157, 18, 3, 3, 3, 3), (157, 18, 3, 3, 3, 2)])


class InboxKeysTests(unittest.TestCase):
    def test_the_read_lookup_asks_for_exactly_the_items_in_the_feed(self):
        at = lambda h: datetime(2026, 11, 10, h, tzinfo=timezone.utc)  # noqa: E731
        alerts = [{"id": 3, "rule": "fatigue", "level": "warn", "title": "t", "created_at": at(2), "resolved_at": None}]
        leads = [{"id": 8, "full_name": "A", "created_time": at(1), "status": "new"}]
        proposals = [{"id": 5, "created_at": at(3)}]
        self.assertEqual(sorted(inbox.item_keys(alerts, leads, proposals)),
                         sorted(i["key"] for i in inbox.build(alerts, leads, proposals, set())))


if __name__ == "__main__":
    unittest.main()
