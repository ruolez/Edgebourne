"""Recurring invoices (retainers).

Generation itself lives in scheduler.py, which runs as its own container. These
routes only edit the template and let an admin force a run.
"""

from datetime import date

from flask import abort, flash, redirect, render_template, request, session, url_for

import billing
import db
import money
import schedule_dates as sd

from . import bp

INTERVALS = [
    ("weekly", "Weekly"), ("monthly", "Monthly"), ("quarterly", "Quarterly"),
    ("semiannual", "Every 6 months"), ("annual", "Annually"),
]
STATUSES = [("active", "Active"), ("paused", "Paused"), ("ended", "Ended")]


def _get(rid):
    row = db.query(
        """SELECT s.*, c.display_name AS customer_name, c.email AS customer_email,
                  c.terms_days AS customer_terms, p.name AS project_name
             FROM subscriptions s
             JOIN customers c ON c.id = s.customer_id
             LEFT JOIN projects p ON p.id = s.project_id
            WHERE s.id = %s""",
        (rid,),
        one=True,
    )
    if not row:
        abort(404)
    return row


@bp.get("/recurring")
def recurring_list():
    rows = db.query(
        """SELECT s.*, c.display_name AS customer_name,
                  (SELECT COUNT(*) FROM invoices i WHERE i.subscription_id = s.id) AS generated,
                  (SELECT COALESCE(SUM(l.amount_cents), 0) FROM subscription_lines l
                    WHERE l.subscription_id = s.id) AS lines_total
             FROM subscriptions s
             JOIN customers c ON c.id = s.customer_id
            ORDER BY s.status, s.next_run_at NULLS LAST, s.id DESC"""
    )
    beat = db.query("SELECT * FROM scheduler_state WHERE key = 'tick'", one=True)
    return render_template("admin/recurring.html", rows=rows, heartbeat=beat,
                           intervals=dict(INTERVALS))


@bp.get("/recurring/new")
@bp.get("/recurring/<int:rid>")
def recurring_form(rid=None):
    row, lines, runs = None, [], []
    if rid:
        row = _get(rid)
        lines = billing.get_lines("recurring", rid)
        runs = db.query(
            """SELECT r.*, i.number AS invoice_number, i.status AS invoice_status
                 FROM subscription_runs r
                 LEFT JOIN invoices i ON i.id = r.invoice_id
                WHERE r.subscription_id = %s ORDER BY r.period_start DESC LIMIT 24""",
            (rid,),
        )
    else:
        preset = request.args.get("customer", "")
        row = {
            "id": None, "name": "", "status": "active", "currency": money.default_currency(),
            "interval": "monthly", "interval_count": 1, "anchor_day": date.today().day,
            "start_date": date.today(), "end_date": None,
            "timezone": db.get_setting("billing_timezone", "UTC"),
            "run_hour": int(db.get_setting("billing_run_hour", "7") or 7),
            "terms_days": int(db.get_setting("billing_default_terms_days", "14") or 14),
            # The shared doc_totals macro reads these, so an unsaved retainer
            # needs the same shape as a persisted one.
            "subtotal_cents": 0, "discount_cents": 0, "tax_cents": 0, "total_cents": 0,
            "max_occurrences": None,
            "auto_send": db.get_setting("billing_default_auto_send", "1") == "1",
            "notes_md": "", "terms_md": db.get_setting("billing_default_terms_text", ""),
            "customer_id": int(preset) if preset.isdigit() else None,
            "project_id": None, "next_run_at": None, "occurrences_generated": 0,
            "last_run_at": None, "last_error": None, "customer_name": "",
        }

    preview = []
    if rid and row["status"] == "active":
        try:
            for n in range(row["occurrences_generated"], row["occurrences_generated"] + 3):
                start, end = sd.period_bounds(row, n)
                preview.append({"start": start, "end": end,
                                "key": sd.period_key(row, start),
                                "run_at": sd.next_run_for(row, n)})
        except Exception:
            preview = []

    return render_template(
        "admin/recurring_form.html",
        row=row, lines=lines, runs=runs, preview=preview, is_new=rid is None,
        intervals=INTERVALS, statuses=STATUSES,
        customers=billing.customer_options(include_archived=bool(rid)),
        projects=billing.project_options(),
    )


