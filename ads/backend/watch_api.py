"""Watch: the ads as a viewer sees them, one after another, with their sound. GET /api/ads/watch gives what the player
draws for each ad (words, picture, button, the Page's name, its numbers for the dates) and /api/ads/ad/<id>/video its
video from this origin: fetched from Meta once, kept in a folder and served with ranges, so the player can seek and
the console's media-src 'self' holds. Reads only: nothing here writes to Meta."""
import fcntl
import logging
import os
import time

import requests
from flask import Blueprint, jsonify, request, send_file

import ads_api
import config
import db
import meta_client
import ranges
import account_info
import settings_store
import watch
from auth import current_user, login_required, visible_campaign_ids
from util import api_error

bp = Blueprint("watch", __name__, url_prefix="/api")
log = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("ADS_VIDEO_CACHE", "/tmp/ebads-videos")
PAGE_NAMES = {}          # page id -> (name, read at)
PAGE_NAME_SECONDS = 3600


def page_name():
    page = settings_store.get("meta_page_id")
    if not page:
        return None
    hit = PAGE_NAMES.get(page)
    if hit and time.time() - hit[1] < PAGE_NAME_SECONDS:
        return hit[0]
    try:
        name = str(meta_client.get(page, fields="name").get("name") or "")[:200] or None
    except meta_client.MetaError:
        name = hit[0] if hit else None
    PAGE_NAMES[page] = (name, time.time())
    return name


def _visible(rows):
    ids = visible_campaign_ids(current_user())
    return [r for r in rows if ids is None or r["campaign_id"] in ids]


@bp.get("/ads/watch")
@login_required
def watch_list():
    ids = watch.parse_ids(request.args.get("ids"))
    if not ids:
        return api_error("Name the ads to watch", 400)
    rows = _visible(db.query("""SELECT id, name, campaign_id, status, effective_status, object_type, title, body, cta_type,
                                       video_id, image_url, thumbnail_url FROM ads WHERE id = ANY(%s)""", (ids,)))
    key, start, end = ads_api.window_from(request.args, live=True)  # the dates the Ads page and the ad page show
    shown = [r["id"] for r in rows]
    metrics = ads_api._metrics("ad_id = ANY(%s)", [shown], start, end) if shown else {}
    by_id = {r["id"]: r for r in rows}
    items = []
    for ad_id in ids:
        r = by_id.get(ad_id)
        if not r:
            continue
        items.append({k: r[k] for k in ("id", "name", "status", "effective_status", "object_type", "title", "body", "cta_type",
                                        "image_url", "thumbnail_url")}
                     | {"video": f"/api/ads/ad/{ad_id}/video" if r["video_id"] else None, "m": metrics.get(ad_id, {})})
    return jsonify({"items": items, "page": {"name": page_name()},
                    "range": {"key": key, "label": ranges.label(start, end, today=account_info.today())}})


def video_source(video_id, story_id):
    """The link of the video's file. Meta may keep it from the console's own key, so it is asked three ways: the video
    with the System User's key, the video with the Page's key, the ad's post with the Page's key. LookupError says why
    none answered."""
    dev = bool(config.META_GRAPH_BASE)
    why = []

    def page_key():
        return meta_client.page_token()

    asks = [("the video", lambda: meta_client.get(video_id, fields="source").get("source")),
            ("the video, as the Page", lambda: meta_client.get(video_id, token=page_key(), fields="source").get("source"))]
    if story_id:
        asks.append(("the ad's post, as the Page", lambda: watch.story_source(meta_client.get(
            story_id, token=page_key(), fields="attachments{media,subattachments{media}}"))))
    for what, ask in asks:
        try:
            src = ask()
        except meta_client.MetaError as exc:
            why.append(f"{what}: {exc}")
            continue
        if watch.allowed_source(src, dev=dev):
            return src
        why.append(f"{what}: no file link")
    raise LookupError("Meta didn't share this video's file (" + "; ".join(why) + ")")


def _fetch(video_id, story_id, path):
    """Download the video Meta keeps for `video_id` into `path` (once, even with two requests at the same time)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(path):
            return
        src = video_source(video_id, story_id)
        part = f"{path}.part"
        got = 0
        try:
            with requests.get(src, stream=True, timeout=(10, 90)) as resp:
                resp.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in resp.iter_content(256 * 1024):
                        got += len(chunk)
                        if got > watch.MAX_VIDEO_BYTES:
                            raise LookupError("This video is too large to play here")
                        f.write(chunk)
            os.replace(part, path)
        finally:
            if os.path.exists(part):
                os.remove(part)
    watch.prune(CACHE_DIR, keep=(path,))


@bp.get("/ads/ad/<ad_id>/video")
@login_required
def ad_video(ad_id):
    rows = _visible(db.query("SELECT id, campaign_id, video_id, story_id FROM ads WHERE id = %s", (ad_id,)))
    if not rows:
        return api_error("Ad not found", 404)
    path = watch.cache_file(CACHE_DIR, rows[0]["video_id"])
    if not path:
        return api_error("This ad has no video", 404)
    if not os.path.exists(path):
        try:
            _fetch(rows[0]["video_id"], rows[0]["story_id"], path)
        except LookupError as exc:
            log.warning("watch: ad %s video %s: %s", ad_id, rows[0]["video_id"], exc)
            return api_error(str(exc), 502)
        except (requests.RequestException, OSError) as exc:
            log.warning("watch: ad %s video %s download: %s", ad_id, rows[0]["video_id"], exc)
            return api_error("The video couldn't be fetched from Meta. Try again in a minute.", 502)
    try:
        os.utime(path)  # recently watched videos are the last to be trimmed
    except OSError:
        pass
    resp = send_file(path, mimetype="video/mp4", conditional=True, max_age=3600)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.keep_cache = True
    return resp
