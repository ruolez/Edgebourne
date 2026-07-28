"""Billing domain logic. Routes call into here; they contain no SQL that
touches more than one table.

THREE RULES, in order of importance:

1. ATOMICITY. Every write that touches payments, refunds, credit_ledger,
   invoices.status or subscriptions.next_run_at goes through db.transaction().
   db.query/db.execute commit per statement and are for reads and non-money
   writes only.

2. DERIVE, NEVER ASSIGN. amount_paid and status are recomputed with SUM over
   source rows by refresh_invoice_state(). They are never incremented and never
   taken from a webhook field. This is what makes out-of-order and duplicate
   Stripe deliveries harmless.

3. LOCK ORDER IS customer -> invoice -> payment -> ledger. Always. A Stripe
   webhook and an admin click land on different gunicorn threads, so the locks
   are real; taking them in one order everywhere makes deadlock impossible.

LEDGER SIGN CONVENTION -- positive means the customer owes us MORE, negative
means the customer owes us LESS. balance = SUM(delta_cents); a negative balance
is credit on account.

credit_ledger is APPEND-ONLY. There is no UPDATE or DELETE against it in this
module, deliberately. (Not DB-enforced -- this project has no PL/pgSQL.)
"""

import hashlib
import logging
import secrets
from datetime import date, timedelta

import db
import money

log = logging.getLogger(__name__)

# Line tables share an identical column set, so save/copy/recompute are each
# written once and dispatched through this whitelist -- the same idiom as
# move_row() in admin/services.py. Separate tables (rather than one polymorphic
# table with a doc_type column) because without an ORM nothing remembers the
# discriminator, and a forgotten predicate would silently sum another
# document's lines into this one's total.
LINE_TABLES = {
    "invoice": ("invoice_lines", "invoice_id", "invoices"),
    "estimate": ("estimate_lines", "estimate_id", "estimates"),
    "recurring": ("subscription_lines", "subscription_id", "subscriptions"),
}

LINE_COLS = ("line_id", "line_kind", "line_description", "line_detail",
             "line_qty", "line_unit", "line_price", "line_rate")

INVOICE_OPEN = ("open", "partial")
PROJECT_STATUSES = [
    ("lead", "Lead"), ("active", "Active"), ("on_hold", "On hold"),
    ("completed", "Completed"), ("cancelled", "Cancelled"),
]


class BillingError(ValueError):
    """Domain rule violation. Route handlers flash the message."""


def _lines(doc_type):
    if doc_type not in LINE_TABLES:
        raise ValueError(f"unknown doc_type {doc_type!r}")
    return LINE_TABLES[doc_type]


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

def new_token(prefix):
    """A customer-facing document token. 32 random bytes; the prefix is not
    secret, it just lets one lookup reject a wrong-type token before hitting
    the database."""
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def token_hash(token):
    """Only the hash is stored, so a pg_dump in /var/backups contains no working
    payment links. The trade-off is that the raw token cannot be re-displayed
    after sending -- re-sharing is 'rotate and resend'."""
    return hashlib.sha256((token or "").encode()).digest()


def token_expiry():
    days = int(db.get_setting("billing_token_ttl_days", "90") or 90)
    return date.today() + timedelta(days=days)


# ---------------------------------------------------------------------------
# numbering
# ---------------------------------------------------------------------------

def next_number(scope):
    """Allocate the next document number. One row-locked statement that rolls
    back with the enclosing transaction -- unlike a SEQUENCE, which would leave
    a gap on every failed save. Call inside db.transaction(), at ISSUE time."""
    period = ""
    if db.get_setting("billing_number_period", "year") == "year":
        period = str(date.today().year)
    row = db.execute(
        """INSERT INTO document_counters (scope, period, next_value)
           VALUES (%s, %s, 2)
           ON CONFLICT (scope, period)
           DO UPDATE SET next_value = document_counters.next_value + 1
           RETURNING next_value - 1 AS n""",
        (scope, period),
        returning=True,
    )
    prefix = db.get_setting(
        "billing_invoice_prefix" if scope == "invoice" else "billing_estimate_prefix",
        "INV" if scope == "invoice" else "EST",
    )
    pad = int(db.get_setting("billing_number_pad", "4") or 4)
    body = f"{row['n']:0{pad}d}"
    return f"{prefix}-{period}-{body}" if period else f"{prefix}-{body}"


# ---------------------------------------------------------------------------
# line items
# ---------------------------------------------------------------------------

