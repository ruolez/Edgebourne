"""D1 match Ads Manager: the check window, comparing our day sums with Meta's account totals, restating
older days safely, and the source line every figure carries. Pure."""
import unittest
from datetime import date, datetime, timedelta, timezone

import meta_client
import numbers_check as nc
import refresh_api
import words

OCT = lambda d: date(2026, 10, d)  # noqa: E731
NOV = lambda d: date(2026, 11, d)  # noqa: E731
USD = lambda c: words.money(c, "USD")  # noqa: E731
UTC = timezone.utc


def tot(spend, leads, impressions=0):
    return {"spend_cents": spend, "leads": leads, "impressions": impressions}


class CheckWindowTests(unittest.TestCase):
    def test_last_month_and_this_month_to_yesterday(self):
        self.assertEqual(nc.check_window(NOV(11)), (OCT(1), NOV(10)))

    def test_end_of_month_still_starts_with_last_month(self):
        self.assertEqual(nc.check_window(NOV(30)), (OCT(1), NOV(29)))

    def test_first_of_the_month_checks_the_month_just_ended(self):
        self.assertEqual(nc.check_window(date(2026, 12, 1)), (NOV(1), NOV(30)))

    def test_short_february(self):
        self.assertEqual(nc.check_window(date(2026, 3, 1)), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_at_least_28_days_when_last_month_starts_later(self):
        # yesterday - 27 = Oct 23 starts later than Oct 1, so last month decides.
        self.assertEqual(nc.check_window(NOV(20)), (OCT(1), NOV(19)))

    def test_always_at_least_28_days(self):
        for n in range(400):
            today = date(2026, 1, 1) + timedelta(days=n)
            start, end = nc.check_window(today)
            self.assertEqual(end, today - timedelta(days=1))
            self.assertGreaterEqual((end - start).days + 1, 28, today)


class PartsTests(unittest.TestCase):
    def test_seven_day_parts_and_a_short_last_one(self):
        self.assertEqual(nc.parts(OCT(1), OCT(15)), [(OCT(1), OCT(7)), (OCT(8), OCT(14)), (OCT(15), OCT(15))])

    def test_one_day(self):
        self.assertEqual(nc.parts(OCT(1), OCT(1)), [(OCT(1), OCT(1))])

    def test_parts_cover_every_day_once(self):
        for days in range(1, 50):
            got = nc.parts(OCT(1), OCT(1) + timedelta(days=days - 1))
            covered = [a + timedelta(days=i) for a, b in got for i in range((b - a).days + 1)]
            self.assertEqual(covered, [OCT(1) + timedelta(days=i) for i in range(days)])


class DayTotalsTests(unittest.TestCase):
    def test_meta_account_rows_become_cents_and_leads_like_the_ad_rows(self):
        rows = [{"date_start": "2026-10-14", "spend": "12.34", "impressions": "900",
                 "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": "3"}]}]
        self.assertEqual(nc.day_totals(rows), {OCT(14): tot(1234, 3, 900)})

    def test_no_lead_action_is_zero_leads(self):
        rows = [{"date_start": "2026-10-15", "spend": "0.5", "impressions": "10"}]
        self.assertEqual(nc.day_totals(rows), {OCT(15): tot(50, 0, 10)})


