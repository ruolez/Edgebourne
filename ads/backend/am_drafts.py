"""AM-B: Ads Manager drafts, read through the Mac link (AM-A). Pure.

The Graph API never returns what Eugene (or Claude on his Mac) staged in Ads Manager without publishing; Meta's Ads MCP
server does (`ads_get_ad_entities` with `object_state: "draft"`). The link pushes that answer here and this module turns
it into rows (listed fields only, strings cut, ids digits only), a tree (campaign → ad sets → ads), what each draft still
lacks, whether the console can finish it, the builders' prefill (New campaign / New ad set / New ad), a staged edit as
old → new rows, the Inbox items, and the words the screens show.

Nothing here writes to Meta. A draft only prefills a builder; the builder creates what the person submits, paused, with
its own checks. Meta's text is data: it is cut, never altered and never turned into HTML or a link."""
import math
import re
from datetime import datetime, timezone

import adset_build as ab
import campaign_build as cb
import words

STR_MAX, NAME_MAX, TITLE_MAX, TEXT_MAX = 300, 200, 255, 5000
LIST_MAX = 50
ROWS_MAX = 200
PROBLEMS_MAX = 20

ID, INT, NUM, STR, NAME, TITLE, TEXT, HASH, WHEN = "id", "int", "num", "str", "name", "title", "text", "hash", "when"


def _list(schema, n=LIST_MAX):
    return ("list", schema, n)


NAMED = {"id": ID, "name": STR}
PLACE = {"key": STR, "name": STR, "radius": NUM, "distance_unit": STR, "country": STR, "region": STR}
PIN = {"latitude": NUM, "longitude": NUM, "radius": NUM, "distance_unit": STR, "name": STR, "address_string": STR, "primary_city_id": ID}
GEO = {"countries": _list(STR), "regions": _list(PLACE), "cities": _list(PLACE), "zips": _list(PLACE), "custom_locations": _list(PIN),
       "location_types": _list(STR)}
HINTS = {"interests": _list(NAMED), "behaviors": _list(NAMED), "work_positions": _list(NAMED)}
# The audience keys status_history compares (AUDIENCE_KEYS) plus the Advantage+ switch and its suggested ages.
TARGETING = {"geo_locations": GEO, "excluded_geo_locations": GEO, "age_min": INT, "age_max": INT, "age_range": _list(INT, 2),
             "genders": _list(INT, 2), "locales": _list(INT), "flexible_spec": _list(HINTS, 10), "exclusions": HINTS,
             "custom_audiences": _list(NAMED), "excluded_custom_audiences": _list(NAMED), "publisher_platforms": _list(STR),
             "facebook_positions": _list(STR), "instagram_positions": _list(STR), "device_platforms": _list(STR),
             "targeting_automation": {"advantage_audience": INT}}
CTA = {"type": STR, "value": {"lead_gen_form_id": ID, "link": STR}}
CREATIVE = {"creative_id": ID, "object_story_spec": {
    "page_id": ID,
    "link_data": {"message": TEXT, "name": TITLE, "description": TEXT, "link": STR, "image_hash": HASH, "call_to_action": CTA},
    "video_data": {"message": TEXT, "title": TITLE, "video_id": ID, "image_hash": HASH, "call_to_action": CTA}}}
# Whitelisted values per object type; any other field Meta sends is kept by name only (other_fields).
FIELDS = {
    "campaign": {"name": NAME, "objective": STR, "buying_type": STR, "daily_budget": INT, "lifetime_budget": INT, "bid_strategy": STR,
                 "spend_cap": INT, "special_ad_categories": _list(STR), "start_time": WHEN, "stop_time": WHEN, "status": STR},
    "adset": {"name": NAME, "campaign_id": ID, "daily_budget": INT, "lifetime_budget": INT, "bid_strategy": STR, "bid_amount": INT,
              "optimization_goal": STR, "billing_event": STR, "destination_type": STR,
              "promoted_object": {"page_id": ID, "pixel_id": ID, "custom_event_type": STR}, "targeting": TARGETING,
              "start_time": WHEN, "end_time": WHEN, "attribution_spec": _list({"event_type": STR, "window_days": INT}, 10), "status": STR},
    "ad": {"name": NAME, "adset_id": ID, "creative": CREATIVE, "status": STR},
}
TYPES = {"campaign": "campaign", "campaign_group": "campaign", "adset": "adset", "ad_set": "adset", "ad": "ad"}
# Staged edits the console applies with its own forms (AM-C wires them; until then "Change it in Ads Manager").
# AM-C: staged edits the console's Edit form applies (prefilled from the draft); the rest stay "Change it in Ads Manager".
EDIT_FIELDS = frozenset({"name", "bid_strategy", "bid_amount", "spend_cap", "start_time", "end_time", "stop_time", "optimization_goal"})

