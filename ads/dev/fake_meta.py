"""Local development only: a stand-in for the Graph API endpoints the Ads console
uses, shaped like the real Edge Bourne account, with in-memory state so on/off,
budgets, duplicates, uploads and new ads can be exercised without touching Meta.
Run by docker-compose.dev.yml as `fake-meta`; the backend points at it with
META_GRAPH_BASE=http://fake-meta:5001/v24.0."""
import hashlib
import itertools
import json
import random
from datetime import date, datetime, timedelta, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)
ACCOUNT = "1025971549903293"
PAGE = "1404203629446490"
FORM = "1132280359202136"
# Meta never reuses an id: start each run of the fake past the last one, so builds and rows a database kept
# from an earlier run never name an object this run makes.
ids = itertools.count(120252700000000000 + int(__import__("time").time()) % 1_000_000 * 10_000)
TODAY = date.today()

CAMPAIGN = {"id": "120252638288040312", "name": "Edge Bourne - Free intro call - Leads", "status": "ACTIVE",
            "effective_status": "ACTIVE", "objective": "OUTCOME_LEADS", "daily_budget": "2000",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "start_time": f"{(TODAY - timedelta(days=10)).isoformat()}T09:00:00-0800"}
ADSET = {"id": "120252672227950312", "name": "SoCal business owners - Instant form", "campaign_id": CAMPAIGN["id"],
         "status": "ACTIVE", "effective_status": "ACTIVE", "optimization_goal": "LEAD_GENERATION",
         "learning_stage_info": {"status": "LEARNING"},
         "targeting": {"age_min": 25, "age_max": 65, "age_range": [30, 64],
                       "geo_locations": {"custom_locations": [
                           {"latitude": 32.7157, "longitude": -117.1611, "radius": 50, "distance_unit": "mile", "primary_city_id": 2421830},
                           {"latitude": 33.9533, "longitude": -117.3962, "radius": 50, "distance_unit": "mile", "primary_city_id": 2421696},
                           {"latitude": 34.0522, "longitude": -118.2437, "radius": 50, "distance_unit": "mile", "primary_city_id": 2420379},
                           {"latitude": 34.2746, "longitude": -119.229, "radius": 50, "distance_unit": "mile", "primary_city_id": 2422675}],
                           "location_types": ["home", "recent"]},
                       "flexible_spec": [{"interests": [{"id": "6003371567474", "name": "Entrepreneurship"}],
                                          "behaviors": [{"id": "6002714898572", "name": "Small business owners"},
                                                        {"id": "6020530281783", "name": "Business page admins"}]}],
                       "targeting_automation": {"advantage_audience": 1}},
         "destination_type": "ON_AD", "billing_event": "IMPRESSIONS", "promoted_object": {"page_id": "1404203629446490"},
         "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "start_time": f"{(TODAY - timedelta(days=10)).isoformat()}T09:00:00-0800"}
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
CRM_EVENTS = []  # lead stages the console sent (Conversions API for CRM)


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
                      "degrees_of_freedom_spec": {"creative_features_spec": {
                          "standard_enhancements": {"enroll_status": "OPT_OUT"}, "inline_comment": {"enroll_status": "OPT_OUT"},
                          "text_optimizations": {"enroll_status": "OPT_OUT"}, "image_touchups": {"enroll_status": "OPT_IN"},
                          "video_filtering": {"enroll_status": "OPT_IN" if i == 2 else "OPT_OUT"}}}}
    ADS[aid] = {"id": aid, "name": name, "campaign_id": CAMPAIGN["id"], "adset_id": ADSET["id"], "status": "ACTIVE",
                "effective_status": "ACTIVE", "creative_id": cid,
                "created_time": (TODAY - timedelta(days=9)).isoformat() + "T13:30:00-0800"}


# FU-A: ad accounts other than Edge Bourne's that the console's key reaches (me/adaccounts and the business's lists).
# Masha Fontana Studio has its own campaign, ad set, two ads and daily results; the other two only exist as list rows.
OTHER_ACCOUNTS = {
    "2223334445556667": {"name": "Masha Fontana Studio", "currency": "USD", "timezone_name": "America/Chicago", "account_status": 1,
                         "business": {"id": "3334445556667778", "name": "Masha Braverman"}},
    "4445556667778889": {"name": "Tokyo Test KK", "currency": "JPY", "timezone_name": "Asia/Tokyo", "account_status": 1},
    "5556667778889990": {"name": "Old Shop", "currency": "USD", "timezone_name": "America/New_York", "account_status": 101},
    # Reached only by OWN_KEY_TOKEN, an account's own System User key (QA: the picker reads with the owner's key, never this one).
    "6667778889990001": {"name": "Own Key Only Shop", "currency": "USD", "timezone_name": "America/Chicago", "account_status": 1},
}
OWN_KEY_TOKEN = "fake-own-key-qa"
REACH = {"hidden": set(), "refuse_business": False}  # /fake/_adaccounts: hide accounts from every list, refuse the business lists
MASHA = "2223334445556667"
OTHER_CAMPAIGNS = {"120252799000000001": {"id": "120252799000000001", "name": "Masha - Extensions - Leads", "status": "ACTIVE",
                                          "effective_status": "ACTIVE", "objective": "OUTCOME_LEADS", "daily_budget": "1500",
                                          "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "account": MASHA,
                                          "start_time": f"{(TODAY - timedelta(days=10)).isoformat()}T09:00:00-0600"}}
