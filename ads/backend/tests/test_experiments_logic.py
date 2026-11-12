import unittest
from datetime import date, datetime

import experiments as ex


def arm(label, spend=0, leads=0, impressions=0, clicks=0, views=0, qualified=0):
    return {"label": label, "spend_cents": spend, "leads": leads, "impressions": impressions,
            "link_clicks": clicks, "video_3s": views, "qualified": qualified}


class ConfidenceTests(unittest.TestCase):
    def test_equal_spend_and_equal_leads_means_no_evidence_of_a_difference(self):
        self.assertEqual(ex.confidence("cpl", arm("A", 10000, 10), arm("B", 10000, 10)), 0)

    def test_a_lopsided_lead_split_on_equal_spend_is_near_certain(self):
        # 20 leads vs 4 on the same spend: exact binomial two-sided p ≈ 0.0015
        self.assertEqual(ex.confidence("cpl", arm("A", 10000, 20), arm("B", 10000, 4)), 99)

    def test_spend_is_the_exposure_so_twice_the_spend_for_twice_the_leads_is_even(self):
        self.assertEqual(ex.confidence("cpl", arm("A", 20000, 12), arm("B", 10000, 6)), 0)

    def test_click_rate_uses_a_two_proportion_test(self):
        # 2.0% vs 1.0% on 5,000 impressions each: z ≈ 4.04
        self.assertEqual(ex.confidence("ctr", arm("A", impressions=5000, clicks=100), arm("B", impressions=5000, clicks=50)), 99)


class JudgeTests(unittest.TestCase):
    def test_too_early_names_what_each_arm_still_needs(self):
        j = ex.judge("cpl", [arm("A", 3000, 2), arm("B", 9000, 3)], target_cents=2000, days_run=5)
        self.assertEqual((j["state"], j["needs"]), ("early", {"A": "$10 more spend and 1 more lead"}))

    def test_a_rate_test_counts_views_not_impressions(self):
        # One vocabulary (9.2): Meta's impressions are "views" on screen. 400 of the 1,000 needed.
        needed = ex.MIN_IMPRESSIONS - 400
        clicks = ex.MIN_SUCCESSES
        self.assertEqual(ex.needs("ctr", arm("A", impressions=400, clicks=clicks), None), f"{needed:,} more views")

    def test_what_an_arm_needs_is_in_the_account_currency(self):
        j = ex.judge("cpl", [arm("A", 3000, 2), arm("B", 9000, 3)], target_cents=2000, days_run=5, currency="GBP")
        self.assertEqual(j["needs"], {"A": "£10 more spend and 1 more lead"})

    def test_nothing_is_judged_before_three_full_days(self):
        j = ex.judge("cpl", [arm("A", 10000, 20), arm("B", 10000, 4)], target_cents=1000, days_run=2)
        self.assertEqual((j["state"], j["note"].startswith("Too early to call: it needs 1 more full day")), ("early", True))

    def test_a_clear_difference_with_enough_data_calls_the_cheaper_arm_the_winner(self):
        j = ex.judge("cpl", [arm("A", 10000, 4), arm("B", 10000, 20)], target_cents=1000, days_run=7)
        self.assertEqual((j["state"], j["leader"], j["diff_pct"], j["note"]), ("winner", "B", 80, "B wins: 80% cheaper, 99% sure."))

    def test_a_small_difference_is_not_called(self):
        j = ex.judge("cpl", [arm("A", 10000, 10), arm("B", 10000, 12)], target_cents=1000, days_run=7)
        self.assertEqual((j["state"], j["leader"], j["note"]),
                         ("even", "B", "No clear difference yet: B is 17% cheaper so far, which could easily be chance."))

    def test_without_a_target_the_pooled_cost_sets_the_spend_bar(self):
        # pooled $50 a lead → each arm needs $100 spent
        j = ex.judge("cpl", [arm("A", 6000, 1), arm("B", 14000, 3)], days_run=7)
        self.assertEqual((j["target_cents"], j["needs"]), (5000, {"A": "$40 more spend and 2 more leads"}))

    def test_an_arm_without_leads_ranks_last_on_cost(self):
        j = ex.judge("cpl", [arm("A", 20000, 0), arm("B", 20000, 9)], target_cents=2000, days_run=7)
        self.assertEqual((j["leader"], j["runner_up"], j["needs"]), ("B", "A", {"A": "3 more leads"}))

    def test_rates_rank_the_higher_share_first(self):
        j = ex.judge("hook", [arm("A", impressions=4000, views=800), arm("B", impressions=4000, views=1200)], days_run=7)
        self.assertEqual((j["state"], j["leader"], j["diff_pct"]), ("winner", "B", 50))

    def test_one_arm_cannot_be_compared(self):
        self.assertEqual(ex.judge("cpl", [arm("A", 1000, 1)], days_run=7)["note"], "Add a second side to compare.")


