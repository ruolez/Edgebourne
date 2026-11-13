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
        self.assertEqual([(i["kind"], i["title"], i["by"], i["source"]) for i in got], [
            ("status", "Turned off", "Eugene", "console"),
            ("change", "Budget $20.00 → $31.00 a day", "Eugene", "console"),
            ("proposal", "Claude's suggestion accepted and applied: Raise the budget 20%", None, "claude"),
            ("status", "Approved · delivering", "Meta", "meta"),
        ])

    def test_failed_changes_say_who_refused(self):
        changes = [{"id": 9, "created_at": T, "action": "status", "old_value": "PAUSED", "new_value": "ACTIVE", "ok": False,
                    "error": "(#100) Invalid parameter", "user_name": "Eugene"},
                   {"id": 10, "created_at": T - timedelta(minutes=1), "action": "update_creative", "old_value": "1",
                    "new_value": "creative 2 not used", "ok": False, "error": "the words differ", "user_name": "Eugene"}]
        got = timeline.merge([], changes, [], money=str)
        self.assertEqual([(i["title"], i["tone"], i["sub"]) for i in got], [
            ("Tried to turn it on", "bad", "Meta refused: (#100) Invalid parameter"),
            ("Tried to update the ad", "bad", "Not applied: the words differ"),
        ])


def change(action, new, ok=True, old=None, **kw):
    return {"id": kw.pop("id", 1), "created_at": T, "action": action, "old_value": old, "new_value": new, "ok": ok,
            "user_name": "Eugene", **kw}


class CheckTests(unittest.TestCase):
    """D3: a change that has a "Did it work?" result carries it, and nothing else changes."""
    CHANGES = [{"id": 5, "created_at": T, "action": "budget", "old_value": "2000", "new_value": "2400", "ok": True, "user_name": "Eugene"},
               {"id": 6, "created_at": T - timedelta(hours=1), "action": "status", "old_value": "ACTIVE", "new_value": "PAUSED", "ok": True}]
    CHECK = {"state": "better", "sentence": "Worked: cost per lead $47 → $28 over 7 days (40% cheaper).", "ready_on": "2026-11-17", "worse": False}

    def merge(self, **kw):
        return timeline.merge([], [dict(c) for c in self.CHANGES], [], money=lambda c: f"${c / 100:.2f}", **kw)

    def test_only_the_checked_change_gets_its_result_and_id(self):
        got = self.merge(checks={5: self.CHECK})
        self.assertEqual([(i.get("change_id"), i.get("check")) for i in got], [(5, self.CHECK), (None, None)])

    def test_without_checks_the_items_are_unchanged(self):
        self.assertEqual(self.merge(), self.merge(checks={}))
        self.assertFalse(any("check" in i or "change_id" in i for i in self.merge()))


class TitleTests(unittest.TestCase):
    def title(self, c):
        return timeline.merge([], [c], [], money=str)[0]["title"]

    def test_ad_changes_read_as_sentences_without_meta_ids(self):
        cases = [
            (change("duplicate", "N3 - copy", old="N3"), "Duplicated as “N3 - copy”"),
            (change("update_creative", "New headline (creative 1789)"), "Updated the ad: New headline"),
            (change("restore_creative", "Back to version 1 (creative 1700)"), "Back to version 1"),
            (change("placement_media", "9:16 video 55 (creative 9)"), "Added a 9:16 video for Reels and Stories"),
            (change("enhancement", "Video filters off (creative 77)"), "Meta's automatic change: Video filters off"),
            (change("create", "N6"), "Created “N6”"),
            (change("rename", "N3 v2"), "Renamed to “N3 v2”"),
            (change("comment_reply", "Thanks!"), "Replied to a comment"),
            (change("comment_hide", None), "Hid a comment"),
            (change("comment_show", None), "Showed a comment again"),
            (change("recommendation", "Use Advantage+ placements"), "Applied Meta's advice: Use Advantage+ placements"),
        ]
        for c, want in cases:
            self.assertEqual(self.title(c), want, c["action"])
            self.assertNotRegex(self.title(c), r"creative \d")

    def test_failed_ad_changes_say_tried(self):
        self.assertEqual(self.title(change("update_creative", "New headline", ok=False, error="x")), "Tried to update the ad")
        self.assertEqual(self.title(change("placement_media", "9:16 video 5", ok=False, error="x")), "Tried to add a 9:16 video for Reels and Stories")
        self.assertEqual(self.title(change("restore_creative", "Back to version 1", ok=False, error="x")), "Tried to switch back to an earlier version")

    def test_an_unknown_action_still_reads_as_words(self):
        self.assertEqual(self.title(change("frobnicate_thing", "x")), "Frobnicate thing")


