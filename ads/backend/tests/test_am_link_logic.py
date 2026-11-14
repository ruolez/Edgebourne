"""AM-A: the Ads Manager link's pure logic (what is due, which pushes are kept, what Meta's answers become, the words)."""
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import am_link

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 13, 10, 0, tzinfo=LA)


def local(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=LA)


class DueKindsTests(unittest.TestCase):
    KINDS = ("drafts", "ad_errors", "benchmarks", "anomalies")

    def due(self, last, now=NOW, mode="direct", forced=False):
        return am_link.due_kinds(last, now, mode, forced, kinds=self.KINDS)

    def daily_read(self, at):
        return {"benchmarks": at, "anomalies": at}

    def test_fast_kinds_read_14_minutes_ago_by_the_mac_itself_are_not_due(self):
        last = {"drafts": NOW - timedelta(minutes=14), "ad_errors": NOW - timedelta(minutes=14), **self.daily_read(NOW - timedelta(hours=1))}
        self.assertEqual(self.due(last), [])

    def test_fast_kinds_follow_the_mode(self):
        def fast(minutes, mode):
            last = {"drafts": NOW - timedelta(minutes=minutes), "ad_errors": NOW - timedelta(minutes=minutes),
                    **self.daily_read(NOW - timedelta(hours=1))}
            return self.due(last, mode=mode)
        self.assertEqual([fast(16, "direct"), fast(16, "claude"), fast(31, "claude")],
                         [["drafts", "ad_errors"], [], ["drafts", "ad_errors"]])

    def test_daily_kinds_wait_for_6_am_account_time(self):
        fresh = {"drafts": local(2026, 11, 13, 5, 55), "ad_errors": local(2026, 11, 13, 5, 55)}
        yesterday = self.daily_read(local(2026, 11, 12, 6, 5))
        self.assertEqual([self.due({**fresh, **yesterday}, now=local(2026, 11, 13, 5, 59)),
                          self.due({**fresh, **yesterday}, now=local(2026, 11, 13, 6, 1))],
                         [[], ["benchmarks", "anomalies"]])

    def test_daily_kinds_read_this_morning_are_not_due_tonight(self):
        last = {"drafts": local(2026, 11, 13, 22, 55), "ad_errors": local(2026, 11, 13, 22, 55), **self.daily_read(local(2026, 11, 13, 6, 5))}
        self.assertEqual(self.due(last, now=local(2026, 11, 13, 23, 0)), [])

    def test_one_daily_read_per_account_day_across_the_clock_change(self):
        # Daylight saving ended on Sunday 2026-11-01 in Los Angeles: that day has 25 hours.
        last = self.daily_read(local(2026, 11, 1, 6, 5))
        fast = lambda now: {"drafts": now, "ad_errors": now}  # noqa: E731
        late_sunday, monday = local(2026, 11, 1, 23, 30), local(2026, 11, 2, 6, 1)
        self.assertEqual([self.due({**fast(late_sunday), **last}, now=late_sunday), self.due({**fast(monday), **last}, now=monday)],
                         [[], ["benchmarks", "anomalies"]])

    def test_never_read_is_due_at_any_hour(self):
        self.assertEqual(self.due({}, now=local(2026, 11, 13, 3, 0)), list(self.KINDS))

    def test_check_now_reads_every_kind(self):
        last = {k: NOW for k in self.KINDS}
        self.assertEqual(self.due(last, forced=True), list(self.KINDS))

    def test_the_stored_kinds_are_what_the_plan_asks_for_by_default(self):
        self.assertEqual(am_link.due_kinds({}, NOW, "direct", True), list(am_link.STORED_KINDS))


