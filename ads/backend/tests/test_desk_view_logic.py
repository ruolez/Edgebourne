import os
import unittest

os.environ.setdefault("WORKERS_ENABLED", "0")

import desk_view  # noqa: E402

N1, V2, HEAD = "120252672229040312", "120252690325970312", "120252689507540312"


def proposal(pid, task_id, **kw):
    return {"id": pid, "task_id": task_id, "kind": "other", "title": "", "entity_type": None, "entity_id": None,
            "status": "pending", "payload": None, **kw}


def task(tid, kind, **kw):
    return {"id": tid, "kind": kind, "status": "done", "options": {}, "proposals": [], "created_at": f"2026-11-09T1{tid}:00", **kw}


class ProposalAdTest(unittest.TestCase):
    def test_the_ad_a_proposal_is_about(self):
        polish = task(2, "polish", options={"ad_id": N1})
        cases = [
            (proposal(1, 2, kind="creative", payload={"template_ad_id": N1}), task(9, "review"), N1),
            (proposal(1, 9, kind="status", entity_type="ad", entity_id=N1), task(9, "review"), N1),
            (proposal(1, 9, kind="budget", entity_type="campaign", entity_id="c1"), task(9, "review"), None),
            (proposal(1, 2, title="Make a new version: x"), polish, N1),
        ]
        for p, t, expected in cases:
            self.assertEqual(desk_view.proposal_ad(p, t), expected, p["kind"])


class ProposalStateTest(unittest.TestCase):
    def test_states_people_read(self):
        cases = [
            (proposal(1, 2), None, None, ("waiting", "Waiting for you")),
            (proposal(1, 2, status="declined"), None, None, ("declined", "Declined")),
            (proposal(1, 2, status="applied"), {"effective_status": "ACTIVE"}, None, ("live", "On")),
            (proposal(1, 2, status="applied"), {"effective_status": "PAUSED"}, None, ("off", "Created, off")),
            (proposal(1, 2, status="applied"), {"effective_status": "IN_PROCESS"}, None, ("review", "In review at Meta")),
            (proposal(1, 2, status="applied"), {"effective_status": "ARCHIVED"}, None, ("archived", "Archived")),
            (proposal(1, 2, status="applied", kind="status"), None, None, ("applied", "Applied on Meta")),
            (proposal(1, 2, status="failed"), None, None, ("failed", "Meta refused it")),
            (proposal(1, 2, status="approved"), None, {"status": "running"}, ("working", "Claude is making it")),
            (proposal(1, 2, status="approved"), None, {"status": "failed"}, ("failed", "Claude didn't finish")),
            (proposal(1, 2, status="approved"), None, None, ("approved", "Approved")),
        ]
        for p, result, followup, expected in cases:
            self.assertEqual(desk_view.proposal_state(p, result, followup), expected, (p["status"], result, followup))

    def test_a_finished_version_request_takes_the_state_of_what_it_made(self):
        made = proposal(5, 3, kind="creative", status="applied")
        state = desk_view.proposal_state(proposal(4, 2, status="approved"), None, {"status": "done"},
                                         made_state=desk_view.proposal_state(made, {"effective_status": "ACTIVE"}, None))
        self.assertEqual(state, ("live", "On"))


class FollowupTest(unittest.TestCase):
    def test_render_run_linked_by_proposal_or_by_the_run_it_came_from(self):
        request = proposal(4, 2, title="Make a new version: offer first", status="approved",
                           decided_at="2026-11-09T12:18:30")
        by_id = task(3, "render", options={"from_proposal": 4, "from_task": 2}, created_at="2026-11-09T12:18:29")
        by_task = task(3, "render", options={"from_task": 2}, created_at="2026-11-09T12:18:29")
        older = task(3, "render", options={"from_task": 2}, created_at="2026-11-09T09:00:00")
        self.assertEqual([desk_view.followup_for(request, [t]) for t in (by_id, by_task, older)],
                         [by_id, by_task, None])

    def test_only_version_requests_have_followups(self):
        p = proposal(1, 2, kind="creative", status="approved")
        self.assertIsNone(desk_view.followup_for(p, [task(3, "render", options={"from_task": 2})]))


