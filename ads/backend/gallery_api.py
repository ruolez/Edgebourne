"""GET /api/gallery: the Gallery's cards (UX-AUDIT 9.5), from what the sync stored; no Meta call.
Numbers come from ad_daily per ad (as concepts_api.by_concept reads them), each ad credited only with
the days it showed what it shows now; gallery.py groups and picks."""
from datetime import timedelta

from flask import Blueprint, jsonify, request

import account_info
import alerts
import concepts
import concepts_api
import creative_versions as cv
import db
import gallery
import ranges
import targets
from auth import current_user, login_required, visible_campaign_ids

bp = Blueprint("gallery", __name__, url_prefix="/api")

# Ads that are part of the picture even before they spend: delivering, waiting for review or stopped by Meta.
SHOWN_UNSPENT = ("ACTIVE",) + gallery.REVIEW + gallery.PROBLEM


def _chains(ad_rows, today):
    """{ad id: its versions with live_on} for ads that changed creative at least once."""
    ids = [a["id"] for a in ad_rows]
    rows = db.query("""SELECT ad_id, number, creative_id, started_at, started_on FROM ad_versions
                       WHERE ad_id = ANY(%s) ORDER BY ad_id, number""", (ids,))
    by_ad = {}
    for r in rows:
        by_ad.setdefault(r["ad_id"], []).append(r)
    changed = [k for k, v in by_ad.items() if len(v) > 1]
    if not changed:
        return {}
    ready = {}
    for r in db.query("""SELECT entity_id, at, (at AT TIME ZONE %s)::date AS day FROM status_events
                         WHERE level = 'ad' AND entity_id = ANY(%s) AND field = 'effective_status' AND new_value = 'ACTIVE'
                           AND old_value IN ('IN_PROCESS', 'PENDING_REVIEW') ORDER BY at""", (account_info.tz_name(), changed)):
        ready.setdefault(r["entity_id"], []).append(r)
    status = {a["id"]: a["effective_status"] for a in ad_rows}
    return {k: cv.with_live_days(by_ad[k], ready.get(k, []), today, status.get(k) in cv.REVIEW_STATES) for k in changed}


@bp.get("/gallery")
@login_required
def gallery_cards():
    user = current_user()
    key = request.args.get("range", "7")
    key = key if key in ranges.KEYS else "7"
    today = account_info.today()
    # FU-C: the cards show the dates through today so far; their order, Too early and Cheapest read complete days.
    start, end = ranges.window(key, today, request.args.get("start"), request.args.get("end"), live=True)
    part = ranges.settled(start, end, today)
    if ranges.includes_today(start, end, today):
        import insights
        insights.read_today()
    dim, value = request.args.get("dim", ""), concepts.clean_value(request.args.get("tag", ""))
    tag = (dim, value) if dim in concepts.DIMENSIONS and value else None
    ids = visible_campaign_ids(user)
    scope, params = ("TRUE", []) if ids is None else ("a.campaign_id = ANY(%s)", [ids])
    ads = db.query(f"""SELECT a.id, a.name, a.campaign_id, a.adset_id, a.effective_status, a.creative_id, a.video_id, a.title, a.body,
                              a.cta_type, a.image_url, a.thumbnail_url, (a.created_time AT TIME ZONE %s)::date AS created_on
                       FROM ads a
                       WHERE {scope} AND (a.effective_status = ANY(%s) OR EXISTS (
                           SELECT 1 FROM ad_daily d WHERE d.ad_id = a.id AND d.day BETWEEN %s AND %s AND d.spend_cents > 0))""",
                   [account_info.tz_name()] + params + [list(SHOWN_UNSPENT), start, end])
    ad_ids = [a["id"] for a in ads]
    days = {}
    for r in db.query("""SELECT ad_id, day, spend_cents, impressions, link_clicks, leads, video_3s FROM ad_daily
                         WHERE ad_id = ANY(%s) AND day BETWEEN %s AND %s""", (ad_ids, start, end)):
        days.setdefault(r["ad_id"], []).append(r)
    chains = _chains(ads, today) if ad_ids else {}
    totals = {a["id"]: gallery.credited(days.get(a["id"], []), chains.get(a["id"], [])) for a in ads}
    in_part = (lambda r: part[0] <= r["day"] <= part[1]) if part else (lambda r: False)
    judged_totals = {a["id"]: gallery.credited([r for r in days.get(a["id"], []) if in_part(r)], chains.get(a["id"], [])) for a in ads}
    first_spend = {r["ad_id"]: r["day"] for r in db.query(
        "SELECT ad_id, MIN(day) AS day FROM ad_daily WHERE ad_id = ANY(%s) AND spend_cents > 0 GROUP BY ad_id", (ad_ids,))}
    launched = {a["id"]: gallery.launch_day(first_spend.get(a["id"]), a["created_on"], chains.get(a["id"], ())) for a in ads}
    track_days = [today - timedelta(days=14 - i) for i in range(14)]
    delivered = {}  # the bars, like the numbers, only count days showing what the ad shows now
    for r in db.query("SELECT ad_id, day FROM ad_daily WHERE ad_id = ANY(%s) AND day BETWEEN %s AND %s AND spend_cents > 0",
                      (ad_ids, track_days[0], track_days[-1])):
        if gallery.counts_now(r["day"], chains.get(r["ad_id"], [])):
            delivered.setdefault(r["ad_id"], set()).add(r["day"])
    since = {a["id"]: gallery.version_since(chains.get(a["id"], [])) for a in ads}
    tired = {r["entity_id"] for r in db.query(
        "SELECT DISTINCT entity_id FROM alerts WHERE rule = 'fatigue' AND resolved_at IS NULL AND entity_id = ANY(%s)", (ad_ids,))}
    tags = concepts_api.tags_for(ad_ids)
    target = targets.lead_own()
    groups = gallery.build(ads, judged_totals, tags, tired, launched, delivered, track_days, today, target, since=since)
    out = gallery.pick(groups, request.args.get("view", "top"), request.args.get("status", ""), tag)
    live_by = {g["key"]: g for g in gallery.build(ads, totals, tags, tired, launched, delivered, track_days, today, target, since=since)}
    out["groups"] = ranges.with_live(out["groups"], [live_by[g["key"]] for g in out["groups"] if g["key"] in live_by], "key",
                                     gallery.NUMBERS + ("video_impressions", "cpl_cents", "hook_rate"), {"enough": False})
    known = {d: sorted({v for x in groups for dd, v in x["tags_all"] if dd == d}, key=str.casefold) for d in concepts.DIMENSIONS}
    return jsonify({**out, "range": {"key": key, "start": start.isoformat(), "end": end.isoformat(), "label": ranges.label(start, end, today=today)},
                    "judged_through": part[1].isoformat() if part else None, "with_today": end >= today,
                    "tag": list(tag) if tag else None, "total": len(groups),
                    "deleted": sum(1 for g in groups if g["bucket"] == "deleted"),
                    "target_cents": target, "fatigue_on": alerts.saved_rules()["fatigue"]["on"], "launch_days": gallery.LAUNCH_DAYS,
                    "dimensions": {k: v[0] for k, v in concepts.DIMENSIONS.items()}, "known": known})
