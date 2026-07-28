"""Customer-facing document pages, addressed by an unguessable token.

There is no customer login. The token IS the credential, so:

  * Only sha256(token) is stored (invoices.token_hash), which keeps working
    payment links out of every pg_dump in /var/backups.
  * Constant-time comparison is neither needed nor achievable -- the comparison
    happens inside a Postgres B-tree lookup, not in Python. What matters is that
    the failure paths are indistinguishable: same template, same headers, no
    extra query on the miss path.
  * No-store / noindex / no-referrer headers come from NO_STORE_PREFIXES in
    app.py. Without that, app.py's default would put `public, max-age=300` on
    these pages and a shared proxy could serve one client's invoice to another.
  * These pages load ZERO third-party resources, and must never enter
    sitemap.xml.

Routes here are two segments, so they cannot be shadowed by public.py's
one-segment CMS catch-all. The reserved slugs exist to protect the namespace,
not to resolve a routing collision.
"""

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from flask import (
    Blueprint, abort, redirect, render_template, request, url_for,
)

import billing
import config
import db
import money

log = logging.getLogger(__name__)

bp = Blueprint("portal", __name__)


def _client_ip():
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


def base_url():
    return config.PUBLIC_BASE_URL or request.url_root.rstrip("/")


def _lookup(table, prefix, token):
    """Resolve a raw token to its document, honouring the 24h rotation grace
    window. Returns None for anything unknown or expired."""
    if not token or not token.startswith(prefix + "_"):
        return None
    digest = billing.token_hash(token)
    return db.query(
        f"""SELECT * FROM {table}
             WHERE token_hash = %s
                OR (previous_token_hash = %s
                    AND token_rotated_at > now() - interval '24 hours')""",
        (digest, digest),
        one=True,
    )


def _record_view(row, kind):
    """Read receipt, and dispute evidence. A plain UPDATE, deliberately outside
    any transaction -- a failure here must never block the page."""
    try:
        table = "invoices" if kind == "invoice" else "estimates"
        db.execute(
            f"""UPDATE {table}
                   SET first_viewed_at = COALESCE(first_viewed_at, now()),
                       last_viewed_at = now()
                 WHERE id = %s""",
            (row["id"],),
        )
        db.execute(
            """INSERT INTO invoice_views (invoice_id, estimate_id, ip, user_agent)
               VALUES (%s, %s, %s, %s)""",
            (row["id"] if kind == "invoice" else None,
             row["id"] if kind == "estimate" else None,
             _client_ip(), (request.user_agent.string or "")[:400]),
        )
    except Exception:
        log.exception("failed to record a %s view", kind)


def _closed(message, code=410):
    """A stale link gets a friendly explanation, never a bare 404 -- the person
    holding it is a customer, not an attacker."""
    return render_template("portal/closed.html", message=message), code


def _company():
    return {k: db.get_setting(f"billing_{k}", "") for k in
            ("company_name", "company_email", "company_phone", "company_address",
             "tax_number", "payment_instructions", "footer_notes")}


@bp.get("/pay/<token>")
def pay(token):
    inv = _lookup("invoices", "inv", token)
    if not inv:
        abort(404)
    # A draft has no token at all, so this is belt-and-braces.
    if inv["status"] == "draft":
        abort(404)
    # token_expires_at is TIMESTAMPTZ, so compare against an aware datetime.
    if inv["token_expires_at"] and inv["token_expires_at"] < datetime.now(timezone.utc):
        return _closed("This payment link has expired. Please get in touch and we'll send a new one.")
    if inv["status"] in ("void", "uncollectible"):
        return _closed("This invoice is no longer available. Please contact us if you have questions.")

    _record_view(inv, "invoice")
    customer = db.query("SELECT * FROM customers WHERE id = %s", (inv["customer_id"],), one=True)
    return render_template(
        "portal/invoice.html",
        inv=inv,
        token=token,
        customer=customer,
        company=_company(),
        lines=billing.get_lines("invoice", inv["id"]),
        payments=db.query(
            """SELECT * FROM payments WHERE invoice_id = %s AND status = 'succeeded'
                ORDER BY received_on, id""",
            (inv["id"],),
        ),
        can_pay=_can_pay(inv),
        min_payment=int(db.get_setting("billing_min_payment_cents", "100") or 100),
        allow_partial=db.get_setting("billing_allow_partial_payment", "1") == "1",
        canceled=request.args.get("canceled") == "1",
    )


def _can_pay(inv):
    """Card payment is offered only when Stripe is actually usable."""
    if inv["status"] not in billing.INVOICE_OPEN or inv["balance_due_cents"] <= 0:
        return False
    if db.get_setting("billing_enabled", "1") != "1":
        return False
    try:
        import stripe_client
        return stripe_client.is_configured()
    except Exception:
        return False


