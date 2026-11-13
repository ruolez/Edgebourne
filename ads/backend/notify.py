"""Every alert to a person goes through here: queued per person and channel, sent by the
background worker within seconds, retried a few times, never sent twice (dedupe_key).

Channels: telegram (the person linked their chat and kept it on), push and email. New-lead
emails (leads.queue_emails) keep their HTML part in `html`.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import account_ctx
import db
import mailer
import telegram

log = logging.getLogger(__name__)

BACKOFF_MINUTES = (1, 5, 15)
GIVE_UP_AFTER = timedelta(hours=1)


def retry_at(attempts, created_at, now, permanent):
    """When to try again after the attempts-th failure, or None to give up."""
    if permanent or attempts > len(BACKOFF_MINUTES) or now - created_at >= GIVE_UP_AFTER:
        return None
    return now + timedelta(minutes=BACKOFF_MINUTES[attempts - 1])


def lead_alert(lead):
    test = " test" if lead.get("is_test") else ""
    lines = [lead.get("business_type") or "Business not given"]
    for label, key in (("Phone", "phone"), ("Email", "email"), ("From ad", "ad_name")):
        if lead.get(key):
            lines.append(f"{label}: {lead[key]}")
    lines += ["", "Call within the hour if you can."]
    junk = " (looks like junk)" if lead.get("junk_flags") and not lead.get("is_test") else ""  # L2: still alerts, says so
    return f"New{test} lead{junk}: {lead.get('full_name') or 'Someone'}", lines


def link(path, account_id=None):
    """A console link that opens in the right account: `acct=` makes the page switch to it first."""
    import config
    acct = account_ctx.current() if account_id is None else account_id
    path = path or "/home.html"
    base, _, frag = path.partition("#")
    sep = "&" if "?" in base else "?"
    return f"{config.APP_BASE_URL.rstrip('/')}{base}{sep}acct={acct}" + (f"#{frag}" if frag else "")


def telegram_people(user_ids):
    """Of these people, the ones Telegram alerts can reach right now."""
    if not user_ids or not telegram.token():
        return []
    rows = db.query("SELECT id FROM users WHERE id = ANY(%s) AND is_active AND notify_telegram AND telegram_chat_id IS NOT NULL",
                    (list(user_ids),))
    return [r["id"] for r in rows]


def reach(user_ids, flag="notify_reminders"):
    """[(user id, channel)]: Telegram when the person linked it, else push when a device of theirs
    has notifications on, else email. `flag` is the person's own on/off switch for this kind of
    alert (a users column)."""
    if not user_ids:
        return []
    import push
    by_tg = set(telegram_people(user_ids))
    by_push = push.has_devices(user_ids)
    rows = db.query(f"SELECT id FROM users WHERE id = ANY(%s) AND is_active AND {flag}", (list(user_ids),))
    out = []
    for r in rows:
        if r["id"] in by_tg:
            out.append((r["id"], "telegram"))
        elif r["id"] in by_push:
            out.append((r["id"], "push"))
        elif mailer.configured():
            out.append((r["id"], "email"))
    return out


def serves(user, account_id):
    """Whether this person works on this account. The console's owners (admins tied to no account)
    work on every account; everyone else only on their own. The users table has no row-level
    security, so every query that picks people to tell about an account goes through this."""
    return user["account_id"] is None or user["account_id"] == account_id


def admin_ids():
    """The active admins of the current account, the console's owners included."""
    rows = db.query("SELECT id, account_id FROM users WHERE role = 'admin' AND is_active ORDER BY id")
    return [r["id"] for r in rows if serves(r, account_ctx.current())]


def account_admin_ids():
    """Who hears about an account's alerts: its active admins and the console's owners (00-PLAN S3)."""
    return admin_ids()


def queue(user_id, channel, kind, title, lines, url=None, button="Open", ref=None, dedupe_key=None, html=None):
    if dedupe_key and account_ctx.current() != account_ctx.DEFAULT:
        dedupe_key = f"a{account_ctx.current()}:{dedupe_key}"  # notifications are shared; keys are per account
    db.execute(
        "INSERT INTO notifications (user_id, channel, kind, ref, dedupe_key, title, lines, url, button, html) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedupe_key) DO NOTHING",
        (user_id, channel, kind, ref, dedupe_key, title, json.dumps(lines), url, button, html))


def _deliver(row):
    if row["channel"] == "telegram":
        user = db.query("SELECT telegram_chat_id FROM users WHERE id = %s AND notify_telegram", (row["user_id"],), one=True)
        if not user or not user["telegram_chat_id"]:
            raise telegram.TelegramError("Telegram isn't linked any more", status=403)
        telegram.send(user["telegram_chat_id"], row["title"], row["lines"], row["url"], row["button"] or "Open")
    elif row["channel"] == "email":
        user = db.query("SELECT email FROM users WHERE id = %s", (row["user_id"],), one=True)
        link = f"\n\n{row['button'] or 'Open'}: {row['url']}" if row["url"] else ""
        mailer.send(user["email"], row["title"], "\n".join(row["lines"]) + link, row.get("html"))
    elif row["channel"] == "push":
        import push
        push.send_to_user(row["user_id"], row["title"], row["lines"], row["url"], tag=row.get("kind"))
    else:
        raise telegram.TelegramError(f"Unknown channel {row['channel']}", status=400)


