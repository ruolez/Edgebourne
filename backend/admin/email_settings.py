from flask import flash, jsonify, redirect, render_template, request, url_for

import db
import mailer

from . import bp

import secrets_store

MASK = secrets_store.MASK
FIELDS = ["smtp_host", "smtp_port", "smtp_user", "smtp_from", "smtp_tls", "notify_email"]


@bp.get("/email")
def email():
    values = {k: db.get_setting(k, "") for k in FIELDS}
    values["smtp_password"] = MASK if secrets_store.is_set("smtp_password") else ""
    return render_template("admin/email.html", v=values)


@bp.post("/email")
def email_save():
    for key in FIELDS:
        db.set_setting(key, (request.form.get(key) or "").strip())
    # Encrypted at rest, so a database backup does not hand over the mailbox.
    secrets_store.save_masked("smtp_password", request.form.get("smtp_password"))
    flash("Email settings saved.", "success")
    return redirect(url_for("admin.email"))


@bp.post("/email/test")
def email_test():
    s = mailer.smtp_settings()
    if not mailer.is_configured(s):
        return jsonify({"ok": False, "error": "SMTP host and From address are required."})
    to = mailer.notify_to(s)
    if not to:
        return jsonify({"ok": False, "error": "Set a notification or contact email first."})
    try:
        mailer.send(
            s,
            f"[{s.get('site_title') or 'EdgeBourne'}] Test email",
            "SMTP is configured correctly — lead notifications will arrive at this address.",
            to,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"})
    return jsonify({"ok": True, "to": to})
