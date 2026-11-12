import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import followup as fu

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 11, 18, 20, tzinfo=timezone.utc)  # Wed 10:20 AM in Los Angeles
UTC = timezone.utc


def la(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=LA)


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def calls(outcomes, undone=()):
    return [{"kind": "call", "outcome": o, "at": NOW + timedelta(minutes=i), "undone_at": NOW if i in undone else None}
            for i, o in enumerate(outcomes)]


def lead(i=1, status="contacted", **kw):
    base = {"id": i, "status": status, "is_test": False, "created_time": NOW - timedelta(days=1), "first_contacted_at": NOW - timedelta(hours=20),
            "next_step_kind": None, "next_step_text": None, "next_step_at": None, "meeting_at": None, "meeting_status": None,
            "booked_at": None, "status_changed_at": NOW - timedelta(days=1), "call_attempts": 0, "ever_reached": False}
    return {**base, **kw}


class DueAtTests(unittest.TestCase):
    def test_presets_in_the_account_time_zone(self):
        cases = [("later_today", la(2026, 11, 11, 10, 20), utc(2026, 11, 11, 22)),
                 ("later_today", la(2026, 11, 11, 16, 30), utc(2026, 11, 12, 17)),
                 ("later_today", la(2026, 11, 11, 14), utc(2026, 11, 12, 1)),
                 ("tomorrow_9", la(2026, 11, 11, 10, 20), utc(2026, 11, 12, 17)),
                 ("tomorrow_9", la(2026, 10, 31, 20), utc(2026, 11, 1, 17)),
                 ("in_3_days", la(2026, 11, 11, 10, 20), utc(2026, 11, 14, 17))]
        self.assertEqual([fu.due_at(p, now, LA) for p, now, _ in cases], [want for _, _, want in cases])

    def test_later_today_that_lands_exactly_at_six_stays_today(self):
        self.assertEqual(fu.due_at("later_today", la(2026, 11, 11, 15), LA), utc(2026, 11, 12, 2))

    def test_unknown_preset_is_refused(self):
        with self.assertRaises(fu.Problem):
            fu.due_at("next_year", NOW, LA)


class ParseLocalTests(unittest.TestCase):
    def test_a_local_time_becomes_utc(self):
        self.assertEqual(fu.parse_local("2026-11-13T14:00", LA, NOW), utc(2026, 11, 13, 22))

    def test_refusals_say_what_to_pick(self):
        got = []
        for value in ("2026-11-10T09:00", "2027-11-12T09:00", "tomorrow", None):
            try:
                fu.parse_local(value, LA, NOW)
                got.append(None)
            except fu.Problem as p:
                got.append((str(p), p.field))
        self.assertEqual(got, [("Pick a time from now on", "when"), ("Pick a date within a year", "when"),
                               ("Pick a date and time", "when"), ("Pick a date and time", "when")])


class CleanNextTests(unittest.TestCase):
    def problem(self, data):
        try:
            fu.clean_next(data, LA, NOW)
        except fu.Problem as p:
            return str(p), p.field
        return None

    def test_refusals(self):
        self.assertEqual([self.problem({"kind": "other", "text": "x" * 121, "preset": "tomorrow_9"}),
                          self.problem({"kind": "other", "text": "  ", "preset": "tomorrow_9"}),
                          self.problem({"kind": "lunch", "preset": "tomorrow_9"}),
                          self.problem({"kind": "call_back"})],
                         [("Keep it under 120 characters", "text"), ("Say what the next step is", "text"),
                          ("Pick a next step", "kind"), ("Pick when", "when")])

    def test_a_preset_or_an_exact_time(self):
        self.assertEqual([fu.clean_next({"kind": "proposal", "preset": "tomorrow_9"}, LA, NOW),
                          fu.clean_next({"kind": "other", "text": " Send the case study ", "at": "2026-11-13T14:00"}, LA, NOW)],
                         [{"kind": "proposal", "text": None, "at": utc(2026, 11, 12, 17)},
                          {"kind": "other", "text": "Send the case study", "at": utc(2026, 11, 13, 22)}])


