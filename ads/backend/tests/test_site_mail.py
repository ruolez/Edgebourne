import base64
import hashlib
import unittest

from cryptography.fernet import Fernet

import site_mail

SITE_SECRET = "a" * 64


def site_encrypt(plaintext, secret=SITE_SECRET):
    """What the website's backend/secrets_store.py stores, rebuilt independently."""
    material = hashlib.pbkdf2_hmac("sha256", secret.encode(), b"edgebourne.secrets.v1", 200_000, dklen=32)
    return "enc:v1:" + Fernet(base64.urlsafe_b64encode(material)).encrypt(plaintext.encode()).decode()


SITE_ROW = {"smtp_host": "mail.edgebourne.com", "smtp_port": "465", "smtp_user": "noreply@edgebourne.com",
            "smtp_from": "noreply@edgebourne.com", "smtp_tls": "SSL"}


class SiteMailTests(unittest.TestCase):
    def test_maps_the_website_settings_and_decrypts_the_password(self):
        raw = {**SITE_ROW, "smtp_password": site_encrypt("pw-123")}
        self.assertEqual(site_mail.to_mailer(raw, SITE_SECRET), {
            "host": "mail.edgebourne.com", "port": 465, "security": "ssl",
            "username": "noreply@edgebourne.com", "password": "pw-123",
            "from_email": "noreply@edgebourne.com"})

    def test_legacy_plaintext_password_is_read_as_is(self):
        self.assertEqual(site_mail.decrypt("plain-pw", SITE_SECRET), "plain-pw")

    def test_wrong_key_gives_an_empty_password_not_an_error(self):
        self.assertEqual(site_mail.decrypt(site_encrypt("pw", "b" * 64), SITE_SECRET), "")

    def test_missing_host_or_from_means_not_configured(self):
        for key in ("smtp_host", "smtp_from"):
            with self.subTest(missing=key):
                self.assertIsNone(site_mail.to_mailer({**SITE_ROW, key: ""}, SITE_SECRET))

    def test_blank_port_and_encryption_fall_back_to_587_starttls(self):
        out = site_mail.to_mailer({**SITE_ROW, "smtp_port": "", "smtp_tls": None}, SITE_SECRET)
        self.assertEqual((out["port"], out["security"]), (587, "starttls"))


if __name__ == "__main__":
    unittest.main()
