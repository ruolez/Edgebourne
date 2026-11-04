import json

from flask import flash, redirect, render_template, request, url_for

import content
import db
import hero_image

from . import bp

FIELDS = [
    "site_title",
    "hero_eyebrow_strong", "hero_eyebrow",
    "hero_title", "hero_title_accent", "hero_sub",
    "hero_cta_primary", "hero_cta_primary_url",
    "hero_cta_secondary", "hero_cta_secondary_url",
    "hero_cta_note", "hero_image_alt", "hero_case_slug",
    "seo_default_title", "seo_default_description",
    "contact_email", "phone", "social_linkedin", "social_github",
    # Shown on /process and /contact. Blank hides the pricing figure entirely
    # rather than printing an empty box, so it is safe to leave unset.
    "onboarding_fee", "onboarding_fee_note",
]


@bp.get("/site")
def site():
    values = {k: db.get_setting(k, "") for k in FIELDS}
    values["about_md"] = db.get_setting("about_md", "")
    cases = db.query(
        "SELECT slug, title FROM case_studies WHERE is_published ORDER BY sort_order, id"
    )
    return render_template(
        "admin/site.html",
        v=values,
        cases=cases,
        hero=hero_image.load(db.get_setting("hero_image", "")),
        focus_options=hero_image.FOCUS,
    )


@bp.post("/site")
def site_save():
    for key in FIELDS:
        db.set_setting(key, (request.form.get(key) or "").strip())
    about_md = request.form.get("about_md") or ""
    db.set_setting("about_md", about_md)
    db.set_setting("about_html", content.render_md(about_md))
    _save_hero_image()
    flash("Site content saved.", "success")
    return redirect(url_for("admin.site"))


def _save_hero_image():
    """Upload, recrop or remove the hero photo. A failed upload is reported
    and leaves the current photo in place; the text fields still save."""
    current = hero_image.load(db.get_setting("hero_image", ""))
    focus = request.form.get("hero_image_focus") or "center"
    upload = request.files.get("hero_image_file")

    if request.form.get("hero_image_remove"):
        hero_image.delete_cut(current, keep_master=False)
        db.set_setting("hero_image", "")
        return

    if upload and upload.filename:
        try:
            master, warning = hero_image.save_master(upload)
        except ValueError as e:
            flash(f"Hero image not changed: {e}", "error")
            return
        info = hero_image.cut(master, focus)
        hero_image.delete_cut(current, keep_master=False)
        db.set_setting("hero_image", json.dumps(info))
        if warning:
            flash(warning, "error")
        return

    if current and focus != current.get("focus"):
        try:
            info = hero_image.cut(current["master"], focus)
        except OSError:
            flash("The original upload is missing, so the photo can't be re-cropped. "
                  "Upload it again.", "error")
            return
        hero_image.delete_cut(current)
        db.set_setting("hero_image", json.dumps(info))
