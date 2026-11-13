"""Audit 3: who hears about an account's leads and alerts, and which account owns a Meta asset."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.setdefault("WORKERS_ENABLED", "0")

import requests  # noqa: E402

import account_ctx  # noqa: E402
import leads  # noqa: E402
import mailer  # noqa: E402
import notify  # noqa: E402
import settings_api  # noqa: E402
import settings_store  # noqa: E402
import telegram  # noqa: E402
import webhooks  # noqa: E402

OWNER = {"id": 1, "name": "Eugene", "email": "eugene@edgebourne.test", "role": "admin", "account_id": None, "notify_new_leads": True}
ADMIN_1 = {"id": 5, "name": "Ann", "email": "ann@edgebourne.test", "role": "admin", "account_id": 1, "notify_new_leads": False}
ADMIN_2 = {"id": 4, "name": "Bea", "email": "bea@client.test", "role": "admin", "account_id": 2, "notify_new_leads": True}
MEMBER_2 = {"id": 7, "name": "Cal", "email": "cal@client.test", "role": "member", "account_id": 2, "notify_new_leads": True}
# What the users table returns: it has no row-level security, so every account's people come back.
EVERYONE = [OWNER, ADMIN_1, ADMIN_2, MEMBER_2]


class RecipientsPerAccountTest(unittest.TestCase):
    def in_account(self, acct, fn, rows):
        with account_ctx.use(acct), mock.patch.object(notify.db, "query", return_value=rows), \
                mock.patch.object(leads.db, "query", return_value=rows):
            return fn()

    def test_alerts_reach_only_the_owners_and_admins_of_that_account(self):
        admins = [u for u in EVERYONE if u["role"] == "admin"]
        self.assertEqual(
            [self.in_account(1, notify.admin_ids, admins), self.in_account(2, notify.admin_ids, admins)],
            [[OWNER["id"], ADMIN_1["id"]], [OWNER["id"], ADMIN_2["id"]]])

    def test_lead_emails_go_to_this_accounts_people_who_want_them(self):
        lead = {"campaign_id": "c1"}
        self.assertEqual(
            [self.in_account(1, lambda: leads.recipients_for(lead), EVERYONE),
             self.in_account(2, lambda: leads.recipients_for(lead), EVERYONE)],
            [[OWNER["email"]], [OWNER["email"], ADMIN_2["email"], MEMBER_2["email"]]])

    def test_people_a_lead_can_be_given_to_stay_in_its_account(self):
        self.assertEqual(
            [self.in_account(1, lambda: leads.staff_for("c1"), EVERYONE), self.in_account(2, lambda: leads.staff_for("c1"), EVERYONE)],
            [[{"id": 1, "name": "Eugene"}, {"id": 5, "name": "Ann"}],
             [{"id": 1, "name": "Eugene"}, {"id": 4, "name": "Bea"}, {"id": 7, "name": "Cal"}]])

    def test_each_recipient_gets_a_message_of_their_own(self):
        lead = {"id": 3, "campaign_id": "c1", "full_name": "Ann", "business_type": None, "phone": None, "email": None,
                "ad_name": None, "is_test": False}
        with mock.patch.object(leads.mailer, "configured", return_value=True), mock.patch.object(notify, "queue") as queue:
            self.in_account(2, lambda: leads.queue_emails(lead), EVERYONE)
        self.assertEqual([(c.args[0], c.args[1], c.kwargs["dedupe_key"]) for c in queue.call_args_list],
                         [(OWNER["id"], "email", "lead:3:email:1"), (ADMIN_2["id"], "email", "lead:3:email:4"),
                          (MEMBER_2["id"], "email", "lead:3:email:7")])


EB_PAGE, EB_ACT, EB_DATASET = "1404203629446490", "1025971549903293", "1821497329119793"
DEFAULTS = {"meta_page_id": EB_PAGE, "meta_ad_account_id": EB_ACT, "meta_dataset_id": EB_DATASET}


class AccountValuesTest(unittest.TestCase):
    def values(self, key, rows):
        with mock.patch.dict(settings_store.config.META_DEFAULTS, DEFAULTS, clear=True):
            return settings_store.account_values(key, rows)

    def test_account_1s_built_in_default_counts_as_its_value(self):
        self.assertEqual(
            [self.values("meta_page_id", []),
             self.values("meta_page_id", [{"key": "meta_page_id", "value": ""}, {"key": "meta_page_id@2", "value": "222"}]),
             self.values("meta_page_id", [{"key": "meta_page_id", "value": "111"}, {"key": "meta_page_id@12", "value": ""}]),
             self.values("meta_business_id", [{"key": "meta_business_id@3", "value": "333"}])],
            [{1: EB_PAGE}, {1: EB_PAGE, 2: "222"}, {1: "111"}, {3: "333"}])


def holders(table):
    return lambda key: table.get(key, [])


class PageRoutingTest(unittest.TestCase):
    def route(self, page, table):
        with mock.patch.object(settings_store, "meta_holders", side_effect=holders(table)):
            return webhooks.account_for_page(page)

    def test_edge_bournes_default_page_stays_with_account_1_even_when_another_account_names_it(self):
        self.assertEqual(self.route(EB_PAGE, {"meta_page_id": [(1, False, EB_PAGE), (2, False, EB_PAGE)]}), 1)

    def test_a_closed_account_never_wins_and_the_order_is_by_account_number(self):
        table = {"meta_page_id": [(1, False, EB_PAGE), (2, True, "777"), (10, False, "777"), (11, False, "777")]}
        self.assertEqual([self.route("777", table), self.route("888", table)], [10, 1])

    def test_a_page_only_a_closed_account_names_goes_nowhere_but_an_unknown_page_goes_to_account_1(self):
        table = {"meta_page_id": [(1, False, EB_PAGE), (2, True, "777")]}
        self.assertEqual([self.route("777", table), self.route("888", table)], [None, 1])

    def test_a_lead_for_a_closed_accounts_page_is_not_queued_under_account_1(self):
        change = {"field": "leadgen", "value": {"leadgen_id": "L1", "page_id": "777"}}
        payload = {"object": "page", "entry": [{"id": "777", "changes": [change]}]}
        with mock.patch.object(settings_store, "meta_holders", side_effect=holders({"meta_page_id": [(1, False, EB_PAGE), (2, True, "777")]})), \
                mock.patch.object(webhooks.db, "execute") as execute, mock.patch.object(webhooks.jobs, "wake"):
            result = webhooks.queue_events(payload)
        self.assertEqual([result, execute.call_args_list], [{"ok": True, "received": 0}, []])


class UsedElsewhereTest(unittest.TestCase):
    TABLE = {"meta_page_id": [(1, False, EB_PAGE), (7, True, "777")], "meta_ad_account_id": [(1, False, EB_ACT)],
             "meta_dataset_id": [(1, False, EB_DATASET)]}

    def check(self, acct, data):
        with account_ctx.use(acct), mock.patch.object(settings_store, "meta_holders", side_effect=holders(self.TABLE)), \
                mock.patch("accounts_api.name_of", side_effect=lambda a: {1: "Edge Bourne", 7: "Old Client"}[a]):
            return settings_api.used_elsewhere(data)

    def test_another_account_cannot_take_edge_bournes_default_page_ad_account_or_dataset(self):
        self.assertEqual(
            [self.check(2, {"meta_page_id": EB_PAGE}), self.check(2, {"meta_ad_account_id": f"act_{EB_ACT}"}),
             self.check(2, {"meta_dataset_id": EB_DATASET})],
            [("meta_page_id", "Another account (Edge Bourne) already uses this Page."),
             ("meta_ad_account_id", "Another account (Edge Bourne) already uses this ad account."),
             ("meta_dataset_id", "Another account (Edge Bourne) already uses this dataset.")])

    def test_a_closed_accounts_page_is_refused_with_a_way_out(self):
        self.assertEqual(self.check(2, {"meta_page_id": "777"}),
                         ("meta_page_id", "Old Client (a closed account) still holds this Page: reopen that account instead."))

    def test_resaving_a_value_the_account_already_shares_is_not_refused_but_changing_to_it_is(self):
        table = {"meta_page_id": [(2, False, "777"), (3, False, "555"), (7, True, "777")]}
        with mock.patch.object(settings_store, "meta_holders", side_effect=holders(table)), \
                mock.patch("accounts_api.name_of", side_effect=lambda a: {2: "Client", 7: "Old Client"}[a]):
            with account_ctx.use(2):
                kept = settings_api.used_elsewhere({"meta_page_id": "777"})
            with account_ctx.use(3):
                moved = settings_api.used_elsewhere({"meta_page_id": "777"})
        self.assertEqual([kept, moved],
                         [None, ("meta_page_id", "Another account (Client) already uses this Page.")])

    def test_an_account_may_keep_its_own_values(self):
        self.assertEqual([self.check(1, {"meta_page_id": EB_PAGE, "meta_ad_account_id": EB_ACT}), self.check(2, {"meta_page_id": "555"})],
                         [None, None])


class TelegramErrorTest(unittest.TestCase):
    def test_a_network_error_never_carries_the_bot_token(self):
        exc = requests.ConnectionError("HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded "
                                       "with url: /bot123456:SECRETTOKEN/sendMessage")
        with mock.patch.object(telegram.requests, "post", side_effect=exc):
            with self.assertRaises(telegram.TelegramError) as caught:
                telegram.call("sendMessage", {}, tok="123456:SECRETTOKEN")
        self.assertEqual(str(caught.exception), "Telegram didn't answer (ConnectionError)")

    def test_a_blocked_bot_or_a_lost_chat_means_the_link_is_gone(self):
        cases = [("Forbidden: bot was blocked by the user", 403), ("Bad Request: chat not found", 400),
                 ("Bad Request: message is too long", 400), ("Unauthorized", 401), ("Telegram didn't answer (Timeout)", None)]
        self.assertEqual([telegram.chat_gone(telegram.TelegramError(m, s)) for m, s in cases], [True, True, False, False, False])


class TelegramFallbackTest(unittest.TestCase):
    ROW = {"id": 9, "user_id": 4, "channel": "telegram", "kind": "reminder", "ref": "3", "dedupe_key": "reminder:1h:3:4",
           "title": "Ann waited 1h", "lines": ["Phone: 555"], "url": "https://x/leads.html", "button": "Open the lead",
           "attempts": 0, "created_at": datetime(2026, 11, 11, tzinfo=timezone.utc)}

    BLOCKED = "Forbidden: bot was blocked by the user"

    def run_once(self, error, channels, **row):
        with mock.patch.object(notify, "settle_interrupted"), mock.patch.object(notify, "claim", return_value=True), \
                mock.patch.object(notify.db, "query", return_value=[{**self.ROW, **row}]), \
                mock.patch.object(notify, "_deliver", side_effect=error), \
                mock.patch.object(notify, "reach", return_value=channels), \
                mock.patch.object(notify.db, "execute") as execute:
            notify.process_pending(now=self.ROW["created_at"] + timedelta(minutes=1))
        inserted = [c.args[1] for c in execute.call_args_list if "INSERT INTO notifications" in c.args[0]]
        errors = [c.args[1][1] for c in execute.call_args_list if c.args[0].startswith("UPDATE notifications SET attempts")]
        return inserted, errors

    def test_a_person_who_blocked_the_bot_gets_it_on_their_next_channel(self):
        self.assertEqual(self.run_once(telegram.TelegramError(self.BLOCKED, 403), [(4, "push")]),
                         ([(4, "push", "reminder", "3", "reminder:1h:3:4:push", "Ann waited 1h", '["Phone: 555"]',
                            "https://x/leads.html", "Open the lead")], [f"{self.BLOCKED}; sent by push instead"]))

    def test_nobody_is_told_it_went_another_way_when_no_other_channel_took_it(self):
        self.assertEqual([self.run_once(telegram.TelegramError(self.BLOCKED, 403), []),
                          self.run_once(telegram.TelegramError(self.BLOCKED, 403), [(4, "email")], kind="lead")],
                         [([], [self.BLOCKED]), ([], [self.BLOCKED])])

    def test_a_passing_telegram_outage_is_retried_on_telegram(self):
        self.assertEqual(self.run_once(telegram.TelegramError("Telegram didn't answer (Timeout)"), [(4, "push")])[0], [])


class MailHeaderTest(unittest.TestCase):
    SMTP = {"host": "mail.test", "port": 25, "security": "none", "username": "", "password": "",
            "from_email": "ads@edgebourne.test", "from_name": "Edge\nBourne Ads", "source": "own"}

    def test_a_line_break_in_a_subject_is_folded_into_a_space(self):
        with mock.patch.object(mailer, "smtp_settings", return_value=dict(self.SMTP)), \
                mock.patch.object(mailer.smtplib, "SMTP") as smtp:
            mailer.send("ann@example.com", "New lead: Ann\r\nWholesale\nbakery", "text")
        msg = smtp.return_value.send_message.call_args.args[0]
        self.assertEqual((msg["Subject"], msg["From"]), ("New lead: Ann Wholesale bakery", "Edge Bourne Ads <ads@edgebourne.test>"))


class LeadQueueTest(unittest.TestCase):
    def test_a_lead_already_filed_under_another_account_is_not_a_crash(self):
        # The insert finds the id taken (another account has it) and returns nothing; the lookup can't see that row.
        cur = mock.MagicMock()
        cur.fetchone.return_value = None
        tx = mock.MagicMock()
        tx.__enter__.return_value = cur
        with mock.patch.object(leads.db, "transaction", return_value=tx), mock.patch.object(leads.db, "execute", return_value=None), \
                mock.patch.object(leads.db, "query", return_value=None), mock.patch("lead_quality_store.junk_flags_on", return_value=True), \
                mock.patch("lead_quality_store.repeat_check_on", return_value=True):
            self.assertEqual(leads.store_lead({"id": "991", "field_data": []}), (None, False))
        self.assertIn("ON CONFLICT (meta_lead_id) DO NOTHING", cur.execute.call_args_list[1].args[0])

    def test_one_broken_event_does_not_hold_up_the_rest(self):
        now = datetime.now(timezone.utc)
        events = [{"id": 1, "leadgen_id": "L1", "received_at": now, "attempts": 0}, {"id": 2, "leadgen_id": "L2", "received_at": now, "attempts": 0},
                  {"id": 3, "leadgen_id": "L3", "received_at": now - timedelta(hours=25), "attempts": 9}]
        with mock.patch.object(leads.db, "query", return_value=events), mock.patch.object(leads.meta_client, "page_token", return_value="tok"), \
                mock.patch.object(leads, "fetch_and_store", side_effect=[TypeError("boom"), (None, False), TypeError("boom")]), \
                mock.patch.object(leads, "log_activity"), mock.patch.object(leads.log, "exception"), \
                mock.patch.object(leads, "datetime", wraps=datetime) as dt, \
                mock.patch.object(leads.db, "execute") as execute:
            dt.now.return_value = now
            leads.process_pending_events()
        self.assertEqual([c.args[1] for c in execute.call_args_list], [
            ("Couldn't store this lead (TypeError)", 1, now + timedelta(minutes=1), 1),
            ("This lead is already filed under another account", 2),
            ("Gave up: Couldn't store this lead (TypeError)", 3)])


if __name__ == "__main__":
    unittest.main()