def read_lines(form):
    """Parse the name-indexed parallel arrays posted by the line_items macro.

    The length check is not paranoia: if the lists ever differ in length, zip
    would silently pair a price with the wrong description and produce a
    plausible-looking wrong invoice."""
    lists = [form.getlist(col) for col in LINE_COLS]
    n = len(lists[0])
    if any(len(lst) != n for lst in lists):
        raise BillingError("The line items were submitted incorrectly — reload and try again.")

    rows = []
    for values in zip(*lists):
        raw = dict(zip(LINE_COLS, values))
        description = (raw["line_description"] or "").strip()
        kind = "heading" if raw["line_kind"] == "heading" else "item"
        # A blank row is how the editor represents "not filled in yet".
        if not description and not (raw["line_price"] or "").strip():
            continue
        if kind == "heading":
            rows.append({"kind": "heading", "description": description, "detail": "",
                         "qty_milli": 0, "unit": "", "unit_price_cents": 0,
                         "tax_rate_milli": 0})
            continue
        rows.append({
            "kind": "item",
            "description": description,
            "detail": (raw["line_detail"] or "").strip(),
            "qty_milli": money.parse_qty(raw["line_qty"], label="Quantity"),
            "unit": (raw["line_unit"] or "").strip()[:40],
            "unit_price_cents": money.parse_money(raw["line_price"], allow_negative=True,
                                                  default=0, label="Price"),
            "tax_rate_milli": money.parse_rate(raw["line_rate"], label="Tax rate"),
        })
    return rows


def save_lines(doc_type, doc_id, rows):
    """Replace a document's lines. Delete-then-insert rather than a diff: line
    ids are not stable across a drag-reorder, and the rows are cheap. Call
    inside db.transaction(); sort_order comes from submitted order."""
    table, fk, _ = _lines(doc_type)
    db.execute(f"DELETE FROM {table} WHERE {fk} = %s", (doc_id,))
    if not rows:
        return
    db.execute_values(
        f"""INSERT INTO {table}
            ({fk}, sort_order, kind, description, detail, qty_milli, unit,
             unit_price_cents, tax_rate_milli) VALUES %s""",
        [
            (doc_id, i, r["kind"], r["description"], r["detail"], r["qty_milli"],
             r["unit"], r["unit_price_cents"], r["tax_rate_milli"])
            for i, r in enumerate(rows)
        ],
    )


def get_lines(doc_type, doc_id):
    table, fk, _ = _lines(doc_type)
    return db.query(f"SELECT * FROM {table} WHERE {fk} = %s ORDER BY sort_order, id", (doc_id,))


def copy_lines(src_type, src_id, dst_type, dst_id):
    """Estimate -> invoice, or duplicating a document. Call inside a transaction."""
    src_table, src_fk, _ = _lines(src_type)
    dst_table, dst_fk, _ = _lines(dst_type)
    db.execute(
        f"""INSERT INTO {dst_table}
            ({dst_fk}, sort_order, kind, description, detail, qty_milli, unit,
             unit_price_cents, tax_rate_milli)
            SELECT %s, sort_order, kind, description, detail, qty_milli, unit,
                   unit_price_cents, tax_rate_milli
              FROM {src_table} WHERE {src_fk} = %s ORDER BY sort_order, id""",
        (dst_id, src_id),
    )


# ---------------------------------------------------------------------------
# totals
# ---------------------------------------------------------------------------

def recompute_totals(doc_type, doc_id, discount_cents=None):
    """Recompute subtotal/discount/tax/total from the current line rows, in one
    statement. No Python arithmetic touches money here.

    Two deliberate properties:

    * Tax is computed per RATE GROUP, not per line. Ten lines of $0.05 at 8.875%
      round to $0.00 each individually but $0.04 as a group; grouping is how
      accounting systems and tax authorities compute it.
    * A document-level discount is allocated pro-rata across rate groups BEFORE
      tax, which is the tax-correct treatment on a mixed-rate document, and is
      clamped to [0, subtotal] so a typo cannot make the total negative.

    Pass discount_cents=None to keep the stored discount (after a line delete);
    pass a value to set it (from the form).

    Must be called inside db.transaction() by every path that mutates lines.
    """
    table, fk, parent = _lines(doc_type)
    sql = f"""
        WITH grp AS (
            SELECT tax_rate_milli, COALESCE(SUM(amount_cents), 0)::bigint AS base
              FROM {table} WHERE {fk} = %(id)s AND kind = 'item'
             GROUP BY tax_rate_milli
        ), sub AS (
            SELECT COALESCE(SUM(base), 0)::bigint AS subtotal FROM grp
        ), disc AS (
            SELECT LEAST(
                     GREATEST(COALESCE(%(discount)s, p.discount_cents), 0),
                     GREATEST(s.subtotal, 0)
                   )::bigint AS discount
              FROM sub s, {parent} p WHERE p.id = %(id)s
        ), tax AS (
            SELECT COALESCE(SUM(
                     round(
                       (g.base - CASE WHEN s.subtotal = 0 THEN 0
                                      ELSE d.discount::numeric * g.base / s.subtotal END)
                       * g.tax_rate_milli / 100000
                     )
                   ), 0)::bigint AS tax
              FROM grp g, sub s, disc d
        )
        UPDATE {parent} p
           SET subtotal_cents = s.subtotal,
               discount_cents = d.discount,
               tax_cents      = t.tax,
               total_cents    = s.subtotal - d.discount + t.tax,
               updated_at     = now()
          FROM sub s, disc d, tax t
         WHERE p.id = %(id)s
        RETURNING p.*
    """
    doc = db.execute(sql, {"id": doc_id, "discount": discount_cents}, returning=True)
    if doc and doc["subtotal_cents"] - doc["discount_cents"] + doc["tax_cents"] != doc["total_cents"]:
        raise BillingError("Total does not reconcile with its parts — refusing to save.")
    return doc


