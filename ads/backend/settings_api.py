from flask import Blueprint, jsonify, request, session

import config
import crm_events
import db
import leads
import mailer
import meta_client
import settings_store
import insights
import sync
import jobs
import notify
import telegram
import refresh_api
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

META_FIELDS = ("meta_app_id", "meta_app_secret", "meta_system_token", "meta_verify_token",
               "meta_page_id", "meta_ad_account_id", "meta_graph_version", "meta_dataset_id",
               "crm_send_enabled")
SMTP_FIELDS = ("smtp_host", "smtp_port", "smtp_security", "smtp_username", "smtp_password",
               "smtp_from_email", "smtp_from_name")


def _section(fields):
    out = {}
    for key in fields:
        value = settings_store.get(key) or ""
        if key in settings_store.SECRET_KEYS:
            out[key] = {"set": bool(value), "hint": settings_store.mask(value)}
        else:
            out[key] = value
    return out


def _smtp_in_use():
    s = mailer.smtp_settings()
    if s["source"] == "none":
        return {"source": "none"}
    return {"source": s["source"], "host": s["host"], "from_email": s["from_email"]}


@bp.get("")
@admin_required
def get_settings():
    pending = db.query("SELECT COUNT(*) AS n, MAX(error) AS last_error FROM webhook_events "
                       "WHERE processed_at IS NULL", one=True)
    return jsonify({
        "meta": _section(META_FIELDS),
        "smtp": _section(SMTP_FIELDS),
        "smtp_in_use": _smtp_in_use(),
        "webhook_url": f"{config.APP_BASE_URL}/webhooks/meta",
        "graph_version_default": config.GRAPH_VERSION_DEFAULT,
        "pending_webhooks": pending["n"],
        "pending_error": pending["last_error"],
        "last_campaign_sync": settings_store.get("last_campaign_sync"),
        "page_subscribed": settings_store.get("meta_page_subscribed") == "1",
        "crm": crm_events.summary(),
        "telegram": {"set": bool(telegram.token()), "username": settings_store.get("telegram_bot_username") if telegram.token() else None,
                     "linked": db.query("SELECT COUNT(*) AS n FROM users WHERE telegram_chat_id IS NOT NULL AND is_active", one=True)["n"],
                     "failed": notify.failed_recently()},
        "auto_refresh_minutes": refresh_api.auto_minutes(settings_store.get("auto_refresh_minutes")),
        "auto_refresh_choices": list(refresh_api.AUTO_CHOICES),
    })


def _save(fields, data):
    changed = []
    for key in fields:
        if key not in data:
            continue
        value = data[key]
        value = "" if value is None else str(value).strip()
        if key in settings_store.SECRET_KEYS and value == "":
            continue  # blank secret field = keep the stored one
        settings_store.set(key, value or None)
        changed.append(key)
    return changed


@bp.put("/meta")
@admin_required
def save_meta():
    changed = _save(META_FIELDS, request.get_json(silent=True) or {})
    log_activity("settings.meta", details={"changed": changed})
    return get_settings()


@bp.put("/refresh")
@admin_required
def save_refresh():
    raw = (request.get_json(silent=True) or {}).get("minutes")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = None
    if minutes not in refresh_api.AUTO_CHOICES:
        return api_error("Pick one of the listed intervals", 400, field="minutes")
    settings_store.set("auto_refresh_minutes", str(minutes))
    log_activity("settings.refresh", details={"minutes": minutes})
    jobs.wake()
    return get_settings()


@bp.put("/telegram")
@admin_required
def save_telegram():
    data = request.get_json(silent=True) or {}
    if data.get("remove"):
        for key in ("telegram_bot_token", "telegram_bot_username", "telegram_update_offset"):
            settings_store.set(key, None)
        log_activity("settings.telegram", details={"removed": True})
        return get_settings()
    tok = (data.get("token") or "").strip()
    if not tok:
        return api_error("Paste the token @BotFather gave you", 400, field="telegram_bot_token")
    try:
        bot = telegram.connect(tok)
    except telegram.TelegramError as exc:
        return api_error(f"Telegram didn't accept that token: {exc}", 400, field="telegram_bot_token")
    log_activity("settings.telegram", details={"bot": bot.get("username")})
    return get_settings()


@bp.put("/smtp")
@admin_required
def save_smtp():
    data = request.get_json(silent=True) or {}
    if "smtp_port" in data and str(data["smtp_port"]).strip() and not str(data["smtp_port"]).isdigit():
        return api_error("The port is a number, usually 587 or 465", 400, field="smtp_port")
    changed = _save(SMTP_FIELDS, data)
    log_activity("settings.smtp", details={"changed": changed})
    return get_settings()


@bp.post("/smtp/test")
@admin_required
def test_smtp():
    me = current_user()
    try:
        mailer.send(me["email"], "Test from Edge Bourne Ads",
                    "Email works. New-lead alerts will arrive like this one.")
    except mailer.MailError as exc:
        return api_error(str(exc), 400)
    return jsonify({"ok": True, "sent_to": me["email"], "source": mailer.smtp_settings()["source"]})


@bp.post("/meta/test")
@admin_required
def test_meta():
    try:
        who = meta_client.get("me", fields="id,name")
        page = meta_client.get(settings_store.get("meta_page_id"), fields="id,name,access_token")
        account = meta_client.get(f"act_{settings_store.get('meta_ad_account_id')}",
                                  fields="name,account_status,currency")
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    return jsonify({
        "system_user": who.get("name"),
        "page": page.get("name"),
        "page_token": bool(page.get("access_token")),
        "ad_account": account.get("name"),
        "currency": account.get("currency"),
    })


@bp.post("/meta/crm-test")
@admin_required
def test_crm():
    code = str((request.get_json(silent=True) or {}).get("code") or "").strip()
    if not code:
        return api_error("Paste the test code from Events Manager → your dataset → Test events", 400, field="code")
    try:
        res = crm_events.send_test(code)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    log_activity("settings.crm_test")
    return jsonify({"received": res.get("events_received"), "trace": res.get("fbtrace_id")})


@bp.post("/meta/connect-page")
@admin_required
def connect_page():
    """Install the app on the Page so Meta sends leadgen webhooks."""
    page_id = settings_store.get("meta_page_id")
    try:
        token = meta_client.page_token(page_id)
        meta_client.post(f"{page_id}/subscribed_apps", token=token, subscribed_fields="leadgen")
        apps = meta_client.get(f"{page_id}/subscribed_apps", token=token)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    settings_store.set("meta_page_subscribed", "1")
    log_activity("settings.page_connected", subject=page_id)
    return jsonify({"ok": True, "apps": apps.get("data", [])})


@bp.post("/meta/sync")
@admin_required
def run_sync():
    try:
        campaigns = insights.sync_all(days=30)["campaigns"]
        new_leads = leads.backfill(days=int((request.get_json(silent=True) or {}).get("days", 30)))
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    jobs.wake()
    log_activity("sync.manual", details={"campaigns": campaigns, "new_leads": new_leads})
    return jsonify({"campaigns": campaigns, "new_leads": new_leads})


@bp.post("/webhooks/retry")
@admin_required
def retry_webhooks():
    done = leads.process_pending_events()
    return jsonify({"processed": done})


@bp.get("/activity")
@admin_required
def activity():
    rows = db.query(
        "SELECT a.at, a.actor, a.action, a.subject, a.details, u.name AS who FROM activity a "
        "LEFT JOIN users u ON u.id = a.user_id WHERE a.action <> 'auth.sign_in' ORDER BY a.at DESC LIMIT 200"
    )
    return jsonify(rows)
