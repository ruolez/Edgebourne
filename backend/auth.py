import secrets
import time
from functools import wraps

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

import db

bp = Blueprint("auth", __name__)

_attempts = {}
_MAX_ATTEMPTS = 10
_WINDOW = 900


def _rate_limited(ip):
    now = time.time()
    count, start = _attempts.get(ip, (0, now))
    if now - start > _WINDOW:
        count, start = 0, now
    if count >= _MAX_ATTEMPTS:
        _attempts[ip] = (count, start)
        return True
    _attempts[ip] = (count + 1, start)
    return False


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def check_csrf():
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF") or ""
    if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
        abort(400, description="CSRF check failed — reload the page and try again.")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)

    return wrapper


@bp.get("/admin/login")
def login():
    if "user_id" in session:
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")


@bp.post("/admin/login")
def login_post():
    check_csrf()
    ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
    if _rate_limited(ip):
        flash("Too many attempts — try again in a few minutes.", "error")
        return redirect(url_for("auth.login"))
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = db.query(
        "SELECT * FROM users WHERE username = %s AND is_active", (username,), one=True
    )
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("auth.login", next=request.form.get("next") or None))
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session.permanent = True
    nxt = request.form.get("next") or ""
    if not nxt.startswith("/admin"):
        nxt = url_for("admin.dashboard")
    return redirect(nxt)


@bp.post("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
