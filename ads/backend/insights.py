"""Pull ads, daily per-ad results and the account spending cap from Meta."""
import json
from datetime import date, timedelta

import account_info
import db
import meta_client
import settings_store
import status_history

INSIGHT_FIELDS = ("ad_id,ad_name,adset_id,campaign_id,spend,impressions,reach,inline_link_clicks,clicks,actions,"
                  "video_thruplay_watched_actions,video_p25_watched_actions,video_p50_watched_actions,"
                  "video_p75_watched_actions,video_p100_watched_actions")
# Instant-form leads appear under these action types; take the first that is present.
LEAD_ACTIONS = ("onsite_conversion.lead_grouped", "lead", "leadgen_grouped")


def lead_count(actions):
    by_type = {a.get("action_type"): a.get("value") for a in actions or []}
    for key in LEAD_ACTIONS:
        if by_type.get(key) not in (None, ""):
            return int(float(by_type[key]))
    return 0


def action_value(actions, action_type=None):
    """Sum of an *_actions list, or of one action type inside `actions`."""
    total = 0
    for a in actions or []:
        if action_type is None or a.get("action_type") == action_type:
            try:
                total += int(float(a.get("value") or 0))
            except (TypeError, ValueError):
                pass
    return total


def to_cents(value):
    return int(round(float(value or 0) * 100))


CREATIVE_FIELDS = "{id,object_type,title,body,call_to_action_type,video_id,image_url,thumbnail_url,effective_object_story_id}"
AD_BASE = ("id,name,campaign_id,adset_id,status,configured_status,effective_status,ad_review_feedback,issues_info,"
           "created_time,updated_time,")
# Larger creative thumbnails when Meta accepts the sizing parameters; plain fields otherwise.
AD_FIELDS = AD_BASE + "creative.thumbnail_width(720).thumbnail_height(900)" + CREATIVE_FIELDS
AD_FIELDS_PLAIN = AD_BASE + "creative" + CREATIVE_FIELDS


def video_picture(video_id, cache):
    """The video's preferred full-size frame (the creative thumbnail is tiny)."""
    if video_id in cache:
        return cache[video_id]
    try:
        thumbs = meta_client.get(video_id, fields="thumbnails{uri,is_preferred,width}").get("thumbnails", {}).get("data", [])
    except meta_client.MetaError:
        thumbs = []
    best = next((t for t in thumbs if t.get("is_preferred")), None) or (max(thumbs, key=lambda t: t.get("width") or 0) if thumbs else None)
    cache[video_id] = best.get("uri") if best else None
    return cache[video_id]


AD_UPSERT = """INSERT INTO ads (id, name, campaign_id, adset_id, status, configured_status, effective_status,
                                thumbnail_url, review_feedback, issues, creative_id, object_type, title, body, cta_type,
                                video_id, image_url, created_time, updated_time, story_id, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, campaign_id = EXCLUDED.campaign_id,
                   adset_id = EXCLUDED.adset_id, status = EXCLUDED.status,
                   configured_status = EXCLUDED.configured_status,
                   effective_status = EXCLUDED.effective_status, thumbnail_url = EXCLUDED.thumbnail_url,
                   review_feedback = EXCLUDED.review_feedback, issues = EXCLUDED.issues,
                   creative_id = EXCLUDED.creative_id, object_type = EXCLUDED.object_type,
                   title = EXCLUDED.title, body = EXCLUDED.body, cta_type = EXCLUDED.cta_type,
                   video_id = EXCLUDED.video_id,
                   image_url = CASE WHEN EXCLUDED.image_url IS NULL AND EXCLUDED.creative_id IS NOT DISTINCT FROM ads.creative_id
                                    THEN ads.image_url ELSE EXCLUDED.image_url END,
                   created_time = EXCLUDED.created_time, updated_time = EXCLUDED.updated_time,
                   story_id = EXCLUDED.story_id, synced_at = now()
               """ + status_history.UNLESS_CONSOLE_WROTE.format(table="ads")


