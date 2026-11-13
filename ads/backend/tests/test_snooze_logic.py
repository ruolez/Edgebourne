import random
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import snooze

LA = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
SNOOZED_AT = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)  # Nov 10, 9 AM in Los Angeles
UNTIL = datetime(2026, 11, 12, 16, 0, tzinfo=UTC)
SPEND_CAP_82 = 82.0
CPL_80 = 8000


def days_snooze(**kw):
    return {"id": 7, "rule": "cpl_high", "mode": "days", "until": UNTIL, "baseline": CPL_80, "baseline_level": "warn",
            "created_at": SNOOZED_AT, **kw}


def alert(**kw):
    return {"rule": "cpl_high", "kind": "condition", "level": "warn", "resolved_at": None, "measure": CPL_80, **kw}


class WorseTests(unittest.TestCase):
    def test_spending_limit_bands(self):
        cases = [(82, 94, "warn"), (82, 96, "warn"), (96, 99, "warn"), (96, 100, "bad")]
        self.assertEqual([snooze.worse("spend_cap", b, m, "warn", lvl) for b, m, lvl in cases], [False, True, False, True])

    def test_cost_per_lead_needs_a_quarter_more(self):
        self.assertEqual([snooze.worse("cpl_high", CPL_80, m, "warn", "warn") for m in (9900, 10000)], [False, True])

    def test_dry_streak_must_double(self):
        self.assertEqual([snooze.worse("no_leads", 3, m, "bad", "bad") for m in (5, 6)], [False, True])

    def test_fatigue_needs_one_more_view_a_week(self):
        self.assertEqual([snooze.worse("fatigue", 3.4, m, "warn", "warn") for m in (4.3, 4.4)], [False, True])

    def test_a_level_going_up_is_worse_without_any_figure(self):
        self.assertEqual(snooze.worse("events_quiet", None, None, "warn", "bad"), True)

    def test_an_unknown_figure_judges_on_level_only(self):
        self.assertEqual([snooze.worse("cpl_high", None, 12000, "warn", "warn"), snooze.worse("cpl_high", CPL_80, None, "warn", "warn")],
                         [False, False])

    def test_rejected_outright_after_issues_is_worse(self):
        self.assertEqual([snooze.worse("ad_rejected", 1, 2, "bad", "bad"), snooze.worse("ad_rejected", 2, 1, "bad", "bad")], [True, False])

    def test_days_left_on_the_limit_wake_at_one(self):
        self.assertEqual([snooze.worse("cap_soon", 3, m, "warn", "warn") for m in (2, 1)], [False, True])

    def test_qualified_share_must_drop_ten_points(self):
        self.assertEqual([snooze.worse("qualified_low", 18, m, "warn", "warn") for m in (9, 8)], [False, True])

    def test_a_qualified_share_under_ten_points_wakes_only_at_none(self):
        self.assertEqual([snooze.worse("qualified_low", 5, m, "warn", "warn") for m in (1, 0)]
                         + [snooze.worse("qualified_low", 0, 0, "warn", "warn")], [False, True, False])

    def test_junk_share_must_rise_fifteen_points(self):
        self.assertEqual([snooze.worse("junk_high", 33.3, m, "warn", "warn") for m in (48.2, 48.3)], [False, True])

    def test_junk_near_the_top_wakes_when_every_lead_is_junk(self):
        self.assertEqual([snooze.worse("junk_high", 90, m, "warn", "warn") for m in (99, 100)]
                         + [snooze.worse("junk_high", 100, 100, "warn", "warn")], [False, True, False])

    def test_steps_of_the_other_rules(self):
        cases = [("no_delivery", 30, 77, 78), ("week_overspend", 14000, 17499, 17500), ("pace_over", 20, 34, 35), ("stale_data", 4, 27.9, 28)]
        self.assertEqual([(snooze.worse(r, b, below, "warn", "warn"), snooze.worse(r, b, at, "warn", "warn")) for r, b, below, at in cases],
                         [(False, True)] * 4)


class WorseProperties(unittest.TestCase):
    def test_an_unchanged_figure_never_wakes_a_snooze(self):
        rng = random.Random(20261112)
        for rule in snooze.WORSE:
            for _ in range(200):
                b = round(rng.uniform(0, 50000), rng.choice((0, 1, 2)))
                level = rng.choice(("warn", "bad", "info"))
                self.assertFalse(snooze.worse(rule, b, b, level, level), (rule, b, level))

    def test_a_multiplied_step_never_wakes_from_zero(self):
        for rule, (how, _) in snooze.WORSE.items():
            if how == "times":
                self.assertFalse(snooze.worse(rule, 0, 0, "warn", "warn"), rule)
                self.assertTrue(snooze.worse(rule, 0, 1, "warn", "warn"), rule)