OTHER_ADSETS = {"120252799000000002": {"id": "120252799000000002", "name": "Fontana women 25-55 - Instant form", "campaign_id": "120252799000000001",
                                       "status": "ACTIVE", "effective_status": "ACTIVE", "optimization_goal": "LEAD_GENERATION", "account": MASHA,
                                       "learning_stage_info": {"status": "LEARNING"}, "billing_event": "IMPRESSIONS",
                                       "targeting": {"age_min": 25, "age_max": 55, "geo_locations": {"countries": ["US"]}},
                                       "destination_type": "ON_AD", "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                                       "start_time": f"{(TODAY - timedelta(days=10)).isoformat()}T09:00:00-0600"}}
OTHER_ADS = {}
for _n, (_aid, _name, _title) in enumerate((("120252799000000003", "M1 - Before and after", "Hair that looks like yours, only more"),
                                            ("120252799000000004", "M2 - Free consult", "Book a free extensions consult"))):
    _cid = str(next(ids))
    CREATIVES[_cid] = {"id": _cid, "object_type": "PHOTO", "title": _title, "body": "Tape-in and K-tip extensions in Fontana.",
                       "call_to_action_type": "LEARN_MORE", "image_url": f"/dev-media/N{_n + 1}.jpg", "thumbnail_url": f"/dev-media/N{_n + 1}.jpg"}
    OTHER_ADS[_aid] = {"id": _aid, "name": _name, "campaign_id": "120252799000000001", "adset_id": "120252799000000002", "status": "ACTIVE",
                       "effective_status": "ACTIVE", "creative_id": _cid, "account": MASHA,
                       "created_time": (TODAY - timedelta(days=9)).isoformat() + "T10:00:00-0600"}


def other_ad_view(ad):
    cr = CREATIVES[ad["creative_id"]]
    return {**{k: v for k, v in ad.items() if k not in ("creative_id", "account")}, "configured_status": ad["status"],
            "creative": {k: cr.get(k) for k in ("id", "object_type", "title", "body", "call_to_action_type", "image_url", "thumbnail_url") if cr.get(k)}}


def other_rows(acct):
    """Masha's daily results: 10 days back and today, per ad (spend and leads unlike Edge Bourne's)."""
    rows, rng = [], random.Random(11)
    for d in range(10, -1, -1):
        day = (TODAY - timedelta(days=d)).isoformat()
        for ad in (x for x in OTHER_ADS.values() if x["account"] == acct):
            spend = round(rng.uniform(6.0, 9.5), 2)
            imps = int(spend * rng.uniform(55, 80))
            leads = rng.choice([0, 1, 1, 2, 3])
            acts = [{"action_type": "onsite_conversion.lead_grouped", "value": str(leads)}] if leads else []
            rows.append({"date_start": day, "date_stop": day, "ad_id": ad["id"], "ad_name": ad["name"], "adset_id": ad["adset_id"],
                         "campaign_id": ad["campaign_id"], "spend": str(spend), "impressions": str(imps), "reach": str(int(imps * .8)),
                         "inline_link_clicks": str(int(imps * .015)), "clicks": str(int(imps * .03)), "actions": acts})
    return rows


def adaccount_row(acct):
    base = (OTHER_ACCOUNTS[acct] if acct in OTHER_ACCOUNTS else
            {"name": "Edge Bourne Consulting", "currency": "USD", "timezone_name": "America/Los_Angeles", "account_status": 1,
             "business": {"id": BUSINESS, "name": "Edge Bourne"}})
    return {"id": f"act_{acct}", "account_id": acct, **base}


def reachable_list(accts):
    return jsonify({"data": [adaccount_row(x) for x in accts if x not in REACH["hidden"]]})


@app.route("/fake/_adaccounts")
def fake_adaccounts():
    """QA: ?hide=<id> hides an ad account from every list, ?refuse_business=1 makes the business lists refuse, ?clear=1 resets."""
    if request.args.get("clear"):
        REACH["hidden"].clear()
        REACH["refuse_business"] = False
    if request.args.get("hide"):
        REACH["hidden"].add(request.args["hide"])
    if "refuse_business" in request.args:
        REACH["refuse_business"] = request.args["refuse_business"] == "1"
    return jsonify({"hidden": sorted(REACH["hidden"]), "refuse_business": REACH["refuse_business"]})


def other_account_get(acct, parts, a):
    """GET on act_<one of OTHER_ACCOUNTS> and its edges."""
    if len(parts) == 1:
        return jsonify({**OTHER_ACCOUNTS[acct], "id": f"act_{acct}", "account_id": acct, **cap_fields(acct)})
    edge = parts[1]
    mine = lambda d: [x for x in d.values() if x.get("account") == acct and listed(x)]  # noqa: E731
    if edge == "campaigns":
        return jsonify({"data": [{k: v for k, v in c.items() if k != "account"} for c in mine(OTHER_CAMPAIGNS)]})
    if edge == "adsets":
        return jsonify({"data": [{k: v for k, v in s.items() if k != "account"} for s in mine(OTHER_ADSETS)]})
    if edge == "ads":
        return jsonify({"data": [other_ad_view(x) for x in mine(OTHER_ADS)]})
    if edge == "insights":
        rows = other_rows(acct)
        tr = json.loads(a.get("time_range") or "{}")
        if a.get("date_preset") == "today":
            rows = [r for r in rows if r["date_start"] == TODAY.isoformat()]
        elif tr:
            rows = [r for r in rows if tr.get("since", "") <= r["date_start"] <= tr.get("until", "9999")]
        level = a.get("level", "ad")
        if "reach" in (a.get("fields") or "") and "spend" not in (a.get("fields") or ""):
            key = {"ad": "ad_id", "adset": "adset_id", "campaign": "campaign_id", "account": "account_id"}[level]
            people = {}
            for r in rows:
                ident = acct if level == "account" else r[key]
                people[ident] = people.get(ident, 0) + int(r["reach"])
            return jsonify({"data": [{key: k, "reach": str(int(v * .62))} for k, v in people.items()]})
        if level == "account":
            by = {}
            for r in rows:
                d = by.setdefault(r["date_start"], {"spend": 0.0, "impressions": 0, "leads": 0})
                d["spend"] += float(r["spend"])
                d["impressions"] += int(r["impressions"])
                d["leads"] += sum(int(x["value"]) for x in r["actions"])
            return jsonify({"data": [{"date_start": k, "date_stop": k, "spend": f"{v['spend']:.2f}", "impressions": str(v["impressions"]),
                                      "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": str(v["leads"])}] if v["leads"] else []}
                                     for k, v in sorted(by.items())]})
        if level == "campaign":
            by = {}
            for r in rows:
                d = by.setdefault(r["campaign_id"], {"spend": 0.0, "leads": 0})
                d["spend"] += float(r["spend"])
                d["leads"] += sum(int(x["value"]) for x in r["actions"])
            return jsonify({"data": [{"campaign_id": k, "spend": f"{v['spend']:.2f}",
                                      "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": str(v["leads"])}]} for k, v in by.items()]})
        return jsonify({"data": rows})
    return jsonify({"data": []})  # activities, recommendations, adimages, advideos…: nothing yet


def by_id(oid):
    if oid in OTHER_CAMPAIGNS:
        return OTHER_CAMPAIGNS[oid]
    if oid in OTHER_ADSETS:
        return OTHER_ADSETS[oid]
    if oid in OTHER_ADS:
        return OTHER_ADS[oid]
    if oid == CAMPAIGN["id"]:
        return CAMPAIGN
    if oid == ADSET["id"]:
        return ADSET
    if oid in NEW_ADSETS:
        return NEW_ADSETS[oid]
    if oid in NEW_CAMPAIGNS:
        return NEW_CAMPAIGNS[oid]
    return ADS.get(oid) or CREATIVES.get(oid) or VIDEOS.get(oid)


REVIEW = {}            # ad id -> Meta review state the fake reports (/fake/_review)
REVIEW_ON_ACTIVATE = []  # when set, an ad turned on goes to IN_PROCESS first (/fake/_review_on_activate)
REJECTED_FEEDBACK = {"global": {"PERSONAL_ATTRIBUTES": "Ads can't imply knowledge of personal attributes."},
                     "placement_specific": {"instagram": {"PERSONAL_ATTRIBUTES": "Personal attributes"}}}
ISSUES = [{"error_code": 1487, "error_summary": "Ad account payment failed", "error_message": "Update the payment method.",
           "error_type": "HARD_ERROR", "level": "AD"}]


def effective(ad):
    review = REVIEW.get(ad.get("id"))
    if review == "DISAPPROVED":
        return review
    if ad["status"] != "ACTIVE":
        return ad["status"]
    if review in ("IN_PROCESS", "PENDING_REVIEW", "WITH_ISSUES", "PREAPPROVED"):
        return review
    camp = CAMPAIGN if ad.get("campaign_id") == CAMPAIGN["id"] else NEW_CAMPAIGNS.get(ad.get("campaign_id"), CAMPAIGN)
    aset = ADSET if ad.get("adset_id") == ADSET["id"] else NEW_ADSETS.get(ad.get("adset_id"), ADSET)
    if camp["status"] == "PAUSED":
        return "CAMPAIGN_PAUSED"
    if aset["status"] == "PAUSED":
        return "ADSET_PAUSED"
    return ad["status"]


def listed(obj):
    return obj.get("status") not in ("ARCHIVED", "DELETED")


def ad_view(ad):
    cr = CREATIVES[ad["creative_id"]]
    review = REVIEW.get(ad["id"])
    extra = {"configured_status": ad["status"]}
    if review == "DISAPPROVED":
        extra["ad_review_feedback"] = REJECTED_FEEDBACK
    if review == "WITH_ISSUES":
        extra["issues_info"] = ISSUES
    return {**{k: v for k, v in ad.items() if k != "creative_id"}, **extra, "effective_status": effective(ad),
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
    rows = restated(rows)
    if level == "campaign":
        today = [r for r in rows if r["date_start"] == TODAY.isoformat()]
        return [{"campaign_id": CAMPAIGN["id"], "spend": str(round(sum(float(r["spend"]) for r in today) * .6, 2)),
                 "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": "1"}]}]
    return rows


# D1: Meta changing an older day after the console stored it (leads credited back, spend corrections), applied to
# both the ad-level and the account-level reads, as Meta would.
RESTATE = {}     # (day, ad id) -> {"spend": dollars to add, "leads": leads to add}
DROPPED = set()  # (day, ad id): that ad-day no longer appears (its spend leaves the account total too)
SHORT = {"next": False}  # the next ad-level read for a window answers with no rows (the restate guard's test)
ACCOUNT_SHIFT = {}  # day -> {"spend": dollars, "leads": n}: Meta's account total moves while its ad rows stay (they disagree)


def restated(rows):
    out = []
    for r in rows:
        key = (r["date_start"], r["ad_id"])
        if key in DROPPED:
            continue
        ch = RESTATE.get(key)
        if ch:
            r = {**r, "spend": str(round(float(r["spend"]) + ch["spend"], 2))}
            acts = [dict(a) for a in r["actions"]]
            lead = next((a for a in acts if a["action_type"] == "onsite_conversion.lead_grouped"), None)
            if lead:
                lead["value"] = str(max(int(lead["value"]) + ch["leads"], 0))
            elif ch["leads"] > 0:
                acts.append({"action_type": "onsite_conversion.lead_grouped", "value": str(ch["leads"])})
            r["actions"] = acts
        out.append(r)
    return out