class FamiliesTest(unittest.TestCase):
    def test_a_version_made_from_an_ad_joins_that_ads_family(self):
        polish = task(2, "polish", options={"ad_id": N1}, proposals=[
            proposal(1, 2, kind="creative", status="applied", payload={"template_ad_id": N1}),
            proposal(2, 2, kind="creative", payload={"template_ad_id": N1})])
        render = task(3, "render", options={"ad_id": N1}, proposals=[
            proposal(5, 3, kind="creative", status="applied", payload={"template_ad_id": N1})])
        later = task(6, "polish", options={"ad_id": V2})
        research = task(1, "research")
        results = {1: HEAD, 5: V2}
        fams = desk_view.families([later, render, polish, research], results)
        self.assertEqual([(f["root"], f["ads"], f["tasks"], f["pending"]) for f in fams], [
            (N1, [N1, HEAD, V2], [6, 3, 2], 1),
            (None, [], [1], 0),
        ])

    def test_families_with_decisions_waiting_come_first(self):
        a = task(5, "polish", options={"ad_id": "a"})
        b = task(4, "polish", options={"ad_id": "b"}, proposals=[proposal(9, 4, kind="creative", payload={"template_ad_id": "b"})])
        self.assertEqual([f["root"] for f in desk_view.families([a, b], {})], ["b", "a"])


if __name__ == "__main__":
    unittest.main()


