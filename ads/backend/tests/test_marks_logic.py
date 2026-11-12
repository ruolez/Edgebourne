import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import marks

LA = ZoneInfo("America/Los_Angeles")
START, END = date(2026, 11, 1), date(2026, 11, 14)


def at(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)


def item(when, cat="money", title="Budget $20.00 → $24.00 a day", **kw):
    base = {"kind": "change", "at": when, "cat": cat, "title": title, "by": "Eugene", "source": "console",
            "level": "campaign", "entity_id": "C", "entity_name": "Leads", "field": "budget", "old": "2000", "new": "2400",
            "tone": ""}
    base.update(kw)
    return base


def status(when, field, old, new, entity="A", **kw):
    return item(when, cat="switch" if field == "configured_status" else "meta", title=f"{field} {new}", kind="status",
                field=field, old=old, new=new, entity_id=entity, level="ad", by="Meta", source="meta", **kw)


class ByDayTests(unittest.TestCase):
    def test_a_change_lands_on_the_account_day(self):
        got = marks.by_day([item(at(10, 6, 30))], LA, START, END)
        self.assertEqual([(d["day"], d["cats"], d["more"]) for d in got], [("2026-11-09", ["money"], 0)])

    def test_days_outside_the_range_are_dropped(self):
        self.assertEqual(marks.by_day([item(at(1, 6))], LA, START, END), [])  # Oct 31 in Los Angeles

    def test_money_first_then_by_time(self):
        got = marks.by_day([item(at(9, 17), cat="meta", title="Approved"), item(at(9, 23))], LA, START, END)
        self.assertEqual((got[0]["cats"], [i["title"] for i in got[0]["items"]]),
                         (["money", "meta"], ["Budget $20.00 → $24.00 a day", "Approved"]))

    def test_a_busy_day_shows_six_and_counts_the_rest(self):
        got = marks.by_day([item(at(9, 17, m)) for m in range(8)], LA, START, END)
        self.assertEqual((len(got[0]["items"]), got[0]["more"]), (6, 2))

    def test_items_carry_what_the_chart_needs(self):
        got = marks.by_day([item(at(9, 17))], LA, START, END)
        self.assertEqual(got[0]["items"], [{"cat": "money", "title": "Budget $20.00 → $24.00 a day", "by": "Eugene", "level": "campaign",
                                            "entity_id": "C", "entity_name": "Leads", "at": at(9, 17).isoformat(), "tone": "",
                                            "short": "budget raised"}])

    def test_a_suggestion_applied_here_says_so_but_never_to_clients(self):
        mine = [item(at(9, 17), proposal_id=5)]
        self.assertEqual([marks.by_day(mine, LA, START, END)[0]["items"][0]["title"],
                          marks.by_day(mine, LA, START, END, for_client=True)[0]["items"][0]["title"]],
                         ["Budget $20.00 → $24.00 a day (Claude's suggestion)", "Budget $20.00 → $24.00 a day"])

    def test_clients_never_see_a_persons_name(self):
        rows = [item(at(9, 17)), status(at(9, 18), "effective_status", "IN_PROCESS", "ACTIVE"),
                item(at(9, 19), by="Ads Manager", source="meta")]
        got = marks.by_day(rows, LA, START, END, for_client=True)
        self.assertEqual(sorted(i["by"] for i in got[0]["items"]), ["Ads Manager", "Meta", "Team"])


class LatestTests(unittest.TestCase):
    """The changes list under the charts: the newest changes of the period, not cut to six a day."""

    def test_a_busy_day_is_not_cut_to_six_in_the_list(self):
        busy = [item(at(12, 17, m), title=f"Change {m}") for m in range(10)]
        got = marks.latest(busy + [item(at(3, 17), title="Old")], LA, START, END, limit=8)
        self.assertEqual(([i["title"] for i in got["items"]], got["total"]),
                         ([f"Change {m}" for m in range(9, 1, -1)], 11))

    def test_newest_first_with_the_account_day(self):
        got = marks.latest([item(at(3, 17), title="Older"), item(at(10, 6, 30), title="Newer")], LA, START, END)
        self.assertEqual([(i["title"], i["day"]) for i in got["items"]], [("Newer", "2026-11-09"), ("Older", "2026-11-03")])

    def test_outside_the_range_is_not_listed_or_counted(self):
        got = marks.latest([item(at(1, 6)), item(at(9, 17))], LA, START, END)
        self.assertEqual((len(got["items"]), got["total"]), (1, 1))

    def test_clients_get_the_same_names_as_on_the_charts(self):
        got = marks.latest([item(at(9, 17), proposal_id=5)], LA, START, END, for_client=True)
        self.assertEqual((got["items"][0]["title"], got["items"][0]["by"]), ("Budget $20.00 → $24.00 a day", "Team"))


class ChartWorthyTests(unittest.TestCase):
    def test_metas_echo_of_a_switch_is_dropped(self):
        rows = [status(at(9, 10), "configured_status", "ACTIVE", "PAUSED"), status(at(9, 10, 4), "effective_status", "ACTIVE", "PAUSED")]
        self.assertEqual([r["field"] for r in marks.chart_worthy(rows)], ["configured_status"])

    def test_cascades_from_the_parent_are_dropped(self):
        rows = [status(at(9, 10), "effective_status", "ACTIVE", "CAMPAIGN_PAUSED"),
                status(at(9, 11), "effective_status", "ADSET_PAUSED", "ACTIVE"),
                status(at(9, 12), "effective_status", "IN_PROCESS", "ACTIVE")]
        self.assertEqual([r["old"] for r in marks.chart_worthy(rows)], ["IN_PROCESS"])

    def test_an_echo_long_after_the_switch_stays(self):
        rows = [status(at(9, 10), "configured_status", "ACTIVE", "PAUSED"), status(at(9, 10, 20), "effective_status", "ACTIVE", "PAUSED")]
        self.assertEqual(len(marks.chart_worthy(rows)), 2)

    def test_suggestions_and_comment_replies_are_dropped(self):
        rows = [item(at(9, 10), kind="proposal"), item(at(9, 11), field="comment_reply", cat="edit"), item(at(9, 12))]
        self.assertEqual([r["at"] for r in marks.chart_worthy(rows)], [at(9, 12)])


class SummaryTests(unittest.TestCase):
    def test_the_changes_in_words(self):
        rows = [item(at(9, 17)), status(at(11, 18), "effective_status", "IN_PROCESS", "ACTIVE", entity_name="N6")]
        got = marks.by_day(rows, LA, START, END)
        self.assertEqual(marks.summary_words(got, lambda d: date.fromisoformat(d).strftime("%b %-d")),
                         "2 changes in this period: budget raised Nov 9, ad “N6” approved Nov 11.")

    def test_none(self):
        self.assertEqual(marks.summary_words([], str), "No changes in this period.")

    def test_a_long_period_names_three_and_counts_the_rest(self):
        rows = [item(at(d, 17), old="2000", new=str(2000 - d)) for d in range(3, 8)]
        text = marks.summary_words(marks.by_day(rows, LA, START, END), lambda d: d[-2:])
        self.assertEqual(text, "5 changes in this period: budget lowered 03, budget lowered 04, budget lowered 05 and 2 more.")
