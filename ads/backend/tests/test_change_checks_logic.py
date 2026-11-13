"""D3 "Did it work?": before/after windows, the verdict, Claude's expectation and Put it back. Pure."""
import unittest
from datetime import date, timedelta

import change_checks as cc
import words

NOV = lambda d: date(2026, 11, d)  # noqa: E731
WHOLE = lambda c: words.money(c, "USD", whole=True)  # noqa: E731
CENTS = lambda c: f"${c / 100:,.2f}"  # noqa: E731


def arm(spend, leads, qualified=0):
    return {"spend_cents": spend, "leads": leads, "qualified": qualified, "impressions": 0}


class WindowsTests(unittest.TestCase):
    def test_equal_complete_days_either_side_of_the_change_day(self):
        got = cc.windows(NOV(9), NOV(9), NOV(20), 7)
        self.assertEqual(got, {"before": (NOV(2), NOV(8)), "after": (NOV(10), NOV(16)), "days": 7, "complete": True,
                               "ready_on": NOV(17), "cut_by": None})

    def test_not_complete_until_the_after_window_has_ended_by_yesterday(self):
        got = cc.windows(NOV(9), NOV(9), NOV(16), 7)
        self.assertEqual((got["complete"], got["ready_on"]), (False, NOV(17)))

    def test_three_days_are_complete_the_day_after_they_end(self):
        got = cc.windows(NOV(9), NOV(9), NOV(13), 3)
        self.assertEqual((got["after"], got["complete"]), ((NOV(10), NOV(12)), True))

    def test_a_later_change_cuts_both_sides_to_the_shorter_length(self):
        got = cc.windows(NOV(9), NOV(9), NOV(20), 7, next_change=NOV(13))
        self.assertEqual((got["before"], got["after"], got["days"], got["cut_by"]), ((NOV(6), NOV(8)), (NOV(10), NOV(12)), 3, NOV(13)))

    def test_a_change_two_days_later_leaves_one_day(self):
        self.assertEqual(cc.windows(NOV(9), NOV(9), NOV(20), 3, next_change=NOV(11))["days"], 1)

    def test_a_change_the_same_day_leaves_nothing_to_compare(self):
        got = cc.windows(NOV(9), NOV(9), NOV(20), 7, next_change=NOV(9))
        self.assertEqual((got["before"], got["after"], got["days"], got["complete"]), (None, None, 0, True))

    def test_the_days_meta_reviewed_a_new_version_count_for_neither_side(self):
        got = cc.windows(NOV(9), NOV(10), NOV(20), 3)
        self.assertEqual((got["before"], got["after"]), ((NOV(6), NOV(8)), (NOV(11), NOV(13))))

    def test_an_earlier_change_cuts_the_before_window(self):
        got = cc.windows(NOV(9), NOV(9), NOV(20), 7, prev_change=NOV(5))
        self.assertEqual((got["before"], got["after"], got["days"]), ((NOV(6), NOV(8)), (NOV(10), NOV(12)), 3))

    def test_property_both_sides_always_have_the_same_length_and_never_touch_the_change_days(self):
        for horizon in cc.HORIZONS:
            for review in range(0, 3):
                for gap in (None, 0, 1, 2, 5, 20):
                    for back in (None, 1, 3, 9, 30):
                        first, last = NOV(9), NOV(9) + timedelta(days=review)
                        got = cc.windows(first, last, NOV(30), horizon, prev_change=back and first - timedelta(days=back),
                                         next_change=None if gap is None else last + timedelta(days=gap))
                        if not got["days"]:
                            continue
                        (bs, be), (a_s, ae) = got["before"], got["after"]
                        self.assertEqual(((be - bs).days + 1, (ae - a_s).days + 1), (got["days"], got["days"]))
                        self.assertTrue(be < first and a_s > last and got["days"] <= horizon, (horizon, review, gap, back))