class BoardTest(unittest.TestCase):
    def board_of(self, *tasks):
        return desk_view.board([{"queue_rank": 0, "archived_at": None, "seen_at": None, "finished_at": None, "thread_id": None, **t} for t in tasks])

    def states(self, board):
        return {tid: t["state"] for tid, t in board["threads"].items()}

    def test_each_conversation_has_one_state_and_one_place(self):
        waiting = task(1, "review", proposals=[proposal(1, 1)], finished_at="2026-11-09T10:00")
        running = task(2, "render", status="running")
        queued = task(3, "question", status="queued")
        done = task(4, "question", finished_at="2026-11-09T11:00")
        failed = task(5, "question", status="failed", finished_at="2026-11-09T12:00")
        cleared = task(6, "question", archived_at="2026-11-09T13:00", finished_at="2026-11-09T12:30")
        stopped = task(7, "question", status="cancelled", finished_at="2026-11-09T12:45")
        board = self.board_of(waiting, running, queued, done, failed, cleared, stopped)
        self.assertEqual({k: board[k] for k in ("working", "line", "recent", "cleared")},
                         {"working": [2], "line": [3], "recent": [7, 5, 4, 1], "cleared": [6]})
        self.assertEqual(self.states(board), {1: "needs", 2: "working", 3: "queued", 4: "done", 5: "failed", 6: "done", 7: "stopped"})

    def test_a_reply_joins_its_conversation_and_decides_its_state(self):
        first = task(1, "review", finished_at="2026-11-09T10:00", seen_at="2026-11-09T10:01")
        reply = task(2, "review", status="running", thread_id=1)
        board = self.board_of(first, reply)
        self.assertEqual((board["working"], board["recent"], list(board["threads"])), ([1], [], [1]))
        self.assertEqual(board["threads"][1]["turns"], [1, 2])

    def test_a_follow_up_waiting_behind_a_running_turn_keeps_the_conversation_working(self):
        board = self.board_of(task(1, "review", status="running"), task(2, "review", status="queued", thread_id=1))
        self.assertEqual((board["threads"][1]["state"], board["queue"], board["line"]), ("working", [2], []))

    def test_suggestions_waiting_on_an_earlier_turn_still_need_you(self):
        first = task(1, "review", finished_at="2026-11-09T10:00", proposals=[proposal(1, 1), proposal(2, 1)])
        reply = task(2, "review", finished_at="2026-11-09T11:00", thread_id=1, proposals=[proposal(3, 2, status="declined")])
        board = self.board_of(first, reply)
        self.assertEqual((board["threads"][1]["state"], board["threads"][1]["waiting"]), ("needs", 2))

    def test_a_running_conversation_stays_working_while_its_suggestions_arrive(self):
        board = self.board_of(task(1, "review", status="running", proposals=[proposal(1, 1)]))
        self.assertEqual((board["working"], board["threads"][1]["state"]), ([1], "working"))

    def test_waiting_suggestions_keep_a_cleared_turn_in_view(self):
        board = self.board_of(task(1, "review", proposals=[proposal(1, 1)], archived_at="2026-11-09T13:00"))
        self.assertEqual((board["recent"], board["cleared"]), ([1], []))

    def test_clearing_one_turn_leaves_the_rest_of_the_conversation(self):
        first = task(1, "review", finished_at="2026-11-09T10:00", archived_at="2026-11-09T13:00")
        reply = task(2, "review", finished_at="2026-11-09T11:00", thread_id=1)
        board = self.board_of(first, reply)
        self.assertEqual((board["threads"][1]["turns"], board["recent"], board["cleared"]), ([2], [1], []))

    def test_a_conversation_with_every_turn_cleared_shows_them_all_under_cleared(self):
        first = task(1, "review", finished_at="2026-11-09T10:00", archived_at="2026-11-09T13:00")
        reply = task(2, "review", finished_at="2026-11-09T11:00", thread_id=1, archived_at="2026-11-09T13:30")
        board = self.board_of(first, reply)
        self.assertEqual((board["threads"][1]["turns"], board["cleared"], board["threads"][1]["cleared"]), ([1, 2], [1], True))

    def test_the_line_runs_moved_up_requests_first_then_oldest(self):
        tasks = [task(1, "question", status="queued"), task(2, "question", status="queued"),
                 task(3, "question", status="queued", queue_rank=-1)]
        board = self.board_of(*tasks)
        self.assertEqual((board["line"], board["queue"]), ([3, 1, 2], [3, 1, 2]))

    def test_finished_means_new_until_opened_or_decided(self):
        new = task(1, "question", finished_at="2026-11-09T10:00")
        opened = task(2, "question", finished_at="2026-11-09T10:00", seen_at="2026-11-09T11:00")
        decided = task(3, "review", finished_at="2026-11-09T10:00", proposals=[proposal(1, 3, status="applied")])
        threads = self.board_of(new, opened, decided)["threads"]
        self.assertEqual({k: v["fresh"] for k, v in threads.items()}, {1: [1], 2: [], 3: []})

    def test_recent_sorts_by_the_last_thing_said(self):
        old_with_new_reply = task(1, "question", finished_at="2026-11-08T10:00")
        reply = task(3, "question", finished_at="2026-11-09T18:00", thread_id=1)
        newer = task(2, "question", finished_at="2026-11-09T09:00")
        self.assertEqual(self.board_of(old_with_new_reply, newer, reply)["recent"], [1, 2])


class ProposalRevisedTest(unittest.TestCase):
    def test_a_suggestion_sent_back_says_so(self):
        self.assertEqual(desk_view.proposal_state({"status": "revised"}, None, None), ("declined", "Sent back to Claude"))


class AcceptedRunTest(unittest.TestCase):
    def test_the_run_started_by_accepting_a_suggestion(self):
        runs = [task(2, "question", options={"reply": True}), task(3, "question", options={"reply": True, "accepted": {"id": 7, "title": "Do it"}})]
        self.assertEqual(desk_view.accepted_run(proposal(7, 1, status="approved"), runs)["id"], 3)

    def test_no_run_means_none(self):
        self.assertIsNone(desk_view.accepted_run(proposal(7, 1, status="approved"), [task(2, "question")]))

    def test_the_state_follows_the_run(self):
        p = proposal(7, 1, status="approved")
        self.assertEqual([desk_view.accepted_state(p, {"status": s}) for s in ("queued", "running", "done", "failed", "cancelled")],
                         [("working", "Claude is on it"), ("working", "Claude is on it"), ("done", "Claude answered below"),
                          ("failed", "Claude didn't finish"), ("declined", "Stopped")])


