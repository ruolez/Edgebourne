import json
import threading
import time
import unittest
from contextlib import nullcontext
from datetime import date
from unittest import mock

import account_ctx
import insights
import meta_client
import status_history as sh

DAY = date(2026, 11, 9)


def error(code, status=400, raw="boom"):
    return meta_client.MetaError("boom", code=code, status=status, raw=raw)


class TransientTests(unittest.TestCase):
    """A field-set fallback is only for Meta refusing a field; a request that got no real answer is re-raised."""

    def test_no_real_answer_is_transient(self):
        self.assertEqual([meta_client.transient(e) for e in (
            error("network", None), error("cooldown", None), error(17), error(80004), error(2, 500), error(1, 500), error(None, 503))],
            [True] * 7)

    def test_refusals_are_not_transient(self):
        self.assertEqual([meta_client.transient(e) for e in (
            error(100, raw="(#100) Tried accessing nonexisting field (issues_info) on node type (AdSet)"),
            error(100, raw="Unsupported get request. Object with ID '1' does not exist"), error(190), error(10))],
            [False] * 4)


class ListingTests(unittest.TestCase):
    def read(self, fail_with):
        calls = []

        def paged(path, fields, limit):
            calls.append(fields)
            if fields == "full" and fail_with:
                raise fail_with
            return iter([{"id": "1"}])
        with mock.patch.object(meta_client, "paged", paged):
            import sync
            try:
                return sync.listing("act_1/adsets", "full", "plain"), calls
            except meta_client.MetaError as exc:
                return exc.code, calls

    def test_a_timeout_is_raised_not_retried_with_fewer_fields(self):
        self.assertEqual(self.read(error("network", None)), ("network", ["full"]))

    def test_a_refused_field_falls_back_and_marks_the_rows_partial(self):
        self.assertEqual(self.read(error(100, raw="Tried accessing nonexisting field (issues_info)")),
                         ([{"id": "1", "_partial": True}], ["full", "plain"]))

    def test_the_full_set_is_not_partial(self):
        self.assertEqual(self.read(None), ([{"id": "1"}], ["full"]))


class FetchManyTests(unittest.TestCase):
    """Webhook refetches: a gone id is skipped, anything else that went wrong keeps the events pending."""

    def fetch(self, answers):
        def get(path, ids=None, fields=None):
            key = ids or path
            ans = answers.get(key, answers.get("*"))
            if isinstance(ans, Exception):
                raise ans
            return ans
        with mock.patch.object(meta_client, "get", get):
            return insights._fetch_many(["a", "b"], "full", "plain")

    def test_a_deleted_id_is_skipped_and_the_rest_read_one_by_one(self):
        gone = error(100, raw="Object with ID 'b' does not exist")
        self.assertEqual(self.fetch({"a,b": gone, "a": {"id": "a"}, "b": gone}), {"a": {"id": "a"}})

    def test_a_rate_limit_on_one_id_is_raised(self):
        with self.assertRaises(meta_client.MetaError):
            self.fetch({"a,b": error(100, raw="Object with ID 'b' does not exist"), "a": {"id": "a"}, "b": error("cooldown", None)})

    def test_a_timeout_on_the_batch_is_raised(self):
        with self.assertRaises(meta_client.MetaError):
            self.fetch({"*": error("network", None)})

    def test_a_refused_field_on_the_one_by_one_read_falls_back_and_marks_that_object_partial(self):
        gone = error(100, raw="Object with ID 'b' does not exist")
        refused = error(100, raw="(#100) Tried accessing nonexisting field (issues_info) on node type (Ad)")

        def get(path, ids=None, fields=None):
            if ids or path == "b":
                raise gone
            if fields == "full":
                raise refused
            return {"id": path, "status": "ACTIVE"}
        with mock.patch.object(meta_client, "get", get):
            self.assertEqual(insights._fetch_many(["a", "b"], "full", "plain"),
                             {"a": {"id": "a", "status": "ACTIVE", "_partial": True}})


