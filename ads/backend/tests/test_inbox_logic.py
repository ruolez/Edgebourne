import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import diagnose
import inbox

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def alert(i, rule, mins, level="bad", campaign="c1"):
    return {"id": i, "rule": rule, "level": level, "title": f"t{i}", "lines": ["l"], "href": f"/ad.html?id=a{i}",
            "entity_id": f"a{i}", "campaign_id": campaign, "created_at": NOW - timedelta(minutes=mins), "resolved_at": None}


class CategoryTests(unittest.TestCase):
    def test_rules_land_in_plain_groups(self):
        self.assertEqual([inbox.category(r) for r in ("ad_rejected", "ad_approved", "learning_limited", "no_delivery",
                                                       "fatigue", "changed_outside", "spend_cap", "cpl_high", "tracking")],
                         ["status", "status", "status", "status", "status", "status", "money", "money", "system"])

    def test_lead_quality_alerts_are_about_leads(self):
        self.assertEqual([inbox.category(r) for r in ("qualified_low", "junk_high")], ["leads", "leads"])

    def test_d3_did_it_work_is_about_money(self):
        self.assertEqual(inbox.category("change_result"), "money")


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.alerts = [alert(1, "ad_rejected", 5), alert(2, "spend_cap", 600, "warn", None)]
        self.leads = [{"id": 9, "full_name": "Dana", "ad_name": "N4", "created_time": NOW - timedelta(minutes=3), "status": "new"}]
        self.proposals = [{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}]

    def test_newest_first_with_keys_and_unread(self):
        got = inbox.build(self.alerts, self.leads, self.proposals, read_keys={"alert:2"})
        self.assertEqual([(i["key"], i["category"], i["unread"]) for i in got],
                         [("lead:9", "leads", True), ("alert:1", "status", True), ("proposal:4", "claude", True),
                          ("alert:2", "money", False)])

    def test_a_fixed_problem_is_resolved_but_an_approval_is_not(self):
        fixed = dict(alert(1, "ad_rejected", 5), kind="condition", resolved_at=NOW)
        approved = dict(alert(2, "ad_approved", 4, "ok"), kind="event", resolved_at=NOW)
        got = inbox.build([fixed, approved], [], [], read_keys=set())
        self.assertEqual([(i["key"], i["resolved"]) for i in got], [("alert:2", False), ("alert:1", True)])

    def test_a_lead_no_longer_new_is_read(self):
        got = inbox.build([], [dict(self.leads[0], status="contacted")], [], read_keys=set())
        self.assertEqual([i["unread"] for i in got], [False])

    def test_filters(self):
        items = inbox.build(self.alerts, self.leads, self.proposals, read_keys={"alert:2"})
        self.assertEqual([i["key"] for i in inbox.pick(items, "unread", "all")], ["lead:9", "alert:1", "proposal:4"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "money")], ["alert:2"])
        self.assertEqual(inbox.counts(items), {"unread": 3, "status": 1, "leads": 1, "claude": 1, "money": 0, "system": 0,
                                               "need": 4, "need_unread": 3, "fyi": 0, "fyi_unread": 0})


