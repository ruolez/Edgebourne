"""Swipe file + competitor watch (roadmap 5.2), pure parts: read an Ad Library link, how long
an ad has run (a long run is the best public sign it works), and cleaning what Claude or a
person saves. Meta's Ad Library API only covers political and EU-delivered ads, so US
competitor searches run on the Mac through the Ads MCP `ads_library_search`."""
import re
from datetime import date

LONG_RUNNING_DAYS = 30
LIMITS = {"page_name": 200, "body": 4000, "title": 300, "notes": 2000, "media_url": 1000, "cta": 60}


def library_id(text):
    """The Ad Library id from a link like facebook.com/ads/library/?id=123, or a bare number."""
    s = str(text or "").strip()
    m = re.search(r"[?&]id=(\d{6,})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"\d{6,}", s) else None


def library_url(lib_id):
    return f"https://www.facebook.com/ads/library/?id={lib_id}"


def days_running(started, until):
    """Whole days from the first day Meta shows it running to `until` (today or the day it stopped)."""
    if not started:
        return None
    return max(0, (until - started).days) + 1


def label(days):
    if days is None:
        return None
    if days >= LONG_RUNNING_DAYS:
        return f"Running {days} days: likely working"
    return f"Running {days} day{'s' if days != 1 else ''}"


def parse_day(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def clean(raw):
    """A swipe from the page or from Claude. Returns (fields, problem)."""
    lib = library_id(raw.get("library_id") or raw.get("link"))
    page = " ".join(str(raw.get("page_name") or "").split())[:LIMITS["page_name"]]
    body = str(raw.get("body") or "").strip()[:LIMITS["body"]]
    if not lib and not body:
        return None, "Paste the Ad Library link, or the ad's text"
    if not page:
        return None, "Say whose ad it is (the Page name)"
    tags = {k: " ".join(str(v).split())[:80] for k, v in (raw.get("tags") or {}).items()
            if k in ("hook", "angle", "format", "offer") and str(v or "").strip()}
    media = str(raw.get("media_url") or "").strip()
    return {"library_id": lib, "page_name": page, "page_id": str(raw.get("page_id") or "")[:40] or None, "body": body or None,
            "title": str(raw.get("title") or "").strip()[:LIMITS["title"]] or None,
            "cta": str(raw.get("cta") or "").strip()[:LIMITS["cta"]] or None,
            "media_url": media if media.startswith("https://") else None,
            "started_on": parse_day(raw.get("started_on")), "stopped_on": parse_day(raw.get("stopped_on")),
            "platforms": [str(p)[:30] for p in (raw.get("platforms") or [])][:6],
            "notes": str(raw.get("notes") or "").strip()[:LIMITS["notes"]] or None, "tags": tags}, None


PROMPT_LIMIT = 4000  # what Claude takes in one request (desk_api.MAX_PROMPT)
DRAFT_MAX = 3500     # a draft leaves room to add a few lines before sending
BRIEF_MAX = 10       # ads in one brief
MIN_BODY = 80
FRAMES = {
    "like": ("Make a new ad for {business} like this competitor ad from our swipe file. Keep what makes it work (the hook, the angle, "
             "the format), but write it for our offer in our own words: don't copy theirs.", "Send it back as a new ad suggestion."),
    "brief": ("Write a short creative brief for {business} from these {n} competitor ads in our swipe file: what they have in common, "
              "what's worth borrowing and what to avoid. Then suggest 3 genuinely different ad concepts for our offer, in our own words, "
              "as new ad suggestions.", ""),
    "brief1": ("Write a short creative brief for {business} from this competitor ad in our swipe file: what makes it work, "
               "what's worth borrowing and what to avoid. Then suggest 3 genuinely different ad concepts for our offer, in our own words, "
               "as new ad suggestions.", ""),
}


def fit(text, limit):
    """One line of at most `limit` characters: spacing tidied, cut at a word with an ellipsis when too long."""
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    cut = s[:limit - 1]
    if " " in cut and s[limit - 1] != " ":
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip() + "…"


def _ran(s):
    days = s.get("days_running")
    if not days:
        return ""
    words = f"running {days} days" if s.get("still_running", True) else f"ran {days} days"
    return words + (", likely working" if s.get("long_running") else "")


def _lines(s, body_room, share):
    """One saved ad as lines; the headline, note and tags get a part of the ad's `share` of the draft, the text the rest."""
    head = fit(s.get("page_name"), LIMITS["page_name"])
    ran = _ran(s)
    cta = str(s.get("cta") or "").replace("_", " ").strip().capitalize()
    tags = fit(" · ".join(f"{k} {fit(v, 80)}" for k, v in (s.get("tags") or {}).items() if str(v or "").strip()), max(40, min(360, share // 4)))
    return [head + (f" · {ran}" if ran else ""),
            *([f"Headline: {fit(s['title'], max(40, min(150, share // 5)))}"] if s.get("title") and str(s["title"]).strip() else []),
            *([f"Text: {fit(s['body'], body_room)}"] if s.get("body") and str(s["body"]).strip() else []),
            *([f"Button: {cta}"] if cta else []),
            *([f"Why we kept it: {fit(s['notes'], max(40, min(300, share // 4)))}"] if s.get("notes") and str(s["notes"]).strip() else []),
            *([f"Tags: {tags}"] if tags else []),
            *([f"Ad Library: {s['library_url']}"] if s.get("library_url") else [])]


def pack(items, frame, lines):
    """A draft from picked items under DRAFT_MAX (both briefs: the swipe file's and the Gallery's). frame(n) →
    (intro, outro, numbered); lines(item, body_room, share) → the item's lines, its "Text: " line only when it has a
    body. The text is trimmed first; when even that won't fit, items drop from the end (never the first one).
    Returns {prompt, left_out} (items past BRIEF_MAX, or that didn't fit)."""
    picked = list(items)[:BRIEF_MAX]
    left_out = len(items) - len(picked)
    while True:
        n = len(picked)
        intro, outro, numbered = frame(n)
        tail = [outro] if outro else []
        if left_out:
            tail.append(f"({left_out} more you picked were left out to keep this short.)")
        frame_len = len(intro) + sum(len(t) + 2 for t in tail) + 2 * n
        share = (DRAFT_MAX - frame_len) // max(n, 1)
        blocks = []
        for i, s in enumerate(picked):
            number = f"{i + 1}. " if numbered else ""
            fixed = len(number) + len("\n".join(lines({**s, "body": ""}, 0, share))) + len("\nText: ")
            blocks.append(number + "\n".join(lines(s, max(MIN_BODY, share - fixed), share)))
        prompt = "\n\n".join([intro, *blocks, *tail])
        if len(prompt) <= DRAFT_MAX or n == 1:
            return {"prompt": prompt, "left_out": left_out}
        picked = picked[:-1]
        left_out += 1


def brief(items, mode, business):
    """The prompt Claude gets for "Make something like this" (one saved ad) or "Write a brief" (several): every
    saved detail of each ad, the ad text trimmed so the whole draft stays under DRAFT_MAX. Returns
    {prompt, left_out} (ads past BRIEF_MAX, or that didn't fit)."""
    who = " ".join(str(business or "").split()) or "us"

    def frame(n):
        key = ("like" if mode == "like" else "brief1") if n == 1 else "brief"
        intro, outro = FRAMES[key]
        return intro.format(business=who, n=n), outro, key == "brief"
    return pack(items, frame, _lines)


def view(row, today):
    until = row.get("stopped_on") or today
    days = days_running(row.get("started_on"), until)
    return {**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()},
            "days_running": days, "running_label": label(days), "long_running": bool(days and days >= LONG_RUNNING_DAYS),
            "still_running": row.get("stopped_on") is None,
            "library_url": library_url(row["library_id"]) if row.get("library_id") else None}