class MembersTests(unittest.TestCase):
    def test_an_arm_names_each_ad_and_ad_set_with_its_id_and_marks_the_ones_gone(self):
        got = ex.arm_members({"label": "A", "ad_ids": ["a1", "a9"], "adset_ids": ["s1", "s9"]},
                             {"a1": "N1 - pain"}, {"s1": "SoCal owners"})
        self.assertEqual(got, [{"level": "ad", "id": "a1", "name": "N1 - pain", "gone": False},
                               {"level": "ad", "id": "a9", "name": None, "gone": True},
                               {"level": "adset", "id": "s1", "name": "SoCal owners", "gone": False},
                               {"level": "adset", "id": "s9", "name": None, "gone": True}])

    def test_an_arm_without_ids_has_no_members(self):
        self.assertEqual(ex.arm_members({"label": "A"}, {}, {}), [])


class ContainingTests(unittest.TestCase):
    def test_tests_with_the_ad_or_its_whole_ad_set_running_ones_first_then_newest(self):
        exps = [{"id": 1, "name": "Old hooks", "status": "done", "arms": [{"ad_ids": ["a1"]}, {"ad_ids": ["a2"]}]},
                {"id": 2, "name": "Sets", "status": "running", "arms": [{"adset_ids": ["s1"]}, {"adset_ids": ["s2"]}]},
                {"id": 3, "name": "Other ads", "status": "running", "arms": [{"ad_ids": ["a3"]}, {"ad_ids": ["a4"]}]},
                {"id": 4, "name": "New hooks", "status": "done", "arms": [{"ad_ids": ["a2", "a1"]}, {"ad_ids": ["a5"]}]}]
        self.assertEqual(ex.containing(exps, "a1", "s1"), [{"id": 2, "name": "Sets", "status": "running"},
                                                           {"id": 4, "name": "New hooks", "status": "done"},
                                                           {"id": 1, "name": "Old hooks", "status": "done"}])

    def test_an_ad_in_no_test_and_an_ad_without_an_ad_set(self):
        exps = [{"id": 1, "name": "T", "status": "running", "arms": [{"ad_ids": ["a2"]}, {"adset_ids": ["s2"]}]}]
        self.assertEqual((ex.containing(exps, "a1", "s1"), ex.containing(exps, "a1", None)), ([], []))



def live(ads=(), adsets=(), campaigns=()):
    return {"ads": {a["id"]: a for a in ads}, "adsets": {s["id"]: s for s in adsets}, "campaigns": {c["id"]: c for c in campaigns}}


def ad(i, name, status="ACTIVE", adset="s1", campaign="c1", effective=None):
    return {"id": i, "name": name, "status": status, "effective_status": effective or status, "adset_id": adset, "campaign_id": campaign}


def aset(i, name, budget=None, status="ACTIVE", campaign="c1"):
    return {"id": i, "name": name, "status": status, "effective_status": status, "campaign_id": campaign, "daily_budget_cents": budget}


def test_of(arms, status="running", state="winner", leader="A", winner=None, metric="cpl", name="Hook test", closed_at=None, verdict=None):
    return {"name": name, "metric": metric, "status": status, "winner": winner, "closed_at": closed_at, "verdict": verdict,
            "judgement": {"state": state, "leader": leader, "note": f"{leader} wins: 40% cheaper, 97% sure."},
            "arms": [{"label": lab, "ad_ids": list(a), "adset_ids": list(s)} for lab, a, s in arms]}


