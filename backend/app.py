import logging
import os
from datetime import datetime, timezone

from flask import Flask, g, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
import config
import db
import money
import portal
import public
import webhooks
from admin import bp as admin_bp

# Responses on these prefixes must never be cached or indexed. /pay and
# /estimate are token-authenticated customer documents: the default
# "public, max-age=300" below would let a shared proxy serve one client's
# invoice to another.
NO_STORE_PREFIXES = ("/admin", "/pay", "/estimate", "/billing")


def create_app():
    app = Flask(__name__)
    # nginx proxies over plain HTTP, so without this every request looks like
    # http:// -- which would produce http:// pay links and Stripe redirect URLs
    # that Stripe rejects in live mode.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # An admin session can move money now, so the cookie is https-only in a
        # real deployment. Set just below, once the database is reachable.
        PERMANENT_SESSION_LIFETIME=43200,
    )
    logging.basicConfig(level=logging.INFO)

    db.run_migrations()

    # Decided at boot, so it cannot read flask.g. Falls back to the site_url
    # setting when PUBLIC_BASE_URL is not in the environment.
    def _https_deployment():
        if config.PUBLIC_BASE_URL:
            return config.PUBLIC_BASE_URL.startswith("https")
        try:
            with db.standalone() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM settings WHERE key = 'site_url'")
                    row = cur.fetchone()
                conn.commit()
            return bool(row and (row[0] or "").startswith("https"))
        except Exception:
            return False

    app.config["SESSION_COOKIE_SECURE"] = _https_deployment()

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin_bp)
    # Registered before public.bp, whose one-segment catch-all GET /<slug>
    # serves CMS pages. (Two-segment portal routes could not collide anyway.)
    app.register_blueprint(portal.bp)
    app.register_blueprint(webhooks.bp)
    app.register_blueprint(public.bp)
    money.register_filters(app)

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

    # Also a template *global*, not just a context value: Jinja macros imported
    # without `with context` cannot see context processors, and the billing
    # macros need setting() for the tax label and company details.
    app.add_template_global(setting, "setting")

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
            try:
                row = db.query(
                    """SELECT
                         (SELECT COUNT(*) FROM invoices
                           WHERE status IN ('open','partial')
                             AND due_date < current_date)                  AS overdue,
                         (SELECT COUNT(*) FROM email_log
                           WHERE status IN ('failed','permanently_failed')) AS failed_emails""",
                    one=True,
                )
                ctx["overdue_count"] = row["overdue"]
                ctx["failed_emails"] = row["failed_emails"]
            except Exception:
                # Billing tables may not exist yet on a partially-migrated box.
                db.rollback()
                ctx["overdue_count"] = ctx["failed_emails"] = 0
        return ctx

    @app.after_request
    def security_and_cache_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith(NO_STORE_PREFIXES):
            resp.headers["Cache-Control"] = "no-store, private, max-age=0"
            resp.headers["X-Frame-Options"] = "DENY"
            if not request.path.startswith("/admin"):
                # Token-addressed customer documents: keep them out of search
                # indexes, and out of the Referer sent when the customer is
                # redirected to Stripe.
                resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
                resp.headers["Referrer-Policy"] = "no-referrer"
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
