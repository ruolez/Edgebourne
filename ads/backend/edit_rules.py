"""AM-C: what can change on a campaign or ad set after it is made, and what a change means. Pure: no database, no Meta.

The edit form works in its own shape (`current` turns a fresh Graph read into it): times as UTC minutes ('2026-12-01T07:59Z'),
money in cents, who it reaches as the builder's places + ages + the rest, placements as {auto} or the platforms picked.
`changes` compares what the person wants with Meta now (normalized: a list in another order, cents as strings or a time in
another zone is no change), `problems` says what Meta or the console's rules refuse, `money` what needs a knowing yes,
`review` the old -> new lines for the confirmation, `meta_params` the one Graph POST, `readback_ok` what Meta didn't keep."""
import copy
import json
from datetime import datetime, timezone

import adset_build as ab
import money_rules
import status_history as sh
import words

NO_SPEND_CAP = "922337203685478"  # Meta's value that removes a campaign spending cap (Marketing API Campaign reference) (verify)
MIN_CAMPAIGN_CAP = 10000          # Meta's lowest campaign spending cap, $100 (verify)
CAPPED = ("COST_CAP", "LOWEST_COST_WITH_BID_CAP")
BID_STRATEGIES = ("LOWEST_COST_WITHOUT_CAP", "COST_CAP", "LOWEST_COST_WITH_BID_CAP")
REACH_GOALS = ("REACH", "THRUPLAY")
GOALS = ("LEAD_GENERATION", "QUALITY_LEAD", "LINK_CLICKS", "LANDING_PAGE_VIEWS", "REACH", "IMPRESSIONS", "THRUPLAY", "CONVERSATIONS")
DESTINATIONS = ("ON_AD", "WEBSITE", "MESSENGER", "PHONE_CALL", "INSTAGRAM_DIRECT", "WHATSAPP")
DESTINATION_WORDS = {"ON_AD": "Instant form", "WEBSITE": "Website", "MESSENGER": "Messenger", "PHONE_CALL": "Phone call",
                     "INSTAGRAM_DIRECT": "Instagram messages", "WHATSAPP": "WhatsApp"}
BILLING = ("IMPRESSIONS", "LINK_CLICKS", "THRUPLAY")
BILLING_WORDS = {"IMPRESSIONS": "Each time it's shown", "LINK_CLICKS": "Each link click", "THRUPLAY": "Each video play"}
ATTRIBUTIONS = ("1d_click", "7d_click", "1d_click_1d_view", "7d_click_1d_view")
CATEGORIES = ("HOUSING", "EMPLOYMENT", "CREDIT", "FINANCIAL_PRODUCTS_SERVICES", "ISSUES_ELECTIONS_POLITICS")
PLATFORMS = ("facebook", "instagram", "messenger", "audience_network")
PLATFORM_WORDS = {"facebook": "Facebook", "instagram": "Instagram", "messenger": "Messenger", "audience_network": "Audience Network"}
POSITIONS = {"facebook": ("feed", "story", "facebook_reels", "marketplace", "video_feeds", "search", "instream_video", "right_hand_column"),
             "instagram": ("stream", "story", "reels", "explore", "explore_home", "profile_feed", "ig_search")}
POSITION_WORDS = {"feed": "Feed", "story": "Stories", "facebook_reels": "Reels", "marketplace": "Marketplace", "video_feeds": "Video feeds",
                  "search": "Search", "instream_video": "In-stream videos", "right_hand_column": "Right column", "stream": "Feed",
                  "reels": "Reels", "explore": "Explore", "explore_home": "Explore home", "profile_feed": "Profile feed", "ig_search": "Search"}
DETAIL_TYPES = ("interests", "behaviors", "work_positions", "work_employers", "industries", "life_events", "family_statuses",
                "education_majors", "income")
LOCALE_NAMES = {6: "English (US)", 24: "English (UK)", 1001: "English (All)", 23: "Spanish", 7: "Spanish (Spain)", 1002: "Spanish (All)",
                9: "French (France)", 44: "French (Canada)", 5: "German", 25: "Korean", 20: "Chinese (Simplified)", 21: "Chinese (Traditional)",
                12: "Portuguese (Brazil)", 39: "Tagalog", 27: "Vietnamese", 17: "Russian", 28: "Armenian", 30: "Japanese"}
SPECIAL_MIN_RADIUS = 15  # miles; Meta's rule for housing, employment and credit audiences
# Which keys of Meta's targeting are stored (sync) and what the audience form manages; everything else Meta sets is kept as is.
TARGETING_KEYS = sh.AUDIENCE_KEYS + ("targeting_automation", "age_range", "messenger_positions", "audience_network_positions")
PLACE_KEYS = ("custom_locations", "cities", "regions", "zips", "countries")

