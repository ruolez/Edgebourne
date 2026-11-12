"""Ad accounts in one console (roadmap 7.1): which one a request works on, the list, adding one,
renaming, switching. Admins see every account; members and clients only their own."""
import re

from flask import Blueprint, jsonify, request, session

import account_ctx
import db
import settings_store
from auth import current_user, is_owner, login_required, owner_required
from util import api_error, log_activity

bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


def active_accounts():
    return db.query("SELECT id, name, created_at FROM accounts WHERE archived_at IS NULL ORDER BY id")


def closed(account_id):
    """True when the account was archived (its people lose access, its share links stop)."""
    if not account_id:
        return False
    with account_ctx.all_accounts():
        row = db.query("SELECT archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
    return not row or row["archived_at"] is not None


def clients_update_leads(account_id=None):
    """Settings → Client access: the account's clients may move leads through stages and add notes."""
    return settings_store.get("client_lead_updates", account_id=account_id) == "on"


def account_for(user):
    """The account a signed-in person works on: the owner's choice, everyone else's own.
    None when that account was closed."""
    if not user:
        return account_ctx.DEFAULT
    if not is_owner(user):
        own = user.get("account_id") or account_ctx.DEFAULT
        return None if closed(own) else own
    try:
        wanted = int(request.cookies.get(COOKIE) or account_ctx.DEFAULT)
    except ValueError:
        wanted = account_ctx.DEFAULT
    return wanted if any(a["id"] == wanted for a in active_accounts()) else account_ctx.DEFAULT


def choose_for_request():
    """before_request: the Mac names its account in a header (checked against the key); a person's
    session decides for them; webhooks decide from the Page in the payload."""
    path = request.path
    account_ctx.set_current(account_ctx.DEFAULT)  # gunicorn reuses threads: never inherit the last request's
    if (path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
            and not path.startswith("/api/agent/") and not _from_the_console()):
        return api_error("This request didn't come from the console", 403)
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
        acct = account_for(user)
        if acct is None:
            if path == "/api/auth/logout":
                return None
            return api_error("This account was closed. Ask Edge Bourne if you need access again.", 403)
        account_ctx.set_current(acct)
        if user and user["role"] == "client" and request.method not in ("GET", "HEAD") and not CLIENT_MAY.match(path):
            if clients_update_leads(acct) and CLIENT_LEADS.match(path):
                return None
            return api_error("Your access is read-only. Ask Edge Bourne to make this change.", 403)


def _from_the_console():
    """Cross-site CSRF guard: a form on another site can't send JSON or custom headers without a
    CORS preflight, which this server never answers. The console's own requests always carry one."""
    return (request.headers.get("X-Requested-With") == "ebads"
            or (request.mimetype or "") == "application/json")


# The admin's chosen account lives in its own cookie, set only by switching: the session cookie is
# re-sent by every response, so a request that started before a switch could undo it. The value is
# only a choice; account_for() checks the person may use it (admins only, active accounts only).
COOKIE = "ebads_account"


def _with_choice(resp, account_id):
    import config
    resp.set_cookie(COOKIE, str(account_id), max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax",
                    secure=config.APP_BASE_URL.startswith("https://"))
    return resp


# What a client (read-only) may still do: sign out, their own password and notification settings,
# and their own Inbox read marks and saved views (both are rows of that person only).
CLIENT_MAY = re.compile(r"^/api/(auth/(logout|password|me)|me/(push|telegram)(/[a-z0-9]+)?|inbox/read|views(/\d+)?)$")
# With Settings → Client access on: moving a lead's stage and adding notes.
CLIENT_LEADS = re.compile(r"^/api/leads/\d+(/notes)?$")


def name_of(account_id):
    row = db.query("SELECT name FROM accounts WHERE id = %s", (account_id,), one=True)
    return row["name"] if row else ""


@bp.get("")
@login_required
def listing():
    user = current_user()
    current = account_ctx.current()
    items = active_accounts() if is_owner(user) else [a for a in active_accounts() if a["id"] == current]
    return jsonify({"current": current, "items": [{"id": a["id"], "name": a["name"]} for a in items]})


@bp.post("")
@owner_required
def create():
    name = " ".join(str((request.get_json(silent=True) or {}).get("name") or "").split())[:120]
    if not name:
        return api_error("Give the account a name (the business it advertises)", 400, field="name")
    if name_taken(name):
        return api_error("Another account already has that name", 409, field="name")
    with account_ctx.all_accounts():
        new = db.execute("INSERT INTO accounts (name) VALUES (%s) RETURNING id", (name,), returning=True)["id"]
        # Claude's regular checks and the first-reply template, ready to use (schedules off).
        db.execute("""INSERT INTO desk_schedules (account_id, name, about, kind, prompt, rule, enabled, position)
                      SELECT %s, name, about, kind, prompt, rule, FALSE, position FROM desk_schedules WHERE account_id = 1""", (new,))
        # The first-reply template, with this business's name instead of Edge Bourne's (check the wording).
        db.execute("""INSERT INTO reply_templates (account_id, name, subject, body, position)
                      SELECT %s, name, replace(subject, 'Edge Bourne', %s), replace(body, 'Edge Bourne', %s), position
                      FROM reply_templates WHERE account_id = 1 ORDER BY position LIMIT 1""", (new, name, name))
    log_activity("account.created", subject=str(new), details={"name": name})
    return _with_choice(jsonify({"id": new, "name": name}), new), 201


@bp.patch("/<int:account_id>")
@owner_required
def rename(account_id):
    """Rename, or close (archived: its people lose access, its share links stop, the worker skips it)."""
    data = request.get_json(silent=True) or {}
    with account_ctx.all_accounts():
        row = db.query("SELECT id, name, archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
        if not row:
            return api_error("No such account", 404)
        if "archived" in data:
            if account_id == account_ctx.DEFAULT:
                return api_error("Edge Bourne's own account can't be closed", 400)
            db.execute("UPDATE accounts SET archived_at = CASE WHEN %s THEN COALESCE(archived_at, now()) END WHERE id = %s",
                       (bool(data["archived"]), account_id))
            log_activity("account.archived" if data["archived"] else "account.reopened", subject=str(account_id))
        if "name" in data:
            name = " ".join(str(data.get("name") or "").split())[:120]
            if not name:
                return api_error("Give the account a name", 400, field="name")
            if name_taken(name, account_id):
                return api_error("Another account already has that name", 409, field="name")
            db.execute("UPDATE accounts SET name = %s WHERE id = %s", (name, account_id))
            log_activity("account.renamed", subject=str(account_id), details={"name": name})
        row = db.query("SELECT id, name, archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
    return jsonify({"id": row["id"], "name": row["name"], "archived": row["archived_at"] is not None})


def name_taken(name, except_id=None):
    with account_ctx.all_accounts():
        return db.query("SELECT 1 FROM accounts WHERE lower(name) = lower(%s) AND archived_at IS NULL AND id <> %s",
                        (name, except_id or 0), one=True) is not None


@bp.get("/all")
@owner_required
def all_accounts_listing():
    """Settings → Accounts: every account with its state, closed ones included."""
    with account_ctx.all_accounts():
        rows = db.query("SELECT id, name, created_at, archived_at FROM accounts ORDER BY archived_at IS NOT NULL, id")
    return jsonify({"items": [{"id": r["id"], "name": r["name"], "archived": r["archived_at"] is not None} for r in rows]})


@bp.post("/switch")
@owner_required
def switch():
    wanted = (request.get_json(silent=True) or {}).get("id")
    if not any(a["id"] == wanted for a in active_accounts()):
        return api_error("No such account", 404)
    return _with_choice(jsonify({"current": wanted, "name": name_of(wanted)}), wanted)
