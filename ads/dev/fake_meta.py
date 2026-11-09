"""Local development only: a stand-in for the Graph API endpoints the Ads console
uses, shaped like the real Edge Bourne account, with in-memory state so on/off,
budgets, duplicates, uploads and new ads can be exercised without touching Meta.
Run by docker-compose.dev.yml as `fake-meta`; the backend points at it with
META_GRAPH_BASE=http://fake-meta:5001/v24.0."""
import hashlib
import itertools
import json
import random
from datetime import date, timedelta

from flask import Flask, jsonify, request

app = Flask(__name__)
ACCOUNT = "1025971549903293"
PAGE = "1404203629446490"
FORM = "1132280359202136"
ids = itertools.count(120252700000000000)
TODAY = date.today()

CAMPAIGN = {"id": "120252638288040312", "name": "Edge Bourne - Free intro call - Leads", "status": "ACTIVE",
            "effective_status": "ACTIVE", "objective": "OUTCOME_LEADS", "daily_budget": "2000",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP"}
ADSET = {"id": "120252672227950312", "name": "SoCal business owners - Instant form", "campaign_id": CAMPAIGN["id"],
         "status": "ACTIVE", "effective_status": "ACTIVE", "optimization_goal": "LEAD_GENERATION",
         "learning_stage_info": {"status": "LEARNING"},
         "targeting": {"age_min": 25, "age_max": 65,
                       "geo_locations": {"custom_locations": [{"radius": 50, "distance_unit": "mile"}] * 4},
                       "flexible_spec": [{"interests": [{"name": "Small business owners"}, {"name": "Entrepreneurship"}],
                                          "behaviors": [{"name": "Business page admins"}]}],
                       "targeting_automation": {"advantage_audience": 1}}}
TEXTS = {
    "N1 - One simple system": ("Everything in one system", "Notepads, spreadsheets, sticky notes, sales reports by hand. It works until the business grows.\nWe bring it all into one simple system your team can use. AI can handle the routine updates, if you want it. You own it.\nFree intro call for Southern California businesses."),
    "N2 - Order portal": ("Orders that come in on their own", "Customers order any time, even at 2 AM. Email orders get read in automatically.\nFree intro call for Southern California businesses."),
    "N3 - Same work twice": ("Stop typing the same thing twice", "Your shop software and your books don't talk, so someone retypes everything. We connect them.\nFree intro call for Southern California businesses."),
    "N4 - Weekly report": ("Your Monday report, already done", "No more Sunday nights pulling numbers. The report builds itself and lands in your inbox.\nFree intro call for Southern California businesses."),
    "N5 - Quote to invoice": ("From quote to invoice in one place", "Quotes, jobs and invoices in one place, with follow-ups that go out on time.\nFree intro call for Southern California businesses."),
}
# Same-origin pictures served by the dev nginx from ads/dev/media (copies of the real N1-N5 frames).
PIC = "/dev-media/N1.jpg"
ADS, CREATIVES, VIDEOS, IMAGES, UPLOADS = {}, {}, {}, {}, {}


def cta():
    return {"type": "BOOK_TRAVEL", "value": {"lead_gen_form_id": FORM}}


REAL_AD_IDS = ["120252672229040312", "120252672229400312", "120252672230740312", "120252672232030312", "120252672233160312"]
for i, (name, (title, body)) in enumerate(TEXTS.items()):
    vid, cid, aid = str(next(ids)), str(next(ids)), REAL_AD_IDS[i]
    pic = f"/dev-media/N{i + 1}.jpg"
    VIDEOS[vid] = {"id": vid, "title": f"{name}.mp4", "picture": pic, "length": 9.0, "status": {"video_status": "ready"},
                   "created_time": f"{TODAY.isoformat()}T13:2{i}:00-0800"}
    CREATIVES[cid] = {"id": cid, "object_type": "VIDEO", "title": title, "body": body, "call_to_action_type": "BOOK_TRAVEL",
                      "video_id": vid, "thumbnail_url": pic, "effective_object_story_id": f"{PAGE}_12209837790354{i}159",
                      "object_story_spec": {"page_id": PAGE, "video_data": {"video_id": vid, "image_url": pic, "message": body,
                                                                           "title": title, "call_to_action": cta()}},
                      "degrees_of_freedom_spec": {"creative_features_spec": {"standard_enhancements": {"enroll_status": "OPT_OUT"}}}}
    ADS[aid] = {"id": aid, "name": name, "campaign_id": CAMPAIGN["id"], "adset_id": ADSET["id"], "status": "ACTIVE",
                "effective_status": "ACTIVE", "creative_id": cid,
                "created_time": (TODAY - timedelta(days=9)).isoformat() + "T13:30:00-0800"}


def by_id(oid):
    if oid == CAMPAIGN["id"]:
        return CAMPAIGN
    if oid == ADSET["id"]:
        return ADSET
    return ADS.get(oid) or CREATIVES.get(oid) or VIDEOS.get(oid)


def effective(ad):
    if CAMPAIGN["status"] == "PAUSED":
        return "CAMPAIGN_PAUSED"
    if ADSET["status"] == "PAUSED":
        return "ADSET_PAUSED"
    return ad["status"]


def ad_view(ad):
    cr = CREATIVES[ad["creative_id"]]
    return {**{k: v for k, v in ad.items() if k != "creative_id"}, "effective_status": effective(ad),
            "creative": {k: cr.get(k) for k in ("id", "object_type", "title", "body", "call_to_action_type",
                                                  "video_id", "image_url", "thumbnail_url", "effective_object_story_id") if cr.get(k)}}


def insights_rows(level):
    rows = []
    rng = random.Random(7)
    for d in range(10, -1, -1):
        day = (TODAY - timedelta(days=d)).isoformat()
        for ad in ADS.values():
            if ad["id"] not in {a["id"] for a in list(ADS.values())[:5]}:
                continue
            spend = round(rng.uniform(2.5, 5.5), 2)
            imps = int(spend * rng.uniform(70, 110))
            leads = rng.choice([0, 0, 0, 1, 1, 2])
            v3 = int(imps * rng.uniform(.22, .38))
            thru = int(v3 * rng.uniform(.25, .45))
            acts = [{"action_type": "video_view", "value": str(v3)}]
            if leads:
                acts.append({"action_type": "onsite_conversion.lead_grouped", "value": str(leads)})
            va = lambda n: [{"action_type": "video_view", "value": str(n)}]
            rows.append({"date_start": day, "date_stop": day, "ad_id": ad["id"], "ad_name": ad["name"],
                         "adset_id": ad["adset_id"], "campaign_id": ad["campaign_id"], "spend": str(spend),
                         "impressions": str(imps), "reach": str(int(imps * .8)), "inline_link_clicks": str(int(imps * .012)),
                         "clicks": str(int(imps * .03)), "actions": acts,
                         "video_thruplay_watched_actions": va(thru), "video_p25_watched_actions": va(int(v3 * .7)),
                         "video_p50_watched_actions": va(int(v3 * .45)), "video_p75_watched_actions": va(int(v3 * .3)),
                         "video_p100_watched_actions": va(int(v3 * .2))})
    if level == "campaign":
        today = [r for r in rows if r["date_start"] == TODAY.isoformat()]
        return [{"campaign_id": CAMPAIGN["id"], "spend": str(round(sum(float(r["spend"]) for r in today) * .6, 2)),
                 "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": "1"}]}]
    return rows


