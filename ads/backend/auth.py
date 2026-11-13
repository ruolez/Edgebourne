import hashlib
import secrets
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import db
from util import api_error, log_activity

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

MIN_PASSWORD = 10
# Checked when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = generate_password_hash("not-a-real-password-0000")


# A sign-in lives in user_sessions; the cookie carries its key. Unused for longer than the cookie lasts: gone.
SESSION_IDLE = "31 days"


def _key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_session_key(user_id):
    """Start a sign-in: the key goes in the cookie, its hash in user_sessions (signing out deletes it)."""
    key = secrets.token_urlsafe(32)
    db.execute("INSERT INTO user_sessions (key_hash, user_id) VALUES (%s, %s)", (_key_hash(key), user_id))
    return key


def current_user():
    """The signed-in, still-active user, read fresh so deactivation and role
    changes take effect on the next request."""
    uid = session.get("user_id")
    if not uid:
        return None
    key = session.get("sk")
    user = db.query(
        "SELECT u.id, u.email, u.name, u.role, u.account_id, u.must_change_password, u.notify_new_leads, u.notify_reminders, "
        "u.notify_alerts, u.session_version, u.is_active, u.full_access_allowed, s.full_until, "
        "s.seen_at < now() - interval '1 hour' AS seen_long_ago "
        "FROM users u JOIN user_sessions s ON s.user_id = u.id AND s.key_hash = %s "
        f"WHERE u.id = %s AND u.is_active AND s.seen_at > now() - interval '{SESSION_IDLE}'",
        (_key_hash(key), uid), one=True,
    ) if key else None
    if user and session.get("sv", 0) != user["session_version"]:
        user = None  # the password changed (or an admin reset it) after this session signed in
        db.execute("DELETE FROM user_sessions WHERE key_hash = %s", (_key_hash(key),))
    if not user:
        session.clear()
        return None
    if user.pop("seen_long_ago"):
        db.execute("UPDATE user_sessions SET seen_at = now() WHERE key_hash = %s", (_key_hash(key),))
    return user


def session_key_hash():
    """This sign-in's user_sessions key (the cookie's key, hashed), or None."""
    key = session.get("sk")
    return _key_hash(key) if key else None


def end_full_access(user_id):
    """FU-D: every unlock of this person ends (password change or reset, deactivation, a role change)."""
    db.execute("UPDATE user_sessions SET full_until = NULL WHERE user_id = %s AND full_until IS NOT NULL", (user_id,))


def is_owner(user):
    """An admin of the whole console (every account). An admin tied to one account is not."""
    return bool(user) and user["role"] == "admin" and not user.get("account_id")


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