def account_days(rows):
    """level=account, time_increment=1: one row per day with spend, the per-day sums of the ads (days with nothing are left out)."""
    by = {}
    for r in rows:
        d = by.setdefault(r["date_start"], {"spend": 0.0, "impressions": 0, "leads": 0})
        d["spend"] += float(r["spend"])
        d["impressions"] += int(r["impressions"])
        d["leads"] += sum(int(a["value"]) for a in r["actions"] if a["action_type"] == "onsite_conversion.lead_grouped")
    for k, ch in ACCOUNT_SHIFT.items():
        if k in by:
            by[k]["spend"] += ch["spend"]
            by[k]["leads"] = max(by[k]["leads"] + ch["leads"], 0)
    return [{"date_start": k, "date_stop": k, "spend": f"{v['spend']:.2f}", "impressions": str(v["impressions"]),
             "actions": [{"action_type": "onsite_conversion.lead_grouped", "value": str(v["leads"])}] if v["leads"] else []}
            for k, v in sorted(by.items())]


@app.route("/fake/_restate")
def fake_restate():
    """?day=YYYY-MM-DD&ad=<id>&spend=<+-dollars>&leads=<+-n>: Meta changes an older day. ?day=&level=account&spend=&leads=:
    only Meta's account total for the day moves (its ad rows no longer add up to it). ?clear=1 puts every day back."""
    if request.args.get("clear"):
        RESTATE.clear()
        DROPPED.clear()
        ACCOUNT_SHIFT.clear()
        SHORT["next"] = False
        SLOW["daily"] = 0.0
        return jsonify({"ok": True})
    if request.args.get("level") == "account":
        old = ACCOUNT_SHIFT.get(request.args["day"], {"spend": 0.0, "leads": 0})
        ACCOUNT_SHIFT[request.args["day"]] = {"spend": round(old["spend"] + float(request.args.get("spend") or 0), 2),
                                              "leads": old["leads"] + int(request.args.get("leads") or 0)}
        return jsonify({"ok": True, "account": ACCOUNT_SHIFT})
    key = (request.args["day"], request.args["ad"])
    old = RESTATE.get(key, {"spend": 0.0, "leads": 0})
    RESTATE[key] = {"spend": old["spend"] + float(request.args.get("spend") or 0), "leads": old["leads"] + int(request.args.get("leads") or 0)}
    return jsonify({"ok": True, "restate": {f"{d}:{a}": v for (d, a), v in RESTATE.items()}})


@app.route("/fake/_restate_drop")
def fake_restate_drop():
    """?day=&ad=: that ad-day disappears from Meta's reads (credited back)."""
    DROPPED.add((request.args["day"], request.args["ad"]))
    return jsonify({"ok": True})


@app.route("/fake/_short_answer")
def fake_short_answer():
    SHORT["next"] = True
    return jsonify({"ok": True})


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


# ---- Telegram Bot API stand-in (TELEGRAM_API_BASE=http://fake-meta:5001/telegram) ----
TG_UPDATES, TG_SENT = [], []
tg_update_ids = itertools.count(1000)


@app.post("/telegram/_start")
def tg_start():
    """Test hook: someone taps Start (or types text) in the bot's chat."""
    a = request.get_json(force=True)
    chat = int(a.get("chat_id", 424242))
    TG_UPDATES.append({"update_id": next(tg_update_ids), "message": {
        "message_id": 1, "chat": {"id": chat, "type": "private"},
        "from": {"id": chat, "first_name": a.get("name", "Eugene"), "username": a.get("username", "eugene_qa")},
        "text": a.get("text") or f"/start {a['code']}"}})
    return jsonify({"ok": True})


@app.get("/telegram/_sent")
def tg_sent():
    return jsonify(TG_SENT)


@app.post("/telegram/bot<tok>/<method>")
def tg_api(tok, method):
    if tok != "123456:FAKE-token":
        return jsonify({"ok": False, "error_code": 401, "description": "Unauthorized"}), 401
    a = request.get_json(silent=True) or {}
    if method == "getMe":
        return jsonify({"ok": True, "result": {"id": 123456, "is_bot": True, "first_name": "Edge Bourne Ads", "username": "EdgeBourneAdsBot"}})
    if method == "deleteWebhook":
        return jsonify({"ok": True, "result": True})
    if method == "getUpdates":
        offset = int(a.get("offset") or 0)
        return jsonify({"ok": True, "result": [u for u in TG_UPDATES if u["update_id"] >= offset]})
    if method == "sendMessage":
        if int(a.get("chat_id", 0)) == 403:
            return jsonify({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}), 403
        TG_SENT.append(a)
        return jsonify({"ok": True, "result": {"message_id": len(TG_SENT), "chat": {"id": a.get("chat_id")}, "text": a.get("text")}})
    return jsonify({"ok": False, "error_code": 404, "description": f"fake: {method} not implemented"}), 404


BUSINESS = "9990001"
NEW_ADSETS = {}
NEW_CAMPAIGNS = {}
DATASET = "1821497329119793"  # the live dataset's id; the fake counts the lead stages it received
# Opportunity Score + recommendations: the live account's one (2026-11-09) plus a budget one to apply.
ADVICE = {"score": 87, "recs": [
    {"type": "reels_pc_recommendation", "object_ids": ["120252672227950312"], "recommendation_stage": "mid_flight_recommendation",
     "recommendation_content": {"lift_estimate": "You could get 8% lower cost per result by optimizing your Reels format",
                                "body": "Including a fullscreen vertical video (9:16) with audio in your Reels ads can improve performance.",
                                "opportunity_score_lift": "4"}, "url": "https://adsmanager.facebook.com/adsmanager/manage/accounts?act=1025971549903293"},
    {"type": "SCALE_GOOD_CAMPAIGN", "recommendation_signature": "fake-scale-1", "object_ids": ["120252638288040312"],
     "recommendation_stage": "mid_flight_recommendation", "recommendation_data": {"additional_budget": 600},
     "recommendation_content": {"lift_estimate": "Up to 18% more leads", "body": "This campaign gets leads below your average cost.",
                                "opportunity_score_lift": "9"}, "url": "https://adsmanager.facebook.com/adsmanager/manage/campaigns"}]}
REFUSE_NEXT_AD = []
FAKE_FLAGS = {}
PLACES = [{"key": "2421696", "name": "Riverside", "type": "city", "region": "California", "country_code": "US"},
          {"key": "2420379", "name": "Los Angeles", "type": "city", "region": "California", "country_code": "US"},
          {"key": "2421830", "name": "San Diego", "type": "city", "region": "California", "country_code": "US"},
          {"key": "2420886", "name": "Fontana", "type": "city", "region": "California", "country_code": "US"},
          {"key": "2422675", "name": "Ventura", "type": "city", "region": "California", "country_code": "US"},
          {"key": "3847", "name": "California", "type": "region", "country_code": "US"},
          {"key": "US:92335", "name": "92335", "type": "zip", "region": "California", "country_code": "US"}]
FORMS = {"1132280359202136": {
    "id": "1132280359202136", "name": "EB | Free AI workflow review", "status": "ACTIVE", "leads_count": 41,
    "created_time": "2026-11-07T20:00:00+0000", "locale": "EN_US", "is_optimized_for_quality": False,
    "questions": [{"type": "FULL_NAME", "key": "full_name"}, {"type": "EMAIL", "key": "email"}, {"type": "PHONE", "key": "phone_number"},
                  {"type": "CUSTOM", "key": "what_kind_of_business_do_you_run?", "label": "What kind of business do you run?",
                   "options": [{"value": "Trades", "key": "a"}, {"value": "Retail", "key": "b"}, {"value": "Professional services", "key": "c"}, {"value": "Other", "key": "d"}]}],
    "privacy_policy_url": "https://edgebourne.com/privacy",
    "context_card": {"title": "Free AI workflow review", "style": "LIST_STYLE", "content": ["20 minutes, by phone", "One thing to fix first"]},
    "thank_you_page": {"title": "Thanks! We'll call you today.", "body": "Eugene from Edge Bourne will call.", "button_type": "VIEW_WEBSITE",
                       "button_text": "Visit our website", "website_url": "https://edgebourne.com"},
    "follow_up_action_url": "https://edgebourne.com"}}
