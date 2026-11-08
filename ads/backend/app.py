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
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )

    if run_migrations:
        db.run_migrations()

    import auth
    import leads_api
    import performance_api
    import settings_api
    import team_api
    import webhooks

    for module in (auth, leads_api, performance_api, settings_api, team_api, webhooks):
        app.register_blueprint(module.bp)
    app.teardown_appcontext(db.close_db)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # Background jobs start in each gunicorn worker (gunicorn.conf.py post_fork),
    # because threads started before the fork do not survive it.
    return app
