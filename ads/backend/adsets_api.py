"""New ad set (admins): start from an existing ad set, change who and when, see the audience
estimate live, create it PAUSED."""
import hashlib
import json

from flask import Blueprint, jsonify, request

import adset_build as ab
import account_info
import config
import db
import meta_client
import settings_store
from auth import admin_required, current_user
from insights_api import cached
from util import api_error

bp = Blueprint("adsets_new", __name__, url_prefix="/api/adsets")

TEMPLATE_FIELDS = "id,name,campaign_id,targeting,promoted_object,destination_type,optimization_goal,billing_event,bid_strategy,attribution_spec"


def _account():
    return settings_store.get("meta_ad_account_id")


def template(adset_id):
    """The existing ad set a new one copies its setup from; {} = from scratch (Meta's lead-form
    defaults: leads, on-ad form, the account's Page)."""
    if not adset_id:
        return {}
    if not db.query("SELECT 1 FROM adsets WHERE id = %s", (adset_id,), one=True):
        raise meta_client.MetaError("Pick an ad set to start from")
    return meta_client.get(adset_id, fields=TEMPLATE_FIELDS)


def clean(raw):
    locs = []
    for loc in (raw.get("locations") or [])[:50]:
        kind = loc.get("kind")
        if kind == "pin":
            try:
                locs.append({"kind": "pin", "latitude": float(loc["latitude"]), "longitude": float(loc["longitude"]),
                             "radius": int(loc.get("radius") or 0), "name": str(loc.get("name") or "")[:120] or None})
            except (KeyError, TypeError, ValueError):
                continue
        elif kind in ("city", "region", "zip") and loc.get("key"):
            item = {"kind": kind, "key": str(loc["key"])[:40], "name": str(loc.get("name") or loc["key"])[:120]}
            if kind == "city":
                item["radius"] = int(loc.get("radius") or 0)
            locs.append(item)

    def num(k, default=None):
        try:
            return int(raw[k]) if raw.get(k) not in (None, "") else default
        except (TypeError, ValueError):
            return default
    start = ab.iso_local(raw["start_day"], num("start_hour", 0), account_info.tz_name()) if raw.get("start_day") else None
    end = ab.iso_local(raw["end_day"], num("end_hour", 23), account_info.tz_name()) if raw.get("end_day") else None
    return {"name": str(raw.get("name") or "")[:200], "locations": locs, "age_min": num("age_min", 18), "age_max": num("age_max", 65),
            "suggest_min": num("suggest_min"), "suggest_max": num("suggest_max"), "advantage": bool(raw.get("advantage")),
            "keep_hints": bool(raw.get("keep_hints")), "start": start, "end": end, "daily_budget_cents": num("daily_budget_cents")}


@bp.get("/new/options")
@admin_required
def options():
    campaigns = db.query("""SELECT id, name, effective_status, daily_budget_cents FROM campaigns
                            WHERE COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED')
                            ORDER BY (effective_status = 'ACTIVE') DESC, name""")
    sets = db.query("""SELECT id, name, campaign_id, effective_status, targeting_summary FROM adsets
                       WHERE COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED')
                       ORDER BY (effective_status = 'ACTIVE') DESC, name""")
    return jsonify({"campaigns": campaigns, "adsets": sets, "tz": account_info.tz_name(),
                    "city_radius": ab.CITY_RADIUS, "pin_radius": ab.PIN_RADIUS, "advantage_max_age_min": ab.ADVANTAGE_MAX_AGE_MIN})


@bp.get("/template/<adset_id>")
@admin_required
def template_spec(adset_id):
    try:
        t = template(adset_id)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    spec = ab.spec_from(t)
    ids = sorted({loc["city_id"] for loc in spec["locations"] if loc.get("city_id") and not loc.get("name")})
    if ids:
        try:
            names = meta_client.get("search", type="adgeolocationmeta", cities=json.dumps(ids)).get("data", {}).get("cities", {})
            for loc in spec["locations"]:
                n = (names.get(loc.get("city_id")) or {}).get("name")
                if n and not loc.get("name"):
                    loc["name"] = f"{n} area"
        except (meta_client.MetaError, AttributeError):
            pass  # unnamed pins still work; they show as map pins
    return jsonify(spec)


