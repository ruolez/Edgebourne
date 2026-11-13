"""Date windows for every screen, and the window just before for "vs previous". Pure.

Two kinds (FU-C): screens show numbers through now (live on: Today, and Last 7/14/30 days and This month
with today so far), while every judgment (verdicts, alerts, tests, Did it work?, Claude's snapshot, checks
against Ads Manager, reports) reads complete days only, through yesterday (account clock), the default.
`tests/test_ranges_logic.LiveRatchetTests` keeps live windows to the display endpoints."""
from datetime import date, timedelta

KEYS = ("today", "7", "14", "30", "mtd", "lastmonth", "custom")
LIVE_KEYS = ("today", "7", "14", "30", "mtd", "custom")  # ranges that may reach today
MAX_DAYS = 366
HOUR_FIELD = "hourly_stats_aggregated_by_advertiser_time_zone"


def _parse(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _month_start(d):
    return d.replace(day=1)


def window(key, today, start=None, end=None, live=False):
    """(start, end) inclusive for a range key; unknown keys mean the last 7 days. Live off (every judgment):
    complete days, "today" being yesterday alone. Live on (what a screen shows): Today is today, Last N days
    are today and the N-1 days before, This month runs to today, a custom range may end today."""
    last = today if live else today - timedelta(days=1)
    if key == "today":
        return last, last
    if key in ("7", "14", "30"):
        return last - timedelta(days=int(key) - 1), last
    if key == "mtd":
        return _month_start(last), last
    if key == "lastmonth":
        end_prev = _month_start(today) - timedelta(days=1)
        return _month_start(end_prev), end_prev
    if key == "custom":
        a, b = _parse(start), _parse(end)
        if a and b:
            a, b = min(a, b), min(max(a, b), last)
            a = min(a, b)
            if (b - a).days + 1 > MAX_DAYS:
                a = b - timedelta(days=MAX_DAYS - 1)
            return a, b
    return window("7", today, live=live)


def settled(start, end, today):
    """The complete-day part of a window, or None when it has none (Today alone)."""
    end = min(end, today - timedelta(days=1))
    return (start, end) if start <= end else None


def includes_today(start, end, today):
    return start <= today <= end


def compare_plan(key, start, end, today):
    """How "vs before" works for a window a screen shows. A past window: against the one before, as always.
    Today alone: against yesterday up to the same hour. A window with today in it: its complete days against
    as many complete days before (today isn't over, so it's shown but not compared)."""
    if end < today:
        return {"mode": "days", "now": (start, end), "before": previous(start, end, key), "note": None}
    part = settled(start, end, today)
    if part is None:
        y = today - timedelta(days=1)
        return {"mode": "hours", "now": (today, today), "before": (y, y), "note": None}
    return {"mode": "days", "now": part, "before": previous(*part, key), "note": "complete days"}


def _hour(row):
    try:
        return int(str(row.get(HOUR_FIELD) or "")[:2])
    except ValueError:
        return None


def _cents(value):
    try:
        return int(round(float(value or 0) * 100))
    except (TypeError, ValueError):
        return 0


def _leads(actions):
    import insights
    return insights.lead_count(actions)


def same_hours(hour_rows, upto_hour):
    """Meta's hourly rows of one day (account time zone) summed for hours 0..upto_hour, both included."""
    out = {"spend_cents": 0, "leads": 0, "impressions": 0, "link_clicks": 0}
    for r in hour_rows:
        h = _hour(r)
        if h is None or h > upto_hour:
            continue
        out["spend_cents"] += _cents(r.get("spend"))
        out["leads"] += _leads(r.get("actions"))
        out["impressions"] += int(r.get("impressions") or 0)
        out["link_clicks"] += int(r.get("inline_link_clicks") or 0)
    return out


def by_hour_words(hour):
    """The clock time a same-hours comparison runs to: hour 14 (2:00-2:59 PM) → "3 PM"."""
    h = (hour + 1) % 24
    return "midnight" if h == 0 else "noon" if h == 12 else f"{h % 12} {'AM' if h < 12 else 'PM'}"


def with_live(judged, live, key, fields, unjudged):
    """Rows judged (and ordered) on complete days, showing the figures through now from `live` (matched on `key`).
    A row only `live` has comes last, with `unjudged` over its own judgments: today's numbers judge nothing."""
    now = {r[key]: r for r in live}
    out = [{**r, **{f: now[r[key]][f] for f in fields}} if r[key] in now else dict(r) for r in judged]
    seen = {r[key] for r in judged}
    return out + [{**r, **unjudged} for r in live if r[key] not in seen]


def previous(start, end, key):
    """The window to compare with: this month or last month (`mtd`, `lastmonth`) against the same days
    of the month before; any other window against the same number of days just before, even when it
    happens to start on the 1st (audit A3-14)."""
    if key in ("mtd", "lastmonth"):
        prev_end_month = start - timedelta(days=1)
        prev_start = _month_start(prev_end_month)
        if (end + timedelta(days=1)).month != end.month:
            return prev_start, prev_end_month
        return prev_start, min(prev_start + timedelta(days=(end - start).days), prev_end_month)
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def label(start, end, today=None):
    """"Nov 5 – Nov 11"; a window ending today (a screen's) says so: "Nov 6 – today", "Today"."""
    if today is not None and end == today:
        return "Today" if start == end else f"{start:%b} {start.day} – today"
    return f"{start:%b} {start.day} – {end:%b} {end.day}" if start != end else f"{start:%b} {start.day}"


def daily_series(rows, start, end, keys, today=None):
    """One entry per day from start to end: rows (ISO day → numbers) where a day has them, zero otherwise.
    Today's entry carries partial: True (Meta is still counting it), so charts draw it apart."""
    out = []
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        r = rows.get(day.isoformat()) or {}
        out.append({"day": day.isoformat(), **{k: int(r.get(k) or 0) for k in keys}, **({"partial": True} if day == today else {})})
    return out
