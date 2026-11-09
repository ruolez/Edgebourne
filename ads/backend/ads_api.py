"""Ads page: see every campaign, ad set and ad with its results, preview ads as
Meta renders them, and make changes: on/off, budgets, duplicate, new ads from
uploaded media, and Claude's proposals. Admins can change everything; teammates
the campaigns assigned to them. Every write to Meta lands in meta_changes."""
import html
import json
import logging
import os
import re
import tempfile
import threading
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import db
import insights
import meta_client
import settings_store
from auth import current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

log = logging.getLogger(__name__)
bp = Blueprint("ads", __name__, url_prefix="/api")

LEVELS = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
RANGES = {"7": 7, "14": 14, "30": 30}
PREVIEW_FORMATS = [
    ("MOBILE_FEED_STANDARD", "Facebook feed"),
    ("INSTAGRAM_STANDARD", "Instagram feed"),
    ("INSTAGRAM_STORY", "Instagram Stories"),
    ("INSTAGRAM_REELS", "Instagram Reels"),
    ("FACEBOOK_STORY_MOBILE", "Facebook Stories"),
    ("FACEBOOK_REELS_MOBILE", "Facebook Reels"),
    ("DESKTOP_FEED_STANDARD", "Facebook desktop"),
]
CTA_TYPES = ["BOOK_TRAVEL", "SIGN_UP", "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SUBSCRIBE", "DOWNLOAD", "CONTACT_US"]
IMAGE_TYPES = {"image/jpeg", "image/png"}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE = 30 * 1024 * 1024
MAX_VIDEO = 250 * 1024 * 1024


# ---------------------------------------------------------------- pure helpers

