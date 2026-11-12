import random
import unittest
from datetime import date, timedelta

import gallery as g

TODAY = date(2026, 11, 12)
TRACK = [TODAY - timedelta(days=14 - i) for i in range(14)]
WORDS = {"title": "Type it once", "body": "Your tools don't talk to each other.", "cta_type": "BOOK_TRAVEL"}


def ad(i, video="v1", creative=None, status="ACTIVE", image=None, **over):
    row = {"id": i, "name": f"Ad {i}", "effective_status": status, "video_id": video, "creative_id": creative or f"c-{i}",
           "image_url": image or f"https://img/{i}.jpg", "thumbnail_url": None, "created_on": TODAY - timedelta(days=30), **WORDS}
    row.update(over)
    return row


def nums(spend=0, leads=0, imp=0, v3=0, clicks=0):
    return {"spend_cents": spend, "leads": leads, "impressions": imp, "video_3s": v3, "link_clicks": clicks}


def build(ads, totals=None, tags=None, tired=(), first=None, delivered=None, target=None, since=None):
    return g.build(ads, totals or {}, tags or {}, set(tired), first or {}, delivered or {}, TRACK, TODAY, target, since=since)


def by_ads(groups):
    return sorted(sorted(a["id"] for a in x["ads"]) for x in groups)


class GroupKeyTests(unittest.TestCase):
    def test_the_same_video_on_a_new_creative_merges(self):
        a = ad("a", creative="c1", adset_id="s1")
        b = ad("b", creative="c2", adset_id="s2", title="  type it ONCE ", body="Your tools  don't talk to each other.")
        groups = build([a, b], {"a": nums(1000, 2, 4000, 1200), "b": nums(500, 1, 2000, 400)})
        self.assertEqual([(by_ads(groups), groups[0]["spend_cents"], groups[0]["leads"], groups[0]["impressions"])],
                         [([["a", "b"]], 1500, 3, 6000)])

    def test_any_difference_in_video_or_words_keeps_them_apart(self):
        base = ad("a")
        for change in ({"video_id": "v2"}, {"title": "Stop retyping"}, {"body": "Other words"}, {"cta_type": "SIGN_UP"}):
            with self.subTest(change=change):
                self.assertEqual(by_ads(build([base, ad("b", **change)])), [["a"], ["b"]])

    def test_never_merges_on_missing_words(self):
        for missing in ("title", "body", "cta_type"):
            with self.subTest(missing=missing):
                ads = [ad("a", **{missing: None}), ad("b", **{missing: None})]
                self.assertEqual(by_ads(build(ads)), [["a"], ["b"]])

    def test_an_ad_with_nothing_to_match_on_stands_alone(self):
        ads = [ad("a", video=None, creative=None), ad("b", video=None, creative=None)]
        ads[0]["creative_id"] = ads[1]["creative_id"] = None
        self.assertEqual(by_ads(build(ads)), [["a"], ["b"]])

    def test_pictures_merge_only_on_the_same_creative(self):
        ads = [ad("a", video=None, creative="p1"), ad("b", video=None, creative="p1"), ad("c", video=None, creative="p2")]
        self.assertEqual(by_ads(build(ads)), [["a", "b"], ["c"]])

    def test_the_same_creative_merges_even_without_words(self):
        ads = [ad("a", creative="c9", title=None), ad("b", creative="c9", title=None)]
        self.assertEqual(by_ads(build(ads)), [["a", "b"]])

    def test_grouping_does_not_depend_on_the_order_ads_come_in(self):
        rng = random.Random(7)
        pool = [ad(f"x{n}", video=rng.choice(["v1", "v2", None]), creative=rng.choice(["c1", "c2", "c3", f"own{n}"]),
                   title=rng.choice(["Type it once", "type it  once", None, "Other"])) for n in range(40)]
        want = by_ads(build(pool))
        for _ in range(20):
            rng.shuffle(pool)
            self.assertEqual(by_ads(build(pool)), want)


