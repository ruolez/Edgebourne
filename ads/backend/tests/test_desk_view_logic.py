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
