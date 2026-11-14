"""AM-E: Meta's extra insights read through the Ads Manager link. How you compare, unusual changes and error messages as
alerts, Meta's picture of an ad, tracking quality and the business context for Claude (pure logic only)."""
import base64
import struct
import unittest
import zlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import am_link
import diagnose
import inbox
import meta_extras as mx
import snooze

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 14)
N2, N3 = "120252672229400312", "120252672230740312"
CAMPAIGN = "120252638288040312"
KNOWN = {N2: {"level": "ad", "name": "N2", "campaign_id": CAMPAIGN}, N3: {"level": "ad", "name": "N3", "campaign_id": CAMPAIGN},
         CAMPAIGN: {"level": "campaign", "name": "Free intro call - Leads", "campaign_id": CAMPAIGN}}
# The fake MCP server's rows (dev/fake_mcp.py), as the link keeps them.
BENCH = [{"metric": "cost_per_lead", "value": 4.79, "peer_low": 18, "peer_median": 27, "peer_high": 42, "industry": "Professional services",
          "region": "US", "period": "last_30d"},
         {"metric": "ctr", "value": 1.08, "peer_low": 0.9, "peer_median": 1.2, "peer_high": 1.6, "period": "last_30d"}]
PEERS = [{"metric": "cost_per_lead", "value": 4.79, "peer_value": 27, "percentile": 90, "direction": "better", "period": "last_30d"}]


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def b64(data):
    return base64.b64encode(data).decode()


class ComparisonRowsTests(unittest.TestCase):
    def test_the_fakes_numbers_in_dollars(self):
        rows = mx.comparison_rows(BENCH, PEERS, "USD")
        self.assertEqual([(r["label"], r["ours"], r["peers"], r["verdict"]) for r in rows],
                         [("Cost per lead", "$4.79", "$18–$42", "better"), ("Click rate", "1.08%", "0.9–1.6%", "same")])

    def test_money_follows_the_accounts_currency(self):
        rows = mx.comparison_rows(BENCH[:1], [], "CAD")
        self.assertEqual((rows[0]["ours"], rows[0]["peers"]), ("4.79 CAD", "18–42 CAD"))

    def test_a_metric_meta_gave_no_peer_value_for_is_left_out(self):
        rows = mx.comparison_rows([{"metric": "cpm", "value": 12.5}], [{"metric": "frequency", "value": 1.4}], "USD")
        self.assertEqual(rows, [])

    def test_percentile_fifty_is_about_the_same_and_only_metas_own_words_say_worse(self):
        same = mx.comparison_rows([], [{"metric": "cpc", "value": 1.2, "peer_value": 1.1, "percentile": 50}], "USD")
        worse = mx.comparison_rows([], [{"metric": "cpc", "value": 3.0, "peer_value": 1.1, "percentile": 15}], "USD")
        unsaid = mx.comparison_rows([], [{"metric": "cpc", "value": 3.0, "peer_value": 1.1}], "USD")
        self.assertEqual([same[0]["verdict"], worse[0]["verdict"], unsaid[0]["verdict"]], ["same", "worse", None])

    def test_a_cost_above_the_peer_range_is_worse_and_a_click_rate_above_it_is_better(self):
        rows = mx.comparison_rows([{"metric": "cost_per_lead", "value": 50, "peer_low": 18, "peer_high": 42},
                                   {"metric": "ctr", "value": 2.4, "peer_low": 0.9, "peer_high": 1.6}], [], "USD")
        self.assertEqual([r["verdict"] for r in rows], ["worse", "better"])

    def test_metas_direction_wins_over_the_range(self):
        rows = mx.comparison_rows([{"metric": "cost_per_lead", "value": 50, "peer_low": 18, "peer_high": 42}],
                                  [{"metric": "cost_per_lead", "value": 50, "peer_value": 27, "direction": "better"}], "USD")
        self.assertEqual(rows[0]["verdict"], "better")

    def test_unknown_metrics_and_markup_never_become_rows(self):
        rows = mx.comparison_rows([{"metric": "<b>x</b>", "value": 1, "peer_low": 1, "peer_high": 2}], [], "USD")
        self.assertEqual(rows, [])