class AdviceTests(unittest.TestCase):
    """Meta's advice keeps what it changed, money included, in the account's money words."""
    MONEY = staticmethod(lambda cents: f"${cents / 100:,.2f}")

    def item(self, c):
        return timeline.merge([], [c], [], money=self.MONEY)[0]

    def test_a_budget_raise_keeps_its_amount(self):
        got = self.item(change("recommendation", "Spend more on a campaign that's doing well (+6.00/day)", old="2000"))
        self.assertEqual(got["title"], "Applied Meta's advice: Spend more on a campaign that's doing well (+$6.00 a day)")

    def test_refused_advice_says_tried(self):
        got = self.item(change("recommendation", "Spend more (+6.00/day)", ok=False, error="(#100) Invalid"))
        self.assertEqual((got["title"], got["sub"]), ("Tried to apply Meta's advice", "Meta refused: (#100) Invalid"))

    def test_a_budget_meta_set_differently_is_not_called_a_refusal(self):
        got = self.item(change("recommendation_check", "2600", old="2650", ok=False,
                               error="Meta set 26.00 a day, not the 26.50 shown"))
        self.assertEqual((got["title"], got["sub"]),
                         ("Meta's advice set a different budget than shown", "Meta set 26.00 a day, not the 26.50 shown"))


class LinkTests(unittest.TestCase):
    def test_changes_on_the_ad_set_or_campaign_name_and_link_where_they_happened(self):
        changes = [change("budget", "3100", old="2000", id=1, level="campaign", entity_id="c1", entity_name="Free intro call"),
                   change("status", "PAUSED", id=2, level="ad", entity_id="a1", entity_name="N3", created_at=T - timedelta(hours=1))]
        got = timeline.merge([], changes, [], money=str, subject="a1")
        self.assertEqual([i.get("on") for i in got], [{"level": "campaign", "id": "c1", "name": "Free intro call"}, None])

    def test_the_link_names_the_ad_set_or_campaign_not_what_the_row_stored(self):
        changes = [change("recommendation", "Spend more (+6.00/day)", id=1, level="campaign", entity_id="c1",
                          entity_name="Spend more on a campaign that's doing well"),
                   change("budget", "3100", old="2000", id=2, level="adset", entity_id="s1", entity_name="Old name")]
        got = timeline.merge([], changes, [], money=str, subject="a1", names={"c1": "Free intro call", "s1": "SoCal"})
        self.assertEqual([i["on"] for i in got], [{"level": "campaign", "id": "c1", "name": "Free intro call"},
                                                  {"level": "adset", "id": "s1", "name": "SoCal"}])

    def test_advice_without_a_known_name_never_uses_the_advice_as_the_name(self):
        got = timeline.merge([], [change("recommendation", "Spend more", level="campaign", entity_id="c9",
                                         entity_name="Spend more")], [], money=str, subject="a1")
        self.assertEqual(got[0]["on"], {"level": "campaign", "id": "c9", "name": None})

    def test_without_a_subject_nothing_is_marked_as_elsewhere(self):
        got = timeline.merge([], [change("budget", "3100", old="2000", level="campaign", entity_id="c1")], [], money=str)
        self.assertIsNone(got[0].get("on"))

    def test_a_change_made_by_accepting_a_suggestion_carries_it(self):
        got = timeline.merge([], [change("status", "PAUSED", proposal_id=12)], [], money=str)
        self.assertEqual(got[0]["proposal_id"], 12)

    def test_decided_suggestions_link_to_their_card_and_conversation(self):
        proposals = [{"id": 5, "task_id": 40, "decided_at": T, "title": "Pause N2", "status": "declined",
                      "entity_type": "adset", "entity_id": "s1", "entity_name": "SoCal"},
                     {"id": 6, "task_id": 41, "decided_at": None, "title": "Still waiting", "status": "pending"}]
        got = timeline.merge([], [], proposals, money=str, subject="a1")
        self.assertEqual([(i["title"], i["proposal_id"], i["task_id"], i["on"]) for i in got],
                         [("Claude's suggestion declined: Pause N2", 5, 40, {"level": "adset", "id": "s1", "name": "SoCal"})])

    def test_every_decided_state_reads_in_the_console_words(self):
        words = {}
        for status in ("applied", "approved", "declined", "failed", "revised", "unknown", "expired"):
            title = timeline.merge([], [], [{"id": 1, "decided_at": T, "title": "X", "status": status}], money=str)[0]["title"]
            self.assertTrue(title.startswith("Claude's suggestion ") and title.endswith(": X"), title)
            self.assertNotRegex(title, r"[Aa]pprov|\bidea\b|failed|unknown")
            words[status] = title[len("Claude's suggestion "):-len(": X")]
        self.assertEqual(words["approved"], "accepted")
        self.assertEqual(words["failed"], "accepted, but Meta refused")
        self.assertEqual(len(set(words.values())), len(words))



