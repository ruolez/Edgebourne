"""The Gallery (UX-AUDIT 9.5): every ad as people see it, with what it earned. Copies of one ad count
once: the same video with the same headline, text and button (on another creative or in another ad
set), or the same creative. Pictures merge only on the same creative, because the picture itself
(Meta's image hash) isn't stored. Nothing merges on a missing field. Pure: grouping, the days an ad's
current version earned, the views (Top, Just launched, Tired) and the filters."""
import hashlib
from datetime import timedelta

import concepts
import creative_versions as cv
import swipes
import words

LAUNCH_DAYS = 7
VIEWS = ("top", "launched", "tired")
STATUSES = ("delivering", "review", "problem", "off", "deleted")
REVIEW = ("IN_PROCESS", "PENDING_REVIEW", "PREAPPROVED")
PROBLEM = ("DISAPPROVED", "WITH_ISSUES", "PENDING_BILLING_INFO")
NUMBERS = ("spend_cents", "impressions", "link_clicks", "leads", "video_3s")


def bucket(status):
    """Meta's effective_status → the Gallery's status filter."""
    if status == "ACTIVE":
        return "delivering"
    if status in REVIEW:
        return "review"
    if status in PROBLEM:
        return "problem"
    if status == "DELETED":
        return "deleted"
    return "off"


def _words(value):
    return " ".join(str(value).split()).casefold() if value is not None else ""


def group_key(ad):
    """Which card an ad belongs to."""
    words = [_words(ad.get(k)) for k in ("title", "body", "cta_type")]
    if ad.get("video_id") and all(words):
        raw = "\x1f".join(["video", str(ad["video_id"]), *words])
        return "v" + hashlib.sha1(raw.encode()).hexdigest()[:16]
    if ad.get("creative_id"):
        return f"c{ad['creative_id']}"
    return f"a{ad['id']}"


def _now_versions(chain):
    """The versions showing what the ad shows now: the newest, and earlier ones with the same creative
    (a restore brings their days back)."""
    current = chain[-1].get("creative_id")
    return {i for i, v in enumerate(chain) if current and v.get("creative_id") == current} | {len(chain) - 1}


def counts_now(day, chain):
    """Whether a day's results belong to what the ad shows now. `chain`: its versions with `live_on`
    (creative_versions.with_live_days), oldest first; empty or one when it never changed. Days between
    a switch and Meta's approval count for no card."""
    if len(chain or ()) < 2:
        return True
    return cv.owner_index(day, chain) in _now_versions(chain)


def credited(days, chain):
    """An ad's numbers over `days` that belong to what it shows now (see counts_now)."""
    out = {"days": 0, **{m: 0 for m in cv.METRICS}}
    for row in days:
        if counts_now(row["day"], chain):
            out["days"] += 1
            for m in cv.METRICS:
                out[m] += int(row.get(m) or 0)
    return out


def launch_day(first_spend, created_on, chain=()):
    """When what the ad shows now started: the day Meta approved the first version with its current
    creative, else the first day it spent, else the day it was made."""
    if len(chain) > 1:
        v = chain[min(_now_versions(chain))]
        if v.get("started_on"):
            return v.get("live_on") or v["started_on"]
    return first_spend or created_on


def version_since(chain):
    """The day the ad last changed what it shows, when that leaves another version's days out of its
    numbers; else None."""
    if len(chain or ()) < 2 or len(_now_versions(chain)) == len(chain):
        return None
    return chain[-1].get("live_on") or chain[-1].get("started_on")


def _rank(status):
    return STATUSES.index(bucket(status))