@bp.post("/recurring/new")
@bp.post("/recurring/<int:rid>")
def recurring_save(rid=None):
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Give this retainer a name — it becomes the invoice title.", "error")
        return redirect(request.path)
    if not (f.get("customer_id") or "").isdigit():
        flash("Pick a customer.", "error")
        return redirect(request.path)
    customer_id = int(f["customer_id"])
    customer = db.query("SELECT * FROM customers WHERE id = %s", (customer_id,), one=True)
    if not customer:
        flash("That customer no longer exists.", "error")
        return redirect(request.path)

    interval = f.get("interval") or "monthly"
    if interval not in dict(INTERVALS):
        flash("Unknown billing interval.", "error")
        return redirect(request.path)
    status = f.get("status") or "active"
    if status not in dict(STATUSES):
        flash("Unknown status.", "error")
        return redirect(request.path)

    try:
        lines = billing.read_lines(f)
        discount = money.parse_money(f.get("discount"), default=0, label="Discount")
        start_date = billing.parse_date(f.get("start_date")) or date.today()
        end_date = billing.parse_date(f.get("end_date"))
        count = max(1, min(52, int(f.get("interval_count") or 1)))
        run_hour = max(0, min(23, int(f.get("run_hour") or 7)))
        terms = max(0, min(365, int(f.get("terms_days") or 14)))
        max_occ = int(f["max_occurrences"]) if (f.get("max_occurrences") or "").strip() else None
    except (billing.BillingError, money.MoneyError) as e:
        flash(str(e), "error")
        return redirect(request.path)
    except ValueError:
        flash("Interval, run hour, terms and occurrence limit must be whole numbers.", "error")
        return redirect(request.path)

    if end_date and end_date < start_date:
        flash("The end date cannot be before the start date.", "error")
        return redirect(request.path)

    tz = (f.get("timezone") or "UTC").strip() or "UTC"
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
    except Exception:
        flash(f'"{tz}" is not a recognised timezone. Use e.g. America/Chicago.', "error")
        return redirect(request.path)

    # Anchoring on the start date is what stops Jan 31 walking to Feb 28 and
    # then staying there. See schedule_dates.
    anchor_day = start_date.day
    params = (name, customer_id,
              int(f["project_id"]) if (f.get("project_id") or "").isdigit() else None,
              status, interval, count, anchor_day, start_date, end_date, tz, run_hour,
              terms, max_occ, bool(f.get("auto_send")),
              f.get("notes_md") or "", f.get("terms_md") or "")

    with db.transaction():
        if rid:
            db.execute(
                """UPDATE subscriptions SET name=%s, customer_id=%s, project_id=%s, status=%s,
                       interval=%s, interval_count=%s, anchor_day=%s, start_date=%s,
                       end_date=%s, timezone=%s, run_hour=%s, terms_days=%s,
                       max_occurrences=%s, auto_send=%s, notes_md=%s, terms_md=%s,
                       updated_at=now()
                     WHERE id=%s""",
                params + (rid,),
            )
        else:
            row = db.execute(
                """INSERT INTO subscriptions (name, customer_id, project_id, status, interval,
                       interval_count, anchor_day, start_date, end_date, timezone, run_hour,
                       terms_days, max_occurrences, auto_send, notes_md, terms_md, currency)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                params + (customer["currency"],),
                returning=True,
            )
            rid = row["id"]
        billing.save_lines("recurring", rid, lines)
        billing.recompute_totals("recurring", rid, discount)
        # next_run_at is always derived from occurrences_generated, so editing
        # the schedule re-plans correctly instead of drifting.
        sub = db.query("SELECT * FROM subscriptions WHERE id = %s", (rid,), one=True)
        nxt = sd.next_run_for(sub) if sub["status"] == "active" else None
        db.execute("UPDATE subscriptions SET next_run_at = %s WHERE id = %s", (nxt, rid))

    flash("Recurring invoice saved.", "success")
    return redirect(url_for("admin.recurring_form", rid=rid))


@bp.post("/recurring/<int:rid>/run-now")
def recurring_run_now(rid):
    """Generate the next due period immediately. Uses the same code the
    scheduler runs, so the period_key constraint still prevents a duplicate."""
    import scheduler

    sub = _get(rid)
    if sub["status"] != "active":
        flash("Only an active retainer can be run.", "error")
        return redirect(url_for("admin.recurring_form", rid=rid))
    try:
        with db.standalone() as conn:
            made = scheduler.generate_one_period(
                conn, dict(sub), scheduler.datetime.now(scheduler.timezone.utc),
                catching_up=False)
    except Exception as e:
        flash(f"Could not generate the invoice: {e}", "error")
        return redirect(url_for("admin.recurring_form", rid=rid))
    billing.audit(session.get("user_id"), session.get("username"),
                  request.headers.get("X-Real-IP") or request.remote_addr,
                  "recurring_run", "subscription", rid, {"created": made})
    flash("Invoice generated." if made else
          "This period was already generated — nothing to do.", "success")
    return redirect(url_for("admin.recurring_form", rid=rid))


@bp.post("/recurring/<int:rid>/delete")
def recurring_delete(rid):
    _get(rid)
    # Generated invoices reference this with ON DELETE SET NULL, so they survive.
    db.execute("DELETE FROM subscriptions WHERE id = %s", (rid,))
    flash("Recurring invoice deleted. Invoices it already generated were kept.", "success")
    return redirect(url_for("admin.recurring_list"))
