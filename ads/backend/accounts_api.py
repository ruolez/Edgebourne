"""Ad accounts in one console (roadmap 7.1): which one a request works on, the list, adding one,
renaming, switching. Admins see every account; members and clients only their own."""
import re

from flask import Blueprint, jsonify, request, session

import account_ctx
import db
from auth import admin_required, current_user, login_required
from util import api_error, log_activity

bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


def active_accounts():
    return db.query("SELECT id, name, created_at FROM accounts WHERE archived_at IS NULL ORDER BY id")


def account_for(user):
    """The account a signed-in person works on: an admin's choice, everyone else's own."""
    if not user:
        return account_ctx.DEFAULT
    if user["role"] != "admin":
        return user.get("account_id") or account_ctx.DEFAULT
    try:
        wanted = int(request.cookies.get(COOKIE) or account_ctx.DEFAULT)
    except ValueError:
        wanted = account_ctx.DEFAULT
    return wanted if any(a["id"] == wanted for a in active_accounts()) else account_ctx.DEFAULT


def choose_for_request():
    """before_request: the Mac names its account in a header (checked against the key); a person's
    session decides for them; webhooks decide from the Page in the payload."""
    path = request.path
    m = re.match(r"^/api/agent/tasks/(\d+)", path)
    if m:
        # A task's calls run in the task's own account, whatever the Mac sends.
        with account_ctx.all_accounts():
            row = db.query("SELECT account_id FROM desk_tasks WHERE id = %s", (int(m.group(1)),), one=True)
        account_ctx.set_current(row["account_id"] if row else account_ctx.DEFAULT)
        return
    if path.startswith("/api/agent/"):
        try:
            account_ctx.set_current(int(request.headers.get("X-Account") or account_ctx.DEFAULT))
        except ValueError:
            account_ctx.set_current(account_ctx.DEFAULT)
        return
    if path.startswith("/api/") and session.get("user_id"):
        user = db.query("SELECT id, role, account_id FROM users WHERE id = %s AND is_active", (session["user_id"],), one=True)
        account_ctx.set_current(account_for(user))
        if user and user["role"] == "client" and request.method not in ("GET", "HEAD") and not CLIENT_MAY.match(path):
            return api_error("Your access is read-only. Ask Edge Bourne to make this change.", 403)


# The admin's chosen account lives in its own cookie, set only by switching: the session cookie is
# re-sent by every response, so a request that started before a switch could undo it. The value is
# only a choice; account_for() checks the person may use it (admins only, active accounts only).
COOKIE = "ebads_account"


def _with_choice(resp, account_id):
    import config
    resp.set_cookie(COOKIE, str(account_id), max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax",
                    secure=config.APP_BASE_URL.startswith("https://"))
    return resp


# What a client (read-only) may still do: sign out, their own password and notification settings.
CLIENT_MAY = re.compile(r"^/api/(auth/(logout|password|me)|me/push(/.*)?|accounts/switch)$")


def name_of(account_id):
    row = db.query("SELECT name FROM accounts WHERE id = %s", (account_id,), one=True)
    return row["name"] if row else ""


@bp.get("")
@login_required
def listing():
    user = current_user()
    current = account_ctx.current()
    items = active_accounts() if user["role"] == "admin" else [a for a in active_accounts() if a["id"] == current]
    return jsonify({"current": current, "items": [{"id": a["id"], "name": a["name"]} for a in items]})


@bp.post("")
@admin_required
def create():
    name = " ".join(str((request.get_json(silent=True) or {}).get("name") or "").split())[:120]
    if not name:
        return api_error("Give the account a name (the business it advertises)", 400, field="name")
    with account_ctx.all_accounts():
        new = db.execute("INSERT INTO accounts (name) VALUES (%s) RETURNING id", (name,), returning=True)["id"]
        # Claude's regular checks and the first-reply template, ready to use (schedules off).
        db.execute("""INSERT INTO desk_schedules (account_id, name, about, kind, prompt, rule, enabled, position)
                      SELECT %s, name, about, kind, prompt, rule, FALSE, position FROM desk_schedules WHERE account_id = 1""", (new,))
        db.execute("""INSERT INTO reply_templates (account_id, name, subject, body, position)
                      SELECT %s, name, subject, body, position FROM reply_templates WHERE account_id = 1 ORDER BY position LIMIT 1""", (new,))
    log_activity("account.created", subject=str(new), details={"name": name})
    return _with_choice(jsonify({"id": new, "name": name}), new), 201


@bp.patch("/<int:account_id>")
@admin_required
def rename(account_id):
    name = " ".join(str((request.get_json(silent=True) or {}).get("name") or "").split())[:120]
    if not name:
        return api_error("Give the account a name", 400, field="name")
    db.execute("UPDATE accounts SET name = %s WHERE id = %s", (name, account_id))
    return jsonify({"id": account_id, "name": name})


@bp.post("/switch")
@admin_required
def switch():
    wanted = (request.get_json(silent=True) or {}).get("id")
    if not any(a["id"] == wanted for a in active_accounts()):
        return api_error("No such account", 404)
    return _with_choice(jsonify({"current": wanted, "name": name_of(wanted)}), wanted)
