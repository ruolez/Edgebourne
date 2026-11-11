"""New campaign wizard (roadmap 4.3), pure parts: check what was filled in, the campaign
request, the build order, and a plain review. Order follows the meta-ads skill (references/15
§18.2): campaign → ad set → creatives → ads, all PAUSED; publishing later turns on the ads,
then the ad set, then the campaign, so nothing can spend before every piece is on."""
import re
from datetime import datetime, timedelta

import account_info
import adset_build as ab

MIN_DAILY_CENTS = 100
MAX_ADS = 6
DAYS_PER_MONTH = 30.4
CTA_FOR_FORMS = ("SIGN_UP", "BOOK_TRAVEL", "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SUBSCRIBE", "DOWNLOAD")


def dollars(cents, currency=None):
    """An amount in the account's currency (`currency` given: pure)."""
    return account_info.money(cents, currency)


def campaign_payload(spec):
    return {"name": spec["name"].strip(), "objective": "OUTCOME_LEADS", "buying_type": "AUCTION",
            "special_ad_categories": [], "daily_budget": int(spec["daily_budget_cents"]),
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "status": "PAUSED"}


def problems(spec, known_forms, known_templates, current_daily_cents=None, currency="USD"):
    """[(step, message)] for anything that stops the build. `step` names the wizard step."""
    out = []
    if not (spec.get("name") or "").strip():
        out.append(("goal", "Give the campaign a name"))
    budget = spec.get("daily_budget_cents")
    if not budget or budget < MIN_DAILY_CENTS:
        out.append(("budget", "Give it a daily budget of at least $1"))
    elif current_daily_cents and budget > 3 * current_daily_cents:
        out.append(("budget", f"{dollars(budget, currency)} a day is more than 3 times what runs now ({dollars(current_daily_cents, currency)}); start lower and raise it in steps"))
    adset = spec.get("adset") or {}
    out += [("adset", m) for _, m in ab.problems(adset, budget)]
    if spec.get("form_id") not in known_forms:
        out.append(("form", "Pick the lead form people fill in"))
    ads = spec.get("ads") or []
    if not ads:
        out.append(("ads", "Add at least one ad"))
    if len(ads) > MAX_ADS:
        out.append(("ads", f"Start with at most {MAX_ADS} ads"))
    names = [a.get("name", "").strip().lower() for a in ads]
    for i, a in enumerate(ads, 1):
        # From scratch (no ad to start from) the ad needs its own image or video; "same" means the template's.
        if a.get("template_ad_id") and a["template_ad_id"] not in known_templates:
            out.append(("ads", f"Ad {i}: pick the ad it starts from"))
        if not a.get("template_ad_id") and (a.get("media") or {}).get("kind") == "same":
            out.append(("ads", f"Ad {i}: choose its image or video (it doesn't start from another ad)"))
        if not (a.get("name") or "").strip() or not (a.get("title") or "").strip() or not (a.get("body") or "").strip():
            out.append(("ads", f"Ad {i}: give it a name, primary text and a headline"))
        if a.get("cta_type") and a["cta_type"] not in CTA_FOR_FORMS:
            out.append(("ads", f"Ad {i}: that button doesn't open a lead form"))
        media = a.get("media") or {}
        if media.get("kind") not in ("same", "image", "video") or (media.get("kind") != "same" and not (media.get("hash") or media.get("video_id"))):
            out.append(("ads", f"Ad {i}: choose its image or video"))
    if len(set(n for n in names if n)) != len([n for n in names if n]):
        out.append(("ads", "Two ads have the same name"))
    return out


PERSONAL = re.compile(r"\b(are you|you're|you are)\b[^.?!]{0,40}\b(struggling|in debt|broke|sick|depressed|overweight|divorced|single|gay|christian|muslim|jewish|over \d\d|under \d\d)\b", re.I)


def copy_warnings(ad):
    """Advice, not blockers: Meta's personal-attributes rule and where text gets cut off."""
    out = []
    text = f"{ad.get('title', '')} {ad.get('body', '')}"
    if PERSONAL.search(text):
        out.append("It may assert a personal attribute (\"Are you struggling…\"); Meta rejects that. Say what the offer does instead.")
    first = (ad.get("body") or "").split("\n")[0]
    if len(first) > 125:
        out.append("The first line runs past 125 characters, where Meta cuts it off with \"See more\".")
    if len(ad.get("title") or "") > 40:
        out.append("Headlines read best under 40 characters.")
    return out


def review(spec, form_name, template_names, currency="USD"):
    """The plain summary shown before creating and in the confirmation."""
    b = spec["daily_budget_cents"]
    s = spec["adset"]
    places = [ab.location_label(l) for l in s["locations"]]
    return {
        "campaign": f"{spec['name']} · Leads (Instant Form) · {dollars(b, currency)} a day (about {dollars(round(b * DAYS_PER_MONTH), currency)} a month), lowest cost",
        "adset": f"{s['name']} · {', '.join(places[:4])}{f' +{len(places) - 4}' if len(places) > 4 else ''} · ages {s['age_min']}–{s['age_max']}"
                 + (" · Advantage+ audience" if s.get("advantage") else "") + " · Advantage+ placements",
        "form": form_name,
        "ads": [{"name": a["name"], "title": a["title"], "starts_from": template_names.get(a["template_ad_id"], ""),
                 "media": {"same": "same media as that ad", "image": "a new image", "video": "a new video"}[a["media"]["kind"]],
                 "warnings": copy_warnings(a)} for a in spec["ads"]],
        "budget_cents": b,
    }


def next_steps(made, n_ads):
    """What's left to create, in order, given what an earlier attempt already made."""
    out = []
    if not made.get("campaign_id"):
        out.append("campaign")
    if not made.get("adset_id"):
        out.append("adset")
    out += [f"ad:{i}" for i in range(n_ads) if not (made.get("ads") or {}).get(str(i))]
    return out


def publish_order(made):
    """Ads first, then the ad set, then the campaign: nothing delivers until the last switch."""
    return [("ad", a) for _, a in sorted((made.get("ads") or {}).items(), key=lambda kv: int(kv[0]))] + \
           [("adset", made["adset_id"]), ("campaign", made["campaign_id"])]


def adoptable(found, name, parent, since, taken):
    """After Meta didn't answer a create, the object the earlier try may have made: same exact name,
    still paused, under the same parent, created since the build started (a minute of clock slack) and
    not already used by another build. The newest such one, or None (audit A3-71, A3-72)."""

    def created(x):
        try:
            return datetime.strptime(x.get("created_time") or "", "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None
    floor = since - timedelta(minutes=1)
    ok = [(created(x), x["id"]) for x in found
          if x.get("name") == name and x.get("status") == "PAUSED" and x["id"] not in taken
          and (parent is None or parent in (x.get("campaign_id"), x.get("adset_id"))) and created(x) and created(x) >= floor]
    return max(ok)[1] if ok else None
