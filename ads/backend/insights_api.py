"""On-demand reads from Meta that are too detailed to sync hourly: who saw an ad
(age, gender, placement, device, region, hour), Meta's quality rankings, comments on
the ad's post, Meta's own change history and audience-size estimates. Each answer is
cached briefly in meta_cache so flipping between tabs doesn't hammer the API."""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import account_info
import ranges
import db
import insights
import meta_client
import settings_store
from ads_api import ad_funnel, can_touch, entity
from auth import admin_required, current_user, login_required
from util import api_error

bp = Blueprint("insights", __name__, url_prefix="/api/insights")

BREAKDOWNS = {
    "age": ("age", "Age"),
    "gender": ("gender", "Gender"),
    "placement": ("publisher_platform,platform_position", "Placement"),
    "device": ("impression_device", "Device"),
    "region": ("region", "Region"),
    "hour": ("hourly_stats_aggregated_by_audience_time_zone", "Hour of day"),
}
PLACEMENT_NAMES = {
    ("facebook", "feed"): "Facebook feed", ("facebook", "facebook_reels"): "Facebook Reels",
    ("facebook", "facebook_stories"): "Facebook Stories", ("facebook", "marketplace"): "Marketplace",
    ("facebook", "video_feeds"): "Facebook video feeds", ("facebook", "search"): "Facebook search",
    ("facebook", "facebook_reels_overlay"): "Reels overlay", ("facebook", "instream_video"): "In-stream video",
    ("facebook", "right_hand_column"): "Right column", ("facebook", "profile_feed"): "Profile feed",
    ("instagram", "stream"): "Instagram feed", ("instagram", "story"): "Instagram Stories",
    ("instagram", "reels"): "Instagram Reels", ("instagram", "explore"): "Instagram Explore",
    ("instagram", "explore_home"): "Explore home", ("instagram", "profile_feed"): "Instagram profile",
    ("messenger", "messenger_inbox"): "Messenger inbox", ("messenger", "story"): "Messenger Stories",
    ("audience_network", "classic"): "Audience Network", ("threads", "threads_stream"): "Threads",
}
RANKINGS = {"ABOVE_AVERAGE": "Above average", "AVERAGE": "Average", "BELOW_AVERAGE_35": "Below average (bottom 35%)",
            "BELOW_AVERAGE_20": "Below average (bottom 20%)", "BELOW_AVERAGE_10": "Below average (bottom 10%)",
            "UNKNOWN": "Not enough data yet"}


# The oldest stored answer that may stand in for one Meta didn't give: older, a figure such as reach since it
# started would sit next to current views and understate both without saying so.
STALE_MAX = 86400


def cached(key, ttl_seconds, fetch, stale_ok=False):
    """meta_cache[key] while younger than the ttl, else fetch() and store it. A read Meta left unanswered
    isn't tried again for a couple of minutes (meta_client.recently_failed); with stale_ok the last stored
    answer (if under a day old) stands in meanwhile, otherwise the error is raised."""
    row = db.query("SELECT data, EXTRACT(EPOCH FROM now() - fetched_at) AS age FROM meta_cache WHERE key = %s",
                   (key,), one=True)
    if row and row["age"] < ttl_seconds:
        return row["data"]
    try:
        failed = meta_client.recently_failed(key)
        if failed:
            raise failed
        try:
            data = fetch()
        except meta_client.MetaError as exc:
            meta_client.remember_failure(key, exc)
            raise
    except meta_client.MetaError:
        if stale_ok and row and row["age"] < STALE_MAX:
            return row["data"]
        raise
    store(key, data)
    return data


def cache_rows(keys):
    """{key: (data, age in seconds)} for the stored ones of these keys, in one query."""
    if not keys:
        return {}
    return {r["key"]: (r["data"], float(r["age"])) for r in db.query(
        "SELECT key, data, EXTRACT(EPOCH FROM now() - fetched_at) AS age FROM meta_cache WHERE key = ANY(%s)", (list(keys),))}


def store(key, data):
    db.execute("""INSERT INTO meta_cache (key, data, fetched_at) VALUES (%s, %s, now())
                  ON CONFLICT (account_id, key) DO UPDATE SET data = EXCLUDED.data, fetched_at = now()""", (key, json.dumps(data)))