BREAKDOWN_VALUES = {
    "age": [{"age": a} for a in ("25-34", "35-44", "45-54", "55-64", "65+")],
    "gender": [{"gender": g} for g in ("male", "female", "unknown")],
    "publisher_platform,platform_position": [{"publisher_platform": p, "platform_position": q} for p, q in (
        ("facebook", "feed"), ("instagram", "stream"), ("instagram", "reels"), ("facebook", "facebook_reels"),
        ("instagram", "story"), ("facebook", "marketplace"), ("audience_network", "classic"))],
    "impression_device": [{"impression_device": d} for d in ("iphone", "android_smartphone", "desktop", "ipad")],
    "region": [{"region": r} for r in ("California", "Nevada", "Arizona")],
    "hourly_stats_aggregated_by_audience_time_zone": [{"hourly_stats_aggregated_by_audience_time_zone": f"{h:02d}:00:00 - {h:02d}:59:59"} for h in range(6, 23)],
}


def breakdown_rows(by):
    rng = random.Random(len(by))
    out = []
    for i, v in enumerate(BREAKDOWN_VALUES.get(by, [])):
        w = rng.uniform(.3, 1.6) / (1 + i * .35)
        out.append({**v, "spend": str(round(40 * w, 2)), "impressions": str(int(3600 * w)), "reach": str(int(2900 * w)),
                    "inline_link_clicks": str(int(40 * w)),
                    "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": str(int(6 * w))}]})
    return out


