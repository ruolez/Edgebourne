"""Desk schedules: Claude's regular checks (daily health, optimizer review, Monday summary,
monthly audit). When one is due the worker files an ordinary Desk task, so the Mac bridge
works it like any other, with the same read-only tools; proposals are still the only thing
that can change anything. A schedule is skipped (and moved on) while its previous run is
still waiting, so a Mac that's off doesn't come back to a pile of duplicates.
"""
import json
import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import db

EVERY = ("day", "days", "week", "month")
WEEKDAYS = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")
AT = re.compile(r"^(\d{1,2}):(\d{2})$")


def _at(rule):
    h, m = AT.match(rule["at"]).groups()
    return int(h), int(m)


def _local(day, rule, tz):
    h, m = _at(rule)
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def next_run(rule, after, tz, last_run=None):
    """The first run strictly after `after` (UTC), at the rule's local time in `tz`."""
    now = after.astimezone(tz)
    every = rule["every"]
    if every == "days" and last_run:
        step = timedelta(days=int(rule["days"]))
        day = last_run.astimezone(tz).date() + step
        while _local(day, rule, tz) <= now:
            day += step
        return _local(day, rule, tz).astimezone(timezone.utc)
    day = now.date()
    for _ in range(400):
        ok = (every in ("day", "days")
              or (every == "week" and day.weekday() == int(rule["weekday"]))
              or (every == "month" and day.day == int(rule["monthday"])))
        if ok and _local(day, rule, tz) > now:
            return _local(day, rule, tz).astimezone(timezone.utc)
        day += timedelta(days=1)
    raise ValueError("no run found for this rule")


def _clock(rule):
    h, m = _at(rule)
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def describe(rule):
    every = rule["every"]
    if every == "day":
        return f"Every day at {_clock(rule)}"
    if every == "days":
        return f"Every {rule['days']} days at {_clock(rule)}"
    if every == "week":
        return f"{WEEKDAYS[int(rule['weekday'])]} at {_clock(rule)}"
    return f"The {_ordinal(int(rule['monthday']))} of each month at {_clock(rule)}"


def clean_rule(data):
    """(rule, None) or (None, name of the field that's wrong)."""
    every = data.get("every")
    if every not in EVERY:
        return None, "every"
    m = AT.match(str(data.get("at") or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None, "at"
    rule = {"every": every, "at": f"{int(m.group(1)):02d}:{m.group(2)}"}
    try:
        if every == "days":
            rule["days"] = int(data.get("days"))
            if not 2 <= rule["days"] <= 30:
                return None, "days"
        if every == "week":
            rule["weekday"] = int(data.get("weekday"))
            if not 0 <= rule["weekday"] <= 6:
                return None, "weekday"
        if every == "month":
            rule["monthday"] = int(data.get("monthday"))
            if not 1 <= rule["monthday"] <= 28:
                return None, "monthday"
    except (TypeError, ValueError):
        return None, {"days": "days", "week": "weekday", "month": "monthday"}[every]
    return rule, None


def tz():
    return ZoneInfo(config.ACCOUNT_TZ)


def run(now=None):
    """File a Desk task for every schedule that's due. Returns the new task ids."""
    now = now or datetime.now(timezone.utc)
    made = []
    for s in db.query("SELECT * FROM desk_schedules WHERE enabled AND next_run_at <= %s ORDER BY id", (now,)):
        nxt = next_run(s["rule"], now, tz(), now)
        claimed = db.execute("UPDATE desk_schedules SET next_run_at = %s, last_run_at = %s WHERE id = %s AND next_run_at = %s RETURNING id",
                             (nxt, now, s["id"], s["next_run_at"]), returning=True)
        if not claimed:
            continue  # another pass got it
        busy = s["last_task_id"] and db.query("SELECT 1 FROM desk_tasks WHERE id = %s AND status IN ('queued', 'claimed', 'running')",
                                               (s["last_task_id"],), one=True)
        if busy:
            db.execute("UPDATE desk_schedules SET skipped = skipped + 1 WHERE id = %s", (s["id"],))
            continue
        task = db.execute("INSERT INTO desk_tasks (kind, prompt, options) VALUES (%s, %s, %s) RETURNING id",
                          (s["kind"], s["prompt"], json.dumps({"schedule_id": s["id"], "schedule": s["name"]})), returning=True)
        db.execute("UPDATE desk_schedules SET last_task_id = %s WHERE id = %s", (task["id"], s["id"]))
        made.append(task["id"])
    return made


def listing():
    rows = db.query("SELECT s.*, t.status AS last_status, t.summary AS last_summary FROM desk_schedules s "
                    "LEFT JOIN desk_tasks t ON t.id = s.last_task_id ORDER BY s.position, s.id")
    for r in rows:
        r["when"] = describe(r["rule"])
    return rows