# (level, field) -> when it may change after creation. Sources: Marketing API Campaign / Ad Set reference ("Updating") and
# Ads Manager behaviour; (verify) = live check owed (AM-C spec, "Live checks owed").
MUTABLE = {
    ("campaign", "name"): "always",
    ("campaign", "objective"): "never", ("campaign", "buying_type"): "never",
    ("campaign", "bid_strategy"): "campaign_budget",   # not away from LOWEST_COST_WITH_MIN_ROAS (Meta); budget on the campaign only
    ("campaign", "adset_bids"): "campaign_budget",     # a capped campaign strategy: the amount goes on each ad set
    ("campaign", "spend_cap"): "always",               # remove = NO_SPEND_CAP (verify); never below what it has spent
    ("campaign", "stop_time"): "lifetime_budget",      # only when the campaign holds a lifetime budget
    ("campaign", "special_ad_categories"): "add_only",  # (verify) removing: Ads Manager only
    ("adset", "name"): "always",
    ("adset", "start_time"): "not_started",
    ("adset", "end_time"): "always",                   # not in the past; required with a lifetime budget
    ("adset", "targeting"): "always",
    ("adset", "placements"): "always",                 # Advantage+ or manual (Meta may refuse manual for lead goals; shown)
    ("adset", "bid_strategy"): "ad_set_budget",
    ("adset", "bid_amount"): "capped_strategy",        # COST_CAP / LOWEST_COST_WITH_BID_CAP only
    ("adset", "optimization_goal"): "never_delivered",  # (verify)
    ("adset", "destination_type"): "never_delivered",  # conversion location (verify)
    ("adset", "attribution_spec"): "never_delivered",  # (verify)
    ("adset", "billing_event"): "never_delivered",     # (verify)
    ("adset", "frequency_control_specs"): "reach_goal",  # REACH / THRUPLAY goals only
    ("adset", "promoted_object"): "never",             # Page, form, pixel event
}
FIELDS = {lv: tuple(f for (lvl, f), rule in MUTABLE.items() if lvl == lv and rule != "never") for lv in ("campaign", "adset")}
ACTIONS = {"name": "rename", "start_time": "schedule", "end_time": "schedule", "stop_time": "schedule", "bid_strategy": "bid_strategy",
           "bid_amount": "bid", "adset_bids": "bid", "spend_cap": "spend_cap", "targeting": "targeting", "placements": "placements",
           "optimization_goal": "optimization", "destination_type": "conversion_location", "attribution_spec": "attribution",
           "billing_event": "billing", "frequency_control_specs": "frequency", "special_ad_categories": "special_categories"}
LEARNING = ("targeting", "placements", "optimization_goal", "destination_type", "billing_event")
LEARNING_NOTE = "Meta restarts learning for this ad set; results wobble for a few days."
LABELS = {"name": "Name", "start_time": "Starts", "end_time": "Ends", "stop_time": "Ends", "bid_strategy": "Bidding",
          "bid_amount": "Cost per result goal", "adset_bids": "Cost per result goal", "spend_cap": "Campaign spending cap",
          "special_ad_categories": "Special ad category", "targeting": "Who it reaches", "placements": "Where it shows",
          "optimization_goal": "What it optimizes for", "destination_type": "Where people answer", "attribution_spec": "How results are counted",
          "billing_event": "What you pay for", "frequency_control_specs": "How often people see it"}
REASONS = {
    "objective": "Meta doesn't allow changing a campaign's goal after it's made. Make a new campaign for another goal.",
    "never_delivered": "Meta doesn't allow changing this after the ad set has delivered.",
    "promoted_object": "Meta doesn't allow changing the Page or form an ad set promotes.",
    "campaign_budget": "The budget is on its ad sets, so bidding is set on each ad set.",
    "min_roas": "Meta doesn't allow switching away from a return on ad spend goal.",
    "lifetime_budget": "The campaign has a daily budget, so it has no end date of its own: set end dates on its ad sets.",
    "not_started": "It has already started, and a start that has passed can't move.",
    "ad_set_budget": "The budget is on the campaign, so bidding is set on the campaign: Edit the campaign.",
    "capped_campaign": "Set a cost per result goal or bid cap on the campaign first (Edit the campaign).",
    "reach_goal": "Only for ad sets that optimize for reach or video plays.",
}


# ---------------------------------------------------------------- reading Meta into the form's shape

def _int(v):
    try:
        return int(v) if v not in (None, "", "0", 0) and not isinstance(v, bool) else None
    except (TypeError, ValueError):
        return None


def _time(v):
    return sh.minute_utc(v) if v not in (None, "", "0", 0) else None


def _dt(minute):
    return datetime.strptime(minute, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) if minute else None


def meta_time(minute):
    return _dt(minute).strftime("%Y-%m-%dT%H:%M:%S+0000")


def locations_from(t):
    """Meta's geo_locations as the builder's places (ab.locations_from), countries too."""
    out = ab.locations_from(t)
    for c in ((t or {}).get("geo_locations") or {}).get("countries") or []:
        out.append({"kind": "country", "key": str(c), "name": str(c)})
    return out


def audience_form(t):
    """Meta's targeting as the form's audience: places, ages, suggested ages, Advantage+ audience, gender, languages,
    detailed targeting (include, with its group, and exclude) and custom audiences (included / left out; AM-D picks them)."""
    t = t or {}
    rng = t.get("age_range")
    if isinstance(rng, dict):
        rng = [rng.get("0"), rng.get("1")]
    include = [{"id": str(i.get("id")), "name": i.get("name") or str(i.get("id")), "type": key, "group": g}
               for g, spec in enumerate(t.get("flexible_spec") or []) for key in DETAIL_TYPES for i in (spec or {}).get(key) or []
               if isinstance(i, dict) and i.get("id")]
    exclude = [{"id": str(i.get("id")), "name": i.get("name") or str(i.get("id")), "type": key}
               for key in DETAIL_TYPES for i in (t.get("exclusions") or {}).get(key) or [] if isinstance(i, dict) and i.get("id")]
    auds = lambda k: [{"id": str(a.get("id")), "name": a.get("name") or str(a.get("id")), **({"subtype": a["subtype"]} if a.get("subtype") else {})}  # noqa: E731
                      for a in t.get(k) or [] if isinstance(a, dict) and a.get("id")]
    return {"locations": locations_from(t), "age_min": _int(t.get("age_min")) or 18, "age_max": _int(t.get("age_max")) or 65,
            "suggest_min": _int((rng or [None, None])[0]), "suggest_max": _int((rng or [None, None])[1]),
            "advantage": (t.get("targeting_automation") or {}).get("advantage_audience") == 1,
            "genders": sorted(int(g) for g in t.get("genders") or [] if str(g) in ("1", "2")),
            "locales": sorted(int(x) for x in t.get("locales") or [] if str(x).isdigit()),
            "include": sorted(include, key=lambda i: (i["type"], i["id"])), "exclude": sorted(exclude, key=lambda i: (i["type"], i["id"])),
            "custom_audiences": auds("custom_audiences"), "excluded_custom_audiences": auds("excluded_custom_audiences")}