# ---------------------------------------------------------------------------
# invoice state
# ---------------------------------------------------------------------------

def refresh_invoice_state(invoice_id):
    """Recompute amount_paid and status FROM SOURCE ROWS.

    Owns amount_paid_cents, status and paid_at. Never touches totals -- a
    payment must not re-derive line totals, or a settings change would silently
    re-tax an already-issued invoice.

    Never increments, and never reads a status out of a webhook payload. That
    is what makes duplicate and out-of-order Stripe deliveries converge on the
    same answer regardless of arrival order.

    Refunds are stored as their own rows and subtracted here, so a full refund
    automatically walks an invoice back paid -> partial -> open with no extra
    code path.
    """
    return db.execute(
        """
        WITH paid AS (
            SELECT COALESCE((SELECT SUM(amount_cents) FROM payments
                              WHERE invoice_id = %(id)s AND status = 'succeeded'), 0)
                 - COALESCE((SELECT SUM(r.amount_cents) FROM refunds r
                              WHERE r.invoice_id = %(id)s AND r.status = 'succeeded'), 0)
                   AS amt
        )
        UPDATE invoices i
           SET amount_paid_cents = GREATEST(paid.amt, 0),
               status = CASE
                   -- A payment must never resurrect a draft or a voided invoice.
                   WHEN i.status IN ('draft', 'void', 'uncollectible') THEN i.status
                   WHEN i.status = 'disputed'                          THEN i.status
                   WHEN i.total_cents <= 0                             THEN 'paid'
                   WHEN paid.amt >= i.total_cents                      THEN 'paid'
                   WHEN paid.amt > 0                                   THEN 'partial'
                   ELSE 'open' END,
               paid_at = CASE
                   WHEN i.status NOT IN ('draft', 'void')
                    AND (i.total_cents <= 0 OR paid.amt >= i.total_cents)
                   THEN COALESCE(i.paid_at, now()) END,
               updated_at = now()
          FROM paid
         WHERE i.id = %(id)s
        RETURNING i.*
        """,
        {"id": invoice_id},
        returning=True,
    )


def issue_invoice(invoice_id, user_id=None):
    """draft -> open. Allocates the number, mints the customer token, and posts
    the charge to the ledger. One transaction: a number without a ledger entry,
    or the reverse, is unrecoverable."""
    with db.transaction():
        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,), one=True)
        if not inv:
            raise BillingError("Invoice not found.")
        if inv["status"] != "draft":
            raise BillingError("This invoice has already been issued.")
        if inv["total_cents"] <= 0:
            raise BillingError("Add at least one line item before issuing.")

        number = next_number("invoice")
        token = new_token("inv")
        db.execute(
            """UPDATE invoices
                  SET number = %s, status = 'open', issued_at = now(),
                      token_hash = %s, token_expires_at = %s, updated_at = now()
                WHERE id = %s""",
            (number, token_hash(token), token_expiry(), invoice_id),
        )
        add_ledger(inv["customer_id"], "invoice", inv["total_cents"], inv["currency"],
                   invoice_id=invoice_id, memo=f"Invoice {number}", user_id=user_id)
        refresh_invoice_state(invoice_id)
    # Returned once and never again -- only the hash is stored.
    return number, token


def void_invoice(invoice_id, user_id=None):
    """Reverses the ledger charge. Blocked while any succeeded payment exists so
    the 'invoice_void' entry stays a clean -total; refund first."""
    with db.transaction():
        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,), one=True)
        if not inv:
            raise BillingError("Invoice not found.")
        if inv["status"] == "void":
            raise BillingError("This invoice is already void.")
        if inv["status"] == "draft":
            raise BillingError("Drafts are deleted, not voided.")
        paid = db.query(
            """SELECT COALESCE(SUM(amount_cents), 0)::bigint AS amt FROM payments
                WHERE invoice_id = %s AND status = 'succeeded'""",
            (invoice_id,),
            one=True,
        )["amt"]
        if paid > 0:
            raise BillingError("This invoice has payments against it — refund them first.")
        db.execute(
            "UPDATE invoices SET status='void', voided_at=now(), updated_at=now() WHERE id=%s",
            (invoice_id,),
        )
        add_ledger(inv["customer_id"], "invoice_void", -inv["total_cents"], inv["currency"],
                   invoice_id=invoice_id,
                   memo=f"Voided {inv['number'] or '#' + str(invoice_id)}", user_id=user_id)