def build(ads, totals, tags, tired, first_days, delivered, track_days, today, target_cents=None, since=None):
    """One card per group of copies. ads: rows with id, name, effective_status, video_id, creative_id,
    title, body, cta_type, image_url, thumbnail_url, created_on; totals: {ad id: credited numbers};
    tags: {ad id: {dimension: value}}; tired: ad ids with an open fatigue alert; first_days: {ad id: the
    day what it shows now started (launch_day)}; delivered: {ad id: days it spent} over `track_days`;
    since: {ad id: version_since}."""
    zero = {k: 0 for k in NUMBERS}
    since = since or {}
    groups = {}
    for ad in ads:
        groups.setdefault(group_key(ad), []).append(ad)
    out = []
    for key, members in groups.items():
        spend = lambda a: (totals.get(a["id"]) or zero)["spend_cents"]
        members = sorted(members, key=lambda a: (-spend(a), str(a["id"])))
        top = members[0]
        best = min(members, key=lambda a: (_rank(a.get("effective_status")), -spend(a), str(a["id"])))
        g = {k: sum((totals.get(a["id"]) or zero).get(k) or 0 for a in members) for k in NUMBERS}
        video = bool(top.get("video_id"))
        g["video_impressions"] = g["impressions"] if video else 0
        launched = [d for d in (first_days.get(a["id"]) or a.get("created_on") for a in members) if d]
        launched_on = min(launched) if launched else None
        status_bucket = bucket(best.get("effective_status"))
        buckets = sorted({bucket(a.get("effective_status")) for a in members}, key=STATUSES.index)
        changed = max(((since[a["id"]], a["id"]) for a in members if since.get(a["id"])), key=lambda t: (t[0], str(t[1])), default=None)
        all_tags = sorted({(d, v) for a in members for d, v in (tags.get(a["id"]) or {}).items()})
        out.append({
            "key": key, "name": top["name"], "kind": "video" if video else "image", "top_ad_id": top["id"],
            "title": top.get("title"),
            "image_url": next((a.get("image_url") or a.get("thumbnail_url") for a in members if a.get("image_url") or a.get("thumbnail_url")), None),
            "ads": [{"id": a["id"], "name": a["name"], "effective_status": a.get("effective_status"), "campaign_id": a.get("campaign_id")} for a in members],
            "effective_status": best.get("effective_status"), "bucket": status_bucket, "buckets": buckets,
            "problems": sum(1 for a in members if bucket(a.get("effective_status")) == "problem") if status_bucket != "problem" else 0,
            "in_review": sum(1 for a in members if bucket(a.get("effective_status")) == "review") if status_bucket != "review" else 0,
            "version_since": changed[0].isoformat() if changed else None, "version_ad": changed[1] if changed else None,
            **g,
            "cpl_cents": round(g["spend_cents"] / g["leads"]) if g["leads"] else None,
            "hook_rate": g["video_3s"] / g["video_impressions"] if g["video_impressions"] else None,
            "tired": any(a["id"] in tired for a in members),
            "launched_on": launched_on.isoformat() if launched_on else None,
            "just_launched": bool(launched_on and launched_on >= today - timedelta(days=LAUNCH_DAYS)),
            "tags": dict(tags.get(top["id"]) or {}), "tags_all": [list(t) for t in all_tags],
            "track": [{"day": d.isoformat(), "on": any(d in (delivered.get(a["id"]) or ()) for a in members)} for d in track_days],
        })
    leads = sum(x["leads"] for x in out)
    target = target_cents or (round(sum(x["spend_cents"] for x in out) / leads) if leads else None)
    for x in out:
        x["enough"] = x["leads"] >= concepts.MIN_LEADS and (not target or x["spend_cents"] >= concepts.SPEND_TIMES * target)
    return out


def pick(groups, view="top", status="", tag=None):
    """The cards one view shows, in its order, and how many each view holds under the same filters.
    No status: everything but deleted cards. Rejected and In review match a card when any copy is (the
    card says how many); Delivering, Off and Deleted go by the card's own status. `tag`: (dimension,
    value), matched on any copy."""
    status = status if status in STATUSES else ""
    view = view if view in VIEWS else "top"
    want = list(tag) if tag else None
    def shows(g):
        if status in ("problem", "review"):
            return status in g["buckets"] and g["bucket"] != "deleted"
        return g["bucket"] == status if status else g["bucket"] != "deleted"

    base = [g for g in groups if shows(g) and (not want or want in g["tags_all"])]
    counts = {"top": len(base), "launched": sum(1 for g in base if g["just_launched"]), "tired": sum(1 for g in base if g["tired"])}
    if view == "launched":
        shown = sorted((g for g in base if g["just_launched"]), key=lambda g: (g["launched_on"], g["spend_cents"]), reverse=True)
    elif view == "tired":
        shown = sorted((g for g in base if g["tired"]), key=lambda g: -g["spend_cents"])
    else:
        shown = sorted(base, key=lambda g: (not g["enough"], g["cpl_cents"] if g["enough"] else 0, -g["spend_cents"]))
    return {"view": view, "status": status, "groups": shown, "counts": counts}


