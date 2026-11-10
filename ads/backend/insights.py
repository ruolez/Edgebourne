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
                   video_id = EXCLUDED.video_id, image_url = EXCLUDED.image_url,
                   created_time = EXCLUDED.created_time, updated_time = EXCLUDED.updated_time,
                   story_id = EXCLUDED.story_id, synced_at = now()"""


def upsert_ad(ad, source, pictures):
    """Store one ad as Meta returned it and record what changed since the last pull."""
    cr = ad.get("creative") or {}
    image = cr.get("image_url") or (video_picture(cr["video_id"], pictures) if cr.get("video_id") else None)
    prev = status_history.upsert_tracked("ad", ad["id"], AD_UPSERT, (
        ad["id"], ad["name"], ad.get("campaign_id"), ad.get("adset_id"), ad.get("status"),
        ad.get("configured_status"), ad.get("effective_status"), cr.get("thumbnail_url"),
        json.dumps(ad.get("ad_review_feedback")) if ad.get("ad_review_feedback") else None,
        json.dumps(ad.get("issues_info")) if ad.get("issues_info") else None,
        cr.get("id"), cr.get("object_type"), cr.get("title"), cr.get("body"), cr.get("call_to_action_type"),
        cr.get("video_id"), image, ad.get("created_time"), ad.get("updated_time"), cr.get("effective_object_story_id")))
    return status_history.track("ad", ad, prev, source)


def sync_ads(source="poll"):
    account = settings_store.get("meta_ad_account_id")
    pictures = {}
    try:
        rows = list(meta_client.paged(f"act_{account}/ads", fields=AD_FIELDS, limit=100))
    except meta_client.MetaError:
        rows = list(meta_client.paged(f"act_{account}/ads", fields=AD_FIELDS_PLAIN, limit=100))
    for ad in rows:
        upsert_ad(ad, source, pictures)
    # Ads deleted in Ads Manager stop appearing in the listing; keep their history, hide them.
    # Meta's list leaves archived ads out; keep them archived rather than calling them deleted.
    status_history.mark_missing("ad", [ad["id"] for ad in rows], source)
    return len(rows)


def sync_structure():
    """Campaigns, ad sets and ads (no insights): after a change made from the dashboard."""
    import sync
    return {"campaigns": sync.sync_campaigns(), "adsets": sync.sync_adsets(), "ads": sync_ads()}


def sync_daily(days=30):
    account = settings_store.get("meta_ad_account_id")
    until = account_info.today()
    since = until - timedelta(days=days - 1)
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


def sync_all(days=30):
    sync_account()  # first: the account's time zone and currency decide how the rest is read
    out = {**sync_structure(), "daily_rows": sync_daily(days)}
    settings_store.set("last_performance_sync", __import__("datetime").datetime.utcnow().isoformat() + "Z")
    return out