class StatusPairTests(unittest.TestCase):
    def test_one_switch_from_the_console_is_one_line(self):
        status = [{"id": 11, "at": T, "headline": "Delivering again", "source": "console", "by_name": "Eugene", "change_id": 7,
                   "field": "effective_status", "new_value": "ACTIVE"},
                  {"id": 10, "at": T, "headline": "Switched on", "source": "console", "by_name": "Eugene", "change_id": 7,
                   "field": "configured_status", "new_value": "ACTIVE"},
                  {"id": 9, "at": T - timedelta(hours=1), "headline": "Switched off", "source": "console", "by_name": "Eugene",
                   "change_id": 6, "field": "configured_status", "new_value": "PAUSED"},
                  {"id": 8, "at": T - timedelta(hours=1), "headline": "Turned off", "source": "console", "by_name": "Eugene",
                   "change_id": 6, "field": "effective_status", "new_value": "PAUSED"},
                  {"id": 5, "at": T - timedelta(hours=2), "headline": "Approved", "source": "webhook", "by_name": None,
                   "change_id": None, "field": "review", "new_value": None}]
        got = timeline.merge(status, [], [], money=str)
        self.assertEqual([(i["title"], i["sub"], i["by"], i["tone"]) for i in got], [
            ("Switched on", "Delivering again", "Eugene", "ok"),
            ("Switched off", "Turned off", "Eugene", ""),
            ("Approved", None, "Meta", "ok"),
        ])


class CheckedRefusalTests(unittest.TestCase):
    def test_a_suggestion_the_console_check_stopped_does_not_blame_meta(self):
        changes = [change("update_creative", "creative 2 not used", ok=False, error="the words differ", proposal_id=5)]
        proposals = [{"id": 5, "decided_at": T, "title": "Shorter headline", "status": "failed"}]
        got = [i for i in timeline.merge([], changes, proposals, money=str) if i["kind"] == "proposal"]
        self.assertEqual([(i["title"], i["tone"]) for i in got],
                         [("Claude's suggestion accepted, but not applied (the copy Meta stored didn't match): Shorter headline", "bad")])

    def test_a_suggestion_meta_refused_still_says_meta(self):
        changes = [change("budget", "3100", old="2000", ok=False, error="(#100) Invalid", proposal_id=5)]
        proposals = [{"id": 5, "decided_at": T, "title": "Raise", "status": "failed"}]
        got = [i for i in timeline.merge([], changes, proposals, money=str) if i["kind"] == "proposal"]
        self.assertEqual(got[0]["title"], "Claude's suggestion accepted, but Meta refused: Raise")