GOALS = {"OUTCOME_LEADS": "Leads", "OUTCOME_SALES": "Sales", "OUTCOME_TRAFFIC": "Traffic", "OUTCOME_AWARENESS": "Awareness",
         "OUTCOME_ENGAGEMENT": "Engagement", "OUTCOME_APP_PROMOTION": "App promotion"}
DESTINATIONS = {"WEBSITE": "a website", "MESSENGER": "Messenger", "WHATSAPP": "WhatsApp", "INSTAGRAM_DIRECT": "Instagram messages",
                "PHONE_CALL": "a phone call", "APP": "an app", "ON_POST": "a post", "ON_VIDEO": "a video", "ON_PAGE": "a Facebook Page"}
BIDS = {"LOWEST_COST_WITHOUT_CAP": "lowest cost", "COST_CAP": "cost cap", "LOWEST_COST_WITH_BID_CAP": "bid cap",
        "LOWEST_COST_WITH_MIN_ROAS": "minimum return"}
CAPPED = {"COST_CAP": "Cost cap", "LOWEST_COST_WITH_BID_CAP": "Bid cap", "LOWEST_COST_WITH_MIN_ROAS": "Minimum return"}
CTA_WORDS = {"SIGN_UP": "Sign up", "BOOK_TRAVEL": "Book now", "LEARN_MORE": "Learn more", "GET_QUOTE": "Get quote", "APPLY_NOW": "Apply now",
             "SUBSCRIBE": "Subscribe", "DOWNLOAD": "Download"}
WHAT = {"campaign": "a campaign", "adset": "an ad set", "ad": "an ad"}
EDGES = {"campaign": ("campaigns", "selected_campaign_ids"), "adset": ("adsets", "selected_adset_ids"), "ad": ("ads", "selected_ad_ids")}
# A staged edit: how each setting reads, how it's shown, and where our stored value lives.
EDIT_LABELS = {"daily_budget": ("Daily budget", "money"), "lifetime_budget": ("Lifetime budget", "money"), "spend_cap": ("Spending limit", "money"),
               "bid_amount": ("Bid", "money"), "name": ("Name", "text"), "status": ("On or off", "status"), "bid_strategy": ("Bidding", "text"),
               "start_time": ("Starts", "time"), "stop_time": ("Ends", "time"), "end_time": ("Ends", "time"), "targeting": ("Who sees it", "audience"),
               "optimization_goal": ("Optimized for", "text"), "creative": ("Words and media", "creative"), "objective": ("Goal", "text")}
LIVE_KEYS = {"daily_budget": "daily_budget_cents", "lifetime_budget": "lifetime_budget_cents", "name": "name", "status": "status",
             "bid_strategy": "bid_strategy"}


# ---------------------------------------------------------------- cleaning

def _digits(v):
    s = str(v).strip() if isinstance(v, (str, int)) and not isinstance(v, bool) else ""
    return s if re.fullmatch(r"\d{1,30}", s) else None


def _int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and math.isfinite(v) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"-?\d{1,15}", v.strip()):
        return int(v)
    return None