def rotate_token(doc_type, doc_id):
    """Mint a new customer link. The old hash is kept for a 24h grace window so
    a customer mid-checkout is not broken."""
    table = "invoices" if doc_type == "invoice" else "estimates"
    prefix = "inv" if doc_type == "invoice" else "est"
    token = new_token(prefix)
    db.execute(
        f"""UPDATE {table}
               SET previous_token_hash = token_hash, token_hash = %s,
                   token_expires_at = %s, token_rotated_at = now(), updated_at = now()
             WHERE id = %s""",
        (token_hash(token), token_expiry(), doc_id),
    )
    return token


# ---------------------------------------------------------------------------
# estimates
#
# An ACCEPTED estimate is the work order -- there is no separate orders table.
# /admin/estimates?status=accepted is the "Work orders" view.
# ---------------------------------------------------------------------------

def issue_estimate(estimate_id, user_id=None):
    """draft -> sent. Allocates the number and mints the customer link.

    Unlike an invoice this posts NOTHING to the ledger: an estimate is an offer,
    not a receivable. The charge appears only when an invoice is issued from it.
    """
    with db.transaction():
        est = db.query("SELECT * FROM estimates WHERE id = %s FOR UPDATE", (estimate_id,), one=True)
        if not est:
            raise BillingError("Estimate not found.")
        if est["status"] != "draft":
            raise BillingError("This estimate has already been sent.")
        if est["total_cents"] <= 0:
            raise BillingError("Add at least one line item before sending.")

        number = est["number"] or next_number("estimate")
        token = new_token("est")
        valid_days = int(db.get_setting("billing_estimate_valid_days", "30") or 30)
        db.execute(
            """UPDATE estimates
                  SET number = %s, status = 'sent', sent_at = now(),
                      valid_until = COALESCE(valid_until, current_date + %s),
                      token_hash = %s, token_expires_at = %s, updated_at = now()
                WHERE id = %s""",
            (number, timedelta(days=valid_days), token_hash(token), token_expiry(), estimate_id),
        )
    return number, token


def set_estimate_status(estimate_id, status, user_id=None):
    """Admin-side status override, for an estimate accepted over the phone or
    one that should be marked declined."""
    if status not in ("draft", "sent", "accepted", "declined", "expired"):
        raise BillingError("Unknown estimate status.")
    est = db.query("SELECT * FROM estimates WHERE id = %s", (estimate_id,), one=True)
    if not est:
        raise BillingError("Estimate not found.")
    if status != "draft" and not est["number"]:
        raise BillingError("Send the estimate first so it gets a number.")
    db.execute(
        """UPDATE estimates
              SET status = %s,
                  accepted_at = CASE WHEN %s = 'accepted' THEN COALESCE(accepted_at, now()) END,
                  accepted_name = CASE WHEN %s = 'accepted'
                                       THEN COALESCE(accepted_name, 'Recorded by staff') END,
                  declined_at = CASE WHEN %s = 'declined' THEN COALESCE(declined_at, now()) END,
                  updated_at = now()
            WHERE id = %s""",
        (status, status, status, status, estimate_id),
    )


def estimate_invoiced_cents(estimate_id):
    """How much of an accepted estimate has already been billed. Voided invoices
    do not count -- they were reversed on the ledger."""
    row = db.query(
        """SELECT COALESCE(SUM(total_cents), 0)::bigint AS amt FROM invoices
            WHERE estimate_id = %s AND status <> 'void'""",
        (estimate_id,),
        one=True,
    )
    return row["amt"] if row else 0


def convert_estimate_to_invoice(estimate_id, user_id=None):
    """Create a DRAFT invoice carrying the estimate's lines.

    Draft, not issued, deliberately: the admin should see the dates and terms
    before a number is burned and a charge hits the customer's ledger. Partial
    invoicing of a large estimate works by editing the draft's lines down.
    """
    with db.transaction():
        est = db.query("SELECT * FROM estimates WHERE id = %s FOR UPDATE", (estimate_id,), one=True)
        if not est:
            raise BillingError("Estimate not found.")
        if est["status"] not in ("accepted", "sent"):
            raise BillingError("Only a sent or accepted estimate can be converted.")

        customer = db.query("SELECT * FROM customers WHERE id = %s",
                            (est["customer_id"],), one=True)
        terms = customer["terms_days"] if customer else 14
        inv = db.execute(
            """INSERT INTO invoices (customer_id, project_id, estimate_id, currency, title,
                   issue_date, due_date, notes_md, terms_md, discount_cents, created_by)
               VALUES (%s,%s,%s,%s,%s, current_date, current_date + %s, %s,%s,%s,%s)
               RETURNING *""",
            (est["customer_id"], est["project_id"], est["id"], est["currency"],
             est["title"], timedelta(days=terms), est["notes_md"], est["terms_md"],
             est["discount_cents"], user_id),
            returning=True,
        )
        copy_lines("estimate", estimate_id, "invoice", inv["id"])
        recompute_totals("invoice", inv["id"], est["discount_cents"])
    return inv["id"]


