import unittest

import account_ctx
import settings_store


class StoredKeyTests(unittest.TestCase):
    def test_account_1_keeps_plain_keys_others_get_a_suffix_and_global_keys_stay_global(self):
        self.assertEqual(settings_store.stored_key("meta_page_id"), "meta_page_id")
        with account_ctx.use(7):
            self.assertEqual((settings_store.stored_key("meta_page_id"), settings_store.stored_key("smtp_host"),
                              settings_store.stored_key("meta_app_secret")), ("meta_page_id@7", "smtp_host", "meta_app_secret"))
        self.assertEqual(settings_store.stored_key("alert_rules", account_id=3), "alert_rules@3")

    def test_the_context_is_restored_after_use(self):
        with account_ctx.use(4):
            with account_ctx.use(5):
                self.assertEqual(account_ctx.current(), 5)
            self.assertEqual(account_ctx.current(), 4)
        self.assertEqual(account_ctx.current(), account_ctx.DEFAULT)


class ClientAllowTests(unittest.TestCase):
    def test_a_client_may_only_manage_their_own_sign_in_notifications_read_marks_and_views(self):
        import accounts_api
        ok = ["/api/auth/logout", "/api/auth/password", "/api/auth/me", "/api/me/push", "/api/me/push/3", "/api/me/push/test",
              "/api/me/telegram", "/api/me/telegram/link", "/api/me/telegram/test", "/api/inbox/read", "/api/views", "/api/views/12"]
        no = ["/api/leads/1", "/api/ads/ad/1/tags", "/api/accounts", "/api/auth/password/reset", "/api/settings/meta",
              "/api/inbox/read/all", "/api/views/12/share", "/api/views/x", "/api/settings/telegram", "/api/me/telegramx"]
        self.assertEqual([bool(accounts_api.CLIENT_MAY.match(p)) for p in ok], [True] * len(ok))
        self.assertEqual([bool(accounts_api.CLIENT_MAY.match(p)) for p in no], [False] * len(no))

    def test_with_client_access_on_a_client_may_work_a_lead_and_nothing_around_it(self):
        import accounts_api
        ok = ["/api/leads/7", "/api/leads/7/notes", "/api/leads/7/calls", "/api/leads/7/events/12/undo", "/api/leads/7/not-junk"]
        no = ["/api/leads", "/api/leads/7/reply", "/api/leads/7/events/12", "/api/leads/7/calls/3", "/api/leads/x/calls", "/api/bookings/1/link"]
        self.assertEqual([bool(accounts_api.CLIENT_LEADS.match(p)) for p in ok + no], [True] * len(ok) + [False] * len(no))


class OverviewTotalsTests(unittest.TestCase):
    def row(self, spend, leads, currency="USD"):
        return {"currency": currency, "spend_cents": spend, "leads": leads}

    def test_accounts_in_different_currencies_are_never_added_up(self):
        import adaccounts
        self.assertEqual(adaccounts.overview_totals([self.row(14012, 9), self.row(5000, 2, "EUR")]), {"same_currency": False, "totals": None})

    def test_the_cost_per_lead_of_the_total_is_total_spend_over_total_leads_not_an_average_of_averages(self):
        import adaccounts
        # $100 for 1 lead and $20 for 4 leads: $24.00 per lead, not ($100 + $5) / 2.
        got = adaccounts.overview_totals([self.row(10000, 1), self.row(2000, 4)])
        self.assertEqual(got, {"same_currency": True, "totals": {"spend_cents": 12000, "leads": 5, "cpl_cents": 2400}})

    def test_no_leads_means_no_cost_per_lead_and_no_rows_means_no_totals(self):
        import adaccounts
        self.assertEqual((adaccounts.overview_totals([self.row(300, 0), self.row(200, 0)]), adaccounts.overview_totals([])),
                         ({"same_currency": True, "totals": {"spend_cents": 500, "leads": 0, "cpl_cents": None}}, {"same_currency": True, "totals": None}))


if __name__ == "__main__":
    unittest.main()