class NeedsFollowThroughTest(unittest.TestCase):
    def test_what_nothing_else_acts_on_goes_to_claude(self):
        self.assertTrue(desk_view.needs_follow_through(proposal(1, 1, title="Fix the apply step")))
        self.assertTrue(desk_view.needs_follow_through(proposal(1, 1, kind="targeting", title="Narrow the age range")))

    def test_a_new_version_has_its_own_run(self):
        self.assertFalse(desk_view.needs_follow_through(proposal(1, 1, title="Make a new version: slower opening")))

    def test_the_prompt_says_what_was_accepted_and_the_next_step(self):
        p = proposal(1, 1, title="Fix the apply step", expected="Read the stored error.")
        self.assertEqual(desk_view.accepted_prompt(p), "I accepted your suggestion: Fix the apply step\nNext step you wrote: Read the stored error.")

    def test_the_prompt_without_a_next_step(self):
        self.assertEqual(desk_view.accepted_prompt(proposal(1, 1, title="Fix it")), "I accepted your suggestion: Fix it")


class NowTest(unittest.TestCase):
    def row(self, tid, status, **kw):
        return {"id": tid, "status": status, "prompt": f"ask {tid}\nmore", "progress": None, "options": {}, "thread_id": None,
                "claimed_at": None, "created_at": "2026-11-10T10:00", "queue_rank": 0, **kw}

    def test_nothing_going_on(self):
        self.assertEqual(desk_view.now([]), {"working": None, "next": [], "queued": 0})

    def test_what_is_running_and_the_line_in_order(self):
        rows = [self.row(1, "queued"), self.row(2, "running", progress="Reading", claimed_at="2026-11-10T10:01", thread_id=9),
                self.row(3, "queued", queue_rank=-1, options={"schedule": "Optimizer"})]
        self.assertEqual(desk_view.now(rows), {
            "working": {"id": 2, "thread": 9, "title": "ask 2", "progress": "Reading", "since": "2026-11-10T10:01"},
            "next": [{"id": 3, "thread": 3, "title": "Optimizer"}, {"id": 1, "thread": 1, "title": "ask 1"}], "queued": 2})

    def test_the_line_is_counted_in_full_but_only_the_start_is_listed(self):
        out = desk_view.now([self.row(i, "queued") for i in range(1, 9)], show=3)
        self.assertEqual(([n["id"] for n in out["next"]], out["queued"]), ([1, 2, 3], 8))


class TranscriptTest(unittest.TestCase):
    def turn(self, tid, **kw):
        return {"id": tid, "kind": "review", "prompt": f"ask {tid}", "status": "done", "summary": f"said {tid}", "error": None,
                "options": {}, "reports": [], "proposals": [], **kw}

    def test_earlier_turns_in_order_with_what_was_decided(self):
        p = {"id": 7, "kind": "budget", "title": "Raise", "status": "declined", "rationale": "cheap", "entity_name": "C",
             "field": "budget", "current_value": "$20/day", "proposed_value": "$24/day", "payload": None, "failure": "Meta said no", "secret": "x"}
        out = desk_view.transcript([self.turn(1, reports=[{"title": "R", "body": "text", "id": 3}], proposals=[p])])
        self.assertEqual(out, [{"id": 1, "kind": "review", "you": "ask 1", "status": "done", "claude": "said 1", "error": None,
                                "reports": [{"title": "R", "body": "text"}],
                                "suggestions": [{"id": 7, "kind": "budget", "title": "Raise", "status": "declined", "rationale": "cheap",
                                                 "entity_name": "C", "field": "budget", "current_value": "$20/day",
                                                 "proposed_value": "$24/day", "payload": None, "failure": "Meta said no"}]}])

    def test_long_reports_are_cut_and_only_recent_turns_kept(self):
        turns = [self.turn(i, reports=[{"title": "R", "body": "x" * 9000}]) for i in range(1, 9)]
        out = desk_view.transcript(turns, limit=3, body=100)
        self.assertEqual(([t["id"] for t in out], len(out[0]["reports"][0]["body"])), ([6, 7, 8], 101))