def expire_estimates():
    """Sent estimates past their valid_until become 'expired'. Run by the
    scheduler; also safe to call from a request."""
    return db.execute(
        """UPDATE estimates SET status = 'expired', updated_at = now()
            WHERE status = 'sent' AND valid_until IS NOT NULL
              AND valid_until < current_date""",
    )


# ---------------------------------------------------------------------------
# payments
# ---------------------------------------------------------------------------

def record_payment(invoice_id, amount_cents, *, method="bank_transfer", received_on=None,
                   reference="", memo="", user_id=None, customer_id=None,
                   status="succeeded", stripe=None):
    """Record money received.

    An amount larger than the invoice balance is SPLIT into two payment rows --
    one applied to the invoice, one on-account (invoice_id NULL) -- so that
        amount_paid_cents == SUM(payments WHERE invoice_id = X)
    remains a true invariant rather than a special case. The on-account row
    makes the ledger balance negative, i.e. it becomes credit that
    apply_credit() can consume later.

    Never auto-refund an overpayment; the caller alerts the admin instead.
    """
    if amount_cents <= 0:
        raise BillingError("Payment amount must be greater than zero.")
    stripe = stripe or {}

    with db.transaction():
        if invoice_id:
            inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,), one=True)
            if not inv:
                raise BillingError("Invoice not found.")
            if inv["status"] == "draft":
                raise BillingError("Issue the invoice before recording a payment against it.")
            customer_id = inv["customer_id"]
            currency = inv["currency"]
            balance = max(inv["balance_due_cents"], 0)
        else:
            if not customer_id:
                raise BillingError("A payment needs an invoice or a customer.")
            cust = db.query("SELECT * FROM customers WHERE id = %s FOR UPDATE", (customer_id,), one=True)
            if not cust:
                raise BillingError("Customer not found.")
            currency, balance, inv = cust["currency"], 0, None

        applied = min(amount_cents, balance) if invoice_id else 0
        overpay = amount_cents - applied
        created = []

        def _insert(target_invoice, amount, note):
            row = db.execute(
                """INSERT INTO payments
                     (customer_id, invoice_id, method, amount_cents, currency, status,
                      received_on, reference, memo, created_by, livemode,
                      stripe_checkout_session_id, stripe_payment_intent_id,
                      stripe_charge_id, receipt_token, receipt_token_expires_at,
                      invoice_version)
                   VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s, current_date),%s,%s,%s,%s,
                           %s,%s,%s,%s,%s,%s)
                   RETURNING *""",
                (customer_id, target_invoice, method, amount, currency, status,
                 received_on, reference, note, user_id,
                 bool(stripe.get("livemode")), stripe.get("checkout_session_id"),
                 stripe.get("payment_intent_id"), stripe.get("charge_id"),
                 stripe.get("receipt_token"), stripe.get("receipt_token_expires_at"),
                 inv["version"] if inv else None),
                returning=True,
            )
            created.append(row)
            if status == "succeeded":
                add_ledger(customer_id, "payment", -amount, currency,
                           invoice_id=target_invoice, payment_id=row["id"],
                           memo=note or "Payment received", user_id=user_id)
            return row

        if applied > 0:
            _insert(invoice_id, applied, memo or "Payment received")
        if overpay > 0:
            _insert(None, overpay,
                    "Payment on account" if not invoice_id else "Overpayment — held on account")

        if invoice_id:
            refresh_invoice_state(invoice_id)

    return {"payments": created, "applied_cents": applied, "overpaid_cents": overpay}


def void_payment(payment_id, user_id=None):
    """A cheque bounced, or the payment was recorded in error. The row is kept
    and marked canceled -- never deleted -- and the ledger gets a compensating
    entry, because the ledger is append-only."""
    with db.transaction():
        pay = db.query("SELECT * FROM payments WHERE id = %s FOR UPDATE", (payment_id,), one=True)
        if not pay:
            raise BillingError("Payment not found.")
        if pay["status"] != "succeeded":
            raise BillingError("Only a succeeded payment can be voided.")
        if pay["method"] == "card":
            raise BillingError("Card payments must be refunded through Stripe, not voided.")
        if pay["method"] == "credit":
            # A credit-funded payment is half of a net-zero ledger pair
            # (credit_apply +X / payment -X). Voiding only the payment half would
            # orphan the credit_apply entry: the customer would lose the credit
            # AND owe the invoice again. Unapplying credit is a separate
            # operation that must reverse both entries; it is not built yet.
            raise BillingError(
                "Applied credit cannot be voided. Record a refund or grant fresh credit instead."
            )
        db.execute(
            "UPDATE payments SET status='canceled', updated_at=now() WHERE id=%s", (payment_id,)
        )
        add_ledger(pay["customer_id"], "payment_void", pay["amount_cents"], pay["currency"],
                   invoice_id=pay["invoice_id"], payment_id=payment_id,
                   memo="Payment voided", user_id=user_id)
        if pay["invoice_id"]:
            refresh_invoice_state(pay["invoice_id"])


