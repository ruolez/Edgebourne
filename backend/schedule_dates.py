"""Recurrence date arithmetic. Pure functions, no I/O — the part of the
scheduler that is worth unit-testing on its own.

THE JAN-31 RULE. Periods are always computed from the anchor as
`start_date + n * interval`, never by mutating the previous period's date.
Iteratively adding a month to a clamped date gives

    Jan 31 -> Feb 28 -> Mar 28 -> Apr 28 ...

which is wrong and drifts forever. Anchoring gives

    Jan 31 -> Feb 29 -> Mar 31 -> Apr 30 -> May 31 ...

and self-heals every long month.
"""

import calendar
from datetime import date, datetime, time, timedelta, timezone

MONTHS_PER_INTERVAL = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}


def add_months(start, months, anchor_day):
    """Shift by whole months, clamping the day to the target month's length."""
    total = start.year * 12 + (start.month - 1) + months
    year, month_index = divmod(total, 12)
    last_day = calendar.monthrange(year, month_index + 1)[1]
    return date(year, month_index + 1, min(anchor_day, last_day))


def nth_period_start(sub, n):
    """Start date of the n-th occurrence (n = 0 is the first), computed from
    start_date -- never from the previous period."""
    start = sub["start_date"]
    count = max(1, int(sub.get("interval_count") or 1))
    interval = sub["interval"]
    if interval == "weekly":
        return start + timedelta(weeks=count * n)
    months = MONTHS_PER_INTERVAL[interval] * count
    anchor = int(sub.get("anchor_day") or start.day)
    return add_months(start, months * n, anchor)


def period_bounds(sub, n):
    """(inclusive start, inclusive end) of the n-th period."""
    start = nth_period_start(sub, n)
    return start, nth_period_start(sub, n + 1) - timedelta(days=1)


def period_key(sub, period_start):
    """Deterministic key for the UNIQUE (subscription_id, period_key) index --
    the constraint, not the advisory lock, is what actually guarantees a period
    is never invoiced twice."""
    interval = sub["interval"]
    if interval == "weekly":
        iso = period_start.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if interval == "monthly":
        return f"{period_start.year}-{period_start.month:02d}"
    if interval == "quarterly":
        return f"{period_start.year}-Q{(period_start.month - 1) // 3 + 1}"
    if interval == "semiannual":
        return f"{period_start.year}-H{1 if period_start.month <= 6 else 2}"
    return str(period_start.year)


def run_at_utc(period_start, run_hour, tz):
    """Convert a local calendar date + hour into an aware UTC instant.

    Computing each period as a LOCAL date and then converting is what makes DST
    transitions harmless -- adding 30 days in UTC would eventually date a
    retainer to the previous day for a west-coast client.
    """
    naive = datetime.combine(period_start, time(hour=int(run_hour or 0)))
    try:
        from zoneinfo import ZoneInfo

        local = naive.replace(tzinfo=ZoneInfo(tz or "UTC"))
    except Exception:
        # Missing tzdata must never stop billing; UTC is a safe fallback.
        local = naive.replace(tzinfo=timezone.utc)
    return local.astimezone(timezone.utc)


def next_run_for(sub, occurrences_generated=None):
    """When the next un-generated period should be billed."""
    n = sub["occurrences_generated"] if occurrences_generated is None else occurrences_generated
    return run_at_utc(nth_period_start(sub, n), sub.get("run_hour") or 0,
                      sub.get("timezone") or "UTC")