def _clean(schema, v):
    """The value kept under `schema`, or None when it isn't that kind of value."""
    if isinstance(schema, tuple):
        if not isinstance(v, list):
            return None
        items = [_clean(schema[1], x) for x in v[:schema[2]]]
        return [x for x in items if x is not None]
    if isinstance(schema, dict):
        if not isinstance(v, dict):
            return None
        out = {}
        for k, sub in schema.items():
            if k in v:
                c = _clean(sub, v[k])
                if c is not None:
                    out[k] = c
        return out
    if schema == ID:
        return _digits(v)
    if schema == INT:
        return _int(v)
    if schema == NUM:
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None
    if schema == HASH:
        return v if isinstance(v, str) and re.fullmatch(r"[0-9a-fA-F]{32,64}", v) else None
    if schema == WHEN:
        return v[:40] if isinstance(v, str) else _int(v)
    cut = {STR: STR_MAX, NAME: NAME_MAX, TITLE: TITLE_MAX, TEXT: TEXT_MAX}[schema]
    return v[:cut] if isinstance(v, str) else None


def _field(schema, entry):
    """{"new": x[, "old": y]} kept, or None when the entry isn't Meta's {new, old} shape or its new value is the wrong kind."""
    if not isinstance(entry, dict) or not ({"new", "old"} & set(entry)):
        return None
    out = {}
    for side in ("new", "old"):
        if side not in entry:
            continue
        if entry[side] is None:
            out[side] = None
            continue
        c = _clean(schema, entry[side])
        if c is None:
            if side == "new":
                return None
            continue
        out[side] = c
    return out


def _message(item):
    if isinstance(item, str):
        return item[:STR_MAX] or None
    if not isinstance(item, dict):
        return None
    for k in ("message", "error_message", "error_user_msg", "error_summary", "summary", "description", "error_user_title"):
        if isinstance(item.get(k), str) and item[k].strip():
            return item[k][:STR_MAX]
    return None


def _problems(active, publish):
    out = []
    for item in (active if isinstance(active, list) else []) + ([publish] if publish else []):
        msg = _message(item)
        if not msg:
            continue
        field = item.get("field") or item.get("error_field") if isinstance(item, dict) else None
        out.append({"message": msg, "field": field[:60] if isinstance(field, str) else None})
        if len(out) >= PROBLEMS_MAX:
            break
    return out


