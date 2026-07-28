"""Estimates — and, via ?status=accepted, work orders.

There is no separate orders table: a signed work order IS an accepted estimate.
That keeps one document type with one status lifecycle instead of two
near-identical tables that have to be kept in sync.

Unlike invoices, an estimate posts nothing to the ledger. It only becomes money
when convert_estimate_to_invoice() produces an invoice and that invoice is
issued.
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

STATUSES = [
    ("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"),
    ("declined", "Declined"), ("expired", "Expired"),
]


def _get(eid):
    row = db.query(
        """SELECT e.*, c.display_name AS customer_name, c.email AS customer_email,
                  c.terms_days, p.name AS project_name
             FROM estimates e
             JOIN customers c ON c.id = e.customer_id
             LEFT JOIN projects p ON p.id = e.project_id
            WHERE e.id = %s""",
        (eid,),
        one=True,
    )
    if not row:
        abort(404)
    return row


def _actor():
    return (session.get("user_id"), session.get("username"),
            request.headers.get("X-Real-IP") or request.remote_addr)


@bp.get("/estimates")
def estimates_list():
    status = request.args.get("status", "")
    customer_id = request.args.get("customer", "")
    # Opening the Work orders view is a natural moment to age out stale offers.
    try:
        billing.expire_estimates()
    except Exception:
        db.rollback()

    where, params = ["TRUE"], []
    if status:
        where.append("e.status = %s")
        params.append(status)
    if customer_id.isdigit():
        where.append("e.customer_id = %s")
        params.append(int(customer_id))

    rows = db.query(
        f"""SELECT e.*, c.display_name AS customer_name, p.name AS project_name,
                   (SELECT COALESCE(SUM(i.total_cents), 0) FROM invoices i
                     WHERE i.estimate_id = e.id AND i.status <> 'void') AS invoiced_cents
              FROM estimates e
              JOIN customers c ON c.id = e.customer_id
              LEFT JOIN projects p ON p.id = e.project_id
             WHERE {' AND '.join(where)}
             ORDER BY e.id DESC LIMIT 300""",
        tuple(params),
    )
    totals = db.query(
        """SELECT COALESCE(SUM(total_cents) FILTER (WHERE status = 'sent'), 0)::bigint AS pipeline,
                  COALESCE(SUM(total_cents) FILTER (WHERE status = 'accepted'), 0)::bigint AS won
             FROM estimates""",
        one=True,
    )
    return render_template("admin/estimates.html", rows=rows, status=status,
                           statuses=STATUSES, totals=totals,
                           work_orders=status == "accepted")


@bp.get("/estimates/new")
@bp.get("/estimates/<int:eid>")
def estimate_form(eid=None):
    row, lines = None, []
    if eid:
        row = _get(eid)
        lines = billing.get_lines("estimate", eid)
        invoices = db.query(
            """SELECT *, (status IN ('open','partial') AND due_date < current_date) AS is_overdue
                 FROM invoices WHERE estimate_id = %s ORDER BY id DESC""",
            (eid,),
        )
        invoiced = sum(i["total_cents"] for i in invoices if i["status"] != "void")
    else:
        invoices, invoiced = [], 0
        preset = request.args.get("customer", "")
        valid_days = int(db.get_setting("billing_estimate_valid_days", "30") or 30)
        row = {
            "id": None, "number": None, "status": "draft", "title": "",
            "currency": money.default_currency(), "issue_date": date.today(),
            "valid_until": date.today() + timedelta(days=valid_days),
            "subtotal_cents": 0, "discount_cents": 0, "tax_cents": 0, "total_cents": 0,
            "customer_id": int(preset) if preset.isdigit() else None,
            "project_id": int(request.args.get("project") or 0) or None,
            "notes_md": "", "terms_md": db.get_setting("billing_default_terms_text", ""),
            "accepted_at": None, "accepted_name": None, "sent_at": None,
            "last_viewed_at": None, "customer_name": "",
        }

    fresh_token = session.pop(f"estimate_link_{eid}", None) if eid else None
    return render_template(
        "admin/estimate_form.html",
        row=row, lines=lines, invoices=invoices, invoiced=invoiced,
        is_new=eid is None, statuses=STATUSES, fresh_token=fresh_token,
        base_url=config.PUBLIC_BASE_URL or request.url_root.rstrip("/"),
        customers=billing.customer_options(include_archived=bool(eid)),
        projects=billing.project_options(),
    )


@bp.post("/estimates/new")
@bp.post("/estimates/<int:eid>")
def estimate_save(eid=None):
    f = request.form
    existing = _get(eid) if eid else None
    if existing and existing["status"] != "draft":
        flash("This estimate has been sent — its line items can no longer be changed.", "error")
        return redirect(url_for("admin.estimate_form", eid=eid))

    if not (f.get("customer_id") or "").isdigit():
        flash("Pick a customer.", "error")
        return redirect(request.path)
    customer_id = int(f["customer_id"])
    customer = db.query("SELECT * FROM customers WHERE id = %s", (customer_id,), one=True)
    if not customer:
        flash("That customer no longer exists.", "error")
        return redirect(request.path)
    if existing and existing["customer_id"] != customer_id:
        flash("An estimate cannot be moved to a different customer. Duplicate it instead.", "error")
        return redirect(request.path)

    project_id = int(f["project_id"]) if (f.get("project_id") or "").isdigit() else None
    try:
        lines = billing.read_lines(f)
        discount = money.parse_money(f.get("discount"), default=0, label="Discount")
        issue_date = billing.parse_date(f.get("issue_date")) or date.today()
        valid_until = billing.parse_date(f.get("valid_until"))
    except (billing.BillingError, money.MoneyError) as e:
        flash(str(e), "error")
        return redirect(request.path)

    if valid_until and valid_until < issue_date:
        flash("The valid-until date cannot be before the issue date.", "error")
        return redirect(request.path)

    params = ((f.get("title") or "").strip(), project_id, issue_date, valid_until,
              f.get("notes_md") or "", f.get("terms_md") or "")
    try:
        with db.transaction():
            if eid:
                db.execute(
                    """UPDATE estimates SET title=%s, project_id=%s, issue_date=%s,
                           valid_until=%s, notes_md=%s, terms_md=%s, updated_at=now()
                         WHERE id=%s""",
                    params + (eid,),
                )
            else:
                row = db.execute(
                    """INSERT INTO estimates (customer_id, currency, title, project_id,
                           issue_date, valid_until, notes_md, terms_md, created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (customer_id, customer["currency"]) + params + (session.get("user_id"),),
                    returning=True,
                )
                eid = row["id"]
            billing.save_lines("estimate", eid, lines)
            billing.recompute_totals("estimate", eid, discount)
    except billing.BillingError as e:
        flash(str(e), "error")
        return redirect(request.path)

    flash("Estimate saved.", "success")
    return redirect(url_for("admin.estimate_form", eid=eid))