def placements_form(t):
    t = t or {}
    if not t.get("publisher_platforms"):
        return {"auto": True}
    return {"auto": False, "platforms": sorted(p for p in t["publisher_platforms"] if p in PLATFORMS),
            "facebook_positions": sorted(t.get("facebook_positions") or []), "instagram_positions": sorted(t.get("instagram_positions") or [])}


def frequency_form(specs):
    key = sh.frequency_key(specs)
    if not key:
        return None
    most, days = key.split("/")
    return {"max": int(most), "days": int(days)}


def current(level, meta, adsets=None):
    """A campaign or ad set as Meta has it now (a fresh Graph read), in the form's shape. `adsets` (campaign): its ad sets'
    {id, bid_amount} for the cost per result goal on each."""
    base = {"name": meta.get("name") or "", "status": meta.get("status"), "daily_budget": _int(meta.get("daily_budget")),
            "lifetime_budget": _int(meta.get("lifetime_budget")), "bid_strategy": meta.get("bid_strategy") or None,
            "start_time": _time(meta.get("start_time"))}
    if level == "campaign":
        cap = _int(meta.get("spend_cap"))
        return {**base, "objective": meta.get("objective"), "spend_cap": None if str(meta.get("spend_cap")) == NO_SPEND_CAP else cap,
                "stop_time": _time(meta.get("stop_time")),
                "special_ad_categories": sorted({c for c in meta.get("special_ad_categories") or [] if c and c != "NONE"}),
                "adset_bids": {str(a["id"]): _int(a.get("bid_amount")) for a in adsets or [] if _int(a.get("bid_amount"))}}
    return {**base, "end_time": _time(meta.get("end_time")), "bid_amount": _int(meta.get("bid_amount")),
            "targeting": audience_form(meta.get("targeting")), "placements": placements_form(meta.get("targeting")),
            "optimization_goal": meta.get("optimization_goal"), "destination_type": meta.get("destination_type"),
            "billing_event": meta.get("billing_event"), "attribution_spec": sh.attribution_key(meta.get("attribution_spec")),
            "frequency_control_specs": frequency_form(meta.get("frequency_control_specs")),
            "promoted_object": meta.get("promoted_object") or None}


def kept_targeting(t):
    """Meta's targeting as the sync stores it: only the keys a person sets (TARGETING_KEYS)."""
    if not isinstance(t, dict):
        return None
    kept = {k: t[k] for k in TARGETING_KEYS if t.get(k) not in (None, [], {})}
    return kept or None


# ---------------------------------------------------------------- comparing

def _loc_key(loc):
    kind = loc.get("kind")
    if kind == "pin":
        try:
            return ("pin", round(float(loc.get("latitude")), 4), round(float(loc.get("longitude")), 4), _int(loc.get("radius")) or 0)
        except (TypeError, ValueError):
            return ("pin", None, None, 0)
    if kind == "city":
        return ("city", str(loc.get("key")), _int(loc.get("radius")) or 0)
    return (str(kind), str(loc.get("key")))


def _audience_normal(t):
    t = t if isinstance(t, dict) else {}
    adv = bool(t.get("advantage"))
    return {"locations": sorted(json.dumps(_loc_key(x)) for x in t.get("locations") or [] if isinstance(x, dict)),
            "ages": [_int(t.get("age_min")) or 18, _int(t.get("age_max")) or 65], "advantage": adv,
            "suggest": [_int(t.get("suggest_min")), _int(t.get("suggest_max"))] if adv and t.get("suggest_min") and t.get("suggest_max") else None,
            "genders": sorted({int(g) for g in t.get("genders") or [] if str(g) in ("1", "2")} or {1, 2}),
            "locales": sorted({int(x) for x in t.get("locales") or [] if str(x).isdigit()}),
            "include": sorted(f"{i.get('group') or 0}:{i.get('type')}:{i.get('id')}" for i in t.get("include") or [] if isinstance(i, dict)),
            "exclude": sorted(f"{i.get('type')}:{i.get('id')}" for i in t.get("exclude") or [] if isinstance(i, dict)),
            "custom": sorted(str(a.get("id")) for a in t.get("custom_audiences") or [] if isinstance(a, dict)),
            "excluded_custom": sorted(str(a.get("id")) for a in t.get("excluded_custom_audiences") or [] if isinstance(a, dict))}


def _placements_normal(p):
    p = p if isinstance(p, dict) else {}
    if p.get("auto", True) and not p.get("platforms"):
        return {"auto": True}
    plats = sorted({x for x in p.get("platforms") or [] if x in PLATFORMS})
    return {"auto": False, "platforms": plats,
            "facebook_positions": sorted(set(p.get("facebook_positions") or [])) if "facebook" in plats else [],
            "instagram_positions": sorted(set(p.get("instagram_positions") or [])) if "instagram" in plats else []}


def normal(field, value):
    """One field as compared (and as written): the form's value cleaned."""
    if field in ("start_time", "end_time", "stop_time"):
        return _time(value)
    if field in ("bid_amount", "spend_cap"):
        return _int(value)
    if field == "name":
        return str(value or "").strip()[:400]
    if field == "targeting":
        return _audience_normal(value)
    if field == "placements":
        return _placements_normal(value)
    if field == "special_ad_categories":
        return sorted({str(c) for c in value or [] if c and c != "NONE"})
    if field == "frequency_control_specs":
        if not isinstance(value, dict) or not _int(value.get("max")) or not _int(value.get("days")):
            return None
        return {"max": _int(value["max"]), "days": _int(value["days"])}
    if field == "adset_bids":
        return {str(k): _int(v) for k, v in (value or {}).items() if _int(v)} if isinstance(value, dict) else {}
    return str(value) if value not in (None, "") else None


def changes(level, live, wanted):
    """[{field, old, new}] for every field the person changed: only real differences, normalized. Unknown fields are ignored."""
    out = []
    for field in FIELDS[level]:
        if field not in (wanted or {}):
            continue
        new = normal(field, wanted[field])
        old = normal(field, live.get(field))
        if field == "adset_bids":
            new = {k: v for k, v in new.items() if old.get(k) != v}
            if new:
                out.append({"field": field, "old": {k: old.get(k) for k in new}, "new": new})
            continue
        if new != old:
            out.append({"field": field, "old": old, "new": new, "value": wanted[field]})
    return out