class NextStepTests(unittest.TestCase):
    """What to do once a test has a winner: switch the others off and fund the winner, each through the
    console's usual confirmations; nothing is decided while the numbers are still out."""

    def test_a_running_winner_offers_to_turn_off_the_losers_still_on_and_its_own_budget(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], []), ("C", ["c1ad"], [])])
        world = live([ad("a1", "N1", adset="s1"), ad("b1", "N3", adset="s2"), ad("c1ad", "N5", status="PAUSED", adset="s2")],
                     [aset("s1", "Owners", budget=2000), aset("s2", "Managers", budget=1500)])
        step = ex.next_step(t, world)
        self.assertEqual(step["winner"], "A")
        self.assertEqual(step["turn_off"], [{"level": "ad", "id": "b1", "name": "N3", "side": "B"}])
        self.assertEqual(step["budgets"], [{"level": "adset", "id": "s1", "name": "Owners", "daily_budget_cents": 2000, "shared_with": []}])
        self.assertFalse(step["winner_off"])

    def test_a_budget_the_winner_shares_with_a_loser_still_on_names_that_loser(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])])
        world = live([ad("a1", "N1", adset="s1"), ad("b1", "N3", adset="s1")], [aset("s1", "Owners", budget=2000)])
        self.assertEqual(ex.next_step(t, world)["budgets"][0]["shared_with"], ["N3"])

    def test_without_an_ad_set_budget_the_campaign_budget_is_the_one_to_raise(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])])
        world = live([ad("a1", "N1", adset="s1", campaign="c1"), ad("b1", "N3", status="PAUSED", adset="s1", campaign="c1")],
                     [aset("s1", "Owners")], [{"id": "c1", "name": "Free intro call", "daily_budget_cents": 3100}])
        step = ex.next_step(t, world)
        self.assertEqual((step["turn_off"], step["budgets"]),
                         ([], [{"level": "campaign", "id": "c1", "name": "Free intro call", "daily_budget_cents": 3100, "shared_with": []}]))

    def test_a_losing_ad_set_holding_the_winning_ad_is_never_offered_to_turn_off(self):
        t = test_of([("A", ["a1"], []), ("B", [], ["s1"])])
        world = live([ad("a1", "N1", adset="s1")], [aset("s1", "Owners", budget=2000)])
        self.assertEqual(ex.next_step(t, world)["turn_off"], [])

    def test_losers_gone_deleted_or_archived_are_left_out(self):
        t = test_of([("A", ["a1"], []), ("B", ["gone", "del", "arc"], [])])
        world = live([ad("a1", "N1"), ad("del", "N7", effective="DELETED"), ad("arc", "N8", effective="ARCHIVED")], [aset("s1", "Owners", 2000)])
        self.assertEqual(ex.next_step(t, world)["turn_off"], [])

    def test_a_winner_picked_by_hand_when_finishing_still_gets_a_next_step(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])], status="done", state="early", leader="A", winner="B")
        world = live([ad("a1", "N1", adset="s2"), ad("b1", "N3", status="PAUSED", adset="s1")], [aset("s1", "Owners", 2000), aset("s2", "Managers", 900)])
        step = ex.next_step(t, world)
        self.assertEqual((step["winner"], [x["id"] for x in step["turn_off"]], step["winner_off"]), ("B", ["a1"], True))

    def test_no_next_step_until_there_is_a_winner(self):
        arms = [("A", ["a1"], []), ("B", ["b1"], [])]
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        for t in (test_of(arms, state="early"), test_of(arms, state="leaning"), test_of(arms, state="even"),
                  test_of(arms, status="done", state="winner", winner=None), test_of(arms, status="stopped", state="winner")):
            self.assertIsNone(ex.next_step(t, world), (t["status"], t["judgement"]["state"], t["winner"]))

    def test_make_more_like_this_asks_claude_about_the_winning_ad_by_name(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])], name="Problem hook vs result hook")
        world = live([ad("a1", "N1 - One simple system"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        more = ex.next_step(t, world)["more_like"]
        self.assertEqual((more["ad_id"], more["name"]), ("a1", "N1 - One simple system"))
        for part in ("N1 - One simple system", "a1", "Problem hook vs result hook", "cost per lead", "40% cheaper"):
            self.assertIn(part, more["prompt"])
        self.assertLessEqual(len(more["prompt"]), 4000)

    def test_a_winning_ad_set_is_described_by_its_name(self):
        t = test_of([("A", [], ["s1"]), ("B", [], ["s2"])], metric="hook")
        world = live([], [aset("s1", "Owners", 2000), aset("s2", "Managers", 1500)])
        step = ex.next_step(t, world)
        self.assertEqual((step["more_like"]["ad_id"], step["turn_off"], [b["id"] for b in step["budgets"]]),
                         (None, [{"level": "adset", "id": "s2", "name": "Managers", "side": "B"}], ["s1"]))
        self.assertIn("Owners", step["more_like"]["prompt"])
        self.assertIn("hook rate", step["more_like"]["prompt"])

    def test_while_meta_still_runs_the_split_nothing_is_offered_to_switch_off_or_fund(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])])
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        for meta in ({"state": "running", "end_day": "2026-11-20"}, {"state": "scheduled", "end_day": "2026-11-20"}, {"creating": True}):
            step = ex.next_step(t, world, meta)
            self.assertEqual((step["turn_off"], step["budgets"], step["wait"]), ([], [], {"until": meta.get("end_day")}), meta)

    def test_once_meta_has_ended_the_usual_next_step_comes_back(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])])
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        step = ex.next_step(t, world, {"state": "ended", "end_day": "2026-11-01"})
        self.assertEqual(([x["id"] for x in step["turn_off"]], step["wait"]), (["b1"], None))

    def test_a_finished_test_offers_its_next_step_for_two_weeks_after_closing(self):
        arms = [("A", ["a1"], []), ("B", ["b1"], [])]
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        today = date(2026, 11, 12)
        fresh = test_of(arms, status="done", winner="A", closed_at=datetime(2026, 10, 29, 9, 0))
        old = test_of(arms, status="done", winner="A", closed_at="2026-10-28T09:00:00+00:00")
        self.assertEqual((ex.next_step(fresh, world, today=today) is not None, ex.next_step(old, world, today=today)), (True, None))

    def test_a_hand_picked_winner_is_never_described_with_the_numbers_other_side_note(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])], status="done", state="winner", leader="A", winner="B")
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        prompt = ex.next_step(t, world)["more_like"]["prompt"]
        self.assertNotIn("A wins", prompt)
        self.assertIn("B was picked as the winner.", prompt)

    def test_a_finished_test_quotes_what_was_learned(self):
        t = test_of([("A", ["a1"], []), ("B", ["b1"], [])], status="done", state="early", winner="B", verdict="Naming the pain first won.")
        world = live([ad("a1", "N1"), ad("b1", "N3")], [aset("s1", "Owners", 2000)])
        self.assertIn("Naming the pain first won.", ex.next_step(t, world)["more_like"]["prompt"])


if __name__ == "__main__":
    unittest.main()
