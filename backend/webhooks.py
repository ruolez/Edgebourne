"""Stripe webhook endpoint. THE authority on whether money moved.

Not under /admin: admin/__init__.py redirects anonymous requests and CSRF-checks
every POST, and Stripe has neither. This placement is deliberate; do not "tidy"
it later.

Status-code contract, because it drives Stripe's retry machine:

  200 - processed, true duplicate, unknown event type, livemode mismatch, an
        event belonging to another integration, or permanently unprocessable.
  400 - signature or parse failure. NEVER 500 here, or a stranger could provoke
        a retry storm.
  500 - only when state may be inconsistent (DB down, unexpected exception).

Handlers do database work only, to stay well inside Stripe's 20-second timeout.
The tempting balance-transaction fee lookup is deferred to the scheduler.
"""

import json
import logging

import psycopg2
from flask import Blueprint, request

import billing
import billing_mail
import db
import mailer
import stripe_client

log = logging.getLogger(__name__)

bp = Blueprint("webhooks", __name__, url_prefix="/billing")

HANDLED = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "charge.succeeded",
    "charge.refunded",
    "charge.refund.updated",
    "charge.dispute.created",
    "charge.dispute.closed",
}


class PermanentlyUnprocessable(Exception):
    """Retrying will never help. Recorded as 'ignored', answered with 200."""


@bp.post("/webhook/stripe")
def stripe_webhook():
    # Read the RAW body before anything touches request.json/request.form --
    # parsing untrusted input before authenticating it is the classic mistake
    # here, and touching request.form would consume the stream.
    payload = request.get_data(cache=False)
    try:
        event = stripe_client.construct_event(payload, request.headers.get("Stripe-Signature", ""))
    except stripe_client.SignatureError as e:
        log.warning("stripe webhook signature rejected: %s", e)
        return "", 400
    except Exception:
        log.exception("stripe webhook parse failure")
        return "", 400

    if bool(event.get("livemode")) != stripe_client.livemode():
        log.warning("stripe webhook livemode mismatch for %s", event.get("id"))
        return "", 200

    api_version = event.get("api_version")
    if api_version and api_version != stripe_client.STRIPE_API_VERSION:
        log.warning("stripe event %s is api_version %s, we pin %s",
                    event.get("id"), api_version, stripe_client.STRIPE_API_VERSION)

    # Dedupe on PROCESSED STATUS, not on row existence. The naive
    # "ON CONFLICT DO NOTHING, skip if present" pattern loses an event forever:
    # insert, fail, return 500, Stripe retries, the retry sees the conflict and
    # skips. Keyed on status, a failed event is retried correctly.
    try:
        with db.transaction():
            row = db.execute(
                """INSERT INTO stripe_events
                     (stripe_event_id, type, livemode, api_version, created_at_stripe,
                      payload, status)
                   VALUES (%s,%s,%s,%s,to_timestamp(%s),%s,'received')
                   ON CONFLICT (stripe_event_id) DO UPDATE
                      SET attempts = stripe_events.attempts + 1, received_at = now()
                   RETURNING id, status, attempts""",
                (event["id"], event["type"], bool(event.get("livemode")), api_version,
                 event.get("created") or 0, json.dumps(event)),
                returning=True,
            )
            if row["status"] == "processed":
                return "", 200
            # Two gunicorn workers can receive the same retry simultaneously.
            db.query("SELECT id FROM stripe_events WHERE id = %s FOR UPDATE NOWAIT",
                     (row["id"],), one=True)
    except psycopg2.errors.LockNotAvailable:
        # Another worker owns it. If that one fails, its own 500 drives the retry.
        return "", 200
    except Exception:
        log.exception("stripe_events insert failed")
        return "", 500  # DB trouble -- Stripe must retry

    try:
        handled = dispatch(event)
    except PermanentlyUnprocessable as e:
        _mark(row["id"], "ignored", str(e))
        return "", 200
    except Exception as e:
        log.exception("webhook handler failed for %s", event["id"])
        _mark(row["id"], "failed", repr(e))
        return "", 500
    _mark(row["id"], "processed" if handled else "ignored")
    return "", 200