STUDIES = {}


COMMENTS = {}


def comments_for(story):
    """Two comments per post, ids shaped like Meta's (<post id>_<comment id>)."""
    post = story.split("_", 1)[-1]
    if post not in COMMENTS:
        COMMENTS[post] = [
            {"id": f"{post}_7001", "message": "How much does something like this cost?", "created_time": TODAY.isoformat() + "T18:02:00+0000",
             "from": {"name": "Daniel K.", "id": "901"}, "like_count": 1, "is_hidden": False, "can_hide": True, "comments": {"data": []}},
            {"id": f"{post}_7002", "message": "We still do invoices in Excel lol", "created_time": TODAY.isoformat() + "T16:40:00+0000",
             "from": {"name": "Maria L.", "id": "902"}, "like_count": 3, "is_hidden": False, "can_hide": True, "comments": {"data": []}}]
    return COMMENTS[post]


def find_comment(cid):
    post = cid.split("_", 1)[0]
    return next((c for c in COMMENTS.get(post, []) if c["id"] == cid), None)


@app.route("/fake/_comments")
def fake_comments():
    return jsonify(COMMENTS)


# ---- A stand-in web push service: devices register their private key here (dev only) so
# the fake can decrypt what the console sends, proving the encryption end to end.
PUSH_DEVICES, PUSH_SENT = {}, []


def _push_decrypt(body, private_b64u, auth_b64u):
    import base64
    import hashlib
    import hmac as hm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    unb = lambda t: base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
    mac = lambda k, d: hm.new(k, d, hashlib.sha256).digest()
    key = ec.derive_private_key(int.from_bytes(unb(private_b64u), "big"), ec.SECP256R1())
    ua_pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    salt, idlen = body[:16], body[20]
    as_pub, cipher = body[21:21 + idlen], body[21 + idlen:]
    ecdh = key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    prk = mac(salt, mac(mac(unb(auth_b64u), ecdh), b"WebPush: info\x00" + ua_pub + as_pub + b"\x01"))
    plain = AESGCM(mac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]).decrypt(mac(prk, b"Content-Encoding: nonce\x00\x01")[:12], cipher, None)
    return plain.rstrip(b"\x00")[:-1].decode()


@app.route("/push/_register", methods=["POST"])
def push_register():
    d = request.get_json()
    PUSH_DEVICES[d["id"]] = d
    return jsonify({"ok": True})


@app.route("/push/_sent")
def push_sent():
    return jsonify(PUSH_SENT)


@app.route("/push/<pid>", methods=["POST"])
def push_receive(pid):
    if pid.startswith("gone"):
        return "", 410
    dev = PUSH_DEVICES.get(pid)
    auth_ok = request.headers.get("Authorization", "").startswith("vapid t=") and request.headers.get("Content-Encoding") == "aes128gcm"
    if not dev or not auth_ok:
        return "", 400
    PUSH_SENT.append({"id": pid, "ttl": request.headers.get("TTL"), "payload": json.loads(_push_decrypt(request.get_data(), dev["private"], dev["auth"]))})
    return "", 201


@app.route("/fake/_review")
def fake_review():
    """Step an ad through Meta review: to=IN_PROCESS|PENDING_REVIEW|PREAPPROVED|ACTIVE|DISAPPROVED|WITH_ISSUES."""
    ad, to = request.args["ad"], request.args.get("to", "ACTIVE")
    if ad not in ADS:
        return jsonify({"error": "no such ad"}), 404
    if to == "ACTIVE":
        REVIEW.pop(ad, None)
    else:
        REVIEW[ad] = to
    return jsonify({"ad": ad, "effective_status": effective(ADS[ad])})


@app.route("/fake/_review_on_activate")
def fake_review_on_activate():
    REVIEW_ON_ACTIVATE[:] = [1] if request.args.get("on", "1") == "1" else []
    return jsonify({"on": bool(REVIEW_ON_ACTIVATE)})


@app.route("/fake/_learning")
def fake_learning():
    """Set an ad set's learning stage: to=LEARNING|SUCCESS|FAIL."""
    aset = ADSET if request.args.get("adset", ADSET["id"]) == ADSET["id"] else NEW_ADSETS[request.args["adset"]]
    aset["learning_stage_info"] = {"status": request.args.get("to", "LEARNING"), "conversions": int(request.args.get("conversions", 9)),
                                   "last_sig_edit_ts": 1762700000, "attribution_windows": ["CLICK_7", "VIEW_1"]}
    return jsonify(aset["learning_stage_info"])


SLOW = {"reach": 0.0, "daily": 0.0}  # seconds the unique-reach / ad-level daily reads hang (a slow Meta), set by QA
HITS = []  # every Graph request (path + query), for QA to count reads


@app.before_request
def _count_hit():
    if request.path.startswith("/v24.0"):
        HITS.append(request.full_path)


@app.route("/fake/_hits")
def fake_hits():
    out = list(HITS)
    if request.args.get("clear"):
        HITS.clear()
    return jsonify(out)


@app.route("/fake/_slow")
def fake_slow():
    if "reach" in request.args or "daily" not in request.args:
        SLOW["reach"] = float(request.args.get("reach", 0))
    if "daily" in request.args:
        SLOW["daily"] = float(request.args["daily"])
    return jsonify(SLOW)


ACTIVITIES = []  # changes made "in Ads Manager" through /fake/_outside, listed by act_…/activities
OUTSIDE_KEYS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "bid_amount", "start_time", "end_time", "stop_time")


