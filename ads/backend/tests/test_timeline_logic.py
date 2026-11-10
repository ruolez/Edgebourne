import unittest
from datetime import datetime, timedelta, timezone

import timeline

T = datetime(2026, 11, 10, 17, 0, tzinfo=timezone.utc)


class MergeTests(unittest.TestCase):
    def test_one_list_newest_first_without_doubles(self):
        status = [{"id": 1, "at": T, "headline": "Turned off", "source": "console", "by_name": "Eugene", "change_id": 7,
                   "field": "effective_status", "new_value": "PAUSED"},
                  {"id": 2, "at": T - timedelta(hours=2), "headline": "Approved · delivering", "source": "webhook",
                   "by_name": None, "change_id": None, "field": "effective_status", "new_value": "ACTIVE"}]
        changes = [{"id": 7, "created_at": T, "action": "status", "old_value": "ACTIVE", "new_value": "PAUSED", "ok": True, "user_name": "Eugene"},
                   {"id": 8, "created_at": T - timedelta(hours=1), "action": "budget", "old_value": "2000", "new_value": "3100",
                    "ok": True, "user_name": "Eugene", "proposal_id": 5}]
        proposals = [{"id": 5, "decided_at": T - timedelta(hours=1, minutes=5), "title": "Raise the budget 20%", "status": "applied"}]
        got = timeline.merge(status, changes, proposals, money=lambda c: f"${c / 100:.2f}")
        self.assertEqual([(i["kind"], i["title"], i["by"]) for i in got], [
            ("status", "Turned off", "Eugene"),
            ("change", "Budget $20.00 → $31.00 a day", "Eugene"),
            ("proposal", "Claude's idea applied: Raise the budget 20%", None),
            ("status", "Approved · delivering", "Meta"),
        ])

    def test_failed_changes_say_so(self):
        changes = [{"id": 9, "created_at": T, "action": "status", "old_value": "PAUSED", "new_value": "ACTIVE", "ok": False,
                    "error": "Meta refused", "user_name": "Eugene"}]
        got = timeline.merge([], changes, [], money=str)
        self.assertEqual((got[0]["title"], got[0]["tone"], got[0]["sub"]), ("Tried to turn it on", "bad", "Meta refused"))


if __name__ == "__main__":
    unittest.main()