class AuctionAndLinesTests(unittest.TestCase):
    RANKS = [{"entity_id": N2, "quality_ranking": "ABOVE_AVERAGE", "engagement_rate_ranking": "AVERAGE",
              "conversion_rate_ranking": "BELOW_AVERAGE_20"},
             {"entity_id": "999", "quality_ranking": "AVERAGE"}]

    def test_rankings_in_words_for_the_ads_we_hold(self):
        self.assertEqual(mx.auction_lines(self.RANKS, KNOWN), [
            {"entity_id": N2, "name": "N2", "words": "Quality: Above average · Engagement: Average · Conversions: Below average (bottom 20 %)"}])

    def test_an_unknown_ranking_word_is_left_out(self):
        lines = mx.auction_lines([{"entity_id": N2, "quality_ranking": "SUPER<script>"}], KNOWN)
        self.assertEqual(lines, [])

    def test_the_campaign_line_names_the_cost_per_lead_and_the_quality(self):
        rows = mx.comparison_rows(BENCH, PEERS, "USD")
        line = mx.campaign_line(rows, mx.auction_lines(self.RANKS, KNOWN))
        self.assertEqual(line, "Your account vs similar advertisers: cost per lead $4.79 against $18–$42 (better). N2 quality: Above average.")

    def test_no_rows_no_line(self):
        self.assertIsNone(mx.campaign_line([], []))

    def test_trend_line_in_plain_words(self):
        self.assertEqual(mx.trend_line([{"metric": "cost_per_lead", "direction": "down", "change_pct": -12, "period": "last_14d"}]),
                         "Meta sees cost per lead falling over 14 days (12 % down).")
        self.assertIsNone(mx.trend_line([{"metric": "nonsense", "direction": "up"}]))

    def test_the_newer_of_the_link_and_the_monday_summary_is_shown(self):
        at = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
        self.assertEqual([mx.pick_benchmarks(at, "2026-11-09"), mx.pick_benchmarks(at, "2026-11-15"), mx.pick_benchmarks(None, "2026-11-09"),
                          mx.pick_benchmarks(at, None), mx.pick_benchmarks(None, None)],
                         ["link", "monday", "monday", "link", None])