def breakdown_label(by, row):
    if by == "placement":
        key = (row.get("publisher_platform"), row.get("platform_position"))
        return PLACEMENT_NAMES.get(key) or " ".join(filter(None, key)).replace("_", " ").title()
    if by == "hour":
        raw = row.get("hourly_stats_aggregated_by_audience_time_zone") or ""
        try:
            h = int(raw[:2])
        except ValueError:
            return raw
        return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
    value = row.get(BREAKDOWNS[by][0]) or "unknown"
    return {"male": "Men", "female": "Women", "unknown": "Unknown"}.get(value, value.replace("_", " ").title() if by == "device" else value)


def shape_breakdown(by, rows):
    out = {}
    for r in rows:
        label = breakdown_label(by, r)
        o = out.setdefault(label, {"label": label, "spend_cents": 0, "impressions": 0, "reach": 0, "link_clicks": 0, "leads": 0})
        o["spend_cents"] += insights.to_cents(r.get("spend"))
        o["impressions"] += int(r.get("impressions") or 0)
        o["reach"] += int(r.get("reach") or 0)
        o["link_clicks"] += int(r.get("inline_link_clicks") or 0)
        o["leads"] += insights.lead_count(r.get("actions"))
    items = list(out.values())
    if by == "hour":
        def hour_key(i):
            t = i["label"].split()
            return (0 if t[-1] == "AM" else 12) + (int(t[0]) % 12) if len(t) == 2 and t[0].isdigit() else 99
        items.sort(key=hour_key)
    elif by == "age":
        items.sort(key=lambda i: i["label"])
    else:
        items.sort(key=lambda i: -i["spend_cents"])
    return items


