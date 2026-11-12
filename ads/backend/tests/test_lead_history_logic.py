import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import jobs
import lead_history as lh

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
LA = ZoneInfo("America/Los_Angeles")
EUGENE, ANNA = 1, 2


def ev(i, kind="stage", mins=2, user=EUGENE, outcome=None, actor="user", undone=False, **details):
    return {"id": i, "at": NOW - timedelta(minutes=mins), "kind": kind, "outcome": outcome, "user_id": user, "actor": actor,
            "who": {EUGENE: "Eugene", ANNA: "Anna"}.get(user), "details": details,
            "undone_at": NOW - timedelta(minutes=1) if undone else None, "undone_who": "Eugene" if undone else None}


class DescribeTests(unittest.TestCase):
    def test_each_line_reads_as_a_sentence(self):
        rows = [ev(1, "received", user=None, actor="meta", ad="N1 · v2"), ev(2, "received", user=None, actor="meta"),
                ev(3, "call", outcome="reached", note="Wants a call with the owner next week, after the holidays are over and things settle"),
                ev(4, "call", outcome="no_answer"), ev(5, "call", outcome="voicemail"), ev(6, "call", outcome="wrong_number"),
                ev(7, "call", outcome="booked", meeting_at="2026-11-13T22:00:00+00:00"), ev(8, "call", outcome="booked"),
                ev(9, backfilled=True, **{"from": "new", "to": "contacted"}), ev(10, **{"from": "contacted", "to": "lost", "note": "Couldn't reach after 3 tries"}),
                ev(11, "owner", to_id=ANNA, to_name="Anna"), ev(12, "owner", to_id=None, from_name="Anna"), ev(13, "owner", owner_id=None),
                ev(14, "note"), ev(15, "email", subject="Your intro call"), ev(16, "email_auto", user=None, actor="system", subject="Thanks"),
                ev(17, "alert_failed", user=None, actor="system"),
                ev(18, "next_set", next_kind="call_back", next_at="2026-11-12T17:00:00+00:00"),
                ev(19, "next_set", next_kind="other", next_text="Send the case study", next_at="2026-11-12T17:00:00+00:00"),
                ev(20, "next_done", next_kind="call_back"), ev(21, "next_cleared", next_kind="call_back"),
                ev(22, "next_cleared", user=None, actor="system", next_kind="call_back", reason="closed", status="won"),
                ev(23, "booked", meeting_at="2026-11-13T22:00:00+00:00"), ev(24, "call_moved", meeting_at="2026-11-14T18:00:00+00:00"),
                ev(25, "call_canceled"), ev(26, "call_held"), ev(27, "no_show"), ev(28, "booking_removed"),
                ev(29, "call", outcome="no_answer", undone=True), ev(30, "repeat")]
        self.assertEqual([lh.describe(r, LA, {ANNA: "Anna"}) for r in rows], [
            "Received from Meta (N1 · v2)",
            "Received from Meta",
            "Eugene called: talked to them · ‘Wants a call with the owner next week, after the holidays are over and things se…’",
            "Eugene called: no answer",
            "Eugene called: left a voicemail",
            "Eugene called: wrong number",
            "Eugene called: booked a call for Fri, Nov 13, 2:00 PM",
            "Eugene called: booked a call, time not set",
            "Eugene moved it from New to Contacted",
            "Eugene moved it from Contacted to Lost: Couldn't reach after 3 tries",
            "Eugene gave it to Anna",
            "Eugene took Anna off it",
            "Eugene took the owner off",
            "Eugene added a note",
            "Eugene emailed them: Your intro call",
            "Automatic reply sent: Thanks",
            "The new-lead email to the team couldn't be sent",
            "Next step: Call back, Thu, Nov 12, 9:00 AM",
            "Next step: Send the case study, Thu, Nov 12, 9:00 AM",
            "Done: Call back",
            "Eugene removed the next step",
            "Next step closed: lead is Won",
            "Eugene marked a call booked for Fri, Nov 13, 2:00 PM",
            "Call moved to Sat, Nov 14, 10:00 AM",
            "Call canceled",
            "The call happened",
            "No-show",
            "Eugene removed the booked call",
            "Eugene called: no answer (undone)",
            "Repeat",
        ])

    def test_a_person_who_left_is_someone(self):
        self.assertEqual(lh.describe({**ev(1, "note"), "who": None, "user_id": None}, LA), "Someone added a note")