class DecideTests(unittest.TestCase):
    def test_quiet_until_the_promised_time(self):
        self.assertEqual([snooze.decide(days_snooze(), alert(), t) for t in (UNTIL - timedelta(minutes=1), UNTIL)],
                         ["quiet", "wake_expired"])

    def test_worse_beats_expired(self):
        self.assertEqual(snooze.decide(days_snooze(), alert(measure=10000), UNTIL + timedelta(hours=1)), "wake_worse")

    def test_until_worse_never_expires(self):
        s = days_snooze(mode="worse", until=None)
        self.assertEqual(snooze.decide(s, alert(), UNTIL + timedelta(days=30)), "quiet")


class UntilTests(unittest.TestCase):
    def test_eight_in_the_morning_three_dates_later(self):
        self.assertEqual(snooze.until_for(datetime(2026, 11, 10, 23, 30, tzinfo=LA), 3), datetime(2026, 11, 13, 8, 0, tzinfo=LA))

    def test_across_the_end_of_daylight_saving(self):
        got = snooze.until_for(datetime(2026, 10, 31, 12, 0, tzinfo=LA), 3)
        self.assertEqual((got.isoformat(), got.utcoffset()), ("2026-11-03T08:00:00-08:00", timedelta(hours=-8)))


class ChoicesTests(unittest.TestCase):
    TOMORROW = [{"mode": "days", "days": 1, "label": "Remind me tomorrow"}]
    BOTH = [{"mode": "days", "days": 3, "label": "In 3 days"}, {"mode": "worse", "days": None, "label": "Only if it gets worse"}]

    def test_events_info_and_cleared_alerts_offer_nothing(self):
        cases = [alert(rule="learning_limited", kind="event"), alert(rule="day_overspend", level="info"),
                 alert(resolved_at=SNOOZED_AT), alert(rule="report_review", kind="event"), alert(rule="ad_approved", level="ok")]
        self.assertEqual([snooze.choices(a) for a in cases], [[]] * 5)

    def test_tracking_and_a_red_money_alert_wait_a_day_at_most(self):
        cases = [alert(rule="tracking", level="bad"), alert(rule="spend_cap", level="bad"), alert(rule="no_leads", level="bad")]
        self.assertEqual([snooze.choices(a) for a in cases], [self.TOMORROW] * 3)

    def test_the_rest_offer_three_days_or_until_worse(self):
        cases = [alert(), alert(rule="spend_cap"), alert(rule="ad_rejected", level="bad")]
        self.assertEqual([snooze.choices(a) for a in cases], [self.BOTH] * 3)

    def test_lead_quality_alerts_offer_three_days_or_until_worse(self):
        cases = [alert(rule="qualified_low", measure=16.7), alert(rule="junk_high", measure=33.3)]
        self.assertEqual([snooze.choices(a) for a in cases], [self.BOTH] * 2)


class HintTests(unittest.TestCase):
    def test_spending_limit(self):
        self.assertEqual([snooze.worse_hint("spend_cap", m) for m in (SPEND_CAP_82, 96)],
                         ["You'll hear again at 95% of the limit.", "You'll hear again when the limit is reached."])

    def test_cost_per_lead_in_dollars(self):
        self.assertEqual(snooze.worse_hint("cpl_high", CPL_80), "You'll hear again if a lead costs $100 or more.")

    def test_days_without_a_lead(self):
        self.assertEqual(snooze.worse_hint("no_leads", 3), "You'll hear again after 6 days without a lead.")

    def test_qualified_share(self):
        self.assertEqual([snooze.worse_hint("qualified_low", m) for m in (17, 16.7, 5, 0)],
                         ["You'll hear again if it drops to 7%.", "You'll hear again if it drops to 6.7%.",
                          "You'll hear again if none of them qualify.", "It ends by itself when leads qualify again."])

    def test_junk_share(self):
        self.assertEqual([snooze.worse_hint("junk_high", m) for m in (33, 33.3, 90)],
                         ["You'll hear again if junk reaches 48%.", "You'll hear again if junk reaches 48.3%.",
                          "You'll hear again if every lead looks like junk."])

    def test_a_qualified_share_at_none_is_not_told_it_ends_twice(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=LA)
        worse = snooze.offer(alert(rule="qualified_low", measure=0), now)[1]
        self.assertEqual(worse["hint"], "No messages while it stays like this. It ends by itself when leads qualify again.")

    def test_an_alert_raised_before_figures_were_kept(self):
        self.assertEqual(snooze.worse_hint("cpl_high", None), "You'll hear again if it turns red.")

    def test_choice_lines_name_the_date_and_say_what_ends_it(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=LA)
        got = snooze.offer(alert(rule="spend_cap", measure=SPEND_CAP_82), now)
        self.assertEqual([(c["label"], c["hint"]) for c in got],
                         [("In 3 days", "Stays in the Inbox without messages until Sat, Nov 14. Comes back sooner if it gets worse."),
                          ("Only if it gets worse", "No messages while it stays like this. You'll hear again at 95% of the limit. "
                                                    "It ends by itself when this clears up.")])

    def test_a_hint_that_already_says_it_ends_is_not_said_twice(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=LA)
        worse = snooze.offer(alert(rule="ad_rejected", level="bad", measure=2), now)[1]
        self.assertEqual(worse["hint"], "No messages while it stays like this. It ends by itself when the ad is approved or switched off.")

    def test_tracking_says_why_it_only_waits_a_day(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=LA)
        self.assertEqual(snooze.offer(alert(rule="tracking", level="bad", measure=4), now)[0]["hint"],
                         "Leads may be getting lost, so this can only wait a day.")


