"""Inbox API: GET the feed (box=need|fyi|all, filter=unread|all, kind=status|leads|claude|money|system|all), POST read marks."""
from flask import Blueprint, jsonify, request

import inbox
from auth import admin_required, current_user, login_required
from util import api_error, log_activity

bp = Blueprint("inbox", __name__, url_prefix="/api/inbox")
alerts_bp = Blueprint("alert_actions", __name__, url_prefix="/api/alerts")


@alerts_bp.post("/<int:alert_id>/done")
@admin_required
def done(alert_id):
    """Done on an event that waits for a person (an outside budget change that broke a money rule)."""
    import alerts
    row = alerts.mark_done(alert_id)
    if not row:
        return api_error("This one is already closed, or it closes by itself", 409)
    log_activity("alert.done", subject=str(alert_id), details={"rule": row["rule"], "title": row["title"]})
    return jsonify({"ok": True})


@bp.get("")
@login_required
def feed():
    user = current_user()
    items = inbox.items_for(user)
    filt = request.args.get("filter", "all")
    kind = request.args.get("kind", "all")
    box = request.args.get("box", "all")
    box = box if box in inbox.BOXES else "all"
    return jsonify({"items": inbox.pick(items, filt, kind, box)[:200], "counts": inbox.counts(items),
                    "kinds": inbox.kinds(inbox.pick(items, filt, "all", box))})


@bp.post("/read")
@login_required
def read():
    user = current_user()
    body = request.get_json(silent=True) or {}
    if body.get("all"):
        keys = [i["key"] for i in inbox.pick(inbox.items_for(user), "unread", body.get("kind") or "all", body.get("box") or "all")]
    else:
        keys = [str(k) for k in (body.get("keys") or []) if isinstance(k, (str, int))][:500]
        if not keys:
            return api_error("Nothing to mark as read", 400)
    inbox.mark_read(user, keys)
    return jsonify({"ok": True, "marked": len(keys)})
