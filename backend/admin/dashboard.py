from flask import render_template

import db

from . import bp


@bp.get("")
@bp.get("/")
def dashboard():
    stats = db.query(
        """SELECT
             (SELECT COUNT(*) FROM leads WHERE NOT is_read) AS unread,
             (SELECT COUNT(*) FROM leads) AS leads,
             (SELECT COUNT(*) FROM services WHERE is_published) AS services,
             (SELECT COUNT(*) FROM case_studies WHERE is_published) AS work,
             (SELECT COUNT(*) FROM posts WHERE is_published) AS posts,
             (SELECT COUNT(*) FROM pages WHERE is_published) AS pages""",
        one=True,
    )
    recent = db.query("SELECT * FROM leads ORDER BY created_at DESC LIMIT 10")
    return render_template("admin/dashboard.html", stats=stats, recent=recent)
