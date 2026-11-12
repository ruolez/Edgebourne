import json

from flask import jsonify, session

import db


def api_error(message, status=400, **extra):
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status


def log_activity(action, subject=None, details=None, actor=None, user_id=None):
    """Append to the activity log. Defaults to the signed-in person. Returns the line's id."""
    if user_id is None and actor in (None, "user"):
        try:
            user_id = session.get("user_id")
        except RuntimeError:
            user_id = None
    row = db.execute(
        "INSERT INTO activity (user_id, actor, action, subject, details) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, actor or ("user" if user_id else "system"), action, subject,
         json.dumps(details or {})), returning=True,
    )
    return row["id"] if row else None
