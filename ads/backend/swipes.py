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


def view(row, today):
    until = row.get("stopped_on") or today
    days = days_running(row.get("started_on"), until)
    return {**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()},
            "days_running": days, "running_label": label(days), "long_running": bool(days and days >= LONG_RUNNING_DAYS),
            "still_running": row.get("stopped_on") is None,
            "library_url": library_url(row["library_id"]) if row.get("library_id") else None}