@app.route("/v24.0/<path:path>", methods=["GET", "POST"])
def graph(path):
    a = {**request.args.to_dict(), **request.form.to_dict()}
    parts = path.strip("/").split("/")
    act = f"act_{ACCOUNT}"
    if request.method == "GET":
        if parts == ["me"]:
            return jsonify({"id": "1", "name": "ads-console (fake)"})
        if parts == [act]:
            return jsonify({"name": "Edge Bourne Consulting", "currency": "USD", "timezone_name": "America/Los_Angeles",
                            "spend_cap": "15000", "amount_spent": "4120", "account_status": 1})
        if parts == [act, "campaigns"]:
            return jsonify({"data": [CAMPAIGN]})
        if parts == [act, "adsets"]:
            return jsonify({"data": [ADSET]})
        if parts == [act, "ads"]:
            return jsonify({"data": [ad_view(x) for x in ADS.values()]})
        if len(parts) == 2 and parts[1] == "insights":
            if a.get("breakdowns"):
                return jsonify({"data": breakdown_rows(a["breakdowns"])})
            if parts[0] == act:
                return jsonify({"data": insights_rows(a.get("level"))})
            return jsonify({"data": [{"quality_ranking": "AVERAGE", "engagement_rate_ranking": "ABOVE_AVERAGE",
                                      "conversion_rate_ranking": "BELOW_AVERAGE_35", "frequency": "1.42", "cpm": "13.80",
                                      "ctr": "2.9", "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4"}]}]})
        if parts == [act, "activities"]:
            return jsonify({"data": [
                {"event_time": TODAY.isoformat() + "T21:36:00+0000", "event_type": "ad_review_approved",
                 "translated_event_type": "Ad approved", "actor_name": "Meta", "object_name": "N5 - Quote to invoice", "object_type": "AD"},
                {"event_time": TODAY.isoformat() + "T21:27:00+0000", "event_type": "update_campaign_budget",
                 "translated_event_type": "Campaign budget updated", "actor_name": "Eugene", "object_name": CAMPAIGN["name"],
                 "object_type": "CAMPAIGN", "extra_data": json.dumps({"old_value": {"new_value": 2000, "currency": "USD"}, "new_value": 2400})}]})
        if len(parts) == 2 and parts[1] == "delivery_estimate":
            return jsonify({"data": [{"estimate_mau_lower_bound": 1_400_000, "estimate_mau_upper_bound": 1_650_000,
                                      "estimate_dau": [{"min_reach": 900, "max_reach": 2600}], "estimate_ready": True}]})
        if len(parts) == 2 and parts[1] == "comments":
            return jsonify({"data": [
                {"id": "c1", "message": "How much does something like this cost?", "created_time": TODAY.isoformat() + "T18:02:00+0000",
                 "from": {"name": "Daniel K."}, "like_count": 1, "comment_count": 0},
                {"id": "c2", "message": "We still do invoices in Excel lol", "created_time": TODAY.isoformat() + "T16:40:00+0000",
                 "from": {"name": "Maria L."}, "like_count": 3, "comment_count": 1}], "summary": {"total_count": 2}})
        if parts == [PAGE]:
            return jsonify({"id": PAGE, "name": "Edge Bourne Consulting", "access_token": "fake-page-token"})
        if parts == [act, "adimages"]:
            return jsonify({"data": list(IMAGES.values())})
        if parts == [act, "advideos"]:
            return jsonify({"data": list(VIDEOS.values())})
        if len(parts) == 2 and parts[1] == "previews":
            fmt = a.get("ad_format", "MOBILE_FEED_STANDARD")
            src = f"https://www.facebook.com/ads/api/preview_iframe.php?d=fake-{parts[0]}&amp;t=fake&amp;f={fmt}"
            return jsonify({"data": [{"body": f'<iframe src="{src}" width="320" height="560" scrolling="yes" style="border: none;"></iframe>'}]})
        if len(parts) == 1:
            obj = by_id(parts[0])
            if obj is None:
                return jsonify({"error": {"message": "Unsupported get request (fake)", "code": 100}}), 400
            if parts[0] in VIDEOS:
                return jsonify({**obj, "thumbnails": {"data": [{"uri": obj["picture"], "is_preferred": True, "width": 1080}]}})
            return jsonify(obj)
    else:
        if parts == [act, "adimages"]:
            f = request.files.get("filename")
            data = f.read() if f else b""
            h = hashlib.md5(data).hexdigest()
            IMAGES[h] = {"hash": h, "url": PIC, "name": f.filename if f else "image", "width": 1080, "height": 1350,
                         "created_time": TODAY.isoformat()}
            return jsonify({"images": {IMAGES[h]["name"]: IMAGES[h]}})
        if parts == [act, "advideos"]:
            phase = a.get("upload_phase")
            if phase == "start":
                sid, vid, size = str(next(ids)), str(next(ids)), int(a["file_size"])
                UPLOADS[sid] = {"video_id": vid, "size": size, "got": 0}
                return jsonify({"upload_session_id": sid, "video_id": vid, "start_offset": "0",
                                "end_offset": str(min(size, 1_048_576))})
            up = UPLOADS[a["upload_session_id"]]
            if phase == "transfer":
                chunk = request.files["video_file_chunk"].read()
                up["got"] = int(a["start_offset"]) + len(chunk)
                return jsonify({"start_offset": str(up["got"]), "end_offset": str(min(up["size"], up["got"] + 1_048_576))})
            VIDEOS[up["video_id"]] = {"id": up["video_id"], "title": a.get("title"), "picture": PIC, "length": 9.0,
                                      "status": {"video_status": "ready"}, "created_time": TODAY.isoformat()}
            return jsonify({"success": up["got"] == up["size"]})
        if parts == [act, "adcreatives"]:
            spec = json.loads(a["object_story_spec"])
            media = spec.get("video_data") or spec.get("link_data")
            cid = str(next(ids))
            CREATIVES[cid] = {"id": cid, "object_type": "VIDEO" if "video_data" in spec else "SHARE",
                              "title": media.get("title") or media.get("name"), "body": media.get("message"),
                              "call_to_action_type": (media.get("call_to_action") or {}).get("type"),
                              "video_id": media.get("video_id"), "image_url": PIC if "link_data" in spec else None,
                              "thumbnail_url": PIC, "object_story_spec": spec}
            return jsonify({"id": cid})
        if parts == [act, "ads"]:
            aid = str(next(ids))
            ADS[aid] = {"id": aid, "name": a["name"], "campaign_id": CAMPAIGN["id"], "adset_id": a["adset_id"],
                        "status": a.get("status", "PAUSED"), "creative_id": json.loads(a["creative"])["creative_id"],
                        "created_time": TODAY.isoformat() + "T12:00:00-0800"}
            return jsonify({"id": aid})
        if len(parts) == 2 and parts[1] == "copies" and parts[0] in ADS:
            src = ADS[parts[0]]
            aid = str(next(ids))
            ADS[aid] = {**src, "id": aid, "status": "PAUSED", "name": src["name"] + " - Copy"}
            return jsonify({"copied_ad_id": aid})
        if len(parts) == 1:
            obj = by_id(parts[0])
            if obj is None:
                return jsonify({"error": {"message": "Object does not exist (fake)", "code": 100}}), 400
            if "daily_budget" in a and int(a["daily_budget"]) < 100:
                return jsonify({"error": {"message": "Budget too low (fake)", "code": 100}}), 400
            for key in ("status", "daily_budget", "name"):
                if key in a:
                    obj[key] = a[key]
            if "status" in a:
                obj["effective_status"] = a["status"]
            return jsonify({"success": True})
    return jsonify({"error": {"message": f"fake Graph: {request.method} /{path} not implemented", "code": 100}}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