class AnomalyAlertTests(unittest.TestCase):
    ROW = {"entity_id": N2, "level": "ad", "metric": "cost_per_lead", "direction": "up", "change_pct": 48, "detected_on": "2026-11-14",
           "summary": "Cost per lead rose 48% against its 7-day pattern."}

    def test_an_anomaly_on_an_ad_we_hold(self):
        [a] = mx.anomaly_alerts([self.ROW], KNOWN, TODAY)
        self.assertEqual(a, {"rule": "meta_anomaly", "entity_id": f"{N2}:cost_per_lead", "key": f"meta_anomaly:{N2}:cost_per_lead:2026-11-14",
                             "level": "warn", "kind": "condition", "title": "Meta noticed: cost per lead up 48 % on “N2”",
                             "lines": ["Cost per lead rose 48% against its 7-day pattern.", "Spotted Sat, Nov 14"],
                             "campaign_id": CAMPAIGN, "href": f"/ad.html?id={N2}", "measure": 48.0})

    def test_an_id_we_dont_hold_is_about_the_account(self):
        [a] = mx.anomaly_alerts([{**self.ROW, "entity_id": "555"}], KNOWN, TODAY)
        self.assertEqual((a["entity_id"], a["campaign_id"], a["title"], a["href"]),
                         ("account:cost_per_lead", None, "Meta noticed: cost per lead up 48 % across the account", "/performance.html"))

    def test_the_next_day_is_a_new_key_and_a_bigger_change_is_worse_for_a_snooze(self):
        [today] = mx.anomaly_alerts([self.ROW], KNOWN, TODAY)
        [tomorrow] = mx.anomaly_alerts([{**self.ROW, "change_pct": 90}], KNOWN, TODAY + timedelta(days=1))
        self.assertNotEqual(today["key"], tomorrow["key"])
        self.assertEqual(today["entity_id"], tomorrow["entity_id"])
        self.assertEqual([snooze.worse("meta_anomaly", 48, 90, "warn", "warn"), snooze.worse("meta_anomaly", 48, 60, "warn", "warn")],
                         [True, False])

    def test_spend_and_cost_changes_are_money_delivery_is_status(self):
        self.assertEqual([inbox.category("meta_anomaly", f"{N2}:cost_per_lead"), inbox.category("meta_anomaly", "account:spend"),
                          inbox.category("meta_anomaly", f"{N2}:impressions"), inbox.category("meta_ad_error", N2)],
                         ["money", "money", "status", "status"])

    def test_the_switch_off_raises_nothing_and_bad_rows_are_skipped(self):
        self.assertEqual(mx.anomaly_alerts([self.ROW], KNOWN, TODAY, on=False), [])
        self.assertEqual(mx.anomaly_alerts([{"entity_id": N2, "summary": "no metric"}, {**self.ROW, "metric": "drop table"}], KNOWN, TODAY), [])

    def test_a_down_change_says_down(self):
        [a] = mx.anomaly_alerts([{**self.ROW, "metric": "impressions", "direction": "down", "change_pct": -35.5}], KNOWN, TODAY)
        self.assertEqual((a["title"], a["measure"]), ("Meta noticed: views down 35.5 % on “N2”", 35.5))

    def test_snooze_offers_both_choices_and_diagnose_reads_it(self):
        [a] = mx.anomaly_alerts([self.ROW], KNOWN, TODAY)
        self.assertEqual([c["mode"] for c in snooze.choices(a)], ["days", "worse"])
        self.assertTrue(diagnose.can_diagnose("meta_anomaly") and diagnose.can_diagnose("meta_ad_error"))
        self.assertEqual(snooze.worse_hint("meta_anomaly", 48), "You'll hear again if the change reaches 73%.")


class ErrorAlertTests(unittest.TestCase):
    BLOCK = {"entity_id": N3, "level": "ad", "code": 1487, "summary": "Payment method failed", "message": "Update it in <b>Billing</b>.",
             "blocking": True, "since": "2026-11-12"}

    def test_blocking_is_bad_limited_is_warn(self):
        [bad] = mx.error_alerts([self.BLOCK], KNOWN, TODAY)
        [warn] = mx.error_alerts([{**self.BLOCK, "blocking": False, "summary": "Delivery limited"}], KNOWN, TODAY)
        self.assertEqual((bad["level"], bad["title"], bad["lines"], bad["href"], bad["entity_id"], bad["campaign_id"]),
                         ("bad", "Meta: “N3” can't deliver until it's fixed", ["Payment method failed"], f"/ad.html?id={N3}", N3, CAMPAIGN))
        self.assertEqual((warn["level"], warn["title"]), ("warn", "Meta flags a problem on “N3”"))

    def test_a_blocking_error_cant_be_snoozed_a_limited_one_waits_3_days(self):
        [bad] = mx.error_alerts([self.BLOCK], KNOWN, TODAY)
        [warn] = mx.error_alerts([{**self.BLOCK, "blocking": False}], KNOWN, TODAY)
        self.assertEqual([snooze.choices(bad), [(c["mode"], c["days"]) for c in snooze.choices(warn)]], [[], [("days", 3)]])

    def test_two_errors_on_one_ad_are_one_alert_led_by_the_blocking_one(self):
        found = mx.error_alerts([{**self.BLOCK, "blocking": False, "summary": "Small text"}, self.BLOCK], KNOWN, TODAY)
        self.assertEqual([(a["level"], a["lines"]) for a in found], [("bad", ["Payment method failed", "+1 more"])])

    def test_the_error_panel_cuts_long_text_and_keeps_markup_as_text(self):
        long = "<b>bold</b> " + "y" * 5000
        [p] = mx.error_panel([{**self.BLOCK, "message": long, "fix": "Open Billing"}], LA)
        self.assertEqual(p, {"summary": "Payment method failed", "message": long[:mx.MESSAGE_MAX], "code": "1487", "fix": "Open Billing",
                             "since_words": "Since Thu, Nov 12", "blocking": True})
        self.assertTrue(p["message"].startswith("<b>bold</b>"))

    def test_the_panel_puts_blocking_errors_first(self):
        panel = mx.error_panel([{**self.BLOCK, "blocking": False, "summary": "later"}, self.BLOCK], LA)
        self.assertEqual([p["summary"] for p in panel], ["Payment method failed", "later"])