class NumbersTests(unittest.TestCase):
    def test_cost_per_lead_and_hook_rate_of_a_video(self):
        x = build([ad("a")], {"a": nums(3000, 4, 2000, 500)})[0]
        self.assertEqual((x["kind"], x["cpl_cents"], x["hook_rate"]), ("video", 750, 0.25))

    def test_a_picture_has_no_hook_rate_rather_than_zero(self):
        x = build([ad("a", video=None)], {"a": nums(3000, 4, 2000, 0)})[0]
        self.assertEqual((x["kind"], x["hook_rate"]), ("image", None))

    def test_no_leads_means_no_cost_per_lead(self):
        self.assertIsNone(build([ad("a")], {"a": nums(900, 0, 100)})[0]["cpl_cents"])

    def test_the_top_spending_copy_names_the_card_and_is_compared(self):
        ads = [ad("a", creative="c1", name="First", image="https://img/first.jpg"), ad("b", creative="c2", name="Second", image="https://img/second.jpg")]
        x = build(ads, {"a": nums(100), "b": nums(900)})[0]
        self.assertEqual((x["name"], x["top_ad_id"], x["image_url"], [a["id"] for a in x["ads"]]),
                         ("Second", "b", "https://img/second.jpg", ["b", "a"]))

    def test_judged_only_with_three_leads_and_twice_the_target_spent(self):
        cases = [(nums(2000, 3), True), (nums(1999, 3), False), (nums(5000, 2), False)]
        for n, want in cases:
            with self.subTest(n=n):
                self.assertEqual(build([ad("a")], {"a": n}, target=1000)[0]["enough"], want)

    def test_without_a_target_the_average_cost_per_lead_is_the_bar(self):
        # $59 for 6 leads: $9.83 on average, so a card needs $19.66 spent and 3 leads
        groups = {x["top_ad_id"]: x["enough"] for x in build([ad("a", video="v1"), ad("b", video="v2")], {"a": nums(4000, 3), "b": nums(1900, 3)})}
        self.assertEqual(groups, {"a": True, "b": False})


class StatusTests(unittest.TestCase):
    def test_a_card_delivers_when_any_copy_does_and_counts_the_rejected_ones(self):
        ads = [ad("a", creative="c1", status="DISAPPROVED"), ad("b", creative="c2", status="ACTIVE"), ad("c", creative="c3", status="PAUSED")]
        x = build(ads)[0]
        self.assertEqual((x["effective_status"], x["bucket"], x["problems"]), ("ACTIVE", "delivering", 1))

    def test_each_status_lands_in_its_bucket(self):
        cases = {"ACTIVE": "delivering", "IN_PROCESS": "review", "PENDING_REVIEW": "review", "PREAPPROVED": "review",
                 "DISAPPROVED": "problem", "WITH_ISSUES": "problem", "PENDING_BILLING_INFO": "problem", "PAUSED": "off",
                 "CAMPAIGN_PAUSED": "off", "ADSET_PAUSED": "off", "ARCHIVED": "off", "DELETED": "deleted", None: "off"}
        self.assertEqual({s: g.bucket(s) for s in cases}, cases)

    def test_copies_waiting_for_review_are_counted_on_a_delivering_card(self):
        ads = [ad("a", creative="c1", status="ACTIVE"), ad("b", creative="c2", status="PENDING_REVIEW")]
        x = build(ads)[0]
        self.assertEqual((x["bucket"], x["buckets"], x["in_review"], x["problems"]), ("delivering", ["delivering", "review"], 1, 0))

    def test_the_track_shows_a_day_when_any_copy_spent(self):
        ads = [ad("a", creative="c1"), ad("b", creative="c2")]
        x = build(ads, delivered={"a": {TRACK[0]}, "b": {TRACK[13]}})[0]
        self.assertEqual([d["on"] for d in x["track"]], [True] + [False] * 12 + [True])