class PushRefusalTests(unittest.TestCase):
    RUN = {"status": "open", "created_at": NOW - timedelta(minutes=5), "kinds": ["ad_errors", "benchmarks"], "ad_account_id": "1025971549903293"}
    BODY = {"kind": "ad_errors", "ad_account_id": "act_1025971549903293", "via": "direct"}

    def refusal(self, run=RUN, account="1025971549903293", body=BODY, size=100):
        return am_link.push_refusal(run, account, body, NOW, size)

    def test_a_good_push_is_kept(self):
        self.assertIsNone(self.refusal())

    def test_every_broken_rule_is_refused(self):
        cases = [self.refusal(run=None), self.refusal(run={**self.RUN, "status": "done"}),
                 self.refusal(run={**self.RUN, "created_at": NOW - timedelta(minutes=31)}),
                 self.refusal(body={**self.BODY, "kind": "peers"}),
                 self.refusal(body={**self.BODY, "ad_account_id": "act_2"}),
                 self.refusal(account="2223334445556667"),
                 self.refusal(size=am_link.MAX_PUSH_BYTES + 1),
                 self.refusal(body={**self.BODY, "via": "browser"})]
        self.assertEqual([bool(c) for c in cases], [True] * len(cases), cases)

    def test_the_reasons_say_what_went_wrong(self):
        self.assertEqual([self.refusal(run=None), self.refusal(body={**self.BODY, "ad_account_id": "act_2"}),
                          self.refusal(account="2223334445556667")],
                         ["This link pass isn't known.", "This link pass is for another ad account.",
                          "This account was switched to another ad account after the pass was made."])


class NormalizeTests(unittest.TestCase):
    def test_ad_errors_keep_listed_fields_and_cut_text(self):
        long = "x" * 5000
        raw = {"errors": [{"entity_id": "120252672229040312", "level": "ad", "code": 1487, "summary": "<script>alert(1)</script> stopped",
                           "message": long, "blocking": True, "since": "2026-11-12", "fix": "Update the card", "token": "SECRET",
                           "extra": {"nested": 1}},
                          {"entity_id": "javascript:alert(1)", "summary": "bad id"}]}
        data, why = am_link.normalize("ad_errors", raw)
        self.assertEqual((why, data), (None, {"rows": [{"entity_id": "120252672229040312", "level": "ad", "code": 1487,
                                                         "summary": "<script>alert(1)</script> stopped", "message": "x" * am_link.STR_MAX,
                                                         "blocking": True, "since": "2026-11-12", "fix": "Update the card"}]}))

    def test_an_account_entity_keeps_its_digits(self):
        data, _ = am_link.normalize("anomalies", [{"entity_id": "act_1025971549903293", "metric": "cost_per_lead", "change_pct": 48.5}])
        self.assertEqual(data["rows"], [{"entity_id": "1025971549903293", "metric": "cost_per_lead", "change_pct": 48.5}])

    def test_lists_are_capped(self):
        data, _ = am_link.normalize("anomalies", {"anomalies": [{"metric": "spend", "change_pct": i} for i in range(80)]})
        self.assertEqual(len(data["rows"]), am_link.LIST_MAX["anomalies"])

    def test_numbers_that_arent_numbers_are_dropped(self):
        data, _ = am_link.normalize("benchmarks", [{"metric": "ctr", "value": float("nan"), "peer_median": 1.2}])
        self.assertEqual(data["rows"], [{"metric": "ctr", "peer_median": 1.2}])

    def test_the_context_is_one_object(self):
        data, why = am_link.normalize("advertiser_context", {"context": {"vertical": "Professional services", "region": "US", "owner_email": "x@y"}})
        self.assertEqual((why, data), (None, {"vertical": "Professional services", "region": "US"}))

    def test_unexpected_shapes_are_refused(self):
        cases = [am_link.normalize("ad_errors", "not json"), am_link.normalize("ad_errors", {"message": "no list here"}),
                 am_link.normalize("advertiser_context", [{"vertical": "x"}]), am_link.normalize("benchmarks", 42)]
        self.assertEqual([c[0] for c in cases], [None] * 4)
        self.assertTrue(all(c[1] and c[1].endswith("unexpected shape") for c in cases), cases)

    def test_a_kind_without_storage_yet_is_refused(self):
        self.assertEqual(am_link.normalize("drafts", {"ad_drafts": []}), (None, "Drafts aren't stored yet."))


class ClampTests(unittest.TestCase):
    def test_the_macs_time_is_kept_inside_the_pass(self):
        created = NOW - timedelta(minutes=5)
        self.assertEqual([am_link.clamp_fetched(NOW + timedelta(hours=3), created, NOW),
                          am_link.clamp_fetched(NOW - timedelta(days=2), created, NOW),
                          am_link.clamp_fetched(NOW - timedelta(minutes=2), created, NOW),
                          am_link.clamp_fetched(None, created, NOW)],
                         [NOW, created - timedelta(minutes=1), NOW - timedelta(minutes=2), NOW])


