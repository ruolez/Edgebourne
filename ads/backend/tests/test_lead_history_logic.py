import unittest
from datetime import datetime, timedelta, timezone

import lead_history as lh

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
EUGENE, ANNA = 1, 2


def ev(i, action="lead.status", mins=2, user=EUGENE, **details):
    return {"id": i, "at": NOW - timedelta(minutes=mins), "action": action, "user_id": user, "who": "Eugene" if user == EUGENE else "Anna",
            "actor": "user", "details": details}


class DescribeTests(unittest.TestCase):
    def test_each_line_reads_as_a_sentence(self):
        rows = [ev(1, "lead.received", actor="meta"), ev(2, **{"from": "new", "to": "contacted"}),
                ev(3, "lead.status_undone", **{"from": "contacted", "to": "new"}), ev(4, "lead.owner", owner_id=ANNA),
                ev(5, "lead.owner", owner_id=None), ev(6, "lead.reply", subject="Your intro call"),
                ev(7, "lead.reply_auto", subject="Thanks"), ev(8, "lead.email_failed"), ev(9, "lead.something_new")]
        rows[0]["who"] = None
        rows[0]["actor"] = "meta"
        self.assertEqual([lh.describe(r, {ANNA: "Anna"}) for r in rows], [
            "Arrived from Meta",
            "Eugene moved it from New to Contacted",
            "Eugene undid the move to Contacted",
            "Eugene gave it to Anna",
            "Eugene took the owner off",
            "Eugene emailed them: Your intro call",
            "Automatic reply sent: Thanks",
            "The alert email to the team couldn't be sent",
            "Something new",
        ])

    def test_a_move_that_was_undone_says_so(self):
        self.assertEqual(lh.describe(ev(2, undone=True, **{"from": "new", "to": "won"}), {}), "Eugene moved it from New to Won (undone)")

    def test_an_owner_who_left_is_still_named_from_the_line(self):
        self.assertEqual(lh.describe(ev(4, "lead.owner", owner_id=9, owner_name="Sam"), {}), "Eugene gave it to Sam")


class UndoTests(unittest.TestCase):
    def plan(self, event, latest=None, user=EUGENE, now=NOW):
        return lh.undo_plan(event, latest if latest is not None else event["id"], user, now)

    def test_the_mover_can_put_it_back_within_ten_minutes(self):
        e = ev(5, mins=9.9, **{"from": "new", "to": "contacted", "changed_before": "2026-11-11T17:00:00+00:00", "first_contact": True, "crm": ["contacted"]})
        self.assertEqual(self.plan(e), {"ok": True, "status": "new", "status_changed_at": "2026-11-11T17:00:00+00:00",
                                        "clear_first_contact": True, "crm": ["contacted"], "to": "contacted"})

    def test_a_move_that_was_not_the_first_contact_keeps_the_contact_time(self):
        e = ev(5, **{"from": "contacted", "to": "qualified"})
        self.assertEqual({k: self.plan(e)[k] for k in ("status", "clear_first_contact", "crm", "status_changed_at")},
                         {"status": "contacted", "clear_first_contact": False, "crm": [], "status_changed_at": None})

    def test_what_cannot_be_undone(self):
        cases = {
            "late": (ev(5, mins=10, **{"from": "new", "to": "won"}), 5, EUGENE),
            "someone else": (ev(5, **{"from": "new", "to": "won"}), 5, ANNA),
            "moved again": (ev(5, **{"from": "new", "to": "won"}), 6, EUGENE),
            "twice": (ev(5, undone=True, **{"from": "new", "to": "won"}), 5, EUGENE),
            "not a stage": (ev(5, "lead.owner", owner_id=ANNA), 5, EUGENE),
        }
        got = {k: self.plan(e, latest, user) for k, (e, latest, user) in cases.items()}
        self.assertEqual({k: (v["ok"], v["code"]) for k, v in got.items()},
                         {"late": (False, 409), "someone else": (False, 403), "moved again": (False, 409), "twice": (False, 409), "not a stage": (False, 400)})
        self.assertEqual(got["late"]["error"], "Too late to undo: move it back by hand")


if __name__ == "__main__":
    unittest.main()