# ---------------------------------------------------------------- what can change now

def _capped(strategy):
    return strategy in CAPPED


def _campaign_budget(c):
    return bool(c and (c.get("daily_budget") or c.get("lifetime_budget")))


def editable(level, live, ctx):
    """{field: None when it can change now, else the plain reason}."""
    now = ctx.get("now") or datetime.now(timezone.utc)
    out = {}
    if level == "campaign":
        budget_here = bool(live.get("daily_budget") or live.get("lifetime_budget"))
        min_roas = live.get("bid_strategy") == "LOWEST_COST_WITH_MIN_ROAS"
        for field in ("name", "objective", "bid_strategy", "adset_bids", "spend_cap", "stop_time", "special_ad_categories"):
            rule = MUTABLE[("campaign", field)]
            out[field] = (REASONS["objective"] if rule == "never" else
                          (REASONS["campaign_budget"] if not budget_here else REASONS["min_roas"] if min_roas else None)
                          if rule == "campaign_budget" else
                          (None if live.get("lifetime_budget") else REASONS["lifetime_budget"]) if rule == "lifetime_budget" else None)
        return out
    camp = ctx.get("campaign") or {}
    for field in FIELDS["adset"] + ("promoted_object",):
        rule = MUTABLE[("adset", field)]
        reason = None
        if rule == "never":
            reason = REASONS["promoted_object"]
        elif rule == "never_delivered" and ctx.get("delivered"):
            reason = REASONS["never_delivered"]
        elif rule == "not_started":
            start = _dt(live.get("start_time"))
            reason = REASONS["not_started"] if start is not None and start <= now else None
        elif rule == "ad_set_budget":
            reason = (REASONS["ad_set_budget"] if _campaign_budget(camp) else
                      REASONS["min_roas"] if live.get("bid_strategy") == "LOWEST_COST_WITH_MIN_ROAS" else None)
        elif rule == "capped_strategy":
            reason = REASONS["capped_campaign"] if _campaign_budget(camp) and not _capped(camp.get("bid_strategy")) else None
        elif rule == "reach_goal":
            reason = None if live.get("optimization_goal") in REACH_GOALS else REASONS["reach_goal"]
        out[field] = reason
    return out


# ---------------------------------------------------------------- what is refused

def _special_problems(t, prefix=""):
    """Meta's rules for housing, employment and credit audiences (and social issues): ages 18-65, every gender, a radius
    of at least 15 miles, no detailed exclusions, no lookalikes."""
    a = _audience_normal(t)
    out = []
    if a["ages"] != [18, 65]:
        out.append(f"{prefix}with a special ad category Meta needs ages 18–65.")
    if a["genders"] != [1, 2]:
        out.append(f"{prefix}with a special ad category Meta needs every gender.")
    if any(x.get("kind") in ("pin", "city") and (_int(x.get("radius")) or 0) < SPECIAL_MIN_RADIUS for x in t.get("locations") or []):
        out.append(f"{prefix}with a special ad category the radius has to be at least {SPECIAL_MIN_RADIUS} miles.")
    if a["exclude"]:
        out.append(f"{prefix}with a special ad category Meta doesn't allow detailed exclusions.")
    if any((c.get("subtype") or "").upper() == "LOOKALIKE" or "lookalike" in (c.get("name") or "").lower() for c in t.get("custom_audiences") or []):
        out.append(f"{prefix}with a special ad category Meta doesn't allow lookalike audiences.")
    return [m[0].upper() + m[1:] if not prefix else m for m in out]


def _audience_problems(t):
    spec = {"name": "x", "locations": t.get("locations") or [], "age_min": t.get("age_min"), "age_max": t.get("age_max"),
            "suggest_min": t.get("suggest_min"), "suggest_max": t.get("suggest_max"), "advantage": t.get("advantage")}
    out = [m for _, m in ab.problems(spec, 0)]
    if any(str(g) not in ("1", "2") for g in t.get("genders") or []):
        out.append("Pick men, women or everyone")
    return out


def _end_problems(field, new, start, lifetime, now):
    if new is None:
        return ["A lifetime budget needs an end date. Keep one, or change the budget in Ads Manager."] if lifetime else []
    end = _dt(new)
    if end <= now:
        return ["The end can't be in the past."]
    if start is not None and end <= start:
        return ["The end has to come after the start."]
    return []