class CompareTests(unittest.TestCase):
    def one(self, meta, here, rows=5, newer=()):
        return nc.compare({OCT(14): meta} if meta is not None else {}, {OCT(14): here} if here is not None else {},
                          {OCT(14): rows}, set(newer), OCT(14), OCT(14))[0]

    def test_a_lead_more_on_meta_is_off(self):
        got = self.one(tot(1234, 3), tot(1234, 2))
        self.assertEqual((got["state"], got["diff_spend_cents"], got["diff_leads"]), ("off", 0, 1))

    def test_spend_within_a_cent_per_row_matches(self):
        self.assertEqual(self.one(tot(1236, 2), tot(1234, 2))["state"], "match")

    def test_spend_past_the_tolerance_is_off(self):
        got = self.one(tot(1300, 2), tot(1234, 2))
        self.assertEqual((got["state"], got["diff_spend_cents"]), ("off", 66))

    def test_meta_says_nothing_was_spent_but_we_have_spend(self):
        got = self.one(tot(0, 0), tot(250, 0))
        self.assertEqual((got["state"], got["diff_spend_cents"]), ("off", -250))

    def test_zero_on_meta_and_nothing_here_matches(self):
        self.assertEqual(self.one(tot(0, 0), None, rows=0)["state"], "match")

    def test_tolerance_is_at_least_one_cent(self):
        self.assertEqual(self.one(tot(1, 0), None, rows=0)["state"], "match")
        self.assertEqual(self.one(tot(2, 0), None, rows=0)["state"], "off")

    def test_a_day_read_again_after_the_check_is_judged_next_time(self):
        self.assertEqual(self.one(tot(1300, 2), tot(1234, 2), newer=[OCT(14)])["state"], "newer")

    def test_a_newer_day_that_agrees_still_matches(self):
        self.assertEqual(self.one(tot(1234, 2), tot(1234, 2), newer=[OCT(14)])["state"], "match")

    def test_no_meta_total_stored_is_unchecked(self):
        self.assertEqual(self.one(None, tot(1234, 2))["state"], "unchecked")

    def test_one_entry_per_day_in_the_window(self):
        got = nc.compare({}, {}, {}, set(), OCT(1), OCT(3))
        self.assertEqual([d["day"] for d in got], [OCT(1), OCT(2), OCT(3)])


def day(state, ds=0, dl=0, d=OCT(14), meta=(0, 0), here=(0, 0)):
    return {"day": d, "state": state, "diff_spend_cents": ds, "diff_leads": dl,
            "meta": {"spend_cents": meta[0], "leads": meta[1]}, "here": {"spend_cents": here[0], "leads": here[1]}}


class SummaryTests(unittest.TestCase):
    def test_off_days_add_up_their_differences_either_way(self):
        s = nc.summary([day("match", d=OCT(13), meta=(500, 1), here=(500, 1)),
                        day("off", 66, 1, d=OCT(14), meta=(1300, 3), here=(1234, 2)),
                        day("off", -20, 0, d=OCT(15), meta=(100, 0), here=(120, 0))])
        self.assertEqual({k: s[k] for k in ("state", "off_days", "spend_off_cents", "leads_off", "meta_spend_cents", "meta_leads",
                                            "start", "end")},
                         {"state": "off", "off_days": ["2026-10-14", "2026-10-15"], "spend_off_cents": 86, "leads_off": 1,
                          "meta_spend_cents": 1900, "meta_leads": 4, "start": "2026-10-13", "end": "2026-10-15"})
        self.assertEqual(s["off"][0], {"day": "2026-10-14", "meta_spend_cents": 1300, "meta_leads": 3, "here_spend_cents": 1234, "here_leads": 2})

    def test_all_match(self):
        self.assertEqual(nc.summary([day("match"), day("newer", d=OCT(15))])["state"], "match")

    def test_counts_the_days_checked_of_the_days_asked(self):
        s = nc.summary([day("unchecked", d=OCT(12)), day("match", d=OCT(13)), day("off", 5, d=OCT(14), meta=(5, 0)), day("newer", d=OCT(15))])
        self.assertEqual((s["days"], s["checked_days"]), (4, 3))

    def test_nothing_checked(self):
        self.assertEqual(nc.summary([day("unchecked")])["state"], "unchecked")
        self.assertEqual(nc.summary([])["state"], "unchecked")