class CleanMeetingTests(unittest.TestCase):
    def test_today_tomorrow_an_exact_time_or_not_sure_yet(self):
        self.assertEqual([fu.clean_meeting({"preset": "today", "time": "14:00"}, LA, NOW),
                          fu.clean_meeting({"preset": "tomorrow", "time": "09:30"}, LA, NOW),
                          fu.clean_meeting({"at": "2026-11-13T14:00"}, LA, NOW),
                          fu.clean_meeting({"unscheduled": True}, LA, NOW)],
                         [utc(2026, 11, 11, 22), utc(2026, 11, 12, 17, 30), utc(2026, 11, 13, 22), None])

    def test_a_time_today_that_has_passed_or_no_time_is_refused(self):
        got = []
        for data in ({"preset": "today", "time": "09:00"}, {"preset": "tomorrow"}, {"preset": "someday", "time": "09:00"}, {}):
            try:
                fu.clean_meeting(data, LA, NOW)
                got.append(None)
            except fu.Problem as p:
                got.append(str(p))
        self.assertEqual(got, ["Pick a time from now on", "Pick a time", "Pick when the call is", "Pick when the call is"])


class CallSummaryTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(fu.call_summary([]), {"attempts": 0, "unanswered_streak": 0, "ever_reached": False, "last_outcome": None, "last_call_at": None})
        self.assertEqual(fu.call_summary(calls(["no_answer", "voicemail", "reached", "no_answer"])),
                         {"attempts": 4, "unanswered_streak": 1, "ever_reached": True, "last_outcome": "no_answer", "last_call_at": NOW + timedelta(minutes=3)})

    def test_undone_calls_do_not_count(self):
        s = fu.call_summary(calls(["no_answer", "no_answer", "no_answer"], undone={1}))
        self.assertEqual((s["attempts"], s["unanswered_streak"]), (2, 2))

    def test_a_booked_call_counts_as_reached_and_a_wrong_number_does_not(self):
        self.assertEqual([fu.call_summary(calls(o))[k] for o, k in ((["wrong_number"], "unanswered_streak"), (["wrong_number"], "ever_reached"),
                                                                    (["no_answer", "booked"], "unanswered_streak"), (["no_answer", "booked"], "ever_reached"))],
                         [1, False, 0, True])

    def test_order_comes_from_the_time_not_the_list(self):
        evs = list(reversed(calls(["no_answer", "reached", "no_answer", "voicemail"])))
        self.assertEqual(fu.call_summary(evs)["unanswered_streak"], 2)


class FirstContactTests(unittest.TestCase):
    def test_the_earliest_call_email_or_stage_move(self):
        t = lambda m: NOW + timedelta(minutes=m)  # noqa: E731
        call = [{"kind": "call", "outcome": "no_answer", "at": t(5), "undone_at": None}]
        stage = [{"kind": "stage", "at": t(30), "details": {"from": "new", "to": "contacted"}, "undone_at": None}]
        self.assertEqual([fu.first_contact_at(call, stage, [t(2)]), fu.first_contact_at([], [], []),
                          fu.first_contact_at([{**call[0], "undone_at": t(6)}], [], []),
                          fu.first_contact_at([], [{**stage[0], "details": {"from": "contacted", "to": "new"}}], []),
                          fu.first_contact_at([], stage, [])],
                         [t(2), None, None, None, t(30)])


class LostSuggestionTests(unittest.TestCase):
    def test_after_three_tries_in_a_row(self):
        s = lambda streak, reached: {"unanswered_streak": streak, "ever_reached": reached}  # noqa: E731
        self.assertEqual([fu.lost_suggestion(s(3, False), "new"), fu.lost_suggestion(s(3, True), "contacted"),
                          fu.lost_suggestion(s(2, False), "new"), fu.lost_suggestion(s(5, False), "won"), fu.lost_suggestion(s(4, False), "lost"),
                          fu.lost_suggestion(s(3, True), "qualified")],
                         ["couldnt_reach", "went_quiet", None, None, None, None])


class MeetingStateTests(unittest.TestCase):
    def state(self, offset, **kw):
        l = lead(meeting_at=NOW + offset, meeting_status="scheduled", booked_at=NOW - timedelta(days=1), **kw)
        return fu.meeting_state(l, NOW)

    def test_by_time(self):
        self.assertEqual([self.state(timedelta(hours=3)), self.state(timedelta(minutes=30)), self.state(timedelta(minutes=-30)),
                          self.state(timedelta(minutes=-61))], ["upcoming", "soon", "soon", "check"])

    def test_moved_on_after_the_call_counts_as_held(self):
        self.assertEqual(self.state(timedelta(minutes=-61), status="qualified", status_changed_at=NOW - timedelta(minutes=10)), "held")

    def test_stored_states_and_no_time(self):
        self.assertEqual([fu.meeting_state(lead(meeting_status="scheduled"), NOW), fu.meeting_state(lead(meeting_status="no_show", meeting_at=NOW), NOW),
                          fu.meeting_state(lead(), NOW)], ["unscheduled", "no_show", None])


