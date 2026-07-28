"""The ONLY module that talks to Stripe. Returns plain dicts, never Stripe objects.

Why the official SDK rather than urllib against a 5-package dependency policy:
that policy exists to keep the image small, not to justify hand-rolling the one
library guarding the money path. A raw client would have to get webhook HMAC
parsing (including multiple signatures during secret rotation and the replay
tolerance window), idempotency-key retry semantics, and the error taxonomy all
correct -- and each is a money bug when wrong.

Keys come from the ENVIRONMENT, never the settings table -- see config.py for
the four reasons. Mode is derived from the key prefix so it cannot desynchronise
from a separate toggle.

Every idempotency key is derived from a local row id that is ALREADY COMMITTED
before the call, so a timeout-and-retry returns the original object instead of
creating a second charge.
"""

import hashlib
import hmac
import json
import logging
import time

import config

log = logging.getLogger(__name__)

# Pinned in code, not only in the Dashboard: someone clicking "upgrade" there
# must not be able to change webhook payload shapes under a running integration.
STRIPE_API_VERSION = "2025-08-27.basil"

# gunicorn serves only 8 concurrent requests for the WHOLE site (2 workers x 4
# threads). A Stripe hang on the default 80s timeout would take the marketing
# site down with it.
REQUEST_TIMEOUT = 20
SIGNATURE_TOLERANCE = 300  # seconds


class StripeNotConfigured(RuntimeError):
    pass


class SignatureError(RuntimeError):
    pass