def _time(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0:
        return datetime.fromtimestamp(v, timezone.utc)
    return _parse(v) if isinstance(v, str) else None


def _parse(s):
    """An ISO time as Meta writes it ('2026-11-01T09:00:00-0800' or with a colon), aware; None otherwise."""
    s = str(s).strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    try:
        at = datetime.fromisoformat(s)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _word(v, n=40):
    return v[:n] if isinstance(v, str) and v.strip() else None


def _row(d):
    if not isinstance(d, dict):
        return None
    kind = TYPES.get(str(d.get("ad_object_type") or "").lower())
    oid = _digits(d.get("ad_object_id"))
    if not kind or not oid:
        return None
    action = str(d.get("action") or "add").lower()[:20]
    fields, other = {}, []
    values = d.get("values") if isinstance(d.get("values"), dict) else {}
    for name, entry in values.items():
        schema = FIELDS[kind].get(name)
        kept = _field(schema, entry) if schema is not None else None
        if kept is None:
            other.append(str(name)[:60])
        else:
            fields[name] = kept
    return {"draft_id": oid, "object_type": kind, "parent_id": _digits(d.get("parent_ad_object_id")),
            "action": action if re.fullmatch(r"[a-z_]+", action) else "edit", "meta_status": _word(d.get("status")),
            "validation_status": _word(d.get("validation_status")), "source": _word(d.get("source"), 60),
            "time_updated": _time(d.get("time_updated")), "fields": fields, "other_fields": sorted(other)[:LIST_MAX],
            "problems": _problems(d.get("active_errors"), d.get("publish_error"))}


def normalize(raw):
    """Meta's {"ad_drafts": [...]} (the Mac joins the cursor pages) → rows for am_drafts; None for any other shape."""
    items = raw if isinstance(raw, list) else raw.get("ad_drafts") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return None
    rows = [r for r in (_row(d) for d in items[:ROWS_MAX * 2]) if r]
    return rows[:ROWS_MAX]


def is_complete(raw):
    """Whether every page came back: the Mac says so (`complete`); a single page complete when Meta offers no next one.
    Only a complete read may call a draft gone."""
    if isinstance(raw, dict) and "complete" in raw:
        return raw["complete"] is True
    paging = (raw.get("paging") if isinstance(raw, dict) else None) or {}
    return not (paging.get("next") and (paging.get("cursors") or {}).get("after"))


def keep_own(rows, own_ids):
    """(rows, dropped): a staged edit of an object this account doesn't hold, or a new draft under a live object it doesn't
    hold, is left out (the Mac's Facebook login sees every ad account; a draft never crosses into another account)."""
    added = {r["draft_id"] for r in rows if r["action"] == "add"}
    kept = [r for r in rows if (r["draft_id"] in own_ids if r["action"] != "add"
                                else r["parent_id"] is None or r["parent_id"] in own_ids or r["parent_id"] in added)]
    return kept, len(rows) - len(kept)


# ---------------------------------------------------------------- the tree and what it lacks

CHILD = {"adset": "campaign", "ad": "adset"}


def _when_key(r):
    t = r.get("time_updated")
    return (t is not None, t.timestamp() if t else 0.0)


def tree(rows):
    """Campaign drafts with their ad set drafts and those with their ad drafts (new ones only, by parent). A draft whose
    parent is a live object, and every staged edit, stands alone (`parent_live`). Newest first; children oldest first."""
    nodes = {r["draft_id"]: {**r, "adsets": [], "ads": [], "parent_live": None} for r in rows}
    roots = []
    for r in sorted(rows, key=lambda x: (_when_key(x), x["draft_id"])):
        node = nodes[r["draft_id"]]
        parent = nodes.get(r["parent_id"]) if r["action"] == "add" and r["parent_id"] else None
        if parent and parent["action"] == "add" and CHILD.get(r["object_type"]) == parent["object_type"]:
            parent["adsets" if r["object_type"] == "adset" else "ads"].append(node)
        else:
            node["parent_live"] = r["parent_id"]
            roots.append(node)
    return sorted(roots, key=lambda n: (_when_key(n), n["draft_id"]), reverse=True)


def shown_rows(rows):
    """The rows the cards show: those flagged `shown` (open, or finished lately), plus the ad sets and ads a finished
    draft held when it was finished, even after Ads Manager dropped them with it (gone no earlier than the finish)."""
    by_id = {r["draft_id"]: r for r in rows}

    def kept_by_finish(r):
        seen, cur = 0, r
        while cur["action"] == "add" and cur.get("parent_id") in by_id and seen < 5:
            cur, seen = by_id[cur["parent_id"]], seen + 1
            if cur.get("shown") and cur.get("finished_at") and r.get("gone_at") and r["gone_at"] >= cur["finished_at"]:
                return True
        return False
    return [r for r in rows if r.get("shown") or kept_by_finish(r)]


def new(node, field, default=None):
    v = (node.get("fields") or {}).get(field)
    return v.get("new", default) if isinstance(v, dict) and v.get("new") is not None else default


def _story(ad):
    return (new(ad, "creative", {}) or {}).get("object_story_spec") or {}


def _ad_parts(ad):
    """(media for the builders, headline, text, button, lead form id, page id) of an ad draft."""
    story = _story(ad)
    video = story.get("video_data") or {}
    link = story.get("link_data") or {}
    data = video or link
    media = ({"kind": "video", "video_id": video["video_id"]} if video.get("video_id")
             else {"kind": "image", "hash": link["image_hash"]} if link.get("image_hash") else {"kind": "none"})
    cta = data.get("call_to_action") or {}
    return {"media": media, "title": video.get("title") if video else link.get("name"), "body": data.get("message"),
            "cta": cta.get("type"), "form": (cta.get("value") or {}).get("lead_gen_form_id"), "page": story.get("page_id")}


def _ads_of(node):
    return node["ads"] if node["object_type"] == "adset" else [a for s in node["adsets"] for a in s["ads"]]


def _geo(targeting):
    return (targeting or {}).get("geo_locations") or {}


def _has_places(targeting):
    g = _geo(targeting)
    return any(g.get(k) for k in ("countries", "regions", "cities", "zips", "custom_locations"))


def _first_set(node):
    if node["object_type"] == "adset":
        return node
    return node["adsets"][0] if node["adsets"] else None


def missing(node):
    """What a new draft lacks before the console can create it, in plain words ([] when nothing). Staged edits lack nothing."""
    if node["action"] != "add":
        return []
    out = []
    kind = node["object_type"]
    if kind == "campaign":
        budgeted = new(node, "daily_budget") or new(node, "lifetime_budget") or any(
            new(s, "daily_budget") or new(s, "lifetime_budget") for s in node["adsets"])
        if not budgeted:
            out.append("No daily budget")
        if not node["adsets"]:
            out.append("No ad set yet")
    first = _first_set(node)
    if first is not None and not _has_places(new(first, "targeting", {})):
        out.append("No places or ages for the ad set")
    ads = [node] if kind == "ad" else first["ads"] if first is not None else []
    if kind != "ad" and not ads:
        out.append("No ads yet")
    for i, ad in enumerate(ads, 1):
        p = _ad_parts(ad)
        label = "The ad" if kind == "ad" else f"Ad {i}"
        if not p["form"]:
            out.append(f"{label} has no lead form")
        if p["media"]["kind"] == "none":
            out.append(f"{label} has no picture or video")
    has_set = first is not None or kind == "ad"
    page = (first is not None and (new(first, "promoted_object", {}) or {}).get("page_id")) or any(_ad_parts(a)["page"] for a in ads)
    if has_set and not page:
        out.append("No Facebook Page")
    return out


def _goal_words(objective):
    return GOALS.get(objective) or str(objective).replace("OUTCOME_", "").replace("_", " ").capitalize()


def finishable(node):
    """None when the console can finish this draft, else why not (it is then opened in Ads Manager). The console builds
    auction lead campaigns with a daily budget and an Instant Form; no constraint of a draft is ever silently dropped."""
    if node["action"] != "add":
        return "This draft changes something that's already running: apply it below."
    if node["object_type"] == "campaign":
        objective = new(node, "objective")
        if objective and objective != "OUTCOME_LEADS":
            return f"This draft's goal is {_goal_words(objective)}; the console builds lead campaigns only."
        buying = new(node, "buying_type")
        if buying and buying != "AUCTION":
            return "This draft buys reach and frequency; the console builds auction campaigns only."
        special = [c for c in new(node, "special_ad_categories", []) or [] if c and c != "NONE"]
        if special:
            return f"This draft is in a special ad category ({', '.join(c.lower().replace('_', ' ') for c in special)}); finish it in Ads Manager."
    sets = node["adsets"] if node["object_type"] == "campaign" else [node] if node["object_type"] == "adset" else []
    if new(node, "lifetime_budget") or any(new(s, "lifetime_budget") for s in sets):
        return "This draft has a lifetime budget; the console sets daily budgets."
    for s in sets:
        dest = new(s, "destination_type")
        if dest and dest != "ON_AD":
            return (f"This draft's ad set sends people to {DESTINATIONS.get(dest, 'somewhere else')}, not an Instant Form; "
                    "the console builds Instant Form ads only.")
    return None


# ---------------------------------------------------------------- the builders' prefill

def _day(value, tz):
    at = _time(value)
    return words.local(at, tz).date() if at else None


def _money(cents, currency):
    return words.money(cents, currency)


def _adset_fields(s, tz, today, notes, extra_start=None, extra_end=None):
    """New ad set's / New campaign's "Who sees it" fields from an ad set draft (the page's own form shape)."""
    targeting = new(s, "targeting", {}) or {}
    base = ab.spec_from({"targeting": targeting})
    flexible = targeting.get("flexible_spec") or []
    countries = _geo(targeting).get("countries") or []
    if countries:
        notes.append(f"The draft reaches whole countries ({', '.join(countries)}); this page picks cities, regions or ZIP codes: add them in Who sees it.")
    start, end = _day(new(s, "start_time") or extra_start, tz), _day(new(s, "end_time") or extra_end, tz)
    if start and start <= today:
        notes.append("The draft's start date has passed; it starts when you publish.")
        start = None
    return {"template_adset_id": "", "name": new(s, "name", "") or "", "locations": base["locations"], "age_min": base["age_min"],
            "age_max": base["age_max"], "suggest_min": base["suggest_min"], "suggest_max": base["suggest_max"], "advantage": base["advantage"],
            "keep_hints": bool(base["hints"]), "hints": base["hints"], "flexible_spec": flexible,
            "start_day": start.isoformat() if start else None, "start_hour": 0, "end_day": end.isoformat() if end and (not start or end > start) else None,
            "end_hour": 23}


def _bid_note(strategy, amount, currency):
    if strategy not in CAPPED and not amount:
        return None
    what = CAPPED.get(strategy, "Bid cap")
    return f"{what}{f' of {_money(amount, currency)}' if amount else ''}: this page uses lowest cost. Set the cap in Ads Manager after creating."


def _ad_fields(ad, i, notes, label=None):
    p = _ad_parts(ad)
    cta = p["cta"] or "SIGN_UP"
    if cta not in cb.CTA_FOR_FORMS:
        notes.append(f"{label or f'Ad {i + 1}'}'s button ({cta}) doesn't open a lead form; it's set to Sign up.")
        cta = "SIGN_UP"
    return {"name": new(ad, "name", "") or f"Ad {i + 1}", "title": p["title"] or "", "body": p["body"] or "", "cta_type": cta,
            "template_ad_id": "", "media": p["media"]}, p["form"]


def _form(forms, known_forms, notes):
    chosen = next((f for f in forms if f), None)
    if len({f for f in forms if f}) > 1:
        notes.append("The draft's ads use different lead forms; this page uses one for all of them.")
    if chosen and chosen not in known_forms:
        notes.append(f"The draft's lead form ({chosen}) isn't one of this account's forms: pick one in the Lead form step.")
        return ""
    return chosen or ""


def _today(tz, today):
    return today or datetime.now(tz).date()


def to_campaign_spec(node, known_forms, page_id, tz, today=None, currency="USD"):
    """(New campaign's form filled in, notes on what it couldn't carry over). The page submits what the person keeps;
    the create route cleans and checks it like typing (a budget over the ceiling stays as it is, so the wizard refuses it)."""
    notes = []
    sets = node["adsets"]
    s = sets[0] if sets else {"fields": {}, "ads": []}
    budget = new(node, "daily_budget")
    if budget is None and new(s, "daily_budget"):
        budget = new(s, "daily_budget")
        notes.append(f"The draft keeps its {_money(budget, currency)} daily budget on the ad set; this page puts it on the campaign.")
    bid = _bid_note(new(node, "bid_strategy") or new(s, "bid_strategy"), new(s, "bid_amount"), currency)
    if bid:
        notes.append(bid)
    draft_page = (new(s, "promoted_object", {}) or {}).get("page_id") or next((p for p in (_ad_parts(a)["page"] for a in s["ads"]) if p), None)
    if draft_page and page_id and draft_page != page_id:
        notes.append(f"The draft names another Facebook Page ({draft_page}); the console uses this account's Page.")
    if len(sets) > 1:
        notes.append(f"The draft has {len(sets)} ad sets; this page makes the first. Make the others with New ad set after creating.")
    ads = s["ads"]
    if len(ads) > cb.MAX_ADS:
        notes.append(f"The draft has {len(ads)} ads; this page makes the first {cb.MAX_ADS}. Add the rest with New ad after creating.")
    out_ads, forms = [], []
    for i, ad in enumerate(ads[:cb.MAX_ADS]):
        spec, form = _ad_fields(ad, i, notes)
        out_ads.append(spec)
        forms.append(form)
    form_id = _form(forms, known_forms, notes)
    adset = _adset_fields(s, tz, _today(tz, today), notes, new(node, "start_time"), new(node, "stop_time"))
    return {"name": new(node, "name", "") or "", "daily_budget_cents": budget, "form_id": form_id, "adset": adset, "ads": out_ads}, notes


def to_adset_spec(node, campaign, tz, today=None, currency="USD"):
    """New ad set filled in from an ad set draft under a live campaign: {campaign_id, template_adset_id, spec}, notes."""
    notes = []
    bid = _bid_note(new(node, "bid_strategy"), new(node, "bid_amount"), currency)
    if bid:
        notes.append(bid)
    own = new(node, "daily_budget")
    if campaign.get("daily_budget_cents") is not None and own:
        notes.append(f"The campaign shares its budget, so the draft's {_money(own, currency)} for this ad set isn't used.")
    spec = _adset_fields(node, tz, _today(tz, today), notes)
    spec.pop("template_adset_id")
    spec["daily_budget_cents"] = own if campaign.get("daily_budget_cents") is None else None
    return {"campaign_id": campaign["id"], "template_adset_id": "", "spec": spec}, notes


def to_ad_spec(node, known_forms):
    """New ad filled in from an ad draft under a live ad set: the payload New ad posts, notes."""
    notes = []
    ad, form = _ad_fields(node, 0, notes, label="The ad")
    form_id = _form([form], known_forms, notes)
    return {"adset_id": node["parent_id"] or "", "template_ad_id": "", "name": ad["name"], "title": ad["title"], "body": ad["body"],
            "cta_type": ad["cta_type"], "form_id": form_id, "media": ad["media"]}, notes


# ---------------------------------------------------------------- staged edits

def edit_rows(node, live, edit_fields=EDIT_FIELDS):
    """A staged edit of a live object as [{field, label, kind, old, new, now, stale, apply, applied}]: `now` is our stored
    value, `stale` when Ads Manager changed it since the draft was made, `apply` how the console applies it: the budget
    dialog ('budget'), the on/off confirmation ('status'), an edit form ('edit') or not here ('manager')."""
    out = []
    applied = node.get("applied") or {}
    order = list(EDIT_LABELS)
    fields = sorted((node.get("fields") or {}).items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else len(order), kv[0]))
    for field, entry in fields:
        label, kind = EDIT_LABELS.get(field, (field.replace("_", " ").capitalize(), "text"))
        now = live.get(LIVE_KEYS[field]) if field in LIVE_KEYS else None
        old = entry.get("old")
        value = entry.get("new")
        if field == "daily_budget" and live.get("daily_budget_cents") is not None and isinstance(value, int):
            how = "budget"
        elif field == "status" and value in ("ACTIVE", "PAUSED"):
            how = "status"
        elif field in edit_fields:
            how = "edit"
        else:
            how = "manager"
        out.append({"field": field, "label": label, "kind": kind, "old": old, "new": value, "now": now,
                    "stale": "old" in entry and now is not None and old != now, "apply": how, "applied": applied.get(field)})
    return out