class TriageTests(unittest.TestCase):
    """Needs action = open problems, open warn/bad events, waiting suggestions, leads nobody has tried. The rest is FYI."""

    def build(self, alerts=(), leads=(), proposals=(), read=()):
        return inbox.build(list(alerts), list(leads), list(proposals), set(read))

    def test_what_needs_a_person_and_what_is_for_information(self):
        items = self.build(
            alerts=[dict(alert(1, "ad_rejected", 5), kind="condition"),
                    dict(alert(2, "ad_rejected", 6), kind="condition", entity_id="a2b", resolved_at=NOW),
                    dict(alert(3, "ad_approved", 7, "ok"), kind="event", resolved_at=NOW),
                    dict(alert(4, "report_review", 8, "warn"), kind="event"),
                    dict(alert(5, "changed_outside", 9, "info"), kind="event"),
                    dict(alert(6, "learning_limited", 10, "warn"), kind="event", resolved_at=NOW)],
            leads=[{"id": 9, "full_name": "Dana", "ad_name": "N4", "created_time": NOW - timedelta(minutes=3), "status": "new", "first_contacted_at": None},
                   {"id": 8, "full_name": "Eli", "ad_name": "N4", "created_time": NOW - timedelta(minutes=4), "status": "new", "first_contacted_at": NOW},
                   {"id": 7, "full_name": "Fay", "ad_name": "N4", "created_time": NOW - timedelta(minutes=11), "status": "contacted", "first_contacted_at": NOW}],
            proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}])
        self.assertEqual({i["key"]: i["need"] for i in items},
                         {"alert:1": True, "alert:2": False, "alert:3": False, "alert:4": True, "alert:5": False, "alert:6": False,
                          "lead:9": True, "lead:8": False, "lead:7": False, "proposal:4": True})

    def test_the_same_problem_open_on_two_days_needs_action_once(self):
        items = self.build(alerts=[dict(alert(1, "spend_cap", 60 * 24, "warn", None), kind="condition", entity_id="account"),
                                   dict(alert(2, "spend_cap", 5, "warn", None), kind="condition", entity_id="account")])
        self.assertEqual([(i["key"], i["need"]) for i in items], [("alert:2", True)])

    def test_boxes_and_counts(self):
        items = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition"),
                                   dict(alert(3, "ad_approved", 7, "ok"), kind="event", resolved_at=NOW)],
                           proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW - timedelta(minutes=60), "entity_name": "Leads"}],
                           read={"proposal:4"})
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "all", "need")], ["alert:1", "proposal:4"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "all", "all", "fyi")], ["alert:3"])
        self.assertEqual([i["key"] for i in inbox.pick(items, "unread", "claude", "need")], [])
        got = inbox.counts(items)
        self.assertEqual({k: got[k] for k in ("unread", "need", "need_unread", "fyi", "fyi_unread")},
                         {"unread": 2, "need": 2, "need_unread": 1, "fyi": 1, "fyi_unread": 1})

    def test_a_problem_fixed_since_leaves_the_needs_action_count(self):
        open_ = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition")])
        fixed = self.build(alerts=[dict(alert(1, "ad_rejected", 5), kind="condition", resolved_at=NOW)])
        self.assertEqual([inbox.counts(open_)["need_unread"], inbox.counts(fixed)["need_unread"], inbox.counts(fixed)["unread"]], [1, 0, 1])

    def test_a_suggestion_names_itself_for_the_accept_sheet(self):
        items = self.build(proposals=[{"id": 4, "summary": "Raise budget", "created_at": NOW, "entity_name": "Leads"}])
        self.assertEqual(items[0]["proposal_id"], 4)


class SubjectTests(unittest.TestCase):
    def test_an_item_about_a_known_campaign_ad_set_or_ad_names_it_with_a_link_target(self):
        items = [{"key": "alert:1", "entity_id": "a1"}, {"key": "alert:2", "entity_id": "c1"},
                 {"key": "alert:3", "entity_id": "gone"}, {"key": "lead:9", "entity_id": None}]
        known = {"a1": {"level": "ad", "name": "N1 - pain"}, "c1": {"level": "campaign", "name": "Free intro call"}}
        got = inbox.with_subjects(items, known)
        self.assertEqual([i["subject"] for i in got], [{"level": "ad", "id": "a1", "name": "N1 - pain"},
                                                        {"level": "campaign", "id": "c1", "name": "Free intro call"}, None, None])


if __name__ == "__main__":
    unittest.main()


class OutsideEditTests(unittest.TestCase):
    """D2: an outside budget change that broke a money rule waits in Needs action until an admin says Done."""
    def ev(self, level, resolved=None):
        return {**alert(30, "outside_edit", 5, level), "kind": "event", "resolved_at": resolved}

    def test_a_warning_needs_action_and_admins_can_close_it(self):
        admin = inbox.build([self.ev("warn")], [], [], set(), can_close=True, now=NOW)[0]
        member = inbox.build([self.ev("warn")], [], [], set(), now=NOW)[0]
        self.assertEqual((admin["category"], admin["need"], admin["actions"], member["actions"]), ("money", True, ["diagnose", "done"], []))

    def test_a_note_and_a_closed_warning_are_for_information(self):
        # Nothing to close; Claude can still look into them for 3 days (W1).
        got = inbox.build([self.ev("info", NOW), {**self.ev("warn", NOW), "id": 31}], [], [], set(), can_close=True, now=NOW)
        self.assertEqual([(i["need"], i["actions"]) for i in got], [(False, ["diagnose"]), (False, ["diagnose"])])


DAY = timedelta(days=1)


def cond(i, rule, created, level="warn", entity="c1", **kw):
    return {"id": i, "rule": rule, "level": level, "title": f"t{i}", "lines": ["l"], "href": "/performance.html", "entity_id": entity,
            "campaign_id": "c1", "created_at": created, "resolved_at": None, "kind": "condition", "measure": None, "quiet": False, **kw}