def refundable_cents(payment_id):
    row = db.query(
        """SELECT p.amount_cents
                 - COALESCE((SELECT SUM(r.amount_cents) FROM refunds r
                              WHERE r.payment_id = p.id
                                AND r.status IN ('succeeded','pending')), 0) AS amt
             FROM payments p WHERE p.id = %s AND p.status = 'succeeded'""",
        (payment_id,),
        one=True,
    )
    return max(row["amt"], 0) if row else 0


def start_refund(payment_id, amount_cents=None, reason="", user_id=None):
    """Create the refunds row and COMMIT it before any network call.

    That ordering is what makes the idempotency key rf:{refund_id} stable: a
    double-click or a timeout-and-retry returns Stripe's original refund instead
    of issuing a second one. Returns the row; the caller then talks to Stripe.
    """
    with db.transaction():
        pay = db.query("SELECT * FROM payments WHERE id = %s FOR UPDATE", (payment_id,), one=True)
        if not pay:
            raise BillingError("Payment not found.")
        if pay["status"] != "succeeded":
            raise BillingError("Only a succeeded payment can be refunded.")
        if pay["method"] == "credit":
            raise BillingError("Applied credit cannot be refunded — grant credit back instead.")
        available = refundable_cents(payment_id)
        amount = amount_cents if amount_cents is not None else available
        if amount <= 0 or amount > available:
            raise BillingError(
                f"Refund must be between 0 and {money.format_money(available, pay['currency'])}.")
        return db.execute(
            """INSERT INTO refunds (payment_id, invoice_id, customer_id, amount_cents,
                   currency, status, reason, initiated_by, created_by)
               VALUES (%s,%s,%s,%s,%s,'pending',%s,'admin',%s) RETURNING *""",
            (payment_id, pay["invoice_id"], pay["customer_id"], amount, pay["currency"],
             reason[:500], user_id),
            returning=True,
        )


def settle_refund(refund_id, *, status, stripe_refund_id=None, error=None, user_id=None):
    """Record the outcome. The ledger effect is recomputed as a SUM over
    succeeded refunds, never incremented, so a webhook arriving with the same
    news cannot double-count it."""
    with db.transaction():
        ref = db.query("SELECT * FROM refunds WHERE id = %s FOR UPDATE", (refund_id,), one=True)
        if not ref:
            raise BillingError("Refund not found.")
        db.execute(
            """UPDATE refunds SET status=%s, stripe_refund_id=COALESCE(%s, stripe_refund_id),
                   error=%s, completed_at=now(), updated_at=now()
                 WHERE id=%s""",
            (status, stripe_refund_id, (error or None), refund_id),
        )
        _resync_refunds(ref["payment_id"], ref["customer_id"], ref["currency"],
                        ref["invoice_id"], user_id)
        if ref["invoice_id"]:
            refresh_invoice_state(ref["invoice_id"])


def _resync_refunds(payment_id, customer_id, currency, invoice_id, user_id=None):
    """Keep the ledger's refund total equal to SUM(succeeded refunds) for this
    payment. Posts only the delta, so it is safe to call repeatedly."""
    total = db.query(
        """SELECT COALESCE(SUM(amount_cents), 0)::bigint AS amt FROM refunds
            WHERE payment_id = %s AND status = 'succeeded'""",
        (payment_id,), one=True)["amt"]
    posted = db.query(
        """SELECT COALESCE(SUM(delta_cents), 0)::bigint AS amt FROM credit_ledger
            WHERE payment_id = %s AND kind = 'refund'""",
        (payment_id,), one=True)["amt"]
    delta = total - posted
    if delta:
        add_ledger(customer_id, "refund", delta, currency, invoice_id=invoice_id,
                   payment_id=payment_id, memo="Refund issued", user_id=user_id)


def record_manual_refund(payment_id, amount_cents, reason="", user_id=None):
    """Money sent back outside Stripe (a cheque, a bank transfer)."""
    ref = start_refund(payment_id, amount_cents, reason, user_id)
    settle_refund(ref["id"], status="succeeded", user_id=user_id)
    return ref


def credit_note(invoice_id, amount_cents, memo="", user_id=None):
    """Reduce what a customer owes without moving money — the honest answer to
    "we refunded because we're not doing the work", which should leave the
    invoice settled rather than reopening its balance."""
    with db.transaction():
        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,), one=True)
        if not inv:
            raise BillingError("Invoice not found.")
        if inv["status"] in ("draft", "void"):
            raise BillingError("A credit note only applies to an issued invoice.")
        if amount_cents <= 0:
            raise BillingError("Credit note amount must be greater than zero.")
        add_ledger(inv["customer_id"], "credit_grant", -amount_cents, inv["currency"],
                   invoice_id=invoice_id,
                   memo=memo or f"Credit note against {inv['number'] or invoice_id}",
                   user_id=user_id)
    return apply_credit(inv["customer_id"], invoice_id, amount_cents, user_id=user_id)


