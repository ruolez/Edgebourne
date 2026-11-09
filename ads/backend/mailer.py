import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import settings_store
import site_mail


class MailError(Exception):
    pass


def own_settings():
    return {
        "host": settings_store.get("smtp_host") or "",
        "port": int(settings_store.get("smtp_port") or 587),
        "security": settings_store.get("smtp_security") or "starttls",  # starttls | ssl | none
        "username": settings_store.get("smtp_username") or "",
        "password": settings_store.get("smtp_password") or "",
        "from_email": settings_store.get("smtp_from_email") or "",
    }


def smtp_settings():
    """The console's own mailbox when its SMTP server is filled in, otherwise the
    website's (Admin → Email). "source" says which: own | website | none."""
    s = own_settings()
    source = "own" if s["host"] else "none"
    if not s["host"]:
        site = site_mail.settings()
        if site:
            s, source = site, "website"
    s["from_name"] = settings_store.get("smtp_from_name") or "Edge Bourne Ads"
    s["source"] = source
    return s


def configured():
    s = smtp_settings()
    return bool(s["host"] and s["from_email"])


def send(to, subject, text, html=None, from_name=None, reply_to=None):
    s = smtp_settings()
    if not (s["host"] and s["from_email"]):
        raise MailError("Email isn't set up yet. Set it up in the website admin (Email) or in Settings → Email here.")
    recipients = [to] if isinstance(to, str) else list(to)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name or s["from_name"], s["from_email"]))
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["To"] = ", ".join(recipients)
    msg["Message-ID"] = make_msgid(domain=s["from_email"].split("@")[-1])
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        if s["security"] == "ssl":
            server = smtplib.SMTP_SSL(s["host"], s["port"], timeout=20,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(s["host"], s["port"], timeout=20)
            if s["security"] == "starttls":
                server.starttls(context=ssl.create_default_context())
        with server:
            if s["username"]:
                server.login(s["username"], s["password"])
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"The mail server refused the message: {exc}") from exc
