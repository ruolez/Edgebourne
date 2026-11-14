"""New ad set (roadmap 4.2): built from an existing ad set's setup, for an Instant Form leads
campaign. Always created PAUSED; placements stay Advantage+ (Meta's default when none are set).

With Advantage+ audience on, Meta treats age_min / age_max as hard limits (age_min at most 25)
and `age_range` as the suggestion it starts from; interests and behaviours are suggestions too."""
from datetime import datetime

CITY_RADIUS = (10, 50)      # miles; Meta's range for a radius around a city
PIN_RADIUS = (1, 50)        # miles around a map pin
ADVANTAGE_MAX_AGE_MIN = 25
MIN_DAILY_BUDGET_CENTS = 100


def location_label(loc):
    if loc["kind"] == "pin":
        return f"{loc.get('name') or 'Map pin'} + {loc['radius']} mi"
    if loc["kind"] == "city":
        return f"{loc['name']} + {loc['radius']} mi"
    return loc["name"]


def locations_from(targeting):
    """The template's places in the builder's shape."""
    geo = (targeting or {}).get("geo_locations") or {}
    out = []
    for p in geo.get("custom_locations") or []:
        miles = p.get("radius") if p.get("distance_unit", "mile") == "mile" else round(p.get("radius", 0) * 0.621)
        out.append({"kind": "pin", "latitude": p.get("latitude"), "longitude": p.get("longitude"), "radius": miles,
                    "name": p.get("name") or p.get("address_string"),
                    **({"city_id": str(p["primary_city_id"])} if p.get("primary_city_id") else {})})
    for c in geo.get("cities") or []:
        out.append({"kind": "city", "key": str(c["key"]), "name": c.get("name") or c["key"], "radius": c.get("radius") or 25})
    for r in geo.get("regions") or []:
        out.append({"kind": "region", "key": str(r["key"]), "name": r.get("name") or r["key"]})
    for z in geo.get("zips") or []:
        out.append({"kind": "zip", "key": str(z["key"]), "name": z.get("name") or z["key"]})
    return out


def spec_from(template):
    """Builder defaults from an existing ad set."""
    t = template.get("targeting") or {}
    rng = t.get("age_range")
    if isinstance(rng, dict):
        rng = [rng.get("0"), rng.get("1")]
    return {"locations": locations_from(t), "age_min": t.get("age_min") or 18, "age_max": t.get("age_max") or 65,
            "suggest_min": (rng or [None, None])[0], "suggest_max": (rng or [None, None])[1],
            "advantage": (t.get("targeting_automation") or {}).get("advantage_audience") == 1,
            "hints": [i.get("name") for s in t.get("flexible_spec") or [] for k in ("interests", "behaviors", "work_positions")
                      for i in s.get(k) or [] if i.get("name")], "keep_hints": True,
            "include_audiences": _audience_ids(t, "custom_audiences"), "exclude_audiences": _audience_ids(t, "excluded_custom_audiences")}


def _audience_ids(t, key):
    """AM-D: the custom audiences a targeting includes / leaves out, as ids."""
    return [str(a["id"]) for a in t.get(key) or [] if isinstance(a, dict) and str(a.get("id") or "").isdigit()]


def problems(spec, campaign_budget_cents):
    out = []
    if not (spec.get("name") or "").strip():
        out.append(("name", "Give the ad set a name"))
    locs = spec.get("locations") or []
    if not locs:
        out.append(("locations", "Add at least one place"))
    for loc in locs:
        rng = CITY_RADIUS if loc.get("kind") == "city" else PIN_RADIUS if loc.get("kind") == "pin" else None
        if rng and not (rng[0] <= int(loc.get("radius") or 0) <= rng[1]):
            out.append(("locations", f"{loc.get('name') or 'A place'}: the radius has to be {rng[0]} to {rng[1]} miles"))
    lo, hi = int(spec.get("age_min") or 18), int(spec.get("age_max") or 65)
    if not (18 <= lo <= hi <= 65):
        out.append(("age", "Ages run from 18 to 65, youngest first"))
    elif spec.get("advantage") and lo > ADVANTAGE_MAX_AGE_MIN:
        out.append(("age", f"With Advantage+ audience the minimum age can be at most {ADVANTAGE_MAX_AGE_MIN}; use the suggested ages for older people"))
    smin, smax = spec.get("suggest_min"), spec.get("suggest_max")
    if spec.get("advantage") and (smin or smax) and not (lo <= int(smin or lo) <= int(smax or hi) <= hi):
        out.append(("age", "The suggested ages have to sit inside the age limits"))
    start, end = spec.get("start"), spec.get("end")
    if end and start and end <= start:
        out.append(("end", "The end has to come after the start"))
    budget = spec.get("daily_budget_cents")
    if campaign_budget_cents is None and (budget is None or budget < MIN_DAILY_BUDGET_CENTS):
        out.append(("budget", "Give it a daily budget of at least $1 (the campaign has no budget of its own)"))
    return out