def apply_credit(customer_id, invoice_id, amount_cents=None, user_id=None):
    """Consume on-account credit against an open invoice.

    The subtle part: the money was already counted when the overpayment or
    deposit landed, so applying it must NOT change the customer balance -- but it
    MUST raise the invoice's amount_paid. So it writes a PAIR of ledger entries
    that net to zero, plus a payments row with method='credit'.

    Two entries rather than one zero-amount entry, so the ledger reads as a
    journal an accountant can follow, and SUM(...) FILTER (WHERE kind='payment')
    stays a true "total paid".
    """
    with db.transaction():
        # Lock order is customer -> invoice, always. You cannot FOR UPDATE an
        # aggregate, so the customer row is the serialization token for the
        # ledger sum.
        cust = db.query("SELECT * FROM customers WHERE id = %s FOR UPDATE", (customer_id,), one=True)
        if not cust:
            raise BillingError("Customer not found.")
        credit = db.query(
            f"SELECT GREATEST({CREDIT_SQL}, 0)::bigint AS c", {"cid": customer_id}, one=True
        )["c"]

        inv = db.query("SELECT * FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,), one=True)
        if not inv or inv["customer_id"] != customer_id:
            raise BillingError("That invoice does not belong to this customer.")
        if inv["status"] not in INVOICE_OPEN:
            raise BillingError("Credit can only be applied to an open invoice.")

        amount = min(credit, max(inv["balance_due_cents"], 0), amount_cents or credit)
        if amount <= 0:
            raise BillingError("There is no credit available to apply.")

        pay = db.execute(
            """INSERT INTO payments (customer_id, invoice_id, method, amount_cents,
                   currency, status, memo, created_by)
               VALUES (%s,%s,'credit',%s,%s,'succeeded',%s,%s) RETURNING *""",
            (customer_id, invoice_id, amount, inv["currency"],
             f"Credit applied to {inv['number'] or '#' + str(invoice_id)}", user_id),
            returning=True,
        )
        add_ledger(customer_id, "credit_apply", amount, inv["currency"],
                   invoice_id=invoice_id, memo="Credit consumed", user_id=user_id)
        add_ledger(customer_id, "payment", -amount, inv["currency"],
                   invoice_id=invoice_id, payment_id=pay["id"],
                   memo="Paid from credit", user_id=user_id)
        refresh_invoice_state(invoice_id)
    return amount


def audit_consistency():
    """Cross-check the ledger against the invoice and payment tables.

    The ledger is derived by the code in this module, so summing it and
    comparing to itself proves nothing. Instead rebuild the balance from the
    OTHER tables and require the two to agree:

        expected = issued invoice totals (excluding draft and void)
                 - succeeded payments
                 + succeeded refunds
                 + credit grants        (stored negative, so this subtracts)
                 + credit applied       (== succeeded payments with method='credit')

    Voided payments need no term: they are excluded from "succeeded", and their
    ledger pair (-amount then +amount) nets to zero.

    Worked example -- invoice $10.00, $2.50 credit granted then applied:
        expected = 1000 - 250 + 0 - 250 + 250 = 750
        ledger   = +1000 (invoice) -250 (grant) +250 (apply) -250 (payment) = 750
    """
    return db.query(
        """
        SELECT c.id, c.display_name, c.currency,
               (SELECT COALESCE(SUM(l.delta_cents), 0) FROM credit_ledger l
                 WHERE l.customer_id = c.id)                                   AS ledger_balance,
               (
                   (SELECT COALESCE(SUM(i.total_cents), 0) FROM invoices i
                     WHERE i.customer_id = c.id AND i.status NOT IN ('draft','void'))
                 - (SELECT COALESCE(SUM(p.amount_cents), 0) FROM payments p
                     WHERE p.customer_id = c.id AND p.status = 'succeeded')
                 + (SELECT COALESCE(SUM(r.amount_cents), 0) FROM refunds r
                     WHERE r.customer_id = c.id AND r.status = 'succeeded')
                 + (SELECT COALESCE(SUM(l.delta_cents), 0) FROM credit_ledger l
                     WHERE l.customer_id = c.id AND l.kind = 'credit_grant')
                 + (SELECT COALESCE(SUM(p.amount_cents), 0) FROM payments p
                     WHERE p.customer_id = c.id AND p.status = 'succeeded'
                       AND p.method = 'credit')
               )                                                               AS expected_balance,
               (SELECT COALESCE(SUM(i.balance_due_cents), 0) FROM invoices i
                 WHERE i.customer_id = c.id AND i.status IN ('open','partial')) AS open_balance,
               (SELECT COUNT(DISTINCT i.currency) FROM invoices i
                 WHERE i.customer_id = c.id)                                   AS currencies,
               (SELECT COUNT(*) FROM payments p
                 WHERE p.customer_id = c.id AND p.needs_review)                AS needs_review
          FROM customers c
         ORDER BY c.display_name
        """
    )


# ---------------------------------------------------------------------------
# customer balance
# ---------------------------------------------------------------------------

CREDIT_SQL = """
    COALESCE((SELECT SUM(p.amount_cents) FROM payments p
               WHERE p.customer_id = %(cid)s AND p.invoice_id IS NULL
                 AND p.status = 'succeeded'), 0)
  - COALESCE((SELECT SUM(l.delta_cents) FROM credit_ledger l
               WHERE l.customer_id = %(cid)s AND l.kind = 'credit_grant'), 0)
  - COALESCE((SELECT SUM(l.delta_cents) FROM credit_ledger l
               WHERE l.customer_id = %(cid)s AND l.kind = 'credit_apply'), 0)
  - COALESCE((SELECT SUM(r.amount_cents) FROM refunds r
                JOIN payments p ON p.id = r.payment_id
               WHERE r.customer_id = %(cid)s AND r.status = 'succeeded'
                 AND p.invoice_id IS NULL), 0)
"""


def customer_balance(customer_id):
    """Overall balance, and credit sitting unallocated on the account.

    Credit is UNAPPLIED MONEY, not "a negative balance". Those differ the moment
    a new invoice is issued: a customer holding $309.22 on account who is then
    invoiced $500 has an overall balance of +$190.78, but still has $309.22 that
    should be applicable to that invoice. Deriving credit from the sign of the
    balance would report zero and make the money unusable.

        credit = on-account payments + credits granted
                 - credit already applied - refunds of on-account money

    (credit_grant deltas are stored negative and credit_apply positive, hence
    both are subtracted.)

    Neither figure is ever a stored column -- caching a pure function of an
    append-only table can only introduce drift.
    """
    row = db.query(
        f"""SELECT COALESCE((SELECT SUM(delta_cents) FROM credit_ledger
                              WHERE customer_id = %(cid)s), 0)::bigint AS balance_cents,
                   GREATEST({CREDIT_SQL}, 0)::bigint AS credit_cents""",
        {"cid": customer_id},
        one=True,
    )
    return row or {"balance_cents": 0, "credit_cents": 0}


def ledger_entries(customer_id, limit=200):
    return db.query(
        """SELECT l.*, i.number AS invoice_number
             FROM credit_ledger l
             LEFT JOIN invoices i ON i.id = l.invoice_id
            WHERE l.customer_id = %s
            ORDER BY l.occurred_on DESC, l.id DESC
            LIMIT %s""",
        (customer_id, limit),
    )


def add_ledger(customer_id, kind, delta_cents, currency, *, invoice_id=None,
               payment_id=None, refund_id=None, memo="", user_id=None):
    """Append one ledger entry. Sign convention is at the top of this module:
    positive = the customer owes us more. Call inside db.transaction()."""
    return db.execute(
        """INSERT INTO credit_ledger
             (customer_id, kind, delta_cents, currency, invoice_id, payment_id,
              refund_id, memo, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (customer_id, kind, delta_cents, currency, invoice_id, payment_id,
         refund_id, memo, user_id),
        returning=True,
    )


def grant_credit(customer_id, amount_cents, memo="", user_id=None):
    """Goodwill credit or a retainer deposit. Negative delta: the customer owes
    us less. Consumed later by apply_credit()."""
    if amount_cents <= 0:
        raise BillingError("Credit amount must be greater than zero.")
    cust = db.query("SELECT currency FROM customers WHERE id = %s", (customer_id,), one=True)
    if not cust:
        raise BillingError("Customer not found.")
    with db.transaction():
        add_ledger(customer_id, "credit_grant", -amount_cents, cust["currency"],
                   memo=memo or "Credit granted", user_id=user_id)


def audit(user_id, username, ip, action, entity="", entity_id=None, detail=None):
    """Best-effort audit trail for money mutations. Never let a logging failure
    roll back a payment."""
    import json
    try:
        db.execute(
            """INSERT INTO billing_audit (user_id, username, ip, action, entity, entity_id, detail)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (user_id, username or "", ip or "", action, entity, entity_id,
             json.dumps(detail) if detail is not None else None),
        )
    except Exception:
        log.exception("billing_audit write failed for %s", action)


# ---------------------------------------------------------------------------
# shared form helpers
# ---------------------------------------------------------------------------

def customer_options(include_archived=False):
    where = "" if include_archived else "WHERE NOT is_archived"
    rows = db.query(f"SELECT id, display_name FROM customers {where} ORDER BY display_name")
    return [(r["id"], r["display_name"]) for r in rows]


def project_options(customer_id=None):
    if customer_id:
        rows = db.query(
            """SELECT id, name FROM projects WHERE customer_id = %s
                ORDER BY status, name""",
            (customer_id,),
        )
    else:
        rows = db.query(
            """SELECT p.id, p.name, c.display_name FROM projects p
                 JOIN customers c ON c.id = p.customer_id
                ORDER BY c.display_name, p.name"""
        )
        return [(r["id"], f"{r['display_name']} — {r['name']}") for r in rows]
    return [(r["id"], r["name"]) for r in rows]


def parse_date(raw):
    """<input type=date> gives ISO or empty."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise BillingError("Dates must be valid.")
