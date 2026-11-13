import unittest

import insights
import insights_api


class ActionValueTests(unittest.TestCase):
    def test_sums_one_type_or_everything(self):
        actions = [{"action_type": "video_view", "value": "120"}, {"action_type": "lead", "value": "2"},
                   {"action_type": "video_view", "value": "5"}]
        self.assertEqual((insights.action_value(actions, "video_view"), insights.action_value(actions), insights.action_value(None)),
                         (125, 127, 0))


class CreativeMediaTests(unittest.TestCase):
    def test_placement_customised_video_ads_count_as_video(self):
        plain_video = {"object_type": "VIDEO", "video_id": "v1"}
        feeds_and_reels = {"object_type": "SHARE", "asset_feed_spec": {"videos": [{"video_id": "v45"}, {"video_id": "v916"}]}}
        image_and_video = {"object_type": "SHARE", "asset_feed_spec": {"images": [{"hash": "h"}], "videos": [{"video_id": "v"}]}}
        image = {"object_type": "SHARE", "image_url": "https://x"}
        self.assertEqual([insights.creative_media(c) for c in (plain_video, feeds_and_reels, image_and_video, image, {})],
                         [("VIDEO", "v1"), ("VIDEO", "v45"), ("SHARE", None), ("SHARE", None), (None, None)])


class BreakdownShapeTests(unittest.TestCase):
    def test_placements_get_readable_names_and_merge(self):
        rows = [{"publisher_platform": "instagram", "platform_position": "stream", "spend": "10", "impressions": "100",
                 "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": "1"}]},
                {"publisher_platform": "facebook", "platform_position": "feed", "spend": "30", "impressions": "300"}]
        items = insights_api.shape_breakdown("placement", rows)
        self.assertEqual([(i["label"], i["spend_cents"], i["leads"]) for i in items],
                         [("Facebook feed", 3000, 0), ("Instagram feed", 1000, 1)])

    def test_hours_are_in_clock_order_with_am_pm(self):
        rows = [{"hourly_stats_aggregated_by_audience_time_zone": f"{h:02d}:00:00 - {h:02d}:59:59", "spend": "1"} for h in (13, 0, 9)]
        self.assertEqual([i["label"] for i in insights_api.shape_breakdown("hour", rows)], ["12 AM", "9 AM", "1 PM"])

    def test_gender_words(self):
        rows = [{"gender": g, "spend": "1"} for g in ("female", "male", "unknown")]
        self.assertEqual(sorted(i["label"] for i in insights_api.shape_breakdown("gender", rows)), ["Men", "Unknown", "Women"])


if __name__ == "__main__":
    unittest.main()


class UniqueReachTests(unittest.TestCase):
    def test_meta_rows_become_people_per_id(self):
        import insights
        rows = [{"ad_id": "a1", "reach": "120"}, {"ad_id": "a2", "reach": "40"}, {"ad_id": "a3"}]
        self.assertEqual(insights.reach_map("ad", rows), {"a1": 120, "a2": 40, "a3": 0})

    def test_account_level_has_one_total(self):
        import insights
        self.assertEqual(insights.reach_map("account", [{"account_id": "1025971549903293", "reach": "510"}]), {"account": 510})

    def test_apply_reach_replaces_summed_daily_reach_and_keeps_zero_for_silent_ads(self):
        import insights
        rows = [{"id": "a1", "m": {"reach": 300}}, {"id": "a2", "m": {"reach": 0}}]
        insights.apply_reach(rows, {"a1": 210}, "m")
        self.assertEqual([r["m"]["reach"] for r in rows], [210, 0])

    def test_apply_reach_without_meta_keeps_the_sum_and_marks_it(self):
        import insights
        rows = [{"id": "a1", "m": {"reach": 300}}]
        insights.apply_reach(rows, None, "m")
        self.assertEqual(rows[0]["m"], {"reach": 300, "reach_summed": True})


