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
        return desk_view.board([{"queue_rank": 0, "archived_at": None, "seen_at": None, "finished_at": None, **t} for t in tasks])

    def test_each_request_lands_in_one_tray(self):
        waiting = task(1, "review", proposals=[proposal(1, 1)], finished_at="2026-11-09T10:00")
        running = task(2, "render", status="running")
        queued = task(3, "question", status="queued")
        done = task(4, "question", finished_at="2026-11-09T11:00")
        failed = task(5, "question", status="failed", finished_at="2026-11-09T12:00")
        cleared = task(6, "question", archived_at="2026-11-09T13:00", finished_at="2026-11-09T12:30")
        self.assertEqual(
            {k: v for k, v in self.board_of(waiting, running, queued, done, failed, cleared).items() if k != "fresh"},
            {"needs_you": [1], "working": [2], "next": [3], "finished": [5, 4], "cleared": [6]})

    def test_a_running_request_stays_working_while_its_suggestions_arrive(self):
        running = task(1, "review", status="running", proposals=[proposal(1, 1)])
        result = self.board_of(running)
        self.assertEqual((result["working"], result["needs_you"]), ([1], []))

    def test_waiting_suggestions_keep_a_cleared_request_in_needs_you(self):
        t = task(1, "review", proposals=[proposal(1, 1)], archived_at="2026-11-09T13:00")
        self.assertEqual(self.board_of(t)["needs_you"], [1])

    def test_the_queue_runs_moved_up_requests_first_then_oldest(self):
        tasks = [task(1, "question", status="queued"), task(2, "question", status="queued"),
                 task(3, "question", status="queued", queue_rank=-1)]
        self.assertEqual(self.board_of(*tasks)["next"], [3, 1, 2])

    def test_finished_means_new_until_opened_or_decided(self):
        new = task(1, "question", finished_at="2026-11-09T10:00")
        opened = task(2, "question", finished_at="2026-11-09T10:00", seen_at="2026-11-09T11:00")
        decided = task(3, "review", finished_at="2026-11-09T10:00", proposals=[proposal(1, 3, status="applied")])
        self.assertEqual(self.board_of(new, opened, decided)["fresh"], [1])


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
            ({"kind": "record"}, "local"),
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

    def test_money_comes_first_and_blocked_last(self):
        items = desk_view.review([
            (proposal(1, 9, title="A"), {"kind": "unclear", "problem": "x"}),
            (proposal(2, 9, title="B"), {"kind": "tags"}),
            (proposal(3, 9, title="C", entity_id="c1"), {"kind": "status", "to": "ACTIVE", "spend": {}}),
            (proposal(4, 9, title="D"), {"kind": "create"}),
        ])
        self.assertEqual([i["id"] for i in items], [3, 4, 2, 1])