def owner_required(f):
    """Console-wide things: accounts, shared settings (Meta app, email), the Mac key, other admins."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return api_error("Sign in to continue", 401)
        if not is_owner(user):
            return api_error("Only the console's owner can change this (it applies to every account)", 403)
        return f(*args, **kwargs)
    return wrapper


def bump_sessions(user_id):
    """Sign the person out everywhere (their next request needs a fresh sign-in)."""
    db.execute("UPDATE users SET session_version = session_version + 1 WHERE id = %s", (user_id,))
    end_full_access(user_id)


def visible_campaign_ids(user):
    """None means every campaign of the current account (admins, and clients, who see their whole
    account read-only); otherwise the assigned ones. Row-level security limits it to one account."""
    if user["role"] in ("admin", "client"):
        return None
    rows = db.query("SELECT campaign_id FROM campaign_members WHERE user_id = %s", (user["id"],))
    return [r["campaign_id"] for r in rows]


def _public(user):
    return {k: user[k] for k in ("id", "email", "name", "role", "must_change_password",
                                 "notify_new_leads", "notify_reminders", "notify_alerts")}


def login_problems(email, password):
    """What's wrong with the sign-in form itself, field by field ([{field, message}]), before any account is
    looked at. A wrong email or password is never said apart: that answer names neither field."""
    email = (email or "").strip()
    problems = []
    if not email:
        problems.append({"field": "email", "message": "Type the email you sign in with."})
    else:
        name, at, domain = email.partition("@")
        # Lenient on purpose: anything a teammate was added with (team_api only asks for an @) can sign in.
        if not (name and at and domain and "@" not in domain and not any(c.isspace() for c in email)):
            problems.append({"field": "email", "message": "Check the email: it looks like name@example.com."})
    if not password:
        problems.append({"field": "password", "message": "Type your password."})
    return problems


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    problems = login_problems(email, password)
    if problems:
        return api_error(problems[0]["message"], 400, field=problems[0]["field"], errors=problems)
    user = db.query("SELECT * FROM users WHERE email = %s AND is_active", (email,), one=True)
    if not check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password) or not user:
        return api_error("That email and password don't match", 401)
    if user["role"] != "admin" or user.get("account_id"):
        import accounts_api
        if accounts_api.closed(user.get("account_id")):
            return api_error("This account was closed. Ask Edge Bourne if you need access again.", 403)
    db.execute(f"DELETE FROM user_sessions WHERE seen_at < now() - interval '{SESSION_IDLE}'")
    if session.get("sk"):  # signing in over an earlier sign-in ends that one, so an old copy of the cookie stops too
        db.execute("DELETE FROM user_sessions WHERE key_hash = %s", (_key_hash(session["sk"]),))
    session.clear()
    session.permanent = bool(data.get("remember", True))
    session["user_id"] = user["id"]
    session["sv"] = user["session_version"]
    session["sk"] = new_session_key(user["id"])
    db.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    log_activity("auth.sign_in", user_id=user["id"])
    return jsonify(_public(user))


@bp.post("/logout")
def logout():
    """Ends this sign-in on the server too, so a copy of the cookie stops working."""
    if session.get("sk"):
        db.execute("DELETE FROM user_sessions WHERE key_hash = %s", (_key_hash(session["sk"]),))
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
@login_required
def me():
    import account_ctx
    import accounts_api
    user = current_user()
    accounts = accounts_api.active_accounts() if is_owner(user) else []
    import account_info
    return jsonify({**_public(user), "owner": is_owner(user), **full_access_state(user),
                    "account": {"id": account_ctx.current(), "name": accounts_api.name_of(account_ctx.current()),
                                "currency": account_info.currency(), "tz": account_info.tz_name(),
                                "ad_account_id": __import__("settings_store").get("meta_ad_account_id"),
                                "connected": bool(__import__("settings_store").own("meta_ad_account_id"))
                                if account_ctx.current() != account_ctx.DEFAULT
                                else bool(__import__("settings_store").get("meta_ad_account_id")),
                                "clients_update_leads": accounts_api.clients_update_leads()},
                    "accounts": [{"id": a["id"], "name": a["name"]} for a in accounts],
                    **(_admin_warnings() if user["role"] == "admin" else {})})


def _admin_warnings():
    """What every admin page shows as a banner: a stopped worker, a token Meta refused, an old Mac helper."""
    import time
    import jobs
    import settings_store
    import desk_api
    out = {}
    if jobs.worker_expected() and jobs.worker_stale(settings_store.get("worker_last_pass"), time.time()):
        out["worker_stale"] = True
    import account_ctx
    token_error = settings_store.own("meta_token_error")
    if not token_error and settings_store.own("meta_system_token") is None:  # uses Edge Bourne's token
        token_error = settings_store.get("meta_token_error", account_id=account_ctx.DEFAULT)
    if token_error:
        out["meta_token_error"] = token_error
    if settings_store.get("bridge_claude_error"):
        out["claude_sign_in_failed"] = True
    old = desk_api.bridge_outdated()
    if old:
        out["bridge_outdated"] = old
    return out


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
        "UPDATE users SET password_hash = %s, must_change_password = FALSE, session_version = session_version + 1 "
        "WHERE id = %s",
        (generate_password_hash(new), user["id"]),
    )
    session["sv"] = user["session_version"] + 1  # this browser stays in; every other one signs in again
    end_full_access(user["id"])  # FU-D: full access needs the new password
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


# ---------------------------------------------------------------- FU-D: full access for the owner's own requests

def full_access_state(user):
    """What /me says: the flagged owner gets {allowed, on, until, home}; another owner {allowed: false}; anyone else
    nothing. `home` is the one account whose conversations can run with full access."""
    import accounts_api
    import full_access as fa
    if not is_owner(user):
        return {}
    if not fa.flagged_owner(user):
        return {"full_access": {"allowed": False}}
    until = user.get("full_until")
    on = fa.is_on(until, db.now())
    return {"full_access": {"allowed": True, "on": on, "until": until.isoformat() if on else None,
                            "home": {"id": fa.HOME_ACCOUNT, "name": accounts_api.name_of(fa.HOME_ACCOUNT)}}}


def _notify_unlocked(user, device, at):
    """A notice on every unlock, by email and push, so an unlock he didn't make doesn't go unseen."""
    import account_info
    import mailer
    import notify
    import push
    from words import clock
    title = "Full access to your Mac was turned on"
    lines = [f"Full access to your Mac was turned on from {device} at {clock(at.astimezone(account_info.tz()))}.",
             "Not you? Change your password in Your account: that signs out your other devices and ends full access."]
    stamp = int(at.timestamp())
    channels = (["email"] if mailer.configured() else []) + (["push"] if push.has_devices([user["id"]]) else [])
    for channel in channels:
        notify.queue(user["id"], channel, "security", title, lines, notify.link("/account.html"), "Your account",
                     dedupe_key=f"full-access:{user['id']}:{stamp}:{channel}")


@bp.post("/full-access")
@login_required
def full_access_on():
    """Turn on full access for this sign-in, after the password again. Only the console's first owner, never with a
    temporary password. Wrong tries are counted under a row lock on this sign-in, so tries sent at once still count
    one by one (security review)."""
    import full_access as fa
    import account_info
    from words import clock
    user = current_user()
    why = fa.may_unlock(user)
    if why:
        return api_error(why, 403)
    key = session_key_hash()
    password = (request.get_json(silent=True) or {}).get("password") or ""
    agent = (request.headers.get("User-Agent") or "")[:300]
    stored = db.query("SELECT password_hash FROM users WHERE id = %s", (user["id"],), one=True)
    with db.transaction() as cur:
        cur.execute("SELECT full_fails, full_fail_at, now() AS now FROM user_sessions WHERE key_hash = %s FOR UPDATE", (key,))
        row = cur.fetchone()
        if not row:
            outcome = ("gone", None)
        elif fa.fails_block(row["full_fails"], row["full_fail_at"], row["now"]):
            outcome = ("blocked", fa.fails_block(row["full_fails"], row["full_fail_at"], row["now"]))
        elif not password:
            outcome = ("empty", None)
        elif not check_password_hash(stored["password_hash"], password):
            fails = fa.next_fails(row["full_fails"], row["full_fail_at"], row["now"])
            cur.execute("UPDATE user_sessions SET full_fails = %s, full_fail_at = %s WHERE key_hash = %s", (fails, row["now"], key))
            outcome = ("wrong", fails)
        else:
            until = fa.unlock_until(row["now"])
            cur.execute("""UPDATE user_sessions SET full_until = %s, full_since = %s, full_fails = 0, full_fail_at = NULL, user_agent = %s
                           WHERE key_hash = %s""", (until, row["now"], agent, key))
            outcome = ("on", until)
    what, value = outcome
    now = row["now"] if row else None

    def blocked_until(t):
        return api_error(f"Too many wrong passwords. Try again after {clock(t.astimezone(account_info.tz()))}.", 429, field="password")

    if what == "gone":
        return api_error("Sign in to continue", 401)
    if what == "blocked":
        return blocked_until(value)
    if what == "empty":
        return api_error("Type your password", 400, field="password")
    if what == "wrong":
        log_activity("auth.full_access_refused", details={"tries": value})
        if value >= fa.MAX_FAILS:
            return blocked_until(now + fa.FAIL_WAIT)
        return api_error("That password isn't right", 400, field="password")
    device = fa.device_words(agent)
    log_activity("auth.full_access_on", details={"until": value.isoformat(), "from": device})
    try:
        _notify_unlocked(user, device, now)
    except Exception:  # noqa: BLE001 - the unlock stands; the activity line records it either way
        import logging
        logging.getLogger(__name__).exception("full access notice not queued")
    return jsonify({"full_access": {**full_access_state({**user, "full_until": value})["full_access"]}})


@bp.delete("/full-access")
@login_required
def full_access_off():
    """Lock now: this sign-in goes back to the usual tools (a run already going finishes)."""
    import full_access as fa
    user = current_user()
    why = fa.may_lock(user)
    if why:
        return api_error(why, 403)
    db.execute("UPDATE user_sessions SET full_until = NULL WHERE key_hash = %s", (session_key_hash(),))
    log_activity("auth.full_access_off")
    return jsonify(full_access_state({**user, "full_until": None}))
