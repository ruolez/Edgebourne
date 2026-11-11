"""Updating an ad in place: a new creative goes on the same ad, so it keeps its ID and results.
Every switch is kept in ad_versions so results can be read per version and a version put back."""
import json
import logging

from flask import Blueprint, jsonify

import account_info
import concepts
import creative_versions as cv
import db
import meta_client
import placements
import targets
from auth import current_user, login_required
from util import api_error

log = logging.getLogger(__name__)
bp = Blueprint("versions", __name__, url_prefix="/api")

OUTSIDE = "Changed outside this console"


def save_switch(ad, new_creative, label, user_id=None, proposal_id=None, title=None, body=None, restored_from=None):
    """Note that `ad` (its row from before the switch) moved to `new_creative`. The first switch
    also records what it had until then as version 1. Saying the same switch twice adds nothing."""
    aid = ad["id"]
    db.run_in_transaction([
        ("""INSERT INTO ad_versions (ad_id, number, creative_id, label, title, body, started_at, started_on)
            SELECT %s, 1, %s, 'Original', %s, %s, COALESCE((SELECT created_time FROM ads WHERE id = %s), now()), NULL
            WHERE NOT EXISTS (SELECT 1 FROM ad_versions WHERE ad_id = %s)
            ON CONFLICT DO NOTHING""",
         (aid, ad["creative_id"], ad.get("title"), ad.get("body"), aid, aid)),
        ("""INSERT INTO ad_versions (ad_id, number, creative_id, label, title, body, restored_from, started_on, user_id, proposal_id)
            SELECT %s, (SELECT COALESCE(MAX(number), 0) + 1 FROM ad_versions WHERE ad_id = %s), %s, %s, %s, %s, %s, %s, %s, %s
            WHERE (SELECT creative_id FROM ad_versions WHERE ad_id = %s ORDER BY number DESC LIMIT 1) IS DISTINCT FROM %s
            ON CONFLICT DO NOTHING""",
         (aid, aid, new_creative, label, title, body, restored_from, account_info.today(), user_id, proposal_id, aid, new_creative)),
    ])


def _with_live_creative(ad):
    """The ad as Meta has it now. A creative changed elsewhere is noted as its own version."""
    live = (meta_client.get(ad["id"], fields="creative").get("creative") or {}).get("id")
    if not live or live == ad["creative_id"]:
        return ad
    db.execute("UPDATE ads SET creative_id = %s WHERE id = %s", (live, ad["id"]))
    save_switch(ad, live, OUTSIDE)
    return {**ad, "creative_id": live}


def _stored(ad, new_creative, title, body):
    db.execute("UPDATE ads SET creative_id = %s, title = %s, body = %s WHERE id = %s", (new_creative, title, body, ad["id"]))


def _ad(ad_id):
    return db.query("SELECT id, name, campaign_id, creative_id, effective_status, title, body FROM ads WHERE id = %s", (ad_id,), one=True)


def update_ad(user, data, proposal_id=None):
    """Put new words or media on an existing ad. The new creative is read back first, so a copy Meta
    stored wrongly never reaches the ad. Returns None, or what went wrong (NOT_SENT-prefixed when
    nothing reached Meta, so the suggestion stays waiting)."""
    import ads_api
    not_sent = ads_api.NOT_SENT
    ad = _ad(data.get("template_ad_id"))
    if not ad or not ad["creative_id"]:
        return not_sent + "The ad this was made for isn't there any more."
    if not ads_api.can_touch(user, ad["campaign_id"]):
        return not_sent + "This campaign isn't assigned to you"
    if ad["effective_status"] in ("ARCHIVED", "DELETED"):
        return not_sent + "That ad is archived, so it can't be updated. Make it a new ad instead."
    row = {"id": ad["id"], "name": ad["name"], "campaign_id": ad["campaign_id"]}
    try:
        ad = _with_live_creative(ad)
        current = meta_client.get(ad["creative_id"], fields="object_story_spec,asset_feed_spec")
        if placements.has_placements(current):
            return not_sent + "This ad shows different media per placement, so it can't be updated here yet. Change it in Ads Manager or make it a new ad."
        ctx, err = ads_api.prepare_creative(user, {**data, "adset_id": None, "name": data.get("name") or ad["name"]})
    except meta_client.MetaError as exc:
        return not_sent + f"Couldn't read the ad from Meta, so nothing was changed: {exc}"
    if err:
        return not_sent + err[0]
    change = cv.change_words(current.get("object_story_spec"), ctx["spec"])
    if not change:
        return not_sent + "This is the same as what the ad shows now, so there's nothing to update."
    payload = {"name": f"{ad['name']} · {change}"[:200], "object_story_spec": json.dumps(ctx["spec"])}
    if ctx["dof"]:
        payload["degrees_of_freedom_spec"] = json.dumps(ctx["dof"])
    title, body = (data.get("title") or "").strip()[:255], (data.get("body") or "").strip()
    switching = False
    try:
        new = meta_client.post(f"act_{ads_api._account()}/adcreatives", data=payload)
        made = meta_client.get(new["id"], fields="object_story_spec")
        problem = cv.readback_problem(ctx["spec"], made)
        if problem:
            log.warning("update read-back refused for ad %s: %s", ad["id"], placements.describe(made))
            ads_api.record(user, "ad", row, "update_creative", ad["creative_id"], f"creative {new['id']} not used", False, problem, proposal_id)
            return f"{ads_api.CHECKED}{problem} The running ad wasn't changed."
        switching = True
        ads_api.put_creative(ad["id"], new["id"])
    except meta_client.MetaError as exc:
        ads_api.record(user, "ad", row, "update_creative", ad["creative_id"], change, False, str(exc), proposal_id)
        if exc.unknown and switching:
            return ads_api.UNKNOWN + ads_api.SWITCH_UNKNOWN
        return f"{exc}. The running ad wasn't changed."
    ads_api.record(user, "ad", row, "update_creative", ad["creative_id"], f"{change} (creative {new['id']})", True, proposal_id=proposal_id)
    ads_api.after_write("stored creative", _stored, ad, new["id"], title, body)
    ads_api.after_write("version history", save_switch, ad, new["id"], change, user["id"], proposal_id, title, body)
    ads_api.resync_later()
    return None