class ChangeResultTests(unittest.TestCase):
    """D3: "didn't help" waits in Needs action until put back or Done; good and flat results are FYI."""
    def ev(self, level, resolved=None):
        return {**alert(40, "change_result", 5, level), "kind": "event", "resolved_at": resolved}

    def test_didnt_help_needs_action_with_done_and_diagnose(self):
        got = inbox.build([self.ev("warn")], [], [], set(), can_close=True, now=NOW)[0]
        self.assertEqual((got["category"], got["need"], got["actions"]), ("money", True, ["diagnose", "done"]))

    def test_worked_is_for_information(self):
        got = inbox.build([self.ev("info", NOW)], [], [], set(), can_close=True, now=NOW)[0]
        self.assertEqual((got["need"], got["actions"]), (False, ["diagnose"]))


class SnoozeAndDiagnoseTests(unittest.TestCase):
    """W1: one item per problem, quiet rows, snoozes in FYI, and what each person may do with an alert."""
    NOV9 = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    NOV10 = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    SNOOZED = {"id": 3, "mode": "worse", "until": None, "by": "Eugene", "words": "Snoozed until it gets worse"}

    def build(self, alerts, proposals=(), read=(), **kw):
        return inbox.build(list(alerts), [], list(proposals), set(read), now=NOW, **kw)

    def test_a_problem_open_for_days_is_one_item_keyed_by_its_newest_row(self):
        # Whole days since the first row, the way the Diagnose request counts them: Nov 9 → Nov 10 is 1 day.
        got = self.build([cond(10, "cpl_high", self.NOV9), cond(14, "cpl_high", self.NOV10)])
        self.assertEqual([(i["key"], i["since"], i["days_open"], i["since_day"], i["need"]) for i in got],
                         [("alert:14", self.NOV9, 1, "Nov 9", True)])

    def test_the_item_lists_every_row_it_stands_for(self):
        """A link to an older row of the episode (a diagnosis's 'From an alert') still finds the item."""
        got = self.build([cond(8, "cpl_high", self.NOV9 - 3 * DAY, resolved_at=self.NOV9), cond(9, "cpl_high", self.NOV9 - 2 * DAY, resolved_at=self.NOV9),
                          cond(10, "cpl_high", self.NOV9), cond(14, "cpl_high", self.NOV10)])
        self.assertEqual([(i["key"], i["ids"]) for i in got], [("alert:14", [14, 10]), ("alert:9", [9, 8])])

    def test_days_open_count_in_the_accounts_time_zone_against_today(self):
        """03:00 UTC on Nov 10 is the evening of Nov 9 in Los Angeles; on Nov 12 the problem is 3 days old,
        not counted up to its newest row and not by UTC dates."""
        la = ZoneInfo("America/Los_Angeles")
        first = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
        got = inbox.build([cond(10, "cpl_high", first), cond(14, "cpl_high", self.NOV10)], [], [], set(), now=now, now_local=now.astimezone(la))
        self.assertEqual((got[0]["days_open"], got[0]["since_day"]), (3, "Nov 9"))

    def test_the_inbox_and_the_diagnose_request_say_the_same_number_of_days(self):
        la = ZoneInfo("America/Los_Angeles")
        now = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
        rows = [cond(10, "no_leads", self.NOV9, "bad"), cond(14, "no_leads", self.NOV10, "bad")]
        item = inbox.build(rows, [], [], set(), now=now, now_local=now.astimezone(la))[0]
        ctx = diagnose.context(rows[1], {}, item["since"])
        text = diagnose.prompt(ctx, diagnose.playbook("no_leads"), la, now)
        self.assertEqual((item["days_open"], f"Open since {item['since_day']} ({item['days_open']} days)." in text), (3, True))

    def test_an_earlier_episode_that_cleared_keeps_its_newest_row(self):
        got = self.build([cond(8, "cpl_high", self.NOV9 - 3 * DAY, resolved_at=self.NOV9), cond(9, "cpl_high", self.NOV9 - 2 * DAY, resolved_at=self.NOV9),
                          cond(14, "cpl_high", self.NOV10)])
        self.assertEqual([(i["key"], i["need"]) for i in got], [("alert:14", True), ("alert:9", False)])

    def test_a_quiet_row_is_never_new(self):
        got = self.build([cond(14, "cpl_high", self.NOV10, quiet=True)])
        self.assertEqual((got[0]["unread"], inbox.counts(got)["unread"]), (False, 0))

    def test_a_snoozed_problem_is_for_information_with_its_chip(self):
        got = self.build([cond(14, "cpl_high", self.NOV10)], snoozes={("cpl_high", "c1"): self.SNOOZED})
        self.assertEqual((got[0]["need"], got[0]["snooze"]["words"], inbox.counts(got)["need"]), (False, "Snoozed until it gets worse", 0))

    def test_what_an_admin_may_do(self):
        run = {"id": 5, "status": "queued", "waiting": 0}
        open_, snoozed, red_money = (self.build([cond(14, "cpl_high", self.NOV10)], can_close=True, runs={"cpl_high:c1": run}),
                                     self.build([cond(14, "cpl_high", self.NOV10)], can_close=True, snoozes={("cpl_high", "c1"): self.SNOOZED}),
                                     self.build([cond(15, "no_leads", self.NOV10, "bad")], can_close=True))
        self.assertEqual([(i[0]["actions"], [c["label"] for c in i[0].get("choices", [])], i[0].get("diagnose")) for i in (open_, snoozed, red_money)],
                         [(["snooze", "diagnose"], ["In 3 days", "Only if it gets worse"], run), (["wake", "diagnose"], [], None),
                          (["snooze", "diagnose"], ["Remind me tomorrow"], None)])

    def test_a_teammate_sees_the_chip_and_no_buttons(self):
        got = self.build([cond(14, "cpl_high", self.NOV10)], snoozes={("cpl_high", "c1"): self.SNOOZED}, runs={"cpl_high:c1": {"id": 5}})
        self.assertEqual((got[0]["actions"], got[0]["snooze"]["by"], "diagnose" in got[0], "choices" in got[0]), ([], "Eugene", False, False))

    def test_a_client_sees_none_of_it(self):
        got = self.build([cond(14, "ad_rejected", self.NOV10, "bad")], snoozes={("ad_rejected", "c1"): self.SNOOZED}, client=True)
        self.assertEqual([k for k in ("snooze", "diagnose", "actions", "choices") if k in got[0]], [])

    def test_claude_looks_into_a_cleared_alert_for_three_days(self):
        got = [self.build([cond(14, "cpl_high", NOW - 5 * DAY, resolved_at=NOW - d * DAY)], can_close=True)[0]["actions"] for d in (2, 4)]
        self.assertEqual(got, [["diagnose"], []])

    def test_alerts_claude_cannot_look_into_offer_no_diagnosis(self):
        got = self.build([cond(14, "tracking", self.NOV10, "bad", "account"), cond(15, "stale_data", self.NOV10, "warn", "account")], can_close=True)
        self.assertEqual([("diagnose" in i["actions"]) for i in got], [False, False])

    def test_a_suggestion_from_a_diagnosis_says_which_alert_it_answers(self):
        got = self.build([], proposals=[{"id": 4, "summary": "Pause N3", "created_at": NOW, "entity_name": "N3",
                                         "alert_title": "No leads for 5 days in “Leads”"}])
        self.assertEqual(got[0]["lines"], ["From: No leads for 5 days in “Leads”"])