def problems(level, live, chs, ctx):
    """[(field, message)]: everything Meta or the console refuses for these changes, before anything is sent."""
    now = ctx.get("now") or datetime.now(timezone.utc)
    can = editable(level, live, ctx)
    new = {c["field"]: c["new"] for c in chs}
    out = []
    for c in chs:
        field, value = c["field"], c["new"]
        if field == "adset_bids":
            own = {str(a["id"]) for a in ctx.get("adsets") or []}
            foreign = sorted(k for k in value if k not in own)
            if foreign:
                out.append((field, "These aren't ad sets of this campaign (refresh the page): " + ", ".join(foreign)))
                continue
        if field == "targeting":  # AM-D: only this account's audiences (ctx["audiences"], read under RLS); one Meta already has may stay
            import audience_rules
            was, now_ = _audience_normal(live.get("targeting")), _audience_normal(c.get("value"))
            if max(len(was["custom"]), len(was["excluded_custom"])) > audience_rules.MAX_PICKED:
                # never write a shorter list than Meta has: the console edits at most MAX_PICKED a side
                out.append((field, f"This ad set includes or leaves out more than {audience_rules.MAX_PICKED} audiences, more than the "
                                   "console edits. Change who sees it in Ads Manager."))
                continue
            if (was["custom"], was["excluded_custom"]) != (now_["custom"], now_["excluded_custom"]):
                picked = audience_rules.pick_problems(now_["custom"], now_["excluded_custom"], ctx.get("audiences") or {}, [],
                                                      keep=set(was["custom"]) | set(was["excluded_custom"]))
                if picked:
                    out += [(field, m) for _, m in picked]
                    continue
        if field != "frequency_control_specs" and can.get(field):
            out.append((field, can[field]))
            continue
        if field == "name" and not value:
            out.append((field, "Give it a name"))
        elif field in ("bid_strategy",) and value not in BID_STRATEGIES:
            out.append((field, "Pick Highest volume, Cost per result goal or Bid cap"))
        elif field == "stop_time":
            out += [(field, m) for m in _end_problems(field, value, _dt(live.get("start_time")), live.get("lifetime_budget"), now)]
        elif field == "end_time":
            start = _dt(new.get("start_time", live.get("start_time")))
            out += [(field, m) for m in _end_problems(field, value, start, live.get("lifetime_budget"), now)]
        elif field == "start_time":
            if value is None:
                out.append((field, "Give it a start"))
            elif (now - _dt(value)).total_seconds() > 300:
                out.append((field, "The start can't be in the past: pick now or later."))
        elif field == "spend_cap" and value is not None and value < MIN_CAMPAIGN_CAP:
            out.append((field, f"Meta's lowest campaign spending cap is {words.money(MIN_CAMPAIGN_CAP)}."))
        elif field == "special_ad_categories":
            if set(live.get("special_ad_categories") or []) - set(value):
                out.append((field, "Meta only lets a special ad category be added after a campaign is made. Removing one is done in Ads Manager."))
            elif set(value) - set(CATEGORIES):
                out.append((field, "Pick one of Meta's special ad categories"))
            else:
                for a in ctx.get("adsets") or []:
                    out += [(field, m) for m in _special_problems(a.get("targeting") or {}, f"“{a.get('name')}”: ")]
        elif field == "targeting":
            out += [(field, m) for m in _audience_problems(c.get("value") or {})]
            if ctx.get("special"):  # each audience's kind as Meta or the account's list has it (never taken from the request)
                known = ctx.get("audiences") or {}
                metas = {str(a.get("id")): a for k in ("custom_audiences", "excluded_custom_audiences")
                         for a in (live.get("targeting") or {}).get(k) or [] if isinstance(a, dict)}

                def kind_of(i):
                    look = (metas.get(i) or {}).get("subtype") == "LOOKALIKE" or (known.get(i) or {}).get("kind") == "lookalike"
                    return {"id": i, "subtype": "LOOKALIKE" if look else None, "name": (metas.get(i) or known.get(i) or {}).get("name")}
                a = _audience_normal(c.get("value"))
                resolved = {"custom_audiences": [kind_of(i) for i in a["custom"] + a["excluded_custom"]]}
                out += [(field, m) for m in _special_problems({**(c.get("value") or {}), **resolved})]
        elif field == "placements" and not value["auto"]:
            if not value["platforms"]:
                out.append((field, "Pick at least one place to show it, or use Advantage+ placements"))
            for plat in ("facebook", "instagram"):
                if set(value[f"{plat}_positions"]) - set(POSITIONS[plat]):
                    out.append((field, f"Unknown {PLATFORM_WORDS[plat]} position"))
        elif field == "optimization_goal" and value not in GOALS:
            out.append((field, "Pick what it optimizes for"))
        elif field == "destination_type" and value not in DESTINATIONS:
            out.append((field, "Pick where people answer"))
        elif field == "billing_event" and value not in BILLING:
            out.append((field, "Pick what you pay for"))
        elif field == "attribution_spec" and value not in ATTRIBUTIONS:
            out.append((field, "Pick how results are counted"))
        elif field == "frequency_control_specs":
            goal = new.get("optimization_goal", live.get("optimization_goal"))
            if goal not in REACH_GOALS:
                out.append((field, REASONS["reach_goal"]))
            elif value and not (1 <= value["max"] <= 90 and 1 <= value["days"] <= 90):
                out.append((field, "Pick 1 to 90 times in 1 to 90 days"))
        elif field == "bid_amount":
            camp = ctx.get("campaign") or {}
            strategy = camp.get("bid_strategy") if _campaign_budget(camp) else new.get("bid_strategy", live.get("bid_strategy"))
            if not _capped(strategy):
                out.append((field, "A cost per result goal or bid cap needs that bidding: pick it under Bidding first."))
            elif value is None or value < 100:
                out.append((field, f"Enter at least {words.money(100)}"))
        if field == "bid_strategy" and level == "adset" and _capped(value) and not can.get(field):
            bid = new.get("bid_amount", live.get("bid_amount"))
            if not bid or bid < 100:
                out.append(("bid_amount", "Enter the cost per result goal (at least $1.00)"))
        if field == "bid_strategy" and level == "campaign" and _capped(value) and not can.get(field):
            bids = {**(live.get("adset_bids") or {}), **new.get("adset_bids", {})}
            missing = [a.get("name") or a["id"] for a in ctx.get("adsets") or [] if (bids.get(str(a["id"])) or 0) < 100]
            if missing:
                out.append(("adset_bids", "Enter a cost per result goal for each ad set: " + ", ".join(f"“{m}”" for m in missing)))
        if field == "adset_bids" and level == "campaign" and not can.get(field):
            if not _capped(new.get("bid_strategy", live.get("bid_strategy"))):
                out.append((field, "A cost per result goal needs that bidding on the campaign: pick it under Bidding first."))
            elif any(v is None or v < 100 for v in value.values()):
                out.append((field, f"Enter at least {words.money(100)} for each ad set"))
    return out


# ---------------------------------------------------------------- money

def _money(cents, currency):
    return words.money(cents, currency) if cents is not None else "none"


