"""Payments: recording money received, voiding a mistake, applying credit.

Cross-resource POST paths (POST /invoices/<id>/payments) live here rather than
in invoices.py -- legal because admin is one shared blueprint, and it keeps the
URL hierarchy honest.
"""

from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import billing
import db
import money

from . import bp

METHODS = [
    ("bank_transfer", "Bank transfer / ACH"), ("check", "Cheque"),
    ("cash", "Cash"), ("card", "Card"), ("other", "Other"),
]
# 'credit' is deliberately absent: credit is applied through apply_credit(),
# which writes the balancing ledger pair. Recording it as a plain payment would
# double-count the money.
MANUAL_METHODS = {m for m, _ in METHODS if m != "card"}


def _actor():
    return (session.get("user_id"), session.get("username"),
            request.headers.get("X-Real-IP") or request.remote_addr)


@bp.get("/payments")
def payments_list():
    method = request.args.get("method", "")
    where, params = ["p.status <> 'pending'"], []
    if method:
        where.append("p.method = %s")
        params.append(method)
    rows = db.query(
        f"""SELECT p.*, c.display_name AS customer_name, i.number AS invoice_number
              FROM payments p
              JOIN customers c ON c.id = p.customer_id
              LEFT JOIN invoices i ON i.id = p.invoice_id
             WHERE {' AND '.join(where)}
             ORDER BY p.received_on DESC, p.id DESC LIMIT 300""",
        tuple(params),
    )
    totals = db.query(
        # Cash actually received. Credit applications are real payment rows but
        # move money collected earlier, so including them would double-count.
        """SELECT COALESCE(SUM(amount_cents), 0)::bigint AS mtd
             FROM payments
            WHERE status = 'succeeded' AND method <> 'credit'
              AND received_on >= date_trunc('month', current_date)""",
        one=True,
    )
    return render_template("admin/payments.html", rows=rows, method=method,
                           methods=METHODS, totals=totals)


