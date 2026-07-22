import logging
import smtplib
import threading
from email.message import EmailMessage

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


def send(s, subject, body, to):
    port = int(s.get("smtp_port") or 587)
    tls = (s.get("smtp_tls") or "starttls").lower()
    if tls == "ssl":
        server = smtplib.SMTP_SSL(s["smtp_host"], port, timeout=10)
    else:
        server = smtplib.SMTP(s["smtp_host"], port, timeout=10)
    try:
        if tls == "starttls":
            server.starttls()
        if s.get("smtp_user"):
            server.login(s["smtp_user"], s.get("smtp_password") or "")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s["smtp_from"]
        msg["To"] = to
        msg.set_content(body)
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