def for_ad(ad):
    """An ad's versions with the results of each, or None when it has only ever had one."""
    rows = db.query("""SELECT number, creative_id, label, title, restored_from, started_at, started_on
                       FROM ad_versions WHERE ad_id = %s ORDER BY number""", (ad["id"],))
    if len(rows) < 2:
        return None
    today = account_info.today()
    days = db.query("SELECT day, spend_cents, impressions, link_clicks, leads, video_3s FROM ad_daily WHERE ad_id = %s AND day < %s",
                    (ad["id"], today))
    ready = db.query("""SELECT at, (at AT TIME ZONE %s)::date AS day FROM status_events
                        WHERE level = 'ad' AND entity_id = %s AND field = 'effective_status' AND new_value = 'ACTIVE'
                          AND old_value IN ('IN_PROCESS', 'PENDING_REVIEW') ORDER BY at""", (account_info.tz_name(), ad["id"]))
    chain = cv.with_live_days(rows, ready, today, ad.get("effective_status") in cv.REVIEW_STATES)
    totals, changeover = cv.split_results(days, chain)
    target = targets.lead()
    versions = []
    for v, total in zip(chain, totals):
        versions.append({"number": v["number"], "label": v["label"], "title": v["title"], "restored_from": v["restored_from"],
                         "started_on": v["started_on"].isoformat() if v["started_on"] else None,
                         "live_on": v["live_on"].isoformat() if v["live_on"] else None,
                         "current": v is chain[-1] and v["creative_id"] == ad["creative_id"],
                         "enough": total["leads"] >= concepts.MIN_LEADS and (not target or total["spend_cents"] >= concepts.SPEND_TIMES * target),
                         **total})
    return {"versions": versions, "changeover": changeover}


@bp.post("/ads/ad/<ad_id>/versions/<int:number>/restore")
@login_required
def restore(ad_id, number):
    """Put an earlier version back on the ad."""
    import ads_api
    user = current_user()
    ad = _ad(ad_id)
    if not ad or not ads_api.can_touch(user, ad["campaign_id"]):
        return api_error("Ad not found", 404)
    version = db.query("SELECT number, creative_id, title, body FROM ad_versions WHERE ad_id = %s AND number = %s", (ad_id, number), one=True)
    if not version:
        return api_error("That version isn't there any more", 404)
    row = {"id": ad["id"], "name": ad["name"], "campaign_id": ad["campaign_id"]}
    label = f"Back to version {number}"
    try:
        ad = _with_live_creative(ad)
        if ad["creative_id"] == version["creative_id"]:
            return api_error("That version is already on the ad", 409)
        ads_api.put_creative(ad["id"], version["creative_id"])
    except meta_client.MetaError as exc:
        ads_api.record(user, "ad", row, "restore_creative", ad["creative_id"], label, False, str(exc))
        if exc.unknown:
            return api_error(ads_api.SWITCH_UNKNOWN, 400)
        return api_error(f"Meta refused: {exc}. The running ad wasn't changed.", 400)
    ads_api.record(user, "ad", row, "restore_creative", ad["creative_id"], f"{label} (creative {version['creative_id']})", True)
    ads_api.after_write("stored creative", _stored, ad, version["creative_id"], version["title"], version["body"])
    ads_api.after_write("version history", save_switch, ad, version["creative_id"], label, user["id"], None, version["title"], version["body"], number)
    ads_api.resync_later()
    return jsonify({"status": "applied"})
