"""Teammates and which campaigns each one works on."""
import secrets

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

import db
from auth import admin_required
from util import api_error, log_activity

bp = Blueprint("team", __name__, url_prefix="/api/team")


def _members():
    users = db.query(
        "SELECT id, email, name, role, is_active, notify_new_leads, last_login_at, created_at "
        "FROM users ORDER BY is_active DESC, role, name"
    )
    links = db.query("SELECT campaign_id, user_id FROM campaign_members")
    by_user = {}
    for link in links:
        by_user.setdefault(link["user_id"], []).append(link["campaign_id"])
    for u in users:
        u["campaign_ids"] = by_user.get(u["id"], [])
    return users


@bp.get("")
@admin_required
def list_team():
    campaigns = db.query(
        "SELECT id, name, effective_status FROM campaigns ORDER BY name"
    )
    return jsonify({"members": _members(), "campaigns": campaigns})


@bp.post("")
@admin_required
def invite():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    role = data.get("role") if data.get("role") in ("admin", "member") else "member"
    if "@" not in email:
        return api_error("Enter the teammate's email address", 400, field="email")
    if not name:
        return api_error("Enter the teammate's name", 400, field="name")
    if db.query("SELECT 1 FROM users WHERE email = %s", (email,), one=True):
        return api_error("Someone with that email is already on the team", 409, field="email")
    temp = secrets.token_urlsafe(9)
    row = db.execute(
        """INSERT INTO users (email, name, password_hash, role, must_change_password)
           VALUES (%s, %s, %s, %s, TRUE) RETURNING id""",
        (email, name, generate_password_hash(temp), role), returning=True,
    )
    _set_campaigns(row["id"], data.get("campaign_ids") or [])
    log_activity("team.added", subject=email, details={"role": role})
    # The temporary password is shown once to the admin, who passes it on.
    return jsonify({"id": row["id"], "temporary_password": temp}), 201


def _set_campaigns(user_id, campaign_ids):
    known = {r["id"] for r in db.query("SELECT id FROM campaigns")}
    wanted = [c for c in dict.fromkeys(str(c) for c in campaign_ids) if c in known]
    db.execute("DELETE FROM campaign_members WHERE user_id = %s", (user_id,))
    for cid in wanted:
        db.execute("INSERT INTO campaign_members (campaign_id, user_id) VALUES (%s, %s)",
                   (cid, user_id))
    return wanted


@bp.patch("/<int:user_id>")
@admin_required
def update(user_id):
    data = request.get_json(silent=True) or {}
    user = db.query("SELECT * FROM users WHERE id = %s", (user_id,), one=True)
    if not user:
        return api_error("That teammate no longer exists", 404)
    changes = {}
    if "role" in data and data["role"] in ("admin", "member"):
        if user_id == session["user_id"] and data["role"] != "admin":
            return api_error("You can't remove your own admin access", 400)
        db.execute("UPDATE users SET role = %s WHERE id = %s", (data["role"], user_id))
        changes["role"] = data["role"]
    if "is_active" in data:
        if user_id == session["user_id"] and not data["is_active"]:
            return api_error("You can't deactivate yourself", 400)
        db.execute("UPDATE users SET is_active = %s WHERE id = %s", (bool(data["is_active"]), user_id))
        changes["is_active"] = bool(data["is_active"])
    if "campaign_ids" in data:
        changes["campaign_ids"] = _set_campaigns(user_id, data["campaign_ids"] or [])
    if data.get("reset_password"):
        temp = secrets.token_urlsafe(9)
        db.execute(
            "UPDATE users SET password_hash = %s, must_change_password = TRUE WHERE id = %s",
            (generate_password_hash(temp), user_id),
        )
        log_activity("team.password_reset", subject=user["email"])
        return jsonify({"temporary_password": temp})
    log_activity("team.updated", subject=user["email"], details=changes)
    return jsonify({"ok": True})