class ActivityTests(unittest.TestCase):
    def test_budget_changes_come_as_cents_marked_money_and_other_changes_as_they_are(self):
        budget = {"old_value": {"new_value": 2000, "currency": "USD"}, "new_value": 2400}
        status = {"old_value": "Active", "new_value": "Paused"}
        self.assertEqual([insights_api.activity_values("update_campaign_budget", budget),
                          insights_api.activity_values("update_ad_run_status", status),
                          insights_api.activity_values("ad_review_approved", None)],
                         [{"old": 2000, "new": 2400, "money": True}, {"old": "Active", "new": "Paused", "money": False},
                          {"old": None, "new": None, "money": False}])

    def test_spend_limits_with_a_currency_beside_plain_values_come_as_cents_marked_money(self):
        old_cents, new_cents = 50000, 60000
        limit = {"currency": "USD", "old_value": old_cents, "new_value": new_cents}
        cap = {"old_value": str(old_cents), "new_value": str(new_cents)}
        self.assertEqual([insights_api.activity_values("ad_account_update_spend_limit", limit),
                          insights_api.activity_values("update_campaign_spend_cap", cap)],
                         [{"old": old_cents, "new": new_cents, "money": True}] * 2)

    def test_a_history_line_points_at_its_campaign_ad_set_or_ad_and_nothing_else(self):
        rows = [{"object_type": "CAMPAIGN", "object_id": "c1"}, {"object_type": "AD_SET", "object_id": "s1"},
                {"object_type": "AD", "object_id": "a1"}, {"object_type": "ACCOUNT", "object_id": "act_1"},
                {"object_type": "AD"}, {}]
        self.assertEqual([insights_api.activity_object(r) for r in rows],
                         [{"level": "campaign", "id": "c1"}, {"level": "adset", "id": "s1"}, {"level": "ad", "id": "a1"},
                          None, None, None])


class DailyValuesTests(unittest.TestCase):
    """D1 refactor: one row of Meta's daily ad insights becomes the stored columns, the same way for the hourly
    sync and the nightly restate."""
    ROW = {"date_start": "2026-10-14", "ad_id": "a1", "campaign_id": "c1", "adset_id": "s1", "ad_name": "N1", "spend": "12.34",
           "impressions": "900", "reach": "700", "inline_link_clicks": "11", "clicks": "27",
           "actions": [{"action_type": "video_view", "value": "300"}, {"action_type": "onsite_conversion.lead_grouped", "value": "3"}],
           "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "90"}],
           "video_p25_watched_actions": [{"action_type": "video_view", "value": "200"}],
           "video_p50_watched_actions": [{"action_type": "video_view", "value": "120"}],
           "video_p75_watched_actions": [{"action_type": "video_view", "value": "80"}],
           "video_p100_watched_actions": [{"action_type": "video_view", "value": "60"}]}

    def test_every_column(self):
        self.assertEqual(insights.daily_values(self.ROW), {
            "day": "2026-10-14", "ad_id": "a1", "campaign_id": "c1", "adset_id": "s1", "ad_name": "N1", "spend_cents": 1234,
            "impressions": 900, "reach": 700, "link_clicks": 11, "leads": 3, "clicks_all": 27, "video_3s": 300, "thruplays": 90,
            "video_p25": 200, "video_p50": 120, "video_p75": 80, "video_p100": 60})

    def test_the_insert_takes_them_in_its_column_order(self):
        self.assertEqual(insights.daily_params(insights.daily_values(self.ROW)),
                         ("2026-10-14", "a1", "c1", "s1", "N1", 1234, 900, 700, 11, 3, 27, 300, 90, 200, 120, 80, 60))

    def test_attribution_setting_on_by_default_and_off_when_turned_off(self):
        self.assertEqual([insights.insight_extra(v) for v in (None, "1", "0")],
                         [{"use_unified_attribution_setting": "true"}, {"use_unified_attribution_setting": "true"}, {}])
