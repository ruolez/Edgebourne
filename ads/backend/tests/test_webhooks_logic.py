import unittest

import webhooks


def payload(field, value, account="act_1025971549903293"):
    return {"object": "ad_account", "entry": [{"id": account, "time": 1762790000, "changes": [{"field": field, "value": value}]}]}


class ParseAdAccountTests(unittest.TestCase):
    def test_with_issues_object(self):
        got = webhooks.parse_ad_account(payload("with_issues_ad_objects", {
            "id": "120252672229400312", "level": "AD", "error_code": 1487, "error_summary": "Payment failed",
            "error_message": "Update the payment method."}))
        self.assertEqual(got, [{"account": "1025971549903293", "field": "with_issues_ad_objects", "object_id": "120252672229400312",
                                "level": "ad", "detail": {"error_code": 1487, "error_summary": "Payment failed",
                                                          "error_message": "Update the payment method."}}])

    def test_in_process_object_for_an_ad_set(self):
        got = webhooks.parse_ad_account(payload("in_process_ad_objects", {"id": "1202", "level": "AD_SET", "status_name": "Active"}))
        self.assertEqual([(g["object_id"], g["level"]) for g in got], [("1202", "adset")])

    def test_effective_status_change_names_the_object(self):
        got = webhooks.parse_ad_account(payload("field_changed", {"object_id": "1203", "object_type": "campaign",
                                                                  "changed_fields": ["effective_status"]}, account="1025971549903293"))
        self.assertEqual([(g["account"], g["object_id"], g["level"]) for g in got], [("1025971549903293", "1203", "campaign")])

    def test_a_creative_level_object_is_kept_for_the_ads_that_use_it(self):
        got = webhooks.parse_ad_account(payload("with_issues_ad_objects", {"id": "77", "level": "CREATIVE"}))
        self.assertEqual([(g["object_id"], g["level"]) for g in got], [("77", "creative")])

    def test_fields_that_name_no_object_are_kept_without_one(self):
        got = webhooks.parse_ad_account(payload("ad_recommendations", {"recommendations": []}))
        self.assertEqual([(g["field"], g["object_id"], g["level"]) for g in got], [("ad_recommendations", None, None)])

    def test_page_payloads_are_not_ad_account_ones(self):
        self.assertEqual(webhooks.parse_ad_account({"object": "page", "entry": [{"id": "1", "changes": [{"field": "leadgen", "value": {}}]}]}), [])


class GroupTests(unittest.TestCase):
    def test_refetch_plan_groups_ids_by_level_once_each(self):
        rows = [{"object_id": "a1", "level": "ad"}, {"object_id": "a1", "level": "ad"}, {"object_id": "s1", "level": "adset"},
                {"object_id": None, "level": None}, {"object_id": "k9", "level": "creative"}]
        self.assertEqual(webhooks.refetch_plan(rows), {"ad": ["a1"], "adset": ["s1"], "creative": ["k9"]})


if __name__ == "__main__":
    unittest.main()