class HeadlineTests(unittest.TestCase):
    def test_differs_by_money_and_leads_on_days(self):
        s = {"state": "off", "off_days": ["2026-10-14", "2026-10-15"], "spend_off_cents": 86, "leads_off": 1}
        self.assertEqual(nc.headline(s, USD), "Differs by $0.86 and 1 lead on 2 days")

    def test_money_only_and_leads_only(self):
        self.assertEqual(nc.headline({"state": "off", "off_days": ["2026-10-14"], "spend_off_cents": 50, "leads_off": 0}, USD),
                         "Differs by $0.50 on 1 day")
        self.assertEqual(nc.headline({"state": "off", "off_days": ["2026-10-14"], "spend_off_cents": 0, "leads_off": 2}, USD),
                         "Differs by 2 leads on 1 day")

    def test_match_and_unchecked(self):
        self.assertEqual(nc.headline({"state": "match"}, USD), "Matches Ads Manager")
        self.assertEqual(nc.headline({"state": "unchecked"}, USD), "Not checked yet")
        self.assertEqual(nc.headline(None, USD), "Not checked yet")


def row(d, ad, spend, leads=0):
    return {"day": d, "ad_id": ad, "spend_cents": spend, "leads": leads}


class RestatePlanTests(unittest.TestCase):
    STORED = {(OCT(14), "a1"), (OCT(14), "a2")}

    def test_a_row_meta_no_longer_returns_is_zeroed_when_the_rest_adds_up_to_meta(self):
        got = nc.restate_plan(self.STORED, [row(OCT(14), "a1", 500)], (OCT(14), OCT(14)), {OCT(14): tot(500, 0)})
        self.assertEqual(got["zero"], [(OCT(14), "a2")])

    def test_nothing_is_zeroed_when_the_fetched_rows_fall_short_of_meta(self):
        got = nc.restate_plan(self.STORED, [row(OCT(14), "a1", 500)], (OCT(14), OCT(14)), {OCT(14): tot(900, 0)})
        self.assertEqual(got["zero"], [])

    def test_an_empty_answer_is_no_proof(self):
        got = nc.restate_plan(self.STORED, [], (OCT(14), OCT(14)), {OCT(14): tot(0, 0)})
        self.assertEqual(got, {"upsert": [], "zero": []})

    def test_leads_must_add_up_too(self):
        got = nc.restate_plan(self.STORED, [row(OCT(14), "a1", 500, 1)], (OCT(14), OCT(14)), {OCT(14): tot(500, 2)})
        self.assertEqual(got["zero"], [])

    def test_a_day_meta_now_says_had_nothing_is_zeroed_when_the_part_answered(self):
        stored = {(OCT(14), "a1"), (OCT(15), "a2")}
        got = nc.restate_plan(stored, [row(OCT(14), "a1", 500)], (OCT(14), OCT(15)), {OCT(14): tot(500, 0), OCT(15): tot(0, 0)})
        self.assertEqual(got["zero"], [(OCT(15), "a2")])

    def test_a_day_without_any_fetched_row_is_left_alone_while_meta_says_it_had_spend(self):
        stored = {(OCT(14), "a1"), (OCT(15), "a2")}
        got = nc.restate_plan(stored, [row(OCT(14), "a1", 500)], (OCT(14), OCT(15)), {OCT(14): tot(500, 0), OCT(15): tot(300, 0)})
        self.assertEqual(got["zero"], [])

    def test_a_day_without_a_meta_total_is_never_zeroed(self):
        got = nc.restate_plan(self.STORED, [row(OCT(15), "a9", 500)], (OCT(14), OCT(15)), {OCT(15): tot(500, 0)})
        self.assertEqual(got["zero"], [])

    def test_iso_days_from_meta_rows_are_understood(self):
        got = nc.restate_plan(self.STORED, [row("2026-10-14", "a1", 500)], (OCT(14), OCT(14)), {OCT(14): tot(500, 0)})
        self.assertEqual(got["zero"], [(OCT(14), "a2")])

    def test_rows_outside_the_part_are_never_zeroed(self):
        stored = {(OCT(14), "a1"), (OCT(20), "a2")}
        got = nc.restate_plan(stored, [row(OCT(14), "a1", 500)], (OCT(14), OCT(14)), {OCT(14): tot(500, 0), OCT(20): tot(0, 0)})
        self.assertEqual(got["zero"], [])