class MeetingWordsTests(unittest.TestCase):
    """The booked call's 'on' phrase reads after 'Did the call', 'No-show', 'Call … canceled' (review: 'on 11:57 AM')."""

    def on(self, at):
        return fu.state_for(lead(meeting_status="scheduled", meeting_at=at), NOW, LA)["meeting"]["on"]

    def test_today_reads_at_the_time_other_days_read_on_the_day(self):
        self.assertEqual([self.on(la(2026, 11, 11, 8, 30)), self.on(la(2026, 11, 10, 15)), self.on(la(2026, 11, 13, 9))],
                         ["at 8:30 AM", "on Tue 3 PM", "on Fri 9 AM"])

    def test_no_time_set_has_no_phrase(self):
        self.assertIsNone(fu.state_for(lead(meeting_status="scheduled"), NOW, LA)["meeting"]["on"])


class ChipTests(unittest.TestCase):
    def test_the_most_urgent_thing_first(self):
        cases = [
            lead(next_step_kind="call_back", next_step_at=NOW - timedelta(days=1), meeting_status="scheduled", meeting_at=NOW - timedelta(hours=3)),
            lead(next_step_kind="call_back", next_step_at=NOW - timedelta(hours=2)),
            lead(meeting_status="scheduled", meeting_at=NOW - timedelta(hours=3), booked_at=NOW - timedelta(days=2)),
            lead(next_step_kind="call_back", next_step_at=la(2026, 11, 11, 16)),
            lead(next_step_kind="other", next_step_text="Send the case study", next_step_at=la(2026, 11, 13, 9)),
            lead(meeting_status="scheduled", meeting_at=la(2026, 11, 13, 14), booked_at=NOW),
            lead(meeting_status="scheduled", booked_at=NOW),
            lead(status="new", call_attempts=2, ever_reached=False),
            lead(status="new"),
            lead(status="lost", next_step_kind="call_back", next_step_at=NOW - timedelta(hours=2)),
        ]
        self.assertEqual([fu.chip(c, NOW, LA) for c in cases], [
            {"tone": "warn", "text": "Overdue: Call back (Tue)"},
            {"tone": "warn", "text": "Overdue: Call back (8:20 AM)"},
            {"tone": "warn", "text": "Did the call happen?"},
            {"tone": "", "text": "Call back · 4 PM"},
            {"tone": "", "text": "Send the case study · Fri 9 AM"},
            {"tone": "", "text": "Call on Fri 2 PM"},
            {"tone": "", "text": "Call booked, time not set"},
            {"tone": "", "text": "Tried 2×"},
            None,
            None,
        ])


class QueueTests(unittest.TestCase):
    def test_buckets_in_order_each_lead_once_tests_left_out(self):
        leads = [
            lead(1, "new", created_time=NOW - timedelta(minutes=10), first_contacted_at=None),
            lead(2, "new", created_time=NOW - timedelta(hours=3), first_contacted_at=None),
            lead(3, next_step_kind="call_back", next_step_at=NOW - timedelta(hours=2)),
            lead(4, meeting_status="scheduled", meeting_at=NOW + timedelta(minutes=30), booked_at=NOW - timedelta(days=1)),
            lead(5, meeting_status="scheduled", meeting_at=NOW - timedelta(hours=2), booked_at=NOW - timedelta(days=1)),
            lead(6, "qualified", next_step_kind="proposal", next_step_at=NOW + timedelta(hours=4)),
            lead(7, is_test=True, next_step_kind="call_back", next_step_at=NOW - timedelta(hours=2)),
            lead(8, next_step_kind="call_back", next_step_at=NOW + timedelta(days=2)),
            lead(9, "lost", meeting_status="scheduled", meeting_at=NOW + timedelta(minutes=30)),
        ]
        got = fu.queue(list(reversed(leads)), NOW, LA)
        self.assertEqual([(r["id"], r["bucket"]) for r in got], [(1, 0), (4, 1), (2, 2), (3, 3), (5, 4), (6, 5)])

    def test_a_lead_waiting_for_a_first_call_with_an_overdue_step_shows_once_as_a_call(self):
        l = lead(1, "new", created_time=NOW - timedelta(hours=3), first_contacted_at=None, next_step_kind="call_back", next_step_at=NOW - timedelta(hours=1))
        self.assertEqual([(r["id"], r["bucket"], r["kind"]) for r in fu.queue([l], NOW, LA)], [(1, 2, "call")])

    def test_a_new_lead_with_a_booked_call_is_not_waiting(self):
        l = lead(1, "new", first_contacted_at=None, meeting_status="scheduled", meeting_at=NOW + timedelta(hours=5), booked_at=NOW)
        self.assertEqual(fu.queue([l], NOW, LA), [])

    def test_oldest_first_inside_a_bucket(self):
        a = lead(1, next_step_kind="call_back", next_step_at=NOW - timedelta(hours=1))
        b = lead(2, next_step_kind="call_back", next_step_at=NOW - timedelta(hours=5))
        self.assertEqual([r["id"] for r in fu.queue([a, b], NOW, LA)], [2, 1])