class ResumeFromTest(unittest.TestCase):
    def test_the_latest_turn_the_mac_actually_started(self):
        turns = [{"id": 1, "claimed_at": "x"}, {"id": 2, "claimed_at": "y"}, {"id": 3, "claimed_at": None}]
        self.assertEqual(desk_view.resume_from(turns), 2)

    def test_nothing_to_resume(self):
        self.assertIsNone(desk_view.resume_from([{"id": 1, "claimed_at": None}]))


class MentionedAdsTest(unittest.TestCase):
    ADS = [{"id": "1", "name": "N1 - One simple system", "effective_status": "PAUSED"},
           {"id": "2", "name": "N1 - One simple system · v2", "effective_status": "ACTIVE"},
           {"id": "3", "name": "N3 - Same work twice", "effective_status": "ACTIVE"},
           {"id": "4", "name": "N4 - Weekly report", "effective_status": "DELETED"},
           {"id": "5", "name": "Summer promo", "effective_status": "ACTIVE"}]

    def ids(self, text, **kw):
        return desk_view.mentioned_ads(text, self.ADS, **kw)

    def test_full_names_and_short_codes_in_reading_order(self):
        self.assertEqual(self.ids("N3 - Same work twice beat the Summer promo."), ["3", "5"])
        self.assertEqual(self.ids("Summer promo lost to N3 last week."), ["5", "3"])

    def test_a_short_code_means_the_version_that_runs(self):
        self.assertEqual(self.ids("N1 carried the account."), ["2"])

    def test_a_named_version_wins(self):
        self.assertEqual(self.ids("N1 · v2 carried it"), ["2"])

    def test_a_full_name_is_not_also_counted_as_its_longer_sibling(self):
        self.assertEqual(self.ids("Compare N1 - One simple system with the rest."), ["1"])

    def test_codes_inside_other_words_do_not_count(self):
        self.assertEqual(self.ids("AN3 and N33 and CN1x are not ads"), [])

    def test_deleted_ads_are_left_out(self):
        self.assertEqual(self.ids("N4 - Weekly report is gone, N4 too."), [])

    def test_at_most_the_limit(self):
        self.assertEqual(self.ids("N3 and Summer promo", limit=1), ["3"])


def plan_item(pid=1, plan=None, **kw):
    return desk_view.review_item(proposal(pid, 9, title="T", **kw), plan or {"kind": "record"})