class UndoLineTests(unittest.TestCase):
    def test_what_putting_it_back_reads_like(self):
        self.assertEqual([lh.undo_text(ev(1, undone=True, **{"from": "new", "to": "won"})), lh.undo_text(ev(2, "call", outcome="no_answer", undone=True)),
                          lh.undo_text({**ev(3, undone=True, **{"from": "new", "to": "won"}), "undone_who": None})],
                         ["Eugene undid the move to Won", "Eugene took back the call", "Someone undid the move to Won"])


class UndoTests(unittest.TestCase):
    def plan(self, event, latest=None, user=EUGENE, now=NOW):
        return lh.undo_plan(event, latest if latest is not None else event["id"], user, now)

    def test_the_mover_can_put_a_stage_back_within_ten_minutes(self):
        e = ev(5, mins=9.9, **{"from": "new", "to": "contacted", "changed_before": "2026-11-11T17:00:00+00:00", "first_contact": True, "crm": ["contacted"]})
        self.assertEqual(self.plan(e), {"ok": True, "kind": "stage", "status": "new", "status_changed_at": "2026-11-11T17:00:00+00:00",
                                        "first_contact": True, "crm": ["contacted"], "to": "contacted"})

    def test_a_call_can_be_taken_back_even_after_a_later_stage_move(self):
        e = ev(7, "call", outcome="no_answer", first_contact=True)
        self.assertEqual(self.plan(e, latest=99), {"ok": True, "kind": "call", "first_contact": True})

    def test_what_cannot_be_undone(self):
        cases = {
            "late stage": (ev(5, mins=10, **{"from": "new", "to": "won"}), 5, EUGENE),
            "late call": (ev(5, "call", mins=10, outcome="reached"), 5, EUGENE),
            "someone else": (ev(5, **{"from": "new", "to": "won"}), 5, ANNA),
            "moved again": (ev(5, **{"from": "new", "to": "won"}), 6, EUGENE),
            "twice": (ev(5, undone=True, **{"from": "new", "to": "won"}), 5, EUGENE),
            "not undoable": (ev(5, "owner", to_id=ANNA), 5, EUGENE),
        }
        got = {k: self.plan(e, latest, user) for k, (e, latest, user) in cases.items()}
        self.assertEqual({k: (v["ok"], v["code"], v["error"]) for k, v in got.items()}, {
            "late stage": (False, 409, "Too late to undo: move it back by hand"),
            "late call": (False, 409, "Too late to undo: log another call instead"),
            "someone else": (False, 403, "Only the person who did it can undo it"),
            "moved again": (False, 409, "It has moved again since: move it back by hand"),
            "twice": (False, 409, "That was already undone"),
            "not undoable": (False, 400, "Only a call or a stage move can be undone"),
        })


class NeverPrunedTests(unittest.TestCase):
    def test_lead_history_and_bookings_are_never_pruned(self):
        self.assertFalse({"lead_events", "bookings"} & {t for t, _ in jobs.PRUNE})


if __name__ == "__main__":
    unittest.main()


class HistoryGapTests(unittest.TestCase):
    """History before the L1 backfill window was never copied: the lead page says so under History."""
    KEPT = datetime(2026, 5, 16, 21, 9, tzinfo=timezone.utc)  # 039 applied 2026-11-12, minus 180 days
    NY = ZoneInfo("America/New_York")

    def test_a_lead_older_than_the_window_gets_the_line(self):
        self.assertEqual(lh.gap_line(self.KEPT - timedelta(days=1), self.KEPT, self.NY), "History before May 16, 2026 was not kept.")

    def test_a_lead_inside_the_window_or_no_window_gets_nothing(self):
        self.assertEqual([lh.gap_line(self.KEPT, self.KEPT, self.NY), lh.gap_line(self.KEPT + timedelta(days=3), self.KEPT, self.NY),
                          lh.gap_line(self.KEPT - timedelta(days=1), None, self.NY)], [None, None, None])