class ClosingTests(unittest.TestCase):
    OPEN = [{"id": 1, "rule": "meta_anomaly", "entity_id": f"{N2}:cost_per_lead", "created_at": NOW - timedelta(hours=3)},
            {"id": 2, "rule": "meta_ad_error", "entity_id": N3, "created_at": NOW - timedelta(hours=3)},
            {"id": 3, "rule": "meta_anomaly", "entity_id": "account:spend", "created_at": NOW + timedelta(minutes=5)}]

    def test_gone_from_a_fresh_read_closes(self):
        self.assertEqual(mx.to_close(self.OPEN, {("meta_ad_error", N3)}, NOW, stale=False), [1])

    def test_a_stale_read_closes_nothing(self):
        self.assertEqual(mx.to_close(self.OPEN, set(), NOW, stale=True), [])

    def test_only_the_rules_the_read_judges(self):
        self.assertEqual(mx.to_close(self.OPEN, set(), NOW, stale=False, rules={"meta_ad_error"}), [2])

    def test_the_hourly_run_never_closes_them(self):
        import alerts
        opened = [{"id": 1, "rule": "meta_anomaly", "entity_id": "x:spend"}, {"id": 2, "rule": "meta_ad_error", "entity_id": "x"}]
        self.assertEqual(alerts.to_resolve(opened, [], {"reach_7d": {}}), [])
        self.assertTrue({"meta_anomaly", "meta_ad_error"} <= alerts.unjudged({"reach_7d": {}}))


class QualityAndContextTests(unittest.TestCase):
    def test_scores_in_words(self):
        rows = mx.quality_rows([{"event": "Lead", "match_quality": 7.8, "advice": "Send email and phone."}, {"event": "PageView", "match_quality": 3.0},
                                {"event": "Bad", "match_quality": 14}, {"event": "None"}])
        self.assertEqual([(r["event"], r["words"], r["pct"], r["band"]) for r in rows],
                         [("Lead", "7.8 out of 10: good", 78, "good"), ("PageView", "3.0 out of 10: poor", 30, "poor")])
        self.assertEqual(rows[0]["advice"], "Send email and phone.")

    def test_the_context_keeps_listed_keys_only_cut(self):
        ctx = mx.context_block({"vertical": "Professional services " + "z" * 500, "region": "US", "owner_email": "e@x.com",
                                "objective_mix": ["leads", "x" * 400], "maturity": {"nested": 1}})
        self.assertEqual(ctx, {"vertical": ("Professional services " + "z" * 500)[:mx.CONTEXT_MAX], "region": "US",
                               "objective_mix": ["leads", "x" * mx.CONTEXT_MAX]})