class SourceTests(unittest.TestCase):
    def words(self, fetched_at, state="connected", last_pass=NOW - timedelta(minutes=10), via="direct", online=True, on=True):
        return am_link.source(fetched_at, state, last_pass, NOW, LA, via, mac_online=online, reading_on=on)

    def test_the_four_sentences(self):
        self.assertEqual([self.words(NOW - timedelta(minutes=12))["words"],
                          self.words(NOW - timedelta(hours=2), state="fallback", via="claude")["words"],
                          self.words(local(2026, 11, 13, 9, 0), last_pass=local(2026, 11, 13, 9, 0), online=False)["words"],
                          self.words(None, state="not_connected", last_pass=None)["words"]],
                         ["From Ads Manager via your Mac, 12 min ago", "From Ads Manager via Claude on your Mac, 2 h ago",
                          "Your Mac has been away since 9:00 AM; this is from then.",
                          "Not read yet: connect the Ads Manager link in Settings."])

    def test_away_since_an_earlier_day_names_the_day(self):
        at = local(2026, 11, 12, 21, 15)
        self.assertEqual(self.words(at, last_pass=at, online=False)["words"], "Your Mac has been away since Thu, Nov 12, 9:15 PM; this is from then.")

    def test_stale_follows_away_and_age(self):
        self.assertEqual([self.words(NOW - timedelta(minutes=12))["stale"],
                          self.words(NOW - timedelta(hours=1), last_pass=NOW - timedelta(hours=1), online=False)["stale"],
                          am_link.source(NOW - timedelta(hours=31), "connected", NOW - timedelta(minutes=5), NOW, LA, "direct", kind="benchmarks")["stale"]],
                         [False, True, True])

    def test_a_mac_that_is_online_is_never_called_away(self):
        # No pass for an hour while the Mac checks in: not "away" (the reads are just old), and the line says how old.
        out = self.words(local(2026, 11, 13, 9, 0), last_pass=local(2026, 11, 13, 9, 0), online=True)
        self.assertEqual((out["words"], out["away"], out["stale"]), ("From Ads Manager via your Mac, 1 h ago", False, True))

    def test_an_expired_login_sends_eugene_to_reconnect_not_to_the_mac(self):
        old = local(2026, 11, 13, 8, 30)
        self.assertEqual([self.words(old, state="expired", last_pass=old, online=False)["words"],
                          self.words(old, state="refused", last_pass=old, online=True)["words"],
                          self.words(None, state="expired", last_pass=None)["words"]],
                         ["Reconnect needed in Settings → Ads Manager link; this is from 8:30 AM.",
                          "Meta won't let your Mac's helper in (Settings → Ads Manager link); this is from 8:30 AM.",
                          "Not read yet: reconnect the Ads Manager link in Settings."])

    def test_reading_switched_off_says_so_instead_of_away(self):
        old = local(2026, 11, 13, 8, 30)
        off = self.words(old, last_pass=old, online=False, on=False)
        self.assertEqual([off["words"], off["away"], off["stale"], self.words(None, last_pass=None, on=False)["words"]],
                         ["Reading this account through the Mac is off; this is from 8:30 AM.", False, True,
                          "Not read yet: reading this account through the Mac is off."])

    def test_older_reads_after_a_disconnect_say_the_link_is_off(self):
        out = self.words(NOW - timedelta(minutes=12), state="not_connected", last_pass=None)
        self.assertEqual((out["words"], out["stale"]), ("From Ads Manager via your Mac, 12 min ago; the link isn't connected now", True))

    def test_connected_and_not_read_yet(self):
        self.assertEqual(self.words(None, last_pass=None)["words"], "Not read yet: your Mac reads Ads Manager within 15 minutes.")


class ReadingOnTests(unittest.TestCase):
    AD = "4445556667778889"

    def test_only_the_ad_account_the_owner_approved_is_read(self):
        self.assertEqual([am_link.reading_on(self.AD, self.AD, False), am_link.reading_on("0", self.AD, False),
                          am_link.reading_on("1025971549903293", self.AD, False), am_link.reading_on(None, self.AD, False),
                          am_link.reading_on("1", self.AD, False)],
                         ["on", "off", "changed", "off", "off"])

    def test_the_owners_own_account_is_read_until_switched_off(self):
        self.assertEqual([am_link.reading_on(None, self.AD, True), am_link.reading_on("0", self.AD, True),
                          am_link.reading_on("1025971549903293", self.AD, True)],
                         ["on", "off", "changed"])

    def test_no_ad_account_means_nothing_is_read(self):
        self.assertEqual([am_link.reading_on(None, None, True), am_link.reading_on(self.AD, None, False)], ["off", "off"])


