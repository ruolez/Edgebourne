"""AM-D: the account's audiences (custom, lookalike, saved). Pure: no database, no Meta.

`clean` + `problems` say what a New audience form may send and what is refused before anything reaches Meta, `create_params`
builds the act_<id>/customaudiences body (shapes marked (verify) are pinned in the fake until a live check), `from_meta` /
`saved_from_meta` keep only listed fields of Meta's read (its text is untrusted: cut, never HTML), `describe` / `readiness` /
`size_words` / `used_words` are the plain words, `where_used` the ad sets using one, `targeting_with` puts picked audiences in
an ad set's targeting, `pick_problems` / `picker_refusal` what a picker refuses. No customer list is ever made here."""
import copy
import json

import edit_rules

KINDS = ("website", "page", "instagram", "lead_form", "video", "lookalike")
RETENTION_MAX = {"website": 180, "page": 365, "instagram": 365, "lead_form": 90, "video": 365}  # days (verify)
LOOKALIKE_RATIOS = (0.01, 0.02, 0.03, 0.05, 0.10)          # 1 % … 10 %
MIN_SOURCE = 100                                            # people in one country (Meta's rule for a lookalike source)
TOO_SMALL = 1000                                            # under this Meta calls an audience too small to deliver well
MAX_PICKED = 20
WEBSITE_WHO = ("all_visitors", "visited_url", "lead_event")
PAGE_WHO = ("page_engaged", "page_visited", "page_messaged", "page_cta_clicked")                  # (verify event names)
IG_WHO = ("ig_business_profile_all", "ig_business_profile_visit", "ig_user_messaged_business")    # (verify)
FORM_WHO = ("lead_generation_opened", "lead_generation_submitted", "lead_generation_dropoff")     # (verify)
VIDEO_WHO = ("video_watched", "video_completed", "video_view_25_percent", "video_view_50_percent", "video_view_75_percent")  # (verify)
WHO = {"website": WEBSITE_WHO, "page": PAGE_WHO, "instagram": IG_WHO, "lead_form": FORM_WHO, "video": VIDEO_WHO}
SOURCE_TYPE = {"website": "pixel", "page": "page", "instagram": "ig_business", "lead_form": "lead", "video": "video"}  # (verify)
SOURCE_KIND = {v: k for k, v in SOURCE_TYPE.items()}
KIND_WORDS = {"website": "Website", "page": "Engagement", "instagram": "Engagement", "lead_form": "Engagement", "video": "Engagement",
              "lookalike": "Lookalike", "customer_list": "Customer list", "saved": "Saved", "other": "Custom"}

VERB = {
    "all_visitors": "visited your website", "lead_event": "sent a lead on your website",
    "page_engaged": "engaged with your Facebook Page", "page_visited": "visited your Facebook Page",
    "page_messaged": "messaged your Facebook Page", "page_cta_clicked": "clicked a button on your Facebook Page",
    "ig_business_profile_all": "engaged with your Instagram account", "ig_business_profile_visit": "visited your Instagram profile",
    "ig_user_messaged_business": "messaged your Instagram account",
    "lead_generation_opened": "opened your lead form{n}", "lead_generation_submitted": "sent your lead form{n}",
    "lead_generation_dropoff": "opened your lead form{n} and didn't send it",
    "video_watched": "watched your video{n}", "video_completed": "watched all of your video{n}",
    "video_view_25_percent": "watched at least a quarter of your video{n}", "video_view_50_percent": "watched at least half of your video{n}",
    "video_view_75_percent": "watched at least three quarters of your video{n}",
}
CHOICES = {  # the New audience form's words for each `who`
    "all_visitors": "Everyone who visited", "visited_url": "Visited a page whose address contains…", "lead_event": "Sent a lead on the website",
    "page_engaged": "Anyone who engaged", "page_visited": "Visited the Page", "page_messaged": "Sent a message", "page_cta_clicked": "Clicked a button",
    "ig_business_profile_all": "Anyone who engaged", "ig_business_profile_visit": "Visited the profile", "ig_user_messaged_business": "Sent a message",
    "lead_generation_opened": "Opened the form", "lead_generation_submitted": "Sent the form", "lead_generation_dropoff": "Opened it but didn't send it",
    "video_watched": "Watched any of it", "video_view_25_percent": "Watched at least a quarter", "video_view_50_percent": "Watched at least half",
    "video_view_75_percent": "Watched at least three quarters", "video_completed": "Watched all of it",
}
LOOKALIKE_SPECIAL = ("Meta doesn't allow lookalike audiences in a campaign with a special ad category (housing, jobs, credit or "
                     "social issues).")
