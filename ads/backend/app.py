import logging

from flask import Flask, jsonify

import config
import db


def create_app(run_migrations=True):
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    logging.basicConfig(level=logging.INFO)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.APP_BASE_URL.startswith("https://"),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
        MAX_CONTENT_LENGTH=260 * 1024 * 1024,  # video uploads; nginx keeps every other route at 2 MB
    )

    if run_migrations:
        db.run_migrations()

    import accounts_api
    import ads_api
    import advice_api
    import adsets_api
    import alerts_api
    import auth
    import builds_api
    import concepts_api
    import desk_api
    import experiments_api
    import forms_api
    import home_api
    import insights_api
    import polish
    import push_api
    import refresh_api
    import reports_api
    import leads_api
    import performance_api
    import settings_api
    import swipes_api
    import team_api
    import tracking_api
    import webhooks

    for module in (accounts_api, ads_api, adsets_api, advice_api, alerts_api, auth, builds_api, concepts_api, desk_api, experiments_api, forms_api, home_api, insights_api, leads_api, polish, performance_api, push_api, refresh_api, reports_api, settings_api, swipes_api, team_api, tracking_api, webhooks):
        app.register_blueprint(module.bp)
    app.register_blueprint(desk_api.agent_bp)
    app.teardown_appcontext(db.close_db)
    app.before_request(accounts_api.choose_for_request)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        """For the installer and monitoring: the database answers and the background worker ran
        lately (503 otherwise, so a stopped worker doesn't go unnoticed)."""
        import time
        import jobs
        import settings_store
        try:
            db.query("SELECT 1")
        except Exception:
            return jsonify({"status": "error", "database": "down"}), 503
        stale = jobs.worker_expected() and jobs.worker_stale(settings_store.get("worker_last_pass"), time.time())
        body = {"status": "stale" if stale else "ok", "worker_last_pass": settings_store.get("worker_last_pass")}
        return jsonify(body), 503 if stale else 200

    # Background jobs start in each gunicorn worker (gunicorn.conf.py post_fork),
    # because threads started before the fork do not survive it.
    return app