def targeting(spec, template_targeting=None):
    """Meta's targeting object for the spec."""
    geo = {"location_types": ["home", "recent"]}
    for loc in spec["locations"]:
        if loc["kind"] == "pin":
            geo.setdefault("custom_locations", []).append({"latitude": loc["latitude"], "longitude": loc["longitude"],
                                                           "radius": int(loc["radius"]), "distance_unit": "mile"})
        elif loc["kind"] == "city":
            geo.setdefault("cities", []).append({"key": loc["key"], "radius": int(loc["radius"]), "distance_unit": "mile"})
        elif loc["kind"] == "region":
            geo.setdefault("regions", []).append({"key": loc["key"]})
        elif loc["kind"] == "zip":
            geo.setdefault("zips", []).append({"key": loc["key"]})
    t = {"geo_locations": geo, "age_min": int(spec["age_min"]), "age_max": int(spec["age_max"]),
         "targeting_automation": {"advantage_audience": 1 if spec.get("advantage") else 0}}
    if spec.get("advantage") and spec.get("suggest_min") and spec.get("suggest_max"):
        t["age_range"] = [int(spec["suggest_min"]), int(spec["suggest_max"])]
    # The hints come from the ad set it starts from, or (from scratch) from an Ads Manager draft it was filled from (AM-B).
    hints = template_targeting.get("flexible_spec") if template_targeting is not None else spec.get("flexible_spec")
    if spec.get("keep_hints") and hints:
        t["flexible_spec"] = [{k: [{"id": str(i["id"]), "name": i.get("name")} for i in s[k]]
                               for k in ("interests", "behaviors", "work_positions") if s.get(k)}
                              for s in hints]
    # AM-D: audiences picked to include / leave out (checked as this account's by the route before this is built).
    for key, ids in (("custom_audiences", spec.get("include_audiences")), ("excluded_custom_audiences", spec.get("exclude_audiences"))):
        if ids:
            t[key] = [{"id": str(i)} for i in ids]
    return t


def payload(spec, template, campaign, page_id):
    """POST act_<id>/adsets. Always PAUSED; no placement fields, so Meta uses Advantage+ placements."""
    promoted = {k: v for k, v in (template.get("promoted_object") or {}).items() if v}
    out = {"name": spec["name"].strip(), "campaign_id": campaign["id"], "status": "PAUSED",
           "optimization_goal": template.get("optimization_goal") or "LEAD_GENERATION",
           "billing_event": template.get("billing_event") or "IMPRESSIONS",
           "destination_type": template.get("destination_type") or "ON_AD",
           "promoted_object": promoted or {"page_id": page_id},
           "targeting": targeting(spec, template.get("targeting"))}
    if campaign.get("daily_budget_cents") is None:
        out["daily_budget"] = int(spec["daily_budget_cents"])
        out["bid_strategy"] = template.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"
    if spec.get("start"):
        out["start_time"] = spec["start"]
    if spec.get("end"):
        out["end_time"] = spec["end"]
    if template.get("attribution_spec"):
        out["attribution_spec"] = template["attribution_spec"]
    return out


def iso_local(day, hour, tz):
    """'2026-11-12' + 6 → the ISO time Meta takes, in the account's time zone."""
    from zoneinfo import ZoneInfo
    return datetime.fromisoformat(f"{day}T{int(hour):02d}:00:00").replace(tzinfo=ZoneInfo(tz)).isoformat()