ADVANTAGE_NOTE = "With Advantage+ audience, Meta treats these as suggestions; people you leave out stay out."  # (verify)


def _digits(v):
    s = str(v if v is not None else "").strip()
    return s if s.isdigit() and len(s) <= 30 else ""


def _int(v):
    try:
        return int(v) if v not in (None, "") and not isinstance(v, bool) else None
    except (TypeError, ValueError):
        return None


def _text(v, n):
    s = " ".join(str(v if v is not None else "").split())
    return s[:n] or None


def clean_ids(raw, cap=True):
    """Picked audience ids: digits only, each once, in order (more than MAX_PICKED are kept so the check can say so; cap=False keeps
    every one, for Meta's own list on an ad set)."""
    out = []
    for x in raw if isinstance(raw, list) else []:
        i = _digits(x.get("id") if isinstance(x, dict) else x) if not isinstance(x, (bool, float)) else ""
        if i and i not in out:
            out.append(i)
    return out[:MAX_PICKED + 5] if cap else out


def clean(kind, raw):
    """What a New audience form sent, typed and cut. Unknown keys are dropped."""
    raw = raw if isinstance(raw, dict) else {}
    try:
        ratio = round(float(raw.get("ratio")), 4) if raw.get("ratio") not in (None, "") else None
    except (TypeError, ValueError):
        ratio = None
    return {"name": str(raw.get("name") or "").strip()[:200], "days": _int(raw.get("days")), "who": str(raw.get("who") or "")[:40],
            "source_id": _digits(raw.get("source_id")), "url": str(raw.get("url") or "").strip()[:300],
            "origin_id": _digits(raw.get("origin_id")), "country": str(raw.get("country") or "").strip().upper()[:2], "ratio": ratio}


# ---------------------------------------------------------------- what is refused

def _source_problem(kind, spec, known):
    sid = spec.get("source_id")
    if kind == "website":
        if not known.get("pixel"):
            return "This account has no Pixel set in Settings → Meta, so there's no website to build from."
        return None if sid == str(known["pixel"]) else "Use this account's Pixel (Settings → Meta)."
    if kind == "page":
        if not known.get("page"):
            return "This account has no Facebook Page set in Settings → Meta."
        return None if sid == str(known["page"]) else "Use this account's Facebook Page."
    if kind == "instagram":
        if not known.get("instagram"):
            return "This account's Facebook Page has no Instagram account connected (connect one in Meta Business Settings)."
        return None if sid == str(known["instagram"]) else "Use this account's Instagram account."
    if kind == "lead_form":
        return None if sid and sid in (known.get("forms") or {}) else "Pick one of this account's lead forms."
    if kind == "video":
        return None if sid and sid in (known.get("videos") or {}) else "Pick one of this account's videos."
    return None


def _url_problem(url):
    if not 3 <= len(url) <= 200 or any(c.isspace() for c in url):
        return "Type 3 to 200 characters of the page's address, without spaces (for example “pricing”)."
    if "://" in url and not url.lower().startswith(("http://", "https://")):
        return "Use a web address (http or https)."
    return None


