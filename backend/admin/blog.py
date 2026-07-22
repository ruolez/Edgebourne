import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import content
import db
import uploads

from . import bp


@bp.get("/blog")
def blog_list():
    rows = db.query(
        "SELECT * FROM posts ORDER BY published_at DESC NULLS FIRST, id DESC"
    )
    return render_template("admin/blog.html", rows=rows)


@bp.get("/blog/new")
@bp.get("/blog/<int:pid>")
def blog_form(pid=None):
    row = None
    if pid:
        row = db.query("SELECT * FROM posts WHERE id = %s", (pid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/blog_form.html", row=row)


@bp.post("/blog/new")
@bp.post("/blog/<int:pid>")
def blog_save(pid=None):
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
    if pid:
        existing = db.query("SELECT * FROM posts WHERE id = %s", (pid,), one=True)
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

    body_md = f.get("body_md") or ""
    excerpt = (f.get("excerpt") or "").strip() or content.excerpt(body_md)
    is_pub = bool(f.get("is_published"))
    params = (
        title, slug, excerpt, body_md, content.render_md(body_md), cover, thumb,
        (f.get("meta_title") or "").strip() or None,
        (f.get("meta_description") or "").strip() or None,
        is_pub,
    )
    try:
        if pid:
            db.execute(
                """UPDATE posts SET title=%s, slug=%s, excerpt=%s, body_md=%s,
                   body_html=%s, cover_image=%s, cover_thumb=%s,
                   meta_title=%s, meta_description=%s, is_published=%s,
                   published_at = CASE WHEN %s AND published_at IS NULL
                                       THEN now() ELSE published_at END,
                   updated_at = now()
                   WHERE id=%s""",
                params + (is_pub, pid),
            )
        else:
            db.execute(
                """INSERT INTO posts
                   (title, slug, excerpt, body_md, body_html, cover_image, cover_thumb,
                    meta_title, meta_description, is_published, published_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           CASE WHEN %s THEN now() END)""",
                params + (is_pub,),
            )
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        flash(f'Slug "{slug}" is already in use.', "error")
        return redirect(request.path)
    flash("Post saved.", "success")
    return redirect(url_for("admin.blog_list"))


@bp.post("/blog/<int:pid>/delete")
def blog_delete(pid):
    row = db.query("SELECT * FROM posts WHERE id = %s", (pid,), one=True)
    if row:
        uploads.delete_upload(row["cover_image"])
        uploads.delete_upload(row["cover_thumb"])
        db.execute("DELETE FROM posts WHERE id = %s", (pid,))
    flash("Post deleted.", "success")
    return redirect(url_for("admin.blog_list"))
