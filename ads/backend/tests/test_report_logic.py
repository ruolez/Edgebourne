import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import report_logic as rl

TODAY = date(2026, 11, 10)  # a Tuesday


class PeriodTests(unittest.TestCase):
    def test_last_complete_week_and_month_and_the_ones_before(self):
        self.assertEqual(rl.period("week", TODAY), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(rl.period("month", TODAY), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(rl.previous(date(2026, 11, 2), date(2026, 11, 8), "week"), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual(rl.previous(date(2026, 3, 1), date(2026, 3, 31), "month"), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_a_chosen_start_snaps_to_its_week_or_month(self):
        self.assertEqual(rl.period("week", TODAY, start=date(2026, 11, 5)), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(rl.period("month", TODAY, start=date(2026, 2, 14)), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_only_finished_periods_are_complete(self):
        self.assertEqual((rl.complete(date(2026, 11, 8), TODAY), rl.complete(date(2026, 11, 10), TODAY)), (True, False))


class FunnelTests(unittest.TestCase):
    """W2 / 00-PLAN C2: one list of steps, each rate a share of its base (the step before unless named)."""

    def test_rates_are_shares_of_the_step_before_and_name_their_base(self):
        self.assertEqual(rl.funnel([(rl.LEAD_STEP, 20), ("Contacted", 15), ("Qualified", 4), ("Won", 1)]),
                         [{"step": "Leads received", "n": 20, "rate": None, "of": None},
                          {"step": "Contacted", "n": 15, "rate": 75, "of": "Leads received"},
                          {"step": "Qualified", "n": 4, "rate": 27, "of": "Contacted"},
                          {"step": "Won", "n": 1, "rate": 25, "of": "Qualified"}])

    def test_nothing_to_convert_gives_no_rate(self):
        got = rl.funnel([(rl.LEAD_STEP, 0), ("Contacted", 0), ("Qualified", 0), ("Won", 0)])
        self.assertEqual([s["rate"] for s in got], [None, None, None, None])

    def test_nested_counts_never_give_a_rate_over_100(self):
        for a in range(7):
            for b in range(a + 1):
                for c in range(b + 1):
                    for d in range(c + 1):
                        rates = [s["rate"] for s in rl.funnel([(rl.LEAD_STEP, a), ("Contacted", b), ("Qualified", c), ("Won", d)])]
                        self.assertTrue(all(r is None or 0 <= r <= 100 for r in rates), (a, b, c, d, rates))

    def test_a_step_can_name_an_earlier_base(self):
        got = rl.funnel([(rl.LEAD_STEP, 10), ("Contacted", 8), ("Booked a call", 5, rl.LEAD_STEP), ("Qualified", 3, "Contacted"), ("Won", 1)])
        self.assertEqual([(s["rate"], s["of"]) for s in got],
                         [(None, None), (80, "Leads received"), (50, "Leads received"), (38, "Contacted"), (33, "Qualified")])

    def test_a_half_rounds_up(self):
        self.assertEqual(rl.funnel([(rl.LEAD_STEP, 8), ("Contacted", 1)])[1]["rate"], 13)

    def test_an_unknown_base_is_refused(self):
        with self.assertRaises(ValueError):
            rl.funnel([(rl.LEAD_STEP, 10), ("Qualified", 3, "Contacted")])


class LeadGapTests(unittest.TestCase):
    """Meta's count beside the leads that reached the console, in plain words (00-PLAN C3: "your leads list")."""

    def test_meta_counted_more(self):
        self.assertEqual(rl.lead_gap(20, 22), {"meta": 22, "received": 20, "diff": -2, "text":
                         "Meta counted 22 leads; 2 of them didn't reach your leads list. Meta can count a lead on the day the ad "
                         "was seen, and test entries are left out here."})
        self.assertTrue(rl.lead_gap(19, 20)["text"].startswith("Meta counted 20 leads; 1 of them didn't reach your leads list."))

    def test_the_list_has_more(self):
        self.assertEqual(rl.lead_gap(21, 20), {"meta": 20, "received": 21, "diff": 1, "text":
                         "Meta counted 20 leads; your leads list has 1 more (someone used the form outside an ad, or Meta counted it on another day)."})

    def test_meta_counted_none(self):
        self.assertEqual(rl.lead_gap(3, 0)["text"],
                         "Meta counted no leads from the ads; your leads list has 3 (from the form outside an ad, or not counted by Meta yet).")

    def test_agreeing_counts_say_nothing(self):
        self.assertEqual([rl.lead_gap(n, n) for n in (0, 1, 40)], [None, None, None])

    def test_one_lead_is_singular(self):
        self.assertTrue(rl.lead_gap(0, 1)["text"].startswith("Meta counted 1 lead; 1 of them didn't reach your leads list."))


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


class WhatWeDidTests(unittest.TestCase):
    """Console writes and changes made in Ads Manager in one dated list, worded like History (00-PLAN C14)."""

    CONSOLE = [{"day": date(2026, 11, 10), "created_at": at(10, 9), "level": "adset", "entity_name": "Broad", "action": "budget",
                "old_value": "2000", "new_value": "2400"}]
    OUTSIDE = [{"day": date(2026, 11, 9), "at": at(9, 18), "level": "ad", "entity_name": "N3", "field": "configured_status",
                "old_value": "ACTIVE", "new_value": "PAUSED"},
               {"day": date(2026, 11, 11), "at": at(11, 8), "level": "adset", "entity_name": "Broad", "field": "daily_budget",
                "old_value": "2400", "new_value": "3000"},
               {"day": date(2026, 11, 11), "at": at(11, 9), "level": "ad", "entity_name": "N4", "field": "learning",
                "old_value": "LEARNING", "new_value": "FAIL"}]

    def test_one_list_by_day_with_outside_rows_marked_and_unknown_fields_left_out(self):
        got = rl.what_we_did(self.CONSOLE, self.OUTSIDE)
        self.assertEqual([(i["day"].isoformat(), i["where"], i["text"]) for i in got],
                         [("2026-11-09", "outside", "Ad “N3”: turned off (in Ads Manager)"),
                          ("2026-11-10", "console", "Ad set “Broad”: budget $20.00 → $24.00 a day"),
                          ("2026-11-11", "outside", "Ad set “Broad”: budget $24.00 → $30.00 a day (in Ads Manager)")])

    def test_items_carry_level_name_and_the_words_after_the_name(self):
        self.assertEqual({k: v for k, v in rl.what_we_did(self.CONSOLE, [])[0].items() if k != "at"},
                         {"day": date(2026, 11, 10), "where": "console", "level": "adset", "name": "Broad",
                          "what": "budget $20.00 → $24.00 a day", "text": "Ad set “Broad”: budget $20.00 → $24.00 a day"})

    def test_same_day_rows_keep_their_time_order(self):
        console = [{"day": date(2026, 11, 9), "created_at": at(9, 20), "level": "ad", "entity_name": "N1", "action": "status",
                    "old_value": "PAUSED", "new_value": "ACTIVE"}]
        got = rl.what_we_did(console, self.OUTSIDE[:1])
        self.assertEqual([i["text"] for i in got], ["Ad “N3”: turned off (in Ads Manager)", "Ad “N1”: turned on"])

    def test_money_in_the_account_currency_and_other_console_actions_in_plain_words(self):
        console = [dict(self.CONSOLE[0]), {"day": date(2026, 11, 10), "created_at": at(10, 10), "level": "ad", "entity_name": "N2",
                                           "action": "update_creative", "old_value": None, "new_value": None},
                   {"day": date(2026, 11, 10), "created_at": at(10, 11), "level": "ad", "entity_name": "N5",
                    "action": "something_new", "old_value": None, "new_value": None}]
        self.assertEqual([i["text"] for i in rl.what_we_did(console, [], currency="EUR")],
                         ["Ad set “Broad”: budget €20.00 → €24.00 a day", "Ad “N2”: new version put on the ad", "Ad “N5”: something new"])


class EmailTests(unittest.TestCase):
    R = {"account": "Burdanova", "kind": "week", "start": "2026-11-09", "headline": "Cost per lead was $5.00. 18 leads from $90.00 spent."}
    LINK = "https://x/report.html?t=T"

    def test_greeting_note_headline_link(self):
        self.assertEqual(rl.email_text(self.R, "Masha", self.LINK, "N3 was turned off."),
                         ("Burdanova: your ads report, Week of Nov 9",
                          "Hi Masha,\n\nN3 was turned off.\n\nCost per lead was $5.00. 18 leads from $90.00 spent.\n\n"
                          "The full report: https://x/report.html?t=T\n(The link works for 90 days.)"))

    def test_no_name_and_no_note(self):
        self.assertTrue(rl.email_text(self.R, None, self.LINK, None)[1].startswith("Hi,\n\nCost per lead"))
        self.assertTrue(rl.email_text(self.R, "Masha", self.LINK, "   ")[1].startswith("Hi Masha,\n\nCost per lead"))

    def test_a_second_round_is_marked_updated_and_months_say_month(self):
        self.assertEqual(rl.email_text(self.R, "Masha", self.LINK, None, round_=2)[0], "Burdanova: your ads report, Week of Nov 9 (updated)")
        self.assertEqual(rl.email_text({**self.R, "kind": "month", "start": "2026-10-01"}, "Masha", self.LINK, None)[0],
                         "Burdanova: your ads report, Month of Oct 1")


LA = ZoneInfo("America/Los_Angeles")


def la(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=LA)


class SendTimeTests(unittest.TestCase):
    def test_the_next_8_am_today_or_tomorrow(self):
        self.assertEqual(rl.next_send_at(la(2026, 11, 16, 7, 59)), la(2026, 11, 16, 8))
        self.assertEqual(rl.next_send_at(la(2026, 11, 16, 8)), la(2026, 11, 17, 8))

    def test_across_the_end_of_summer_time(self):
        got = rl.next_send_at(la(2026, 10, 31, 21))
        self.assertEqual((got.astimezone(timezone.utc), got.utcoffset()), (datetime(2026, 11, 1, 16, tzinfo=timezone.utc), timedelta(hours=-8)))

    def test_who_it_goes_to(self):
        self.assertEqual([rl.who_label([]), rl.who_label(["a@x.com"]), rl.who_label(["a@x.com", "b@y.com"]),
                          rl.who_label(["a@x.com", "b@y.com", "c@z.com"])],
                         ["nobody yet", "a@x.com", "a@x.com and b@y.com", "a@x.com and 2 others"])


MON_7 = la(2026, 11, 16, 7)
MON_9 = la(2026, 11, 16, 9)
ONE = ["a@x.com"]


class ReviewStateTests(unittest.TestCase):
    """What the review bar on Reports says and offers, one case per situation."""

    def state(self, row=None, mode="wait", recipients=ONE, mail=True, complete=True, auto_at=None, now=MON_9):
        return rl.review_state(row, mode, recipients, mail, complete, auto_at, now)

    def test_waiting_for_review(self):
        self.assertEqual(self.state(), {"status": "waiting", "pill": ["warn", "Waiting for you"],
                                        "line": "Nothing goes to a@x.com until you press Send.",
                                        "actions": ["send_now", "send_later", "skip"], "later_label": "Send tomorrow at 8 AM"})
        self.assertEqual(self.state({"status": "waiting"}, mode="auto", now=MON_7)["later_label"], "Send at 8 AM")

    def test_sent_by_itself_at_8(self):
        self.assertEqual(self.state(mode="auto", auto_at=la(2026, 11, 16, 8), now=MON_7),
                         {"status": "auto", "pill": ["info", "Goes out at 8:00 AM"],
                          "line": "It goes to a@x.com at 8:00 AM without your review. Hold it to read it first.",
                          "actions": ["send_now", "hold"], "later_label": "Send at 8 AM"})

    def test_auto_mode_with_nothing_due_was_not_emailed(self):
        got = self.state(mode="auto")
        self.assertEqual((got["pill"], got["line"], got["actions"]), (["", "Not sent"], "This one wasn't emailed.", ["send_now", "send_later"]))

    def test_nothing_to_offer_before_the_end_without_clients_or_mail(self):
        self.assertEqual([(s["pill"], s["line"], s["actions"]) for s in
                          (self.state(complete=False), self.state(recipients=[]), self.state(mail=False))],
                         [(["", "Not finished yet"], "You can send it once the week is over.", []),
                          (["", "No clients yet"], "No clients on this account yet: add them on the Team page.", []),
                          (["bad", "Email isn't set up"], "Email isn't set up yet: Settings → Email.", [])])

    def test_scheduled_sending_sent_skipped(self):
        sched = self.state({"status": "scheduled", "send_at": la(2026, 11, 17, 8)})
        self.assertEqual((sched["pill"], sched["line"], sched["actions"]),
                         (["info", "Goes out Tue, Nov 17, 8:00 AM"], "To a@x.com.", ["send_now", "hold", "skip"]))
        sending = self.state({"status": "sending", "sent_to": ["a@x.com"]}, recipients=["a@x.com", "b@y.com"])
        self.assertEqual((sending["pill"], sending["line"], sending["actions"]), (["info", "Sending…"], "1 of 2 sent.", []))
        sent = self.state({"status": "sent", "sent_at": la(2026, 11, 16, 8, 14), "sent_to": ["a@x.com"], "snapshot": {"round": 1}}, recipients=[])
        self.assertEqual((sent["pill"], sent["line"], sent["actions"]),
                         (["ok", "Sent Mon, Nov 16, 8:14 AM"], "To a@x.com. Clients see it as it was sent.", ["view_sent", "send_again"]))
        skipped = self.state({"status": "skipped"})
        self.assertEqual((skipped["pill"], skipped["line"], skipped["actions"]), (["", "Not sending"], "You chose not to send this one.", ["undo_skip"]))

    def test_a_month_says_month(self):
        self.assertEqual(rl.review_state(None, "wait", ONE, True, False, None, MON_9, kind="month")["line"],
                         "You can send it once the month is over.")

    def test_send_now_reads_sending_once_its_time_has_come(self):
        due = self.state({"status": "scheduled", "send_at": MON_9 - timedelta(seconds=1), "sent_to": []})
        later = self.state({"status": "scheduled", "send_at": MON_9 + timedelta(minutes=1), "sent_to": []})
        self.assertEqual((due["status"], due["pill"], due["line"], due["actions"], later["status"]),
                         ("sending", ["info", "Sending…"], "0 of 1 sent.", [], "scheduled"))

    def test_wait_mode_waits_only_for_the_newest_period_that_gets_emailed(self):
        older = rl.review_state(None, "wait", ONE, True, True, None, MON_9, emailing=True, newest=False)
        not_emailed = rl.review_state(None, "wait", ONE, True, True, None, MON_9, emailing=False, newest=True)
        held = rl.review_state({"status": "waiting"}, "wait", ONE, True, True, None, MON_9, emailing=False, newest=False)
        self.assertEqual([(s["status"], s["pill"], s["line"], s["actions"]) for s in (older, not_emailed)],
                         [("not_sent", ["", "Not sent"], "This one wasn't emailed.", ["send_now", "send_later"])] * 2)
        self.assertEqual(held["status"], "waiting")

    def test_a_period_sent_before_review_existed_has_no_copy_to_open(self):
        old = self.state({"status": "sent", "sent_at": None, "sent_to": [], "snapshot": None})
        self.assertEqual((old["pill"], old["line"], old["actions"]),
                         (["ok", "Sent"], "Sent before review was added; no copy was kept.", ["send_again"]))


class IdeaLeadsTests(unittest.TestCase):
    """The report's ideas count one set of people: the console's leads per ad, summed by idea (never Meta's count)."""

    def test_received_and_qualified_are_summed_per_idea_from_the_console(self):
        rows = [{"id": "a1", "received": 3, "qualified": 1}, {"id": "a2", "received": 2, "qualified": 2},
                {"id": "a3", "received": 4, "qualified": 0}, {"id": "a4", "received": 0, "qualified": 0}]
        tags = {"a1": {"hook": "Price"}, "a2": {"hook": "Price"}, "a3": {"hook": "Speed", "angle": "Fear"}}
        self.assertEqual(rl.idea_leads(rows, tags, "hook", "Not tagged"),
                         {"Price": {"received": 5, "qualified": 3}, "Speed": {"received": 4, "qualified": 0},
                          "Not tagged": {"received": 0, "qualified": 0}})

    def test_qualified_never_exceeds_received(self):
        rows = [{"id": f"a{i}", "received": r, "qualified": min(q, r)} for i, (r, q) in enumerate([(0, 0), (1, 1), (5, 2), (2, 9)])]
        tags = {r["id"]: {"hook": "H" if i % 2 else "G"} for i, r in enumerate(rows)}
        for idea in rl.idea_leads(rows, tags, "hook", "Not tagged").values():
            self.assertLessEqual(idea["qualified"], idea["received"])


class VisibilityTests(unittest.TestCase):
    def test_a_client_of_an_account_that_does_not_email_this_report_reads_it_live(self):
        self.assertEqual([rl.client_can_open("wait", None, emailing=False), rl.client_can_open("wait", {"status": "waiting"}, emailing=False),
                          rl.client_can_open("wait", None, emailing=True)], [True, True, False])

    def test_who_can_open_a_period_and_when_the_note_shows(self):
        self.assertEqual([rl.client_can_open("wait", None), rl.client_can_open("wait", {"status": "waiting"}),
                          rl.client_can_open("wait", {"status": "sent"}), rl.client_can_open("auto", None),
                          rl.client_can_open("auto", {"status": "skipped"})], [False, False, True, True, True])
        self.assertEqual([rl.note_visible({"status": "waiting", "note": "x"}, True), rl.note_visible({"status": "waiting", "note": "x"}, False),
                          rl.note_visible({"status": "sent", "note": "x"}, False), rl.note_visible(None, False),
                          rl.note_visible({"status": "sent", "note": None}, True)], [True, False, True, False, False])


class ReviewAlertTests(unittest.TestCase):
    def test_the_inbox_item_for_a_waiting_report(self):
        self.assertEqual(rl.review_alert("Burdanova", "week", date(2026, 11, 9), ["masha@burdanova.com"]),
                         {"rule": "report_review", "key": "report_review:week:2026-11-09", "level": "warn",
                          "title": "Weekly report for Burdanova is waiting for you",
                          "lines": ["Week of Nov 9 · goes to masha@burdanova.com", "Read it, add a note if you like, then press Send."],
                          "href": "/report.html?kind=week&start=2026-11-09#review"})
        self.assertEqual(rl.review_alert("Burdanova", "month", date(2026, 10, 1), ONE)["title"], "Monthly report for Burdanova is waiting for you")


class ContentTests(unittest.TestCase):
    def test_footnotes_say_where_leads_come_from_and_when_a_copy_was_sent(self):
        notes = rl.footnotes(date(2026, 11, 2), date(2026, 11, 8), sent_on=date(2026, 11, 9))
        self.assertTrue(notes[0].startswith("Leads are the people who reached your leads list from the lead forms (test entries left out)"))
        self.assertEqual(notes[-1], "Figures as sent on Nov 9, 2026.")
        self.assertEqual(len(rl.footnotes(date(2026, 11, 2), date(2026, 11, 8))), len(notes) - 1)

    def test_headline_uses_qualified_leads_when_there_are_any_and_says_when_it_is_thin(self):
        h = rl.headline({"spend_cents": 14000, "leads": 30, "qualified": 2}, {"spend_cents": 14000, "leads": 25, "qualified": 1}, 6000)
        self.assertEqual(h, "Cost per qualified lead was $70.00 against the $60.00 target (over by $10.00), down from $140.00 the period before. "
                            "2 qualified leads from $140.00 spent; at this volume the number is directional.")

    def test_headline_is_written_in_the_account_currency(self):
        h = rl.headline({"spend_cents": 9000, "leads": 18, "qualified": 0}, {"spend_cents": 0, "leads": 0}, 6000, currency="EUR")
        self.assertEqual(h, "Cost per lead was €5.00 against the €60.00 target (under by €55.00). 18 leads from €90.00 spent.")

    def test_headline_falls_back_to_leads_and_to_spend(self):
        self.assertEqual(rl.headline({"spend_cents": 9000, "leads": 18, "qualified": 0}, {"spend_cents": 0, "leads": 0}),
                         "Cost per lead was $5.00. 18 leads from $90.00 spent.")
        self.assertEqual(rl.headline({"spend_cents": 500, "leads": 0, "qualified": 0}, {"spend_cents": 0, "leads": 0}),
                         "$5.00 spent and no leads yet. 0 leads from $5.00 spent.")

    def test_the_measurement_change_footnote_only_when_the_period_spans_it(self):
        self.assertEqual([len(rl.footnotes(date(2026, 11, 2), date(2026, 11, 8))), len(rl.footnotes(date(2026, 11, 9), date(2026, 11, 15)))], [2, 3])


class ShareTests(unittest.TestCase):
    def test_a_signed_link_round_trips_and_tampering_or_expiry_fails(self):
        t = rl.sign("s3cret", {"a": 2, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"})
        self.assertEqual(rl.verify("s3cret", t, TODAY), {"a": 2, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"})
        body, mac = t.rsplit(".", 1)
        forged = rl.sign("other", {"a": 1, "k": "week", "s": "2026-11-02", "exp": "2027-02-08"}).rsplit(".", 1)[0] + "." + mac
        self.assertEqual([rl.verify("wrong", t, TODAY), rl.verify("s3cret", forged, TODAY), rl.verify("s3cret", t, date(2027, 3, 1)),
                          rl.verify("s3cret", "garbage", TODAY)], [None, None, None, None])



class RecentPeriodsTests(unittest.TestCase):
    """The earlier-period picker on Reports: complete weeks or months, newest first, back to the first data."""

    def test_weeks_are_whole_mondays_to_sundays_back_to_back_newest_first(self):
        weeks = rl.recent_periods("week", TODAY, n=3)
        self.assertEqual(weeks, [(date(2026, 11, 2), date(2026, 11, 8)), (date(2026, 10, 26), date(2026, 11, 1)),
                                 (date(2026, 10, 19), date(2026, 10, 25))])

    def test_months_cross_february_and_the_year_end(self):
        months = rl.recent_periods("month", date(2026, 3, 4), n=4)
        self.assertEqual(months, [(date(2026, 2, 1), date(2026, 2, 28)), (date(2026, 1, 1), date(2026, 1, 31)),
                                  (date(2025, 12, 1), date(2025, 12, 31)), (date(2025, 11, 1), date(2025, 11, 30))])

    def test_every_offered_period_is_complete_and_the_first_is_the_default_report(self):
        for kind in ("week", "month"):
            got = rl.recent_periods(kind, TODAY, n=12)
            self.assertEqual(got[0], rl.period(kind, TODAY))
            self.assertEqual(len(got), 12)
            self.assertTrue(all(rl.complete(e, TODAY) for _, e in got))
            self.assertTrue(all((got[i][0] - got[i + 1][1]).days == 1 for i in range(len(got) - 1)))

    def test_it_stops_at_the_period_holding_the_first_day_with_data(self):
        self.assertEqual(rl.recent_periods("week", TODAY, since=date(2026, 10, 28)),
                         [(date(2026, 11, 2), date(2026, 11, 8)), (date(2026, 10, 26), date(2026, 11, 1))])
        self.assertEqual(rl.recent_periods("month", TODAY, since=date(2026, 9, 15)),
                         [(date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 9, 1), date(2026, 9, 30))])

    def test_an_account_newer_than_the_last_complete_period_still_gets_that_one(self):
        self.assertEqual(rl.recent_periods("week", TODAY, since=date(2026, 11, 9)), [(date(2026, 11, 2), date(2026, 11, 8))])


if __name__ == "__main__":
    unittest.main()
