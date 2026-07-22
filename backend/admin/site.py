from flask import flash, redirect, render_template, request, url_for

import content
import db

from . import bp

FIELDS = [
    "site_title",
    "hero_eyebrow_strong", "hero_eyebrow",
    "hero_title", "hero_title_accent", "hero_sub",
    "hero_cta_primary", "hero_cta_primary_url",
    "hero_cta_secondary", "hero_cta_secondary_url",
    "seo_default_title", "seo_default_description",
    "contact_email", "phone", "social_linkedin", "social_github",
]


@bp.get("/site")
def site():
    values = {k: db.get_setting(k, "") for k in FIELDS}
    values["about_md"] = db.get_setting("about_md", "")
    return render_template("admin/site.html", v=values)


@bp.post("/site")
def site_save():
    for key in FIELDS:
        db.set_setting(key, (request.form.get(key) or "").strip())
    about_md = request.form.get("about_md") or ""
    db.set_setting("about_md", about_md)
    db.set_setting("about_html", content.render_md(about_md))
    flash("Site content saved.", "success")
    return redirect(url_for("admin.site"))
