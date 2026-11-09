"""Every alert to a person goes through here: queued per person and channel, sent by the
background worker within seconds, retried a few times, never sent twice (dedupe_key).

Channels: telegram (the person linked their chat and kept it on). New-lead emails still go
out from leads.notify, as before; reminders (1.4) use both.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

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
    return f"New{test} lead: {lead.get('full_name') or 'Someone'}", lines


def telegram_people(user_ids):
    """Of these people, the ones Telegram alerts can reach right now."""
    if not user_ids or not telegram.token():
        return []
    rows = db.query("SELECT id FROM users WHERE id = ANY(%s) AND is_active AND notify_telegram AND telegram_chat_id IS NOT NULL",
                    (list(user_ids),))
    return [r["id"] for r in rows]


def queue(user_id, channel, kind, title, lines, url=None, button="Open", ref=None, dedupe_key=None):
    db.execute(
        "INSERT INTO notifications (user_id, channel, kind, ref, dedupe_key, title, lines, url, button) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dedupe_key) DO NOTHING",
        (user_id, channel, kind, ref, dedupe_key, title, json.dumps(lines), url, button))


def _deliver(row):
    if row["channel"] == "telegram":
        user = db.query("SELECT telegram_chat_id FROM users WHERE id = %s AND notify_telegram", (row["user_id"],), one=True)
        if not user or not user["telegram_chat_id"]:
            raise telegram.TelegramError("Telegram isn't linked any more", status=403)
        telegram.send(user["telegram_chat_id"], row["title"], row["lines"], row["url"], row["button"] or "Open")
    elif row["channel"] == "email":
        user = db.query("SELECT email FROM users WHERE id = %s", (row["user_id"],), one=True)
        link = f"\n\n{row['button'] or 'Open'}: {row['url']}" if row["url"] else ""
        mailer.send(user["email"], row["title"], "\n".join(row["lines"]) + link)
    else:
        raise telegram.TelegramError(f"Unknown channel {row['channel']}", status=400)


def process_pending(now=None):
    now = now or datetime.now(timezone.utc)
    rows = db.query("SELECT * FROM notifications WHERE status = 'pending' AND next_attempt_at <= %s ORDER BY id LIMIT 50", (now,))
    for row in rows:
        try:
            _deliver(row)
        except (telegram.TelegramError, mailer.MailError) as exc:
            attempts = row["attempts"] + 1
            again = retry_at(attempts, row["created_at"], now, getattr(exc, "permanent", False))
            db.execute("UPDATE notifications SET attempts = %s, last_error = %s, status = %s, next_attempt_at = COALESCE(%s, next_attempt_at) WHERE id = %s",
                       (attempts, str(exc)[:500], "pending" if again else "failed", again, row["id"]))
            log.info("notification %s (%s) not sent: %s", row["id"], row["channel"], exc)
            continue
        db.execute("UPDATE notifications SET status = 'sent', sent_at = now(), attempts = attempts + 1, last_error = NULL WHERE id = %s", (row["id"],))
    return len(rows)


def failed_recently():
    row = db.query("SELECT COUNT(*) AS n, MAX(last_error) AS last_error FROM notifications "
                   "WHERE status = 'failed' AND created_at > now() - interval '2 days'", one=True)
    return {"n": int(row["n"]), "last_error": row["last_error"]}