class TotalsTests(unittest.TestCase):
    def test_sums_the_days_inside_the_window_only(self):
        daily = [{"day": NOV(d), "spend_cents": 100 * d, "leads": 1, "qualified": d % 2, "impressions": 10} for d in range(1, 11)]
        self.assertEqual(cc.totals(daily, NOV(3), NOV(5)), {"days": 3, "spend_cents": 1200, "leads": 3, "qualified": 2, "impressions": 30})

    def test_days_without_rows_still_count_as_days(self):
        self.assertEqual(cc.totals([], NOV(3), NOV(9)), {"days": 7, "spend_cents": 0, "leads": 0, "qualified": 0, "impressions": 0})


class JudgeTests(unittest.TestCase):
    L = 6000

    def judge(self, before, after, q=None, mode="self"):
        return cc.judge(mode, before, after, q, self.L)

    def test_cheaper_but_could_be_chance(self):
        got = self.judge(arm(14000, 3), arm(14000, 5))
        self.assertEqual((got["metric"], got["delta_pct"], got["confidence"], got["state"]), ("cpl_cents", -40, 27, "lean_better"))

    def test_much_cheaper_and_sure(self):
        got = self.judge(arm(30000, 3), arm(30000, 12))
        self.assertEqual((got["delta_pct"], got["confidence"], got["state"]), (-75, 96, "better"))

    def test_much_dearer_and_sure(self):
        got = self.judge(arm(30000, 12), arm(30000, 3))
        self.assertEqual((got["delta_pct"], got["confidence"], got["state"]), (300, 96, "worse"))

    def test_under_ten_percent_is_no_clear_change(self):
        got = self.judge(arm(14000, 4), arm(14000, 4))
        self.assertEqual((got["delta_pct"], got["state"]), (0, "same"))

    def test_too_early_says_what_the_after_side_still_needs(self):
        got = self.judge(arm(14000, 4), arm(9000, 2))
        self.assertEqual((got["state"], got["needs"]), ("too_early", "$30 more spend and 1 more lead"))

    def test_too_early_on_the_before_side_says_so(self):
        got = self.judge(arm(9000, 2), arm(14000, 4))
        self.assertEqual((got["state"], got["needs"], got["notes"]), ("too_early", "$30 more spend and 1 more lead", ["before_short"]))

    def test_no_leads_after_three_times_the_target_looks_worse_but_never_worse(self):
        got = self.judge(arm(18000, 4), arm(18000, 0))
        self.assertEqual((got["state"], got["notes"]), ("lean_worse", ["no_leads"]))

    def test_no_leads_just_under_three_times_the_target_is_too_early(self):
        self.assertEqual(self.judge(arm(18000, 4), arm(17999, 0))["state"], "too_early")

    def test_the_qualified_target_decides_when_both_sides_have_enough_qualified_leads(self):
        got = self.judge(arm(14000, 6, 3), arm(14000, 8, 3), q=6000)
        self.assertEqual((got["metric"], got["state"]), ("cpq_cents", "same"))

    def test_too_few_qualified_leads_falls_back_to_cost_per_lead_with_a_note(self):
        got = self.judge(arm(14000, 6, 3), arm(14000, 8, 1), q=6000)
        self.assertEqual((got["metric"], got["notes"]), ("cpl_cents", ["qualified_short"]))

    def test_no_spend_before_means_nothing_to_compare(self):
        self.assertEqual(self.judge(arm(0, 0), arm(14000, 4))["state"], "no_compare")

    def test_a_new_one_is_measured_against_the_target(self):
        got = cc.judge("new", None, arm(14000, 4), None, 4000)
        self.assertEqual((got["state"], got["metric"]), ("on_target", "cpl_cents"))
        self.assertEqual(cc.judge("new", None, arm(14000, 3), None, 4000)["state"], "over_target")

    def test_a_new_one_that_never_spent_is_not_running(self):
        self.assertEqual(cc.judge("new", None, arm(0, 0), None, 4000)["state"], "not_running")

    def test_stopped_has_only_the_before_numbers(self):
        got = cc.judge("stopped", arm(14000, 3), None, None, self.L)
        self.assertEqual((got["state"], got["delta_pct"], got["confidence"]), ("stopped", None, None))

    def test_a_parent_that_spent_nothing_after_is_stopped(self):
        self.assertEqual(self.judge(arm(14000, 3), arm(0, 0), mode="parent")["state"], "stopped")

    def test_no_target_judges_nothing(self):
        got = cc.judge("self", arm(30000, 12), arm(30000, 3), None, None)
        self.assertEqual((got["state"], got["notes"]), ("too_early", ["no_target"]))

    def test_after_ready_says_which_metrics_can_be_read_on_the_after_side(self):
        got = self.judge(arm(14000, 6, 3), arm(14000, 8, 1), q=6000)
        self.assertEqual(got["after_ready"], {"cpl_cents": True, "cpq_cents": False})


