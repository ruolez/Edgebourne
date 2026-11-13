"""Emails to leads. Templates live in Settings → Lead replies; a person sends one from the
lead page (edited first if they like), and when the switch is on the default template goes
out by itself to every real lead with an email, signed by the admin who turned it on.

Placeholders: {first_name} {full_name} {business} {phone} {my_name} {my_email} {booking_link}.
A line whose placeholder has no value (no phone, no booking link) is left out.
"""
import logging
import re
from datetime import datetime, timezone

import db
import lead_history
import mailer
import notify
import settings_store

log = logging.getLogger(__name__)

PLACEHOLDERS = ("first_name", "full_name", "business", "phone", "my_name", "my_email", "booking_link")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TOKEN = re.compile(r"\{(\w+)\}")


US_PHONE = re.compile(r"^\+?1?(\d{3})(\d{3})(\d{4})$")


def phone_display(raw):
    raw = (raw or "").strip()
    m = US_PHONE.match(re.sub(r"[\s().-]", "", raw))
    return f"({m.group(1)}) {m.group(2)}-{m.group(3)}" if m else raw


def values(lead, sender, booking_link):
    full = (lead.get("full_name") or "").strip()
    return {
        "first_name": full.split()[0] if full else "there",
        "full_name": full or "there",
        "business": (lead.get("business_type") or "").strip() or "your business",
        "phone": phone_display(lead.get("phone")),
        "my_name": sender.get("name") or "",
        "my_email": sender.get("email") or "",
        "booking_link": (booking_link or "").strip(),
    }


def fill(text, vals):
    out = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        keys = [k for k in TOKEN.findall(line) if k in PLACEHOLDERS]
        if any(not vals.get(k) for k in keys):
            continue
        line = TOKEN.sub(lambda m: vals[m.group(1)] if m.group(1) in PLACEHOLDERS else m.group(0), line)
        if line.strip() == "" and out and out[-1].strip() == "":
            continue
        out.append(line)
    return "\n".join(out).strip()


def auto_reason(lead, enabled):
    """Why a new lead gets no automatic reply, or None when it does."""
    if not enabled:
        return "off"
    if lead.get("is_test"):
        return "test lead"
    if not EMAIL.match((lead.get("email") or "").strip()):
        return "no email"
    if lead.get("repeat_of"):
        return "repeat"     # they had the first reply already (L2)
    if {"test_email", "throwaway_email"} & set(lead.get("junk_flags") or []):
        return "looks fake"  # a bounce hurts the sender's name
    return None


def booking_link():
    return settings_store.get("reply_booking_link") or ""


def auto_enabled():
    return settings_store.get("reply_auto") == "1"


def templates():
    return db.query("SELECT id, name, subject, body, position FROM reply_templates ORDER BY position, id")


def template(template_id=None):
    if template_id:
        row = db.query("SELECT * FROM reply_templates WHERE id = %s", (template_id,), one=True)
        if row:
            return row
    return db.query("SELECT * FROM reply_templates ORDER BY position, id LIMIT 1", one=True)


def draft(lead, sender, template_id=None):
    t = template(template_id)
    if not t:
        return {"template_id": None, "subject": "", "body": "", "to": lead.get("email")}
    v = values(lead, sender, booking_link())
    return {"template_id": t["id"], "subject": fill(t["subject"], v), "body": fill(t["body"], v), "to": lead.get("email")}


def _mail(row, sender):
    mailer.send(row["to_email"], row["subject"], row["body"],
                from_name=sender.get("name"), reply_to=sender.get("email"))


def send_now(lead, sender, subject, body, template_id=None):
    """A reply someone wrote on the lead page. Raises mailer.MailError; the row says failed."""
    row = db.execute(
        "INSERT INTO lead_replies (lead_id, user_id, template_id, to_email, subject, body, attempts, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, 1, 'sending') RETURNING *",
        (lead["id"], sender["id"], template_id, lead["email"].strip(), subject, body), returning=True)
    try:
        _mail(row, sender)
    except mailer.MailError as exc:
        db.execute("UPDATE lead_replies SET status = 'failed', error = %s WHERE id = %s", (str(exc)[:500], row["id"]))
        raise
    db.execute("UPDATE lead_replies SET status = 'sent', sent_at = now() WHERE id = %s", (row["id"],))
    db.execute("UPDATE leads SET first_contacted_at = COALESCE(first_contacted_at, now()) WHERE id = %s", (lead["id"],))
    lead_history.record(lead["id"], "email", ref_id=row["id"], user_id=sender["id"], details={"subject": subject})
    return row


