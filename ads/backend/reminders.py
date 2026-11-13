"""Leads nobody has tried get chased: after 5 minutes the owner (or, with no owner, everyone who gets the
lead alert) hears about it, after an hour the admins do. A next step that comes due reminds the lead's owner
(else whoever set it, else the admins) once per due time (L1). At 8 AM local time each admin gets the day
(leads waiting for a first call, follow-ups due or overdue, booked calls); a teammate gets the leads they own.
"Tried" means a logged call, an email sent from the lead page or a stage change, as on Today and Leads; a note
alone is not a call, and a booked call stops the first-call reminders. Test leads and leads over a day old
never trigger a first-call reminder.

Alerts go to Telegram when the person linked it, otherwise by email (notify.py queue).
"""
import statistics
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account_info
import config
import db
import followup
import mailer
import notify
import replies
import settings_store
import today

STEPS = (("5m", timedelta(minutes=today.FRESH_MINUTES)), ("1h", timedelta(minutes=today.LATE_MINUTES)))
TOO_OLD = timedelta(hours=24)
DIGEST_HOUR = 8


def untouched(lead):
    """The rule Today and Leads use (today.waiting): New, not a test, nobody called, emailed or moved it."""
    return today.waiting(lead)


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
    junk = bool(lead.get("junk_flags")) and not lead.get("junk_dismissed")
    if kind == "5m":
        title = f"Nobody has called {name} yet (5 min{', looks like junk' if junk else ''})"
    else:
        title = f"{name} has waited {_wait(lead, now)} for a call" + (" (looks like junk)" if junk else "")
    lines = [lead.get("business_type") or "Business not given"]
    if lead.get("phone"):
        lines.append(f"Phone: {replies.phone_display(lead['phone'])}")
    return title, lines


LEADS_SQL = """SELECT l.* FROM leads l
               WHERE l.status = 'new' AND NOT l.is_test AND l.repeat_of IS NULL AND l.first_contacted_at IS NULL
               AND l.meeting_status IS DISTINCT FROM 'scheduled'"""
OPEN_SQL = "l.status IN ('new', 'contacted', 'qualified') AND NOT l.is_test AND l.repeat_of IS NULL"


def followups(now):
    """One reminder per follow-up that came due (a moved step reminds again; a retry never does). It goes to
    the lead's owner, else whoever set the step, else the account's admins. Missed for a day: dropped (the
    digest still lists it as overdue)."""
    tz = account_info.tz()
    queued = 0
    for lead in db.query(f"SELECT l.* FROM leads l WHERE {OPEN_SQL} AND l.next_step_at <= %s AND l.next_step_at > %s",
                         (now, now - followup.REMIND_FOR)):
        if not followup.reminder_due(lead, now):
            continue
        people = [lead["owner_id"]] if lead["owner_id"] else [lead["next_step_by"]] if lead["next_step_by"] else notify.admin_ids()
        title, lines = followup.due_text(lead, tz)
        epoch = int(lead["next_step_at"].timestamp())
        for uid, channel in notify.reach(people):
            notify.queue(uid, channel, "followup", title, lines, notify.link(f"/leads.html#lead={lead['id']}"), "Open the lead",
                         ref=str(lead["id"]), dedupe_key=f"followup:{lead['id']}:{epoch}:{uid}")
            queued += 1
    return queued


def digest(now, local):
    """The 8 AM message: admins get every lead, a teammate the leads they own. Returns how many were queued."""
    tz = account_info.tz()
    end = followup.due_where("today", now, tz)[1][1]
    waiting = [l for l in db.query(LEADS_SQL + " ORDER BY l.created_time") if untouched(l)]
    due = db.query(f"SELECT l.* FROM leads l WHERE {OPEN_SQL} AND l.next_step_at < %s ORDER BY l.next_step_at", (end,))
    calls = db.query(f"""SELECT l.* FROM leads l WHERE {OPEN_SQL} AND l.meeting_status = 'scheduled'
                         AND l.meeting_at >= %s AND l.meeting_at < %s ORDER BY l.meeting_at""", (now, end))
    admins = notify.admin_ids()
    owners = {l["owner_id"] for l in waiting + due + calls if l["owner_id"] and l["owner_id"] not in admins}
    queued = 0
    for uid in list(admins) + sorted(owners):
        mine = (lambda ls: ls) if uid in admins else (lambda ls, u=uid: [l for l in ls if l["owner_id"] == u])
        text = followup.digest_text(mine(waiting), mine(due), mine(calls), now, tz)
        if not text:
            continue
        for who, channel in notify.reach([uid]):
            notify.queue(who, channel, "digest", text[0], text[1], notify.link("/leads.html?due=today"), "Open the leads",
                         dedupe_key=f"digest:{local.date().isoformat()}:{who}")
            queued += 1
    return queued


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
        queued += digest(now, local)
    return queued + followups(now)


def stats(where="TRUE", params=()):
    """The response line on Leads: how fast leads got a first try, and the calls logged, last 30 days."""
    rows = db.query(
        f"SELECT EXTRACT(EPOCH FROM (l.first_contacted_at - l.created_time)) / 60 AS wait_minutes FROM leads l "
        f"WHERE {where} AND NOT l.is_test AND l.repeat_of IS NULL AND l.created_time > now() - interval '30 days'", list(params))
    calls = db.query(
        f"""SELECT e.outcome, e.undone_at IS NOT NULL AS undone FROM lead_events e JOIN leads l ON l.id = e.lead_id
            WHERE e.kind = 'call' AND e.at > now() - interval '30 days' AND {where} AND NOT l.is_test""", list(params))
    return {**response_stats([{"wait_minutes": float(r["wait_minutes"]) if r["wait_minutes"] is not None else None} for r in rows]),
            **followup.call_stats(calls)}
