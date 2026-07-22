from flask import abort, flash, redirect, render_template, request, url_for

import db

from . import bp


@bp.get("/leads")
def leads_list():
    show = request.args.get("show", "all")
    where = "WHERE NOT is_read" if show == "unread" else ""
    rows = db.query(f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT 500")
    return render_template("admin/leads.html", rows=rows, show=show)


@bp.get("/leads/<int:lid>")
def lead_detail(lid):
    row = db.query("SELECT * FROM leads WHERE id = %s", (lid,), one=True)
    if not row:
        abort(404)
    if not row["is_read"]:
        db.execute("UPDATE leads SET is_read = true WHERE id = %s", (lid,))
    return render_template("admin/lead_detail.html", lead=row)


@bp.post("/leads/<int:lid>/delete")
def lead_delete(lid):
    db.execute("DELETE FROM leads WHERE id = %s", (lid,))
    flash("Lead deleted.", "success")
    return redirect(url_for("admin.leads_list"))


@bp.post("/leads/read-all")
def leads_read_all():
    db.execute("UPDATE leads SET is_read = true WHERE NOT is_read")
    flash("All leads marked read.", "success")
    return redirect(url_for("admin.leads_list"))