def auto_sender():
    """Who automatic replies are signed by: the admin who turned them on for this account. Only
    Edge Bourne's own account falls back to the first admin; a client's leads must never get an
    email signed by someone the account didn't choose."""
    import account_ctx
    uid = settings_store.get("reply_auto_user_id")
    row = None
    if uid:
        row = db.query("SELECT id, name, email FROM users WHERE id = %s AND is_active", (int(uid),), one=True)
    if row or account_ctx.current() != account_ctx.DEFAULT:
        return row
    return db.query("SELECT id, name, email FROM users WHERE role = 'admin' AND is_active "
                    "AND (account_id IS NULL OR account_id = %s) ORDER BY id LIMIT 1", (account_ctx.DEFAULT,), one=True)


def queue_auto(lead):
    if auto_reason(lead, auto_enabled()) or not mailer.configured():
        return False
    sender = auto_sender()
    if not sender:
        return False
    tid = settings_store.get("reply_auto_template_id")
    d = draft(lead, sender, int(tid) if tid else None)
    if not d["template_id"]:
        return False
    db.execute(
        "INSERT INTO lead_replies (lead_id, user_id, template_id, auto, to_email, subject, body) "
        "VALUES (%s, %s, %s, TRUE, %s, %s, %s) ON CONFLICT (lead_id) WHERE auto DO NOTHING",
        (lead["id"], sender["id"], d["template_id"], lead["email"].strip(), d["subject"], d["body"]))
    return True


def process_pending(now=None):
    now = now or datetime.now(timezone.utc)
    rows = db.query("SELECT r.*, u.name AS sender_name, u.email AS sender_email FROM lead_replies r "
                    "LEFT JOIN users u ON u.id = r.user_id "
                    "WHERE r.status = 'pending' AND r.next_attempt_at <= %s ORDER BY r.id LIMIT 20", (now,))
    notify.settle_interrupted("lead_replies", "error")
    for row in rows:
        if not notify.claim("lead_replies", row["id"]):
            continue
        try:
            _mail(row, {"name": row["sender_name"], "email": row["sender_email"]})
        except mailer.MailError as exc:
            attempts = row["attempts"] + 1
            again = notify.retry_at(attempts, row["created_at"], now, permanent=False)
            db.execute("UPDATE lead_replies SET attempts = %s, error = %s, status = %s, next_attempt_at = COALESCE(%s, next_attempt_at) WHERE id = %s",
                       (attempts, str(exc)[:500], "pending" if again else "failed", again, row["id"]))
            continue
        db.execute("UPDATE lead_replies SET status = 'sent', sent_at = now(), attempts = attempts + 1, error = NULL WHERE id = %s", (row["id"],))
        lead_history.record(row["lead_id"], "email_auto", ref_id=row["id"], actor="system", details={"subject": row["subject"]})
    return len(rows)


def for_lead(lead_id):
    return db.query("SELECT r.id, r.subject, r.body, r.auto, r.status, r.error, r.created_at, r.sent_at, u.name AS sender "
                    "FROM lead_replies r LEFT JOIN users u ON u.id = r.user_id WHERE r.lead_id = %s ORDER BY r.created_at",
                    (lead_id,))


def summary():
    row = db.query("SELECT COUNT(*) FILTER (WHERE status = 'sent' AND created_at > now() - interval '7 days') AS sent_7d, "
                   "COUNT(*) FILTER (WHERE status = 'failed' AND created_at > now() - interval '7 days') AS failed_7d, "
                   "MAX(error) FILTER (WHERE status = 'failed') AS last_error FROM lead_replies", one=True)
    return {"sent_7d": int(row["sent_7d"]), "failed_7d": int(row["failed_7d"]), "last_error": row["last_error"]}
