"""Key/value settings. Secret values are encrypted at rest with a key derived
from SECRET_KEY and are never returned to the browser in full."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

import account_ctx
import config
import db

SECRET_KEYS = {
    "telegram_bot_token",
    "vapid_private_key",
    "meta_app_secret",
    "meta_system_token",
    "meta_verify_token",
    "smtp_password",
}

# Settings that belong to one ad account (roadmap 7.1). Account 1 keeps the plain key, so nothing
# stored before agency mode moves; other accounts store "key@<id>". The Meta connection falls back
# to account 1's when an account has none of its own (one System User can reach clients' accounts).
ACCOUNT_KEYS = {
    "meta_ad_account_id", "meta_page_id", "meta_system_token", "meta_dataset_id", "meta_business_id", "meta_page_subscribed",
    "crm_send_enabled", "last_refresh_at", "last_performance_sync", "last_campaign_sync", "today_snapshot", "account_snapshot",
    "tracking_snapshot", "meta_advice", "meta_benchmarks", "monthly_target_cents", "meta_ab_tests", "alert_rules",
    "reply_auto", "reply_auto_template_id", "reply_auto_user_id", "reply_booking_link", "reminder_digest_date",
    "kpi_target_cents", "report_email", "report_last_sent", "meta_token_error", "account_tz", "account_currency", "report_sent_to", "client_lead_updates", "report_link_epoch", "max_daily_budget_cents", "lead_target_cents", "meta_status_webhooks", "meta_status_webhook_at",
}
INHERITED = {"meta_system_token"}


def stored_key(key, account_id=None):
    acct = account_ctx.current() if account_id is None else account_id
    return key if key not in ACCOUNT_KEYS or acct == account_ctx.DEFAULT else f"{key}@{acct}"


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


def get(key, default=None, account_id=None):
    row = db.query("SELECT value FROM settings WHERE key = %s", (stored_key(key, account_id),), one=True)
    if (not row or row["value"] in (None, "")) and key in INHERITED and stored_key(key, account_id) != key:
        row = db.query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
    if not row or row["value"] in (None, ""):
        return config.META_DEFAULTS.get(key, default) if stored_key(key, account_id) == key else default
    return _decrypt(row["value"]) if key in SECRET_KEYS else row["value"]


def own(key, account_id=None):
    """The account's own value, without falling back to account 1's."""
    row = db.query("SELECT value FROM settings WHERE key = %s", (stored_key(key, account_id),), one=True)
    if not row or row["value"] in (None, ""):
        return None
    return _decrypt(row["value"]) if key in SECRET_KEYS else row["value"]


def account_values(key, rows):
    """{account id: value} from the stored rows of `key` (plain = account 1, "key@N" = account N),
    with account 1's built-in default where it stores none, as get() reads it."""
    out = {}
    for r in rows:
        if r["value"] not in (None, ""):
            out[int(r["key"].split("@", 1)[1]) if "@" in r["key"] else account_ctx.DEFAULT] = r["value"]
    if account_ctx.DEFAULT not in out and config.META_DEFAULTS.get(key):
        out[account_ctx.DEFAULT] = config.META_DEFAULTS[key]
    return out


def meta_holders(key):
    """[(account id, closed, value)] in account order: every account's value of a Meta id such as
    the Page or the ad account, account 1's built-in default included."""
    with account_ctx.all_accounts():
        rows = db.query("SELECT key, value FROM settings WHERE key = %s OR key LIKE %s", (key, f"{key}@%"))
        accounts = db.query("SELECT id, archived_at IS NOT NULL AS closed FROM accounts ORDER BY id")
    values = account_values(key, rows)
    return [(a["id"], a["closed"], values[a["id"]]) for a in accounts if a["id"] in values]


def set(key, value, account_id=None):  # noqa: A001 - mirrors the store's vocabulary
    name = stored_key(key, account_id)
    if value is None:
        db.execute("DELETE FROM settings WHERE key = %s", (name,))
        return
    stored = _encrypt(value) if key in SECRET_KEYS and value else value
    db.execute(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (name, stored),
    )


def mask(value):
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 8 else "•" * len(value)