class ChangesTests(unittest.TestCase):
    def test_only_days_that_moved_oldest_first(self):
        before = {OCT(14): tot(1234, 2), OCT(15): tot(500, 1)}
        after = {OCT(14): tot(1200, 3), OCT(15): tot(500, 1)}
        self.assertEqual(nc.changes(before, after), [{"day": "2026-10-14", "spend_cents": -34, "leads": 1}])

    def test_a_day_that_appears_or_goes(self):
        self.assertEqual(nc.changes({OCT(14): tot(100, 0)}, {OCT(13): tot(0, 1)}),
                         [{"day": "2026-10-13", "spend_cents": 0, "leads": 1}, {"day": "2026-10-14", "spend_cents": -100, "leads": 0}])


class ChangedLineTests(unittest.TestCase):
    def test_a_night_that_changed_days(self):
        changed = [{"day": "2026-10-14", "spend_cents": -110, "leads": 2}, {"day": "2026-10-15", "spend_cents": 0, "leads": 0},
                   {"day": "2026-10-16", "spend_cents": 0, "leads": 0}]
        self.assertEqual(nc.changed_line(changed, USD, nightly=True),
                         "Last night Meta changed 3 older days; we updated them: +2 leads, −$1.10.")

    def test_one_day_pulled_by_hand(self):
        self.assertEqual(nc.changed_line([{"day": "2026-10-14", "spend_cents": 50, "leads": 1}], USD, nightly=False),
                         "Meta changed 1 older day; we updated it: +1 lead, +$0.50.")

    def test_nothing_changed(self):
        self.assertIsNone(nc.changed_line([], USD, nightly=True))


class WindowSyncedTests(unittest.TestCase):
    def test_the_oldest_of_the_newest_reads(self):
        got = nc.window_synced({OCT(14): datetime(2026, 11, 11, 9, 42, tzinfo=UTC), OCT(15): datetime(2026, 11, 11, 4, 10, tzinfo=UTC)})
        self.assertEqual(got, datetime(2026, 11, 11, 4, 10, tzinfo=UTC))

    def test_nothing_stored(self):
        self.assertIsNone(nc.window_synced({}))


class FreshnessTests(unittest.TestCase):
    NOW = 1_000_000_000.0

    def test_behind_after_twice_the_automatic_interval(self):
        self.assertTrue(nc.freshness(self.NOW, self.NOW - 40 * 60, 15, self.NOW)["behind"])
        self.assertFalse(nc.freshness(self.NOW, self.NOW - 20 * 60, 15, self.NOW)["behind"])

    def test_at_least_thirty_minutes_and_twice_a_long_interval(self):
        self.assertFalse(nc.freshness(self.NOW, self.NOW - 40 * 60, 60, self.NOW)["behind"])
        self.assertTrue(nc.freshness(self.NOW, self.NOW - 31 * 60, 5, self.NOW)["behind"])

    def test_never_pulled_is_behind(self):
        self.assertTrue(nc.freshness(self.NOW, None, 15, self.NOW)["behind"])

    def test_the_check_is_old_after_36_hours_or_never(self):
        self.assertTrue(nc.freshness(self.NOW, self.NOW, 15, self.NOW - 37 * 3600)["check_old"])
        self.assertFalse(nc.freshness(self.NOW, self.NOW, 15, self.NOW - 35 * 3600)["check_old"])
        self.assertTrue(nc.freshness(self.NOW, self.NOW, 15, None)["check_old"])