@bp.get("/estimate/<token>")
def estimate(token):
    est = _lookup("estimates", "est", token)
    if not est:
        abort(404)
    if est["status"] == "draft":
        abort(404)
    if est["status"] == "declined":
        return _closed("This estimate was declined. Please contact us if that was a mistake.")
    expired = bool(est["valid_until"] and est["valid_until"] < date.today())

    _record_view(est, "estimate")
    customer = db.query("SELECT * FROM customers WHERE id = %s", (est["customer_id"],), one=True)
    return render_template(
        "portal/estimate.html",
        est=est,
        token=token,
        customer=customer,
        company=_company(),
        lines=billing.get_lines("estimate", est["id"]),
        expired=expired,
    )


@bp.post("/estimate/<token>/accept")
def estimate_accept(token):
    # Honeypot, following the /contact precedent in public.py.
    if request.form.get("website"):
        return redirect(url_for("portal.estimate", token=token))
    # Classic CSRF does not apply: a third-party site cannot forge this without
    # knowing the token, and no ambient cookie authority is involved. The Origin
    # check blocks the naive case anyway.
    origin = request.headers.get("Origin")
    if origin and not origin.startswith(base_url()):
        abort(400)

    est = _lookup("estimates", "est", token)
    if not est or est["status"] == "draft":
        abort(404)
    if est["status"] != "sent":
        return redirect(url_for("portal.estimate", token=token))
    if est["valid_until"] and est["valid_until"] < date.today():
        return _closed("This estimate has expired. Please contact us for a fresh one.")

    name = (request.form.get("accepted_name") or "").strip()
    if not name:
        return redirect(url_for("portal.estimate", token=token, error="name"))

    db.execute(
        """UPDATE estimates
              SET status = 'accepted', accepted_at = now(), accepted_name = %s,
                  accepted_ip = %s, accepted_user_agent = %s, updated_at = now()
            WHERE id = %s AND status = 'sent'""",
        (name[:200], _client_ip(), (request.user_agent.string or "")[:400], est["id"]),
    )
    try:
        import billing_mail
        customer = db.query("SELECT display_name FROM customers WHERE id = %s",
                            (est["customer_id"],), one=True)
        log_id = billing_mail.alert_admin(
            f"Estimate {est['number']} accepted",
            f"{customer['display_name']} accepted estimate {est['number']} "
            f"({est['total_cents'] / 100:.2f} {est['currency']}).\n"
            f"Signed as: {name}\nIP: {_client_ip()}",
        )
        if log_id:
            import mailer
            mailer.try_send_now(log_id)
    except Exception:
        log.exception("estimate acceptance alert failed (acceptance was recorded)")

    return redirect(url_for("portal.estimate", token=token))


@bp.post("/estimate/<token>/decline")
def estimate_decline(token):
    if request.form.get("website"):
        return redirect(url_for("portal.estimate", token=token))
    est = _lookup("estimates", "est", token)
    if not est or est["status"] != "sent":
        abort(404)
    db.execute(
        """UPDATE estimates SET status='declined', declined_at=now(), updated_at=now()
            WHERE id = %s AND status = 'sent'""",
        (est["id"],),
    )
    return _closed("Thanks for letting us know. We'll be in touch.", 200)


# ---------------------------------------------------------------------------
# Stripe Hosted Checkout
# ---------------------------------------------------------------------------

SESSION_MINUTES = 30