class ModeTests(unittest.TestCase):
    AD = {"level": "ad", "id": "a1", "adset_id": "s1", "campaign_id": "c1"}
    SET = {"level": "adset", "id": "s1", "campaign_id": "c1"}
    CAMP = {"level": "campaign", "id": "c1"}

    def mode(self, action, level, entity, new=None, ok=True):
        return cc.mode_for({"action": action, "level": level, "entity_id": entity["id"], "new_value": new, "ok": ok}, entity)

    def test_a_budget_is_measured_on_the_thing_itself(self):
        self.assertEqual(self.mode("budget", "campaign", self.CAMP), ("self", "campaign", "c1"))

    def test_pausing_an_ad_or_ad_set_is_measured_one_level_up(self):
        self.assertEqual(self.mode("status", "ad", self.AD, "PAUSED"), ("parent", "adset", "s1"))
        self.assertEqual(self.mode("status", "adset", self.SET, "PAUSED"), ("parent", "campaign", "c1"))
        self.assertEqual(self.mode("status", "ad", self.AD, "ACTIVE"), ("parent", "adset", "s1"))

    def test_a_campaign_switched_off_is_stopped_and_on_is_new(self):
        self.assertEqual(self.mode("status", "campaign", self.CAMP, "PAUSED"), ("stopped", "campaign", "c1"))
        self.assertEqual(self.mode("status", "campaign", self.CAMP, "ACTIVE"), ("new", "campaign", "c1"))

    def test_a_new_version_and_a_new_ad(self):
        self.assertEqual(self.mode("update_creative", "ad", self.AD), ("version", "ad", "a1"))
        self.assertEqual(self.mode("restore_creative", "ad", self.AD), ("version", "ad", "a1"))
        self.assertEqual(self.mode("create", "ad", self.AD), ("new", "ad", "a1"))

    def test_meta_advice_and_automatic_changes_are_measured_on_the_thing(self):
        self.assertEqual(self.mode("enhancement", "ad", self.AD), ("self", "ad", "a1"))
        self.assertEqual(self.mode("recommendation", "campaign", self.CAMP), ("self", "campaign", "c1"))

    def test_nothing_to_check(self):
        got = [self.mode(a, "ad", self.AD) for a in ("duplicate", "archive", "delete", "comment_reply", "rename", "subscribe")]
        got += [self.mode("budget", "form", {"id": "f1"}), self.mode("recommendation", "account", {"id": "x"}),
                self.mode("budget", "campaign", self.CAMP, ok=False), self.mode("status", "ad", {"level": "ad", "id": "a9"}, "PAUSED")]
        self.assertEqual(got, [None] * 10)


