import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import content
import db

from . import bp


@bp.get("/services")
def services_list():
    rows = db.query("SELECT * FROM services ORDER BY sort_order, id")
    return render_template("admin/services.html", rows=rows)


@bp.get("/services/new")
@bp.get("/services/<int:sid>")
def service_form(sid=None):
    row = None
    if sid:
        row = db.query("SELECT * FROM services WHERE id = %s", (sid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/service_form.html", row=row)


@bp.post("/services/new")
@bp.post("/services/<int:sid>")
def service_save(sid=None):
    f = request.form
    title = (f.get("title") or "").strip()
    if not title:
        flash("Title is required.", "error")
        return redirect(request.path)
    slug = content.clean_slug(f.get("slug"), title)
    err = content.slug_error(slug)
    if err:
        flash(err, "error")
        return redirect(request.path)
    body_md = f.get("body_md") or ""
    params = (
        title, slug, (f.get("summary") or "").strip(),
        body_md, content.render_md(body_md), bool(f.get("is_published")),
    )
    try:
        if sid:
            db.execute(
                """UPDATE services SET title=%s, slug=%s, summary=%s, body_md=%s,
                   body_html=%s, is_published=%s, updated_at=now() WHERE id=%s""",
                params + (sid,),
            )
        else:
            nxt = db.query(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM services", one=True
            )["n"]
            db.execute(
                """INSERT INTO services
                   (title, slug, summary, body_md, body_html, is_published, sort_order)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                params + (nxt,),
            )
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        flash(f'Slug "{slug}" is already in use.', "error")
        return redirect(request.path)
    flash("Service saved.", "success")
    return redirect(url_for("admin.services_list"))


@bp.post("/services/<int:sid>/delete")
def service_delete(sid):
    db.execute("DELETE FROM services WHERE id = %s", (sid,))
    flash("Service deleted.", "success")
    return redirect(url_for("admin.services_list"))


@bp.post("/services/<int:sid>/move")
def service_move(sid):
    move_row("services", sid, request.form.get("dir"))
    return redirect(url_for("admin.services_list"))


def move_row(table, row_id, direction):
    """Swap a row with its neighbor in sort_order, then renumber 0..n."""
    assert table in ("services", "case_studies", "pages")
    rows = db.query(f"SELECT id FROM {table} ORDER BY sort_order, id")
    ids = [r["id"] for r in rows]
    if row_id not in ids:
        return
    i = ids.index(row_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for order, id_ in enumerate(ids):
        db.execute(
            f"UPDATE {table} SET sort_order = %s WHERE id = %s", (order, id_)
        )
