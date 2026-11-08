"""The EdgeBourne website's own mail settings (Admin → Email), read-only.

The ads console runs next to the website on the same Postgres, so when its own
Email settings are empty it sends with the website's mailbox instead of asking for
the same details twice. The password is stored encrypted by the website
(backend/secrets_store.py: Fernet, key = PBKDF2 of the site's SECRET_KEY); it is
decrypted here only to log in to the mail server and is never returned by the API.
"""
import base64
import hashlib
import logging

import psycopg2
from cryptography.fernet import Fernet, InvalidToken

import config

log = logging.getLogger(__name__)

PREFIX = "enc:v1:"
KEYS = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_tls")


def decrypt(stored, site_secret):
    if not stored:
        return ""
    if not stored.startswith(PREFIX):
        return stored  # the website reads unprefixed values as legacy plaintext
    material = hashlib.pbkdf2_hmac("sha256", site_secret.encode(), b"edgebourne.secrets.v1",
                                   200_000, dklen=32)
    try:
        return Fernet(base64.urlsafe_b64encode(material)).decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("the website's SMTP password could not be decrypted (SECRET_KEY mismatch?)")
        return ""


def to_mailer(raw, site_secret):
    """Website setting names → the ads mailer's shape, or None when not configured."""
    if not (raw.get("smtp_host") and raw.get("smtp_from")):
        return None
    port = str(raw.get("smtp_port") or "").strip()
    return {
        "host": raw["smtp_host"].strip(),
        "port": int(port) if port.isdigit() else 587,
        "security": (raw.get("smtp_tls") or "starttls").lower(),
        "username": (raw.get("smtp_user") or "").strip(),
        "password": decrypt(raw.get("smtp_password") or "", site_secret),
        "from_email": raw["smtp_from"].strip(),
    }


def settings():
    if not (config.SITE_POSTGRES_DB and config.SITE_SECRET_KEY):
        return None
    try:
        conn = psycopg2.connect(**{**config.POSTGRES, "dbname": config.SITE_POSTGRES_DB})
    except psycopg2.Error:
        log.exception("could not reach the website database for its mail settings")
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM settings WHERE key = ANY(%s)", (list(KEYS),))
            raw = {k: v for k, v in cur.fetchall()}
        conn.rollback()
    except psycopg2.Error:
        log.exception("could not read the website's mail settings")
        return None
    finally:
        conn.close()
    return to_mailer(raw, config.SITE_SECRET_KEY)
