"""Billing email bodies.

Rendered through a standalone Jinja Environment rather than flask.render_template
because the scheduler process has no app context. Same templates work in both.

Deliverability note: invoice mail carrying a payment link, sent from a fresh
domain over a generic mailbox's SMTP, lands in spam and the client never sees
the invoice. That is a revenue bug dressed as a config detail -- SPF, DKIM and
DMARC on the sending domain are required, and a transactional provider
(Postmark, SES) is strongly preferred over a mailbox.

No tracking pixel: it is a spam signal and a privacy problem, and invoice_views
from the /pay fetch is a more accurate read receipt anyway.
"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

import db
import mailer
import money

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "email")

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["money"] = money.format_money


def _company():
    return {k: db.get_setting(f"billing_{k}", "") for k in
            ("company_name", "company_email", "company_phone", "company_address",
             "payment_instructions")}


def _recipient(customer, livemode=True):
    """In Stripe test mode all customer mail is diverted to the override address
    (or suppressed) -- the guard against sending forty test invoices to real
    clients."""
    override = db.get_setting("billing_test_email_override", "")
    if not livemode and override:
        return override, ""
    if not livemode:
        return None, ""
    return customer.get("email"), customer.get("cc_emails") or ""


def _render(name, **ctx):
    # NOT ctx.setdefault(...): setdefault evaluates its default eagerly, so
    # _company() would run even when the caller supplied one -- and it needs
    # flask.g, which the scheduler process does not have. The scheduler passes
    # `company` in explicitly; this must not touch the database in that case.
    if "company" not in ctx:
        ctx["company"] = _company()
    if "setting" not in ctx:
        ctx["setting"] = db.get_setting
    return (_env.get_template(f"{name}.txt").render(**ctx),
            _env.get_template(f"{name}.html").render(**ctx))


def send_invoice(invoice, customer, pay_url, *, livemode=True, reminder=None,
                 send_after=None):
    to, cc = _recipient(customer, livemode)
    if not to:
        return None
    company = _company()
    prefix = "" if livemode else "[TEST] "
    if reminder is None:
        subject = f"{prefix}Invoice {invoice['number']} from {company['company_name']}"
        kind = "invoice_sent"
    else:
        overdue = reminder > 0
        subject = (f"{prefix}Reminder: invoice {invoice['number']} "
                   f"{'is overdue' if overdue else 'is due'}")
        kind = "invoice_reminder"
    text, html = _render("invoice", inv=invoice, customer=customer,
                         pay_url=pay_url, reminder=reminder, company=company)
    log_id = mailer.queue(kind, to, subject, text, html, cc=cc,
                          customer_id=customer["id"], invoice_id=invoice["id"],
                          send_after=send_after)
    return log_id


def send_receipt(invoice, customer, payment, *, livemode=True):
    to, cc = _recipient(customer, livemode)
    if not to:
        return None
    company = _company()
    prefix = "" if livemode else "[TEST] "
    subject = f"{prefix}Payment received — invoice {invoice['number']}"
    text, html = _render("receipt", inv=invoice, customer=customer,
                         payment=payment, company=company)
    return mailer.queue("payment_receipt", to, subject, text, html, cc=cc,
                        customer_id=customer["id"], invoice_id=invoice["id"])


def send_estimate(estimate, customer, view_url, *, livemode=True):
    to, cc = _recipient(customer, livemode)
    if not to:
        return None
    company = _company()
    prefix = "" if livemode else "[TEST] "
    subject = f"{prefix}Estimate {estimate['number']} from {company['company_name']}"
    text, html = _render("estimate", est=estimate, customer=customer,
                         view_url=view_url, company=company)
    return mailer.queue("estimate_sent", to, subject, text, html, cc=cc,
                        customer_id=customer["id"], estimate_id=estimate["id"])


def alert_admin(subject, body, *, invoice_id=None, customer_id=None):
    """Overpayments, disputes, scheduler problems. Email cannot be the only
    channel for reporting an email failure, so these are also visible in the
    admin -- see the email log and the dashboard badge."""
    to = db.get_setting("billing_admin_alert_email") or db.get_setting("notify_email") \
        or db.get_setting("contact_email")
    if not to:
        return None
    return mailer.queue("admin_alert", to, f"[Billing] {subject}", body,
                        invoice_id=invoice_id, customer_id=customer_id)
