"""Settings → Targets → Account spending limit (FU-B): read live, check a new amount, change it with the same
confirmation as Accept, and (owner only) clear the pause a read-back mismatch set. Teammates and clients never."""
from flask import Blueprint, jsonify, request

import ads_api
import meta_client
import spend_limit
from auth import admin_required, current_user, owner_required
from util import api_error

bp = Blueprint("spend_limit", __name__, url_prefix="/api/settings/spend-limit")


def _wanted(data):
    """(cents or None, remove, problem) from {to_cents} or {remove: true}."""
    remove = data.get("remove") is True
    if remove:
        return None, True, None
    cents = ads_api._echoed_cents(data, "to_cents")
    if cents is ads_api._MISSING or cents is None:
        return None, False, "Type the new limit, like 200"
    return cents, False, None


@bp.get("")
@admin_required
def get_limit():
    try:
        return jsonify(spend_limit.view(spend_limit.live()))
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the spending limit from Meta: {exc}", 400)


SWITCHED = "You switched accounts in another tab, so this page shows another account's limit. Reload the page."


def _other_account(data):
    """The page names the ad account it showed (`act` from the read); a cookie switched in another tab since then
    would otherwise point the change at a different account's limit."""
    return data.get("act") != spend_limit.act()


@bp.post("/check")
@admin_required
def check_limit():
    data = request.get_json(silent=True) or {}
    cents, remove, problem = _wanted(data)
    if problem:
        return api_error(problem, 400, field="to_cents")
    if _other_account(data):
        return api_error(SWITCHED, 409)
    try:
        return jsonify(spend_limit.plan(cents, remove=remove))
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the spending limit from Meta: {exc}", 400)


@bp.post("")
@admin_required
def change_limit():
    data = request.get_json(silent=True) or {}
    cents, remove, problem = _wanted(data)
    if problem:
        return api_error(problem, 400, field="to_cents")
    if _other_account(data):
        return api_error(SWITCHED, 409)
    from_cents = ads_api._echoed_cents(data, "from_cents")
    if from_cents is ads_api._MISSING:
        return api_error("Check the amounts again: the limit you saw wasn't sent.", 409)
    meta_client.watch_writes()
    error, info = spend_limit.apply(current_user(), cents, remove=remove, confirm_remove=data.get("confirm_remove") is True,
                                    from_cents=from_cents, accept_big=data.get("accept_big") is True)
    if error and error.startswith(ads_api.NOT_SENT):
        return api_error(ads_api.error_words(error), 400 if info.get("code") else 409,
                         **({"plan": info["plan"]} if info.get("plan") else {}))
    if error:
        return ads_api.write_error(error)
    try:
        now = spend_limit.view(spend_limit.live())
    except meta_client.MetaError:
        now = {}
    return jsonify({**now, "limit_cents": info.get("limit_cents")})


@bp.post("/unblock")
@owner_required
def unblock():
    if not spend_limit.blocked():
        return api_error("Limit changes aren't paused", 409)
    spend_limit.unblock(current_user())
    return jsonify({"blocked": None})