def _mark(event_row_id, status, error=None):
    try:
        db.execute(
            """UPDATE stripe_events SET status=%s, error=%s, processed_at=now()
                WHERE id=%s""",
            (status, (error or None) and str(error)[:1000], event_row_id),
        )
    except Exception:
        log.exception("could not mark stripe_event %s as %s", event_row_id, status)


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def dispatch(event):
    kind = event["type"]
    obj = event["data"]["object"]
    if kind not in HANDLED:
        return False

    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return _checkout_completed(obj, event)
    if kind == "checkout.session.async_payment_failed":
        return _payment_failed(obj.get("payment_intent"), "async payment failed")
    if kind == "checkout.session.expired":
        return _session_expired(obj)
    if kind == "payment_intent.succeeded":
        return _payment_intent_succeeded(obj, event)
    if kind == "payment_intent.payment_failed":
        return _payment_failed(obj.get("id"), (obj.get("last_payment_error") or {}).get("message"))
    if kind == "charge.succeeded":
        return _charge_succeeded(obj)
    if kind in ("charge.refunded", "charge.refund.updated"):
        return _charge_refunded(obj)
    if kind == "charge.dispute.created":
        return _dispute_opened(obj)
    if kind == "charge.dispute.closed":
        return _dispute_closed(obj)
    return False


def _ours(metadata):
    """A valid signature proves the event came from Stripe -- not that it is
    OURS. Another integration sharing the same Stripe account delivers here too."""
    return (metadata or {}).get("app") == "edgebourne"


def _find_payment(metadata, payment_intent_id=None, session_id=None):
    meta = metadata or {}
    if meta.get("payment_id"):
        row = db.query("SELECT * FROM payments WHERE id = %s", (int(meta["payment_id"]),), one=True)
        if row:
            return row
    if payment_intent_id:
        row = db.query("SELECT * FROM payments WHERE stripe_payment_intent_id = %s",
                       (payment_intent_id,), one=True)
        if row:
            return row
    if session_id:
        return db.query("SELECT * FROM payments WHERE stripe_checkout_session_id = %s",
                        (session_id,), one=True)
    return None


def _checkout_completed(session, event):
    meta = session.get("metadata") or {}
    if not _ours(meta):
        raise PermanentlyUnprocessable("event is not from this application")
    # checkout.session.completed does NOT mean paid for asynchronous payment
    # methods -- only payment_status does.
    if session.get("payment_status") != "paid":
        pay = _find_payment(meta, session_id=session.get("id"))
        if pay:
            db.execute(
                "UPDATE payments SET status='processing', last_event_at=to_timestamp(%s), updated_at=now() WHERE id=%s",
                (event.get("created") or 0, pay["id"]),
            )
        return True
    return apply_successful_payment(
        payment_id=int(meta["payment_id"]) if meta.get("payment_id") else None,
        invoice_id=int(meta["invoice_id"]) if meta.get("invoice_id") else None,
        payment_intent_id=session.get("payment_intent"),
        session_id=session.get("id"),
        amount_cents=session.get("amount_total"),
        currency=(session.get("currency") or "").upper(),
        invoice_version=int(meta.get("invoice_version") or 0) or None,
        event_created=event.get("created"),
    )


def _payment_intent_succeeded(pi, event):
    """Belt and braces: records the payment even if the session event is lost.
    Fully idempotent via the unique index on stripe_payment_intent_id."""
    meta = pi.get("metadata") or {}
    if not _ours(meta):
        raise PermanentlyUnprocessable("event is not from this application")
    return apply_successful_payment(
        payment_id=int(meta["payment_id"]) if meta.get("payment_id") else None,
        invoice_id=int(meta["invoice_id"]) if meta.get("invoice_id") else None,
        payment_intent_id=pi.get("id"),
        session_id=None,
        amount_cents=pi.get("amount_received") or pi.get("amount"),
        currency=(pi.get("currency") or "").upper(),
        invoice_version=int(meta.get("invoice_version") or 0) or None,
        event_created=event.get("created"),
    )


