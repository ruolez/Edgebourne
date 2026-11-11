"""Every stored lead is announced once (email, phone alerts, automatic reply), whichever path stored
it; organic form leads are real leads; a failing lead ping waits longer each time."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.setdefault("WORKERS_ENABLED", "0")

import leads  # noqa: E402
import meta_client  # noqa: E402
import notify  # noqa: E402
import replies  # noqa: E402
import reports_api  # noqa: E402

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)
LEAD = {"id": 7, "full_name": "Ann Lee", "phone": "+15550001111", "email": "ann@example.com", "business_type": "Bakery",
        "ad_name": None, "campaign_id": "c1", "is_test": False, "is_organic": True}


class IsTestLeadTest(unittest.TestCase):
    def test_only_a_lead_with_no_ad_that_meta_does_not_call_organic_is_a_test(self):
        cases = [{"ad_id": "1"}, {"is_organic": True}, {"ad_id": "1", "is_organic": False}, {}, {"is_organic": False}]
        self.assertEqual([leads.is_test_lead(c) for c in cases], [False, False, False, True, True])

    def test_testing_tool_dummy_answers_make_a_test_lead_even_with_an_ad_or_marked_organic(self):
        dummy = [{"name": "full_name", "values": ["<test lead: dummy data for full_name>"]}]
        real = [{"name": "full_name", "values": ["Ann <test lead> Lee"]}, {"name": "note", "values": []}]
        cases = [{"ad_id": "1", "field_data": dummy}, {"is_organic": True, "field_data": dummy},
                 {"is_organic": True, "field_data": real}, {"ad_id": "1", "field_data": None}]
        self.assertEqual([leads.is_test_lead(c) for c in cases], [True, True, False, False])


class WithoutNulTest(unittest.TestCase):
    def test_nul_characters_are_dropped_everywhere_postgres_would_refuse_them(self):
        data = {"id": "1", "field_data": [{"name": "note\x00", "values": ["a\x00b", 3, None]}], "is_organic": True}
        self.assertEqual(leads.without_nul(data),
                         {"id": "1", "field_data": [{"name": "note", "values": ["ab", 3, None]}], "is_organic": True})


class EventRetryTest(unittest.TestCase):
    def test_waits_longer_after_each_failure_and_at_most_an_hour(self):
        self.assertEqual([leads.event_retry_at(n, NOW) - NOW for n in (1, 2, 3, 4, 9)],
                         [1 * MIN, 5 * MIN, 15 * MIN, 60 * MIN, 60 * MIN])

    def test_missing_permissions_looks_like_not_found_and_is_tried_for_a_day(self):
        no_access = 33
        cases = [(100, NOW - timedelta(hours=23), no_access), (100, NOW, None), (100, NOW - timedelta(hours=25), no_access)]
        self.assertEqual([leads.event_gives_up(code, at, NOW, sub) for code, at, sub in cases], [False, True, True])

    def test_only_metas_webhook_test_sample_is_a_sample(self):
        self.assertEqual([leads.is_sample_ping(i) for i in ("444444444444", 444444444444, "4444444444441", "120252")],
                         [True, True, False, False])

    def test_token_permission_rate_and_network_errors_stop_the_batch(self):
        codes = [190, 17, "cooldown", "network", 10, 200, 100, None]
        self.assertEqual([leads.stops_batch(c) for c in codes], [True, True, True, True, True, True, False, False])

    def test_meta_errors_keep_their_subcode(self):
        resp = mock.Mock(status_code=400)
        resp.json.return_value = {"error": {"code": 100, "error_subcode": 33, "message": "Unsupported get request"}}
        with self.assertRaises(meta_client.MetaError) as caught:
            meta_client._raise_for(resp)
        self.assertEqual((caught.exception.code, caught.exception.subcode), (100, 33))


class AnnounceTest(unittest.TestCase):
    def run_announce(self, lead=LEAD, claimed=True, fail=None):
        steps = {name: mock.Mock(side_effect=RuntimeError("down") if name == fail else None)
                 for name in ("queue_emails", "alert_phones", "queue_auto")}
        with mock.patch.object(leads.db, "query", return_value=lead), \
                mock.patch.object(leads.db, "execute", return_value={"id": 7} if claimed else None) as execute, \
                mock.patch.object(leads, "queue_emails", steps["queue_emails"]), \
                mock.patch.object(leads, "alert_phones", steps["alert_phones"]), \
                mock.patch.object(replies, "queue_auto", steps["queue_auto"]), \
                mock.patch.object(leads.log, "exception"), \
                mock.patch.object(leads, "log_activity") as activity:
            result = leads.announce(7)
        return result, {n: s.called for n, s in steps.items()}, execute.called, [c.args[0] for c in activity.call_args_list]

    def test_the_pass_that_claims_the_lead_queues_everything_and_writes_one_history_line(self):
        self.assertEqual(self.run_announce(),
                         (True, {"queue_emails": True, "alert_phones": True, "queue_auto": True}, True, ["lead.received"]))

    def test_a_lead_already_announced_or_over_a_day_old_gets_nothing(self):
        with mock.patch.object(leads.db, "query", return_value=None) as query:
            self.assertEqual(self.run_announce(lead=None),
                             (False, {"queue_emails": False, "alert_phones": False, "queue_auto": False}, False, []))
            leads.announce(7)
        sql, params = query.call_args.args
        self.assertEqual((" alerted_at IS NULL" in sql, "created_time > now() - %s" in sql, params),
                         (True, True, (7, leads.ANNOUNCE_WITHIN)))

    def test_the_sweep_reads_only_unannounced_leads_of_the_last_day_and_counts_the_ones_it_announced(self):
        with mock.patch.object(leads.db, "query", return_value=[{"id": 4}, {"id": 9}]) as query, \
                mock.patch.object(leads, "announce", side_effect=[True, False]) as announce:
            count = leads.announce_pending()
        sql, params = query.call_args.args
        self.assertEqual((count, [c.args for c in announce.call_args_list], " alerted_at IS NULL" in sql,
                          "created_time > now() - %s" in sql, params),
                         (1, [(4,), (9,)], True, True, (leads.ANNOUNCE_WITHIN,)))

    def test_when_another_path_claimed_it_first_there_is_no_second_history_line(self):
        self.assertEqual(self.run_announce(claimed=False)[0::3], (False, []))

    def test_a_step_that_fails_leaves_the_lead_for_the_next_pass_without_stopping_the_others(self):
        self.assertEqual(self.run_announce(fail="alert_phones"),
                         (False, {"queue_emails": True, "alert_phones": True, "queue_auto": True}, False, []))


class LeadEmailQueueTest(unittest.TestCase):
    def test_one_queued_email_per_person_who_wants_it_keyed_by_lead_and_person(self):
        staff = [{"id": 1, "email": "eu@x.com", "notify_new_leads": True}, {"id": 2, "email": "mo@x.com", "notify_new_leads": False}]
        with mock.patch.object(leads, "_staff", return_value=staff), mock.patch.object(leads.mailer, "configured", return_value=True), \
                mock.patch.object(notify, "queue") as queue:
            leads.queue_emails(LEAD)
        subject, text, body_html = leads.render_email(LEAD)
        self.assertEqual([(c.args, c.kwargs) for c in queue.call_args_list], [(
            (1, "email", "lead", subject, text.split("\n")),
            {"ref": "7", "html": body_html, "dedupe_key": "lead:7:email:1"})])

    def test_queued_emails_keep_their_html_part(self):
        row = {"channel": "email", "user_id": 1, "title": "New lead: Ann", "lines": ["Phone: 1"], "url": None,
               "button": None, "html": "<p>Ann</p>"}
        with mock.patch.object(notify.db, "query", return_value={"email": "eu@x.com"}), \
                mock.patch.object(notify.mailer, "send") as send:
            notify._deliver(row)
        self.assertEqual(send.call_args.args, ("eu@x.com", "New lead: Ann", "Phone: 1", "<p>Ann</p>"))


class EveryPathAnnouncesTest(unittest.TestCase):
    def test_the_webhook_announces_a_lead_the_catch_up_stored_first(self):
        with mock.patch.object(leads.meta_client, "get", return_value={"id": "L1"}), \
                mock.patch.object(leads, "store_lead", return_value=(5, False)), \
                mock.patch.object(leads, "announce") as announce:
            leads.fetch_and_store("L1", page_token="tok")
        self.assertEqual([c.args for c in announce.call_args_list], [(5,)])

    def test_the_catch_up_announces_what_it_stores_and_skips_leads_of_another_account(self):
        pages = [[{"id": "F1", "name": "Intro call"}], [{"id": "L1"}, {"id": "L2"}, {"id": "L3"}]]
        with mock.patch.object(leads.meta_client, "page_token", return_value="tok"), \
                mock.patch("settings_store.get", return_value="P1"), \
                mock.patch.object(leads.meta_client, "paged", side_effect=pages), \
                mock.patch.object(leads, "store_lead", side_effect=[(5, True), (6, False), (None, False)]), \
                mock.patch.object(leads.db, "execute"), \
                mock.patch.object(leads, "announce") as announce:
            new = leads.backfill(days=7)
        self.assertEqual((new, [c.args for c in announce.call_args_list]), (1, [(5,), (6,)]))


class LeadPingBackoffTest(unittest.TestCase):
    def test_a_failed_ping_waits_and_a_token_error_leaves_the_rest_for_the_next_pass(self):
        events = [{"id": 1, "leadgen_id": "L1", "received_at": NOW, "attempts": 0},
                  {"id": 2, "leadgen_id": "L2", "received_at": NOW, "attempts": 2},
                  {"id": 3, "leadgen_id": "L3", "received_at": NOW, "attempts": 0}]
        refused = meta_client.MetaError("token refused", code=190)
        with mock.patch.object(leads.db, "query", return_value=events), \
                mock.patch.object(leads.meta_client, "page_token", return_value="tok"), \
                mock.patch.object(leads, "fetch_and_store", side_effect=[meta_client.MetaError("down", code=2), refused]) as fetch, \
                mock.patch.object(leads, "datetime", wraps=datetime) as dt, \
                mock.patch.object(leads.db, "execute") as execute:
            dt.now.return_value = NOW
            leads.process_pending_events()
        self.assertEqual((fetch.call_count, [c.args[1] for c in execute.call_args_list]),
                         (2, [("down", 1, NOW + 1 * MIN, 1), ("token refused", 3, NOW + 15 * MIN, 2)]))


class SamplePingTest(unittest.TestCase):
    def test_the_webhook_test_sample_is_closed_without_asking_meta(self):
        events = [{"id": 1, "leadgen_id": "444444444444", "received_at": NOW, "attempts": 0}]
        with mock.patch.object(leads.db, "query", return_value=events), \
                mock.patch.object(leads.meta_client, "page_token", return_value="tok"), \
                mock.patch.object(leads, "fetch_and_store") as fetch, \
                mock.patch.object(leads, "log_activity") as activity, \
                mock.patch.object(leads.db, "execute") as execute:
            leads.process_pending_events()
        self.assertEqual((fetch.called, activity.called, [c.args[1] for c in execute.call_args_list]),
                         (False, False, [(leads.SAMPLE_PING_NOTE, 1)]))


class LeadEmailFailedTest(unittest.TestCase):
    def run_failure(self, kind, channel, permanent):
        row = {"id": 11, "user_id": 1, "channel": channel, "kind": kind, "ref": "7", "attempts": 0, "created_at": NOW}
        error = notify.mailer.MailError("mailbox full")
        error.permanent = permanent
        with mock.patch.object(notify, "settle_interrupted"), \
                mock.patch.object(notify.db, "query", side_effect=[[row], {"account_id": 3}]), \
                mock.patch.object(notify, "claim", return_value=True), \
                mock.patch.object(notify, "_deliver", side_effect=error), \
                mock.patch.object(notify.db, "execute"), \
                mock.patch("util.log_activity") as activity, \
                mock.patch.object(notify.account_ctx, "use", wraps=notify.account_ctx.use) as use:
            notify.process_pending(NOW)
        return [(c.args, c.kwargs) for c in activity.call_args_list], [c.args for c in use.call_args_list]

    def test_a_lead_email_that_finally_fails_shows_in_the_lead_history_of_its_account(self):
        self.assertEqual(self.run_failure("lead", "email", permanent=True),
                         ([(("lead.email_failed",), {"subject": "7", "actor": "system", "details": {"error": "mailbox full"}})],
                          [(3,)]))

    def test_a_retry_still_to_come_or_another_alert_writes_nothing(self):
        self.assertEqual([self.run_failure("lead", "email", permanent=False)[0], self.run_failure("lead", "telegram", True)[0],
                          self.run_failure("reminder", "email", True)[0]], [[], [], []])


class ReportProgressTest(unittest.TestCase):
    def test_each_client_mailed_is_recorded_before_the_next_send(self):
        people = [{"email": "a@client.com", "name": "Ann A"}, {"email": "b@client.com", "name": "Bo B"}]
        saved = []
        with mock.patch.object(reports_api.settings_store, "get", side_effect=lambda k, *a: {"report_email": "weekly"}.get(k)), \
                mock.patch("mailer.configured", return_value=True), \
                mock.patch.object(reports_api.rl, "email_due", return_value=("week", NOW.date(), NOW.date(), "w46")), \
                mock.patch.object(reports_api.account_info, "tz", return_value=timezone.utc), \
                mock.patch.object(reports_api.db, "query", return_value=people), \
                mock.patch.object(reports_api, "build", return_value={"account": "Edge", "headline": "Good week"}), \
                mock.patch.object(reports_api, "share_token", return_value=("tok", None)), \
                mock.patch("mailer.send", side_effect=[None, SystemExit("worker killed")]), \
                mock.patch.object(reports_api.settings_store, "set", side_effect=lambda k, v: saved.append((k, v))):
            with self.assertRaises(SystemExit):
                reports_api.send_due(NOW)
        self.assertEqual(saved, [("report_sent_to", '{"key": "w46", "to": ["a@client.com"], "retry_at": 0}')])


if __name__ == "__main__":
    unittest.main()