class CreditedTests(unittest.TestCase):
    DAYS = [{"day": TODAY - timedelta(days=n), "spend_cents": 100, "impressions": 10, "link_clicks": 1, "leads": 1, "video_3s": 2} for n in range(1, 11)]

    def test_an_ad_that_never_changed_keeps_every_day(self):
        for chain in ([], [{"started_on": None, "live_on": None}]):
            with self.subTest(chain=chain):
                self.assertEqual((g.credited(self.DAYS, chain)["spend_cents"], g.credited(self.DAYS, chain)["days"]), (1000, 10))

    def test_only_the_current_versions_days_count(self):
        # switched 5 days ago, approved 4 days ago: the last 3 days are the new version's, days 5 and 4 belong to neither
        chain = [{"started_on": None, "live_on": None}, {"started_on": TODAY - timedelta(days=5), "live_on": TODAY - timedelta(days=4)}]
        got = g.credited(self.DAYS, chain)
        self.assertEqual((got["days"], got["spend_cents"], got["leads"], got["video_3s"]), (3, 300, 3, 6))


    def test_a_restore_counts_every_day_the_restored_creative_showed(self):
        # v1 (creative k1) until 8 days ago, v2 (k2) from 8, approved 7 days ago, back to k1 from 3, approved 2 days ago:
        # days 10..9 (v1) and 1 (v3) count; 8..7 and 3..2 are changeovers, 6..4 were the other creative's
        chain = [{"creative_id": "k1", "started_on": None, "live_on": None},
                 {"creative_id": "k2", "started_on": TODAY - timedelta(days=8), "live_on": TODAY - timedelta(days=7)},
                 {"creative_id": "k1", "started_on": TODAY - timedelta(days=3), "live_on": TODAY - timedelta(days=2)}]
        got = g.credited(self.DAYS, chain)
        self.assertEqual((got["days"], got["spend_cents"]), (3, 300))

    def test_counts_now_says_which_days_belong_to_what_the_ad_shows_now(self):
        chain = [{"creative_id": "k1", "started_on": None, "live_on": None},
                 {"creative_id": "k2", "started_on": TODAY - timedelta(days=5), "live_on": TODAY - timedelta(days=4)}]
        self.assertEqual([g.counts_now(TODAY - timedelta(days=n), chain) for n in (6, 5, 4, 3)], [False, False, False, True])
        self.assertEqual(g.counts_now(TODAY - timedelta(days=30), []), True)


class LaunchTests(unittest.TestCase):
    def test_the_day_it_first_spent_else_the_day_it_was_made(self):
        self.assertEqual((g.launch_day(date(2026, 11, 3), date(2026, 11, 1)), g.launch_day(None, date(2026, 11, 1))),
                         (date(2026, 11, 3), date(2026, 11, 1)))

    def test_a_new_version_launches_the_day_meta_approved_it(self):
        chain = [{"started_on": None, "live_on": None}, {"started_on": date(2026, 11, 9), "live_on": date(2026, 11, 10)}]
        self.assertEqual(g.launch_day(date(2026, 10, 1), date(2026, 9, 30), chain), date(2026, 11, 10))

    def test_a_restore_launches_on_the_day_the_restored_creative_first_did(self):
        chain = [{"creative_id": "k1", "started_on": None, "live_on": None},
                 {"creative_id": "k2", "started_on": date(2026, 11, 5), "live_on": date(2026, 11, 6)},
                 {"creative_id": "k1", "started_on": date(2026, 11, 10), "live_on": date(2026, 11, 11)}]
        self.assertEqual(g.launch_day(date(2026, 10, 1), date(2026, 9, 30), chain), date(2026, 10, 1))

    def test_version_since_is_the_newest_switch_when_other_days_were_left_out(self):
        k = lambda cid, day: {"creative_id": cid, "started_on": day, "live_on": day}
        cases = [([], None), ([k("k1", None)], None),
                 ([k("k1", None), k("k2", date(2026, 11, 9))], date(2026, 11, 9)),
                 ([k("k1", None), k("k2", date(2026, 11, 5)), k("k1", date(2026, 11, 10))], date(2026, 11, 10))]
        self.assertEqual([g.version_since(c) for c, _ in cases], [want for _, want in cases])

    def test_a_card_names_its_latest_change_and_the_copy_it_was_on(self):
        ads = [ad("a", creative="c1"), ad("b", creative="c2")]
        x = build(ads, since={"a": date(2026, 11, 3), "b": date(2026, 11, 9)})[0]
        self.assertEqual((x["version_since"], x["version_ad"]), ("2026-11-09", "b"))
        self.assertEqual(build([ad("c")])[0]["version_since"], None)

    def test_a_card_launched_when_its_earliest_copy_did(self):
        ads = [ad("a", creative="c1"), ad("b", creative="c2")]
        x = build(ads, first={"a": TODAY - timedelta(days=3), "b": TODAY - timedelta(days=20)})[0]
        self.assertEqual((x["launched_on"], x["just_launched"]), ((TODAY - timedelta(days=20)).isoformat(), False))


