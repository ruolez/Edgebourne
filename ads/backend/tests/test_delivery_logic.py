import unittest

import delivery

REJECTED = {"global": {"PERSONAL_ATTRIBUTES": "Ads can't imply knowledge of personal attributes."},
            "placement_specific": {"instagram": {"PROFANITY": "No swearing on Instagram."}}}
ISSUE = [{"error_code": 1487, "error_summary": "Ad set budget too low", "error_message": "Raise the budget to deliver."}]


def ad(**kw):
    base = {"id": "a1", "status": "ACTIVE", "effective_status": "ACTIVE", "review_feedback": None, "issues": None}
    base.update(kw)
    return base


def days(on, of=14):
    return [{"day": f"2026-11-{i + 1:02d}", "on": i < on} for i in range(of)]


class ReasonsTests(unittest.TestCase):
    def test_meta_review_reasons_come_first_then_issues_each_once(self):
        got = delivery.reasons(ad(review_feedback=REJECTED, issues=ISSUE + ISSUE))
        self.assertEqual(got, ["Ads can't imply knowledge of personal attributes.", "Instagram: No swearing on Instagram.",
                               "Raise the budget to deliver."])

    def test_stored_json_text_and_a_single_issue_object_are_read_too(self):
        got = delivery.reasons(ad(review_feedback='{"global": {"X": "Too much text."}}', issues='{"error_summary": "Billing"}'))
        self.assertEqual(got, ["Too much text.", "Billing"])

    def test_nothing_reported_means_no_reasons(self):
        self.assertEqual(delivery.reasons(ad(review_feedback={}, issues=[])), [])

    def test_unreadable_text_is_ignored_not_shown_raw(self):
        self.assertEqual(delivery.reasons(ad(review_feedback="{not json", issues="also not json")), [])


class ExplainTests(unittest.TestCase):
    def test_delivering_counts_the_days_it_spent(self):
        got = delivery.explain(ad(), track=days(9))
        self.assertEqual((got["tone"], got["headline"], got["days_on"], got["fix"], got["learning"]), ("ok", "Delivering", 9, None, None))
        self.assertIn("9 of the last 14 days", got["line"])

    def test_delivering_with_no_spend_yet_says_so_instead_of_zero_days(self):
        got = delivery.explain(ad(), track=days(0))
        self.assertNotIn("0 of", got["line"])
        self.assertIn("hasn't spent", got["line"])

    def test_learning_is_named_only_while_it_delivers(self):
        self.assertEqual(delivery.explain(ad(), learning_stage="FAIL", track=days(3))["learning"], "learning_limited")
        self.assertEqual(delivery.explain(ad(), learning_stage="LEARNING", track=days(3))["learning"], "learning")
        self.assertIsNone(delivery.explain(ad(status="PAUSED", effective_status="PAUSED"), learning_stage="LEARNING")["learning"])

    def test_switched_off_points_to_the_switch(self):
        got = delivery.explain(ad(status="PAUSED", effective_status="PAUSED"))
        self.assertEqual((got["tone"], got["headline"], got["fix"]), ("", "Off", "switch"))

    def test_off_because_of_the_campaign_or_ad_set_points_there(self):
        self.assertEqual(delivery.explain(ad(effective_status="CAMPAIGN_PAUSED"))["fix"], "campaign")
        self.assertEqual(delivery.explain(ad(effective_status="ADSET_PAUSED"))["fix"], "adset")
        self.assertIn("campaign is off", delivery.explain(ad(effective_status="CAMPAIGN_PAUSED"))["line"])

    def test_in_review_is_a_wait_not_a_problem(self):
        for s in ("IN_PROCESS", "PENDING_REVIEW"):
            got = delivery.explain(ad(effective_status=s))
            self.assertEqual((got["tone"], got["headline"], got["fix"]), ("warn", "In review", None))

    def test_rejected_carries_meta_reasons_and_offers_a_fix(self):
        got = delivery.explain(ad(effective_status="DISAPPROVED", review_feedback=REJECTED))
        self.assertEqual((got["tone"], got["headline"], got["fix"], len(got["reasons"])), ("bad", "Rejected", "polish", 2))

    def test_issues_and_billing_are_problems_with_their_own_next_step(self):
        self.assertEqual(delivery.explain(ad(effective_status="WITH_ISSUES", issues=ISSUE))["fix"], "polish")
        got = delivery.explain(ad(effective_status="PENDING_BILLING_INFO"))
        self.assertEqual((got["tone"], got["fix"]), ("bad", "billing"))

    def test_archived_and_deleted_cannot_be_switched_on(self):
        for s in ("ARCHIVED", "DELETED"):
            got = delivery.explain(ad(status=s, effective_status=s))
            self.assertEqual((got["tone"], got["fix"]), ("", None))
            self.assertNotIn("switch", got["line"].lower())

    def test_every_meta_status_has_plain_words(self):
        for s in delivery.HEADLINES:
            got = delivery.explain(ad(effective_status=s))
            self.assertTrue(got["headline"] and got["line"] and "_" not in got["line"], s)

    def test_an_unknown_status_falls_back_to_readable_words(self):
        got = delivery.explain(ad(effective_status="SOMETHING_NEW"))
        self.assertEqual(got["headline"], "Something new")


if __name__ == "__main__":
    unittest.main()