class ExpectTests(unittest.TestCase):
    def test_reads_the_usual_ways_claude_writes_an_expectation(self):
        cases = {
            "CPL under $40 within 7 days": {"metric": "cpl", "op": "<", "cents": 4000, "days": 7},
            "Cost per qualified lead below $60": {"metric": "cpq", "op": "<", "cents": 6000, "days": 7},
            "cost per lead drops to $35.50": {"metric": "cpl", "op": "<=", "cents": 3550, "days": 7},
            "Per lead under $1,200": {"metric": "cpl", "op": "<", "cents": 120000, "days": 7},
            "CPQL less than $55 over 14 days": {"metric": "cpq", "op": "<", "cents": 5500, "days": 14},
            "cost per lead at most $45 in 3 days": {"metric": "cpl", "op": "<=", "cents": 4500, "days": 3},
        }
        self.assertEqual({t: cc.expect_from_text(t) for t in cases}, cases)

    def test_anything_else_is_not_read(self):
        self.assertEqual([cc.expect_from_text(t) for t in ("More leads, same budget", "CPM under $10", "", None, "cost per lead improves")],
                         [None] * 5)

    def test_clean_expect_takes_only_the_exact_shape(self):
        good = {"metric": "cpl", "op": "<", "cents": 4000, "days": 14}
        self.assertEqual(cc.clean_expect(good), good)
        self.assertEqual(cc.clean_expect({"metric": "cpq", "op": "<=", "cents": 6000}), {"metric": "cpq", "op": "<=", "cents": 6000, "days": 7})
        bad = [{"metric": "cpl", "op": "<", "cents": "4000"}, {"metric": "roas", "op": "<", "cents": 4000}, {**good, "days": 30},
               {**good, "op": ">"}, {**good, "cents": 0}, {**good, "cents": 10_000_001}, {**good, "cents": True}, "cpl < 40", None]
        self.assertEqual([cc.clean_expect(b) for b in bad], [None] * len(bad))

    def test_expectation_met_only_once_that_metric_can_be_read(self):
        expect = {"metric": "cpl", "op": "<", "cents": 4000, "days": 7}
        row = lambda cpl, ready=True, cpq_ready=False: {"after": {"cpl_cents": cpl, "cpq_cents": None},  # noqa: E731
                                                         "after_ready": {"cpl_cents": ready, "cpq_cents": cpq_ready}}
        self.assertEqual([cc.expectation_met(expect, row(3600)), cc.expectation_met(expect, row(4200)), cc.expectation_met(expect, row(4000)),
                          cc.expectation_met({**expect, "op": "<="}, row(4000)), cc.expectation_met(expect, row(3600, ready=False)),
                          cc.expectation_met({**expect, "metric": "cpq"}, row(3600))], [True, False, False, True, None, None])

    def test_expectation_in_words(self):
        self.assertEqual([cc.expect_words({"metric": "cpl", "op": "<", "cents": 4000, "days": 7}, WHOLE),
                          cc.expect_words({"metric": "cpq", "op": "<=", "cents": 6000, "days": 14}, WHOLE)],
                         ["cost per lead under $40", "cost per qualified lead at most $60"])

    def test_what_it_got_in_words(self):
        row = {"days": 7, "after": {"cpl_cents": 3600}, "after_ready": {"cpl_cents": True}}
        self.assertEqual(cc.got_words({"metric": "cpl", "op": "<", "cents": 4000, "days": 7}, row, WHOLE), "$36 over 7 days")
        self.assertIsNone(cc.got_words({"metric": "cpl", "op": "<", "cents": 4000, "days": 7}, {**row, "after_ready": {}}, WHOLE))


def check(state, **kw):
    return {"state": state, "metric": "cpl_cents", "days": 7, "before": None, "after": None, "delta_pct": None, "needs": None,
            "notes": [], "cut_by": None, "changed_on": NOV(9), "ready_on": NOV(13), "target_cents": 6000, **kw}


