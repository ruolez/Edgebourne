"""Teammates and which campaigns each one works on."""
import secrets

from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

import account_ctx
import db
from auth import admin_required, bump_sessions, current_user, is_owner
from util import api_error, log_activity

bp = Blueprint("team", __name__, url_prefix="/api/team")


ROLES = ("admin", "account_admin", "member", "client")  # account_admin = an admin of this account only


def _role_of(u):
    return "account_admin" if u["role"] == "admin" and u.get("account_id") else u["role"]


def _members():
    users = db.query(
        "SELECT id, email, name, role, account_id, is_active, notify_new_leads, last_login_at, created_at "
        "FROM users WHERE (role = 'admin' AND account_id IS NULL) OR account_id = %s ORDER BY is_active DESC, role, name",
        (account_ctx.current(),)
    )
    links = db.query("SELECT campaign_id, user_id FROM campaign_members")
    by_user = {}
    for link in links:
        by_user.setdefault(link["user_id"], []).append(link["campaign_id"])
    for u in users:
        u["campaign_ids"] = by_user.get(u["id"], [])
        u["access"] = _role_of(u)
    return users


def _may_edit(editor, target):
    """Who may change whom: the owner anyone; an account admin only people of their own account."""
    if is_owner(editor):
        return target.get("account_id") in (None, account_ctx.current())
    return target.get("account_id") == account_ctx.current()


def _store_role(access):
    """(users.role, users.account_id) for an access level picked on the Team page."""
    if access == "admin":
        return "admin", None
    return ("admin" if access == "account_admin" else access), account_ctx.current()


@bp.get("")
@admin_required
def list_team():
    campaigns = db.query(
        "SELECT id, name, effective_status FROM campaigns ORDER BY name"
    )
    return jsonify({"members": _members(), "campaigns": campaigns, "owner": is_owner(current_user())})


@bp.post("")
@admin_required
def invite():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    access = data.get("role") if data.get("role") in ROLES else "member"
    if access == "admin" and not is_owner(current_user()):
        return api_error("Only the console's owner can add an admin of every account", 403, field="role")
    role, account_id = _store_role(access)
    if "@" not in email:
        return api_error("Enter the teammate's email address", 400, field="email")
    if not name:
        return api_error("Enter the teammate's name", 400, field="name")
    if db.query("SELECT 1 FROM users WHERE email = %s", (email,), one=True):
        return api_error("Someone with that email is already on the team", 409, field="email")
    temp = secrets.token_urlsafe(9)
    row = db.execute(
        """INSERT INTO users (email, name, password_hash, role, must_change_password, account_id)
           VALUES (%s, %s, %s, %s, TRUE, %s) RETURNING id""",
        (email, name, generate_password_hash(temp), role, account_id), returning=True,
    )
    _set_campaigns(row["id"], data.get("campaign_ids") or [])
    log_activity("team.added", subject=email, details={"role": access})
    # The temporary password is shown once to the admin, who passes it on.
    return jsonify({"id": row["id"], "temporary_password": temp}), 201


def _set_campaigns(user_id, campaign_ids):
    # Row-level security keeps both the campaigns and the assignments to the current account, so
    # this only replaces the person's assignments here, never another account's.
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
    editor = current_user()
    if not _may_edit(editor, user):
        return api_error("This person belongs to another account (or is the console's owner)", 403)
    changes = {}
    if "role" in data and data["role"] in ROLES and data["role"] != _role_of(user):
        if user_id == session["user_id"]:
            return api_error("You can't change your own access", 400)
        if data["role"] == "admin" and not is_owner(editor):
            return api_error("Only the console's owner can make someone an admin of every account", 403)
        role, account_id = _store_role(data["role"])
        db.execute("UPDATE users SET role = %s, account_id = %s, session_version = session_version + 1 WHERE id = %s",
                   (role, account_id, user_id))
        changes["role"] = data["role"]
    if "is_active" in data:
        if user_id == session["user_id"] and not data["is_active"]:
            return api_error("You can't deactivate yourself", 400)
        db.execute("UPDATE users SET is_active = %s WHERE id = %s", (bool(data["is_active"]), user_id))
        bump_sessions(user_id)
        changes["is_active"] = bool(data["is_active"])
    if "campaign_ids" in data:
        changes["campaign_ids"] = _set_campaigns(user_id, data["campaign_ids"] or [])
    if data.get("reset_password"):
        temp = secrets.token_urlsafe(9)
        db.execute(
            "UPDATE users SET password_hash = %s, must_change_password = TRUE, session_version = session_version + 1 WHERE id = %s",
            (generate_password_hash(temp), user_id),
        )
        log_activity("team.password_reset", subject=user["email"])
        return jsonify({"temporary_password": temp})
    log_activity("team.updated", subject=user["email"], details=changes)
    return jsonify({"ok": True})