# ---------------------------------------------------------------- Inbox

def name_of(node, fallback="Untitled draft"):
    """A new draft by its own name; a staged edit by the name it changes (Meta's old value, else `fallback`, our stored one)."""
    old = ((node.get("fields") or {}).get("name") or {}).get("old")
    if node.get("action", "add") != "add":
        return old or (fallback if fallback != "Untitled draft" else None) or new(node, "name") or fallback
    return new(node, "name") or fallback


def href(draft_id):
    return f"/ads.html?level=campaign&view=drafts#draft={draft_id}"


def root_problems(rows):
    """{top-level draft id: Meta's problems with it and everything under it} (the Inbox has one item per draft)."""
    return {n["draft_id"]: all_problems(n) for n in tree(rows)}


def inbox_events(before, after, complete, rules, today, tz):
    """(alerts to raise, draft ids whose problem alert closes), one item per top-level draft. before: {draft_id: row} as
    stored before this read; after: the rows this read returned. New draft → `draft_new` (FYI, once); problems with it or
    anything under it → `draft_problems` (FYI condition, one per day while they last), closed when they clear or a complete
    read no longer lists the draft. A draft the console finished never raises one."""
    found, resolve = [], []
    on = lambda rule: (rules.get(rule) or {}).get("on", True)  # noqa: E731
    was = root_problems(list(before.values()))
    roots = tree(after)
    for n in roots:
        rid, name = n["draft_id"], name_of(n)
        finished = bool(n.get("finished_at"))
        problems = all_problems(n)
        if rid not in before and not finished and on("draft_new"):
            at = last_edited(n)
            found.append({"rule": "draft_new", "entity_id": rid, "key": f"draft_new:{rid}", "level": "info", "kind": "event",
                          "title": f"New draft in Ads Manager: “{name}”", "campaign_id": None, "href": href(rid), "measure": None,
                          "lines": [f"Edited in Ads Manager {words.day_time(at, tz)}" if at else "Read from Ads Manager",
                                    "Finish it here or open it in Ads Manager."]})
        if problems and not finished and on("draft_problems"):
            more = len(problems) - 1
            found.append({"rule": "draft_problems", "entity_id": rid, "key": f"draft_problems:{rid}:{today.isoformat()}", "level": "info",
                          "kind": "condition", "title": f"Meta has problems with your draft “{name}”", "campaign_id": None,
                          "href": href(rid), "measure": len(problems),
                          "lines": [problems[0]["message"]] + ([f"+{more} more"] if more else [])})
        elif was.get(rid):
            resolve.append(rid)
    if complete:
        seen = {n["draft_id"] for n in roots}
        resolve += [rid for rid, p in was.items() if rid not in seen and p]
    return found, resolve


