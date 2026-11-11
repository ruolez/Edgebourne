"""The Telegram bot that brings alerts to people's phones.

An admin creates the bot with @BotFather and pastes its token in Settings. Each person links
their own chat from Your account: the console makes a one-time code, the person opens
t.me/<bot>?start=<code> and taps Start, and the bot's updates (read with getUpdates, no
webhook needed) match the code to the person. Sending /stop to the bot unlinks the chat.
"""
import html
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

import requests

import config
import db
import settings_store

log = logging.getLogger(__name__)

CODE = re.compile(r"^/start(?:@\w+)?\s+([A-Za-z0-9_-]{8,64})$")
LINK_VALID = timedelta(minutes=15)
POLL_LOCK = 7_204_312
TIMEOUT = 15


class TelegramError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

    @property
    def permanent(self):
        """Telegram said no for a reason a retry won't fix (blocked, bad chat, bad token)."""
        return self.status in (400, 401, 403, 404)


def chat_gone(exc):
    """The person blocked the bot or the chat no longer exists: this link will never work again."""
    return exc.status == 403 or (exc.status == 400 and "chat not found" in str(exc).lower())


def start_code(text):
    m = CODE.match((text or "").strip())
    return m.group(1) if m else None


def deep_link(username, code):
    return f"https://t.me/{username}?start={code}"


def e(text):
    """Telegram's HTML mode needs only <, > and & escaped."""
    return html.escape(text, quote=False)


def message(title, lines, url=None, button="Open"):
    """sendMessage fields. Telegram refuses buttons that aren't https, so those go in the text."""
    body = "\n".join([f"<b>{e(title)}</b>", *(e(str(x)) for x in lines)])
    out = {"text": body, "parse_mode": "HTML", "disable_web_page_preview": True}
    if url and url.startswith("https://"):
        out["reply_markup"] = {"inline_keyboard": [[{"text": button, "url": url}]]}
    elif url:
        out["text"] = f"{body}\n\n{e(button)}: {e(url)}"
    return out


def token():
    return settings_store.get("telegram_bot_token")


def call(method, payload=None, tok=None):
    tok = tok or token()
    if not tok:
        raise TelegramError("The Telegram bot isn't set up yet. An admin adds it in Settings.")
    try:
        resp = requests.post(f"{config.TELEGRAM_API_BASE}/bot{tok}/{method}", json=payload or {}, timeout=TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        # Never the exception's text: a connection error quotes the URL, and the URL holds the bot token.
        raise TelegramError(f"Telegram didn't answer ({type(exc).__name__})") from None
    if not data.get("ok"):
        raise TelegramError(data.get("description") or f"Telegram refused it ({resp.status_code})", data.get("error_code") or resp.status_code)
    return data.get("result")


def send(chat_id, title, lines, url=None, button="Open"):
    return call("sendMessage", {"chat_id": chat_id, **message(title, lines, url, button)})


def connect(tok):
    """Check a new bot token and remember the bot's name. Updates are read by polling,
    so any webhook left on the bot is removed."""
    bot = call("getMe", tok=tok)
    call("deleteWebhook", {"drop_pending_updates": False}, tok=tok)
    settings_store.set("telegram_bot_token", tok)
    settings_store.set("telegram_bot_username", bot.get("username"))
    settings_store.set("telegram_update_offset", None)
    return bot


def new_link_code(user_id):
    code = secrets.token_urlsafe(12)
    db.execute("UPDATE users SET telegram_link_code = %s, telegram_link_expires = %s WHERE id = %s",
               (code, datetime.now(timezone.utc) + LINK_VALID, user_id))
    return code


def _handle(update):
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return None
    text = (msg.get("text") or "").strip()
    sender = msg.get("from") or {}
    name = sender.get("username") and f"@{sender['username']}" or sender.get("first_name") or "Telegram"
    code = start_code(text)
    if code:
        user = db.query("UPDATE users SET telegram_chat_id = %s, telegram_name = %s, notify_telegram = TRUE, "
                        "telegram_link_code = NULL, telegram_link_expires = NULL "
                        "WHERE telegram_link_code = %s AND telegram_link_expires > now() AND is_active "
                        "RETURNING id, name", (chat["id"], name, code), one=True)
        if user:
            send(chat["id"], "You're connected", [f"Hi {user['name']}. New leads and reminders from Edge Bourne Ads will show up here.", "Send /stop to turn them off."])
            return user["id"]
        send(chat["id"], "That link has expired", ["Open Your account in the Ads console and tap Connect Telegram again."])
        return None
    if text.startswith("/stop"):
        rows = db.query("UPDATE users SET telegram_chat_id = NULL, telegram_name = NULL WHERE telegram_chat_id = %s RETURNING id",
                        (chat["id"],))
        if rows:
            send(chat["id"], "Alerts turned off", ["Connect again any time from Your account in the Ads console."])
    return None


def poll_updates(conn):
    """Read the bot's new messages once. Returns the ids of people who just linked."""
    if not token():
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (POLL_LOCK,))
        if not cur.fetchone()[0]:
            return []
    try:
        offset = settings_store.get("telegram_update_offset")
        updates = call("getUpdates", {"timeout": 0, "allowed_updates": ["message"], **({"offset": int(offset)} if offset else {})})
        linked = []
        for update in updates or []:
            settings_store.set("telegram_update_offset", str(update["update_id"] + 1))
            try:
                uid = _handle(update)
            except TelegramError as exc:
                log.info("telegram: couldn't answer an update: %s", exc)
                uid = None
            if uid:
                linked.append(uid)
        return linked
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (POLL_LOCK,))


def link_pending():
    return bool(db.query("SELECT 1 FROM users WHERE telegram_link_expires > now() LIMIT 1", one=True))
