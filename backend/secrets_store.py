"""Encrypted-at-rest secrets in the `settings` table.

Secrets are editable from the admin UI, but a database dump on its own is
useless: values are encrypted with a key derived from SECRET_KEY, which lives in
.env and is never written to the database. Restoring a stolen pg_dump elsewhere
yields ciphertext.

That is the property that makes UI-configurable payment keys defensible. It does
NOT protect against an attacker who has both the dump and .env, or one who is
already executing code on the box -- nothing at this layer could.

Storage format:  enc:v1:<fernet token>
Anything without the prefix is treated as legacy plaintext and read as-is, so
an existing smtp_password keeps working and is re-encrypted the next time it is
saved.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

import config
import db

log = logging.getLogger(__name__)

PREFIX = "enc:v1:"
MASK = "••••••••"

_fernet = None


def _key():
    """Derive a Fernet key from SECRET_KEY.

    PBKDF2 with a fixed salt: the salt's job is to stop precomputation across
    *different* deployments, and SECRET_KEY is already 32 bytes of randomness
    per deployment, so a per-value salt would buy nothing here and would have to
    be stored alongside the ciphertext.
    """
    global _fernet
    if _fernet is None:
        material = hashlib.pbkdf2_hmac(
            "sha256", config.SECRET_KEY.encode(), b"edgebourne.secrets.v1", 200_000, dklen=32
        )
        _fernet = Fernet(base64.urlsafe_b64encode(material))
    return _fernet


def encrypt(plaintext):
    if not plaintext:
        return ""
    return PREFIX + _key().encrypt(plaintext.encode()).decode()


def decrypt(stored):
    """Returns plaintext, or "" if the value cannot be read.

    A value that will not decrypt almost always means SECRET_KEY was changed or
    the row was restored from another deployment. That is logged loudly rather
    than raising, so a bad key degrades the billing UI instead of taking the
    whole site down at import time.
    """
    if not stored:
        return ""
    if not stored.startswith(PREFIX):
        return stored  # legacy plaintext; re-encrypted on next save
    try:
        return _key().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("A stored secret could not be decrypted — was SECRET_KEY changed, "
                  "or this database restored from another deployment?")
        return ""


def _read(key):
    """Read a raw setting with or without a Flask app context.

    The scheduler runs as its own process and has no flask.g, but it still needs
    the Stripe keys for the reconciliation sweep. Falling back to a standalone
    connection keeps every caller working rather than making each one remember
    to build an app context.
    """
    try:
        return db.get_setting(key, "") or ""
    except RuntimeError:
        try:
            with db.standalone() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                    row = cur.fetchone()
                conn.commit()
            return (row[0] if row else "") or ""
        except Exception:
            log.exception("could not read setting %s outside an app context", key)
            return ""


def get_secret(key, default=""):
    return decrypt(_read(key)) or default


def set_secret(key, plaintext):
    db.set_setting(key, encrypt(plaintext))


def is_set(key):
    return bool(_read(key))


def fingerprint(key, keep=4):
    """Enough to tell two keys apart in the UI, never enough to use one."""
    value = get_secret(key)
    if not value:
        return ""
    return f"{value[:8]}…{value[-keep:]}" if len(value) > 12 + keep else "set"


def save_masked(key, submitted):
    """Write-only field handling, as in admin/email_settings.py.

    Returns True when the stored value actually changed -- the caller uses that
    to decide whether to write an audit entry and alert.
    """
    if submitted is None:
        return False
    submitted = submitted.strip()
    if submitted == MASK:
        return False  # unchanged; the form only ever shows the mask
    if not submitted:
        if is_set(key):
            db.set_setting(key, "")
            return True
        return False
    if submitted == get_secret(key):
        return False
    set_secret(key, submitted)
    return True