class NumbersOffTests(unittest.TestCase):
    """D1: our numbers differing from Ads Manager is a system item; one night is FYI, two in a row need action."""

    def test_category(self):
        self.assertEqual(inbox.category("numbers_off"), "system")

    def test_info_is_for_information_and_warn_needs_action(self):
        rows = [dict(alert(1, "numbers_off", 5, "info"), kind="condition", entity_id="account"),
                dict(alert(2, "numbers_off", 5, "warn"), kind="condition", entity_id="account2")]
        got = {i["key"]: i["need"] for i in inbox.build(rows, [], [], set())}
        self.assertEqual(got, {"alert:1": False, "alert:2": True})


class SpendLimitMismatchTests(unittest.TestCase):
    def test_money_needs_action_and_never_snoozable(self):
        import snooze
        a = {"rule": "spend_limit_mismatch", "level": "bad", "kind": "event", "resolved_at": None, "entity_id": "account"}
        self.assertEqual((inbox.category("spend_limit_mismatch"), inbox._alert_needs(a), snooze.choices(a)), ("money", True, []))


class DraftsTests(unittest.TestCase):
    """AM-B: drafts read from Ads Manager are notes for the owner and account admins, never something that needs action."""

    def test_category_and_both_kinds_are_for_information(self):
        rows = [dict(alert(1, "draft_new", 5, "info"), kind="event", entity_id="900", campaign_id=None),
                dict(alert(2, "draft_problems", 5, "info"), kind="condition", entity_id="901", campaign_id=None)]
        got = {i["key"]: (i["category"], i["need"], i["actions"]) for i in inbox.build(rows, [], [], set(), can_close=True)}
        self.assertEqual(got, {"alert:1": ("status", False, []), "alert:2": ("status", False, [])})

    def test_clients_never_get_them(self):
        self.assertEqual(sorted(inbox.ADMIN_ONLY), ["draft_new", "draft_problems"])