@app.route("/fake/_outside")
def fake_outside():
    """Change a campaign or ad set as someone in Ads Manager would (QA): budgets, bid, dates, audience
    (targeting_age_min), Meta's own audience defaults (targeting_noise=1) or clear=<field,…> to remove fields."""
    a = request.args
    obj = by_id(a.get("id", ""))
    if obj is None or a.get("id") in ADS:
        return jsonify({"error": "campaign or ad set only"}), 404
    before = {k: obj.get(k) for k in OUTSIDE_KEYS}
    for key in OUTSIDE_KEYS:
        if a.get(key) not in (None, ""):
            obj[key] = a[key]
    for key in [k for k in (a.get("clear") or "").split(",") if k]:
        obj.pop(key, None)
    if a.get("targeting_age_min"):
        obj["targeting"] = {**(obj.get("targeting") or {}), "age_min": int(a["targeting_age_min"])}
    if a.get("targeting_noise"):
        obj["targeting"] = {**(obj.get("targeting") or {}), "targeting_relaxation_types": {"lookalike": 1, "custom_audience": 1}}
    obj["updated_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    camp = obj.get("objective") is not None
    kind = "update_campaign_budget" if camp else "update_ad_set_target_spec" if a.get("targeting_age_min") else (
        "update_ad_set_run_status" if a.get("end_time") or "end_time" in (a.get("clear") or "") else "update_ad_set_budget")
    ACTIVITIES.insert(0, {"event_time": obj["updated_time"], "event_type": kind, "translated_event_type": kind.replace("_", " ").capitalize(),
                          "actor_name": "Eugene", "object_name": obj["name"], "object_type": "CAMPAIGN" if camp else "AD_SET",
                          "object_id": obj["id"], "extra_data": json.dumps({"old_value": before, "new_value": {k: obj.get(k) for k in OUTSIDE_KEYS}})})
    return jsonify({k: obj.get(k) for k in (*OUTSIDE_KEYS, "targeting", "updated_time")})


@app.route("/fake/_refuse_next_ad")
def fake_refuse_next_ad():
    REFUSE_NEXT_AD.append(1)
    return jsonify({"ok": True})


FORM_LEADS = {}


def _lead_from(lead_id, ad, fields):
    return {"id": lead_id, "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "ad_id": REAL_AD_IDS[ad], "ad_name": list(TEXTS)[ad], "adset_id": ADSET["id"],
            "campaign_id": CAMPAIGN["id"], "campaign_name": CAMPAIGN["name"], "form_id": FORM, "is_organic": False,
            "field_data": [{"name": k, "values": [v]} for k, v in fields]}


# Leads a QA webhook names, by id prefix. 7700: a new person each time (its own email and phone from the id, on
# addresses that aren't reserved for tests, so lead quality neither flags nor folds them). 7711: the same person
# every time ("Repeat QA", from N3), so a second one is a repeat. 7713: a lead that looks like junk.
WEBHOOK_LEADS = {
    "7700": lambda i: _lead_from(i, 1, [("full_name", "Telegram QA Lead"), ("phone_number", f"+16197{i[-6:]}"),
                                        ("email", f"tgqa+{i[-6:]}@qa.edgebourne.com")]),
    "7711": lambda i: _lead_from(i, 2, [("full_name", "Repeat QA"), ("phone_number", "+16195557701"),
                                        ("email", "repeat-qa@qa.edgebourne.com"), ("what_kind_of_business_do_you_run?", "Machine shop")]),
    "7713": lambda i: _lead_from(i, 4, [("full_name", "a"), ("phone_number", "1234567890"), ("email", "test@test.com"),
                                        ("what_kind_of_business_do_you_run?", "asdf"), ("how_many_people_work_there?", "asdf")]),
}


def webhook_lead(lead_id):
    return WEBHOOK_LEADS[lead_id[:4]](lead_id)


@app.route("/fake/_form_lead")
def fake_form_lead():
    """A lead on the first form that only the catch-up sees until a webhook names it (QA)."""
    a = request.args
    lead = {"id": a["id"], "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "form_id": FORM, "is_organic": a.get("organic") == "1",
            "field_data": [{"name": "full_name", "values": [a.get("name", "Form QA Lead")]},
                           {"name": "email", "values": [a.get("email", "formqa@qa.edgebourne.com")]}]}
    if a.get("organic") != "1":
        lead.update({"ad_id": REAL_AD_IDS[1], "ad_name": "N2 - Order portal", "adset_id": ADSET["id"],
                     "campaign_id": CAMPAIGN["id"], "campaign_name": CAMPAIGN["name"]})
    FORM_LEADS[lead["id"]] = lead
    return jsonify(lead)


@app.route("/fake/_drop_form")
def fake_drop_form():
    FAKE_FLAGS["drop_form"] = request.args.get("on", "1") == "1"
    return jsonify({"ok": True})


@app.route("/fake/_creative/<cid>")
def fake_creative(cid):
    return jsonify(CREATIVES.get(cid) or {})


@app.route("/fake/_campaigns")
def fake_campaigns():
    return jsonify(NEW_CAMPAIGNS)


@app.route("/fake/_adsets")
def fake_adsets():
    return jsonify(NEW_ADSETS)


@app.route("/fake/_creatives")
def fake_creatives():
    return jsonify(CREATIVES)


@app.route("/fake/_forms")
def fake_forms():
    return jsonify(FORMS)


@app.route("/fake/_studies")
def fake_studies():
    return jsonify(STUDIES)


SUBSCRIPTIONS = {"app": {}, "accounts": []}  # app-level webhook objects, ad accounts that installed the app

# FU-B: each ad account's spending limit. Read like Meta, in cents as numeric strings ("0" = no limit); written like
# Meta's documented update parameter, a decimal in the currency's standard unit ("200.00" = $200).
ACCOUNT_STATE = {}
SPEND_CAP = {"mode": "normal", "silent_readback": 0.0, "hang_next": False, "lose_next": False}


def account_state(acct):
    if acct not in ACCOUNT_STATE:
        ACCOUNT_STATE[acct] = {"spend_cap": 15000, "amount_spent": 4120} if acct == ACCOUNT else {"spend_cap": None, "amount_spent": 0}
    return ACCOUNT_STATE[acct]


def cap_fields(acct):
    st = account_state(acct)
    if SPEND_CAP["hang_next"] and request.method == "GET":
        SPEND_CAP["hang_next"] = False
        import time
        time.sleep(SPEND_CAP["silent_readback"])  # the read-back after a write goes unanswered (longer than the console waits)
    return {"spend_cap": st.get("raw") or str(st["spend_cap"] or 0), "amount_spent": str(st["amount_spent"])}


@app.route("/fake/_spend_cap")
def fake_spend_cap():
    """QA: ?mode=cents (the NEXT write is read as cents: "200.00" stored as 200) | ignore (the next write answers success
    and changes nothing) | decimal (the next write is read back as the decimal it was sent, e.g. "200.00") | normal;
    ?limit=<cents|0> and ?amount_spent=<cents> set the state; ?silent_readback=<s> makes the first read after the next
    write hang that long; ?lose_next=1 drops the connection after the next write is stored (the console gets no answer);
    ?acct=<id> picks the ad account (Edge Bourne's by default)."""
    st = account_state(request.args.get("acct") or ACCOUNT)
    if "mode" in request.args:
        SPEND_CAP["mode"] = request.args["mode"]
    if "limit" in request.args:
        st["spend_cap"] = int(request.args["limit"]) or None
        st.pop("raw", None)
    if "lose_next" in request.args:
        SPEND_CAP["lose_next"] = request.args["lose_next"] == "1"
    if "amount_spent" in request.args:
        st["amount_spent"] = int(request.args["amount_spent"])
    if "silent_readback" in request.args:
        SPEND_CAP["silent_readback"] = float(request.args["silent_readback"])
        SPEND_CAP["hang_next"] = False
    return jsonify({**st, **SPEND_CAP})


def account_write(acct, a):
    """POST act_<id>: only spend_cap is modelled. The action parameter (reset / delete) is refused: the console never sends it."""
    if "spend_cap_action" in a:
        return jsonify({"error": {"message": "spend_cap_action is not used by the console (fake)", "code": 100}}), 400
    if "spend_cap" not in a:
        return jsonify({"error": {"message": "fake Graph: only spend_cap is modelled on an ad account", "code": 100}}), 400
    import re
    from decimal import Decimal
    raw = str(a["spend_cap"]).strip()
    if not re.fullmatch(r"\d+(\.\d{1,2})?", raw):
        return jsonify({"error": {"message": f"(#100) Invalid parameter: spend_cap {raw!r} (fake)", "code": 100}}), 400
    cents = int(Decimal(raw) * 100)
    mode, SPEND_CAP["mode"] = SPEND_CAP["mode"], "normal"
    st = account_state(acct)
    if mode == "cents":
        st["spend_cap"] = int(Decimal(raw)) or None
    elif mode == "decimal":
        st["raw"] = raw
    elif mode != "ignore":
        st["spend_cap"] = cents or None
        st.pop("raw", None)
    if SPEND_CAP["silent_readback"]:
        SPEND_CAP["hang_next"] = True
    if SPEND_CAP["lose_next"]:
        SPEND_CAP["lose_next"] = False
        import socket
        request.environ["werkzeug.socket"].shutdown(socket.SHUT_RDWR)  # stored, but the answer never arrives
    return jsonify({"success": True})


@app.route("/fake/_subscriptions")
def fake_subscriptions():
    return jsonify(SUBSCRIPTIONS)


@app.route("/v24.0/", methods=["GET"])
def graph_ids():
    """Meta's multi-id read: GET /?ids=a,b&fields=…; an unknown id fails the whole call, as on Meta."""
    out = {}
    for oid in (request.args.get("ids") or "").split(","):
        if oid.startswith("act_"):
            out[oid] = {"id": oid, **cap_fields(oid[4:])}
            continue
        obj = by_id(oid)
        if obj is None:
            return jsonify({"error": {"message": f"Object {oid} does not exist (fake)", "code": 100}}), 400
        out[oid] = ad_view(obj) if oid in ADS else other_ad_view(obj) if oid in OTHER_ADS else obj
    return jsonify(out)


@app.route("/v24.0/<path:path>", methods=["GET", "POST", "DELETE"])
def graph(path):
    a = {**request.args.to_dict(), **request.form.to_dict()}
    parts = path.strip("/").split("/")
    act = f"act_{ACCOUNT}"
    if len(parts) == 2 and parts[1] == "subscriptions" and request.method == "POST":
        SUBSCRIPTIONS["app"][a.get("object")] = {"callback_url": a.get("callback_url"), "fields": (a.get("fields") or "").split(","),
                                                 "app_token": "|" in (a.get("access_token") or "")}
        return jsonify({"success": True})
    if parts == [act, "subscribed_apps"]:
        if request.method == "POST":
            SUBSCRIPTIONS["accounts"] = [ACCOUNT]
            return jsonify({"success": True})
        if request.method == "DELETE":
            SUBSCRIPTIONS["accounts"] = []
            return jsonify({"success": True})
        return jsonify({"data": [{"id": "fake-app", "name": "Edge Bourne Ads Console"}] if SUBSCRIPTIONS["accounts"] else []})
    if request.method == "GET":
        if parts == ["me"]:
            return jsonify({"id": "1", "name": "ads-console (fake)"})
        if parts == ["me", "adaccounts"]:
            extra = ["6667778889990001"] if a.get("access_token") == OWN_KEY_TOKEN else []
            return reachable_list([ACCOUNT, MASHA, "4445556667778889", *extra])
        if len(parts) == 2 and parts[1] in ("owned_ad_accounts", "client_ad_accounts"):
            if REACH["refuse_business"]:
                return jsonify({"error": {"message": "(#200) Requires business_management permission to manage the object (fake)",
                                          "code": 200, "type": "OAuthException"}}), 403
            if parts[0] != BUSINESS:
                return jsonify({"data": []})
            return reachable_list([ACCOUNT] if parts[1] == "owned_ad_accounts" else ["5556667778889990"])
        if parts and parts[0].startswith("act_") and parts[0][4:] in OTHER_ACCOUNTS:
            return other_account_get(parts[0][4:], parts, a)
        if parts == [act]:
            return jsonify({"name": "Edge Bourne Consulting", "currency": "USD", "timezone_name": "America/Los_Angeles",
                            **cap_fields(ACCOUNT), "account_status": 1,
                            "business": {"id": BUSINESS, "name": "Edge Bourne"}, "opportunity_score": ADVICE["score"]})
        if parts == [act, "recommendations"]:
            return jsonify({"data": [{"recommendations": ADVICE["recs"]}]})
        # Like Meta, the account's lists leave archived and deleted objects out (they are still read by id).
        if parts == [act, "campaigns"]:
            return jsonify({"data": [c for c in (CAMPAIGN, *NEW_CAMPAIGNS.values()) if listed(c)]})
        if parts == [act, "adsets"]:
            return jsonify({"data": [s for s in (ADSET, *NEW_ADSETS.values()) if listed(s)]})
        if parts == ["search"] and a.get("type") == "adgeolocationmeta":
            names = {p["key"]: p for p in PLACES}
            return jsonify({"data": {"cities": {k: {"key": k, "name": names[k]["name"]} for k in json.loads(a.get("cities") or "[]") if k in names}}})
        if parts == ["search"] and a.get("type") == "adgeolocation":
            q = (a.get("q") or "").lower()
            return jsonify({"data": [p for p in PLACES if q in p["name"].lower()][:8]})
        if parts == [act, "ads"]:
            return jsonify({"data": [ad_view(x) for x in ADS.values() if listed(x)]})
        if len(parts) == 2 and parts[1] == "insights":
            if a.get("breakdowns"):
                return jsonify({"data": breakdown_rows(a["breakdowns"])})
            if parts[0] == act and "reach" in (a.get("fields") or "") and "spend" not in (a.get("fields") or ""):
                # Unique reach for a whole window: fewer people than the daily rows added up.
                __import__("time").sleep(SLOW["reach"])
                level = a.get("level", "ad")
                key = {"ad": "ad_id", "adset": "adset_id", "campaign": "campaign_id", "account": "account_id"}[level]
                tr = json.loads(a.get("time_range") or "{}")
                rows = [r for r in insights_rows("ad") if tr.get("since", "") <= r["date_start"] <= tr.get("until", "9999")]
                people = {}
                for r in rows:
                    ident = ACCOUNT if level == "account" else r[key]
                    people[ident] = people.get(ident, 0) + int(r["reach"])
                return jsonify({"data": [{key: k, "reach": str(int(v * .62))} for k, v in people.items()]})
            if parts[0] == act and a.get("level") in ("ad", "account") and a.get("time_range"):
                # Meta honours the window of a daily read (D1: the 3-day quick pull stores only those days).
                tr = json.loads(a["time_range"])
                rows = [r for r in insights_rows("ad") if tr.get("since", "") <= r["date_start"] <= tr.get("until", "9999")]
                if a.get("level") == "account":
                    return jsonify({"data": account_days(rows)})
                if SHORT["next"]:
                    SHORT["next"] = False
                    return jsonify({"data": []})
                if SLOW["daily"]:
                    __import__("time").sleep(SLOW["daily"])
                return jsonify({"data": rows})
            if parts[0] == act:
                return jsonify({"data": insights_rows(a.get("level"))})
            if a.get("date_preset") == "maximum" and a.get("fields") == "reach":
                rows = [r for r in insights_rows("ad") if r["ad_id"] == parts[0]]
                return jsonify({"data": [{"reach": str(int(sum(int(r["reach"]) for r in rows) * .62))}] if rows else []})
            return jsonify({"data": [{"quality_ranking": "AVERAGE", "engagement_rate_ranking": "ABOVE_AVERAGE",
                                      "conversion_rate_ranking": "BELOW_AVERAGE_35", "frequency": "1.42", "cpm": "13.80",
                                      "ctr": "2.9", "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4"}]}]})
        if parts == [act, "activities"]:
            return jsonify({"data": ACTIVITIES + [
                {"event_time": TODAY.isoformat() + "T21:36:00+0000", "event_type": "ad_review_approved",
                 "translated_event_type": "Ad approved", "actor_name": "Meta", "object_name": "N5 - Quote to invoice", "object_type": "AD",
                 "object_id": next((k for k, v in ADS.items() if v["name"] == "N5 - Quote to invoice"), None)},
                {"event_time": TODAY.isoformat() + "T21:27:00+0000", "event_type": "update_campaign_budget",
                 "translated_event_type": "Campaign budget updated", "actor_name": "Eugene", "object_name": CAMPAIGN["name"],
                 "object_type": "CAMPAIGN", "object_id": CAMPAIGN["id"], "extra_data": json.dumps({"old_value": {"new_value": 2000, "currency": "USD"}, "new_value": 2400})}]})
        if len(parts) == 2 and parts[1] == "delivery_estimate":
            return jsonify({"data": [{"estimate_mau_lower_bound": 1_400_000, "estimate_mau_upper_bound": 1_650_000,
                                      "estimate_ready": True}]})
        if parts == ["dataset_quality"]:
            seen = [e for e in CRM_EVENTS]
            return jsonify({"web": [], "crm": [{"event_name": "Lead", "event_match_quality": {"composite_score": 7.4}}] if seen else []})
        if len(parts) == 1 and parts[0] == DATASET:
            last = max((e.get("event_time") for e in CRM_EVENTS), default=None)
            return jsonify({"id": DATASET, "name": "edgebourne.com", "is_unavailable": False,
                            "last_fired_time": "1969-12-31T16:00:00-0800",
                            "server_last_fired_time": int(last) if last else "1969-12-31T16:00:00-0800"})
        if len(parts) == 2 and parts[0] == DATASET and parts[1] == "stats":
            if a.get("aggregation") == "event_source":
                rows = [{"value": "SERVER", "count": len(CRM_EVENTS)}] if CRM_EVENTS else []
            else:
                byname = {}
                for e in CRM_EVENTS:
                    byname[e["event_name"]] = byname.get(e["event_name"], 0) + 1
                rows = [{"value": k, "count": v} for k, v in byname.items()]
            return jsonify({"data": [{"start_time": TODAY.isoformat(), "aggregation": a.get("aggregation"), "data": rows}] if rows else []})
        if len(parts) == 2 and parts[1] == "comments":
            items = comments_for(parts[0])
            return jsonify({"data": [{**c, "comment_count": len(c["comments"]["data"])} for c in items], "summary": {"total_count": len(items)}})
        if parts == [PAGE, "leadgen_forms"]:
            return jsonify({"data": [{k: f.get(k) for k in ("id", "name", "status", "leads_count", "created_time")} for f in FORMS.values()]})
        if len(parts) == 1 and parts[0] in FORMS:
            return jsonify(FORMS[parts[0]])
        if len(parts) == 2 and parts[1] == "leads":
            return jsonify({"data": [l for l in FORM_LEADS.values() if l["form_id"] == parts[0]]})
        if len(parts) == 1 and parts[0] in FORM_LEADS:
            return jsonify(FORM_LEADS[parts[0]])
        if len(parts) == 1 and parts[0][:4] in WEBHOOK_LEADS and len(parts[0]) == 16:
            # A form lead the webhook announced (QA uses 7700…, 7711…, 7713…); shaped like Meta's.
            return jsonify(webhook_lead(parts[0]))
        if parts == [PAGE]:
            return jsonify({"id": PAGE, "name": "Edge Bourne Consulting", "access_token": "fake-page-token"})
        if len(parts) == 2 and parts[0] in STUDIES and parts[1] == "objectives":
            st = STUDIES[parts[0]]
            cells = [c.get("ads") or c.get("adsets") for c in st["cells"]]
            ids_ = [x[0] for x in cells]
            res = ({"high_performer_ids": [ids_[-1]], "winner_ad_object_id": None, "winner_confidence": None,
                    "confidence_by_ad_object_id": {i: round(0.9 if i == ids_[-1] else 0.1 / (len(ids_) - 1), 2) for i in ids_}}
                   if st["type"] == "SPLIT_TEST_V2" else {"winner_ad_object_id": ids_[0], "winner_confidence": 0.82})
            return jsonify({"data": [{"id": parts[0] + "1", "name": "Cost per result", "results": [json.dumps(res)]}]})
        if len(parts) == 1 and parts[0] in STUDIES:
            return jsonify(STUDIES[parts[0]])
        if parts == [act, "adimages"]:
            return jsonify({"data": list(IMAGES.values())})
        if len(parts) == 2 and parts[1] == "adsets" and parts[0] in (CAMPAIGN["id"], *NEW_CAMPAIGNS):
            return jsonify({"data": [s for s in (ADSET, *NEW_ADSETS.values()) if s["campaign_id"] == parts[0]]})
        if parts == [BUSINESS, "ad_studies"]:
            return jsonify({"data": [{"id": k, "name": v["name"]} for k, v in STUDIES.items()]})
        if parts == [act, "advideos"]:
            return jsonify({"data": list(VIDEOS.values())})
        if parts == [act, "generatepreviews"]:
            if not json.loads(a.get("creative") or "{}").get("object_story_spec"):
                return jsonify({"error": {"message": "creative is required (fake)", "code": 100}}), 400
            fmt = a.get("ad_format", "MOBILE_FEED_STANDARD")
            src = f"https://www.facebook.com/ads/api/preview_iframe.php?d=fake-new&amp;t=fake&amp;f={fmt}"
            return jsonify({"data": [{"body": f'<iframe src="{src}" width="320" height="560" scrolling="yes" style="border: none;"></iframe>'}]})
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
            if parts[0] in ADS:
                return jsonify({**obj, "creative": {"id": obj["creative_id"]}})
            if parts[0] in OTHER_ADS:
                return jsonify(other_ad_view(obj))
            return jsonify({k: v for k, v in obj.items() if k != "account"})
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
            feed = json.loads(a.get("asset_feed_spec") or "null")
            if feed:
                # Placement asset customization: checked the way the console relies on (two labelled
                # videos, rules pointing at them); FAKE_DROP_FORM simulates Meta losing the form.
                labels = {l["name"] for v in feed.get("videos") or [] for l in v.get("adlabels") or []}
                if len(feed.get("videos") or []) < 2 or any(r["video_label"]["name"] not in labels for r in feed.get("asset_customization_rules") or []):
                    return jsonify({"error": {"message": "Invalid asset_feed_spec (fake)", "code": 100}}), 400
                if FAKE_FLAGS.get("drop_form"):
                    feed = {**feed, "call_to_actions": [{"type": c["type"]} for c in feed.get("call_to_actions") or []]}
                cid = str(next(ids))
                first = feed["videos"][0]
                CREATIVES[cid] = {"id": cid, "object_type": "VIDEO", "title": feed["titles"][0]["text"], "body": feed["bodies"][0]["text"],
                                  "call_to_action_type": (feed.get("call_to_action_types") or [None])[0], "video_id": first["video_id"],
                                  "image_url": None, "thumbnail_url": PIC, "object_story_spec": spec, "asset_feed_spec": feed,
                                  "degrees_of_freedom_spec": json.loads(a.get("degrees_of_freedom_spec") or "{}"),
                                  "effective_object_story_id": f"{PAGE}_{next(ids)}"}
                return jsonify({"id": cid})
            media = spec.get("video_data") or spec.get("link_data")
            if FAKE_FLAGS.get("drop_form"):
                spec = json.loads(json.dumps(spec))
                ((spec.get("video_data") or spec.get("link_data")).get("call_to_action") or {}).get("value", {}).pop("lead_gen_form_id", None)
            cid = str(next(ids))
            CREATIVES[cid] = {"id": cid, "object_type": "VIDEO" if "video_data" in spec else "SHARE",
                              "title": media.get("title") or media.get("name"), "body": media.get("message"),
                              "call_to_action_type": (media.get("call_to_action") or {}).get("type"),
                              "video_id": media.get("video_id"), "image_url": PIC if "link_data" in spec else None,
                              "thumbnail_url": PIC, "object_story_spec": spec,
                              "degrees_of_freedom_spec": json.loads(a.get("degrees_of_freedom_spec") or "{}"),
                              "effective_object_story_id": f"{PAGE}_{next(ids)}"}
            return jsonify({"id": cid})
        if parts == [act, "campaigns"]:
            if a.get("status") != "PAUSED" or a.get("objective") != "OUTCOME_LEADS" or not a.get("name"):
                return jsonify({"error": {"message": "Invalid parameter (fake): campaign", "code": 100}}), 400
            cid = str(next(ids))
            NEW_CAMPAIGNS[cid] = {"id": cid, "name": a["name"], "status": "PAUSED", "effective_status": "PAUSED", "objective": a["objective"],
                                  "daily_budget": a.get("daily_budget"), "bid_strategy": a.get("bid_strategy"),
                                  "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")}
            return jsonify({"id": cid})
        if parts == [act, "adsets"]:
            # Shaped like Meta's ad set create: the fake checks what the builder relies on.
            t = json.loads(a.get("targeting") or "{}")
            geo = t.get("geo_locations") or {}
            if a.get("status") != "PAUSED" or not a.get("campaign_id") or not (geo.get("custom_locations") or geo.get("cities") or geo.get("regions") or geo.get("zips")):
                return jsonify({"error": {"message": "Invalid parameter (fake): adset", "code": 100}}), 400
            if a["campaign_id"] == CAMPAIGN["id"] and a.get("daily_budget"):
                return jsonify({"error": {"message": "Budget is set on the campaign (fake)", "code": 100}}), 400
            sid = str(next(ids))
            NEW_ADSETS[sid] = {"id": sid, "name": a["name"], "campaign_id": a["campaign_id"], "status": "PAUSED", "effective_status": "PAUSED",
                               "optimization_goal": a.get("optimization_goal"), "billing_event": a.get("billing_event"),
                               "destination_type": a.get("destination_type"), "promoted_object": json.loads(a.get("promoted_object") or "{}"),
                               "targeting": t, "start_time": a.get("start_time"), "end_time": a.get("end_time"),
                               "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")}
            return jsonify({"id": sid})
        if parts == [act, "ads"] and REFUSE_NEXT_AD:
            REFUSE_NEXT_AD.pop()
            return jsonify({"error": {"message": "The ad was refused (fake)", "code": 100}}), 400
        if parts == [act, "ads"]:
            aid = str(next(ids))
            parent = NEW_ADSETS.get(a["adset_id"]) or ADSET
            ADS[aid] = {"id": aid, "name": a["name"], "campaign_id": parent["campaign_id"], "adset_id": a["adset_id"],
                        "status": a.get("status", "PAUSED"), "creative_id": json.loads(a["creative"])["creative_id"],
                        "created_time": TODAY.isoformat() + "T12:00:00-0800"}
            return jsonify({"id": aid})
        if len(parts) == 2 and parts[1] == "events":
            events = json.loads(a.get("data") or "[]")
            bad = [e for e in events if not str(e.get("user_data", {}).get("lead_id", "")).isdigit()]
            if bad or not events:
                return jsonify({"error": {"message": "Invalid parameter (fake): lead_id", "code": 100}}), 400
            CRM_EVENTS.extend({**e, "test_event_code": a.get("test_event_code")} for e in events)
            return jsonify({"events_received": len(events), "messages": [], "fbtrace_id": "fake"})
        if parts == [PAGE, "leadgen_forms"]:
            # Shaped like Meta's Page leadgen_forms edge; the fake checks what the builder relies on.
            try:
                qs = json.loads(a.get("questions") or "[]")
                pp = json.loads(a.get("privacy_policy") or "{}")
                ty = json.loads(a.get("thank_you_page") or "{}")
                card = json.loads(a.get("context_card") or "{}")
            except ValueError:
                return jsonify({"error": {"message": "Invalid JSON (fake)", "code": 100}}), 400
            keys = [q.get("key") for q in qs]
            if not a.get("name") or not qs or len(set(keys)) != len(keys) or not pp.get("url") or not ty.get("button_type") or not ty.get("title"):
                return jsonify({"error": {"message": "Invalid parameter (fake): form", "code": 100}}), 400
            fid = str(next(ids))
            FORMS[fid] = {"id": fid, "name": a["name"], "status": "ACTIVE", "leads_count": 0, "created_time": TODAY.isoformat() + "T12:00:00+0000",
                          "questions": qs, "privacy_policy_url": pp["url"], "thank_you_page": ty, "context_card": card,
                          "follow_up_action_url": a.get("follow_up_action_url"), "locale": a.get("locale"),
                          "is_optimized_for_quality": a.get("is_optimized_for_quality") == "true"}
            return jsonify({"id": fid})
        if len(parts) == 2 and parts[1] == "comments":
            parent = find_comment(parts[0])
            if not parent or not a.get("message"):
                return jsonify({"error": {"message": "Unsupported post request (fake)", "code": 100}}), 400
            rid = f"{parts[0].split('_')[0]}_{next(ids)}"
            parent["comments"]["data"].append({"id": rid, "message": a["message"], "created_time": TODAY.isoformat() + "T20:00:00+0000",
                                               "from": {"name": "Edge Bourne Consulting", "id": PAGE}})
            return jsonify({"id": rid})
        if len(parts) == 1 and find_comment(parts[0]) and "is_hidden" in a:
            find_comment(parts[0])["is_hidden"] = a["is_hidden"] == "true"
            return jsonify({"success": True})
        if parts == [act, "recommendations"]:
            sig = a.get("recommendation_signature", "").strip('"')
            rec = next((r for r in ADVICE["recs"] if r.get("recommendation_signature") == sig), None)
            if not rec:
                return jsonify({"error": {"message": "Invalid recommendation signature (fake)", "code": 100}}), 400
            if rec["type"] == "SCALE_GOOD_CAMPAIGN":
                CAMPAIGN["daily_budget"] = str(int(CAMPAIGN["daily_budget"]) + rec["recommendation_data"]["additional_budget"])
            ADVICE["recs"].remove(rec)
            ADVICE["score"] = min(100, ADVICE["score"] + int(rec["recommendation_content"]["opportunity_score_lift"]))
            return jsonify({"success": True})
        if len(parts) == 2 and parts[0] == BUSINESS and parts[1] == "ad_studies":
            # Shaped like Meta's ad study rules (split testing guide): fake only checks what we rely on.
            cells = json.loads(a.get("cells") or "[]")
            kind = a.get("type")
            missing = [k for k in ("name", "type", "start_time", "end_time") if not a.get(k)]
            if missing or kind not in ("SPLIT_TEST", "SPLIT_TEST_V2") or len(cells) < 2:
                return jsonify({"error": {"message": f"Invalid parameter (fake): {missing or kind or 'cells'}", "code": 100}}), 400
            if sum(c["treatment_percentage"] for c in cells) > 100:
                return jsonify({"error": {"message": "Treatment percentages over 100 (fake)", "code": 100}}), 400
            if kind == "SPLIT_TEST_V2" and (not json.loads(a.get("creative_test_config") or "{}").get("daily_budget")
                                            or a.get("cooldown_start_time") != a["start_time"] or a.get("observation_end_time") != a["end_time"]
                                            or any(len(c.get("ads") or []) != 1 for c in cells) or sum(c["treatment_percentage"] for c in cells) != 100):
                return jsonify({"error": {"message": "Creative test settings are invalid (fake)", "code": 100}}), 400
            sid = str(next(ids))
            STUDIES[sid] = {"id": sid, "name": a["name"], "type": kind, "start_time": int(a["start_time"]),
                            "end_time": int(a["end_time"]), "cells": cells, "description": a.get("description")}
            return jsonify({"id": sid})
        if len(parts) == 1 and parts[0].startswith("act_") and (parts[0][4:] == ACCOUNT or parts[0][4:] in OTHER_ACCOUNTS):
            return account_write(parts[0][4:], a)
        if len(parts) == 1 and parts[0] in STUDIES:
            if "end_time" in a:
                STUDIES[parts[0]]["end_time"] = int(a["end_time"])
            return jsonify({"success": True})
        if len(parts) == 2 and parts[1] == "copies" and parts[0] in ADS:
            src = ADS[parts[0]]
            aid = str(next(ids))
            ADS[aid] = {**src, "id": aid, "status": "PAUSED", "name": src["name"] + " - Copy"}
            return jsonify({"copied_ad_id": aid})
        if len(parts) == 1:
            obj = by_id(parts[0])
            if obj is None:
                return jsonify({"error": {"message": "Object does not exist (fake)", "code": 100}}), 400
            if a.get("daily_budget") and int(a["daily_budget"]) < 100:
                return jsonify({"error": {"message": "Budget too low (fake)", "code": 100}}), 400
            # lifetime_budget / end_time: QA moves a campaign to a lifetime budget (daily_budget="") and back.
            for key in ("status", "daily_budget", "lifetime_budget", "end_time", "name", "spend_cap", "bid_strategy",
                        "bid_amount", "start_time", "stop_time"):
                if key in a:
                    obj[key] = a[key]
            if "targeting" in a:
                obj["targeting"] = json.loads(a["targeting"])
            if "creative" in a and parts[0] in ADS:
                cid = json.loads(a["creative"])["creative_id"]
                if cid not in CREATIVES:
                    return jsonify({"error": {"message": "Unknown creative (fake)", "code": 100}}), 400
                obj["creative_id"] = cid
            if "status" in a and parts[0] in ADS and a["status"] == "ACTIVE" and REVIEW_ON_ACTIVATE and parts[0] not in REVIEW:
                REVIEW[parts[0]] = "IN_PROCESS"
            if "status" in a:
                obj["effective_status"] = a["status"] if parts[0] not in ADS else effective(obj)
            return jsonify({"success": True})
    return jsonify({"error": {"message": f"fake Graph: {request.method} /{path} not implemented", "code": 100}}), 400


