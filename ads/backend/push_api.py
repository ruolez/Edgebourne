"""This device's notifications (any signed-in person): the public key to subscribe with, the
person's devices, turning one on or off, and a test message."""
from flask import Blueprint, jsonify, request

import config
import db
import push
from auth import current_user, login_required
from util import api_error, log_activity

bp = Blueprint("push", __name__, url_prefix="/api/me/push")


def view(user_id):
    _, pub = push.keys()
    return {"public_key": pub, "devices": [{**d, "created_at": d["created_at"].isoformat(),
                                             "last_ok_at": d["last_ok_at"].isoformat() if d["last_ok_at"] else None} for d in push.devices(user_id)]}


@bp.get("")
@login_required
def get_push():
    return jsonify(view(current_user()["id"]))


@bp.post("")
@login_required
def subscribe():
    data = request.get_json(silent=True) or {}
    sub = data.get("subscription") or {}
    endpoint = str(sub.get("endpoint") or "")
    keys = sub.get("keys") or {}
    if not push.allowed_endpoint(endpoint, config.PUSH_TEST_HOSTS):
        return api_error("This browser's push service isn't one we know", 400)
    if not push.valid_keys(keys.get("p256dh"), keys.get("auth")):
        return api_error("This browser sent keys that can't be used for notifications", 400)
    user = current_user()
    label = str(data.get("label") or "")[:120] or None
    db.execute("""INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, label) VALUES (%s, %s, %s, %s, %s)
                  ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth,
                  label = EXCLUDED.label, failures = 0""", (user["id"], endpoint, keys["p256dh"][:200], keys["auth"][:100], label))
    log_activity("push.on", details={"label": label})
    return jsonify(view(user["id"])), 201


@bp.delete("/<int:sid>")
@login_required
def unsubscribe(sid):
    user = current_user()
    db.execute("DELETE FROM push_subscriptions WHERE id = %s AND user_id = %s", (sid, user["id"]))
    return jsonify(view(user["id"]))


@bp.post("/off")
@login_required
def unsubscribe_endpoint():
    """The browser turned notifications off: forget it by its endpoint."""
    user = current_user()
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id = %s",
               (str((request.get_json(silent=True) or {}).get("endpoint") or ""), user["id"]))
    return jsonify(view(user["id"]))


@bp.post("/test")
@login_required
def test():
    user = current_user()
    try:
        n = push.send_to_user(user["id"], "Test from Edge Bourne Ads", ["This is how new leads, reminders and alerts arrive."], "/home.html", tag="test")
    except push.PushError as exc:
        return api_error(str(exc), 400)
    return jsonify({"sent": n, **view(user["id"])})