def stored_pictures():
    """The video frames already stored, so a sync asks Meta only about new videos. Meta's picture links
    expire, so once a day (account time) every one is read again (audit A3-82, A3-124)."""
    if settings_store.get("video_pictures_day") != account_info.today().isoformat():
        return {}
    return {r["video_id"]: r["image_url"] for r in db.query(
        "SELECT DISTINCT ON (video_id) video_id, image_url FROM ads WHERE video_id IS NOT NULL AND image_url IS NOT NULL "
        "ORDER BY video_id, synced_at DESC")}


def upsert_ad(ad, source, pictures, listed_at):
    """Store one ad as Meta returned it and record what changed since the last pull."""
    cr = ad.get("creative") or {}
    image = cr.get("image_url") or (video_picture(cr["video_id"], pictures) if cr.get("video_id") else None)
    prev, written = status_history.upsert_tracked("ad", ad["id"], AD_UPSERT, (
        ad["id"], ad["name"], ad.get("campaign_id"), ad.get("adset_id"), ad.get("status"),
        ad.get("configured_status"), ad.get("effective_status"), cr.get("thumbnail_url"),
        json.dumps(ad.get("ad_review_feedback")) if ad.get("ad_review_feedback") else None,
        json.dumps(ad.get("issues_info")) if ad.get("issues_info") else None,
        cr.get("id"), cr.get("object_type"), cr.get("title"), cr.get("body"), cr.get("call_to_action_type"),
        cr.get("video_id"), image, ad.get("created_time"), ad.get("updated_time"), cr.get("effective_object_story_id"),
        listed_at))
    if not written:
        return []
    if prev and prev.get("creative_id") and cr.get("id") and prev["creative_id"] != cr["id"]:
        import versions_api
        versions_api.save_switch({**prev, "id": ad["id"]}, cr["id"], versions_api.OUTSIDE, title=cr.get("title"), body=cr.get("body"))
    return status_history.track("ad", ad, prev, source)


def sync_ads(source="poll"):
    import sync
    account = settings_store.get("meta_ad_account_id")
    pictures = stored_pictures()
    fresh = not pictures
    listed_at = db.now()
    rows = sync.listing(f"act_{account}/ads", AD_FIELDS, AD_FIELDS_PLAIN)
    for ad in rows:
        upsert_ad(ad, source, pictures, listed_at)
    if fresh:
        settings_store.set("video_pictures_day", account_info.today().isoformat())
    # Ads deleted in Ads Manager stop appearing in the listing; keep their history, hide them.
    # Meta's list leaves archived ads out too: mark_missing asks Meta which of the two each one is.
    status_history.mark_missing("ad", [ad["id"] for ad in rows], source, listed_at)
    return len(rows)


def sync_structure():
    """Campaigns, ad sets and ads (no insights): after a change made from the dashboard."""
    import sync
    return {"campaigns": sync.sync_campaigns(), "adsets": sync.sync_adsets(), "ads": sync_ads()}


def sync_daily(days=30):
    until = account_info.today()
    return sync_days(until - timedelta(days=days - 1), until)