def time_params(range_key):
    if range_key == "lifetime":
        return {"date_preset": "maximum"}, "lifetime"
    start, end = ranges.window(range_key, account_info.today())
    return {"time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()})}, f"{start}..{end}"


def _scoped(level, entity_id):
    user = current_user()
    if level == "account":
        return None if user["role"] == "admin" else api_error("Only admins can see account-wide numbers", 403)
    row = entity(level, entity_id)
    if not row or not can_touch(user, row["campaign_id"]):
        return api_error("Not found", 404)
    return None


@bp.get("/breakdown")
@login_required
def breakdown():
    level = request.args.get("level", "ad")
    entity_id = request.args.get("id", "")
    by = request.args.get("by", "age")
    if level not in ("account", "campaign", "adset", "ad") or by not in BREAKDOWNS:
        return api_error("Unknown breakdown", 400)
    err = _scoped(level, entity_id)
    if err:
        return err
    params, period = time_params(request.args.get("range", "7"))
    node = f"act_{settings_store.get('meta_ad_account_id')}" if level == "account" else entity_id
    key = f"bd:{node}:{by}:{period}"

    def fetch():
        rows = list(meta_client.paged(f"{node}/insights", fields="spend,impressions,reach,inline_link_clicks,actions",
                                      breakdowns=BREAKDOWNS[by][0], limit=200, **params))
        return shape_breakdown(by, rows)
    try:
        items = cached(key, 3600, fetch)
    except meta_client.MetaError as exc:
        return api_error(f"Meta couldn't break this down: {exc}", 400)
    return jsonify({"by": by, "label": BREAKDOWNS[by][1], "period": period, "items": items})


@bp.get("/ad/<ad_id>/diagnostics")
@login_required
def diagnostics(ad_id):
    err = _scoped("ad", ad_id)
    if err:
        return err

    def fetch():
        rows = meta_client.get(f"{ad_id}/insights", date_preset="last_30d",
                               fields="quality_ranking,engagement_rate_ranking,conversion_rate_ranking,frequency,cpm,ctr,"
                                      "video_avg_time_watched_actions").get("data", [])
        return rows[0] if rows else {}
    try:
        meta = cached(f"diag:{ad_id}", 3600, fetch)
    except meta_client.MetaError as exc:
        meta = {"error": str(exc)}
    funnel = ad_funnel(ad_id)
    avg = insights.action_value(meta.get("video_avg_time_watched_actions"))
    return jsonify({
        "rankings": {k: {"value": meta.get(k), "label": RANKINGS.get(meta.get(k) or "UNKNOWN", meta.get(k))}
                     for k in ("quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking")},
        "frequency": float(meta["frequency"]) if meta.get("frequency") else None,
        "cpm_cents": insights.to_cents(meta.get("cpm")) if meta.get("cpm") else None,
        "avg_watch_seconds": avg or None,
        "funnel": funnel,
        "error": meta.get("error"),
    })


@bp.get("/ad/<ad_id>/comments")
@login_required
def comments(ad_id):
    err = _scoped("ad", ad_id)
    if err:
        return err
    row = db.query("SELECT story_id FROM ads WHERE id = %s", (ad_id,), one=True)
    story = row and row["story_id"]
    if not story:
        return jsonify({"items": [], "total": 0, "post_url": None, "note": "Meta hasn't linked a post to this ad yet."})

    def fetch():
        import comments as cm
        token = meta_client.page_token()
        body = meta_client.get(f"{story}/comments", token=token,
                               fields="id,message,created_time,from{name,id},like_count,comment_count,is_hidden,can_hide,"
                                      "comments.limit(10){id,message,created_time,from{name,id}}",
                               order="reverse_chronological", summary="true", filter="toplevel", limit=50)
        page_id = settings_store.get("meta_page_id")
        return {"items": [cm.shape(c, page_id) for c in body.get("data", [])],
                "total": (body.get("summary") or {}).get("total_count", len(body.get("data", [])))}
    try:
        data = cached(f"comments:{story}", 300, fetch)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the comments: {exc}", 400)
    page, post = (story.split("_", 1) + [""])[:2]
    return jsonify({**data, "post_url": f"https://www.facebook.com/{page}/posts/{post}"})


def _comment_target(ad_id, comment_id):
    """(ad row, error response) for a comment on this ad's own post, for someone allowed to act."""
    import comments as cm
    err = _scoped("ad", ad_id)
    if err:
        return None, err
    row = db.query("SELECT id, name, campaign_id, story_id FROM ads WHERE id = %s", (ad_id,), one=True)
    if not row or not cm.belongs(comment_id, row["story_id"]):
        return None, api_error("That comment isn't on this ad's post", 404)
    return row, None


@bp.post("/ad/<ad_id>/comments/<comment_id>/reply")
@login_required
def reply_comment(ad_id, comment_id):
    """Reply as the Page. Shown publicly under the comment."""
    import ads_api
    import comments as cm
    row, err = _comment_target(ad_id, comment_id)
    if err:
        return err
    text, problem = cm.clean_reply((request.get_json(silent=True) or {}).get("message"))
    if problem:
        return api_error(problem, 400, field="message")
    with db.try_lock(f"reply:{comment_id}") as mine:
        if not mine:
            return api_error("This reply is already being posted", 409)
        if db.query("""SELECT 1 FROM meta_changes WHERE action = 'comment_reply' AND ok AND old_value = %s AND new_value = %s
                       AND created_at > now() - interval '2 minutes'""", (comment_id, text[:200]), one=True):
            return api_error("You already posted this reply a moment ago", 409)
        try:
            made = meta_client.post(f"{comment_id}/comments", token=meta_client.page_token(), data={"message": text})
        except meta_client.MetaError as exc:
            ads_api.record(current_user(), "ad", row, "comment_reply", comment_id, text[:200], False, str(exc))
            return api_error(f"Facebook refused the reply: {exc}", 400)
        ads_api.record(current_user(), "ad", row, "comment_reply", comment_id, text[:200], True)
    db.execute("DELETE FROM meta_cache WHERE key = %s", (f"comments:{row['story_id']}",))
    return jsonify({"id": made.get("id")})


@bp.post("/ad/<ad_id>/comments/<comment_id>/hide")
@login_required
def hide_comment(ad_id, comment_id):
    """Hide or show a comment. Hidden comments stay visible to their writer and friends; nothing is deleted."""
    import ads_api
    row, err = _comment_target(ad_id, comment_id)
    if err:
        return err
    hidden = bool((request.get_json(silent=True) or {}).get("hidden"))
    try:
        meta_client.post(comment_id, token=meta_client.page_token(), data={"is_hidden": "true" if hidden else "false"})
    except meta_client.MetaError as exc:
        ads_api.record(current_user(), "ad", row, "comment_hide" if hidden else "comment_show", comment_id, None, False, str(exc))
        return api_error(f"Facebook refused: {exc}", 400)
    ads_api.record(current_user(), "ad", row, "comment_hide" if hidden else "comment_show", comment_id, None, True)
    db.execute("DELETE FROM meta_cache WHERE key = %s", (f"comments:{row['story_id']}",))
    return jsonify({"hidden": hidden})


@bp.get("/adset/<adset_id>/estimate")
@login_required
def estimate(adset_id):
    err = _scoped("adset", adset_id)
    if err:
        return err

    def fetch():
        rows = meta_client.get(f"{adset_id}/delivery_estimate",
                               fields="estimate_mau_lower_bound,estimate_mau_upper_bound,estimate_ready").get("data", [])
        return rows[0] if rows else {}
    try:
        e = cached(f"estimate:{adset_id}", 6 * 3600, fetch)
    except meta_client.MetaError as exc:
        return api_error(f"Meta has no estimate: {exc}", 400)
    return jsonify({"lower": e.get("estimate_mau_lower_bound"), "upper": e.get("estimate_mau_upper_bound"),
                    "ready": e.get("estimate_ready")})


def _plain(v):
    return v.get("new_value", v.get("value")) if isinstance(v, dict) else v


ACTIVITY_LEVELS = {"CAMPAIGN": "campaign", "AD_SET": "adset", "ADSET": "adset", "AD": "ad"}


def activity_object(row):
    """The campaign, ad set or ad one of Meta's history lines is about, so the page can link to it."""
    level = ACTIVITY_LEVELS.get((row or {}).get("object_type") or "")
    return {"level": level, "id": str(row["object_id"])} if level and row.get("object_id") else None


def activity_values(event_type, extra):
    """Old and new value of one of Meta's history lines. Budget and spend-limit amounts are minor units (cents)
    and come marked `money`, so the page writes them in the account currency, never as a bare 2000 (audit A3-38)."""
    extra = extra if isinstance(extra, dict) else {}
    old, new = extra.get("old_value"), extra.get("new_value")
    kind = event_type or ""
    money = (any(w in kind for w in ("budget", "spend_cap", "spend_limit")) or "currency" in extra
             or any(isinstance(v, dict) and "currency" in v for v in (old, new)))
    old, new = _plain(old), _plain(new)
    if money:
        try:
            return {"old": None if old is None else int(float(old)), "new": None if new is None else int(float(new)), "money": True}
        except (TypeError, ValueError):
            pass  # not an amount after all: shown as Meta wrote it
    return {"old": old, "new": new, "money": False}


@bp.get("/activity")
@admin_required
def activity():
    """Meta's own change history for the account: edits from Ads Manager, the
    dashboard, Claude or Meta's automatic changes, side by side."""
    days = max(1, min(90, int(request.args.get("days", "14") or 14)))
    since = (account_info.today() - timedelta(days=days)).isoformat()

    def fetch():
        rows = meta_client.get(f"act_{settings_store.get('meta_ad_account_id')}/activities", since=since, limit=100,
                               fields="event_time,event_type,translated_event_type,actor_name,object_id,object_name,object_type,extra_data"
                               ).get("data", [])
        out = []
        for r in rows:
            extra = r.get("extra_data")
            try:
                extra = json.loads(extra) if isinstance(extra, str) else extra
            except ValueError:
                pass
            out.append({"time": r.get("event_time"), "what": r.get("translated_event_type") or r.get("event_type"),
                        "who": r.get("actor_name"), "object": r.get("object_name"), "type": r.get("object_type"),
                        "about": activity_object(r), **activity_values(r.get("event_type"), extra)})
        return out
    try:
        items = cached(f"activity:{since}", 600, fetch)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read Meta's history: {exc}", 400)
    return jsonify({"items": items, "days": days})
