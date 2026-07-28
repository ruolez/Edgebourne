import logging
import smtplib
import threading
from email.message import EmailMessage

import psycopg2.extras

import db

log = logging.getLogger(__name__)

SETTING_KEYS = [
    "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from",
    "smtp_tls", "notify_email", "contact_email", "site_title",
]


def smtp_settings():
    """Read SMTP settings inside a request context; the result is a plain dict
    safe to hand to a background thread."""
    return {k: db.get_setting(k) for k in SETTING_KEYS}


def is_configured(s):
    return bool(s.get("smtp_host") and s.get("smtp_from"))


def notify_to(s):
    return s.get("notify_email") or s.get("contact_email")


def send(s, subject, body, to, *, html=None, cc=None, reply_to=None):
    port = int(s.get("smtp_port") or 587)
    tls = (s.get("smtp_tls") or "starttls").lower()
    if tls == "ssl":
        server = smtplib.SMTP_SSL(s["smtp_host"], port, timeout=20)
    else:
        server = smtplib.SMTP(s["smtp_host"], port, timeout=20)
    try:
        if tls == "starttls":
            server.starttls()
        if s.get("smtp_user"):
            server.login(s["smtp_user"], s.get("smtp_password") or "")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s["smtp_from"]
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Auto-Submitted"] = "auto-generated"
        # Always set the text part first. add_alternative() after set_content()
        # produces a correct multipart/alternative; HTML-only mail is a spam
        # signal and unreadable in plain-text clients.
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def notify_lead(lead):
    """Fire-and-forget notification for a new lead. The lead is already saved;
    a missing config or SMTP failure must never surface to the visitor."""
    s = smtp_settings()
    if not is_configured(s):
        log.info("SMTP not configured — lead %s saved without notification", lead.get("id"))
        return
    to = notify_to(s)
    if not to:
        log.warning("SMTP configured but no notify/contact email set")
        return
    site = s.get("site_title") or "EdgeBourne"
    subject = f"[{site}] New lead: {lead.get('name', '')}"
    lines = [
        f"Name:    {lead.get('name', '')}",
        f"Email:   {lead.get('email', '')}",
        f"Company: {lead.get('company', '') or '—'}",
        f"Phone:   {lead.get('phone', '') or '—'}",
        f"Page:    {lead.get('source_page', '') or '—'}",
        "",
        lead.get("message", ""),
    ]

    def run():
        try:
            send(s, subject, "\n".join(lines), to)
        except Exception:
            log.exception("Lead notification email failed (lead saved fine)")

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# durable queue (billing)
#
# notify_lead()'s fire-and-forget thread is fine for a lead: it is already saved
# and visible in the admin. It is NOT acceptable for an invoice -- a silently
# unsent invoice is revenue nobody discovers for thirty days, and sent_at would
# already be set, so the admin believes it went out.
#
# So billing mail is written to email_log inside the caller's transaction (pass
# cur=... to enlist), then attempted immediately, then retried by the scheduler.
# ---------------------------------------------------------------------------

BACKOFF_MINUTES = [1, 5, 15, 60, 360, 1440]
MAX_ATTEMPTS = len(BACKOFF_MINUTES)


def queue(kind, to, subject, text, html=None, *, cc="", customer_id=None,
          invoice_id=None, estimate_id=None, send_after=None):
    """Insert a queued email. Call inside the same db.transaction() as the state
    change it belongs to, so there is never a window where an invoice is 'open'
    with no email obligation recorded."""
    row = db.execute(
        """INSERT INTO email_log (kind, to_addr, cc_addr, subject, body_text, body_html,
               customer_id, invoice_id, estimate_id, send_after)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, COALESCE(%s, now()))
           RETURNING id""",
        (kind, to, cc or "", subject, text, html, customer_id, invoice_id,
         estimate_id, send_after),
        returning=True,
    )
    return row["id"]


def _mark_sent(conn, log_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE email_log SET status='sent', sent_at=now(), error=NULL, updated_at=now() WHERE id=%s",
            (log_id,),
        )
    conn.commit()


def _mark_failed(conn, log_id, attempts, error):
    permanent = attempts >= MAX_ATTEMPTS
    delay = BACKOFF_MINUTES[min(attempts, MAX_ATTEMPTS - 1)]
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE email_log
                  SET status = %s, attempts = %s, error = %s,
                      next_attempt_at = now() + (%s || ' minutes')::interval,
                      updated_at = now()
                WHERE id = %s""",
            ("permanently_failed" if permanent else "failed", attempts,
             str(error)[:1000], delay, log_id),
        )
    conn.commit()


def _deliver(s, row, conn):
    send(s, row["subject"], row["body_text"], row["to_addr"],
         html=row["body_html"], cc=row["cc_addr"] or None)
    _mark_sent(conn, row["id"])


def try_send_now(log_id):
    """Best-effort immediate delivery on a daemon thread, so the admin gets a
    snappy redirect. The row is already durable; if this fails the scheduler
    retries it. Settings are snapshotted first -- the thread has no app context."""
    s = smtp_settings()
    if not is_configured(s):
        log.info("SMTP not configured — email_log %s left queued", log_id)
        return

    def run():
        try:
            with db.standalone() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM email_log WHERE id=%s AND status IN ('queued','failed')",
                        (log_id,),
                    )
                    row = cur.fetchone()
                conn.commit()
                if not row:
                    return
                try:
                    _deliver(s, row, conn)
                except Exception as e:
                    log.exception("email_log %s send failed", log_id)
                    _mark_failed(conn, log_id, (row["attempts"] or 0) + 1, e)
        except Exception:
            log.exception("email_log %s could not be processed", log_id)

    threading.Thread(target=run, daemon=True).start()


def drain(conn, settings, limit=25):
    """Scheduler job: send anything queued or awaiting retry. Returns the number
    delivered."""
    if not is_configured(settings):
        return 0
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT * FROM email_log
                WHERE status IN ('queued','failed')
                  AND send_after <= now()
                  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY id LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
    conn.commit()
    sent = 0
    for row in rows:
        try:
            _deliver(settings, row, conn)
            sent += 1
        except Exception as e:
            log.warning("email_log %s failed: %s", row["id"], e)
            _mark_failed(conn, row["id"], (row["attempts"] or 0) + 1, e)
    return sent
