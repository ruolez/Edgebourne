"""Your account → Phone alerts: link Telegram, test it, turn it off."""
from flask import Blueprint, jsonify, request

import db
import settings_store
import telegram
from auth import current_user, login_required
from util import api_error, log_activity

bp = Blueprint("alerts", __name__, url_prefix="/api/me/telegram")


def _state(user_id, link=None):
    u = db.query("SELECT telegram_chat_id, telegram_name, notify_telegram, telegram_link_code, "
                 "telegram_link_expires > now() AS pending FROM users WHERE id = %s", (user_id,), one=True)
    bot = settings_store.get("telegram_bot_username") if telegram.token() else None
    code = u["telegram_link_code"] if u["pending"] else None
    return {"bot": bot, "linked": bool(u["telegram_chat_id"]), "name": u["telegram_name"],
            "enabled": u["notify_telegram"], "pending": bool(code),
            "link": telegram.deep_link(bot, code) if bot and code else None}


@bp.get("")
@login_required
def state():
    user = current_user()
    if telegram.token() and telegram.link_pending():
        try:
            telegram.poll_updates(db.get_db())
        except telegram.TelegramError:
            pass  # the worker reads them again on its next pass
    return jsonify(_state(user["id"]))


@bp.post("/link")
@login_required
def link():
    user = current_user()
    if not telegram.token():
        return api_error("The Telegram bot isn't set up yet. An admin adds it in Settings.", 400)
    telegram.new_link_code(user["id"])
    return jsonify(_state(user["id"]))


@bp.patch("")
@login_required
def update():
    user = current_user()
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        db.execute("UPDATE users SET notify_telegram = %s WHERE id = %s", (bool(data["enabled"]), user["id"]))
    return jsonify(_state(user["id"]))


@bp.post("/test")
@login_required
def test():
    user = current_user()
    row = db.query("SELECT telegram_chat_id FROM users WHERE id = %s", (user["id"],), one=True)
    if not row["telegram_chat_id"]:
        return api_error("Connect Telegram first", 400)
    try:
        telegram.send(row["telegram_chat_id"], "Test from Edge Bourne Ads", ["This is how new leads and reminders will arrive."])
    except telegram.TelegramError as exc:
        return api_error(str(exc), 502)
    return jsonify({"ok": True})


@bp.delete("")
@login_required
def unlink():
    user = current_user()
    db.execute("UPDATE users SET telegram_chat_id = NULL, telegram_name = NULL, telegram_link_code = NULL, "
               "telegram_link_expires = NULL WHERE id = %s", (user["id"],))
    log_activity("account.telegram_off")
    return jsonify(_state(user["id"]))
