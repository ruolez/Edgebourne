from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import db
from util import api_error, log_activity

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

MIN_PASSWORD = 10


def current_user():
    """The signed-in, still-active user, read fresh so deactivation and role
    changes take effect on the next request."""
    uid = session.get("user_id")
    if not uid:
        return None
    user = db.query(
        "SELECT id, email, name, role, must_change_password, notify_new_leads, notify_reminders, notify_alerts FROM users "
        "WHERE id = %s AND is_active",
        (uid,), one=True,
    )
    if not user:
        session.clear()
    return user


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return api_error("Sign in to continue", 401)
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return api_error("Sign in to continue", 401)
        if user["role"] != "admin":
            return api_error("Only admins can do this", 403)
        return f(*args, **kwargs)
    return wrapper


def visible_campaign_ids(user):
    """None means every campaign (admins); otherwise the assigned ones."""
    if user["role"] == "admin":
        return None
    rows = db.query("SELECT campaign_id FROM campaign_members WHERE user_id = %s", (user["id"],))
    return [r["campaign_id"] for r in rows]


def _public(user):
    return {k: user[k] for k in ("id", "email", "name", "role", "must_change_password",
                                 "notify_new_leads", "notify_reminders", "notify_alerts")}


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = db.query("SELECT * FROM users WHERE email = %s AND is_active", (email,), one=True)
    if not user or not check_password_hash(user["password_hash"], password):
        return api_error("That email and password don't match", 401)
    session.clear()
    session.permanent = bool(data.get("remember", True))
    session["user_id"] = user["id"]
    db.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    log_activity("auth.sign_in", user_id=user["id"])
    return jsonify(_public(user))


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
@login_required
def me():
    return jsonify(_public(current_user()))


@bp.post("/password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    user = db.query("SELECT * FROM users WHERE id = %s", (session["user_id"],), one=True)
    if not check_password_hash(user["password_hash"], data.get("current") or ""):
        return api_error("Your current password is not right", 400, field="current")
    new = data.get("new") or ""
    if len(new) < MIN_PASSWORD:
        return api_error(f"Use at least {MIN_PASSWORD} characters", 400, field="new")
    db.execute(
        "UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
        (generate_password_hash(new), user["id"]),
    )
    log_activity("auth.password_changed")
    return jsonify({"ok": True})


@bp.patch("/me")
@login_required
def update_me():
    data = request.get_json(silent=True) or {}
    user = current_user()
    if "notify_new_leads" in data:
        db.execute("UPDATE users SET notify_new_leads = %s WHERE id = %s",
                   (bool(data["notify_new_leads"]), user["id"]))
    if "notify_alerts" in data:
        db.execute("UPDATE users SET notify_alerts = %s WHERE id = %s", (bool(data["notify_alerts"]), user["id"]))
    if "notify_reminders" in data:
        db.execute("UPDATE users SET notify_reminders = %s WHERE id = %s",
                   (bool(data["notify_reminders"]), user["id"]))
    if "name" in data and (data["name"] or "").strip():
        db.execute("UPDATE users SET name = %s WHERE id = %s", (data["name"].strip(), user["id"]))
    return jsonify(_public(current_user()))