def sync_days(since, until):
    """Per-ad results for each day from `since` to `until` (account days), stored in ad_daily."""
    account = settings_store.get("meta_ad_account_id")
    rows = 0
    for r in meta_client.paged(
        f"act_{account}/insights",
        level="ad", time_increment=1, fields=INSIGHT_FIELDS, limit=500,
        time_range=json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
    ):
        db.execute(
            """INSERT INTO ad_daily (day, ad_id, campaign_id, adset_id, ad_name, spend_cents, impressions,
                                     reach, link_clicks, leads, clicks_all, video_3s, thruplays,
                                     video_p25, video_p50, video_p75, video_p100, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (day, ad_id) DO UPDATE SET spend_cents = EXCLUDED.spend_cents,
                   impressions = EXCLUDED.impressions, reach = EXCLUDED.reach,
                   link_clicks = EXCLUDED.link_clicks, leads = EXCLUDED.leads,
                   clicks_all = EXCLUDED.clicks_all, video_3s = EXCLUDED.video_3s, thruplays = EXCLUDED.thruplays,
                   video_p25 = EXCLUDED.video_p25, video_p50 = EXCLUDED.video_p50,
                   video_p75 = EXCLUDED.video_p75, video_p100 = EXCLUDED.video_p100,
                   ad_name = EXCLUDED.ad_name, synced_at = now()""",
            (r["date_start"], r["ad_id"], r.get("campaign_id"), r.get("adset_id"), r.get("ad_name"),
             to_cents(r.get("spend")), int(r.get("impressions") or 0), int(r.get("reach") or 0),
             int(r.get("inline_link_clicks") or 0), lead_count(r.get("actions")), int(r.get("clicks") or 0),
             action_value(r.get("actions"), "video_view"), action_value(r.get("video_thruplay_watched_actions")),
             action_value(r.get("video_p25_watched_actions")), action_value(r.get("video_p50_watched_actions")),
             action_value(r.get("video_p75_watched_actions")), action_value(r.get("video_p100_watched_actions"))),
        )
        rows += 1
    return rows


def sync_account():
    account = settings_store.get("meta_ad_account_id")
    a = meta_client.get(f"act_{account}",
                        fields="name,currency,timezone_name,spend_cap,amount_spent,account_status")
    settings_store.set("account_snapshot", json.dumps({
        "name": a.get("name"),
        "currency": a.get("currency"),
        "timezone": a.get("timezone_name"),
        # Meta reports both in the account currency's minor units, as strings.
        "spend_cap_cents": int(a["spend_cap"]) if a.get("spend_cap") not in (None, "", "0") else None,
        "amount_spent_cents": int(a.get("amount_spent") or 0),
        "account_status": a.get("account_status"),
    }))
    import account_info
    problem = account_info.currency_problem(a.get("currency"))
    if problem:
        raise meta_client.MetaError(problem)


def sync_all(days=30, structure=True):
    """structure=False: only the results (the worker's hourly week when a pull has just read the rest)."""
    sync_account()  # first: the account's time zone and currency decide how the rest is read
    out = {**(sync_structure() if structure else {}), "daily_rows": sync_daily(days)}
    settings_store.set("last_performance_sync", __import__("datetime").datetime.utcnow().isoformat() + "Z")
    return out


def _fetch_many(ids, fields, fallback):
    """Meta's multi-id read (?ids=a,b), with the older field set if a new field is refused, and one by
    one if an id no longer exists (Meta refuses the whole batch then). Only ids that are gone are left out:
    anything else Meta didn't answer is raised, so webhook events stay pending (audit A3-83)."""
    import sync
    out = {}
    for chunk in (ids[i:i + 50] for i in range(0, len(ids), 50)):
        try:
            out.update(sync.with_fallback(lambda f: meta_client.get("", ids=",".join(chunk), fields=f), fields, fallback,
                                          shape="ids"))
        except meta_client.MetaError as exc:
            if meta_client.transient(exc):
                raise
            for one in chunk:
                try:
                    out[one] = sync.with_fallback(lambda f: meta_client.get(one, fields=f), fields, fallback, shape="one")
                except meta_client.MetaError as exc:
                    if not meta_client.not_found(exc):
                        raise
    return out


