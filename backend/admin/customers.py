"""Customers: list, form, and the detail hub.

Departs from the services.py one-form convention on purpose: a customer is a hub
record with children (projects, invoices, estimates, ledger), so /customers/<id>
is a detail view and /customers/<id>/edit is the form. admin/leads.py already
establishes the detail-view precedent.
"""

import psycopg2
from flask import abort, flash, redirect, render_template, request, session, url_for

import billing
import content
import db
import money

from . import bp

FIELDS = [
    "display_name", "company", "contact_name", "email", "cc_emails", "phone",
    "website", "address_line1", "address_line2", "address_city", "address_region",
    "address_postcode", "address_country", "tax_number",
]


@bp.get("/customers")
def customers_list():
    show = request.args.get("show", "active")
    q = (request.args.get("q") or "").strip()
    where = ["TRUE" if show == "all" else ("c.is_archived" if show == "archived" else "NOT c.is_archived")]
    params = []
    if q:
        where.append("(c.display_name ILIKE %s OR c.company ILIKE %s OR c.email ILIKE %s)")
        params += [f"%{q}%"] * 3
    rows = db.query(
        f"""SELECT c.*,
                   (SELECT COALESCE(SUM(l.delta_cents), 0) FROM credit_ledger l
                     WHERE l.customer_id = c.id) AS balance_cents,
                   (SELECT COUNT(*) FROM invoices i
                     WHERE i.customer_id = c.id AND i.status IN ('open','partial')) AS open_invoices,
                   (SELECT COUNT(*) FROM invoices i
                     WHERE i.customer_id = c.id AND i.status IN ('open','partial')
                       AND i.due_date < current_date) AS overdue_invoices
              FROM customers c
             WHERE {' AND '.join(where)}
             ORDER BY c.display_name""",
        tuple(params),
    )
    return render_template("admin/customers.html", rows=rows, show=show, q=q)


@bp.get("/customers/<int:cid>")
def customer_detail(cid):
    row = db.query("SELECT * FROM customers WHERE id = %s", (cid,), one=True)
    if not row:
        abort(404)
    tab = request.args.get("tab", "invoices")
    return render_template(
        "admin/customer_detail.html",
        c=row,
        tab=tab,
        bal=billing.customer_balance(cid),
        invoices=db.query(
            """SELECT *, (status IN ('open','partial') AND due_date < current_date) AS is_overdue
                 FROM invoices WHERE customer_id = %s ORDER BY id DESC LIMIT 100""",
            (cid,),
        ),
        estimates=db.query(
            "SELECT * FROM estimates WHERE customer_id = %s ORDER BY id DESC LIMIT 100", (cid,)
        ),
        projects=db.query(
            "SELECT * FROM projects WHERE customer_id = %s ORDER BY status, name", (cid,)
        ),
        payments=db.query(
            """SELECT p.*, i.number AS invoice_number FROM payments p
                 LEFT JOIN invoices i ON i.id = p.invoice_id
                WHERE p.customer_id = %s ORDER BY p.received_on DESC, p.id DESC LIMIT 100""",
            (cid,),
        ),
        ledger=billing.ledger_entries(cid),
    )


@bp.get("/customers/new")
@bp.get("/customers/<int:cid>/edit")
def customer_form(cid=None):
    row = None
    if cid:
        row = db.query("SELECT * FROM customers WHERE id = %s", (cid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/customer_form.html", row=row)


@bp.post("/customers/new")
@bp.post("/customers/<int:cid>/edit")
def customer_save(cid=None):
    f = request.form
    values = {k: (f.get(k) or "").strip() for k in FIELDS}
    if not values["display_name"]:
        flash("A name is required.", "error")
        return redirect(request.path)

    try:
        currency = money.check_supported(f.get("currency") or money.default_currency())
        tax_rate = money.parse_rate(f.get("default_tax_rate_milli"), default=0)
    except money.MoneyError as e:
        flash(str(e), "error")
        return redirect(request.path)

    try:
        terms_days = max(0, min(365, int(f.get("terms_days") or 14)))
    except ValueError:
        flash("Payment terms must be a whole number of days.", "error")
        return redirect(request.path)

    notes_md = f.get("notes_md") or ""
    params = tuple(values[k] for k in FIELDS) + (
        currency, terms_days, tax_rate, notes_md, content.render_md(notes_md),
        bool(f.get("is_archived")),
    )
    cols = ", ".join(FIELDS) + ", currency, terms_days, default_tax_rate_milli, notes_md, notes_html, is_archived"

    if cid:
        # Currency is deliberately not editable once set (see the ledger note in
        # 004_billing.sql); the form renders it read-only after creation, and
        # this SET list simply omits it.
        sets = ", ".join(f"{k} = %s" for k in FIELDS)
        db.execute(
            f"""UPDATE customers SET {sets}, terms_days = %s, default_tax_rate_milli = %s,
                   notes_md = %s, notes_html = %s, is_archived = %s, updated_at = now()
                 WHERE id = %s""",
            tuple(values[k] for k in FIELDS)
            + (terms_days, tax_rate, notes_md, content.render_md(notes_md),
               bool(f.get("is_archived")), cid),
        )
    else:
        placeholders = ", ".join(["%s"] * (len(FIELDS) + 6))
        row = db.execute(
            f"INSERT INTO customers ({cols}) VALUES ({placeholders}) RETURNING id",
            params,
            returning=True,
        )
        cid = row["id"]

    flash("Customer saved.", "success")
    return redirect(url_for("admin.customer_detail", cid=cid))


@bp.post("/customers/<int:cid>/archive")
def customer_archive(cid):
    row = db.execute(
        "UPDATE customers SET is_archived = NOT is_archived, updated_at = now() WHERE id = %s RETURNING is_archived",
        (cid,),
        returning=True,
    )
    if not row:
        abort(404)
    flash("Customer archived." if row["is_archived"] else "Customer restored.", "success")
    return redirect(url_for("admin.customer_detail", cid=cid))


@bp.post("/customers/<int:cid>/delete")
def customer_delete(cid):
    try:
        db.execute("DELETE FROM customers WHERE id = %s", (cid,))
    except psycopg2.errors.ForeignKeyViolation:
        # The RESTRICT foreign keys earning their keep: a customer with any
        # financial history must never be deletable.
        db.rollback()
        flash("This customer has projects or financial records — archive them instead.", "error")
        return redirect(url_for("admin.customer_detail", cid=cid))
    flash("Customer deleted.", "success")
    return redirect(url_for("admin.customers_list"))


@bp.post("/customers/<int:cid>/credit")
def customer_credit(cid):
    row = db.query("SELECT * FROM customers WHERE id = %s", (cid,), one=True)
    if not row:
        abort(404)
    try:
        amount = money.parse_money(request.form.get("amount"), label="Credit amount")
        billing.grant_credit(cid, amount, request.form.get("memo") or "",
                             user_id=session.get("user_id"))
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return redirect(url_for("admin.customer_detail", cid=cid, tab="ledger"))
    billing.audit(session.get("user_id"), session.get("username"),
                  request.headers.get("X-Real-IP") or request.remote_addr,
                  "credit_grant", "customer", cid, {"amount_cents": amount})
    flash(f"Granted {money.format_money(amount, row['currency'])} of credit.", "success")
    return redirect(url_for("admin.customer_detail", cid=cid, tab="ledger"))
