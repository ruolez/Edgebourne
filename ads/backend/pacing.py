"""Month pacing: spend so far this month, where the month lands at the current pace, when the
account spending limit runs out, and the daily spend that lands on a monthly target.
Pure; the pace is the average of the last 7 complete days (the daily budget before any)."""
import calendar
from datetime import timedelta


def pace(today, month_days, recent_daily, daily_budget_cents, target_cents, cap_remaining_cents, today_so_far_cents=0):
    """month_days: [(day, cents)] for complete days this month; recent_daily: last 7 complete days' cents."""
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day + 1
    done = sum(c for d, c in month_days if d.month == today.month and d < today)
    rate = round(sum(recent_daily) / len(recent_daily)) if recent_daily else (daily_budget_cents or 0)
    projected = done + rate * days_left
    cap_days = cap_remaining_cents // rate if cap_remaining_cents is not None and rate > 0 else None
    return {
        "month": today.strftime("%B"),
        "days_done": today.day - 1,
        "days_left": days_left,
        "mtd_cents": done + (today_so_far_cents or 0),
        "rate_cents": rate,
        "projected_cents": projected,
        "target_cents": target_cents,
        "needed_daily_cents": max(0, round((target_cents - done) / days_left)) if target_cents else None,
        "vs_target_pct": round(projected / target_cents * 100 - 100) if target_cents else None,
        "cap_days": cap_days,
        "cap_date": (today + timedelta(days=cap_days)).isoformat() if cap_days is not None else None,
    }