class ScreenshotTests(unittest.TestCase):
    def test_at_most_twelve_delivering_ads_and_fresh_ones_left_out(self):
        ads = [{"id": str(i), "effective_status": "ACTIVE"} for i in range(20)]
        have = {str(i): NOW - timedelta(hours=2) for i in range(5)}
        have["6"] = NOW - timedelta(days=2)
        self.assertEqual(mx.screenshot_targets(ads, have, NOW), [str(i) for i in range(5, 12)])

    def test_paused_ads_get_no_daily_picture(self):
        ads = [{"id": "1", "effective_status": "PAUSED"}, {"id": "2", "effective_status": "ACTIVE"}]
        self.assertEqual(mx.screenshot_targets(ads, {}, NOW), ["2"])

    def test_a_png_from_the_mac_is_kept_with_its_size(self):
        data = png(4, 5)
        pic, why = mx.picture({"images": [{"mime": "image/gif", "data_b64": b64(data)}]})
        self.assertIsNone(why)
        self.assertEqual((pic["mime"], pic["width"], pic["height"], pic["bytes"], pic["placement"]), ("image/png", 4, 5, data, ""))

    def test_the_specs_flat_shape_and_metas_raw_content_work_too(self):
        data = png(2, 2)
        flat, _ = mx.picture({"mime": "image/png", "data_b64": b64(data), "placement": "INSTAGRAM_STORY"})
        raw, _ = mx.picture({"content": [{"type": "text", "text": "hi"}, {"type": "image", "mimeType": "image/png", "data": b64(data)}]})
        self.assertEqual([(flat["placement"], flat["bytes"]), (raw["placement"], raw["bytes"])], [("INSTAGRAM_STORY", data), ("", data)])

    def test_refusals(self):
        gif = b"GIF89a" + bytes(40)
        html = b"<html><script>alert(1)</script></html>"
        cases = {"gif": {"images": [{"mime": "image/png", "data_b64": b64(gif)}]},
                 "html": {"mime": "image/png", "data_b64": b64(html)},
                 "not base64": {"mime": "image/png", "data_b64": "!!!not base64!!!"},
                 "too big": {"mime": "image/png", "data_b64": b64(png(1, 1) + bytes(mx.PICTURE_MAX))},
                 "no image": {"images": []}, "not an object": "x"}
        out = {k: mx.picture(v) for k, v in cases.items()}
        self.assertEqual({k: v[0] for k, v in out.items()}, {k: None for k in cases})
        self.assertEqual(out["gif"][1], "Meta's picture isn't a PNG, JPEG or WebP image; nothing was kept.")
        self.assertEqual(out["too big"][1], "Meta's picture is bigger than 3 MB; nothing was kept.")

    def test_an_odd_placement_name_is_dropped(self):
        pic, _ = mx.picture({"mime": "image/png", "data_b64": b64(png(1, 1)), "placement": "<script>"})
        self.assertEqual(pic["placement"], "")

    def test_a_picture_push_may_be_bigger_than_other_kinds(self):
        run = {"status": "open", "created_at": NOW - timedelta(minutes=1), "kinds": ["screenshots"], "ad_account_id": "1"}
        body = {"kind": "screenshots", "ad_account_id": "act_1", "via": "direct"}
        self.assertIsNone(am_link.push_refusal(run, "1", body, NOW, 4_000_000))
        self.assertEqual(am_link.push_refusal({**run, "kinds": ["benchmarks"]}, "1", {**body, "kind": "benchmarks"}, NOW, 4_000_000),
                         "Meta's answer is too big to keep.")


class LinkTextTests(unittest.TestCase):
    def test_metas_error_message_keeps_up_to_a_thousand_characters(self):
        data, _ = am_link.normalize("ad_errors", {"errors": [{"entity_id": N3, "message": "m" * 5000, "summary": "s" * 5000}]})
        self.assertEqual((len(data["rows"][0]["message"]), len(data["rows"][0]["summary"])), (1000, am_link.STR_MAX))

    def test_subject_of_an_anomaly_is_its_entity(self):
        self.assertEqual([mx.subject_id(f"{N2}:cost_per_lead"), mx.subject_id(N3), mx.subject_id("account:spend"), mx.subject_id(None)],
                         [N2, N3, "account", None])


if __name__ == "__main__":
    unittest.main()