def problems(kind, spec, known):
    """[(field, message)]: everything refused before Meta is asked. `known`: this account's pixel, page, instagram, forms {id: name},
    videos {id: title}, audiences {id: row} (not gone) and the countries its ads reach."""
    if kind not in KINDS:
        return [("kind", "Pick what kind of audience to make.")]
    out = []
    if not (spec.get("name") or "").strip():
        out.append(("name", "Give the audience a name."))
    if kind == "lookalike":
        src = (known.get("audiences") or {}).get(spec.get("origin_id") or "")
        if not src or src.get("kind") not in ("custom",):
            out.append(("origin", "Pick one of this account's website, engagement or customer list audiences (a lookalike can't start from "
                                  "another lookalike)." if not src or src.get("kind") == "lookalike" else "Pick one of this account's audiences."))
        elif src.get("ready") == "problem":
            out.append(("origin", f"Meta reports a problem with “{src.get('name')}”: {src.get('status_words') or 'it can’t be used'}."))
        elif src.get("ready") == "filling" or src.get("size_lower") in (None,) or (src.get("size_lower") or 0) < 0:
            out.append(("origin", f"“{src.get('name')}” is still filling: Meta needs a few hours before a lookalike can be made from it."))
        elif src["size_lower"] < MIN_SOURCE:
            out.append(("origin", f"A lookalike needs a source of at least {MIN_SOURCE} people in one country (Meta's rule); "
                                  f"“{src.get('name')}” has about {src['size_lower']:,}."))
        if spec.get("country") not in (known.get("countries") or []):
            out.append(("country", "Pick a country this account's ads reach."))
        if spec.get("ratio") not in LOOKALIKE_RATIOS:
            out.append(("ratio", "Pick how close: 1 % (most like them) to 10 % (broader)."))
        return out
    top = RETENTION_MAX[kind]
    if spec.get("days") is None or not 1 <= spec["days"] <= top:
        out.append(("days", f"Pick 1 to {top} days back for this kind of audience."))
    if spec.get("who") not in WHO[kind]:
        out.append(("who", "Pick who it includes."))
    why = _source_problem(kind, spec, known)
    if why:
        out.append(("source", why))
    if kind == "website" and spec.get("who") == "visited_url":
        why = _url_problem(spec.get("url") or "")
        if why:
            out.append(("url", why))
    return out


# ---------------------------------------------------------------- Meta's create body

def _rule(kind, spec):
    if kind == "website":
        filt = ({"field": "url", "operator": "i_contains", "value": spec["url"]} if spec["who"] == "visited_url" else
                {"field": "event", "operator": "eq", "value": "Lead"} if spec["who"] == "lead_event" else
                {"field": "url", "operator": "i_contains", "value": ""})
    else:
        filt = {"field": "event", "operator": "eq", "value": spec["who"]}
    return {"inclusions": {"operator": "or", "rules": [{"event_sources": [{"id": spec["source_id"], "type": SOURCE_TYPE[kind]}],
                                                         "retention_seconds": int(spec["days"]) * 86400,
                                                         "filter": {"operator": "and", "filters": [filt]}}]}}


def create_params(kind, spec, description=None):
    """POST act_<id>/customaudiences (Custom Audiences reference) (verify): objects as Python values; the route JSON-encodes them."""
    out = {"name": spec["name"].strip()}
    if description:
        out["description"] = description[:300]
    if kind == "lookalike":
        return {**out, "subtype": "LOOKALIKE", "origin_audience_id": spec["origin_id"],
                "lookalike_spec": {"type": "similarity", "country": spec["country"], "ratio": spec["ratio"]}}
    if kind == "website":
        return {**out, "subtype": "WEBSITE", "retention_days": int(spec["days"]), "prefill": True, "rule": _rule(kind, spec)}
    return {**out, "subtype": "ENGAGEMENT", "prefill": True, "rule": _rule(kind, spec)}


def row_from_spec(kind, spec):
    """The stored row's parts for an audience the console makes (before Meta reports its size)."""
    if kind == "lookalike":
        return {"kind": "lookalike", "subtype": "LOOKALIKE", "source_kind": "lookalike", "who": None, "detail": None,
                "source_id": spec["origin_id"], "retention_days": None, "lookalike": {"country": spec["country"], "ratio": spec["ratio"]}}
    return {"kind": "custom", "subtype": "WEBSITE" if kind == "website" else "ENGAGEMENT", "source_kind": kind, "who": spec["who"],
            "detail": spec["url"][:200] if spec["who"] == "visited_url" else None, "source_id": spec["source_id"],
            "retention_days": int(spec["days"]), "lookalike": None}