@bp.post("/estimates/<int:eid>/send")
def estimate_send(eid):
    row = _get(eid)
    token = None
    if row["status"] == "draft":
        try:
            _, token = billing.issue_estimate(eid, user_id=session.get("user_id"))
        except billing.BillingError as e:
            flash(str(e), "error")
            return redirect(url_for("admin.estimate_form", eid=eid))
        row = _get(eid)

    if not row["customer_email"]:
        flash("This customer has no billing email address.", "error")
        return redirect(url_for("admin.estimate_form", eid=eid))
    if token is None:
        token = billing.rotate_token("estimate", eid)

    livemode = True
    try:
        import stripe_client
        livemode = stripe_client.livemode() if stripe_client.is_configured() else True
    except Exception:
        pass

    customer = db.query("SELECT * FROM customers WHERE id = %s", (row["customer_id"],), one=True)
    view_url = f"{config.PUBLIC_BASE_URL or request.url_root.rstrip('/')}/estimate/{token}"
    log_id = billing_mail.send_estimate(dict(row), dict(customer), view_url, livemode=livemode)
    db.execute("UPDATE estimates SET sent_at = now(), updated_at = now() WHERE id = %s", (eid,))
    if log_id:
        mailer.try_send_now(log_id)
        flash(f"Estimate sent to {customer['email']}.", "success")
    else:
        flash("Email is suppressed in test mode — set a test-email override in billing settings.",
              "error")
    session[f"estimate_link_{eid}"] = token
    billing.audit(*_actor(), "estimate_send", "estimate", eid, {"to": customer["email"]})
    return redirect(url_for("admin.estimate_form", eid=eid))


