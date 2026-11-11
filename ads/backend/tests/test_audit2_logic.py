"""Audit 2 (2026-11-10): the pure parts of the fixes."""
import traceback
import unittest
from datetime import datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import requests

import account_info
import desk_api
import meta_client
import notify
import report_logic as rl

TOKEN = "EAAB-secret-token-123"


class MetaClientNetworkTest(unittest.TestCase):
    def call(self, exc, method="GET"):
        with mock.patch.object(meta_client.requests, "request", side_effect=exc), \
                mock.patch.object(meta_client.account_ctx, "current", return_value=999):
            try:
                meta_client._call(method, "act_1/ads", TOKEN)
            except meta_client.MetaError as err:
                return err
        self.fail("no MetaError")

    def test_a_network_error_never_carries_the_token(self):
        err = self.call(requests.ConnectionError(f"HTTPSConnectionPool: /act_1/ads?access_token={TOKEN}"))
        printed = "".join(traceback.format_exception(err))
        self.assertEqual((TOKEN in str(err), TOKEN in printed), (False, False))

    def test_a_write_that_timed_out_is_marked_unknown(self):
        self.assertEqual([self.call(requests.Timeout("x"), "POST").unknown, self.call(requests.Timeout("x"), "GET").unknown],
                         [True, False])

    def test_metas_codes_in_plain_words(self):
        self.assertEqual([("token" in meta_client.plain(190, "x").lower()), ("slow down" in meta_client.plain(17, "x")),
                          meta_client.plain(100, "Invalid parameter")], [True, True, "Invalid parameter"])

    def test_metas_own_explanation_and_subcode_are_kept(self):
        resp = mock.Mock(status_code=400, json=lambda: {"error": {"message": "Invalid parameter", "code": 100, "error_subcode": 1487390,
                                                                  "error_user_title": "Creative can't be used", "error_user_msg": "Pick another creative."}})
        with self.assertRaises(meta_client.MetaError) as cm:
            meta_client._raise_for(resp)
        self.assertEqual(str(cm.exception), "Invalid parameter: Creative can't be used. Pick another creative. (Meta code 100, subcode 1487390)")

    def test_a_bare_error_stays_as_meta_wrote_it(self):
        resp = mock.Mock(status_code=400, json=lambda: {"error": {"message": "Invalid parameter", "code": 100}})
        with self.assertRaises(meta_client.MetaError) as cm:
            meta_client._raise_for(resp)
        self.assertEqual(str(cm.exception), "Invalid parameter")

    def test_a_rate_limit_pauses_that_account(self):
        resp = mock.Mock(status_code=400, json=lambda: {"error": {"message": "User request limit reached", "code": 17}})
        with mock.patch.object(meta_client.requests, "request", return_value=resp) as req, \
                mock.patch.object(meta_client.account_ctx, "current", return_value=4242):
            for _ in range(2):
                with self.assertRaises(meta_client.MetaError):
                    meta_client._call("GET", "act_1/ads", TOKEN)
        meta_client._cooldown.pop(4242, None)
        self.assertEqual(req.call_count, 1)  # the second call waited instead of asking Meta again


class NotifyLinkTest(unittest.TestCase):
    def test_links_name_their_account_before_the_fragment(self):
        with mock.patch("config.APP_BASE_URL", "https://ads.example.com"):
            self.assertEqual([notify.link("/leads.html#lead=7", 2), notify.link("/ad.html?id=5", 1), notify.link(None, 3)],
                             ["https://ads.example.com/leads.html?acct=2#lead=7", "https://ads.example.com/ad.html?id=5&acct=1",
                              "https://ads.example.com/home.html?acct=3"])


class ReportEmailDueTest(unittest.TestCase):
    LA = ZoneInfo("America/Los_Angeles")

    def at(self, iso):
        return datetime.fromisoformat(iso).replace(tzinfo=self.LA)

    def test_weekly_is_due_from_monday_8am_until_sent(self):
        monday_7, monday_9, wednesday = self.at("2026-11-09T07:00"), self.at("2026-11-09T09:00"), self.at("2026-11-11T10:00")
        key = "week:2026-11-02"
        self.assertEqual([rl.email_due("weekly", monday_7, None), rl.email_due("weekly", monday_9, None)[3],
                          rl.email_due("weekly", wednesday, None)[3], rl.email_due("weekly", wednesday, key)],
                         [None, key, key, None])

    def test_off_sends_nothing(self):
        self.assertIsNone(rl.email_due(None, self.at("2026-11-09T09:00"), None))


class AccountClockTest(unittest.TestCase):
    def test_evening_in_los_angeles_is_still_today_there(self):
        utc_evening = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)  # 7:30 PM Nov 9 in Los Angeles
        self.assertEqual([str(account_info.today(utc_evening, ZoneInfo("America/Los_Angeles"))),
                          str(account_info.yesterday(utc_evening, ZoneInfo("America/Los_Angeles")))],
                         ["2026-11-09", "2026-11-08"])

    def test_currencies_without_cents_are_refused(self):
        self.assertEqual([account_info.currency_problem(c) is None for c in ("USD", "EUR", "JPY", "krw")],
                         [True, True, False, False])

    def test_time_zone_from_the_snapshot_with_a_safe_fallback(self):
        self.assertEqual([account_info.tz_name({"timezone": "America/New_York"}), account_info.tz_name({"timezone": "Nowhere/Else"})],
                         ["America/New_York", account_info.config.ACCOUNT_TZ])


class MacHelperTest(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        self.assertEqual([desk_api.version_tuple("1.10") > desk_api.version_tuple("1.6"), desk_api.version_tuple("x")],
                         [True, (0, 0)])

    def test_sign_in_trouble_is_recognised(self):
        self.assertEqual([desk_api.claude_sign_in_problem("Claude stopped. Last output: OAuth token has expired"),
                          desk_api.claude_sign_in_problem("Meta refused: invalid parameter")], [True, False])


class AdviceAmountTest(unittest.TestCase):
    def test_a_budget_suggestion_without_whole_cents_cannot_be_applied_here(self):
        import advice
        rec = {"type": "SCALE_GOOD_CAMPAIGN", "recommendation_signature": "sig", "object_ids": ["c1"],
               "recommendation_data": {"additional_budget": "50.00"}}
        clear = {**rec, "recommendation_data": {"additional_budget": 500}}
        out, ok = advice.normalize(rec, {"c1": 2000}), advice.normalize(clear, {"c1": 2000})
        self.assertEqual([(out["can_apply"], out["budget"]["to"]), (ok["can_apply"], ok["budget"]["to"])],
                         [(False, None), (True, 2500)])


if __name__ == "__main__":
    unittest.main()