def adopt_match(kind, spec, raw):
    """True when an audience Meta lists is the one this form asked for (same name, type and source; for a lookalike the same origin,
    country and ratio when Meta says them), so an unanswered create may adopt it instead of making a second one."""
    got = from_meta(raw)
    if not got or str((raw or {}).get("name") or "") != spec["name"].strip():
        return False
    want = row_from_spec(kind, spec)
    if got["subtype"] != want["subtype"] or (got["source_id"] and got["source_id"] != want["source_id"]):
        return False
    if kind == "lookalike":
        if not got["source_id"]:
            return False
        la = got["lookalike"] or {}
        return (not la.get("country") or la["country"] == want["lookalike"]["country"]) and \
            (la.get("ratio") is None or abs(la["ratio"] - float(want["lookalike"]["ratio"])) < 1e-6)
    return not got["source_kind"] or got["source_kind"] in (kind, "other")


# ---------------------------------------------------------------- reading Meta

def readiness(lower, upper, delivery, operation):
    """(ready, words): 'ready' | 'filling' (Meta reports no size yet) | 'too_small' | 'problem' (Meta's status says so)."""
    for st in (delivery, operation):
        code = _int((st or {}).get("code")) if isinstance(st, dict) else None
        if code is not None and code >= 400:
            return "problem", _text((st or {}).get("description"), 200) or "Meta reports a problem with this audience"
    lo, hi = _int(lower), _int(upper)
    if lo is None or hi is None or lo < 0 or hi <= 0:
        return "filling", "Still filling (Meta needs a few hours)"
    if hi < TOO_SMALL:
        return "too_small", "Too small to use yet (under 1,000)"
    return "ready", "Ready"


