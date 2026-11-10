"""Date windows for every screen: complete days only (through yesterday, account clock), and the
window just before for "vs previous". Pure."""
from datetime import date, timedelta

KEYS = ("7", "14", "30", "mtd", "lastmonth", "custom")
MAX_DAYS = 366


def _parse(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _month_start(d):
    return d.replace(day=1)


def window(key, today, start=None, end=None):
    """(start, end) inclusive for a range key; unknown keys mean the last 7 days."""
    last = today - timedelta(days=1)
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
    return window("7", today)


def previous(start, end):
    """The window to compare with: a calendar month (or month to date) against the same days of the
    month before; anything else against the same number of days just before."""
    if start.day == 1:
        prev_end_month = start - timedelta(days=1)
        prev_start = _month_start(prev_end_month)
        if end.month == start.month and end.year == start.year:
            last_day = (end + timedelta(days=1)).month != end.month
            if last_day:
                return prev_start, prev_end_month
            return prev_start, min(prev_start + timedelta(days=(end - start).days), prev_end_month)
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def label(start, end):
    return f"{start:%b} {start.day} – {end:%b} {end.day}" if start != end else f"{start:%b} {start.day}"
