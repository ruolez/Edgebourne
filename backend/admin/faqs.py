from flask import abort, flash, redirect, render_template, request, url_for

import content
import db

from . import bp
from .services import move_row


@bp.get("/faqs")
def faqs_list():
    rows = db.query("SELECT * FROM faqs ORDER BY sort_order, id")
    return render_template("admin/faqs.html", rows=rows)


@bp.get("/faqs/new")
@bp.get("/faqs/<int:fid>")
def faq_form(fid=None):
    row = None
    if fid:
        row = db.query("SELECT * FROM faqs WHERE id = %s", (fid,), one=True)
        if not row:
            abort(404)
    return render_template("admin/faq_form.html", row=row)


@bp.post("/faqs/new")
@bp.post("/faqs/<int:fid>")
def faq_save(fid=None):
    f = request.form
    question = (f.get("question") or "").strip()
    if not question:
        flash("A question is required.", "error")
        return redirect(request.path)
    answer_md = f.get("answer_md") or ""
    params = (
        question, answer_md, content.render_md(answer_md), bool(f.get("is_published")),
    )
    if fid:
        if not db.query("SELECT id FROM faqs WHERE id = %s", (fid,), one=True):
            abort(404)
        db.execute(
            """UPDATE faqs SET question=%s, answer_md=%s, answer_html=%s,
               is_published=%s WHERE id=%s""",
            params + (fid,),
        )
    else:
        nxt = db.query(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM faqs", one=True
        )["n"]
        db.execute(
            """INSERT INTO faqs
               (question, answer_md, answer_html, is_published, sort_order)
               VALUES (%s, %s, %s, %s, %s)""",
            params + (nxt,),
        )
    flash("FAQ saved.", "success")
    return redirect(url_for("admin.faqs_list"))


@bp.post("/faqs/<int:fid>/delete")
def faq_delete(fid):
    db.execute("DELETE FROM faqs WHERE id = %s", (fid,))
    flash("FAQ deleted.", "success")
    return redirect(url_for("admin.faqs_list"))


@bp.post("/faqs/<int:fid>/move")
def faq_move(fid):
    move_row("faqs", fid, request.form.get("dir"))
    return redirect(url_for("admin.faqs_list"))
