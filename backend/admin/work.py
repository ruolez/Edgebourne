import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for
from psycopg2.extras import Json

import content
import db
import uploads

from . import bp
from .services import move_row

METRIC_ROWS = 4
GALLERY_BLANK_ROWS = 3


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
    gallery = list(row["gallery"]) if row else []
    return render_template(
        "admin/work_form.html",
        row=row,
        metric_rows=_pad(row["metrics"] if row else [], METRIC_ROWS),
        gallery_rows=gallery + [{}] * GALLERY_BLANK_ROWS,
    )


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

    try:
        gallery = _gallery(f, request.files)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(request.path)
    if existing:
        _prune_gallery_uploads(existing["gallery"], gallery)

    tags = _csv(f.get("tech_tags"))
    stack = _csv(f.get("stack"))
    body_md = f.get("body_md") or ""
    is_pub = bool(f.get("is_published"))
    params = (
        title, slug, (f.get("client") or "").strip(), (f.get("summary") or "").strip(),
        body_md, content.render_md(body_md), cover, thumb, tags,
        (f.get("industry") or "").strip(), (f.get("engagement") or "").strip(),
        (f.get("problem_lede") or "").strip(),
        Json(_metrics(f)), Json(gallery), stack, bool(f.get("is_featured")),
        (f.get("meta_title") or "").strip() or None,
        (f.get("meta_description") or "").strip() or None,
        is_pub,
    )
    try:
        if wid:
            db.execute(
                """UPDATE case_studies SET title=%s, slug=%s, client=%s, summary=%s,
                   body_md=%s, body_html=%s, cover_image=%s, cover_thumb=%s,
                   tech_tags=%s, industry=%s, engagement=%s, problem_lede=%s,
                   metrics=%s, gallery=%s, stack=%s, is_featured=%s,
                   meta_title=%s, meta_description=%s, is_published=%s,
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
                    cover_thumb, tech_tags, industry, engagement, problem_lede,
                    metrics, gallery, stack, is_featured,
                    meta_title, meta_description, is_published,
                    published_at, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
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
        _prune_gallery_uploads(row["gallery"], [])
        db.execute("DELETE FROM case_studies WHERE id = %s", (wid,))
    flash("Case study deleted.", "success")
    return redirect(url_for("admin.work_list"))


@bp.post("/work/<int:wid>/move")
def work_move(wid):
    move_row("case_studies", wid, request.form.get("dir"))
    return redirect(url_for("admin.work_list"))


def _csv(raw):
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


def _pad(items, count):
    """Grow a JSONB list to a fixed number of form rows. The editor renders a
    constant row count so every field has a stable index and needs no JS."""
    rows = list(items or [])[:count]
    return rows + [{}] * (count - len(rows))


def _metrics(f):
    """Parallel metric_value/metric_label fields -> [{"value","label"}].
    Rows with neither half filled in are dropped."""
    labels = f.getlist("metric_label")
    out = []
    for i, value in enumerate(f.getlist("metric_value")):
        value = value.strip()[:24]
        label = (labels[i].strip() if i < len(labels) else "")[:80]
        if value or label:
            out.append({"value": value, "label": label})
    return out[:METRIC_ROWS]


def _gallery(f, files):
    """Parallel gallery_src/gallery_thumb/gallery_caption fields, plus an
    optional per-row upload, -> [{"src","thumb","caption"}].

    Portfolio images are committed static files, so the path field is the
    primary input; the upload is the escape hatch for a one-off image.
    Clearing a row's src drops that image. Raises ValueError on a bad path."""
    thumbs = f.getlist("gallery_thumb")
    captions = f.getlist("gallery_caption")
    out = []
    for i, src in enumerate(f.getlist("gallery_src")):
        src = _media_path(src)
        thumb = _media_path(thumbs[i] if i < len(thumbs) else "")
        upload = files.get(f"gallery_file_{i}")
        if upload and upload.filename:
            src, thumb = uploads.save_image(upload)
        if not src:
            continue
        caption = (captions[i].strip() if i < len(captions) else "")[:200]
        out.append({"src": src, "thumb": thumb or src, "caption": caption})
    return out


def _media_path(raw):
    """A gallery path is written straight into an <img src>, so it must be a
    site-relative URL -- never javascript:, data: or an off-site host."""
    path = (raw or "").strip()
    if not path:
        return ""
    if not path.startswith("/") or path.startswith("//") or ".." in path:
        raise ValueError(
            f'Image path "{path}" must be a site path, '
            "e.g. /static/media/work/my-slug/01-screen.webp"
        )
    return path


def _prune_gallery_uploads(old, new):
    """Delete uploaded files dropped from the gallery. delete_upload ignores
    anything outside /uploads/, so committed /static paths are left alone."""
    keep = {i.get("src") for i in new} | {i.get("thumb") for i in new}
    for item in old or []:
        for path in (item.get("src"), item.get("thumb")):
            if path and path not in keep:
                uploads.delete_upload(path)
