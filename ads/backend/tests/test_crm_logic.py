import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("WORKERS_ENABLED", "0")

import crm_events  # noqa: E402

LEAD_ID = "1234567890123456"
T0 = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


class StagesToSendTest(unittest.TestCase):
    def test_a_jump_ahead_fills_in_the_skipped_funnel_stages_in_order(self):
        self.assertEqual(crm_events.stages_to_send("won", {"new"}), ["contacted", "qualified", "won"])

    def test_lost_sends_only_itself_after_the_initial_lead(self):
        cases = [(set(), ["new", "lost"]), ({"new", "contacted"}, ["lost"])]
        for sent, expected in cases:
            self.assertEqual(crm_events.stages_to_send("lost", sent), expected, sent)

    def test_a_stage_already_sent_or_a_move_back_sends_nothing(self):
        cases = [("contacted", {"new", "contacted", "qualified"}), ("new", {"new"})]
        for stage, sent in cases:
            self.assertEqual(crm_events.stages_to_send(stage, sent), [], stage)

    def test_unknown_stage_sends_nothing(self):
        self.assertEqual(crm_events.stages_to_send("archived", set()), [])


class EventTimeTest(unittest.TestCase):
    def test_a_change_after_the_lead_keeps_its_own_time(self):
        changed = T0 + timedelta(hours=2)
        self.assertEqual(crm_events.event_time_for(changed, T0), changed)

    def test_never_at_or_before_the_lead_was_created(self):
        self.assertEqual(crm_events.event_time_for(T0 - timedelta(seconds=5), T0), T0 + timedelta(seconds=1))
        self.assertEqual(crm_events.event_time_for(T0, T0), T0 + timedelta(seconds=1))


class BuildEventTest(unittest.TestCase):
    def test_payload_matches_metas_conversion_leads_spec(self):
        payload, reason = crm_events.build_event(LEAD_ID, "qualified", T0)
        self.assertEqual((payload, reason), ({
            "event_name": "Qualified",
            "event_time": int(T0.timestamp()),
            "action_source": "system_generated",
            "user_data": {"lead_id": 1234567890123456},
            "custom_data": {"event_source": "crm", "lead_event_source": "Edge Bourne Ads Console"},
        }, None))

    def test_each_stage_has_its_own_event_name(self):
        names = [crm_events.build_event(LEAD_ID, s, T0)[0]["event_name"] for s in crm_events.STAGES]
        self.assertEqual(names, ["Lead", "Contacted", "Qualified", "Won", "Lost"])

    def test_missing_or_malformed_lead_id_is_skipped_with_a_reason(self):
        for bad in (None, "", "12345", "abc4567890123456", "123456789012345678"):
            payload, reason = crm_events.build_event(bad, "new", T0)
            self.assertIsNone(payload, bad)
            self.assertIn("Meta lead id", reason)


class TooOldTest(unittest.TestCase):
    def test_meta_takes_events_up_to_seven_days_old(self):
        cases = [(timedelta(days=6, hours=23), False), (timedelta(days=7, minutes=1), True), (timedelta(0), False)]
        for age, expected in cases:
            self.assertEqual(crm_events.too_old(T0 - age, T0), expected, age)


class RetryAtTest(unittest.TestCase):
    def test_backoff_grows_with_each_attempt(self):
        waits = [crm_events.retry_at(n, T0, T0, None) - T0 for n in (1, 2, 3, 4, 5, 6, 9)]
        self.assertEqual(waits, [timedelta(minutes=m) for m in (1, 5, 15, 60, 180, 360, 360)])

    def test_gives_up_on_a_lead_meta_rejects_or_after_a_day(self):
        cases = [(100, T0, T0), (None, T0 - timedelta(hours=25), T0)]
        for code, queued, now in cases:
            self.assertIsNone(crm_events.retry_at(1, queued, now, code), code)

    def test_keeps_trying_other_errors_within_the_day(self):
        self.assertEqual(crm_events.retry_at(1, T0 - timedelta(hours=23), T0, 10), T0 + timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main()