if __name__ == "__main__":
    unittest.main()


class OutsideEditTests(unittest.TestCase):
    """D2: budget, bid, date and audience changes made in Ads Manager, and the console's knowing yeses."""
    money = staticmethod(lambda c: f"${c / 100:.2f}")

    def event(self, **kw):
        base = {"id": 20, "at": T, "level": "campaign", "entity_id": "C", "entity_name": "Leads", "field": "daily_budget",
                "old_value": "2000", "new_value": "3000", "source": "poll", "by_name": None, "change_id": None, "detail": None,
                "headline": "Budget $20.00 → $30.00 a day"}
        base.update(kw)
        return base

    def test_an_outside_budget_change_is_by_ads_manager_in_the_money_category(self):
        got = timeline.merge([self.event()], [], [], money=self.money)
        self.assertEqual([(i["title"], i["by"], i["cat"], i["level"], i["entity_id"], i["entity_name"]) for i in got],
                         [("Budget $20.00 → $30.00 a day", "Ads Manager", "money", "campaign", "C", "Leads")])

    def test_a_known_person_outside_the_console_is_named(self):
        got = timeline.merge([self.event(detail={"actor": "Eugene R."})], [], [], money=self.money)
        self.assertEqual(got[0]["by"], "Eugene R.")

    def test_status_from_meta_is_still_by_meta(self):
        got = timeline.merge([self.event(field="effective_status", old_value="IN_PROCESS", new_value="ACTIVE", headline="Approved")],
                             [], [], money=self.money)
        self.assertEqual((got[0]["by"], got[0]["cat"]), ("Meta", "meta"))

    def test_a_change_confirmed_knowingly_says_which_warning(self):
        rows = [change("budget", "2600", old="2400", id=1, accepted=["recent"]),
                change("budget", "3200", old="2400", id=2, accepted=["big", "recent"]),
                change("budget", "3000", old="2400", id=3, accepted=["big"])]
        got = sorted(timeline.merge([], rows, [], money=self.money), key=lambda i: i["title"])
        self.assertEqual([(i["title"], i["sub"], i["tone"], i["cat"]) for i in got], [
            ("Budget $24.00 → $26.00 a day", "Confirmed knowingly: under 3 days since the last change", "", "money"),
            ("Budget $24.00 → $30.00 a day", "Confirmed knowingly: more than +20%", "", "money"),
            ("Budget $24.00 → $32.00 a day", "Confirmed knowingly: more than +20% and under 3 days since the last change", "", "money"),
        ])

    def test_a_new_version_is_an_edit(self):
        versions = [{"ad_id": "A", "ad_name": "N3", "number": 2, "label": "shorter hook", "started_at": T},
                    {"ad_id": "A", "ad_name": "N3", "number": 3, "label": None, "started_at": T - timedelta(hours=1)}]
        got = timeline.merge([], [], [], money=self.money, versions=versions, checks=None)
        self.assertEqual([(i["kind"], i["cat"], i["title"], i["level"], i["entity_id"]) for i in got],
                         [("version", "edit", "Version 2 started: shorter hook", "ad", "A"),
                          ("version", "edit", "Version 3 started", "ad", "A")])

    def test_switches_and_new_things_have_their_category(self):
        rows = [change("status", "PAUSED", old="ACTIVE", id=1), change("create", "N6", id=2), change("archive", "ARCHIVED", id=3)]
        self.assertEqual(sorted(i["cat"] for i in timeline.merge([], rows, [], money=self.money)), ["edit", "switch", "switch"])