class NightTests(unittest.TestCase):
    def test_not_before_four(self):
        self.assertFalse(nc.night_due(datetime(2026, 11, 11, 3, 59), "2026-11-10"))

    def test_from_four_once_a_night(self):
        self.assertTrue(nc.night_due(datetime(2026, 11, 11, 4, 0), "2026-11-10"))
        self.assertFalse(nc.night_due(datetime(2026, 11, 11, 23, 0), "2026-11-11"))
        self.assertTrue(nc.night_due(datetime(2026, 11, 11, 4, 0), None))

    def test_a_failed_night_tries_again_after_half_an_hour_three_times(self):
        local, now = datetime(2026, 11, 11, 5, 0), 10_000.0
        self.assertTrue(nc.night_should_run(local, "2026-11-10", None, now))
        tried = {"day": "2026-11-11", "n": 1, "at": now - 600}
        self.assertFalse(nc.night_should_run(local, "2026-11-10", tried, now))
        self.assertTrue(nc.night_should_run(local, "2026-11-10", {**tried, "at": now - 1800}, now))
        self.assertFalse(nc.night_should_run(local, "2026-11-10", {**tried, "n": 3, "at": now - 7200}, now))
        # Yesterday's failures don't count tonight.
        self.assertTrue(nc.night_should_run(local, "2026-11-10", {"day": "2026-11-10", "n": 3, "at": now}, now))


class OffRunsTests(unittest.TestCase):
    """Judged on the whole check window after the run (window_state), counted only for runs that read it all again."""

    def test_nights_that_end_off_count_in_a_row(self):
        self.assertEqual(nc.off_runs_after(0, "nightly", "off", covers=True), 1)
        self.assertEqual(nc.off_runs_after(1, "nightly", "off", covers=True), 2)

    def test_a_pull_of_a_few_days_that_leaves_other_days_off_keeps_the_count(self):
        self.assertEqual(nc.off_runs_after(1, "pull", "off", covers=False), 1)
        self.assertEqual(nc.off_runs_after(1, "report", "off", covers=False), 1)

    def test_a_pull_of_the_whole_window_that_ends_off_counts(self):
        self.assertEqual(nc.off_runs_after(1, "pull", "off", covers=True), 2)

    def test_a_window_that_matches_clears_whatever_the_run(self):
        for kind, covers in (("nightly", True), ("pull", False), ("check", True)):
            self.assertEqual(nc.off_runs_after(2, kind, "match", covers=covers), 0)

    def test_a_check_never_counts(self):
        self.assertEqual(nc.off_runs_after(2, "check", "off", covers=True), 2)

    def test_unchecked_keeps_the_count(self):
        self.assertEqual(nc.off_runs_after(1, "nightly", "unchecked", covers=True), 1)


class JudgeWindowTests(unittest.TestCase):
    """The account-wide verdict the alert and Settings read: the whole check window after each run, never just the days
    the run read."""
    NIGHT = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)

    def test_a_matching_pull_of_one_day_leaves_the_other_day_off(self):
        later = self.NIGHT + timedelta(hours=3)
        meta = {OCT(14): tot(1300, 3), OCT(20): tot(500, 1)}
        stored = {OCT(14): tot(1234, 2), OCT(20): tot(500, 1)}
        # the hourly sync read Oct 14 again after the night; the pull read Oct 20 and stamped its total
        synced = {OCT(14): later, OCT(20): later}
        fetched = {OCT(14): self.NIGHT, OCT(20): later + timedelta(seconds=1)}
        s = nc.judge(meta, stored, {OCT(14): 3, OCT(20): 2}, synced, fetched, {OCT(14)}, OCT(14), OCT(20))
        self.assertEqual((s["state"], s["off_days"]), ("off", ["2026-10-14"]))

    def test_without_the_night_verdict_a_day_read_again_since_waits_for_the_next_check(self):
        later = self.NIGHT + timedelta(hours=3)
        s = nc.judge({OCT(14): tot(1300, 3)}, {OCT(14): tot(1234, 2)}, {OCT(14): 3}, {OCT(14): later}, {OCT(14): self.NIGHT},
                     set(), OCT(14), OCT(14))
        self.assertEqual((s["state"], s["newer_days"]), ("match", ["2026-10-14"]))


class CoversTests(unittest.TestCase):
    def test_a_run_covers_the_window_only_when_it_read_every_day_of_it(self):
        window = (OCT(1), NOV(10))
        self.assertTrue(nc.covers(OCT(1), NOV(10), window))
        self.assertTrue(nc.covers(date(2026, 9, 30), NOV(10), window))
        self.assertFalse(nc.covers(OCT(2), NOV(10), window))
        self.assertFalse(nc.covers(NOV(5), NOV(5), window))