class OwnDataTests(unittest.TestCase):
    AD = "1025971549903293"

    def test_an_answer_naming_another_ad_account_is_caught_anywhere_in_it(self):
        cases = [{"errors": [{"entity_id": "1", "account_id": "act_2223334445556667"}]},
                 {"data": {"meta": {"ad_account_id": "2223334445556667"}}},
                 [{"rows": [{"ad_account_id": "act_x"}]}],
                 {"errors": [{"account_id": f"act_{self.AD}"}], "ad_account_id": self.AD},
                 {"errors": [{"account_id": None, "summary": "act_2223334445556667 in text is only text"}]}]
        self.assertEqual([am_link.foreign_account(c, self.AD) for c in cases], [True, True, True, False, False])

    def test_a_deeply_nested_answer_is_foreign(self):
        deep = {}
        node = deep
        for _ in range(40):
            node["x"] = {}
            node = node["x"]
        self.assertTrue(am_link.foreign_account(deep, self.AD))

    def test_rows_about_ads_outside_this_account_are_dropped(self):
        data = {"rows": [{"entity_id": "111", "metric": "a"}, {"entity_id": "999", "metric": "b"},
                         {"entity_id": self.AD, "metric": "c"}, {"metric": "d"}]}
        self.assertEqual(am_link.keep_own(data, {"111"}, self.AD),
                         ({"rows": [{"entity_id": "111", "metric": "a"}, {"entity_id": self.AD, "metric": "c"}, {"metric": "d"}]}, 1))

    def test_the_context_object_is_kept_whole(self):
        self.assertEqual(am_link.keep_own({"vertical": "x"}, set(), self.AD), ({"vertical": "x"}, 0))


class StatusWordsTests(unittest.TestCase):
    def test_each_state_has_its_sentence(self):
        states = ["not_connected", "connecting", "connected", "expired", "refused", "fallback", "off"]
        self.assertEqual([am_link.link_status_words(s, None, None) for s in states],
                         ["Not connected", "Waiting for your Mac to open the Facebook page…", "Connected",
                          "Reconnect needed: Meta asked for a new login", "Meta won't let the Mac's helper in",
                          "Working through Claude on your Mac", "Disconnecting: your Mac removes its Facebook login next time it checks in"])


class LinkDownTests(unittest.TestCase):
    def down(self, state, since, online=True, hours=6):
        return am_link.link_down(state, since, online, NOW, hours)

    def test_quiet_while_reading(self):
        self.assertIsNone(self.down("connected", NOW - timedelta(hours=2)))

    def test_reads_stopped_while_the_mac_is_online(self):
        a = self.down("connected", NOW - timedelta(hours=7))
        self.assertEqual((a["level"], a["title"], a["measure"]), ("info", "Ads Manager hasn't been read for 7 hours", 7))

    def test_a_mac_that_is_away_is_not_a_link_problem(self):
        self.assertIsNone(self.down("connected", NOW - timedelta(hours=7), online=False))

    def test_expired_and_refused_without_fallback_tell_at_once_and_warn_after_a_day(self):
        self.assertEqual([self.down("expired", NOW - timedelta(hours=1))["level"], self.down("refused", NOW - timedelta(hours=25))["level"],
                          self.down("fallback", NOW - timedelta(hours=1)), self.down("not_connected", None)],
                         ["info", "warn", None, None])


class ToolArgsTests(unittest.TestCase):
    def test_every_stored_kind_names_its_read_tool(self):
        self.assertEqual({k: am_link.TOOLS[k] for k in am_link.STORED_KINDS}["ad_errors"], "ads_get_errors")
        self.assertTrue(all(am_link.TOOLS[k].startswith(("ads_get_", "ads_insights_")) for k in am_link.KINDS))

    def test_arguments_name_the_ad_account_the_pass_is_for(self):
        self.assertEqual([am_link.tool_args("ad_errors", "123"), am_link.tool_args("drafts", "123", after="c1"),
                          am_link.tool_args("screenshots", "123", scope="120")],
                         [{"ad_account_id": "act_123"}, {"ad_account_id": "act_123", "object_state": "draft", "limit": 25, "after": "c1"},
                          {"ad_id": "120"}])


if __name__ == "__main__":
    unittest.main()
