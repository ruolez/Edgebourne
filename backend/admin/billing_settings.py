"""Billing configuration, including the Stripe keys.

Payment secrets are editable here but never stored in the clear: secrets_store
encrypts them with a key derived from SECRET_KEY, which lives in .env and is
never written to the database, so a stolen pg_dump yields ciphertext.

Two further guards, because a settable webhook secret is exactly what an
attacker with a stolen admin session would want -- point it at a secret they
control, then POST forged, correctly-signed "payment succeeded" events:

  * changing any payment secret requires the admin password again;
  * every change is written to billing_audit and emailed to the alert address.

Environment variables still take precedence when set, for operators who would
rather keep keys off the box entirely.
"""

import logging

from flask import (
    flash, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

import billing
import config
import db
import money
import secrets_store

from . import bp

log = logging.getLogger(__name__)

# Written encrypted, shown only as a mask or a fingerprint.
SECRET_FIELDS = [
    ("stripe_secret_key", "Secret key", "sk_live_… or sk_test_…"),
    ("stripe_webhook_secret", "Webhook signing secret", "whsec_…"),
]

# Plain text settings, saved verbatim.
TEXT_FIELDS = [
    "billing_currency", "billing_tax_label", "billing_tax_number",
    "billing_invoice_prefix", "billing_estimate_prefix", "billing_number_period",
    "billing_company_name", "billing_company_address", "billing_company_email",
    "billing_company_phone", "billing_company_logo", "billing_payment_instructions",
    "billing_default_terms_text", "billing_footer_notes", "billing_timezone",
    "billing_catchup_mode", "billing_reminder_days", "billing_admin_alert_email",
    "billing_test_email_override",
]

# Checkboxes: absent from the form means unchecked, so they cannot use the
# TEXT_FIELDS loop (a missing key would blank a real value).
BOOL_FIELDS = [
    "billing_enabled", "billing_allow_partial_payment",
    "billing_default_auto_send", "billing_reminder_enabled",
]

# (key, minimum, maximum)
INT_FIELDS = [
    ("billing_default_terms_days", 0, 365),
    ("billing_number_pad", 1, 10),
    ("billing_run_hour", 0, 23),
    ("billing_send_delay_minutes", 0, 1440),
    ("billing_estimate_valid_days", 1, 365),
    ("billing_token_ttl_days", 1, 3650),
]

MONEY_FIELDS = ["billing_min_payment_cents", "billing_auto_send_max_cents"]


def _values():
    keys = (
        TEXT_FIELDS
        + BOOL_FIELDS
        + [k for k, _, _ in INT_FIELDS]
        + MONEY_FIELDS
        + ["billing_tax_rate_milli", "billing_statement_descriptor_suffix"]
    )
    return {k: db.get_setting(k, "") for k in keys}


def _stripe_status():
    """Secrets are never echoed back -- only a fingerprint and whether they are
    set. Fields managed by the environment are reported as locked, so the UI
    does not pretend to control something it cannot."""
    import stripe_client

    key = stripe_client.secret_key()
    live = key.startswith("sk_live_")
    base = config.site_base_url(request.url_root)
    return {
        "configured": bool(key),
        "livemode": live,
        "mode": "live" if live else "test",
        "fingerprint": (key[:8] + "…" + key[-4:]) if len(key) > 16 else "",
        "webhook_secret_set": bool(stripe_client.webhook_secrets()),
        "webhook_url": f"{base}/billing/webhook/stripe",
        "site_url": config.site_base_url(""),
        "env_locked": {
            "stripe_secret_key": bool(config.STRIPE_SECRET_KEY),
            "stripe_webhook_secret": bool(config.STRIPE_WEBHOOK_SECRET),
            "site_url": bool(config.PUBLIC_BASE_URL),
        },
        "any_env_locked": bool(config.STRIPE_SECRET_KEY or config.STRIPE_WEBHOOK_SECRET
                               or config.PUBLIC_BASE_URL),
    }


@bp.get("/billing")
def billing_settings():
    recent = db.query(
        """SELECT stripe_event_id, type, status, received_at
             FROM stripe_events ORDER BY received_at DESC LIMIT 10"""
    )
    last = db.query("SELECT max(received_at) AS at FROM stripe_events", one=True)
    values = _values()
    values["site_url"] = db.get_setting("site_url", "")
    for key, _, _ in SECRET_FIELDS:
        values[key] = secrets_store.MASK if secrets_store.is_set(key) else ""
    return render_template(
        "admin/billing.html",
        v=values,
        secret_fields=SECRET_FIELDS,
        mask=secrets_store.MASK,
        stripe=_stripe_status(),
        recent_events=recent,
        last_event_at=last["at"] if last else None,
    )


@bp.post("/billing/keys")
def billing_keys_save():
    """Payment secrets are saved on their own form, separately from the ordinary
    settings, so the password prompt only appears when it is actually needed."""
    import stripe_client

    user = db.query("SELECT * FROM users WHERE id = %s", (session.get("user_id"),), one=True)
    if not user or not check_password_hash(user["password_hash"],
                                           request.form.get("password") or ""):
        flash("Password incorrect — the payment keys were not changed.", "error")
        return redirect(url_for("admin.billing_settings"))

    changed = []
    for key, label, _ in SECRET_FIELDS:
        if getattr(config, key.upper(), ""):
            continue  # the environment owns this one
        submitted = request.form.get(key)
        if key == "stripe_webhook_secret" and submitted and submitted.strip() not in (
                "", secrets_store.MASK):
            # Keep the outgoing secret valid for one rotation so events signed
            # with it are still accepted while Stripe switches over.
            previous = secrets_store.get_secret("stripe_webhook_secret")
            if previous and previous != submitted.strip():
                secrets_store.set_secret("stripe_webhook_secret_previous", previous)
        if secrets_store.save_masked(key, submitted):
            changed.append(label)

    site_url = (request.form.get("site_url") or "").strip().rstrip("/")
    if not config.PUBLIC_BASE_URL and site_url != db.get_setting("site_url", ""):
        if site_url and not site_url.startswith(("http://", "https://")):
            flash("The public site address must start with https:// or http://.", "error")
            return redirect(url_for("admin.billing_settings"))
        db.set_setting("site_url", site_url)
        changed.append("Public site address")

    if not changed:
        flash("Nothing changed.", "success")
        return redirect(url_for("admin.billing_settings"))

    ip = request.headers.get("X-Real-IP") or request.remote_addr
    billing.audit(session.get("user_id"), session.get("username"), ip,
                  "stripe_keys_changed", "settings", None, {"fields": changed})
    # Emailed as well as logged: silently swapping the webhook secret is the
    # single most valuable thing an attacker with a session could do here.
    try:
        import billing_mail
        import mailer

        log_id = billing_mail.alert_admin(
            "Payment keys were changed",
            f"{', '.join(changed)} changed by "
            f"{session.get('username') or 'an admin'} from {ip}.\n\n"
            "If that was not you, rotate the keys in the Stripe Dashboard now.")
        if log_id:
            mailer.try_send_now(log_id)
    except Exception:
        log.exception("could not send the key-change alert")

    flash(f"Updated: {', '.join(changed)}. Mode is now {stripe_client.mode_label().upper()}.",
          "success")
    return redirect(url_for("admin.billing_settings"))


@bp.post("/billing")
def billing_settings_save():
    form = request.form

    currency = (form.get("billing_currency") or "USD").strip().upper()
    try:
        money.check_supported(currency)
    except money.MoneyError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.billing_settings"))

    for key in TEXT_FIELDS:
        value = (form.get(key) or "").strip()
        if key == "billing_currency":
            value = currency
        db.set_setting(key, value)

    for key in BOOL_FIELDS:
        db.set_setting(key, "1" if form.get(key) else "")

    for key, lo, hi in INT_FIELDS:
        raw = (form.get(key) or "").strip()
        try:
            value = int(raw)
        except ValueError:
            flash(f"{key.replace('billing_', '').replace('_', ' ').capitalize()} must be a whole number.", "error")
            return redirect(url_for("admin.billing_settings"))
        db.set_setting(key, str(max(lo, min(hi, value))))

    try:
        for key in MONEY_FIELDS:
            db.set_setting(key, str(money.parse_money(form.get(key), default=0)))
        db.set_setting(
            "billing_tax_rate_milli",
            str(money.parse_rate(form.get("billing_tax_rate_milli"), default=0)),
        )
    except money.MoneyError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.billing_settings"))

    # Stripe caps this at 22 chars and rejects several symbols; trim rather than
    # letting the whole checkout session fail later.
    db.set_setting(
        "billing_statement_descriptor_suffix",
        (form.get("billing_statement_descriptor_suffix") or "").strip()[:22],
    )

    flash("Billing settings saved.", "success")
    return redirect(url_for("admin.billing_settings"))


@bp.post("/billing/stripe-test")
def billing_stripe_test():
    """Mirrors /admin/email/test: a JSON round-trip proving the key works."""
    try:
        import stripe_client
    except Exception as e:  # pragma: no cover - import guard
        return jsonify({"ok": False, "error": f"Stripe client unavailable: {e}"})
    if not stripe_client.is_configured():
        return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not set in the environment."})
    try:
        account = stripe_client.account_check()
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"})
    return jsonify({"ok": True, "account": account})