def apply_successful_payment(*, payment_id, invoice_id, payment_intent_id, session_id,
                             amount_cents, currency, invoice_version=None,
                             event_created=None):
    """Idempotent. Safe to call from the webhook AND from the success redirect.

    Records what Stripe ACTUALLY took, not what we asked for -- if they differ,
    the money is still credited and the row is flagged for a human.
    """
    receipt = None
    with db.transaction():
        pay = _find_payment({"payment_id": payment_id} if payment_id else None,
                            payment_intent_id, session_id)
        if not pay:
            raise PermanentlyUnprocessable("no local payment row for this event")

        pay = db.query("SELECT * FROM payments WHERE id = %s FOR UPDATE", (pay["id"],), one=True)
        if pay["status"] == "succeeded":
            return True  # duplicate delivery

        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE",
                       (pay["invoice_id"] or invoice_id,), one=True)

        review, reason = False, None
        if amount_cents and int(amount_cents) != pay["amount_cents"]:
            review = True
            reason = (f"Stripe charged {amount_cents} but the pending payment was "
                      f"{pay['amount_cents']}")
            amount = int(amount_cents)
        else:
            amount = pay["amount_cents"]
        if inv and invoice_version and inv["version"] != invoice_version:
            review = True
            reason = (reason or "") + " Invoice changed after checkout started."

        db.execute(
            """UPDATE payments
                  SET status='succeeded', amount_cents=%s,
                      stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, %s),
                      stripe_checkout_session_id = COALESCE(stripe_checkout_session_id, %s),
                      needs_review = %s, review_reason = %s,
                      last_event_at = to_timestamp(%s), received_on = current_date,
                      updated_at = now()
                WHERE id = %s""",
            (amount, payment_intent_id, session_id, review, reason,
             event_created or 0, pay["id"]),
        )
        billing.add_ledger(pay["customer_id"], "payment", -amount, pay["currency"],
                           invoice_id=pay["invoice_id"], payment_id=pay["id"],
                           memo="Card payment received")

        if pay["invoice_id"]:
            inv = billing.refresh_invoice_state(pay["invoice_id"])
            # Stripe Checkout charges a fixed amount so it cannot overpay, but a
            # second tab or a cheque arriving meanwhile can. Never auto-refund.
            if inv and inv["amount_paid_cents"] > inv["total_cents"]:
                over = inv["amount_paid_cents"] - inv["total_cents"]
                db.execute("UPDATE payments SET needs_review=true, review_reason=%s WHERE id=%s",
                           (f"Overpaid by {over} cents", pay["id"]))
            customer = db.query("SELECT * FROM customers WHERE id = %s",
                                (pay["customer_id"],), one=True)
            payment_row = db.query("SELECT * FROM payments WHERE id = %s", (pay["id"],), one=True)
            # Queued in the SAME transaction as the ledger mutation, so the
            # receipt fires exactly once whether or not the customer ever saw
            # the success redirect.
            receipt = billing_mail.send_receipt(dict(inv), dict(customer), dict(payment_row),
                                                livemode=stripe_client.livemode())
    if receipt:
        mailer.try_send_now(receipt)
    return True


def _payment_failed(payment_intent_id, message):
    if not payment_intent_id:
        return False
    db.execute(
        """UPDATE payments SET status='failed', review_reason=%s, updated_at=now()
            WHERE stripe_payment_intent_id = %s AND status IN ('pending','processing')""",
        ((message or "payment failed")[:500], payment_intent_id),
    )
    return True


def _session_expired(session):
    db.execute(
        """UPDATE payments SET status='canceled', updated_at=now()
            WHERE stripe_checkout_session_id = %s AND status = 'pending'""",
        (session.get("id"),),
    )
    return True


def _charge_succeeded(charge):
    """Fills in the charge and balance-transaction ids only; the fee lookup is a
    separate API call and is deferred to the scheduler to stay inside Stripe's
    webhook timeout."""
    pi = charge.get("payment_intent")
    if not pi:
        return False
    db.execute(
        """UPDATE payments
              SET stripe_charge_id = %s, stripe_balance_txn_id = %s, updated_at = now()
            WHERE stripe_payment_intent_id = %s""",
        (charge.get("id"), charge.get("balance_transaction"), pi),
    )
    return True