def _bid_questions(field, old, new, ctx, entity=None, name=None, currency="USD"):
    last = (ctx.get("last_bid") or {}).get(entity) if entity else (ctx.get("last_bid") or {}).get("self")
    ch = money_rules.bid_change(old, new, ctx.get("target_cpl"), ctx["cap"], last, ctx.get("now") if last else None)
    who = f" on “{name}”" if name else ""
    base = {"field": field, "entity": entity, "from": old, "to": new, "pct": ch["pct"]}
    if ch["over_cap"]:
        return [{**base, "code": "refused", "message": f"That goal{who} is above this account's highest daily budget "
                 f"({_money(ctx['cap'], currency)}): a goal above a day's budget means nothing. Raise the ceiling first if you mean it."}]
    out = []
    if ch["big"]:
        out.append({**base, "code": "big", "message": (f"Removing the cost per result goal{who} lets Meta pay whatever a result costs."
                                                         if ch["remove"] else f"That's +{ch['pct']}%{who}, more than +20% in one step; Meta may restart learning.")})
    if ch["recent"]:
        out.append({**base, "code": "recent", "message": f"The goal{who} last changed {money_rules.since_words(ch['hours'])}. "
                                                          "Raising it again this soon makes results hard to read."})
    if ch["high"]:
        out.append({**base, "code": "high", "message": f"That's more than {money_rules.BID_HIGH_TIMES}× your target cost per lead "
                                                        f"({_money(ctx.get('target_cpl'), currency)}){who}."})
    return out


def money(level, live, chs, ctx, currency="USD"):
    """The money questions these changes raise: [{field, code, message, …}]. code: refused (never sent) | big | recent | high
    (a knowing yes each) | danger (a second, danger yes) | spend (the turn-on confirmation of what it can spend)."""
    now = ctx.get("now") or datetime.now(timezone.utc)
    new = {c["field"]: c for c in chs}
    out = []
    if "bid_amount" in new:
        c = new["bid_amount"]
        old = c["old"] if _capped(live.get("bid_strategy")) or (ctx.get("campaign") or {}).get("bid_strategy") in CAPPED else None
        out += _bid_questions("bid_amount", old, c["new"], ctx, currency=currency)
    if "bid_strategy" in new and _capped(new["bid_strategy"]["old"]) and not _capped(new["bid_strategy"]["new"]):
        # Removing the goal is a big raise; the 3-day rule follows the last goal change of the ad set (or of any ad set of the
        # campaign, whose goals all go). Each question once.
        olds = ([(None, live.get("bid_amount") or 1)] if level == "adset" else
                [(str(a["id"]), a.get("bid_amount") or 1) for a in ctx.get("adsets") or []] or [(None, 1)])
        seen = set()
        for entity, old in olds:
            for q in _bid_questions("bid_strategy", old, None, ctx, entity, currency=currency):
                if q["code"] in ("big", "recent") and q["code"] not in seen:
                    seen.add(q["code"])
                    out.append({**q, "entity": None})
    if "adset_bids" in new:
        names = {str(a["id"]): a.get("name") for a in ctx.get("adsets") or []}
        for sid, cents in new["adset_bids"]["new"].items():
            out += _bid_questions("adset_bids", new["adset_bids"]["old"].get(sid), cents, ctx, sid, names.get(sid), currency)
    if "spend_cap" in new:
        c = new["spend_cap"]
        ch = money_rules.spend_cap_change(c["old"], c["new"], ctx.get("spent") or 0)
        if ch["refused"]:
            out.append({"field": "spend_cap", "code": "refused", "message": f"{ch['refused']} It has spent {_money(ch['spent'], currency)}."})
        elif ch["danger"]:
            out.append({"field": "spend_cap", "code": "danger", "from": c["old"], "to": c["new"],
                        "message": ("Removing the cap lets this campaign spend without a total limit." if ch["remove"] else
                                    f"That's more than {money_rules.CAMPAIGN_CAP_DANGER}× the current cap ({_money(c['old'], currency)}).")})
    when = [f for f in ("end_time", "stop_time", "start_time") if f in new]
    if when:
        field = when[0]
        wanted = {("start_time" if f == "start_time" else "end_time"): _dt(new[f]["new"]) for f in when}
        sched = money_rules.schedule_money(
            {"lifetime_budget": live.get("lifetime_budget"), "spent": ctx.get("spent"), "end_time": _dt(live.get("end_time") or live.get("stop_time")),
             "start_time": _dt(live.get("start_time")), "status": live.get("status")}, wanted, now, ctx["cap"], ctx.get("last_budget"))
        pace = sched["pace"]
        what = "new dates make" if len(when) > 1 else "new start makes" if field == "start_time" else "new end makes"
        if pace and pace["over_cap"]:
            out.append({"field": field, "code": "refused", "message": f"The {what} the lifetime budget spend {_money(pace['to'], currency)} a day, "
                        f"above this account's highest daily budget ({_money(ctx['cap'], currency)})."})
        elif pace and pace["big"]:
            out.append({"field": field, "code": "big", "from": pace["from"], "to": pace["to"], "pct": pace["pct"],
                        "message": f"The lifetime budget spends {_money(pace['from'], currency)} → {_money(pace['to'], currency)} a day "
                                   f"(+{pace['pct']}%), more than +20% in one step."})
        if pace and pace["recent"] and not pace["over_cap"]:
            out.append({"field": field, "code": "recent", "message": "The budget changed less than 3 days ago; spending faster this soon makes results hard to read."})
        if sched["turn_on"]:
            out.append({"field": field, "code": "spend", "lead": "It's on and its end has passed, so it starts spending again" if sched["resumes"]
                        else "It's on, so it starts spending earlier",
                        "message": ("It's on and its end has passed, so a new end starts it spending again: confirm what it can spend."
                                    if sched["resumes"] else "It's on, so it starts spending earlier: confirm what it can spend.")})
    return out


def money_problem(questions, accepts):
    """The first money question these accepts don't answer (refused is never answered), else None."""
    for q in questions:
        if q["code"] == "refused" or not (accepts or {}).get(q["code"]):
            return q
    return None


# ---------------------------------------------------------------- words

def _when(minute, tz):
    if not minute:
        return None
    from zoneinfo import ZoneInfo
    d = _dt(minute).astimezone(ZoneInfo(tz) if isinstance(tz, str) else tz)
    return f"{words.day(d)}, {words.clock(d)}"