class NewerDaysTests(unittest.TestCase):
    T = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)

    def test_rows_read_after_meta_total_are_newer(self):
        later = self.T + timedelta(minutes=5)
        self.assertEqual(nc.newer_days({OCT(14): later, OCT(15): self.T}, {OCT(14): self.T, OCT(15): later}), {OCT(14)})

    def test_a_day_without_a_meta_total_is_never_newer(self):
        self.assertEqual(nc.newer_days({OCT(14): self.T}, {}), set())

    def test_a_day_judged_off_stays_off_until_meta_total_is_read_again(self):
        later = self.T + timedelta(hours=1)
        self.assertEqual(nc.newer_days({OCT(14): later, OCT(15): later}, {OCT(14): self.T, OCT(15): self.T}, judged_off={OCT(14)}), {OCT(15)})

    def test_a_restate_that_stamps_the_totals_after_its_rows_judges_its_days_at_once(self):
        # restate reads the totals, rewrites the rows (synced later), then stamps the totals again: a day whose ad rows
        # don't add up to Meta's own total is off, never "updated since the check".
        rows_written = self.T + timedelta(seconds=30)
        restamped = rows_written + timedelta(seconds=1)
        newer = nc.newer_days({OCT(14): rows_written}, {OCT(14): restamped})
        got = nc.compare({OCT(14): tot(1300, 2)}, {OCT(14): tot(1260, 2)}, {OCT(14): 3}, newer, OCT(14), OCT(14))
        self.assertEqual([d["state"] for d in got], ["off"])


class PullRangeTests(unittest.TestCase):
    def test_up_to_yesterday(self):
        self.assertEqual(nc.pull_range(NOV(11), NOV(11), NOV(11)), "Pick days up to yesterday")

    def test_at_most_93_days(self):
        self.assertEqual(nc.pull_range(NOV(10) - timedelta(days=93), NOV(10), NOV(11)), "Pick at most 93 days at a time")
        self.assertEqual(nc.pull_range(NOV(10) - timedelta(days=92), NOV(10), NOV(11)), (NOV(10) - timedelta(days=92), NOV(10)))

    def test_a_week(self):
        self.assertEqual(nc.pull_range(OCT(14), OCT(20), NOV(11)), (OCT(14), OCT(20)))

    def test_older_than_meta_keeps(self):
        self.assertEqual(nc.pull_range(date(2023, 9, 1), date(2023, 9, 7), NOV(11)), "Meta only keeps the last 37 months")

    def test_start_after_end(self):
        self.assertEqual(nc.pull_range(OCT(20), OCT(14), NOV(11)), "The first day comes after the last")


class PairTests(unittest.TestCase):
    def test_differ_or_not(self):
        self.assertEqual(nc.pair(12, 11), {"meta": 12, "received": 11, "differ": True})
        self.assertEqual(nc.pair(3, 3), {"meta": 3, "received": 3, "differ": False})