@bp.get("/places")
@admin_required
def places():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    try:
        rows = meta_client.get("search", type="adgeolocation", q=q, limit=8, country_code="US",
                               location_types=json.dumps(["city", "region", "zip"])).get("data", [])
    except meta_client.MetaError as exc:
        return api_error(f"Meta's place search failed: {exc}", 400)
    out = [{"kind": r.get("type"), "key": str(r.get("key")),
            "name": ", ".join(x for x in (r.get("name"), r.get("region") if r.get("type") != "region" else None) if x)}
           for r in rows if r.get("type") in ("city", "region", "zip")]
    return jsonify({"items": out})


@bp.post("/estimate")
@admin_required
def estimate():
    data = request.get_json(silent=True) or {}
    spec = clean(data.get("spec") or {})
    if not spec["locations"]:
        return jsonify({"lower": None, "upper": None})
    try:
        t = template(str(data.get("template_adset_id") or ""))
        targeting = ab.targeting(spec, t.get("targeting"))
        key = "estimate:new:" + hashlib.sha1(json.dumps(targeting, sort_keys=True).encode()).hexdigest()
        row = cached(key, 3600, lambda: (meta_client.get(f"act_{_account()}/delivery_estimate", targeting_spec=json.dumps(targeting),
                                                         optimization_goal=t.get("optimization_goal") or "LEAD_GENERATION").get("data") or [{}])[0])
    except meta_client.MetaError as exc:
        return api_error(f"Meta has no estimate: {exc}", 400)
    return jsonify({"lower": row.get("estimate_mau_lower_bound"), "upper": row.get("estimate_mau_upper_bound")})


def check(data):
    """(campaign row or None, spec, [(field, message)]): everything create() refuses, without asking Meta,
    so the page can mark each field before its confirmation (9.4e)."""
    spec = clean(data.get("spec") or {})
    campaign = db.query("""SELECT id, name, daily_budget_cents FROM campaigns WHERE id = %s
                           AND COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED')""", (str(data.get("campaign_id") or ""),), one=True)
    errs = [] if campaign else [("campaign", "Pick the campaign it goes in")]
    errs += ab.problems(spec, campaign["daily_budget_cents"] if campaign else 0)
    import targets
    if campaign and spec.get("daily_budget_cents") and campaign["daily_budget_cents"] is None and spec["daily_budget_cents"] > targets.ceiling():
        errs.append(("budget", f"That's above this account's ceiling of {targets.ceiling() / 100:,.2f} a day "
                               "(Settings → Targets → highest daily budget)."))
    tid = str(data.get("template_adset_id") or "")
    if tid and not db.query("SELECT 1 FROM adsets WHERE id = %s", (tid,), one=True):
        errs.append(("template", "That ad set isn't there any more: pick another, or start from scratch"))
    return campaign, spec, errs


@bp.post("/check")
@admin_required
def check_only():
    _, _, errs = check(request.get_json(silent=True) or {})
    return jsonify({"problems": [{"field": f, "message": m} for f, m in errs]})


@bp.post("")
@admin_required
def create():
    data = request.get_json(silent=True) or {}
    campaign, spec, errs = check(data)
    if errs:
        return api_error(errs[0][1], 400, field=errs[0][0])
    import ads_api
    import insights
    user = current_user()
    row = {"id": campaign["id"], "name": spec["name"], "campaign_id": campaign["id"]}
    try:
        t = template(str(data.get("template_adset_id") or ""))
        body = ab.payload(spec, t, campaign, settings_store.get("meta_page_id"))
        made = meta_client.post(f"act_{_account()}/adsets",
                                data={k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in body.items()})
    except meta_client.MetaError as exc:
        ads_api.record(user, "adset", row, "create", None, spec["name"], False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    ads_api.record(user, "adset", {**row, "id": made["id"]}, "create", None, f"{spec['name']} (paused)", True)
    try:
        insights.sync_structure()
    except meta_client.MetaError:
        pass
    return jsonify({"id": made["id"]}), 201