class SentenceTests(unittest.TestCase):
    def say(self, c):
        return cc.sentence(c, WHOLE, words.day)

    def test_every_state_in_plain_words(self):
        b47, a28 = {"cpl_cents": 4667, "spend_cents": 14000, "leads": 3}, {"cpl_cents": 2800, "spend_cents": 14000, "leads": 5}
        cases = [
            (check("waiting"), "First check on Nov 13"),
            (check("waiting", notes=["stale"]), "Not checked yet: waiting for Meta's numbers."),
            (check("too_early", needs="$30 more spend and 1 more lead"), "Too early to tell: needs $30 more spend and 1 more lead."),
            (check("better", before=b47, after=a28, delta_pct=-40), "Worked: cost per lead $47 → $28 over 7 days (40% cheaper)."),
            (check("lean_better", before=b47, after=a28, delta_pct=-40), "Looks better, not sure yet: cost per lead $47 → $28 over 7 days."),
            (check("same", before={"cpl_cents": 3500}, after={"cpl_cents": 3600}, delta_pct=3), "No clear change: cost per lead $35 → $36 over 7 days."),
            (check("lean_worse", before={"cpl_cents": 2800}, after={"cpl_cents": 4100}, delta_pct=46),
             "Looks worse, not sure yet: cost per lead $28 → $41 over 7 days."),
            (check("lean_worse", after={"cpl_cents": None, "spend_cents": 18000, "leads": 0}, notes=["no_leads"]),
             "Looks worse, not sure yet: no leads in 7 days after spending $180 (3× your target)."),
            (check("worse", before={"cpl_cents": 2500}, after={"cpl_cents": 10000}, delta_pct=300),
             "Didn't help: cost per lead $25 → $100 over 7 days (300% more)."),
            (check("on_target", after={"cpl_cents": 3600}, target_cents=4000), "Got $36 per lead over its first 7 days (target $40)."),
            (check("over_target", after={"cpl_cents": 5200}, target_cents=4000), "Got $52 per lead over its first 7 days (target $40)."),
            (check("mixed", cut_by=NOV(13)), "Changed again on Nov 13, too soon to tell the two changes apart."),
            (check("no_compare"), "It hadn't run long enough before the change to compare."),
            (check("stopped", before={"spend_cents": 14000, "leads": 3, "cpl_cents": 4667}),
             "Off since Nov 9. In the 7 days before, it spent $140 for 3 leads ($47 each)."),
            (check("stopped", before={"spend_cents": 9000, "leads": 0, "cpl_cents": None}), "Off since Nov 9. In the 7 days before, it spent $90 and got no leads."),
            (check("not_running"), "Hasn't spent anything yet."),
            (check("too_early", notes=["no_target"]), "Too early to tell: set a cost-per-lead target in Settings → Targets to judge it."),
        ]
        self.assertEqual([self.say(c) for c, _ in cases], [want for _, want in cases])

    def test_the_qualified_metric_says_so(self):
        c = check("worse", metric="cpq_cents", before={"cpq_cents": 2500}, after={"cpq_cents": 10000}, delta_pct=300, days=3)
        self.assertEqual(self.say(c), "Didn't help: cost per qualified lead $25 → $100 over 3 days (300% more).")
        self.assertEqual(self.say(check("on_target", metric="cpq_cents", after={"cpq_cents": 3600}, days=14)),
                         "Got $36 per qualified lead over its first 14 days (target $60).")


class HeadlineTests(unittest.TestCase):
    def test_the_longest_horizon_that_has_been_read(self):
        rows = [{"horizon": 3, "state": "same"}, {"horizon": 7, "state": "better"}, {"horizon": 14, "state": "waiting"}]
        self.assertEqual(cc.headline(rows), rows[1])

    def test_all_waiting_shows_the_first_check(self):
        rows = [{"horizon": h, "state": "waiting"} for h in (14, 3, 7)]
        self.assertEqual(cc.headline(rows), {"horizon": 3, "state": "waiting"})

    def test_nothing_to_show(self):
        self.assertIsNone(cc.headline([]))


class StateClassTests(unittest.TestCase):
    def test_groups(self):
        self.assertEqual({s: cc.state_class(s) for s in ("better", "lean_better", "on_target", "worse", "lean_worse", "same", "over_target",
                                                         "too_early", "waiting", "mixed", "no_compare", "stopped", "not_running")},
                         {"better": "good", "lean_better": "good", "on_target": "good", "worse": "bad", "lean_worse": "bad", "same": "flat",
                          "over_target": "flat", "too_early": None, "waiting": None, "mixed": None, "no_compare": None, "stopped": None,
                          "not_running": None})