def _charge_refunded(charge):
    """A full SYNC of the charge's refund list, never an append.

    Matching on stripe_refund_id alone would duplicate our own pending row,
    because this event can arrive before the create_refund() response is stored.
    metadata.refund_id exists from the moment the refund is created, so it is a
    join key that is always available.
    """
    pi = charge.get("payment_intent")
    pay = db.query("SELECT * FROM payments WHERE stripe_payment_intent_id = %s", (pi,), one=True)
    if not pay:
        raise PermanentlyUnprocessable("refund for an unknown payment")

    refunds = (charge.get("refunds") or {}).get("data") or []
    with db.transaction():
        for r in refunds:
            local_id = (r.get("metadata") or {}).get("refund_id")
            status = "succeeded" if r.get("status") == "succeeded" else (
                "failed" if r.get("status") in ("failed", "canceled") else "pending")
            if local_id:
                db.execute(
                    """UPDATE refunds SET stripe_refund_id=%s, status=%s, amount_cents=%s,
                           completed_at=now(), updated_at=now()
                         WHERE id=%s""",
                    (r["id"], status, r["amount"], int(local_id)),
                )
            else:
                # Issued directly in the Stripe Dashboard.
                db.execute(
                    """INSERT INTO refunds (payment_id, invoice_id, customer_id, amount_cents,
                           currency, status, stripe_refund_id, reason, initiated_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'stripe_dashboard')
                       ON CONFLICT (stripe_refund_id) DO UPDATE
                          SET status = EXCLUDED.status, amount_cents = EXCLUDED.amount_cents,
                              updated_at = now()""",
                    (pay["id"], pay["invoice_id"], pay["customer_id"], r["amount"],
                     (r.get("currency") or pay["currency"]).upper(), status, r["id"],
                     r.get("reason") or ""),
                )
        _resync_refund_ledger(pay)
        if pay["invoice_id"]:
            billing.refresh_invoice_state(pay["invoice_id"])
    return True


def _resync_refund_ledger(pay):
    """Keep the ledger's refund total equal to the SUM of succeeded refunds.
    Recomputed rather than incremented, so a duplicate delivery cannot
    double-count."""
    total = db.query(
        """SELECT COALESCE(SUM(amount_cents), 0)::bigint AS amt FROM refunds
            WHERE payment_id = %s AND status = 'succeeded'""",
        (pay["id"],),
        one=True,
    )["amt"]
    posted = db.query(
        """SELECT COALESCE(SUM(delta_cents), 0)::bigint AS amt FROM credit_ledger
            WHERE payment_id = %s AND kind = 'refund'""",
        (pay["id"],),
        one=True,
    )["amt"]
    delta = total - posted
    if delta:
        billing.add_ledger(pay["customer_id"], "refund", delta, pay["currency"],
                           invoice_id=pay["invoice_id"], payment_id=pay["id"],
                           memo="Refund issued")


def _dispute_opened(dispute):
    pi = dispute.get("payment_intent")
    pay = db.query("SELECT * FROM payments WHERE stripe_payment_intent_id = %s", (pi,), one=True)
    if not pay:
        raise PermanentlyUnprocessable("dispute for an unknown payment")
    with db.transaction():
        if pay["invoice_id"]:
            db.execute(
                "UPDATE invoices SET status='disputed', updated_at=now() WHERE id=%s",
                (pay["invoice_id"],),
            )
        db.execute("UPDATE payments SET needs_review=true, review_reason=%s WHERE id=%s",
                   ("Chargeback opened", pay["id"]))
        billing.add_ledger(pay["customer_id"], "chargeback", dispute.get("amount") or 0,
                           pay["currency"], invoice_id=pay["invoice_id"], payment_id=pay["id"],
                           memo="Funds held for dispute")
    log_id = billing_mail.alert_admin(
        "Chargeback opened — evidence deadline applies",
        f"A dispute was opened on payment #{pay['id']}"
        f"{' (invoice #' + str(pay['invoice_id']) + ')' if pay['invoice_id'] else ''}.\n"
        f"Amount: {dispute.get('amount')} {(dispute.get('currency') or '').upper()}\n"
        f"Reason: {dispute.get('reason')}\n\n"
        "Respond in the Stripe Dashboard before the evidence deadline.",
        invoice_id=pay["invoice_id"],
    )
    if log_id:
        mailer.try_send_now(log_id)
    return True


def _dispute_closed(dispute):
    pi = dispute.get("payment_intent")
    pay = db.query("SELECT * FROM payments WHERE stripe_payment_intent_id = %s", (pi,), one=True)
    if not pay:
        raise PermanentlyUnprocessable("dispute for an unknown payment")
    won = dispute.get("status") == "won"
    with db.transaction():
        if won:
            # Reverse the hold; the money comes back.
            billing.add_ledger(pay["customer_id"], "chargeback", -(dispute.get("amount") or 0),
                               pay["currency"], invoice_id=pay["invoice_id"],
                               payment_id=pay["id"], memo="Dispute won — hold released")
        if pay["invoice_id"]:
            db.execute(
                """UPDATE invoices SET status = CASE WHEN %s THEN 'open' ELSE 'uncollectible' END,
                       updated_at = now()
                     WHERE id = %s AND status = 'disputed'""",
                (won, pay["invoice_id"]),
            )
            billing.refresh_invoice_state(pay["invoice_id"])
    return True