def cards():
    ads = [ad("cheap", video="v1"), ad("dear", video="v2"), ad("early", video="v3"), ad("new", video="v4"),
           ad("gone", video="v5", status="DELETED"), ad("tired", video="v6"), ad("review", video="v7", status="IN_PROCESS")]
    totals = {"cheap": nums(2400, 6), "dear": nums(4000, 4), "early": nums(5000, 1), "new": nums(300, 0), "gone": nums(9000, 9),
              "tired": nums(1000, 2), "review": nums(0, 0)}
    first = {k: TODAY - timedelta(days=40) for k in totals}
    first.update({"new": TODAY - timedelta(days=2), "review": None})
    tags = {"dear": {"hook": "Question"}, "new": {"hook": "Question", "angle": "Speed"}, "cheap": {"hook": "Command"}}
    for a in ads:
        if a["id"] == "review":
            a["created_on"] = TODAY - timedelta(days=1)
    return build(ads, totals, tags, tired={"tired"}, first=first, target=1000)


def ids(picked):
    return [x["top_ad_id"] for x in picked["groups"]]


class PickTests(unittest.TestCase):
    def test_top_puts_judged_cards_cheapest_first_then_the_rest_by_spend(self):
        self.assertEqual(ids(g.pick(cards(), "top")), ["cheap", "dear", "early", "tired", "new", "review"])

    def test_deleted_cards_show_only_when_asked_for(self):
        self.assertEqual((ids(g.pick(cards(), "top", status="deleted")), "gone" in ids(g.pick(cards(), "top"))), (["gone"], False))

    def test_status_filter_keeps_one_bucket(self):
        self.assertEqual(ids(g.pick(cards(), "top", status="review")), ["review"])

    def test_just_launched_is_the_last_seven_days_newest_first(self):
        self.assertEqual(ids(g.pick(cards(), "launched")), ["review", "new"])

    def test_tired_is_cards_with_an_open_fatigue_alert(self):
        self.assertEqual(ids(g.pick(cards(), "tired")), ["tired"])

    def test_a_tag_matches_any_copy_and_every_view_counts_with_the_same_filters(self):
        out = g.pick(cards(), "top", tag=("hook", "Question"))
        self.assertEqual((ids(out), out["counts"]), (["dear", "new"], {"top": 2, "launched": 1, "tired": 0}))

    def test_rejected_or_in_review_matches_a_card_when_any_copy_is(self):
        ads = [ad("live", creative="c1", status="ACTIVE"), ad("bad", creative="c2", status="DISAPPROVED"),
               ad("wait", video="v2", creative="c3", status="ACTIVE"), ad("new", video="v2", creative="c4", status="IN_PROCESS"),
               ad("plain", video="v3", status="ACTIVE")]
        groups = build(ads, {"live": nums(900), "wait": nums(800), "plain": nums(700)})
        self.assertEqual((ids(g.pick(groups, "top", status="problem")), ids(g.pick(groups, "top", status="review")),
                          ids(g.pick(groups, "top", status="delivering"))), (["live"], ["wait"], ["live", "wait", "plain"]))

    def test_off_and_deleted_go_by_the_card_not_one_copy(self):
        ads = [ad("on", creative="c1", status="ACTIVE"), ad("paused", creative="c2", status="PAUSED"), ad("gone", creative="c3", status="DELETED"),
               ad("dead", video="v2", creative="c4", status="DELETED"), ad("dead2", video="v2", creative="c5", status="DELETED")]
        groups = build(ads, {"on": nums(900), "dead": nums(100)})
        self.assertEqual((ids(g.pick(groups, "top", status="off")), ids(g.pick(groups, "top", status="deleted"))), ([], ["dead"]))

    def test_a_tag_only_the_second_copy_carries_still_finds_the_card_and_is_listed_on_it(self):
        ads = [ad("first", creative="c1"), ad("second", creative="c2")]
        groups = build(ads, {"first": nums(900), "second": nums(100)}, tags={"first": {"hook": "Command"}, "second": {"hook": "Question"}})
        out = g.pick(groups, "top", tag=("hook", "Question"))
        self.assertEqual((ids(out), out["groups"][0]["tags_all"]), (["first"], [["hook", "Command"], ["hook", "Question"]]))

    def test_an_unknown_view_or_status_falls_back_to_everything_live(self):
        self.assertEqual(ids(g.pick(cards(), "nonsense", status="nonsense")), ids(g.pick(cards(), "top")))


if __name__ == "__main__":
    unittest.main()
