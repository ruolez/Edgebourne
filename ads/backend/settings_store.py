"""Key/value settings. Secret values are encrypted at rest with a key derived
from SECRET_KEY and are never returned to the browser in full."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

import config
import db

SECRET_KEYS = {
    "telegram_bot_token",
    "meta_app_secret",
    "meta_system_token",
    "meta_verify_token",
    "smtp_password",
}

_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.SECRET_KEY.encode()).digest()))


def _encrypt(value):
    return "enc:" + _fernet.encrypt(value.encode()).decode()


def _decrypt(value):
    if not value or not value.startswith("enc:"):
        return value
    try:
        return _fernet.decrypt(value[4:].encode()).decode()
    except InvalidToken:
        return None


def get(key, default=None):
    row = db.query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
    if not row or row["value"] in (None, ""):
        return config.META_DEFAULTS.get(key, default)
    return _decrypt(row["value"]) if key in SECRET_KEYS else row["value"]


def set(key, value):  # noqa: A001 - mirrors the store's vocabulary
    if value is None:
        db.execute("DELETE FROM settings WHERE key = %s", (key,))
        return
    stored = _encrypt(value) if key in SECRET_KEYS and value else value
    db.execute(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (key, stored),
    )


def mask(value):
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 8 else "•" * len(value)