class UndoPlanTests(unittest.TestCase):
    BUDGET = {"id": 5, "action": "budget", "level": "campaign", "entity_id": "c1", "entity_name": "Free intro call",
              "old_value": "2000", "new_value": "2400", "ok": True}
    PAUSE = {"id": 6, "action": "status", "level": "ad", "entity_id": "a1", "entity_name": "N4", "old_value": "ACTIVE", "new_value": "PAUSED", "ok": True}
    VERSION = {"id": 7, "action": "update_creative", "level": "ad", "entity_id": "a1", "entity_name": "N3", "old_value": "111",
               "new_value": "New headline (creative 222)", "ok": True}
    VERSIONS = [{"number": 1, "creative_id": "111"}, {"number": 2, "creative_id": "222"}]

    def plan(self, change, entity, versions=()):
        return cc.undo_plan(change, entity, list(versions), CENTS)

    def test_a_budget_still_in_place_goes_back_to_the_exact_amount(self):
        self.assertEqual(self.plan(self.BUDGET, {"status": "ACTIVE", "daily_budget_cents": 2400}),
                         {"plan": {"kind": "budget", "level": "campaign", "id": "c1", "name": "Free intro call", "from_cents": 2400, "to_cents": 2000},
                          "reason": None})

    def test_a_budget_changed_again_since_says_what_it_is_now(self):
        self.assertEqual(self.plan(self.BUDGET, {"status": "ACTIVE", "daily_budget_cents": 3000}),
                         {"plan": None, "reason": "The budget was changed again since: it's $30.00 a day now."})

    def test_a_switch(self):
        self.assertEqual(self.plan(self.PAUSE, {"status": "PAUSED"})["plan"], {"kind": "status", "level": "ad", "id": "a1", "name": "N4", "to": "ACTIVE"})
        self.assertEqual(self.plan(self.PAUSE, {"status": "ACTIVE"}), {"plan": None, "reason": "It's already on again."})
        on = {**self.PAUSE, "old_value": "PAUSED", "new_value": "ACTIVE"}
        self.assertEqual(self.plan(on, {"status": "PAUSED"}), {"plan": None, "reason": "It's already off again."})

    def test_archived_or_gone(self):
        self.assertEqual([self.plan(self.PAUSE, {"status": "ARCHIVED"})["reason"], self.plan(self.BUDGET, {"status": "DELETED", "daily_budget_cents": 2400})["reason"],
                          self.plan(self.BUDGET, None)["reason"]],
                         ["It's archived, so it can't be switched back.", "It's deleted, so it can't be changed back.",
                          "It isn't on Meta any more, so it can't be changed back."])

    def test_a_new_version_goes_back_to_the_one_before(self):
        self.assertEqual(self.plan(self.VERSION, {"status": "ACTIVE", "creative_id": "222"}, self.VERSIONS),
                         {"plan": {"kind": "version", "level": "ad", "id": "a1", "name": "N3", "number": 1}, "reason": None})
        self.assertEqual(self.plan(self.VERSION, {"status": "ACTIVE", "creative_id": "333"}, self.VERSIONS),
                         {"plan": None, "reason": "The ad has a newer version since."})

    def test_everything_else_is_changed_back_on_the_ads_page(self):
        enh = {**self.BUDGET, "action": "enhancement", "level": "ad", "new_value": "Music off"}
        self.assertEqual(self.plan(enh, {"status": "ACTIVE"}), {"plan": None, "reason": "Change it back on the ad's page."})


