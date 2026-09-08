from flask import abort, flash, redirect, render_template, request, url_for

import db

from . import bp
from .services import move_row


@bp.get("/testimonials")
def testimonials_list():
    rows = db.query("SELECT * FROM testimonials ORDER BY sort_order, id")
    return render_template("admin/testimonials.html", rows=rows)


@bp.get("/testimonials/new")
@bp.get("/testimonials/<int:tid>")
def testimonial_form(tid=None):
    row = None
    if tid:
        row = db.query("SELECT * FROM testimonials WHERE id = %s", (tid,), one=True)
        if not row:
            abort(404)
    return render_template(
        "admin/testimonial_form.html", row=row, case_studies=_case_study_options()
    )


@bp.post("/testimonials/new")
@bp.post("/testimonials/<int:tid>")
def testimonial_save(tid=None):
    f = request.form
    quote = (f.get("quote") or "").strip()
    if not quote:
        flash("A quote is required.", "error")
        return redirect(request.path)
    slug = (f.get("case_study_slug") or "").strip()
    if slug and slug not in {s for s, _ in _case_study_options()}:
        flash("That case study no longer exists.", "error")
        return redirect(request.path)
    params = (
        quote, (f.get("author_role") or "").strip(), (f.get("industry") or "").strip(),
        slug, bool(f.get("is_approved")),
    )
    if tid:
        if not db.query("SELECT id FROM testimonials WHERE id = %s", (tid,), one=True):
            abort(404)
        db.execute(
            """UPDATE testimonials SET quote=%s, author_role=%s, industry=%s,
               case_study_slug=%s, is_approved=%s WHERE id=%s""",
            params + (tid,),
        )
    else:
        nxt = db.query(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM testimonials", one=True
        )["n"]
        db.execute(
            """INSERT INTO testimonials
               (quote, author_role, industry, case_study_slug, is_approved, sort_order)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            params + (nxt,),
        )
    flash("Testimonial saved.", "success")
    return redirect(url_for("admin.testimonials_list"))


@bp.post("/testimonials/<int:tid>/delete")
def testimonial_delete(tid):
    db.execute("DELETE FROM testimonials WHERE id = %s", (tid,))
    flash("Testimonial deleted.", "success")
    return redirect(url_for("admin.testimonials_list"))


@bp.post("/testimonials/<int:tid>/move")
def testimonial_move(tid):
    move_row("testimonials", tid, request.form.get("dir"))
    return redirect(url_for("admin.testimonials_list"))


def _case_study_options():
    rows = db.query("SELECT slug, title FROM case_studies ORDER BY sort_order, id")
    return [(r["slug"], r["title"]) for r in rows]