@bp.post("/pay/<token>/checkout")
def pay_checkout(token):
    """Create a Checkout Session and redirect.

    The ordering below is load-bearing: the payments row is COMMITTED before
    Stripe is called, so the idempotency key co:{payment_id} is stable across a
    timeout-and-retry. If the process dies between the two transactions the
    pending row is orphaned but harmless -- no ledger effect ever occurred, and
    the scheduler's sweep cancels it.
    """
    import stripe_client

    inv = _lookup("invoices", "inv", token)
    if not inv or inv["status"] == "draft":
        abort(404)
    if not _can_pay(inv):
        return redirect(url_for("portal.pay", token=token))

    pay_url = f"{base_url()}/pay/{token}"

    with db.transaction():
        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (inv["id"],), one=True)
        state = billing.refresh_invoice_state(inv["id"])
        due = max(state["balance_due_cents"], 0)
        if due <= 0:
            return redirect(pay_url)

        # The amount is NEVER trusted from the form.
        allow_partial = db.get_setting("billing_allow_partial_payment", "1") == "1"
        minimum = int(db.get_setting("billing_min_payment_cents", "100") or 100)
        amount = due
        if allow_partial and request.form.get("amount"):
            try:
                amount = money.parse_money(request.form.get("amount"), label="Amount")
            except money.MoneyError:
                return redirect(pay_url + "?error=amount")
            amount = max(0, min(amount, due))
        if amount < minimum or amount <= 0:
            return redirect(pay_url + "?error=amount")

        # Double-submit guard. Also structurally caps session creation at roughly
        # one per invoice per 30 minutes, which protects real payments from
        # Stripe's write rate limit.
        reuse = db.query(
            """SELECT * FROM payments
                WHERE invoice_id = %s AND status = 'pending' AND amount_cents = %s
                  AND stripe_checkout_session_id IS NOT NULL
                  AND session_expires_at > now() + interval '2 minutes'
                ORDER BY id DESC LIMIT 1""",
            (inv["id"], amount),
            one=True,
        )

        receipt_token = secrets.token_urlsafe(16)
        pending = db.execute(
            """INSERT INTO payments (customer_id, invoice_id, method, amount_cents, currency,
                   status, livemode, receipt_token, receipt_token_expires_at, invoice_version)
               VALUES (%s,%s,'card',%s,%s,'pending',%s,%s, now() + interval '24 hours', %s)
               RETURNING *""",
            (inv["customer_id"], inv["id"], amount, inv["currency"],
             stripe_client.livemode(), receipt_token, inv["version"]),
            returning=True,
        )
    # --- committed; only now do we touch the network ---

    if reuse:
        # Send them back to the SAME Checkout page rather than creating a second
        # session. The URL is not stored anywhere -- it is re-read from Stripe on
        # this rare path, which keeps it out of the database and out of backups.
        try:
            existing = stripe_client.retrieve_checkout_session(
                reuse["stripe_checkout_session_id"], expand=())
            if existing.get("status") == "open" and existing.get("url"):
                db.execute("UPDATE payments SET status='canceled', updated_at=now() WHERE id=%s",
                           (pending["id"],))
                return redirect(existing["url"], code=303)
        except Exception:
            log.warning("could not reuse checkout session %s; creating a new one",
                        reuse["stripe_checkout_session_id"])

    customer = db.query("SELECT * FROM customers WHERE id = %s", (inv["customer_id"],), one=True)
    try:
        sess = stripe_client.create_checkout_session(
            payment_id=pending["id"],
            invoice_id=inv["id"],
            invoice_number=inv["number"],
            invoice_version=inv["version"],
            amount_cents=amount,
            currency=inv["currency"],
            description=inv["title"] or f"Invoice {inv['number']}",
            customer_email=customer["email"],
            stripe_customer_id=customer[stripe_client.customer_id_column()],
            # A SEPARATE short-lived token: whatever URL we hand Stripe is stored
            # on the session and visible in the Dashboard, and the invoice token
            # is a long-lived payment credential.
            success_url=f"{base_url()}/pay/thanks/{receipt_token}",
            cancel_url=f"{pay_url}?canceled=1",
            expires_at=(datetime.now(timezone.utc)
                        + timedelta(minutes=SESSION_MINUTES)).timestamp(),
            statement_descriptor_suffix=db.get_setting("billing_statement_descriptor_suffix"),
        )
    except Exception:
        log.exception("could not create a checkout session for invoice %s", inv["id"])
        db.execute("UPDATE payments SET status='canceled', updated_at=now() WHERE id=%s",
                   (pending["id"],))
        return redirect(pay_url + "?error=stripe")

    db.execute(
        """UPDATE payments SET stripe_checkout_session_id=%s,
               session_expires_at=to_timestamp(%s), updated_at=now()
             WHERE id=%s""",
        (sess["id"], sess.get("expires_at") or 0, pending["id"]),
    )
    return redirect(sess["url"], code=303)


@bp.get("/pay/thanks/<receipt_token>")
def pay_thanks(receipt_token):
    """Post-payment landing. Does NOT decide whether the invoice is paid -- the
    webhook does. It may run the same idempotent apply, so the page is truthful
    when the webhook is a few seconds behind, but the webhook remains the
    authority: this URL is attacker-reachable and the redirect can be skipped
    entirely."""
    pay = db.query(
        """SELECT * FROM payments
            WHERE receipt_token = %s AND receipt_token_expires_at > now()""",
        (receipt_token,),
        one=True,
    )
    if not pay:
        abort(404)

    if pay["status"] in ("pending", "processing") and pay["stripe_checkout_session_id"]:
        try:
            import stripe_client
            import webhooks

            sess = stripe_client.retrieve_checkout_session(pay["stripe_checkout_session_id"])
            # Cross-check what Stripe says against our own row before trusting it.
            meta = sess.get("metadata") or {}
            if meta.get("payment_id") == str(pay["id"]) and sess.get("payment_status") == "paid":
                webhooks.apply_successful_payment(
                    payment_id=pay["id"], invoice_id=pay["invoice_id"],
                    payment_intent_id=(sess.get("payment_intent") or {}).get("id")
                    if isinstance(sess.get("payment_intent"), dict) else sess.get("payment_intent"),
                    session_id=sess.get("id"),
                    amount_cents=sess.get("amount_total"),
                    currency=(sess.get("currency") or "").upper(),
                )
                pay = db.query("SELECT * FROM payments WHERE id = %s", (pay["id"],), one=True)
        except Exception:
            log.exception("thanks-page reconcile failed for payment %s", pay["id"])

    inv = db.query("SELECT * FROM invoices WHERE id = %s", (pay["invoice_id"],), one=True)
    customer = db.query("SELECT * FROM customers WHERE id = %s", (pay["customer_id"],), one=True)
    return render_template("portal/receipt.html", pay=pay, inv=inv, customer=customer,
                           company=_company(), settled=pay["status"] == "succeeded")