def sync_entities(level, ids, source="webhook"):
    """Read these campaigns, ad sets or ads again (a webhook named them) and record what changed."""
    import sync
    if level == "creative":
        rows = db.query("SELECT id FROM ads WHERE creative_id = ANY(%s)", (list(ids),))
        level, ids = "ad", [r["id"] for r in rows]
    if not ids:
        return []
    events = []
    listed_at = db.now()
    if level == "ad":
        pictures = stored_pictures()
        for ad in _fetch_many(list(ids), AD_FIELDS, AD_FIELDS_PLAIN).values():
            events += upsert_ad(ad, source, pictures, listed_at)
    elif level == "adset":
        for a in _fetch_many(list(ids), sync.ADSET_FIELDS, sync.ADSET_FIELDS_PLAIN).values():
            events += sync.upsert_adset(a, source, listed_at)
    elif level == "campaign":
        for c in _fetch_many(list(ids), sync.CAMPAIGN_FIELDS, sync.CAMPAIGN_FIELDS_PLAIN).values():
            events += sync.upsert_campaign(c, source, listed_at)
    return events


# ---------------------------------------------------------------- today so far

def today_for(raw, day):
    """The stored today-by-campaign snapshot when it was taken on `day` (account time), else None: a
    snapshot from yesterday must never be added to today's spend (audit A3-13, A3-47)."""
    snap = json.loads(raw) if raw else None
    return snap if snap and snap.get("day") == day.isoformat() else None


def stored_today():
    return today_for(settings_store.get("today_snapshot"), account_info.today())


def pull_today(timeout=meta_client.TIMEOUT):
    """Spend and leads so far today per campaign, read from Meta and stored with the day they belong to."""
    import time
    account = settings_store.get("meta_ad_account_id")
    day = account_info.today()
    rows = list(meta_client.paged(f"act_{account}/insights", timeout=timeout, level="campaign", date_preset="today",
                                  fields="campaign_id,spend,actions", limit=100))
    snap = {"at": time.time(), "day": day.isoformat(),
            "campaigns": {r["campaign_id"]: {"spend_cents": to_cents(r.get("spend")), "leads": lead_count(r.get("actions"))}
                          for r in rows}}
    settings_store.set("today_snapshot", json.dumps(snap))
    return snap


# ---------------------------------------------------------------- results from before the first sync

BACKFILL_LIMIT = timedelta(days=37 * 30)  # Meta keeps per-day results about 37 months
BACKFILL_CHUNK = 90


def backfill_windows(earliest, first_synced, today, chunk=BACKFILL_CHUNK):
    """(since, until) windows covering the days from `earliest` (when the oldest campaign or ad started)
    to the day before the first stored day (yesterday when nothing is stored yet)."""
    end = (first_synced or today) - timedelta(days=1)
    start = max(earliest, today - BACKFILL_LIMIT)
    out = []
    while start <= end:
        out.append((start, min(end, start + timedelta(days=chunk - 1))))
        start += timedelta(days=chunk)
    return out


def backfill_daily():
    """Once per ad account: per-day results from before the first sync, so "since it started" and every
    all-time figure cover the whole life of older ads, not just the synced days (audit A3-60)."""
    account = settings_store.get("meta_ad_account_id")
    if not account or settings_store.get("daily_backfill_for") == account:
        return 0
    tz = account_info.tz_name()
    earliest = db.query(
        """SELECT MIN(d) AS d FROM (SELECT (MIN(created_time) AT TIME ZONE %s)::date AS d FROM ads
                                    UNION ALL SELECT (MIN(created_time) AT TIME ZONE %s)::date FROM campaigns) x""",
        (tz, tz), one=True)["d"]
    first = db.query("SELECT MIN(day) AS d FROM ad_daily", one=True)["d"]
    rows = 0
    for since, until in backfill_windows(earliest, first, account_info.today()) if earliest else []:
        rows += sync_days(since, until)
    settings_store.set("daily_backfill_for", account)
    return rows


# ---------------------------------------------------------------- unique reach
# Reach is the number of different people. It can't be added up day by day (someone who saw the ad
# on Monday and Tuesday counts once), nor across ads, so each window is asked from Meta as a whole.
REACH_ID = {"ad": "ad_id", "adset": "adset_id", "campaign": "campaign_id", "account": "account_id"}