def _place(loc):
    if loc.get("kind") == "country":
        return loc.get("name") or loc.get("key")
    return ab.location_label({**loc, "name": loc.get("name") or ("Map pin" if loc.get("kind") == "pin" else loc.get("key"))})


def audience_parts(t):
    """Who it reaches, part by part in words (the order the form shows them)."""
    t = t or {}
    genders = sorted({int(g) for g in t.get("genders") or [] if str(g) in ("1", "2")})
    parts = {"Places": ", ".join(_place(x) for x in t.get("locations") or []) or "none",
             "Ages": f"{t.get('age_min') or 18}–{t.get('age_max') or 65}",
             "Advantage+ audience": "on" if t.get("advantage") else "off",
             "Suggested ages": (f"{t['suggest_min']}–{t['suggest_max']}" if t.get("advantage") and t.get("suggest_min") and t.get("suggest_max") else "none"),
             "Gender": "Women" if genders == [2] else "Men" if genders == [1] else "Everyone",
             "Languages": ", ".join(LOCALE_NAMES.get(int(x), f"Language {x}") for x in t.get("locales") or []) or "any",
             "Detailed targeting": ", ".join(i.get("name") or i.get("id") for i in t.get("include") or []) or "none",
             "Excluded": ", ".join(i.get("name") or i.get("id") for i in t.get("exclude") or []) or "none",
             "Includes people in": _aud_names(t.get("custom_audiences")),
             "Leaves out people in": _aud_names(t.get("excluded_custom_audiences"))}
    return parts


def _aud_names(lst):
    return ", ".join(f"“{a.get('name') or a.get('id')}”" for a in lst or [] if isinstance(a, dict)) or "none"


def audience_words(t):
    p = audience_parts(t)
    places = [_place(x) for x in (t or {}).get("locations") or []]
    out = [", ".join(places[:2]) + (f" + {len(places) - 2} more" if len(places) > 2 else "") or "no places", f"ages {p['Ages']}"]
    if p["Gender"] != "Everyone":
        out.append(p["Gender"].lower())
    if p["Advantage+ audience"] == "on":
        out.append("Advantage+ audience")
    if p["Detailed targeting"] != "none":
        out.append(f"hints: {p['Detailed targeting']}")
    if p["Includes people in"] != "none":
        out.append(f"in {p['Includes people in']}")
    if p["Leaves out people in"] != "none":
        out.append(f"not in {p['Leaves out people in']}")
    return ", ".join(out)


def placements_words(p):
    p = _placements_normal(p)
    if p["auto"]:
        return "Advantage+ placements"
    out = []
    for plat in p["platforms"]:
        pos = p.get(f"{plat}_positions") or []
        out.append(PLATFORM_WORDS[plat] + (f" ({', '.join(POSITION_WORDS.get(x, x) for x in pos)})" if pos else ""))
    return ", ".join(out) or "nowhere"


def value_words(level, field, value, tz, currency="USD"):
    if field in ("start_time", "end_time", "stop_time"):
        return _when(value, tz) or ("No end date" if field != "start_time" else "none")
    if field in ("bid_amount", "spend_cap"):
        return _money(value, currency) if value is not None else ("No cap" if field == "spend_cap" else "none")
    if field == "bid_strategy":
        return sh.bid_words(value)
    if field == "targeting":
        return audience_words(value)
    if field == "placements":
        return placements_words(value)
    if field == "optimization_goal":
        return sh.goal_words(value)
    if field == "destination_type":
        return DESTINATION_WORDS.get(value, value or "none")
    if field == "billing_event":
        return BILLING_WORDS.get(value, value or "none")
    if field == "attribution_spec":
        return sh.attribution_words(value)
    if field == "frequency_control_specs":
        return sh.frequency_words(f"{value['max']}/{value['days']}" if value else None)
    if field == "special_ad_categories":
        return sh.category_words(",".join(value or []) or None)
    return str(value) if value not in (None, "") else "none"


def review(level, live, chs, tz, currency="USD", names=None):
    """The confirmation's lines: [{field, label, old_words, new_words, note}]. Who it reaches gives one line per part that
    changed ("Ages 25–65 → 30–65"); a cost per result goal on each ad set one line per ad set."""
    out = []
    for c in chs:
        field = c["field"]
        note = LEARNING_NOTE if field in LEARNING else None
        label = LABELS[field]
        if field == "bid_amount" and live.get("bid_strategy") == "LOWEST_COST_WITH_BID_CAP":
            label = "Bid cap"
        if field == "targeting":
            before, after = audience_parts(live.get("targeting")), audience_parts(c.get("value") or {})
            diff = [k for k in before if before[k] != after[k]]
            for i, k in enumerate(diff):
                out.append({"field": field, "label": k, "old_words": before[k], "new_words": after[k], "note": note if i == len(diff) - 1 else None})
            continue
        if field == "adset_bids":
            for sid, cents in c["new"].items():
                out.append({"field": field, "label": f"{label}: {(names or {}).get(sid) or sid}", "old_words": _money(c["old"].get(sid), currency),
                            "new_words": _money(cents, currency), "note": None})
            continue
        out.append({"field": field, "label": label, "old_words": value_words(level, field, c["old"], tz, currency),
                    "new_words": value_words(level, field, c["new"], tz, currency), "note": note})
    return out


def history_words(rows, field):
    """One History line for a field from its review rows: 'Ages 25–65 → 30–65; Advantage+ audience on → off'."""
    mine = [r for r in rows if r["field"] == field]
    if field == "name":
        return None
    return "; ".join(f"{r['label']} {r['old_words']} → {r['new_words']}" if field == "targeting"
                     else f"{r['label']}: {r['old_words']} → {r['new_words']}" for r in mine)


# ---------------------------------------------------------------- writing

