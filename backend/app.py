import logging
import os
from datetime import datetime, timezone

from flask import Flask, g, render_template, request, session

import auth
import config
import db
import public
from admin import bp as admin_bp


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=43200,
    )
    logging.basicConfig(level=logging.INFO)

    db.run_migrations()

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public.bp)

    _asset_mtimes = {}

    def static_url(path):
        if path not in _asset_mtimes:
            try:
                full = os.path.join(app.static_folder, path)
                _asset_mtimes[path] = int(os.path.getmtime(full))
            except OSError:
                _asset_mtimes[path] = 0
        return f"/static/{path}?v={_asset_mtimes[path]}"

    def settings_all():
        if "settings_cache" not in g:
            try:
                rows = db.query("SELECT key, value FROM settings")
                g.settings_cache = {r["key"]: r["value"] for r in rows}
            except Exception:
                g.settings_cache = {}
        return g.settings_cache

    def setting(key, default=""):
        value = settings_all().get(key)
        return value if value not in (None, "") else default

    def nav_pages():
        try:
            return db.query(
                """SELECT slug, title, nav_label FROM pages
                   WHERE show_in_nav AND is_published
                   ORDER BY sort_order, id"""
            )
        except Exception:
            return []

    @app.context_processor
    def inject_globals():
        ctx = {
            "setting": setting,
            "nav_pages": nav_pages(),
            "csrf_token": auth.csrf_token,
            "static_url": static_url,
            "current_year": datetime.now(timezone.utc).year,
        }
        if session.get("user_id"):
            try:
                row = db.query(
                    "SELECT COUNT(*) AS c FROM leads WHERE NOT is_read", one=True
                )
                ctx["unread_leads"] = row["c"]
            except Exception:
                ctx["unread_leads"] = 0
        return ctx

    @app.after_request
    def security_and_cache_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Frame-Options"] = "DENY"
        else:
            resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            cacheable = (
                request.method == "GET"
                and resp.status_code == 200
                and request.path != "/contact"
                and "Cache-Control" not in resp.headers
                and "user_id" not in session
            )
            if cacheable:
                resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    @app.errorhandler(404)
    def not_found(_e):
        try:
            return render_template("public/404.html"), 404
        except Exception:
            return "Not found", 404

    @app.errorhandler(413)
    def too_large(_e):
        return "File too large (max 10 MB).", 413

    return app