# ---------------------------------------------------------------- words

def _plural(n, one, many=None):
    return f"{n} {one if n == 1 else many or one + 's'}"


def _who(s):
    targeting = new(s, "targeting", {}) or {}
    labels = [ab.location_label(loc) for loc in ab.locations_from(targeting)] + list(_geo(targeting).get("countries") or [])
    places = (", ".join(labels[:2]) + (f" +{len(labels) - 2}" if len(labels) > 2 else "")) if labels else "no places yet"
    lo, hi = targeting.get("age_min"), targeting.get("age_max")
    return f"{places}, ages {lo or 18}–{hi or 65}"


def what_words(node, currency):
    """"New campaign · Leads · $20.00 a day · lowest cost", "Changes to a campaign that's running", …"""
    kind = node["object_type"]
    if node["action"] != "add":
        return f"Changes to {WHAT[kind]} that's running"
    if kind == "adset":
        return "New ad set in a running campaign"
    if kind == "ad":
        return "New ad in a running ad set"
    parts = ["New campaign"]
    if new(node, "objective"):
        parts.append(_goal_words(new(node, "objective")))
    if new(node, "daily_budget"):
        parts.append(f"{_money(new(node, 'daily_budget'), currency)} a day")
    elif new(node, "lifetime_budget"):
        parts.append(f"{_money(new(node, 'lifetime_budget'), currency)} in total")
    if new(node, "bid_strategy") in BIDS:
        parts.append(BIDS[new(node, "bid_strategy")])
    return " · ".join(parts)


