"""Inbox API: GET the feed (filter=unread|all, kind=status|leads|claude|money|system|all), POST read marks."""
from flask import Blueprint, jsonify, request

import inbox
from auth import current_user, login_required
from util import api_error

bp = Blueprint("inbox", __name__, url_prefix="/api/inbox")


@bp.get("")
@login_required
def feed():
    user = current_user()
    items = inbox.items_for(user)
    filt = request.args.get("filter", "all")
    kind = request.args.get("kind", "all")
    return jsonify({"items": inbox.pick(items, filt, kind)[:200], "counts": inbox.counts(items)})


@bp.post("/read")
@login_required
def read():
    user = current_user()
    body = request.get_json(silent=True) or {}
    if body.get("all"):
        keys = [i["key"] for i in inbox.pick(inbox.items_for(user), "unread", body.get("kind") or "all")]
    else:
        keys = [str(k) for k in (body.get("keys") or []) if isinstance(k, (str, int))][:500]
        if not keys:
            return api_error("Nothing to mark as read", 400)
    inbox.mark_read(user, keys)
    return jsonify({"ok": True, "marked": len(keys)})
