import json
import unittest
from datetime import date

import meta_tests as mt

TZ = "America/Los_Angeles"
TODAY = date(2026, 11, 9)


def exp(*arms, **kw):
    return {"id": 7, "name": "Hook test", "hypothesis": "Pain first wins", "arms": list(arms), **kw}


AD_A = {"label": "A", "ad_ids": ["111"], "adset_ids": []}
AD_B = {"label": "B", "ad_ids": ["222"], "adset_ids": []}
SET_A = {"label": "A", "ad_ids": [], "adset_ids": ["901"]}
SET_B = {"label": "B", "ad_ids": [], "adset_ids": ["902"]}


class SplitTests(unittest.TestCase):
    def test_shares_are_whole_numbers_that_add_up_to_100(self):
        self.assertEqual([mt.split(2), mt.split(3), mt.split(7)],
                         [[50, 50], [34, 33, 33], [15, 15, 14, 14, 14, 14, 14]])


class PlanTests(unittest.TestCase):
    def test_two_ads_make_a_creative_test_with_a_test_budget_and_matching_windows(self):
        p = mt.plan(exp(AD_A, AD_B), date(2026, 11, 10), date(2026, 11, 17), 1000, TODAY, TZ)
        start, end = 1794297600, 1794902400  # Nov 10 and Nov 17 2026, midnight Pacific (PST, UTC-8)
        self.assertEqual(p["payload"], {
            "name": "Hook test (Edge Bourne Ads #7)", "description": "Pain first wins", "start_time": start, "end_time": end,
            "type": "SPLIT_TEST_V2", "cells": [{"name": "A", "treatment_percentage": 50, "ads": ["111"]},
                                               {"name": "B", "treatment_percentage": 50, "ads": ["222"]}],
            "creative_test_config": {"daily_budget": 1000}, "cooldown_start_time": start, "observation_end_time": end})
        self.assertEqual((p["kind"], p["days"], p["total_cents"]), ("ad", 7, 7000))

    def test_ad_sets_make_a_split_test_that_spends_nothing_extra(self):
        p = mt.plan(exp(SET_A, SET_B), date(2026, 11, 10), date(2026, 11, 17), None, TODAY, TZ)
        self.assertEqual((p["payload"]["type"], p["payload"]["cells"][1], p["total_cents"]),
                         ("SPLIT_TEST", {"name": "B", "treatment_percentage": 50, "adsets": ["902"]}, None))

    def test_refusals_say_why_and_point_at_the_field(self):
        cases = [
            (exp(AD_A, SET_B), date(2026, 11, 10), date(2026, 11, 17), 1000, None, "all ads or all ad sets"),
            (exp({**AD_A, "ad_ids": ["1", "2"]}, AD_B), date(2026, 11, 10), date(2026, 11, 17), 1000, None, "exactly one ad"),
            (exp(AD_A, AD_B), TODAY, date(2026, 11, 17), 1000, "start_day", "tomorrow at the earliest"),
            (exp(AD_A, AD_B), date(2026, 11, 10), date(2026, 11, 12), 1000, "end_day", "3 to 30 days"),
            (exp(AD_A, AD_B), date(2026, 11, 10), date(2026, 12, 20), 1000, "end_day", "3 to 30 days"),
            (exp(AD_A, AD_B), date(2026, 11, 10), date(2026, 11, 17), 50, "budget", "at least $1"),
        ]
        for e, start, end, budget, field, words in cases:
            with self.subTest(words=words):
                with self.assertRaises(mt.PlanError) as cm:
                    mt.plan(e, start, end, budget, TODAY, TZ)
                self.assertEqual((cm.exception.field, words in str(cm.exception)), (field, True))

    def test_a_test_budget_over_twice_the_campaign_budget_is_refused(self):
        with self.assertRaises(mt.PlanError) as cm:
            mt.plan(exp(AD_A, AD_B), date(2026, 11, 10), date(2026, 11, 17), 4100, TODAY, TZ, max_budget_cents=4000)
        self.assertEqual(str(cm.exception), "Keep the test budget at $40.00 a day or less (twice the campaign's daily budget)")

    def test_graph_form_sends_lists_and_objects_as_json(self):
        form = mt.graph_form({"name": "x", "start_time": 5, "cells": [{"a": 1}], "creative_test_config": {"daily_budget": 9}})
        self.assertEqual(form, {"name": "x", "start_time": 5, "cells": '[{"a": 1}]', "creative_test_config": '{"daily_budget": 9}'})


class ResultTests(unittest.TestCase):
    def test_results_arrive_as_json_strings_and_are_merged(self):
        objectives = [{"id": "1", "results": [json.dumps({"high_performer_ids": ["222"]}), {"confidence_by_ad_object_id": {"111": 0.12, "222": 0.88}}]}]
        self.assertEqual(mt.merge_results(objectives), {"high_performer_ids": ["222"], "confidence_by_ad_object_id": {"111": 0.12, "222": 0.88}})

    def test_a_creative_test_result_is_told_in_the_arms_names(self):
        v = mt.meta_verdict({"high_performer_ids": ["222"], "confidence_by_ad_object_id": {"111": 0.12, "222": 0.88},
                             "winner_ad_object_id": None, "winner_confidence": None}, [AD_A, AD_B])
        self.assertEqual(v, {"winner": None, "confidence": None, "high_performers": ["B"], "by_arm": {"A": 12, "B": 88},
                             "note": "Meta marks B as the high performer (A 12%, B 88%)."})

    def test_a_split_test_winner_is_named(self):
        v = mt.meta_verdict({"winner_ad_object_id": "901", "winner_confidence": 0.93}, [SET_A, SET_B])
        self.assertEqual((v["winner"], v["note"]), ("A", "Meta's pick: A (93% confidence)."))

    def test_no_result_yet(self):
        self.assertEqual(mt.meta_verdict({}, [AD_A, AD_B])["note"], "Meta hasn't picked a winner yet.")

    def test_state_follows_the_schedule_and_an_early_end(self):
        s = {"start_time": 100, "end_time": 200}
        self.assertEqual([mt.study_state(s, 50), mt.study_state(s, 150), mt.study_state(s, 250), mt.study_state({**s, "ended_early_at": "x"}, 150)],
                         ["scheduled", "running", "ended", "ended"])



class BookingUnsettledTest(unittest.TestCase):
    """A booking cut off mid-request (a restart) must be recoverable, not 'being booked' forever."""
    AT = "2026-11-09T10:00:00+00:00"
    AT_TS = 1794218400  # AT as a timestamp

    def test_an_unanswered_or_abandoned_booking_needs_a_look(self):
        cases = [({"creating": True, "unknown": True, "at": self.AT}, self.AT_TS, True),
                 ({"creating": True, "at": self.AT}, self.AT_TS + 60, False),
                 ({"creating": True, "at": self.AT}, self.AT_TS + 601, True),
                 ({"creating": True}, self.AT_TS, True),
                 ({"id": "9", "creating": True, "unknown": True}, self.AT_TS + 9999, False),
                 (None, self.AT_TS, False)]
        self.assertEqual([mt.booking_unsettled(s, now) for s, now, _ in cases], [want for _, _, want in cases])


if __name__ == "__main__":
    unittest.main()
