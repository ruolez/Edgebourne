"""Change marks on the daily charts: what changed on which day (budget, on/off, edits, Meta's own),
grouped by the account's day, with Meta's echoes of a switch left out. Pure.

Items are timeline.merge items: {kind, at, cat, title, by, source, level, entity_id, entity_name, field, old,
new, tone, proposal_id}."""
from datetime import timedelta

CAT_ORDER = ("money", "switch", "edit", "meta")
PER_DAY = 6
LIST_MAX = 30  # rows in the changes list under the charts; each History has the rest
ECHO = timedelta(minutes=15)
CASCADE = ("CAMPAIGN_PAUSED", "ADSET_PAUSED")
MONEY_FIELDS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "bid_amount")
# AM-C setup fields Meta reports (status_history.EDIT_SETUP) chart as edits: the "created"/"targeting" rule below covers them.
SWITCH_STATES = ("PAUSED", "ARCHIVED", "DELETED") + CASCADE
NOT_CHARTED = ("subscribe", "unsubscribe", "copy")
LEVEL_WORDS = {"campaign": "campaign", "adset": "ad set", "ad": "ad"}


def category(item):
    """money | switch | edit | meta for one timeline item (from its field, action or kind)."""
    kind, field, new = item.get("kind"), item.get("field"), item.get("new")
    if kind == "version":
        return "edit"
    if kind == "change":
        if field in ("budget", "recommendation", "recommendation_check", "spend_limit", "spend_limit_restore", "bid", "bid_strategy", "spend_cap"):
            return "money"
        if field in ("status", "archive", "delete", "schedule", "copy_guard"):
            return "switch"
        return "edit"
    if field in MONEY_FIELDS:
        return "money"
    if field in ("configured_status", "start_time", "end_time"):
        return "switch"
    if field in ("created", "targeting", "placements", "optimization_goal", "attribution", "frequency", "special_ad_categories"):
        return "edit"
    if field == "effective_status" and new in SWITCH_STATES:
        return "switch"
    return "meta"


def chart_worthy(items):
    """Leave out what would only repeat another mark: an ad set or ad stopping because its parent was
    switched (the parent's mark says it), Meta's echo of a switch made a moment before, decided suggestions
    (their change is there) and comment replies."""
    switches = [i for i in items if i.get("kind") == "status" and i.get("field") == "configured_status"]
    out = []
    for i in items:
        if i.get("kind") == "proposal":
            continue
        field = i.get("field") or ""
        if i.get("kind") == "change" and (field.startswith("comment_") or field in NOT_CHARTED):
            continue
        if i.get("kind") == "status" and field == "effective_status":
            if i.get("new") in CASCADE or (i.get("old") in CASCADE and i.get("new") == "ACTIVE"):
                continue
            if any(s["entity_id"] == i.get("entity_id") and s.get("new") == i.get("new") and abs(s["at"] - i["at"]) <= ECHO
                   for s in switches):
                continue
        out.append(i)
    return out


def _cents(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def short_words(item):
    """A few words for the summary line: 'budget raised', 'ad “N6” approved'."""
    field, old, new, cat = item.get("field"), item.get("old"), item.get("new"), item.get("cat")
    who = f"{LEVEL_WORDS.get(item.get('level'), 'it')} “{item.get('entity_name') or ''}”"
    if field in ("budget", "daily_budget", "lifetime_budget"):
        a, b = _cents(old), _cents(new)
        return "budget raised" if a and b and b > a else "budget lowered" if a and b and b < a else "budget changed"
    if field in ("recommendation", "recommendation_check"):
        return "Meta's advice applied"
    if field in ("spend_cap", "spend_limit", "spend_limit_restore"):
        return "spending limit changed"
    if field in ("bid_strategy", "bid_amount"):
        return "bid changed"
    if field in ("start_time", "end_time"):
        return "dates changed"
    if field == "targeting":
        return "audience changed"
    if item.get("kind") == "version":
        return f"{who} new version"
    if field in ("configured_status", "status"):
        return f"{who} switched {'on' if new == 'ACTIVE' else 'off'}"
    if field == "effective_status" and new == "ACTIVE" and old in ("IN_PROCESS", "PENDING_REVIEW", "PREAPPROVED"):
        return f"{who} approved"
    if field in ("effective_status", "created") and new == "DISAPPROVED":
        return f"{who} rejected"
    if field == "created":
        return f"{who} created"
    if cat == "edit":
        return f"{who} edited"
    return f"{who}: {str(item.get('title') or '').lower()}"


def _title(item, for_client):
    title = item.get("title") or ""
    if item.get("kind") == "change" and item.get("proposal_id") and not for_client:
        title += " (Claude's suggestion)"
    return title


def _by(item, for_client):
    if not for_client:
        return item.get("by")
    return "Team" if item.get("source") == "console" else (item.get("by") or "Meta")


def _shown(r, for_client):
    return {"cat": r.get("cat") or "meta", "title": _title(r, for_client), "by": _by(r, for_client),
            "level": r.get("level"), "entity_id": r.get("entity_id"), "entity_name": r.get("entity_name"),
            "at": r["at"].isoformat(), "tone": r.get("tone") or "", "short": short_words(r)}


def by_day(items, tz, start, end, for_client=False):
    """[{day, cats, items, more}] for the days in [start, end] (account days) that had a change; each day's
    items money first, then by time, at most PER_DAY. Clients never see a person's name or Claude."""
    days = {}
    for i in items:
        d = i["at"].astimezone(tz).date()
        if start <= d <= end:
            days.setdefault(d, []).append(i)
    out = []
    for d in sorted(days):
        rows = sorted(days[d], key=lambda i: (CAT_ORDER.index(i.get("cat") or "meta"), i["at"]))
        shown = rows[:PER_DAY]
        out.append({"day": d.isoformat(),
                    "cats": [c for c in CAT_ORDER if any(r.get("cat") == c for r in rows)],
                    "items": [_shown(r, for_client) for r in shown],
                    "more": len(rows) - len(shown)})
    return out


def latest(items, tz, start, end, for_client=False, limit=LIST_MAX):
    """{items, total} for the changes list: the newest `limit` changes in [start, end] (account days), newest
    first, each with its `day`, whatever the per-day cap on the charts; `total` counts every change."""
    rows = [(i, i["at"].astimezone(tz).date()) for i in items]
    rows = sorted(((i, d) for i, d in rows if start <= d <= end), key=lambda x: x[0]["at"], reverse=True)
    return {"items": [{**_shown(i, for_client), "day": d.isoformat()} for i, d in rows[:limit]], "total": len(rows)}


def summary_words(marks, day_words, limit=3):
    """'2 changes in this period: budget raised Nov 9, ad “N6” approved Nov 11.'"""
    flat = sorted(((i["at"], i["short"], m["day"]) for m in marks for i in m["items"]), key=lambda x: x[0])
    total = sum(len(m["items"]) + m.get("more", 0) for m in marks)
    if not total:
        return "No changes in this period."
    named = ", ".join(f"{short} {day_words(day)}" for _, short, day in flat[:limit])
    rest = total - min(limit, len(flat))
    return f"{total} change{'s' if total != 1 else ''} in this period: {named}{f' and {rest} more' if rest else ''}."
