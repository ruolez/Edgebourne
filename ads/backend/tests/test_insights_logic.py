import unittest

import insights
import insights_api


class ActionValueTests(unittest.TestCase):
    def test_sums_one_type_or_everything(self):
        actions = [{"action_type": "video_view", "value": "120"}, {"action_type": "lead", "value": "2"},
                   {"action_type": "video_view", "value": "5"}]
        self.assertEqual((insights.action_value(actions, "video_view"), insights.action_value(actions), insights.action_value(None)),
                         (125, 127, 0))


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