def holds_words(node):
    """"1 ad set · Riverside, CA + 25 mi, ages 25–65 · 0 ads"; a staged edit names the settings it changes."""
    kind = node["object_type"]
    if node["action"] != "add":
        return ", ".join(EDIT_LABELS.get(f, (f.replace("_", " ").capitalize(),))[0] for f in node.get("fields") or {}) or "No changes yet"
    if kind == "ad":
        p = _ad_parts(node)
        media = {"image": "a picture", "video": "a video"}.get(p["media"]["kind"], "no picture or video")
        return f"“{p['title']}” · {media}" if p["title"] else media.capitalize()
    if kind == "adset":
        return f"{_who(node)} · {_plural(len(node['ads']), 'ad')}"
    sets = node["adsets"]
    if not sets:
        return "No ad set yet"
    return f"{_plural(len(sets), 'ad set')} · {_who(sets[0])} · {_plural(len(_ads_of(node)), 'ad')}"


def all_problems(node):
    """Meta's problems with a draft and everything under it, in order."""
    out = list(node.get("problems") or [])
    for child in node.get("adsets", []) + node.get("ads", []):
        out += all_problems(child)
    return out


def last_edited(node):
    times = [t for t in [node.get("time_updated")] + [last_edited(c) for c in node.get("adsets", []) + node.get("ads", [])] if t]
    return max(times) if times else None


def manager_url(ad_account, object_type, object_id):
    """Ads Manager with this draft picked, built from digits only (never a link Meta's answer carried)."""
    act, oid = _digits(ad_account), _digits(object_id)
    if not act or not oid or object_type not in EDGES:
        return None
    edge, param = EDGES[object_type]
    return f"https://adsmanager.facebook.com/adsmanager/manage/{edge}?act={act}&{param}={oid}"
