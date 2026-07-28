"""Billing configuration, plus the read-only Stripe status panel.

Note the deliberate asymmetry with admin/email_settings.py: SMTP credentials are
editable here in the UI, Stripe keys are NOT. They come from the environment and
only a fingerprint is displayed. Reason: with a settable webhook secret, anyone
holding an admin session could point it at a secret they control and then POST
forged, correctly-signed "payment succeeded" events. See backend/config.py.
"""

from flask import flash, jsonify, redirect, render_template, request, url_for

import config
import db
import money

from . import bp

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
    """Everything shown about Stripe is derived from env, never echoed back."""
    key = config.STRIPE_SECRET_KEY
    live = key.startswith("sk_live_")
    base = config.PUBLIC_BASE_URL or request.url_root.rstrip("/")
    return {
        "configured": bool(key),
        "livemode": live,
        "mode": "live" if live else "test",
        "fingerprint": (key[:8] + "…" + key[-4:]) if len(key) > 16 else "",
        "webhook_secret_set": bool(config.STRIPE_WEBHOOK_SECRET),
        "webhook_url": f"{base}/billing/webhook/stripe",
        "public_base_url": config.PUBLIC_BASE_URL,
    }


@bp.get("/billing")
def billing_settings():
    recent = db.query(
        """SELECT stripe_event_id, type, status, received_at
             FROM stripe_events ORDER BY received_at DESC LIMIT 10"""
    )
    last = db.query("SELECT max(received_at) AS at FROM stripe_events", one=True)
    return render_template(
        "admin/billing.html",
        v=_values(),
        stripe=_stripe_status(),
        recent_events=recent,
        last_event_at=last["at"] if last else None,
    )


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