class ReversesTests(unittest.TestCase):
    """A write only counts as putting a change back when it restores exactly what was there before."""
    BUDGET, PAUSE, VERSION, VERSIONS = UndoPlanTests.BUDGET, UndoPlanTests.PAUSE, UndoPlanTests.VERSION, UndoPlanTests.VERSIONS

    def test_a_budget_counts_only_at_the_exact_old_amount(self):
        self.assertEqual([cc.reverses(self.BUDGET, cents) for cents in (2000, 3000, 2001, 2400, None, "x")],
                         [True, False, False, False, False, False])

    def test_a_switch_counts_only_back_to_the_old_status(self):
        self.assertEqual([cc.reverses(self.PAUSE, s) for s in ("ACTIVE", "PAUSED", None)], [True, False, False])

    def test_a_version_counts_when_it_is_the_old_creative(self):
        three = self.VERSIONS + [{"number": 3, "creative_id": "333"}]
        self.assertEqual([cc.reverses(self.VERSION, v, three) for v in three], [True, False, False])

    def test_a_version_without_the_old_creative_counts_only_for_the_one_before(self):
        made = {**self.VERSION, "old_value": "999"}
        self.assertEqual([cc.reverses(made, v, self.VERSIONS) for v in self.VERSIONS], [True, False])

    def test_other_changes_never_count(self):
        enh = {**self.BUDGET, "action": "enhancement"}
        self.assertEqual(cc.reverses(enh, 2000), False)


class DialogWordsTests(unittest.TestCase):
    def test_what_is_compared(self):
        self.assertEqual([cc.compared_words("self", "campaign", "Free intro call", "campaign", None),
                          cc.compared_words("parent", "adset", "Broad US", "ad", None),
                          cc.compared_words("version", "ad", "N3", "ad", (NOV(9), NOV(10))),
                          cc.compared_words("version", "ad", "N3", "ad", (NOV(9), NOV(9))),
                          cc.compared_words("stopped", "campaign", "Free intro call", "campaign", None),
                          cc.compared_words("new", "ad", "N6", "ad", None)],
                         ["Compared on the campaign itself.", "Compared on the ad set “Broad US”, which this ad is in.",
                          "The days Meta was reviewing the new version (Nov 9 – Nov 10) count for neither side.",
                          "The day of the switch counts for neither side.", "It's off, so there's no after to compare.",
                          "Its first days are compared with your target."])

    def test_the_minimum_data_rule(self):
        self.assertEqual([cc.rule_words("cpl_cents", 6000, WHOLE), cc.rule_words("cpq_cents", 6000, WHOLE), cc.rule_words("cpl_cents", None, WHOLE)],
                         ["Judged only once each side has spent at least $120 (2× your $60 target) and has 3 leads.",
                          "Judged only once each side has spent at least $120 (2× your $60 target) and has 3 qualified leads.",
                          "Set a cost-per-lead target in Settings → Targets to judge results."])


class AlertTitleTests(unittest.TestCase):
    def test_says_what_was_changed_and_how_it_went(self):
        budget = {"action": "budget", "level": "campaign", "old_value": "2000", "new_value": "2400"}
        self.assertEqual([cc.alert_title(budget, "Free intro call", "worse"),
                          cc.alert_title({**budget, "new_value": "1500"}, "Free intro call", "better"),
                          cc.alert_title({"action": "status", "level": "ad", "new_value": "PAUSED"}, "N4", "lean_worse"),
                          cc.alert_title({"action": "update_creative", "level": "ad"}, "N3", "same")],
                         ["Budget raise on “Free intro call”: didn't help", "Budget cut on “Free intro call”: worked",
                          "Turning off “N4”: looks worse, not sure yet", "New version of “N3”: no clear change"])


if __name__ == "__main__":
    unittest.main()


class SpendLimitNotJudgedTests(unittest.TestCase):
    def test_did_it_work_ignores_account_spending_limit_changes(self):
        cases = [{"ok": True, "level": "account", "action": a, "entity_id": "act_1"} for a in ("spend_limit", "spend_limit_restore")]
        self.assertEqual([cc.mode_for(c, None) for c in cases], [None, None])