class CallStatsTests(unittest.TestCase):
    def test_talked_counts_reached_and_booked(self):
        rows = [{"outcome": o, "undone": False} for o in ("reached", "no_answer", "no_answer", "booked", "voicemail")] + [{"outcome": "reached", "undone": True}]
        self.assertEqual([fu.call_stats(rows), fu.call_stats([])],
                         [{"calls": 5, "talked": 2, "rate": 40, "booked": 1}, {"calls": 0, "talked": 0, "rate": None, "booked": 0}])


class ReminderDueTests(unittest.TestCase):
    def test_from_the_due_time_for_a_day_on_open_leads(self):
        l = lead(next_step_kind="call_back", next_step_at=NOW)
        cases = [(l, NOW - timedelta(minutes=1)), (l, NOW), (l, NOW + timedelta(hours=23, minutes=59)), (l, NOW + timedelta(hours=24)),
                 ({**l, "status": "lost"}, NOW), ({**l, "is_test": True}, NOW), (lead(), NOW)]
        self.assertEqual([fu.reminder_due(x, at) for x, at in cases], [False, True, True, False, False, False, False])


class PresetLabelTests(unittest.TestCase):
    def test_each_button_says_its_time(self):
        self.assertEqual({k: v["label"] for k, v in fu.presets(NOW, LA).items()},
                         {"later_today": "Later today (2 PM)", "tomorrow_9": "Tomorrow 9 AM", "in_3_days": "Sat, Nov 14 9 AM"})

    def test_late_in_the_day_later_today_says_tomorrow(self):
        self.assertEqual(fu.presets(utc(2026, 11, 12, 1), LA)["later_today"]["label"], "Later today (tomorrow 9 AM)")


class DigestTextTests(unittest.TestCase):
    AT8 = la(2026, 11, 11, 8).astimezone(UTC)

    def test_everything_for_the_day_in_one_message(self):
        waiting = [{"full_name": "Maria Lopez", "business_type": "Bakery", "created_time": self.AT8 - timedelta(hours=14)}]
        due = [{"full_name": "Tom Reed", "next_step_kind": "call_back", "next_step_text": None, "next_step_at": la(2026, 11, 10, 16)},
               {"full_name": "Sam Hill", "next_step_kind": "proposal", "next_step_text": None, "next_step_at": la(2026, 11, 11, 15)}]
        today = [{"full_name": "Ana Ruiz", "meeting_at": la(2026, 11, 11, 14)}]
        self.assertEqual(fu.digest_text(waiting, due, today, self.AT8, LA),
                         ("Today: 1 lead waiting for a first call, 2 follow-ups due, 1 booked call",
                          ["Maria Lopez, Bakery: waiting 14 h", "Call back Tom Reed: overdue since Tue", "Send a quote Sam Hill: due 3:00 PM",
                           "Call at 2:00 PM: Ana Ruiz"]))

    def test_parts_with_nothing_are_left_out_and_an_empty_day_sends_nothing(self):
        due = [{"full_name": n, "next_step_kind": "call_back", "next_step_text": None, "next_step_at": la(2026, 11, 11, 9)} for n in ("A", "B")]
        self.assertEqual([fu.digest_text([], due, [], self.AT8, LA)[0], fu.digest_text([], [], [], self.AT8, LA)],
                         ["Today: 2 follow-ups due", None])


class DueTextTests(unittest.TestCase):
    def test_the_reminder_for_a_follow_up(self):
        l = lead(full_name="Maria Lopez", business_type="Bakery", phone="+16195557788", next_step_kind="call_back",
                 next_step_at=la(2026, 11, 11, 15), last_outcome="no_answer", last_call_at=la(2026, 11, 10, 15, 10))
        self.assertEqual(fu.due_text(l, LA), ("Call back Maria Lopez: due 3:00 PM",
                                             ["Bakery", "Phone: (619) 555-7788", "Last try: no answer, Tue 3:10 PM"]))


if __name__ == "__main__":
    unittest.main()
