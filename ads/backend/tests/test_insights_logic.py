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