def targeting_from(form, live_targeting, placements=None):
    """Meta's targeting for a form audience and/or placements, built on what Meta has now: every key the form doesn't manage
    (location types, Meta's own defaults) is kept as it is."""
    t = copy.deepcopy(live_targeting or {})
    if form is not None:
        geo = {k: v for k, v in (t.get("geo_locations") or {}).items() if k not in PLACE_KEYS}
        geo.setdefault("location_types", ["home", "recent"])
        for loc in form.get("locations") or []:
            kind = loc.get("kind")
            if kind == "pin":
                pin = {"latitude": float(loc["latitude"]), "longitude": float(loc["longitude"]), "radius": int(loc["radius"]), "distance_unit": "mile"}
                if loc.get("city_id"):
                    pin["primary_city_id"] = int(loc["city_id"]) if str(loc["city_id"]).isdigit() else loc["city_id"]
                geo.setdefault("custom_locations", []).append(pin)
            elif kind == "city":
                geo.setdefault("cities", []).append({"key": str(loc["key"]), "radius": int(loc["radius"]), "distance_unit": "mile"})
            elif kind in ("region", "zip"):
                geo.setdefault(f"{kind}s", []).append({"key": str(loc["key"])})
            elif kind == "country":
                geo.setdefault("countries", []).append(str(loc["key"]))
        t["geo_locations"] = geo
        t["age_min"], t["age_max"] = int(form.get("age_min") or 18), int(form.get("age_max") or 65)
        auto = dict(t.get("targeting_automation") or {})
        auto["advantage_audience"] = 1 if form.get("advantage") else 0
        t["targeting_automation"] = auto
        t.pop("age_range", None)
        if form.get("advantage") and form.get("suggest_min") and form.get("suggest_max"):
            t["age_range"] = [int(form["suggest_min"]), int(form["suggest_max"])]
        for key, value in (("genders", sorted({int(g) for g in form.get("genders") or [] if str(g) in ("1", "2")})),
                           ("locales", sorted({int(x) for x in form.get("locales") or [] if str(x).isdigit()}))):
            if value and value != [1, 2]:
                t[key] = value
            else:
                t.pop(key, None)
        groups = {}
        for i in form.get("include") or []:
            if i.get("type") in DETAIL_TYPES and str(i.get("id") or "").isdigit():
                groups.setdefault(int(i.get("group") or 0), {}).setdefault(i["type"], []).append({"id": str(i["id"]), "name": i.get("name")})
        if groups:
            t["flexible_spec"] = [groups[g] for g in sorted(groups)]
        else:
            t.pop("flexible_spec", None)
        excl = {}
        for i in form.get("exclude") or []:
            if i.get("type") in DETAIL_TYPES and str(i.get("id") or "").isdigit():
                excl.setdefault(i["type"], []).append({"id": str(i["id"]), "name": i.get("name")})
        if excl:
            t["exclusions"] = excl
        else:
            t.pop("exclusions", None)
        for key in ("custom_audiences", "excluded_custom_audiences"):
            ids = [{"id": str(a["id"])} for a in form.get(key) or [] if str(a.get("id") or "").isdigit()]
            if ids:
                t[key] = ids
            else:
                t.pop(key, None)
    if placements is not None:
        p = _placements_normal(placements)
        for key in sh.PLACEMENT_KEYS:
            t.pop(key, None)
        if not p["auto"]:
            t["publisher_platforms"] = p["platforms"]
            for plat in ("facebook", "instagram"):
                if p[f"{plat}_positions"]:
                    t[f"{plat}_positions"] = p[f"{plat}_positions"]
    return t


def _attribution_spec(key):
    out = []
    for days, kind in zip(key.split("_")[0::2], key.split("_")[1::2]):
        event = {v: k for k, v in sh.ATTRIBUTION_EVENTS.items()}[kind]
        out.append({"event_type": event, "window_days": int(days.rstrip("d"))})
    return out


def meta_params(level, chs, live_targeting=None):
    """The one Graph POST /{id} for these changes: only the changed fields, objects as JSON strings."""
    out = {}
    by = {c["field"]: c for c in chs}
    for field, c in by.items():
        value = c["new"]
        if field in ("start_time", "end_time", "stop_time"):
            out[field] = meta_time(value) if value else "0"
        elif field in ("bid_amount",):
            out[field] = str(int(value))
        elif field == "spend_cap":
            out[field] = str(int(value)) if value is not None else NO_SPEND_CAP
        elif field == "special_ad_categories":
            out[field] = json.dumps(value)
        elif field == "attribution_spec":
            out[field] = json.dumps(_attribution_spec(value))
        elif field == "frequency_control_specs":
            out[field] = json.dumps([{"event": "IMPRESSIONS", "interval_days": value["days"], "max_frequency": value["max"]}] if value else [])
        elif field in ("targeting", "placements", "adset_bids"):
            continue
        else:
            out[field] = value
    if "targeting" in by or "placements" in by:
        merged = targeting_from(by["targeting"].get("value") if "targeting" in by else None, live_targeting,
                                by["placements"]["new"] if "placements" in by else None)
        out["targeting"] = json.dumps(merged)
    return out


def readback_ok(chs, fresh):
    """Fields whose fresh read differs from what was sent (`fresh` in the form's shape): named in History and to the person."""
    return [c["field"] for c in chs if c["field"] != "adset_bids" and normal(c["field"], fresh.get(c["field"])) != c["new"]]


def change_text(field, value, merged_targeting=None):
    """The machine part of a meta_changes value: what status_history.console_value reads to tell an Edit from an Ads Manager change.
    The History words follow it after a space."""
    if field == "start_time":
        return f"start {_time(value) or 'none'}"
    if field in ("end_time", "stop_time"):
        return f"end {_time(value) or 'none'}"
    if field == "targeting":
        return f"fp:{sh.targeting_fingerprint(merged_targeting)}"
    if field == "placements":
        return f"fp:{sh.placements_fingerprint(merged_targeting)} tfp:{sh.targeting_fingerprint(merged_targeting)}"
    if field in ("bid_amount", "spend_cap"):
        return str(_int(value)) if _int(value) else "none"
    if field == "special_ad_categories":
        return sh.categories_key(value) or "none"
    if field == "frequency_control_specs":
        return f"{value['max']}/{value['days']}" if value else "none"
    return str(value) if value not in (None, "") else "none"
