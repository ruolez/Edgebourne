"""Invoices.

Line items are editable only while status='draft'. Once issued, a document is a
financial record: corrections go through void-and-reissue or a credit. That rule
is what keeps the ledger's 'invoice' entry permanently equal to total_cents with
no reconciliation logic, and it also removes the "invoice edited while the
customer was mid-checkout" race.
"""

from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, session, url_for

import billing
import billing_mail
import config
import db
import mailer
import money

from . import bp

LIST_SQL = """
    SELECT i.*, c.display_name AS customer_name, p.name AS project_name,
           (i.status IN ('open','partial') AND i.due_date < current_date) AS is_overdue
      FROM invoices i
      JOIN customers c ON c.id = i.customer_id
      LEFT JOIN projects p ON p.id = i.project_id
"""


def _get(iid):
    row = db.query(
        """SELECT i.*, c.display_name AS customer_name, c.email AS customer_email,
                  c.company AS customer_company, c.terms_days,
                  c.default_tax_rate_milli, p.name AS project_name,
                  (i.status IN ('open','partial') AND i.due_date < current_date) AS is_overdue
             FROM invoices i
             JOIN customers c ON c.id = i.customer_id
             LEFT JOIN projects p ON p.id = i.project_id
            WHERE i.id = %s""",
        (iid,),
        one=True,
    )
    if not row:
        abort(404)
    return row


@bp.get("/invoices")
def invoices_list():
    status = request.args.get("status", "")
    customer_id = request.args.get("customer", "")
    where, params = ["TRUE"], []
    if status == "overdue":
        where.append("i.status IN ('open','partial') AND i.due_date < current_date")
    elif status == "unpaid":
        where.append("i.status IN ('open','partial')")
    elif status:
        where.append("i.status = %s")
        params.append(status)
    if customer_id.isdigit():
        where.append("i.customer_id = %s")
        params.append(int(customer_id))

    rows = db.query(
        f"{LIST_SQL} WHERE {' AND '.join(where)} ORDER BY i.id DESC LIMIT 300",
        tuple(params),
    )
    totals = db.query(
        """SELECT COALESCE(SUM(balance_due_cents), 0)::bigint AS outstanding,
                  COALESCE(SUM(balance_due_cents) FILTER (WHERE due_date < current_date), 0)::bigint AS overdue
             FROM invoices WHERE status IN ('open','partial')""",
        one=True,
    )
    return render_template("admin/invoices.html", rows=rows, status=status,
                           customer_id=customer_id, totals=totals)


@bp.get("/invoices/new")
@bp.get("/invoices/<int:iid>")
def invoice_form(iid=None):
    row, lines = None, []
    if iid:
        row = _get(iid)
        lines = billing.get_lines("invoice", iid)
        payments = db.query(
            "SELECT * FROM payments WHERE invoice_id = %s ORDER BY received_on DESC, id DESC",
            (iid,),
        )
        bal = billing.customer_balance(row["customer_id"])
    else:
        payments, bal = [], None

    preset_customer = request.args.get("customer", "")
    # A brand-new invoice needs a doc-shaped object so the shared totals macro
    # and the currency affix work before anything is saved.
    if not row:
        terms = int(db.get_setting("billing_default_terms_days", "14") or 14)
        row = {
            "id": None, "number": None, "status": "draft", "title": "",
            "currency": money.default_currency(), "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=terms),
            "subtotal_cents": 0, "discount_cents": 0, "tax_cents": 0,
            "total_cents": 0, "amount_paid_cents": 0, "balance_due_cents": 0,
            "customer_id": int(preset_customer) if preset_customer.isdigit() else None,
            "project_id": int(request.args.get("project") or 0) or None,
            "notes_md": "", "terms_md": db.get_setting("billing_default_terms_text", ""),
        }

    # Shown once, right after issuing or rotating. Only the hash is stored, so
    # this is the single opportunity to copy the link out of the UI.
    fresh_token = session.pop(f"invoice_link_{iid}", None) if iid else None

    return render_template(
        "admin/invoice_form.html",
        row=row, lines=lines, payments=payments, bal=bal, is_new=iid is None,
        fresh_token=fresh_token, base_url=config.site_base_url(request.url_root),
        methods=[("bank_transfer", "Bank transfer / ACH"), ("check", "Cheque"),
                 ("cash", "Cash"), ("other", "Other")],
        customers=billing.customer_options(include_archived=bool(iid)),
        projects=billing.project_options(),
    )