def reach_map(level, rows):
    key = REACH_ID[level]
    if level == "account":
        return {"account": sum(int(r.get("reach") or 0) for r in rows)}
    return {r[key]: int(r.get("reach") or 0) for r in rows if r.get(key)}


def apply_reach(rows, reach, field):
    """Put Meta's unique reach on rows[field]; without it keep the daily sum and say so."""
    for r in rows:
        m = r.get(field)
        if m is None:
            continue
        if reach is None:
            m["reach_summed"] = True
        else:
            m["reach"] = reach.get(r["id"], 0)


def reach_key(level, start=None, end=None, preset=None):
    return f"reach:{level}:{preset or f'{start}:{end}'}"


def _reach_read(account, level, start, end, preset):
    window = {"date_preset": preset} if preset else {"time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()})}
    return f"act_{account}/insights", {"level": level, "fields": f"{REACH_ID[level]},reach", "limit": 500, **window}


def reach_many(wanted, stale_ok=True, timeout=None):
    """{name: {id: people} or None} for several windows at once, `wanted` = {name: (level, start, end, preset, ttl)}
    (preset is a Meta date preset such as "maximum"). What meta_cache holds younger than its ttl is used as
    is; the rest is asked from Meta together, in parallel with a short timeout, so a page waits for one read,
    not one after another (audit A3-46). A window Meta doesn't answer keeps its last stored answer when
    stale_ok and that answer is under a day old (insights_api.STALE_MAX), else None (the caller then adds up daily reach and says so), and isn't asked again for a
    couple of minutes."""
    import insights_api
    account = settings_store.get("meta_ad_account_id")
    if not account or not wanted:
        return {n: None for n in wanted}
    keys = {n: reach_key(*spec[:4]) for n, spec in wanted.items()}
    stored = insights_api.cache_rows(set(keys.values()))
    out, todo = {}, {}
    def stand_in(key):
        data, age = stored.get(key, (None, None))
        return data if stale_ok and data is not None and age < insights_api.STALE_MAX else None
    for n, (level, start, end, preset, ttl) in wanted.items():
        data, age = stored.get(keys[n], (None, None))
        if data is not None and age < ttl:
            out[n] = data
        elif meta_client.recently_failed(keys[n]):
            out[n] = stand_in(keys[n])
        else:
            todo.setdefault(keys[n], ((level, start, end, preset), []))[1].append(n)
    reads = [_reach_read(account, *spec) for spec, _ in todo.values()]
    answers = meta_client.read_many(reads, timeout=timeout or meta_client.READ_TIMEOUT)
    for (key, ((level, *_), names)), rows in zip(todo.items(), answers):
        if isinstance(rows, meta_client.MetaError):
            meta_client.remember_failure(key, rows)
            value = stand_in(key)
        else:
            value = reach_map(level, rows)
            insights_api.store(key, value)
        for n in names:
            out[n] = value
    return out


def unique_reach(level, start=None, end=None, preset=None, ttl=1800):
    """{id: people} for one window (or a Meta date preset such as "maximum"), cached; None when Meta doesn't answer.
    For the worker: no stale answer, and Meta's full timeout."""
    return reach_many({"r": (level, start, end, preset, ttl)}, stale_ok=False, timeout=meta_client.TIMEOUT)["r"]


def lifetime_reach(ad_id):
    """People who saw the ad since it started; the ad page waits on it, so a short timeout and, when Meta
    doesn't answer, the last stored figure (audit A3-123)."""
    import insights_api

    def fetch():
        rows = meta_client.get(f"{ad_id}/insights", timeout=meta_client.READ_TIMEOUT, date_preset="maximum",
                               fields="reach").get("data", [])
        return {"reach": int(rows[0].get("reach") or 0) if rows else 0}
    try:
        return insights_api.cached(f"reach:life:{ad_id}", 1800, fetch, stale_ok=True)["reach"]
    except meta_client.MetaError:
        return None
