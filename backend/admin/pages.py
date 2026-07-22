import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import content
import db

from . import bp
from .services import move_row


@bp.get("/pages")
def pages_list():
    rows = db.query("SELECT * FROM pages ORDER BY sort_order, id")
    return render_template("admin/pages.html", rows=rows)


@bp.get("/pages/new")
@bp.get("/pages/<int:pid>")
def page_form(pid=None):
    row = None
    if pid:
        row = db.query("SELECT * FROM pages WHERE id = %s", (pid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/page_form.html", row=row)


@bp.post("/pages/new")
@bp.post("/pages/<int:pid>")
def page_save(pid=None):
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
        title, slug, body_md, content.render_md(body_md),
        (f.get("meta_title") or "").strip() or None,
        (f.get("meta_description") or "").strip() or None,
        bool(f.get("show_in_nav")),
        (f.get("nav_label") or "").strip() or None,
        bool(f.get("is_published")),
    )
    try:
        if pid:
            db.execute(
                """UPDATE pages SET title=%s, slug=%s, body_md=%s, body_html=%s,
                   meta_title=%s, meta_description=%s, show_in_nav=%s, nav_label=%s,
                   is_published=%s, updated_at=now() WHERE id=%s""",
                params + (pid,),
            )
        else:
            nxt = db.query(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM pages", one=True
            )["n"]
            db.execute(
                """INSERT INTO pages
                   (title, slug, body_md, body_html, meta_title, meta_description,
                    show_in_nav, nav_label, is_published, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                params + (nxt,),
            )
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        flash(f'Slug "{slug}" is already in use.', "error")
        return redirect(request.path)
    flash("Page saved.", "success")
    return redirect(url_for("admin.pages_list"))


@bp.post("/pages/<int:pid>/delete")
def page_delete(pid):
    db.execute("DELETE FROM pages WHERE id = %s", (pid,))
    flash("Page deleted.", "success")
    return redirect(url_for("admin.pages_list"))


@bp.post("/pages/<int:pid>/move")
def page_move(pid):
    move_row("pages", pid, request.form.get("dir"))
    return redirect(url_for("admin.pages_list"))
