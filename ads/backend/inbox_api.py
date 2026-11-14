"""Inbox API: GET the feed (box=need|fyi|all, filter=unread|all, kind=status|leads|claude|money|system|all), POST read marks."""
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
    box = request.args.get("box", "all")
    box = box if box in inbox.BOXES else "all"
    rule = request.args.get("rule")
    shown = inbox.pick(items, filt, kind, box)
    if rule in inbox.RULE_FILTERS:  # AM-E: Results' "Meta noticed N unusual changes" opens just those
        shown = [i for i in shown if i["rule"] == rule]
    return jsonify({"items": shown[:200], "counts": inbox.counts(items),
                    "kinds": inbox.kinds(inbox.pick(items, filt, "all", box)), "rule": rule if rule in inbox.RULE_FILTERS else None})


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
