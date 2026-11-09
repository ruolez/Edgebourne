import unittest
from datetime import datetime, timedelta, timezone

import notify
import telegram

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)


class StartCodeTests(unittest.TestCase):
    def test_reads_the_code_from_a_start_command(self):
        self.assertEqual(
            [telegram.start_code(t) for t in ("/start AbC123_-xyz9", "/start@EdgeBourneAdsBot AbC123_-xyz9", "/start", "/start short", "hello", None, "/start bad!code")],
            ["AbC123_-xyz9", "AbC123_-xyz9", None, None, None, None, None])


class DeepLinkTests(unittest.TestCase):
    def test_opens_the_bot_with_the_code(self):
        self.assertEqual(telegram.deep_link("EdgeBourneAdsBot", "AbC123_-xyz9"), "https://t.me/EdgeBourneAdsBot?start=AbC123_-xyz9")


class MessageTests(unittest.TestCase):
    def test_escapes_text_and_adds_a_button_for_https_links(self):
        msg = telegram.message("New lead: Ann <b>&", ["Bakery", "Phone: 555"], "https://ads.edgebourne.com/leads.html#lead=7", "Open the lead")
        self.assertEqual(msg, {
            "text": "<b>New lead: Ann &lt;b&gt;&amp;</b>\nBakery\nPhone: 555",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {"inline_keyboard": [[{"text": "Open the lead", "url": "https://ads.edgebourne.com/leads.html#lead=7"}]]},
        })

    def test_puts_a_plain_link_in_the_text_when_telegram_would_refuse_the_button(self):
        msg = telegram.message("Hi", [], "http://ads.localhost:8090/leads.html", "Open")
        self.assertEqual((msg["text"], "reply_markup" in msg), ("<b>Hi</b>\n\nOpen: http://ads.localhost:8090/leads.html", False))


class RetryTests(unittest.TestCase):
    def test_backs_off_then_gives_up(self):
        made = NOW - timedelta(minutes=2)
        self.assertEqual(
            [notify.retry_at(n, made, NOW, permanent=False) for n in (1, 2, 3, 4)],
            [NOW + timedelta(minutes=1), NOW + timedelta(minutes=5), NOW + timedelta(minutes=15), None])

    def test_a_refusal_or_an_old_alert_is_not_retried(self):
        self.assertEqual(
            [notify.retry_at(1, NOW, NOW, permanent=True), notify.retry_at(1, NOW - notify.GIVE_UP_AFTER, NOW, permanent=False)],
            [None, None])


class LeadAlertTests(unittest.TestCase):
    LEAD = {"id": 7, "full_name": "Maria Lopez", "business_type": "Wholesale bakery", "phone": "+15551234567",
            "email": "maria@example.com", "ad_name": "N2 - Order portal", "is_test": False}

    def test_says_who_how_to_reach_them_and_which_ad(self):
        title, lines = notify.lead_alert(self.LEAD)
        self.assertEqual((title, lines), ("New lead: Maria Lopez", [
            "Wholesale bakery", "Phone: +15551234567", "Email: maria@example.com", "From ad: N2 - Order portal",
            "", "Call within the hour if you can."]))

    def test_marks_a_test_lead_and_skips_missing_details(self):
        title, lines = notify.lead_alert({**self.LEAD, "full_name": None, "business_type": None, "email": None, "ad_name": None, "is_test": True})
        self.assertEqual((title, lines), ("New test lead: Someone", [
            "Business not given", "Phone: +15551234567", "", "Call within the hour if you can."]))
