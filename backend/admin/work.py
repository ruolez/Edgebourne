import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import content
import db
import uploads

from . import bp
from .services import move_row


@bp.get("/work")
def work_list():
    rows = db.query("SELECT * FROM case_studies ORDER BY sort_order, id")
    return render_template("admin/work.html", rows=rows)


@bp.get("/work/new")
@bp.get("/work/<int:wid>")
def work_form(wid=None):
    row = None
    if wid:
        row = db.query("SELECT * FROM case_studies WHERE id = %s", (wid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/work_form.html", row=row)


@bp.post("/work/new")
@bp.post("/work/<int:wid>")
def work_save(wid=None):
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

    existing = None
    if wid:
        existing = db.query("SELECT * FROM case_studies WHERE id = %s", (wid,), one=True)
        if not existing:
            abort(404)

    cover = existing["cover_image"] if existing else None
    thumb = existing["cover_thumb"] if existing else None
    file = request.files.get("cover")
    if file and file.filename:
        try:
            new_cover, new_thumb = uploads.save_image(file)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(request.path)
        uploads.delete_upload(cover)
        uploads.delete_upload(thumb)
        cover, thumb = new_cover, new_thumb

    tags = [t.strip() for t in (f.get("tech_tags") or "").split(",") if t.strip()]
    body_md = f.get("body_md") or ""
    is_pub = bool(f.get("is_published"))
    params = (
        title, slug, (f.get("client") or "").strip(), (f.get("summary") or "").strip(),
        body_md, content.render_md(body_md), cover, thumb, tags,
        (f.get("meta_title") or "").strip() or None,
        (f.get("meta_description") or "").strip() or None,
        is_pub,
    )
    try:
        if wid:
            db.execute(
                """UPDATE case_studies SET title=%s, slug=%s, client=%s, summary=%s,
                   body_md=%s, body_html=%s, cover_image=%s, cover_thumb=%s,
                   tech_tags=%s, meta_title=%s, meta_description=%s, is_published=%s,
                   published_at = CASE WHEN %s AND published_at IS NULL
                                       THEN now() ELSE published_at END,
                   updated_at = now()
                   WHERE id=%s""",
                params + (is_pub, wid),
            )
        else:
            nxt = db.query(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM case_studies",
                one=True,
            )["n"]
            db.execute(
                """INSERT INTO case_studies
                   (title, slug, client, summary, body_md, body_html, cover_image,
                    cover_thumb, tech_tags, meta_title, meta_description, is_published,
                    published_at, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           CASE WHEN %s THEN now() END, %s)""",
                params + (is_pub, nxt),
            )
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        flash(f'Slug "{slug}" is already in use.', "error")
        return redirect(request.path)
    flash("Case study saved.", "success")
    return redirect(url_for("admin.work_list"))


@bp.post("/work/<int:wid>/delete")
def work_delete(wid):
    row = db.query("SELECT * FROM case_studies WHERE id = %s", (wid,), one=True)
    if row:
        uploads.delete_upload(row["cover_image"])
        uploads.delete_upload(row["cover_thumb"])
        db.execute("DELETE FROM case_studies WHERE id = %s", (wid,))
    flash("Case study deleted.", "success")
    return redirect(url_for("admin.work_list"))


@bp.post("/work/<int:wid>/move")
def work_move(wid):
    move_row("case_studies", wid, request.form.get("dir"))
    return redirect(url_for("admin.work_list"))