class ReviewItemTest(unittest.TestCase):
    def test_each_kind_of_change_lands_in_its_group(self):
        cases = [
            ({"kind": "budget", "from": 2000, "to": 2400, "pct": 20, "big": False, "problem": None}, "money"),
            ({"kind": "status", "to": "ACTIVE", "spend": {"daily_cents": 2000}}, "money"),
            ({"kind": "status", "to": "PAUSED"}, "live"),
            ({"kind": "vertical", "name": "N1", "live": True}, "live"),
            ({"kind": "create"}, "create"),
            ({"kind": "render", "ad_id": N1}, "mac"),
            ({"kind": "experiment"}, "local"),
            ({"kind": "tags"}, "local"),
            ({"kind": "record"}, "mac"),
        ]
        for plan, group in cases:
            self.assertEqual(plan_item(plan=plan)["group"], group, plan["kind"])

    def test_a_budget_step_within_the_rules_is_ticked_with_the_amounts_it_was_read_at(self):
        item = plan_item(plan={"kind": "budget", "from": 2000, "to": 2400, "pct": 20, "big": False, "problem": None})
        self.assertEqual((item["tick"], item["needs_tick"], item["body"]),
                         (True, False, {"from_cents": 2000, "to_cents": 2400, "accept_big": False}))

    def test_a_big_budget_step_waits_for_its_own_tick(self):
        item = plan_item(plan={"kind": "budget", "from": 2000, "to": 4000, "pct": 100, "big": True, "problem": None})
        self.assertEqual((item["tick"], item["needs_tick"], item["body"]["accept_big"]), (False, True, True))

    def test_a_budget_that_moved_since_claude_looked_waits_for_its_own_tick(self):
        step = {"kind": "budget", "from": 3100, "to": 2400, "pct": -23, "big": False, "problem": None}
        cases = [("$20/day", True, "Claude saw $20.00 a day. It's $31.00 now."), ("$31/day", False, None), (None, False, None)]
        for seen, held, note in cases:
            item = plan_item(plan=step, current_value=seen)
            self.assertEqual((item["needs_tick"], item["tick"], item["note"]), (held, not held, note), seen)

    def test_turning_something_on_waits_for_its_own_tick(self):
        item = plan_item(plan={"kind": "status", "to": "ACTIVE", "spend": {"daily_cents": 2000, "where": "C"}})
        self.assertEqual((item["tick"], item["needs_tick"], item["body"]), (False, True, {"confirm_daily_cents": 2000}))

    def test_what_cannot_be_applied_is_blocked_with_the_reason(self):
        cases = [
            ({"kind": "unclear", "problem": "Not one clear amount"}, "Not one clear amount"),
            ({"kind": "budget", "from": 2000, "to": 90000, "pct": 4400, "big": True, "problem": "Above the ceiling"}, "Above the ceiling"),
        ]
        for plan, reason in cases:
            item = plan_item(plan=plan)
            self.assertEqual((item["group"], item["blocked"], item["tick"]), ("blocked", reason, False))


class ReviewTest(unittest.TestCase):
    def test_two_changes_to_the_same_budget_are_never_ticked_together(self):
        step = {"kind": "budget", "from": 2000, "to": 2400, "pct": 20, "big": False, "problem": None}
        items = desk_view.review([
            (proposal(1, 9, title="A", kind="budget", entity_id="c1"), step),
            (proposal(2, 9, title="B", kind="budget", entity_id="c1"), step),
            (proposal(3, 9, title="C", kind="budget", entity_id="c2"), step),
        ])
        self.assertEqual([(i["id"], i["tick"], i["conflict"]) for i in items],
                         [(1, False, "budget:c1"), (2, False, "budget:c1"), (3, True, None)])

    def test_two_updates_of_one_ad_are_never_ticked_together(self):
        update = {"kind": "update", "name": "N3", "live": True, "ad_id": "a1"}
        other = {"kind": "update", "name": "N4", "live": True, "ad_id": "a2"}
        items = desk_view.review([(proposal(1, 9, title="A", kind="creative"), update),
                                  (proposal(2, 9, title="B", kind="creative"), update),
                                  (proposal(3, 9, title="C", kind="creative"), other)])
        self.assertEqual([(i["id"], i["group"], i["tick"], i["conflict"]) for i in items],
                         [(1, "live", False, "creative:a1"), (2, "live", False, "creative:a1"), (3, "live", True, None)])

    def test_a_words_update_and_a_9_16_update_of_one_ad_conflict(self):
        items = desk_view.review([(proposal(1, 9, title="A", kind="creative"), {"kind": "update", "name": "N3", "ad_id": "a1"}),
                                  (proposal(2, 9, title="B", kind="creative", payload={"template_ad_id": "a1"}), {"kind": "vertical", "name": "N3"})])
        self.assertEqual([i["conflict"] for i in items], ["creative:a1", "creative:a1"])

    def test_money_comes_first_and_blocked_last(self):
        items = desk_view.review([
            (proposal(1, 9, title="A"), {"kind": "unclear", "problem": "x"}),
            (proposal(2, 9, title="B"), {"kind": "tags"}),
            (proposal(3, 9, title="C", entity_id="c1"), {"kind": "status", "to": "ACTIVE", "spend": {}}),
            (proposal(4, 9, title="D"), {"kind": "create"}),
        ])
        self.assertEqual([i["id"] for i in items], [3, 4, 2, 1])