class StripeCallError(RuntimeError):
    def __init__(self, message, *, code=None, kind=None, request_id=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.kind = kind
        self.request_id = request_id
        self.http_status = http_status


def _stripe():
    """Lazy import + configure. gunicorn --preload runs create_app() in the
    arbiter, so a module-level api_key assignment would execute there; a missing
    or bad key must degrade the billing UI, never crash boot."""
    if not config.STRIPE_SECRET_KEY:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not set.")
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    stripe.api_version = STRIPE_API_VERSION
    stripe.max_network_retries = 1  # request path; the scheduler raises this
    return stripe


def _call(fn, *args, **kwargs):
    """Translate the SDK's exception hierarchy into one local error type."""
    import stripe as _s

    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    try:
        return fn(*args, **kwargs)
    except _s.CardError as e:
        raise StripeCallError(e.user_message or str(e), code=e.code, kind="card_error",
                              request_id=e.request_id, http_status=e.http_status)
    except _s.RateLimitError as e:
        raise StripeCallError(str(e), kind="rate_limit", request_id=e.request_id)
    except _s.IdempotencyError as e:
        # Same key, different parameters -- always a bug on our side.
        raise StripeCallError(str(e), kind="idempotency", request_id=e.request_id)
    except _s.InvalidRequestError as e:
        raise StripeCallError(str(e), code=getattr(e, "code", None), kind="invalid_request",
                              request_id=e.request_id, http_status=e.http_status)
    except _s.AuthenticationError as e:
        raise StripeCallError("Stripe rejected the API key.", kind="auth",
                              request_id=e.request_id)
    except _s.APIConnectionError as e:
        raise StripeCallError(str(e), kind="connection")
    except _s.StripeError as e:
        raise StripeCallError(str(e), kind="api_error", request_id=getattr(e, "request_id", None))


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

def is_configured():
    return bool(config.STRIPE_SECRET_KEY)


def livemode():
    return config.STRIPE_SECRET_KEY.startswith("sk_live_")


def mode_label():
    return "live" if livemode() else "test"


def key_fingerprint():
    key = config.STRIPE_SECRET_KEY
    return f"{key[:8]}…{key[-4:]}" if len(key) > 16 else ""


def customer_id_column():
    """Switching modes must never hand a test cus_ to the live API."""
    return "stripe_customer_id" if livemode() else "stripe_customer_id_test"


def account_check():
    s = _stripe()
    acct = _call(s.Account.retrieve)
    return {
        "id": acct.get("id"),
        "business_name": (acct.get("business_profile") or {}).get("name") or acct.get("id"),
        "charges_enabled": bool(acct.get("charges_enabled")),
        "default_currency": (acct.get("default_currency") or "").upper(),
        "mode": mode_label(),
    }


# ---------------------------------------------------------------------------
# customers
# ---------------------------------------------------------------------------

def ensure_customer(*, local_customer_id, name, email, address=None, existing_stripe_id=None):
    s = _stripe()
    payload = {"name": name or None, "email": email or None,
               "metadata": {"app": "edgebourne", "customer_id": str(local_customer_id)}}
    if address:
        payload["address"] = {k: v for k, v in address.items() if v}
    if existing_stripe_id:
        try:
            return _call(s.Customer.modify, existing_stripe_id, **payload)["id"]
        except StripeCallError as e:
            if e.kind != "invalid_request":
                raise
            log.warning("stripe customer %s gone, recreating", existing_stripe_id)
    created = _call(s.Customer.create,
                    idempotency_key=f"cust:{local_customer_id}:{mode_label()}", **payload)
    return created["id"]


# ---------------------------------------------------------------------------
# checkout
# ---------------------------------------------------------------------------

def create_checkout_session(*, payment_id, invoice_id, invoice_number, invoice_version,
                            amount_cents, currency, description, customer_email,
                            stripe_customer_id, success_url, cancel_url,
                            expires_at, statement_descriptor_suffix=None):
    """One synthetic line item, not a mapping of invoice lines.

    Partial payments make a line mapping meaningless, and Stripe requires the
    line items to sum EXACTLY to the charge -- distributing tax and discounts
    across many lines is a classic off-by-one-cent failure that rejects the
    whole session. The customer already sees the itemisation on our page;
    Checkout only needs to collect the money.
    """
    s = _stripe()
    metadata = {
        "app": "edgebourne",
        "payment_id": str(payment_id),
        "invoice_id": str(invoice_id),
        "invoice_number": invoice_number or "",
        "invoice_version": str(invoice_version or 1),
    }
    payload = {
        "mode": "payment",
        "line_items": [{
            "price_data": {
                "currency": currency.lower(),
                "unit_amount": int(amount_cents),
                "product_data": {
                    "name": f"Invoice {invoice_number}",
                    "description": (description or "")[:500] or None,
                },
            },
            "quantity": 1,
        }],
        "client_reference_id": f"pay_{payment_id}",
        "metadata": metadata,
        # Metadata on the PaymentIntent too, not just the Session: charge.refunded
        # and charge.dispute.created carry a Charge with a payment_intent and NO
        # session, so without this you cannot resolve them back to an invoice.
        "payment_intent_data": {
            "description": f"Invoice {invoice_number}",
            "metadata": metadata,
        },
        "success_url": success_url,
        "cancel_url": cancel_url,
        "expires_at": int(expires_at),
        "automatic_tax": {"enabled": False},   # we compute tax ourselves
        "submit_type": "pay",
        "locale": "auto",
        "allow_promotion_codes": False,
    }
    if statement_descriptor_suffix:
        payload["payment_intent_data"]["statement_descriptor_suffix"] = \
            statement_descriptor_suffix[:22]
    # Never both -- Stripe rejects it.
    if stripe_customer_id:
        payload["customer"] = stripe_customer_id
    elif customer_email:
        payload["customer_email"] = customer_email

    sess = _call(s.checkout.Session.create, idempotency_key=f"co:{payment_id}", **payload)
    return {
        "id": sess["id"],
        "url": sess["url"],
        "expires_at": sess.get("expires_at"),
        "payment_intent": sess.get("payment_intent"),
    }


def retrieve_checkout_session(session_id, expand=("payment_intent",)):
    s = _stripe()
    return dict(_call(s.checkout.Session.retrieve, session_id, expand=list(expand)))


def expire_checkout_session(session_id):
    s = _stripe()
    return dict(_call(s.checkout.Session.expire, session_id))


# ---------------------------------------------------------------------------
# payments / refunds
# ---------------------------------------------------------------------------

def retrieve_payment_intent(pi_id, expand=("latest_charge",)):
    s = _stripe()
    return dict(_call(s.PaymentIntent.retrieve, pi_id, expand=list(expand)))


def retrieve_charge(charge_id, expand=("balance_transaction", "refunds")):
    s = _stripe()
    return dict(_call(s.Charge.retrieve, charge_id, expand=list(expand)))


def retrieve_balance_transaction(bt_id):
    s = _stripe()
    return dict(_call(s.BalanceTransaction.retrieve, bt_id))


def create_refund(*, refund_id, payment_intent_id, amount_cents=None, reason=None,
                  metadata=None):
    """amount_cents=None means a full refund. The idempotency key comes from the
    refunds row, which the caller committed before calling -- so a double-click
    or a timeout retry returns the ORIGINAL refund instead of issuing a second."""
    s = _stripe()
    payload = {
        "payment_intent": payment_intent_id,
        "metadata": {"app": "edgebourne", "refund_id": str(refund_id), **(metadata or {})},
    }
    if amount_cents is not None:
        payload["amount"] = int(amount_cents)
    if reason in ("duplicate", "fraudulent", "requested_by_customer"):
        payload["reason"] = reason
    return dict(_call(s.Refund.create, idempotency_key=f"rf:{refund_id}", **payload))


def list_payment_intents_since(ts, limit=100):
    """Reconciliation sweep. If the webhook endpoint was down beyond Stripe's
    ~3-day retry window, this is the only thing that finds the lost payments."""
    s = _stripe()
    res = _call(s.PaymentIntent.list, created={"gte": int(ts)}, limit=limit)
    return [dict(p) for p in res.get("data", [])]


# ---------------------------------------------------------------------------
# webhooks
# ---------------------------------------------------------------------------

def _webhook_secrets():
    for secret in (config.STRIPE_WEBHOOK_SECRET, config.STRIPE_WEBHOOK_SECRET_PREVIOUS):
        if secret:
            yield secret


def construct_event(payload, sig_header):
    """Verify the signature and parse. Accepts the current secret or the previous
    one, so a webhook secret can be rotated with no downtime.

    Hand-written rather than delegated so the tolerance check is explicit: a
    valid-but-old signature is a replay and must be rejected.
    """
    if not any(_webhook_secrets()):
        raise SignatureError("No STRIPE_WEBHOOK_SECRET configured.")
    if not sig_header:
        raise SignatureError("Missing Stripe-Signature header.")

    parts = {}
    signatures = []
    for chunk in sig_header.split(","):
        key, _, value = chunk.strip().partition("=")
        if key == "v1":
            signatures.append(value)
        else:
            parts[key] = value
    timestamp = parts.get("t", "")
    if not timestamp.isdigit() or not signatures:
        raise SignatureError("Malformed Stripe-Signature header.")

    signed = timestamp.encode() + b"." + payload
    for secret in _webhook_secrets():
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(expected, sig) for sig in signatures):
            if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE:
                raise SignatureError("Signature timestamp outside tolerance (replay?).")
            try:
                return json.loads(payload)
            except ValueError as e:
                raise SignatureError(f"Signed payload is not JSON: {e}")
    raise SignatureError("No matching signature.")
