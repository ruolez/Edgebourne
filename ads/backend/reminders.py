"""Leads nobody has contacted get chased: after 5 minutes the owner (or, with no owner, everyone
who gets the lead alert) hears about it, after an hour the admins do, and at 8 AM local time the
admins get the list of every lead still waiting. "Contacted" means a stage change, an email sent
from the lead page or a note. Test leads and leads over a day old never trigger a reminder.

Alerts go to Telegram when the person linked it, otherwise by email (notify.py queue).
"""
import statistics
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account_info
import config
import db
import mailer
import notify
import replies
import settings_store

STEPS = (("5m", timedelta(minutes=5)), ("1h", timedelta(hours=1)))
TOO_OLD = timedelta(hours=24)
DIGEST_HOUR = 8


def untouched(lead):
    return (lead["status"] == "new" and not lead["is_test"] and not lead["first_contacted_at"] and not lead["notes"])


def due(lead, now):
    """Which reminder steps this lead has reached (the queue never sends one twice)."""
    age = now - lead["created_time"]
    if not untouched(lead) or age >= TOO_OLD:
        return []
    return [kind for kind, after in STEPS if age >= after]


def digest_due(now_local, last_date):
    return now_local.hour >= DIGEST_HOUR and last_date != now_local.date().isoformat()


def response_stats(rows):
    waits = [r["wait_minutes"] for r in rows if r["wait_minutes"] is not None]
    return {"leads": len(rows), "contacted": len(waits),
            "median_minutes": round(statistics.median(waits)) if waits else None,
            "within_5": sum(1 for w in waits if w <= 5), "untouched": len(rows) - len(waits)}


def _wait(lead, now):
    minutes = int((now - lead["created_time"]).total_seconds() // 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h"


def reminder_text(lead, kind, now):
    name = lead.get("full_name") or "Someone"
    title = f"Nobody has called {name} yet (5 min)" if kind == "5m" else f"{name} has waited {_wait(lead, now)} for a call"
    lines = [lead.get("business_type") or "Business not given"]
    if lead.get("phone"):
        lines.append(f"Phone: {replies.phone_display(lead['phone'])}")
    return title, lines


def digest_text(leads, now):
    n = len(leads)
    title = f"{n} lead{'s are' if n != 1 else ' is'} still waiting for a call"
    lines = [f"{l.get('full_name') or 'Someone'}{', ' + l['business_type'] if l.get('business_type') else ''}: waiting {_wait(l, now)}" for l in leads]
    return title, lines


LEADS_SQL = """SELECT l.*, (SELECT COUNT(*) FROM lead_notes n WHERE n.lead_id = l.id) AS notes FROM leads l
               WHERE l.status = 'new' AND NOT l.is_test AND l.first_contacted_at IS NULL"""


def run(now=None):
    """One pass: queue whatever reminders are due. Cheap enough for every worker pass."""
    import leads as leads_mod
    now = now or datetime.now(timezone.utc)
    queued = 0
    for lead in db.query(LEADS_SQL + " AND l.created_time > %s", (now - TOO_OLD,)):
        url = notify.link(f"/leads.html#lead={lead['id']}")
        kinds = due(lead, now)
        admins = notify.admin_ids()
        for kind in kinds:
            people = ([lead["owner_id"]] if lead["owner_id"] else leads_mod.recipient_ids(lead)) if kind == "5m" else admins
            if kind == "5m" and "1h" in kinds:  # caught up late: admins get only the hour one
                people = [p for p in people if p not in admins]
            title, lines = reminder_text(lead, kind, now)
            for uid, channel in notify.reach(people):
                notify.queue(uid, channel, "reminder", title, lines, url, "Open the lead", ref=str(lead["id"]),
                             dedupe_key=f"reminder:{kind}:{lead['id']}:{uid}")
                queued += 1
    local = now.astimezone(account_info.tz())
    last = settings_store.get("reminder_digest_date")
    if last is None:  # first run: start tomorrow rather than send a list the moment it's switched on
        settings_store.set("reminder_digest_date", local.date().isoformat())
    elif digest_due(local, last):
        settings_store.set("reminder_digest_date", local.date().isoformat())
        waiting = [l for l in db.query(LEADS_SQL + " ORDER BY l.created_time") if untouched(l)]
        if waiting:
            title, lines = digest_text(waiting, now)
            for uid, channel in notify.reach(notify.admin_ids()):
                notify.queue(uid, channel, "digest", title, lines, notify.link("/leads.html"), "Open the leads",
                             dedupe_key=f"digest:{local.date().isoformat()}:{uid}")
                queued += 1
    return queued


def stats(where="TRUE", params=()):
    rows = db.query(
        f"SELECT EXTRACT(EPOCH FROM (l.first_contacted_at - l.created_time)) / 60 AS wait_minutes FROM leads l "
        f"WHERE {where} AND NOT l.is_test AND l.created_time > now() - interval '30 days'", list(params))
    return response_stats([{"wait_minutes": float(r["wait_minutes"]) if r["wait_minutes"] is not None else None} for r in rows])