class SourceInfoTests(unittest.TestCase):
    OFF = {"state": "off", "off_days": ["2026-10-14", "2026-10-15"], "spend_off_cents": 86, "leads_off": 1, "checked_days": 30, "days": 30}
    FRESH = {"behind": False, "check_old": False}

    def info(self, admin, check=OFF, end=NOV(10)):
        return nc.source_info(synced=datetime(2026, 11, 11, 12, 10, tzinfo=UTC), end=end, today=NOV(11),
                              check=check, checked_at=datetime(2026, 11, 11, 12, 10, tzinfo=UTC), fresh=self.FRESH,
                              scope_note=False, admin=admin)

    def test_teammates_and_clients_get_the_state_without_amounts(self):
        got = self.info(False)["meta"]["check"]
        self.assertEqual(got, {"state": "off", "checked_at": "2026-11-11T12:10:00+00:00", "off_days": 2, "old": False,
                               "checked_days": 30, "days": 30, "spend_off_cents": None, "leads_off": None})

    def test_admins_get_the_amounts(self):
        got = self.info(True)["meta"]["check"]
        self.assertEqual((got["spend_off_cents"], got["leads_off"]), (86, 1))

    def test_the_rest_of_the_payload(self):
        got = self.info(True)["meta"]
        self.assertEqual({k: got[k] for k in ("synced_at", "complete_to", "partial_today", "behind")},
                         {"synced_at": "2026-11-11T12:10:00+00:00", "complete_to": "2026-11-10", "partial_today": False, "behind": False})

    def test_a_window_that_runs_into_today_is_partial(self):
        self.assertTrue(self.info(True, end=NOV(11))["meta"]["partial_today"])

    def test_no_check_yet(self):
        self.assertIsNone(self.info(True, check=None)["meta"]["check"])

    def test_a_window_reaching_past_the_checked_days_says_how_many_were_checked(self):
        got = self.info(False, check={"state": "match", "off_days": [], "checked_days": 30, "days": 90})["meta"]["check"]
        self.assertEqual((got["state"], got["checked_days"], got["days"]), ("match", 30, 90))


class StampTests(unittest.TestCase):
    AT = datetime(2026, 11, 11, 12, 10, tzinfo=UTC)
    OFF = {"state": "off", "off_days": ["2026-10-14"], "spend_off_cents": 50, "leads_off": 1,
           "off": [{"day": "2026-10-14", "meta_spend_cents": 1284, "meta_leads": 3, "here_spend_cents": 1234, "here_leads": 2}]}

    def test_a_match_is_said_with_when(self):
        got = nc.report_stamp({"state": "match"}, self.AT, UTC, USD, admin=False)
        self.assertEqual(got, {"state": "match", "text": "Checked against Meta's own totals on Wed, Nov 11, 12:10 PM: they match.",
                               "warning": None, "off_days": []})

    def test_off_for_clients_says_it_is_being_checked_without_amounts(self):
        got = nc.report_stamp(self.OFF, self.AT, UTC, USD, admin=False)
        self.assertEqual((got["text"], got["warning"], got["off_days"]),
                         ("Checked against Meta's own totals on Wed, Nov 11, 12:10 PM: a few days are being checked again.", None, []))

    def test_off_for_admins_warns_with_the_days(self):
        got = nc.report_stamp(self.OFF, self.AT, UTC, USD, admin=True)
        self.assertEqual((got["warning"], got["off_days"]),
                         ("Meta's totals differ for Oct 14 ($0.50, 1 lead). Pull these days again before sharing.", ["2026-10-14"]))

    def test_never_checked(self):
        self.assertEqual(nc.report_stamp(None, None, UTC, USD, admin=True)["text"], "Not checked against Meta's own totals yet.")

    def test_a_period_only_partly_checked_says_how_many_days(self):
        got = nc.report_stamp({"state": "match", "checked_days": 12, "days": 31}, self.AT, UTC, USD, admin=False)
        self.assertEqual(got["text"], "Checked 12 of 31 days against Meta's own totals on Wed, Nov 11, 12:10 PM: they match.")

    def test_every_day_checked_says_they_match_plainly(self):
        got = nc.report_stamp({"state": "match", "checked_days": 7, "days": 7}, self.AT, UTC, USD, admin=False)
        self.assertEqual(got["text"], "Checked against Meta's own totals on Wed, Nov 11, 12:10 PM: they match.")


class AlertWordsTests(unittest.TestCase):
    def test_up_to_three_days_named_then_how_many_more(self):
        self.assertEqual(nc.day_list(["2026-10-14"]), "Oct 14")
        self.assertEqual(nc.day_list(["2026-10-14", "2026-10-20"]), "Oct 14 and Oct 20")
        self.assertEqual(nc.day_list(["2026-10-14", "2026-10-15", "2026-10-16"]), "Oct 14, Oct 15 and Oct 16")
        self.assertEqual(nc.day_list(["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"]),
                         "Oct 14, Oct 15, Oct 16 and 2 more")

    def test_one_day_in_words(self):
        off = {"day": "2026-10-14", "meta_spend_cents": 1234, "meta_leads": 3, "here_spend_cents": 1204, "here_leads": 2}
        self.assertEqual(nc.day_line(off, USD), "Ads Manager says $12.34 and 3 leads for Oct 14; we have $12.04 and 2.")