class WordsTests(unittest.TestCase):
    def test_wake_lines(self):
        s = days_snooze(rule="spend_cap", baseline=SPEND_CAP_82)
        self.assertEqual([snooze.woke_line(s, "wake_worse", LA), snooze.woke_line(s, "wake_expired", LA)],
                         ["You snoozed this at 82% on Nov 10.", "You asked to be reminded on Nov 10."])

    def test_wake_lines_of_the_lead_quality_alerts(self):
        self.assertEqual([snooze.woke_line(days_snooze(rule="qualified_low", baseline=16.7), "wake_worse", LA),
                          snooze.woke_line(days_snooze(rule="junk_high", baseline=33.3), "wake_worse", LA)],
                         ["You snoozed this at 17% qualified on Nov 10.", "You snoozed this at 33% junk on Nov 10."])
        self.assertEqual(snooze.woke_line(days_snooze(rule="qualified_low", baseline=12.5), "wake_worse", LA),
                         "You snoozed this at 13% qualified on Nov 10.")

    def test_chip_words(self):
        self.assertEqual([snooze.snooze_words(days_snooze(), LA), snooze.snooze_words(days_snooze(mode="worse", until=None), LA)],
                         ["Snoozed until Thu, Nov 12", "Snoozed until it gets worse"])


class ApplyTests(unittest.TestCase):
    def test_a_quiet_alert_is_stored_without_a_message(self):
        a = dict(alert(), key="cpl_high:c1:2026-11-11", title="Leads cost $90.00 each", lines=["l"])
        self.assertEqual(snooze.apply(a, days_snooze(), "quiet", LA), {**a, "quiet": True})

    def test_a_wake_up_names_why_and_gets_a_key_of_its_own(self):
        a = dict(alert(measure=10000), key="cpl_high:c1:2026-11-11", title="Leads cost $100 each", lines=["Last 7 days: …"])
        got = snooze.apply(a, days_snooze(), "wake_worse", LA)
        self.assertEqual((got["title"], got["lines"], got["wake_key"], got.get("quiet")),
                         ("Worse: Leads cost $100 each", ["You snoozed this at $80 on Nov 10.", "Last 7 days: …"],
                          "cpl_high:c1:2026-11-11:w7", False))

    def test_back_as_promised(self):
        a = dict(alert(), key="k", title="“N3” looks tired", lines=[])
        self.assertEqual(snooze.apply(a, days_snooze(rule="fatigue"), "wake_expired", LA)["title"], "Back as promised: “N3” looks tired")


class SweepTests(unittest.TestCase):
    LIVE = [{"id": 1, "rule": "cpl_high", "entity_id": "c1", "mode": "worse", "until": None},
            {"id": 2, "rule": "fatigue", "entity_id": "a1", "mode": "days", "until": UNTIL},
            {"id": 3, "rule": "spend_cap", "entity_id": "account", "mode": "days", "until": UNTIL + timedelta(days=1)}]

    def test_gone_conditions_end_their_snoozes(self):
        got = snooze.sweep(self.LIVE, {("spend_cap", "account")}, UNTIL + timedelta(hours=1), stale=False)
        self.assertEqual(got, [(1, "cleared"), (2, "expired")])

    def test_stale_meta_data_keeps_every_snooze(self):
        self.assertEqual(snooze.sweep(self.LIVE, set(), UNTIL, stale=True), [])

    def test_a_rule_that_could_not_be_judged_keeps_its_snooze(self):
        self.assertEqual(snooze.sweep(self.LIVE, set(), UNTIL - timedelta(hours=1), stale=False, unjudged={"fatigue"}),
                         [(1, "cleared"), (3, "cleared")])


if __name__ == "__main__":
    unittest.main()


class NumbersOffSnoozeTests(unittest.TestCase):
    """D1: days that differ from Ads Manager snooze until 3 more days differ."""

    def test_three_more_days_wake_it(self):
        self.assertEqual([snooze.worse("numbers_off", 2, m, "warn", "warn") for m in (2, 4, 5)], [False, False, True])

    def test_hint_and_figure(self):
        self.assertEqual((snooze.worse_hint("numbers_off", 2), snooze.measure_words("numbers_off", 2), snooze.measure_words("numbers_off", 1)),
                         ("You'll hear again if 3 more days differ.", "2 days that differ", "1 day that differs"))