# ---- A mail catcher (SMTP on fake-meta:1025, no TLS, no login); GET /mail/_sent lists what arrived ----
MAIL = []


def _smtp_server():
    import socketserver
    from email import message_from_bytes, policy

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            say = lambda line: self.wfile.write((line + "\r\n").encode())  # noqa: E731
            say("220 fake-smtp ready")
            rcpt, sender = [], None
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                cmd = line.decode(errors="replace").strip()
                up = cmd.upper()
                if up.startswith(("EHLO", "HELO")):
                    say("250-fake-smtp")
                    say("250 8BITMIME")
                elif up.startswith("MAIL FROM"):
                    sender, rcpt = cmd.split(":", 1)[1].strip(), []
                    say("250 OK")
                elif up.startswith("RCPT TO"):
                    rcpt.append(cmd.split(":", 1)[1].strip().strip("<>"))
                    say("250 OK")
                elif up == "DATA":
                    say("354 go ahead")
                    raw = b""
                    while True:
                        chunk = self.rfile.readline()
                        if chunk in (b".\r\n", b".\n", b""):
                            break
                        raw += chunk[1:] if chunk.startswith(b"..") else chunk
                    msg = message_from_bytes(raw, policy=policy.default)
                    body = msg.get_body(preferencelist=("plain",))
                    MAIL.append({"from": msg["From"], "to": rcpt, "reply_to": msg["Reply-To"], "subject": msg["Subject"],
                                 "text": body.get_content() if body else ""})
                    say("250 queued")
                elif up in ("RSET", "NOOP"):
                    say("250 OK")
                elif up == "QUIT":
                    say("221 bye")
                    return
                else:
                    say("502 not implemented")

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    Server(("0.0.0.0", 1025), Handler).serve_forever()


@app.get("/mail/_sent")
def mail_sent():
    return jsonify(MAIL)


if __name__ == "__main__":
    import threading
    threading.Thread(target=_smtp_server, daemon=True).start()
    app.run(host="0.0.0.0", port=5001)