@bp.post("/invoices/<int:iid>/payments")
def payment_record(iid):
    f = request.form
    method = f.get("method") or "bank_transfer"
    if method not in MANUAL_METHODS:
        flash("Pick a valid payment method.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    try:
        amount = money.parse_money(f.get("amount"), label="Payment amount")
        received_on = billing.parse_date(f.get("received_on"))
        result = billing.record_payment(
            iid, amount, method=method, received_on=received_on,
            reference=(f.get("reference") or "").strip(),
            memo=(f.get("memo") or "").strip(),
            user_id=session.get("user_id"),
        )
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return redirect(url_for("admin.invoice_form", iid=iid))

    billing.audit(*_actor(), "payment_record", "invoice", iid, {"amount_cents": amount})
    if result["overpaid_cents"]:
        flash(
            f"Recorded {money.format_money(amount)}. "
            f"{money.format_money(result['overpaid_cents'])} exceeded the balance and is now "
            f"credit on this customer's account.",
            "success",
        )
    else:
        flash(f"Recorded {money.format_money(amount)}.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/customers/<int:cid>/payments")
def payment_on_account(cid):
    f = request.form
    method = f.get("method") or "bank_transfer"
    if method not in MANUAL_METHODS:
        flash("Pick a valid payment method.", "error")
        return redirect(url_for("admin.customer_detail", cid=cid, tab="payments"))
    try:
        amount = money.parse_money(f.get("amount"), label="Payment amount")
        billing.record_payment(
            None, amount, method=method,
            received_on=billing.parse_date(f.get("received_on")),
            reference=(f.get("reference") or "").strip(),
            memo=(f.get("memo") or "").strip(),
            customer_id=cid, user_id=session.get("user_id"),
        )
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return redirect(url_for("admin.customer_detail", cid=cid, tab="payments"))
    billing.audit(*_actor(), "payment_on_account", "customer", cid, {"amount_cents": amount})
    flash(f"Recorded {money.format_money(amount)} on account.", "success")
    return redirect(url_for("admin.customer_detail", cid=cid, tab="payments"))


@bp.post("/invoices/<int:iid>/apply-credit")
def payment_apply_credit(iid):
    inv = db.query("SELECT * FROM invoices WHERE id = %s", (iid,), one=True)
    if not inv:
        abort(404)
    raw = (request.form.get("amount") or "").strip()
    try:
        amount = money.parse_money(raw, label="Amount") if raw else None
        applied = billing.apply_credit(inv["customer_id"], iid, amount,
                                       user_id=session.get("user_id"))
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    billing.audit(*_actor(), "credit_apply", "invoice", iid, {"amount_cents": applied})
    flash(f"Applied {money.format_money(applied, inv['currency'])} of credit.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/payments/<int:pid>/void")
def payment_void(pid):
    pay = db.query("SELECT * FROM payments WHERE id = %s", (pid,), one=True)
    if not pay:
        abort(404)
    try:
        billing.void_payment(pid, user_id=session.get("user_id"))
    except billing.BillingError as e:
        flash(str(e), "error")
    else:
        billing.audit(*_actor(), "payment_void", "payment", pid,
                      {"amount_cents": pay["amount_cents"]})
        flash("Payment voided. The invoice balance has been restored.", "success")
    if pay["invoice_id"]:
        return redirect(url_for("admin.invoice_form", iid=pay["invoice_id"]))
    return redirect(url_for("admin.customer_detail", cid=pay["customer_id"], tab="payments"))


@bp.post("/payments/<int:pid>/refund")
def payment_refund(pid):
    """Admin-initiated refund.

    Requires the admin's password again: this moves money OUT, and a hijacked
    session must not be able to drain the account by clicking a button.
    """
    pay = db.query("SELECT * FROM payments WHERE id = %s", (pid,), one=True)
    if not pay:
        abort(404)

    user = db.query("SELECT * FROM users WHERE id = %s", (session.get("user_id"),), one=True)
    if not user or not check_password_hash(user["password_hash"],
                                           request.form.get("password") or ""):
        flash("Password incorrect — the refund was not issued.", "error")
        return _back(pay)

    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Give a reason for the refund.", "error")
        return _back(pay)

    try:
        amount = (money.parse_money(request.form["amount"], label="Refund amount")
                  if (request.form.get("amount") or "").strip() else None)
        ref = billing.start_refund(pid, amount, reason, user_id=session.get("user_id"))
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return _back(pay)

    # The refunds row is committed; only now do we touch the network, so the
    # idempotency key rf:{id} is stable across a timeout and retry.
    if pay["method"] == "card" and pay["stripe_payment_intent_id"]:
        try:
            import stripe_client
            result = stripe_client.create_refund(
                refund_id=ref["id"], payment_intent_id=pay["stripe_payment_intent_id"],
                amount_cents=ref["amount_cents"], reason=None,
                metadata={"invoice_id": str(pay["invoice_id"] or "")})
            billing.settle_refund(
                ref["id"],
                status={"succeeded": "succeeded", "pending": "pending"}.get(
                    result.get("status"), "failed"),
                stripe_refund_id=result.get("id"), user_id=session.get("user_id"))
        except Exception as e:
            billing.settle_refund(ref["id"], status="error", error=str(e),
                                  user_id=session.get("user_id"))
            flash(f"Stripe refused the refund: {e}. It is recorded as failed — retry safely, "
                  "the same refund will not be issued twice.", "error")
            return _back(pay)
    else:
        billing.settle_refund(ref["id"], status="succeeded", user_id=session.get("user_id"))

    if request.form.get("credit_note"):
        try:
            billing.credit_note(pay["invoice_id"], ref["amount_cents"],
                                f"Credit note with refund: {reason}",
                                user_id=session.get("user_id"))
        except billing.BillingError as e:
            flash(f"Refund issued, but the credit note failed: {e}", "error")

    billing.audit(*_actor(), "payment_refund", "payment", pid,
                  {"amount_cents": ref["amount_cents"], "reason": reason})
    flash(f"Refunded {money.format_money(ref['amount_cents'], pay['currency'])}.", "success")
    return _back(pay)


def _back(pay):
    if pay["invoice_id"]:
        return redirect(url_for("admin.invoice_form", iid=pay["invoice_id"]))
    return redirect(url_for("admin.customer_detail", cid=pay["customer_id"], tab="payments"))


@bp.get("/billing/email-log")
def email_log_page():
    """Email cannot be the only channel for reporting an email failure."""
    rows = db.query(
        """SELECT e.*, c.display_name AS customer_name, i.number AS invoice_number
             FROM email_log e
             LEFT JOIN customers c ON c.id = e.customer_id
             LEFT JOIN invoices i ON i.id = e.invoice_id
            ORDER BY e.id DESC LIMIT 200"""
    )
    return render_template("admin/email_log.html", rows=rows)


@bp.post("/billing/email-log/<int:lid>/resend")
def email_log_resend(lid):
    import mailer
    row = db.execute(
        """UPDATE email_log SET status='queued', next_attempt_at=NULL, send_after=now(),
               attempts=0, error=NULL, updated_at=now()
             WHERE id=%s RETURNING id""", (lid,), returning=True)
    if not row:
        abort(404)
    mailer.try_send_now(lid)
    flash("Queued for sending.", "success")
    return redirect(url_for("admin.email_log_page"))


@bp.post("/billing/email-log/<int:lid>/cancel")
def email_log_cancel(lid):
    """The billing_send_delay_minutes window exists so a scheduler mistake is
    'delete a draft', not 'apologise to the client'. This is that button."""
    db.execute(
        """UPDATE email_log SET status='canceled', updated_at=now()
            WHERE id=%s AND status IN ('queued','failed')""", (lid,))
    flash("Cancelled — it will not be sent.", "success")
    return redirect(url_for("admin.email_log_page"))


@bp.get("/billing/audit")
def billing_audit_page():
    rows = billing.audit_consistency()
    for r in rows:
        r["drift_cents"] = r["ledger_balance"] - r["expected_balance"]
        r["ok"] = r["drift_cents"] == 0 and r["currencies"] <= 1 and not r["needs_review"]
    return render_template(
        "admin/billing_audit.html",
        rows=rows,
        problems=[r for r in rows if not r["ok"]],
        recent=db.query("SELECT * FROM billing_audit ORDER BY created_at DESC LIMIT 50"),
    )