@bp.post("/invoices/new")
@bp.post("/invoices/<int:iid>")
def invoice_save(iid=None):
    f = request.form
    existing = _get(iid) if iid else None

    if existing and existing["status"] != "draft":
        flash("This invoice has been issued — its line items can no longer be changed.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))

    if not (f.get("customer_id") or "").isdigit():
        flash("Pick a customer.", "error")
        return redirect(request.path)
    customer_id = int(f["customer_id"])
    customer = db.query("SELECT * FROM customers WHERE id = %s", (customer_id,), one=True)
    if not customer:
        flash("That customer no longer exists.", "error")
        return redirect(request.path)
    if existing and existing["customer_id"] != customer_id:
        # The ledger sums one currency per customer; moving a document between
        # customers would move money between two ledgers.
        flash("An invoice cannot be moved to a different customer. Duplicate it instead.", "error")
        return redirect(request.path)

    project_id = int(f["project_id"]) if (f.get("project_id") or "").isdigit() else None

    try:
        lines = billing.read_lines(f)
        discount = money.parse_money(f.get("discount"), default=0, label="Discount")
        issue_date = billing.parse_date(f.get("issue_date")) or date.today()
        due_date = billing.parse_date(f.get("due_date"))
    except (billing.BillingError, money.MoneyError) as e:
        flash(str(e), "error")
        return redirect(request.path)

    if due_date and due_date < issue_date:
        flash("The due date cannot be before the issue date.", "error")
        return redirect(request.path)
    if not due_date:
        due_date = issue_date + timedelta(days=customer["terms_days"])

    params = (
        (f.get("title") or "").strip(), project_id, issue_date, due_date,
        f.get("notes_md") or "", f.get("terms_md") or "",
    )

    try:
        with db.transaction():
            if iid:
                db.execute(
                    """UPDATE invoices SET title=%s, project_id=%s, issue_date=%s,
                           due_date=%s, notes_md=%s, terms_md=%s, updated_at=now()
                         WHERE id=%s""",
                    params + (iid,),
                )
            else:
                row = db.execute(
                    """INSERT INTO invoices (customer_id, currency, title, project_id,
                           issue_date, due_date, notes_md, terms_md, created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (customer_id, customer["currency"]) + params + (session.get("user_id"),),
                    returning=True,
                )
                iid = row["id"]
            billing.save_lines("invoice", iid, lines)
            billing.recompute_totals("invoice", iid, discount)
    except billing.BillingError as e:
        flash(str(e), "error")
        return redirect(request.path)

    flash("Invoice saved.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


def _actor():
    return (session.get("user_id"), session.get("username"),
            request.headers.get("X-Real-IP") or request.remote_addr)


@bp.post("/invoices/<int:iid>/issue")
def invoice_issue(iid):
    try:
        number, token = billing.issue_invoice(iid, user_id=session.get("user_id"))
    except billing.BillingError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    billing.audit(*_actor(), "invoice_issue", "invoice", iid, {"number": number})
    # The raw token exists only here and in the email; only its hash is stored.
    session[f"invoice_link_{iid}"] = token
    flash(f"Issued as {number}. The customer payment link is ready to send.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/invoices/<int:iid>/void")
def invoice_void(iid):
    try:
        billing.void_invoice(iid, user_id=session.get("user_id"))
    except billing.BillingError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    billing.audit(*_actor(), "invoice_void", "invoice", iid)
    flash("Invoice voided and reversed on the customer's ledger.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/invoices/<int:iid>/send")
def invoice_send(iid):
    """Email the invoice. Issues it first if it is still a draft, so 'Send' is
    one click rather than two. A fresh token is minted only when there isn't one
    already, so resending does not break a link the customer already has."""
    row = _get(iid)
    token = None
    if row["status"] == "draft":
        try:
            _, token = billing.issue_invoice(iid, user_id=session.get("user_id"))
        except billing.BillingError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.invoice_form", iid=iid))
        row = _get(iid)
    if row["status"] in ("void", "uncollectible"):
        flash("This invoice is void — it cannot be sent.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))

    customer = db.query("SELECT * FROM customers WHERE id = %s", (row["customer_id"],), one=True)
    if not customer["email"]:
        flash("This customer has no billing email address.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))

    if token is None:
        # Only the hash is stored, so an existing link cannot be re-derived.
        # Rotating keeps the old one alive for 24h, so nothing breaks.
        token = billing.rotate_token("invoice", iid)

    livemode = True
    try:
        import stripe_client
        livemode = stripe_client.livemode() if stripe_client.is_configured() else True
    except Exception:
        pass

    pay_url = f"{config.site_base_url(request.url_root)}/pay/{token}"
    log_id = billing_mail.send_invoice(dict(row), dict(customer), pay_url, livemode=livemode)
    db.execute("UPDATE invoices SET sent_at = now(), updated_at = now() WHERE id = %s", (iid,))
    if log_id:
        mailer.try_send_now(log_id)
        flash(f"Invoice sent to {customer['email']}.", "success")
    else:
        flash("Email is suppressed in test mode — set a test-email override in billing settings.",
              "error")
    session[f"invoice_link_{iid}"] = token
    billing.audit(*_actor(), "invoice_send", "invoice", iid, {"to": customer["email"]})
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/invoices/<int:iid>/token")
def invoice_rotate_token(iid):
    row = _get(iid)
    if row["status"] == "draft":
        flash("A draft has no customer link yet — issue it first.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    token = billing.rotate_token("invoice", iid)
    session[f"invoice_link_{iid}"] = token
    billing.audit(*_actor(), "invoice_rotate_token", "invoice", iid)
    flash("New link generated. The previous one stops working in 24 hours.", "success")
    return redirect(url_for("admin.invoice_form", iid=iid))


@bp.post("/invoices/<int:iid>/duplicate")
def invoice_duplicate(iid):
    src = _get(iid)
    terms = src["terms_days"] or 14
    with db.transaction():
        new = db.execute(
            """INSERT INTO invoices (customer_id, project_id, currency, title,
                   issue_date, due_date, notes_md, terms_md, discount_cents, created_by)
               SELECT customer_id, project_id, currency, title, current_date,
                      current_date + %s, notes_md, terms_md, discount_cents, %s
                 FROM invoices WHERE id = %s
               RETURNING id""",
            (timedelta(days=terms), session.get("user_id"), iid),
            returning=True,
        )
        billing.copy_lines("invoice", iid, "invoice", new["id"])
        billing.recompute_totals("invoice", new["id"])
    flash("Invoice duplicated as a new draft.", "success")
    return redirect(url_for("admin.invoice_form", iid=new["id"]))


@bp.post("/invoices/<int:iid>/delete")
def invoice_delete(iid):
    row = _get(iid)
    # Issued invoices are never deletable: the number is allocated, the ledger
    # has an entry, and gapless numbering is a legal requirement in some
    # jurisdictions. Void is the only way out.
    if row["status"] != "draft":
        flash("Only drafts can be deleted. Void this invoice instead.", "error")
        return redirect(url_for("admin.invoice_form", iid=iid))
    db.execute("DELETE FROM invoices WHERE id = %s", (iid,))
    flash("Draft deleted.", "success")
    return redirect(url_for("admin.invoices_list"))


@bp.get("/invoices/<int:iid>/print")
def invoice_print(iid):
    row = _get(iid)
    return render_template(
        "admin/invoice_print.html",
        inv=row,
        lines=billing.get_lines("invoice", iid),
        customer=db.query("SELECT * FROM customers WHERE id = %s", (row["customer_id"],), one=True),
        payments=db.query(
            """SELECT * FROM payments WHERE invoice_id = %s AND status = 'succeeded'
                ORDER BY received_on, id""",
            (iid,),
        ),
    )