class MissingVerdictTests(unittest.TestCase):
    """Meta's listings leave archived and deleted objects out; each missing one is read by id first."""

    def test_archived_stays_archived_deleted_or_gone_is_deleted_and_alive_is_left_alone(self):
        found = {"a1": {"id": "a1", "effective_status": "ARCHIVED"}, "a2": {"id": "a2", "effective_status": "DELETED"},
                 "a4": {"id": "a4", "effective_status": "PAUSED"}}
        self.assertEqual(sh.missing_verdicts(["a1", "a2", "a3", "a4"], found),
                         {"a1": "ARCHIVED", "a2": "DELETED", "a3": "DELETED"})


class TodaySnapshotTests(unittest.TestCase):
    """Today's spend is only today's: a snapshot from another day (or without one) is ignored."""

    def test_only_a_snapshot_of_this_day_counts(self):
        mine = {"at": 1.0, "day": DAY.isoformat(), "campaigns": {"c1": {"spend_cents": 1800, "leads": 1}}}
        old = {**mine, "day": "2026-11-08"}
        legacy = {"at": 1.0, "campaigns": {"c1": {"spend_cents": 1800, "leads": 1}}}
        self.assertEqual([insights.today_for(json.dumps(s) if s else None, DAY) for s in (mine, old, legacy, None)],
                         [mine, None, None, None])


class BackfillWindowTests(unittest.TestCase):
    """Results before the first synced day are read once, in chunks, back to when the oldest thing started."""

    def test_chunks_from_the_oldest_start_to_the_day_before_the_first_synced_day(self):
        self.assertEqual(insights.backfill_windows(date(2026, 6, 1), date(2026, 10, 11), date(2026, 11, 9), chunk=60),
                         [(date(2026, 6, 1), date(2026, 7, 30)), (date(2026, 7, 31), date(2026, 9, 28)),
                          (date(2026, 9, 29), date(2026, 10, 10))])

    def test_nothing_older_than_the_first_synced_day_means_nothing_to_read(self):
        self.assertEqual(insights.backfill_windows(date(2026, 10, 20), date(2026, 10, 11), date(2026, 11, 9)), [])

    def test_never_further_back_than_meta_keeps_results(self):
        windows = insights.backfill_windows(date(2020, 1, 1), date(2026, 10, 11), date(2026, 11, 9))
        self.assertEqual((windows[0][0], windows[-1][1]), (date(2026, 11, 9) - insights.BACKFILL_LIMIT, date(2026, 10, 10)))

    def test_no_synced_day_yet_reads_up_to_yesterday(self):
        self.assertEqual(insights.backfill_windows(date(2026, 11, 1), None, date(2026, 11, 9)),
                         [(date(2026, 11, 1), date(2026, 11, 8))])


class ResyncLockTests(unittest.TestCase):
    """Another process (a second gunicorn worker) already re-reading this account: wait and try again, never overlap."""

    def test_a_held_lock_postpones_the_resync_instead_of_running_alongside(self):
        import ads_api
        from contextlib import contextmanager
        held, runs, done = [True], [], threading.Event()

        @contextmanager
        def try_lock(name):
            free = not held[0]
            held[0] = False  # the other process finishes after the first attempt
            yield free

        def sync_structure():
            runs.append(time.time())
            done.set()
        with mock.patch.object(ads_api, "RESYNC_DELAY", 0.1), mock.patch.object(insights, "sync_structure", sync_structure), \
                mock.patch.object(ads_api.db, "reusing", nullcontext), mock.patch.object(ads_api.db, "try_lock", try_lock):
            with account_ctx.use(8):
                ads_api.resync_later()
            done.wait(3)
            time.sleep(0.3)
        self.assertEqual((len(runs), held[0]), (1, False))


class ResyncTests(unittest.TestCase):
    """After a console write the structure is re-read once per burst of writes, in its own context."""

    def test_a_burst_of_writes_gives_one_resync_outside_the_request(self):
        import ads_api
        import flask
        seen, done = [], threading.Event()

        def sync_structure():
            seen.append((flask.has_app_context(), account_ctx.current()))
            done.set()
        with mock.patch.object(ads_api, "RESYNC_DELAY", 0.2), mock.patch.object(insights, "sync_structure", sync_structure), \
                mock.patch.object(ads_api.db, "reusing", nullcontext):
            with flask.Flask("t").app_context(), account_ctx.use(7):
                for _ in range(3):
                    ads_api.resync_later()
            done.wait(3)
            time.sleep(0.4)
        self.assertEqual(seen, [(False, 7)])


if __name__ == "__main__":
    unittest.main()