def parse_dollars(text):
    """'$24/day', '24', '$1,250.50 per day' -> cents; None when there's no amount."""
    if text is None:
        return None
    m = re.search(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", str(text))
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", "")) * 100))


def proposal_action(p, entity):
    """What approving a proposal does on Meta: ("status", "PAUSED"), ("budget", cents)
    or None when it isn't something the dashboard can apply by itself."""
    if not entity or not p.get("entity_id"):
        return None
    if p["kind"] == "status":
        value = (p.get("proposed_value") or "").strip().upper()
        value = {"OFF": "PAUSED", "PAUSE": "PAUSED", "ON": "ACTIVE", "RESUME": "ACTIVE"}.get(value, value)
        return ("status", value) if value in ("ACTIVE", "PAUSED") else None
    if p["kind"] == "budget" and entity.get("daily_budget_cents"):
        cents = parse_dollars(p.get("proposed_value"))
        return ("budget", cents) if cents and cents >= 100 else None
    return None


def build_story_spec(template, media, body, title, cta_type=None):
    """A new object_story_spec from an existing ad's: same Page, Instagram identity and
    button (lead form), new media and words."""
    old_media = template.get("video_data") or template.get("link_data") or {}
    cta = json.loads(json.dumps(old_media.get("call_to_action") or {}))
    if cta_type:
        cta["type"] = cta_type
    spec = {k: template[k] for k in ("page_id", "instagram_user_id", "instagram_actor_id") if template.get(k)}
    if media["kind"] == "video":
        data = {"video_id": media["video_id"], "message": body, "title": title}
        if media.get("thumbnail_url"):
            data["image_url"] = media["thumbnail_url"]
        if cta:
            data["call_to_action"] = cta
        spec["video_data"] = data
    else:
        link = old_media.get("link") or (cta.get("value") or {}).get("link") or "http://fb.me/"
        data = {"image_hash": media["hash"], "message": body, "name": title, "link": link}
        if cta:
            data["call_to_action"] = cta
        spec["link_data"] = data
    return spec


def preview_src(body_html):
    m = re.search(r'src="([^"]+)"', body_html or "")
    return html.unescape(m.group(1)) if m else None


def preview_size(body_html):
    w = re.search(r'width="(\d+)"', body_html or "")
    h = re.search(r'height="(\d+)"', body_html or "")
    return (int(w.group(1)) if w else None, int(h.group(1)) if h else None)


# ---------------------------------------------------------------- access

def _scope(user, column):
    ids = visible_campaign_ids(user)
    return ("TRUE", []) if ids is None else (f"{column} = ANY(%s)", [ids])


def entity(level, entity_id):
    table = LEVELS.get(level)
    if not table:
        return None
    campaign_col = "id" if level == "campaign" else "campaign_id"
    budget = "daily_budget_cents, " if level != "ad" else "NULL::int AS daily_budget_cents, "
    return db.query(f"SELECT id, name, status, effective_status, {budget}{campaign_col} AS campaign_id "
                    f"FROM {table} WHERE id = %s", (entity_id,), one=True)


def find_entity(entity_id):
    for level in ("ad", "adset", "campaign"):
        row = entity(level, entity_id)
        if row:
            return level, row
    return None, None


def can_touch(user, campaign_id):
    ids = visible_campaign_ids(user)
    return ids is None or campaign_id in ids


def record(user, level, row, action, old, new, ok, error=None, proposal_id=None, entity_id=None):
    db.execute(
        """INSERT INTO meta_changes (user_id, level, entity_id, entity_name, campaign_id, action, old_value,
                                     new_value, ok, error, proposal_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (user["id"] if user else None, level, entity_id or row["id"], row.get("name"), row.get("campaign_id"),
         action, None if old is None else str(old), None if new is None else str(new), ok, error, proposal_id))
    log_activity(f"meta.{action}" + ("" if ok else "_failed"), subject=entity_id or row["id"],
                 details={"level": level, "name": row.get("name"), "old": old, "new": new, "error": error})


def resync_later():
    def run():
        try:
            insights.sync_structure()
        except Exception as exc:
            log.info("resync after change failed: %s", exc)
    threading.Thread(target=run, daemon=True).start()


def refresh_entity(level, entity_id):
    try:
        fresh = meta_client.get(entity_id, fields="status,effective_status")
        db.execute(f"UPDATE {LEVELS[level]} SET status = %s, effective_status = %s WHERE id = %s",
                   (fresh.get("status"), fresh.get("effective_status"), entity_id))
    except meta_client.MetaError:
        pass


# ---------------------------------------------------------------- changes (shared with proposals)

def apply_status(user, level, row, status, proposal_id=None):
    old = row["status"]
    if old == status:
        return None
    try:
        meta_client.post(row["id"], status=status)
    except meta_client.MetaError as exc:
        record(user, level, row, "status", old, status, False, str(exc), proposal_id)
        return str(exc)
    record(user, level, row, "status", old, status, True, proposal_id=proposal_id)
    refresh_entity(level, row["id"])
    resync_later()
    return None


def apply_budget(user, level, row, cents, proposal_id=None):
    old = row["daily_budget_cents"]
    if not old:
        return "This one has no daily budget of its own (the budget is set one level up)."
    try:
        meta_client.post(row["id"], daily_budget=str(int(cents)))
    except meta_client.MetaError as exc:
        record(user, level, row, "budget", old, cents, False, str(exc), proposal_id)
        return str(exc)
    db.execute(f"UPDATE {LEVELS[level]} SET daily_budget_cents = %s WHERE id = %s", (int(cents), row["id"]))
    record(user, level, row, "budget", old, cents, True, proposal_id=proposal_id)
    return None


# ---------------------------------------------------------------- read

def _metrics(where, params, start, end):
    rows = db.query(
        f"""SELECT ad_id, COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                   COALESCE(SUM(reach),0) AS reach, COALESCE(SUM(link_clicks),0) AS link_clicks,
                   COALESCE(SUM(leads),0) AS leads
            FROM ad_daily WHERE day BETWEEN %s AND %s AND {where} GROUP BY ad_id""",
        [start, end] + params)
    return {r["ad_id"]: {k: int(v) for k, v in r.items() if k != "ad_id"} for r in rows}


def _sum(items):
    keys = ("spend_cents", "impressions", "reach", "link_clicks", "leads", "qualified")
    return {k: sum(i["m"].get(k, 0) for i in items) for k in keys}


@bp.get("/ads")
@login_required
def tree():
    user = current_user()
    days = RANGES.get(request.args.get("range", "7"), 7)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    cw, cp = _scope(user, "id")
    aw, ap = _scope(user, "campaign_id")
    campaigns = db.query(f"SELECT * FROM campaigns WHERE {cw} ORDER BY effective_status = 'ACTIVE' DESC, name", cp)
    adsets = db.query(f"SELECT * FROM adsets WHERE {aw} ORDER BY name", ap)
    ads = db.query(f"""SELECT id, name, campaign_id, adset_id, status, effective_status, image_url, thumbnail_url,
                              title, object_type, review_feedback, issues, created_time
                       FROM ads WHERE {aw} ORDER BY name""", ap)
    metrics = _metrics(aw, ap, start, end)
    lifetime = {r["ad_id"]: int(r["impressions"]) for r in db.query(
        f"SELECT ad_id, SUM(impressions) AS impressions FROM ad_daily WHERE {aw} GROUP BY ad_id", ap)}
    quality = {r["ad_id"]: int(r["n"]) for r in db.query(
        f"""SELECT ad_id, COUNT(*) AS n FROM leads WHERE NOT is_test AND status IN ('qualified','won')
            AND created_time::date BETWEEN %s AND %s AND {aw} GROUP BY ad_id""", [start, end] + ap)}
    pending = {r["entity_id"]: int(r["n"]) for r in db.query(
        "SELECT entity_id, COUNT(*) AS n FROM desk_proposals WHERE status = 'pending' AND entity_id IS NOT NULL GROUP BY 1")}
    for ad in ads:
        ad["m"] = {**metrics.get(ad["id"], {}), "qualified": quality.get(ad["id"], 0)}
        ad["lifetime_impressions"] = lifetime.get(ad["id"], 0)
        ad["pending_proposals"] = pending.get(ad["id"], 0)
    for s in adsets:
        s["ads"] = [a for a in ads if a["adset_id"] == s["id"]]
        s["m"] = _sum(s["ads"])
        s["pending_proposals"] = pending.get(s["id"], 0)
    for c in campaigns:
        c["adsets"] = [s for s in adsets if s["campaign_id"] == c["id"]]
        c["m"] = _sum(c["adsets"])
        c["pending_proposals"] = pending.get(c["id"], 0)
        c["can_control"] = can_touch(user, c["id"])
    return jsonify({"range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
                    "campaigns": campaigns, "last_sync": settings_store.get("last_performance_sync")})


@bp.get("/ads/ad/<ad_id>")
@login_required
def ad_detail(ad_id):
    user = current_user()
    ad = db.query("""SELECT a.*, s.name AS adset_name, s.targeting_summary, s.learning_stage,
                            c.name AS campaign_name, c.daily_budget_cents AS campaign_budget_cents,
                            s.daily_budget_cents AS adset_budget_cents
                     FROM ads a LEFT JOIN adsets s ON s.id = a.adset_id LEFT JOIN campaigns c ON c.id = a.campaign_id
                     WHERE a.id = %s""", (ad_id,), one=True)
    if not ad or not can_touch(user, ad["campaign_id"]):
        return api_error("Ad not found", 404)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    rows = {r["day"].isoformat(): r for r in db.query(
        "SELECT day, spend_cents, impressions, link_clicks, leads FROM ad_daily WHERE ad_id = %s AND day BETWEEN %s AND %s",
        (ad_id, start, end))}
    series = []
    for i in range(30):
        d = (start + timedelta(days=i)).isoformat()
        r = rows.get(d) or {}
        series.append({"day": d, "spend_cents": int(r.get("spend_cents") or 0), "leads": int(r.get("leads") or 0),
                       "impressions": int(r.get("impressions") or 0), "link_clicks": int(r.get("link_clicks") or 0)})
    totals = db.query("""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                                COALESCE(SUM(reach),0) AS reach, COALESCE(SUM(link_clicks),0) AS link_clicks,
                                COALESCE(SUM(leads),0) AS leads FROM ad_daily WHERE ad_id = %s""", (ad_id,), one=True)
    leads = db.query("""SELECT id, full_name, business_type, status, created_time, is_test FROM leads
                        WHERE ad_id = %s ORDER BY created_time DESC LIMIT 50""", (ad_id,))
    proposals = db.query("""SELECT p.*, t.prompt FROM desk_proposals p JOIN desk_tasks t ON t.id = p.task_id
                            WHERE p.entity_id IN (%s, %s, %s) ORDER BY p.id DESC LIMIT 20""",
                         (ad_id, ad["adset_id"], ad["campaign_id"]))
    changes = db.query("""SELECT m.*, u.name AS user_name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                          WHERE m.entity_id IN (%s, %s, %s) ORDER BY m.id DESC LIMIT 30""",
                       (ad_id, ad["adset_id"], ad["campaign_id"]))
    ad["can_control"] = True
    return jsonify({"ad": ad, "series": series, "lifetime": {k: int(v) for k, v in totals.items()},
                    "leads": leads, "proposals": proposals, "changes": changes,
                    "formats": [{"id": f, "label": label} for f, label in PREVIEW_FORMATS]})


@bp.get("/ads/ad/<ad_id>/preview")
@login_required
def ad_preview(ad_id):
    row = entity("ad", ad_id)
    if not row or not can_touch(current_user(), row["campaign_id"]):
        return api_error("Ad not found", 404)
    fmt = request.args.get("format", "MOBILE_FEED_STANDARD")
    if fmt not in dict(PREVIEW_FORMATS):
        return api_error("Unknown preview format", 400)
    try:
        body = meta_client.get(f"{ad_id}/previews", ad_format=fmt)
    except meta_client.MetaError as exc:
        return api_error(f"Meta couldn't render this preview: {exc}", 400)
    data = (body.get("data") or [{}])[0]
    src = preview_src(data.get("body"))
    if not src:
        return api_error("Meta has no preview for this placement", 404)
    width, height = preview_size(data.get("body"))
    return jsonify({"src": src, "format": fmt, "width": width, "height": height})


# ---------------------------------------------------------------- write

def _target(level, entity_id):
    if level not in LEVELS:
        return None, api_error("Unknown level", 400)
    row = entity(level, entity_id)
    if not row:
        return None, api_error("Not found. Refresh the page.", 404)
    if not can_touch(current_user(), row["campaign_id"]):
        return None, api_error("This campaign isn't assigned to you", 403)
    return row, None


@bp.post("/ads/<level>/<entity_id>/status")
@login_required
def set_status(level, entity_id):
    row, err = _target(level, entity_id)
    if err:
        return err
    status = ((request.get_json(silent=True) or {}).get("status") or "").upper()
    if status not in ("ACTIVE", "PAUSED"):
        return api_error("status must be ACTIVE or PAUSED", 400)
    error = apply_status(current_user(), level, row, status)
    if error:
        return api_error(f"Meta refused: {error}", 400)
    return jsonify(entity(level, entity_id))


@bp.post("/ads/<level>/<entity_id>/budget")
@login_required
def set_budget(level, entity_id):
    if level not in ("campaign", "adset"):
        return api_error("Budgets live on campaigns or ad sets", 400)
    row, err = _target(level, entity_id)
    if err:
        return err
    try:
        cents = int((request.get_json(silent=True) or {}).get("daily_budget_cents"))
    except (TypeError, ValueError):
        return api_error("Enter the new daily budget in dollars", 400, field="budget")
    if cents < 100:
        return api_error("The daily budget must be at least $1", 400, field="budget")
    error = apply_budget(current_user(), level, row, cents)
    if error:
        return api_error(error if "level up" in error else f"Meta refused: {error}", 400)
    return jsonify(entity(level, entity_id))


@bp.post("/ads/ad/<ad_id>/duplicate")
@login_required
def duplicate(ad_id):
    row, err = _target("ad", ad_id)
    if err:
        return err
    name = ((request.get_json(silent=True) or {}).get("name") or f"{row['name']} - copy").strip()[:200]
    user = current_user()
    try:
        out = meta_client.post(f"{ad_id}/copies", status_option="PAUSED")
        new_id = out.get("copied_ad_id") or (out.get("ad_object_ids") or [{}])[0].get("copied_id")
        if not new_id:
            raise meta_client.MetaError("Meta didn't return the new ad's id")
        meta_client.post(new_id, name=name)
    except meta_client.MetaError as exc:
        record(user, "ad", row, "duplicate", row["name"], name, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    record(user, "ad", {**row, "name": name}, "duplicate", row["name"], name, True, entity_id=new_id)
    try:
        insights.sync_structure()
    except meta_client.MetaError:
        pass
    return jsonify({"id": new_id}), 201


# ---------------------------------------------------------------- media + new ads

def _account():
    return settings_store.get("meta_ad_account_id")


def _may_create(user):
    ids = visible_campaign_ids(user)
    return ids is None or bool(ids)


@bp.get("/media")
@login_required
def media_library():
    if not _may_create(current_user()):
        return api_error("No campaigns are assigned to you", 403)
    try:
        images = meta_client.get(f"act_{_account()}/adimages", fields="hash,url,name,width,height,created_time",
                                 limit=60).get("data", [])
        videos = meta_client.get(f"act_{_account()}/advideos", fields="id,title,picture,length,created_time,status",
                                 limit=60).get("data", [])
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't load the media library: {exc}", 400)
    items = [{"kind": "image", "hash": i["hash"], "url": i.get("url"), "name": i.get("name"),
              "width": i.get("width"), "height": i.get("height"), "created_time": i.get("created_time")} for i in images]
    items += [{"kind": "video", "video_id": v["id"], "url": v.get("picture"), "name": v.get("title"),
               "length": v.get("length"), "created_time": v.get("created_time"),
               "ready": ((v.get("status") or {}).get("video_status") == "ready")} for v in videos]
    items.sort(key=lambda i: i.get("created_time") or "", reverse=True)
    return jsonify({"items": items})


def _upload_video(path, size, name):
    account = _account()
    start = meta_client.post(f"act_{account}/advideos", upload_phase="start", file_size=str(size), timeout=60, video=True)
    session, video_id = start["upload_session_id"], start["video_id"]
    lo, hi = int(start["start_offset"]), int(start["end_offset"])
    with open(path, "rb") as fh:
        while lo < hi:
            fh.seek(lo)
            chunk = fh.read(hi - lo)
            step = meta_client.post(f"act_{account}/advideos", data={"upload_phase": "transfer",
                                    "upload_session_id": session, "start_offset": str(lo)},
                                    files={"video_file_chunk": (name, chunk, "application/octet-stream")},
                                    timeout=300, video=True)
            lo, hi = int(step["start_offset"]), int(step["end_offset"])
    meta_client.post(f"act_{account}/advideos", upload_phase="finish", upload_session_id=session, title=name,
                     timeout=60, video=True)
    return video_id


@bp.post("/media/upload")
@login_required
def upload():
    user = current_user()
    if not _may_create(user):
        return api_error("No campaigns are assigned to you", 403)
    f = request.files.get("file")
    if not f or not f.filename:
        return api_error("Choose a file", 400)
    kind = "image" if f.mimetype in IMAGE_TYPES else "video" if f.mimetype in VIDEO_TYPES else None
    if not kind:
        return api_error("Use a JPG or PNG image, or an MP4 or MOV video", 400)
    name = os.path.basename(f.filename)[:120]
    fd, path = tempfile.mkstemp(prefix="ebads-upload-")
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        size = os.path.getsize(path)
        if size > (MAX_IMAGE if kind == "image" else MAX_VIDEO):
            return api_error(f"That file is too big (images up to 30 MB, videos up to 250 MB)", 400)
        if kind == "image":
            with open(path, "rb") as fh:
                out = meta_client.post(f"act_{_account()}/adimages", files={"filename": (name, fh, f.mimetype)}, timeout=120)
            img = next(iter((out.get("images") or {}).values()), {})
            result = {"kind": "image", "hash": img.get("hash"), "url": img.get("url"), "name": name}
        else:
            result = {"kind": "video", "video_id": _upload_video(path, size, name), "name": name, "ready": False}
    except meta_client.MetaError as exc:
        return api_error(f"Meta refused the upload: {exc}", 400)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    log_activity("meta.media_uploaded", subject=result.get("hash") or result.get("video_id"),
                 details={"kind": kind, "name": name})
    return jsonify(result), 201


def _video_state(video_id):
    v = meta_client.get(video_id, fields="status,thumbnails{uri,is_preferred,width},picture")
    thumbs = (v.get("thumbnails") or {}).get("data", [])
    best = next((t for t in thumbs if t.get("is_preferred")), None) or (thumbs[0] if thumbs else {})
    return {"video_id": video_id, "ready": (v.get("status") or {}).get("video_status") == "ready",
            "processing": (v.get("status") or {}).get("processing_progress"),
            "thumbnail_url": best.get("uri") or v.get("picture")}


@bp.get("/media/video/<video_id>")
@login_required
def video_status(video_id):
    try:
        return jsonify(_video_state(video_id))
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)


@bp.get("/ads/new/options")
@login_required
def new_options():
    user = current_user()
    aw, ap = _scope(user, "s.campaign_id")
    adsets = db.query(f"""SELECT s.id, s.name, c.name AS campaign_name FROM adsets s
                          JOIN campaigns c ON c.id = s.campaign_id WHERE {aw} ORDER BY c.name, s.name""", ap)
    tw, tp = _scope(user, "campaign_id")
    templates = db.query(f"""SELECT id, name, adset_id, title, body, cta_type, image_url, object_type
                             FROM ads WHERE {tw} ORDER BY created_time DESC NULLS LAST""", tp)
    return jsonify({"adsets": adsets, "templates": templates, "cta_types": CTA_TYPES})


@bp.post("/ads/new")
@login_required
def create_ad():
    user = current_user()
    data = request.get_json(silent=True) or {}
    adset = db.query("SELECT id, name, campaign_id FROM adsets WHERE id = %s", (data.get("adset_id"),), one=True)
    template = db.query("SELECT id, name, creative_id, campaign_id FROM ads WHERE id = %s",
                        (data.get("template_ad_id"),), one=True)
    if not adset or not template:
        return api_error("Pick the ad set and the ad to start from", 400)
    if not can_touch(user, adset["campaign_id"]) or not can_touch(user, template["campaign_id"]):
        return api_error("This campaign isn't assigned to you", 403)
    name = (data.get("name") or "").strip()[:200]
    body = (data.get("body") or "").strip()
    title = (data.get("title") or "").strip()[:255]
    media = data.get("media") or {}
    cta = data.get("cta_type") or None
    if not name or not body or not title:
        return api_error("Give the ad a name, primary text and a headline", 400)
    if media.get("kind") not in ("image", "video") or not (media.get("hash") or media.get("video_id")):
        return api_error("Choose an image or video", 400)
    if cta and cta not in CTA_TYPES:
        return api_error("Unknown button", 400)
    try:
        if media["kind"] == "video":
            state = _video_state(media["video_id"])
            if not state["ready"]:
                return api_error("Meta is still processing that video. Try again in a minute.", 409)
            media["thumbnail_url"] = state["thumbnail_url"]
        try:
            tpl = meta_client.get(template["creative_id"], fields="object_story_spec,degrees_of_freedom_spec")
        except meta_client.MetaError:
            tpl = meta_client.get(template["creative_id"], fields="object_story_spec")
        if not tpl.get("object_story_spec"):
            return api_error("That ad can't be used as a starting point (it has no single image or video). Pick another.", 400)
        spec = build_story_spec(tpl.get("object_story_spec") or {}, media, body, title, cta)
        payload = {"name": f"{name} creative", "object_story_spec": json.dumps(spec)}
        if tpl.get("degrees_of_freedom_spec"):
            payload["degrees_of_freedom_spec"] = json.dumps(tpl["degrees_of_freedom_spec"])
        creative = meta_client.post(f"act_{_account()}/adcreatives", data=payload)
        ad = meta_client.post(f"act_{_account()}/ads", data={
            "name": name, "adset_id": adset["id"], "status": "PAUSED",
            "creative": json.dumps({"creative_id": creative["id"]})})
    except meta_client.MetaError as exc:
        record(user, "ad", {"id": template["id"], "name": name, "campaign_id": adset["campaign_id"]},
               "create", None, name, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    record(user, "ad", {"id": ad["id"], "name": name, "campaign_id": adset["campaign_id"]}, "create", None, name, True)
    try:
        insights.sync_structure()
    except meta_client.MetaError:
        pass
    return jsonify({"id": ad["id"]}), 201


# ---------------------------------------------------------------- proposals

@bp.post("/proposals/<int:proposal_id>/<decision>")
@login_required
def decide(proposal_id, decision):
    if decision not in ("approve", "decline"):
        return api_error("approve or decline", 400)
    user = current_user()
    p = db.query("SELECT * FROM desk_proposals WHERE id = %s", (proposal_id,), one=True)
    if not p:
        return api_error("Proposal not found", 404)
    if p["status"] != "pending":
        return api_error("This proposal was already decided", 409)
    level, row = find_entity(p["entity_id"]) if p.get("entity_id") else (None, None)
    if row and not can_touch(user, row["campaign_id"]):
        return api_error("This campaign isn't assigned to you", 403)
    if not row and user["role"] != "admin":
        return api_error("Only admins can decide account-wide proposals", 403)

    def close(status):
        db.execute("UPDATE desk_proposals SET status = %s, decided_by = %s, decided_at = now() WHERE id = %s",
                   (status, user["id"], proposal_id))
        log_activity(f"proposal.{status}", subject=str(proposal_id), details={"title": p["title"]})

    if decision == "decline":
        close("declined")
        return jsonify({"status": "declined"})
    action = proposal_action(p, row)
    if not action:
        close("approved")
        return jsonify({"status": "approved", "applied": False,
                        "note": "Recorded. This one isn't a simple on/off or budget change, so nothing was changed on Meta."})
    kind, value = action
    error = (apply_status(user, level, row, value, proposal_id) if kind == "status"
             else apply_budget(user, level, row, value, proposal_id))
    close("failed" if error else "applied")
    if error:
        return api_error(f"Approved, but Meta refused the change: {error}", 400)
    return jsonify({"status": "applied", "applied": True})


@bp.post("/ads/sync")
@login_required
def sync_now():
    try:
        out = insights.sync_all(days=30)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    return jsonify(out)