STATUS_WORDS = {"delivering": "Delivering", "review": "In review", "problem": "Rejected or has a problem", "off": "Off", "deleted": "Deleted"}
BRIEF_FRAMES = {
    "one": ("Make more ads for {business} like this one of ours from the Gallery. Keep what seems to make it work (the hook, the angle, "
            "the format) and write 3 genuinely different new ads for the same offer, in fresh words: not copies of it."),
    "many": ("Make more ads for {business} like these {n} of ours from the Gallery. Say what they have in common and what seems to make "
             "them work (cost per lead counts only where there's enough to judge), then write 3 genuinely different new ads that keep it, "
             "in fresh words: not copies of them."),
}
BRIEF_OUTRO = "Send them back as new ad suggestions."


def _results(card, currency):
    if not card.get("spend_cents"):
        return "Results: nothing spent on these days"
    spent = f"spent {words.money(card['spend_cents'], currency)}, {card['leads']} lead{'' if card['leads'] == 1 else 's'}"
    if not card.get("enough") or not card.get("cpl_cents"):
        return f"Results: {spent} (too early to judge)"
    return f"Results: {spent}, {words.money(card['cpl_cents'], currency)} per lead"


def _brief_lines(card, body_room, share, currency, numbers):
    """One card as lines: what it is, its words, what it earned on the complete days, its ideas, its ad id."""
    head = [swipes.fit(card.get("name"), 200), f"{card.get('kind') or 'image'} ad", STATUS_WORDS.get(card.get("bucket"), "Off")]
    if len(card.get("ads") or ()) > 1:
        head.append(f"runs as {len(card['ads'])} ads")
    if card.get("tired"):
        head.append("looks tired")
    cta = str(card.get("cta_type") or "").replace("_", " ").strip().capitalize()
    order = list(concepts.DIMENSIONS)
    tags = sorted((t for t in card.get("tags_all") or () if t[0] in concepts.DIMENSIONS and str(t[1] or "").strip()), key=lambda t: (order.index(t[0]), t[1]))
    ideas = swipes.fit(" · ".join(f"{concepts.DIMENSIONS[d][0]}: {swipes.fit(v, 80)}" for d, v in tags), max(40, min(300, share // 4)))
    hook = card.get("hook_rate") if card.get("kind") == "video" and card.get("spend_cents") else None
    return [" · ".join(head),
            *([f"Headline: {swipes.fit(card['title'], max(40, min(150, share // 5)))}"] if str(card.get("title") or "").strip() else []),
            *([f"Text: {swipes.fit(card['body'], body_room)}"] if str(card.get("body") or "").strip() else []),
            *([f"Button: {cta}"] if cta else []),
            *([_results(card, currency)] if numbers else []),
            *([f"Hook rate: {hook * 100:.1f}% watched 3 seconds"] if numbers and hook is not None else []),
            *([f"Ideas: {ideas}"] if ideas else []),
            f"Ad id: {card.get('top_ad_id')}"]


def brief(cards, business, period, currency="USD"):
    """The request "Make more like these" drafts from Gallery cards picked (in that order), for Claude to edit
    and send: each card's words, what it earned over `period` ((first, last) complete days, or None when the
    dates picked have none yet: no numbers then) and its ideas, trimmed under swipes.DRAFT_MAX like a swipe
    brief. cards: gallery.build cards plus their top ad's `body` and `cta_type`. Returns {prompt, left_out}."""
    who = " ".join(str(business or "").split()) or "us"
    when = (f"The numbers are for {words.day(period[0])}{'' if period[0] == period[1] else f' – {words.day(period[1])}'}, complete days only."
            if period else "There are no complete days in the dates picked yet, so no numbers.")

    def frame(n):
        return f"{BRIEF_FRAMES['one' if n == 1 else 'many'].format(business=who, n=n)} {when}", BRIEF_OUTRO, n > 1
    return swipes.pack(cards, frame, lambda c, room, share: _brief_lines(c, room, share, currency, bool(period)))
