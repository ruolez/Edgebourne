"""Projects: the engagement container. Groups estimates and invoices under a
customer and tracks budget against what has actually been billed."""

import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import billing
import content
import db
import money

from . import bp


@bp.get("/projects")
def projects_list():
    status = request.args.get("status", "")
    customer_id = request.args.get("customer", "")
    where, params = ["TRUE"], []
    if status:
        where.append("p.status = %s")
        params.append(status)
    if customer_id.isdigit():
        where.append("p.customer_id = %s")
        params.append(int(customer_id))
    rows = db.query(
        f"""SELECT p.*, c.display_name AS customer_name, c.currency,
                   (SELECT COALESCE(SUM(i.total_cents), 0) FROM invoices i
                     WHERE i.project_id = p.id AND i.status <> 'void') AS billed_cents
              FROM projects p
              JOIN customers c ON c.id = p.customer_id
             WHERE {' AND '.join(where)}
             ORDER BY c.display_name, p.name""",
        tuple(params),
    )
    return render_template("admin/projects.html", rows=rows, status=status,
                           customer_id=customer_id,
                           customers=billing.customer_options(include_archived=True))


@bp.get("/projects/new")
@bp.get("/projects/<int:pid>")
def project_form(pid=None):
    row = None
    related = {"invoices": [], "estimates": [], "billed_cents": 0}
    if pid:
        row = db.query(
            """SELECT p.*, c.currency, c.display_name AS customer_name
                 FROM projects p JOIN customers c ON c.id = p.customer_id
                WHERE p.id = %s""",
            (pid,),
            one=True,
        )
        if not row:
            abort(404)
        related["invoices"] = db.query(
            """SELECT *, (status IN ('open','partial') AND due_date < current_date) AS is_overdue
                 FROM invoices WHERE project_id = %s ORDER BY id DESC""",
            (pid,),
        )
        related["estimates"] = db.query(
            "SELECT * FROM estimates WHERE project_id = %s ORDER BY id DESC", (pid,)
        )
        related["billed_cents"] = sum(
            i["total_cents"] for i in related["invoices"] if i["status"] != "void"
        )
    return render_template(
        "admin/project_form.html",
        row=row,
        related=related,
        customers=billing.customer_options(include_archived=bool(row)),
        statuses=billing.PROJECT_STATUSES,
        preset_customer=request.args.get("customer", ""),
    )


@bp.post("/projects/new")
@bp.post("/projects/<int:pid>")
def project_save(pid=None):
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("A project name is required.", "error")
        return redirect(request.path)
    if not (f.get("customer_id") or "").isdigit():
        flash("Pick a customer.", "error")
        return redirect(request.path)

    try:
        budget = money.parse_money(f.get("budget_cents"), default=0, label="Budget")
        start = billing.parse_date(f.get("start_date"))
        end = billing.parse_date(f.get("end_date"))
    except (money.MoneyError, billing.BillingError) as e:
        flash(str(e), "error")
        return redirect(request.path)

    if start and end and end < start:
        flash("The end date cannot be before the start date.", "error")
        return redirect(request.path)

    status = f.get("status") or "active"
    if status not in dict(billing.PROJECT_STATUSES):
        flash("Unknown project status.", "error")
        return redirect(request.path)

    desc_md = f.get("description_md") or ""
    params = (
        int(f["customer_id"]), name, (f.get("code") or "").strip(), status,
        start, end, budget, desc_md, content.render_md(desc_md),
    )

    if pid:
        db.execute(
            """UPDATE projects SET customer_id=%s, name=%s, code=%s, status=%s,
                   start_date=%s, end_date=%s, budget_cents=%s,
                   description_md=%s, description_html=%s, updated_at=now()
                 WHERE id=%s""",
            params + (pid,),
        )
    else:
        row = db.execute(
            """INSERT INTO projects (customer_id, name, code, status, start_date,
                   end_date, budget_cents, description_md, description_html)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            params,
            returning=True,
        )
        pid = row["id"]

    flash("Project saved.", "success")
    return redirect(url_for("admin.project_form", pid=pid))


@bp.post("/projects/<int:pid>/delete")
def project_delete(pid):
    # Invoices/estimates reference projects with ON DELETE SET NULL, so this
    # succeeds and orphans nothing -- the documents survive, which is correct.
    try:
        db.execute("DELETE FROM projects WHERE id = %s", (pid,))
    except psycopg2.errors.ForeignKeyViolation:
        db.rollback()
        flash("This project is still referenced and cannot be deleted.", "error")
        return redirect(url_for("admin.project_form", pid=pid))
    flash("Project deleted. Its invoices and estimates were kept.", "success")
    return redirect(url_for("admin.projects_list"))