def _parse_rule(raw_rule):
    try:
        r = json.loads(raw_rule) if isinstance(raw_rule, str) else raw_rule
        first = ((r or {}).get("inclusions") or {}).get("rules") or []
        first = first[0] if first and isinstance(first[0], dict) else {}
    except (TypeError, ValueError):
        return {}
    src = (first.get("event_sources") or [{}])[0] if isinstance(first.get("event_sources"), list) else {}
    filters = ((first.get("filter") or {}).get("filters") or []) if isinstance(first.get("filter"), dict) else []
    out = {"source_kind": SOURCE_KIND.get(str((src or {}).get("type") or "")), "source_id": _digits((src or {}).get("id")),
           "days": (_int(first.get("retention_seconds")) or 0) // 86400 or None}
    for f in filters if isinstance(filters, list) else []:
        if not isinstance(f, dict):
            continue
        if f.get("field") == "event":
            out["who"] = "lead_event" if out["source_kind"] == "website" and f.get("value") == "Lead" else str(f.get("value") or "")[:40]
        elif f.get("field") == "url" and out["source_kind"] == "website":
            value = str(f.get("value") or "")
            out["who"], out["detail"] = ("visited_url", value[:200]) if value else ("all_visitors", None)
    return out


def from_meta(raw):
    """One act_<id>/customaudiences row as stored (listed fields only, text cut); None for a row without a numeric id."""
    aid = _digits((raw or {}).get("id"))
    if not aid:
        return None
    subtype = str(raw.get("subtype") or "").upper()[:30] or None
    ready, words = readiness(raw.get("approximate_count_lower_bound"), raw.get("approximate_count_upper_bound"),
                             raw.get("delivery_status"), raw.get("operation_status"))
    out = {"id": aid, "kind": "lookalike" if subtype == "LOOKALIKE" else "custom", "subtype": subtype, "name": _text(raw.get("name"), 200) or aid,
           "description": _text(raw.get("description"), 300), "size_lower": _int(raw.get("approximate_count_lower_bound")),
           "size_upper": _int(raw.get("approximate_count_upper_bound")), "ready": ready, "status_words": words,
           "retention_days": _int(raw.get("retention_days")), "source_kind": None, "who": None, "detail": None, "source_id": None,
           "lookalike": None, "targeting": None, "time_created": _int(raw.get("time_created")) if str(raw.get("time_created") or "").isdigit() else raw.get("time_created")}
    if out["size_lower"] is not None and out["size_lower"] < 0:
        out["size_lower"] = out["size_upper"] = None
    if subtype == "LOOKALIKE":
        spec = raw.get("lookalike_spec")
        try:
            spec = json.loads(spec) if isinstance(spec, str) else spec or {}
        except ValueError:
            spec = {}
        origin = (spec.get("origin") or [{}])[0] if isinstance(spec.get("origin"), list) and spec.get("origin") else {}
        try:
            ratio = round(float(spec.get("ratio")), 4) if spec.get("ratio") is not None else None
        except (TypeError, ValueError):
            ratio = None
        out.update(source_kind="lookalike", source_id=_digits((origin or {}).get("id")) or None,
                   lookalike={"country": str(spec.get("country") or "")[:2].upper() or None, "ratio": ratio})
    elif subtype == "CUSTOM":
        out["source_kind"] = "customer_list"
    else:
        rule = _parse_rule(raw.get("rule"))
        out.update(source_kind=rule.get("source_kind") or ("website" if subtype == "WEBSITE" else "other"),
                   who=rule.get("who"), detail=rule.get("detail"), source_id=rule.get("source_id") or None)
        out["retention_days"] = out["retention_days"] or rule.get("days")
    return out


def saved_from_meta(raw):
    """One act_<id>/saved_audiences row: its targeting kept only for the keys a person sets (edit_rules.TARGETING_KEYS)."""
    aid = _digits((raw or {}).get("id"))
    if not aid:
        return None
    t = raw.get("targeting")
    try:
        t = json.loads(t) if isinstance(t, str) else t
    except ValueError:
        t = None
    return {"id": aid, "kind": "saved", "subtype": None, "name": _text(raw.get("name"), 200) or aid, "description": _text(raw.get("description"), 300),
            "size_lower": None, "size_upper": None, "ready": "ready", "status_words": "Ready", "retention_days": None, "source_kind": "saved",
            "who": None, "detail": None, "source_id": None, "lookalike": None, "targeting": edit_rules.kept_targeting(t),
            "time_created": raw.get("time_created")}


# ---------------------------------------------------------------- plain words

def _days(row):
    d = row.get("retention_days")
    return f" in the last {d} days" if d else ""


def _pct(ratio):
    try:
        p = float(ratio) * 100
    except (TypeError, ValueError):
        return None
    return f"{int(round(p))}" if abs(p - round(p)) < 1e-6 else f"{p:.1f}"


def describe(row, names=None):
    """What an audience is, in one plain sentence. A console-made one keeps the words written when it was made."""
    names = names or {}
    if row.get("made_here") and row.get("description"):
        return row["description"]
    kind, sk, who = row.get("kind"), row.get("source_kind"), row.get("who")
    if kind == "saved":
        form = edit_rules.audience_form(row.get("targeting") or {})
        return "Saved targeting: " + edit_rules.audience_words(form)
    if kind == "lookalike" or sk == "lookalike":
        spec = row.get("lookalike") or {}
        src = names.get(row.get("source_id") or "")
        parts = [x for x in (f"{_pct(spec.get('ratio'))} %" if spec.get("ratio") is not None else None, spec.get("country")) if x]
        return f"People like {f'“{src}”' if src else 'another audience'}" + (f" ({', '.join(parts)})" if parts else "")
    if sk == "customer_list":
        return "A customer list uploaded to Meta"
    if sk == "website" and who == "visited_url":
        return f"People who visited a page whose address contains “{row.get('detail') or ''}”{_days(row)}"
    if who in VERB:
        n = names.get(row.get("source_id") or "")
        return "People who " + VERB[who].format(n=f" “{n}”" if n else "") + _days(row)
    if sk == "website":
        return "People who visited your website" + _days(row)
    return row.get("description") or "A custom audience made in Ads Manager"


META_PEOPLE = {"US": 200_000_000, "CA": 30_000_000, "GB": 50_000_000, "AU": 20_000_000, "MX": 90_000_000}  # rough reach, for words only


def lookalike_size_words(country, ratio):
    pct = _pct(ratio)
    if not country or pct is None:
        return None
    head = f"Meta picks the {pct} % of people in {'the US' if country == 'US' else country} most like your source"
    people = META_PEOPLE.get(country)
    if not people:
        return head + "."
    n = people * float(ratio)
    return head + f": roughly {n / 1e6:,.0f} million people." if n >= 1e6 else head + f": roughly {n:,.0f} people."


def size_words(row):
    if row.get("ready") == "filling" or row.get("size_lower") is None or row.get("size_upper") is None:
        return "Still filling"
    return f"{row['size_lower']:,}–{row['size_upper']:,} people"  # too small: the pill says so, the size shows how small


def kind_words(row):
    return KIND_WORDS.get("saved" if row.get("kind") == "saved" else "lookalike" if row.get("kind") == "lookalike" else row.get("source_kind") or "other", "Custom")


# ---------------------------------------------------------------- where it is used

def where_used(audience_id, adsets):
    """{include: [...], exclude: [...]} of the ad sets naming this audience (deleted ad sets left out)."""
    out = {"include": [], "exclude": []}
    for a in adsets or []:
        if (a.get("effective_status") or a.get("status")) == "DELETED":
            continue
        item = {"id": a.get("id"), "name": a.get("name"), "status": a.get("effective_status") or a.get("status"), "campaign_id": a.get("campaign_id")}
        if audience_id in (a.get("audience_ids") or []):
            out["include"].append(item)
        if audience_id in (a.get("excluded_audience_ids") or []):
            out["exclude"].append(item)
    return out


def used_words(used):
    n, m = len(used.get("include") or []), len(used.get("exclude") or [])
    parts = ([f"In {n} ad set{'' if n == 1 else 's'}"] if n else []) + ([f"left out of {m}" if n else f"Left out of {m} ad set{'' if m == 1 else 's'}"] if m else [])
    return " · ".join(parts) or "Not used yet"


def ids_in(targeting, key):
    return [_digits(a.get("id")) for a in (targeting or {}).get(key) or [] if isinstance(a, dict) and _digits(a.get("id"))]


# ---------------------------------------------------------------- pickers

def targeting_with(targeting, include_ids, exclude_ids):
    """Meta's targeting with these audiences included / left out; every other key kept as it is."""
    t = copy.deepcopy(targeting or {})
    for key, ids in (("custom_audiences", include_ids), ("excluded_custom_audiences", exclude_ids)):
        if ids:
            t[key] = [{"id": str(i)} for i in ids]
        else:
            t.pop(key, None)
    return t


def picker_refusal(campaign, audience):
    """Why this audience can't be picked for an ad set in this campaign, or None."""
    if audience.get("ready") == "problem":
        return f"Meta reports a problem with this audience: {audience.get('status_words') or 'it can’t be used'}."
    if audience.get("kind") == "lookalike" and ((campaign or {}).get("special_ad_categories") or []):
        return LOOKALIKE_SPECIAL
    return None


def pick_problems(include, exclude, known, special, keep=()):
    """[(field, message)] for audiences picked to include / leave out: at most MAX_PICKED each, only this account's (`known`, not gone;
    one already on the ad set may stay), never both ways, and what picker_refusal says."""
    out = []
    if len(include) > MAX_PICKED or len(exclude) > MAX_PICKED:
        out.append(("audiences", f"Pick at most {MAX_PICKED} audiences to include and {MAX_PICKED} to leave out."))
    unknown = [i for i in list(include) + list(exclude) if i not in known and i not in set(keep)]
    if unknown:
        out.append(("audiences", "That audience isn't in this account"))
    if set(include) & set(exclude):
        out.append(("audiences", "An audience can't be both included and left out."))
    camp = {"special_ad_categories": list(special or [])}
    for i in list(include) + list(exclude):
        a = known.get(i)
        why = a and picker_refusal(camp, a)
        if why:
            out.append(("audiences", f"“{a.get('name')}”: {why}"))
    return out