def push_error():
    import push
    return push.PushError


INTERRUPTED = "Interrupted while sending (the server restarted); not sent again so nobody gets it twice"


def claim(table, row_id):
    """Mark a row 'sending' before it goes out, so a restart mid-send can't send it twice.
    False when another pass already took it."""
    return db.execute(f"UPDATE {table} SET status = 'sending' WHERE id = %s AND status = 'pending' RETURNING id",
                      (row_id,), returning=True) is not None


def settle_interrupted(table, error_column="last_error"):
    """Rows left 'sending' by a killed worker: failed (at most once), never resent."""
    db.execute(f"UPDATE {table} SET status = 'failed', {error_column} = %s "
               "WHERE status = 'sending' AND next_attempt_at < now() - interval '15 minutes'", (INTERRUPTED,))


def process_pending(now=None):
    now = now or datetime.now(timezone.utc)
    settle_interrupted("notifications")
    rows = db.query("SELECT * FROM notifications WHERE status = 'pending' AND next_attempt_at <= %s ORDER BY id LIMIT 50", (now,))
    for row in rows:
        if not claim("notifications", row["id"]):
            continue
        try:
            _deliver(row)
        except (telegram.TelegramError, mailer.MailError, push_error()) as exc:
            if row["channel"] == "telegram" and isinstance(exc, telegram.TelegramError) and telegram.chat_gone(exc):
                taken = _fall_back(row)
                if taken:
                    exc = telegram.TelegramError(f"{exc}; sent by {' and '.join(taken)} instead", status=exc.status)
            attempts = row["attempts"] + 1
            again = retry_at(attempts, row["created_at"], now, getattr(exc, "permanent", False))
            db.execute("UPDATE notifications SET attempts = %s, last_error = %s, status = %s, next_attempt_at = COALESCE(%s, next_attempt_at) WHERE id = %s",
                       (attempts, str(exc)[:500], "pending" if again else "failed", again, row["id"]))
            log.info("notification %s (%s) not sent: %s", row["id"], row["channel"], exc)
            if not again and row["kind"] == "lead" and row["channel"] == "email" and row["ref"]:
                _note_email_failed(int(row["ref"]), exc)
            continue
        db.execute("UPDATE notifications SET status = 'sent', sent_at = now(), attempts = attempts + 1, last_error = NULL WHERE id = %s", (row["id"],))
        if row["kind"] == "lead" and row["channel"] == "email" and row["ref"]:
            _mark_emailed(int(row["ref"]))
    return len(rows)


def _mark_emailed(lead_id):
    """The queue serves every account; lead ids are unique across them."""
    try:
        with account_ctx.all_accounts():
            db.execute("UPDATE leads SET emailed_at = COALESCE(emailed_at, now()) WHERE id = %s", (lead_id,))
    except Exception:  # the email went out; a missing timestamp must not stop the rest of the queue
        log.exception("lead %s: emailed_at not recorded", lead_id)


def _note_email_failed(lead_id, exc):
    """A lead email the queue gave up on shows in that lead's history, under the lead's account."""
    import lead_history
    try:
        with account_ctx.all_accounts():
            lead = db.query("SELECT account_id FROM leads WHERE id = %s", (lead_id,), one=True)
        if lead:
            with account_ctx.use(lead["account_id"]):
                lead_history.record(int(lead_id), "alert_failed", actor="system", details={"error": str(exc)})
    except Exception:
        log.exception("lead %s: the failed email was not recorded", lead_id)


def _fall_back(row):
    """Telegram says the person blocked the bot or the chat is gone: unlink it (as /stop would) and
    send this alert on their next channel. A new-lead alert never falls back to email: the lead
    email goes to them anyway. Returns the channels it went to (none when nothing else reaches them)."""
    db.execute("UPDATE users SET telegram_chat_id = NULL, telegram_name = NULL WHERE id = %s AND notify_telegram",
               (row["user_id"],))
    taken = []
    for uid, channel in reach([row["user_id"]], "TRUE"):
        if channel == "telegram" or (row["kind"] == "lead" and channel == "email"):
            continue
        taken.append(channel)
        db.execute(
            "INSERT INTO notifications (user_id, channel, kind, ref, dedupe_key, title, lines, url, button) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedupe_key) DO NOTHING",
            (uid, channel, row["kind"], row["ref"], f"{row['dedupe_key']}:{channel}" if row["dedupe_key"] else None,
             row["title"], json.dumps(row["lines"]), row["url"], row["button"]))
    return taken


def failed_recently():
    row = db.query("SELECT COUNT(*) AS n, MAX(last_error) AS last_error FROM notifications "
                   "WHERE status = 'failed' AND created_at > now() - interval '2 days'", one=True)
    return {"n": int(row["n"]), "last_error": row["last_error"]}