@bp.post("/estimates/<int:eid>/status")
def estimate_status(eid):
    try:
        billing.set_estimate_status(eid, request.form.get("status") or "",
                                    user_id=session.get("user_id"))
    except billing.BillingError as e:
        flash(str(e), "error")
    else:
        billing.audit(*_actor(), "estimate_status", "estimate", eid,
                      {"status": request.form.get("status")})
        flash("Estimate updated.", "success")
    return redirect(url_for("admin.estimate_form", eid=eid))


@bp.post("/estimates/<int:eid>/convert")
def estimate_convert(eid):
    try:
        invoice_id = billing.convert_estimate_to_invoice(eid, user_id=session.get("user_id"))
    except billing.BillingError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.estimate_form", eid=eid))
    billing.audit(*_actor(), "estimate_convert", "estimate", eid, {"invoice_id": invoice_id})
    flash("Draft invoice created from this estimate. Check the dates, then issue it.", "success")
    return redirect(url_for("admin.invoice_form", iid=invoice_id))


@bp.post("/estimates/<int:eid>/token")
def estimate_rotate_token(eid):
    row = _get(eid)
    if row["status"] == "draft":
        flash("A draft has no customer link yet — send it first.", "error")
        return redirect(url_for("admin.estimate_form", eid=eid))
    session[f"estimate_link_{eid}"] = billing.rotate_token("estimate", eid)
    billing.audit(*_actor(), "estimate_rotate_token", "estimate", eid)
    flash("New link generated. The previous one stops working in 24 hours.", "success")
    return redirect(url_for("admin.estimate_form", eid=eid))


@bp.post("/estimates/<int:eid>/duplicate")
def estimate_duplicate(eid):
    _get(eid)
    valid_days = int(db.get_setting("billing_estimate_valid_days", "30") or 30)
    with db.transaction():
        new = db.execute(
            """INSERT INTO estimates (customer_id, project_id, currency, title, issue_date,
                   valid_until, notes_md, terms_md, discount_cents, created_by)
               SELECT customer_id, project_id, currency, title, current_date,
                      current_date + %s, notes_md, terms_md, discount_cents, %s
                 FROM estimates WHERE id = %s
               RETURNING id""",
            (timedelta(days=valid_days), session.get("user_id"), eid),
            returning=True,
        )
        billing.copy_lines("estimate", eid, "estimate", new["id"])
        billing.recompute_totals("estimate", new["id"])
    flash("Estimate duplicated as a new draft.", "success")
    return redirect(url_for("admin.estimate_form", eid=new["id"]))


@bp.post("/estimates/<int:eid>/delete")
def estimate_delete(eid):
    row = _get(eid)
    if row["status"] != "draft":
        flash("Only drafts can be deleted. Mark this one declined or expired instead.", "error")
        return redirect(url_for("admin.estimate_form", eid=eid))
    db.execute("DELETE FROM estimates WHERE id = %s", (eid,))
    flash("Draft deleted.", "success")
    return redirect(url_for("admin.estimates_list"))


@bp.get("/estimates/<int:eid>/print")
def estimate_print(eid):
    row = _get(eid)
    return render_template(
        "admin/estimate_print.html",
        est=row,
        lines=billing.get_lines("estimate", eid),
        customer=db.query("SELECT * FROM customers WHERE id = %s",
                          (row["customer_id"],), one=True),
    )