class PullMessageTests(unittest.TestCase):
    def test_matches_now(self):
        self.assertEqual(nc.pull_message(7, {"state": "match"}, USD), "Pulled 7 days again. Matches Ads Manager now.")

    def test_still_off(self):
        s = {"state": "off", "off_days": ["2026-10-14"], "spend_off_cents": 50, "leads_off": 0}
        self.assertEqual(nc.pull_message(1, s, USD),
                         "Pulled 1 day again. Still off by $0.50 on Oct 14: Meta's totals sometimes settle a day later.")


class RunPartsTests(unittest.TestCase):
    PARTS = [(OCT(1), OCT(7)), (OCT(8), OCT(14)), (OCT(15), OCT(21))]

    def test_a_rate_limit_stops_the_run_and_keeps_the_finished_parts(self):
        asked, written = [], []

        def fetch(part):
            asked.append(part)
            if len(asked) == 3:
                raise meta_client.MetaError("slow down", code=17)
            return [part]
        got = nc.run_parts(self.PARTS, fetch, lambda part, rows: rows, written.append)
        self.assertEqual(got, {"parts_done": 2, "parts_total": 3, "ok": False,
                               "error": "Stopped after 2 of 3 parts: Meta asked us to slow down."})
        self.assertEqual((asked, written), (self.PARTS, [[self.PARTS[0]], [self.PARTS[1]]]))

    def test_our_own_cooldown_stops_too(self):
        def fetch(part):
            raise meta_client.MetaError("wait", code="cooldown")
        got = nc.run_parts(self.PARTS, fetch, lambda p, r: r, lambda p: None)
        self.assertEqual(got["error"], "Stopped after 0 of 3 parts: Meta asked us to slow down.")

    def test_too_much_data_is_read_one_day_at_a_time_once(self):
        asked = []

        def fetch(part):
            asked.append(part)
            if part == self.PARTS[0]:
                raise meta_client.MetaError("Please reduce the amount of data you're asking for, then retry your request", code=1)
            return []
        got = nc.run_parts(self.PARTS[:1], fetch, lambda p, r: r, lambda p: None)
        self.assertEqual(got, {"parts_done": 1, "parts_total": 1, "ok": True, "error": None})
        self.assertEqual(asked, [self.PARTS[0]] + [(OCT(d), OCT(d)) for d in range(1, 8)])

    def test_any_other_meta_error_stops_with_its_words(self):
        def fetch(part):
            raise meta_client.MetaError("The System User doesn't have permission for this: x", code=200)
        got = nc.run_parts(self.PARTS, fetch, lambda p, r: r, lambda p: None)
        self.assertEqual(got["error"], "Stopped after 0 of 3 parts: The System User doesn't have permission for this: x")

    def test_all_parts(self):
        got = nc.run_parts(self.PARTS, lambda p: [], lambda p, r: r, lambda p: None)
        self.assertEqual(got, {"parts_done": 3, "parts_total": 3, "ok": True, "error": None})

    def test_progress_is_told_after_each_finished_part(self):
        seen = []

        def fetch(part):
            if part == self.PARTS[2]:
                raise meta_client.MetaError("slow down", code=17)
            return []
        nc.run_parts(self.PARTS, fetch, lambda p, r: r, lambda p: None, progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen, [(1, 3), (2, 3)])


class LockTests(unittest.TestCase):
    def test_one_pull_lock_per_account(self):
        self.assertNotEqual(refresh_api.pull_lock(1), refresh_api.pull_lock(2))
        self.assertEqual(refresh_api.pull_lock(1), refresh_api.LOCK_KEY * 1000 + 1)


if __name__ == "__main__":
    unittest.main()
