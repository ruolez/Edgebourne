"""Follow-ups and booked calls (L1): call outcomes, the next step with its due time, and a booked call.

The rules are pure (top half, unit tested); the writes below keep the lead's follow-up columns in step with
`lead_events` (lead_history.record), the one record of what happened. Times are worked out in the account's
time zone (account_info.tz()), which also handles daylight saving.

Words: a booked call is a "call" (never meeting or appointment); a next step is a "follow-up".
"""
import re
from datetime import datetime, time, timedelta, timezone

import words

OUTCOMES = ("reached", "no_answer", "voicemail", "wrong_number", "booked")
REACHED = ("reached", "booked")
OUTCOME_WORDS = {"reached": "talked to them", "no_answer": "no answer", "voicemail": "left a voicemail",
                 "wrong_number": "wrong number", "booked": "booked a call"}
NEXT_KINDS = ("call_back", "proposal", "follow_up", "other")
NEXT_WORDS = {"call_back": "Call back", "proposal": "Send a quote", "follow_up": "Follow up"}
PRESETS = ("later_today", "tomorrow_9", "in_3_days")
LATER_TODAY_HOURS, DAY_END_HOUR, MORNING_HOUR = 3, 18, 9
MEETING_GRACE = timedelta(minutes=60)
LOST_AFTER = 3
OPEN = ("new", "contacted", "qualified")
REMIND_FOR = timedelta(hours=24)
TEXT_MAX = 120
LOST_NOTES = {"couldnt_reach": "Couldn't reach after 3 tries", "went_quiet": "Went quiet after 3 tries"}
# The Lost reasons a stage move may carry until L2 adds its own list (L2 extends this, never free text).
LOST_REASONS = ("no_response",)


class Problem(ValueError):
    """A plain message for the person, and the field it is about."""

    def __init__(self, message, field="when"):
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------- words

def short_clock(dt):
    """'2 PM', '2:30 PM'."""
    return f"{dt.hour % 12 or 12}{f':{dt.minute:02d}' if dt.minute else ''} {'AM' if dt.hour < 12 else 'PM'}"


def next_words(kind, text=None):
    return (text or "Something else") if kind == "other" else NEXT_WORDS.get(kind, "Follow up")


def _name(lead):
    return lead.get("full_name") or "Someone"


# ---------------------------------------------------------------- times

def _local_at(day, hour, tz, minute=0):
    return datetime.combine(day, time(hour, minute), tz).astimezone(timezone.utc)


def due_at(preset, now, tz):
    """When a preset falls, in UTC. Later today: in 3 hours rounded up to the hour, or tomorrow 9 AM when that
    is after 6 PM. Tomorrow 9 AM. In 3 days at 9 AM (weekends included: the button shows its date)."""
    local = now.astimezone(tz)
    if preset == "later_today":
        t = local + timedelta(hours=LATER_TODAY_HOURS)
        if t.minute or t.second or t.microsecond:
            t = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        if t.date() != local.date() or t.hour > DAY_END_HOUR or (t.hour == DAY_END_HOUR and t.minute):
            return _local_at(local.date() + timedelta(days=1), MORNING_HOUR, tz)
        return _local_at(t.date(), t.hour, tz)
    if preset == "tomorrow_9":
        return _local_at(local.date() + timedelta(days=1), MORNING_HOUR, tz)
    if preset == "in_3_days":
        return _local_at(local.date() + timedelta(days=3), MORNING_HOUR, tz)
    raise Problem("Pick when")


def _check_future(at, now):
    if at < now:
        raise Problem("Pick a time from now on")
    if at > now + timedelta(days=365):
        raise Problem("Pick a date within a year")
    return at


def parse_local(value, tz, now):
    """'2026-11-13T14:00' in the account's time zone → UTC; from now on, within a year."""
    try:
        naive = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise Problem("Pick a date and time")
    at = (naive.replace(tzinfo=tz) if naive.tzinfo is None else naive).astimezone(timezone.utc)
    return _check_future(at, now)


def clean_next(data, tz, now):
    """{kind, text, at} from {kind, text?, preset? | at?}, or Problem."""
    data = data or {}
    kind = data.get("kind")
    if kind not in NEXT_KINDS:
        raise Problem("Pick a next step", "kind")
    text = None
    if kind == "other":
        text = re.sub(r"\s+", " ", str(data.get("text") or "")).strip()
        if not text:
            raise Problem("Say what the next step is", "text")
        if len(text) > TEXT_MAX:
            raise Problem(f"Keep it under {TEXT_MAX} characters", "text")
    if data.get("preset") in PRESETS:
        at = due_at(data["preset"], now, tz)
    elif data.get("at"):
        at = parse_local(data["at"], tz, now)
    else:
        raise Problem("Pick when")
    return {"kind": kind, "text": text, "at": at}


def clean_meeting(data, tz, now):
    """When the booked call is (UTC), or None for "Not sure yet". {preset: today|tomorrow, time: "14:00"} |
    {at: "2026-11-13T14:00"} | {unscheduled: true}."""
    data = data or {}
    if data.get("unscheduled"):
        return None
    if data.get("at"):
        return parse_local(data["at"], tz, now)
    preset = data.get("preset")
    if preset not in ("today", "tomorrow"):
        raise Problem("Pick when the call is")
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(data.get("time") or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise Problem("Pick a time")
    day = now.astimezone(tz).date() + timedelta(days=1 if preset == "tomorrow" else 0)
    return _check_future(_local_at(day, int(m.group(1)), tz, int(m.group(2))), now)


def presets(now, tz):
    """The time buttons, each saying when it falls: 'Later today (2 PM)', 'Tomorrow 9 AM', 'Sat, Nov 14 9 AM'."""
    local = now.astimezone(tz)
    out = {}
    for p in PRESETS:
        at = due_at(p, now, tz)
        la = at.astimezone(tz)
        if p == "later_today":
            label = f"Later today ({short_clock(la)})" if la.date() == local.date() else f"Later today (tomorrow {short_clock(la)})"
        elif p == "tomorrow_9":
            label = f"Tomorrow {short_clock(la)}"
        else:
            label = f"{words.weekday(la)} {short_clock(la)}"
        out[p] = {"label": label, "at": at.isoformat()}
    return out


# ---------------------------------------------------------------- rules

def _live_calls(events):
    return sorted((e for e in events if e.get("kind", "call") == "call" and not e.get("undone_at")), key=lambda e: e["at"])


def call_summary(events):
    """The lead's call counters from its call events (undone ones left out)."""
    live = _live_calls(events)
    streak = 0
    for e in live:
        streak = 0 if e["outcome"] in REACHED else streak + 1
    return {"attempts": len(live), "unanswered_streak": streak, "ever_reached": any(e["outcome"] in REACHED for e in live),
            "last_outcome": live[-1]["outcome"] if live else None, "last_call_at": live[-1]["at"] if live else None}


def first_contact_at(calls, stage_changes, emails):
    """The first try: the earliest call (any outcome), email sent, or stage move out of New."""
    times = [e["at"] for e in _live_calls(calls)]
    times += [e["at"] for e in stage_changes if not e.get("undone_at") and (e.get("details") or {}).get("to") not in (None, "new")]
    times += [t for t in emails if t]
    return min(times) if times else None


def lost_suggestion(summary, status):
    """After 3 calls in a row nobody answered: offer Lost (never done on its own). Not once someone qualified them."""
    if status not in ("new", "contacted") or summary.get("unanswered_streak", 0) < LOST_AFTER:
        return None
    return "went_quiet" if summary.get("ever_reached") else "couldnt_reach"


def is_open(lead):
    return lead.get("status") in OPEN and not lead.get("is_test")


def waiting(lead):
    """The one urgency rule (today.waiting): New, not a test, nobody tried yet, no call booked."""
    return (lead.get("status") == "new" and not lead.get("is_test") and not lead.get("first_contacted_at")
            and lead.get("meeting_status") != "scheduled" and not lead.get("repeat_of"))


def meeting_state(lead, now):
    status = lead.get("meeting_status")
    if status is None:
        return None
    if status != "scheduled":
        return status
    at = lead.get("meeting_at")
    if at is None:
        return "unscheduled"
    if now < at - MEETING_GRACE:
        return "upcoming"
    if now < at + MEETING_GRACE:
        return "soon"
    moved = lead.get("status_changed_at")
    if lead.get("status") in ("qualified", "won") and moved and moved >= at:
        return "held"
    return "check"


def _when_words(dt, now, tz):
    """'4 PM' today, else 'Fri 9 AM'."""
    local, today = dt.astimezone(tz), now.astimezone(tz).date()
    return short_clock(local) if local.date() == today else f"{local.strftime('%a')} {short_clock(local)}"


def _on_words(dt, now, tz):
    """'at 4 PM' today, else 'on Fri 9 AM': reads after 'Did the call' or 'No-show'."""
    local, today = dt.astimezone(tz), now.astimezone(tz).date()
    return f"at {short_clock(local)}" if local.date() == today else f"on {_when_words(dt, now, tz)}"


def chip(lead, now, tz):
    """The one chip a lead row shows: the most urgent thing that applies."""
    if not is_open(lead):
        return None
    nxt = lead.get("next_step_at")
    label = next_words(lead.get("next_step_kind"), lead.get("next_step_text")) if nxt else None
    if nxt and nxt <= now:
        local, today = nxt.astimezone(tz), now.astimezone(tz).date()
        since = short_clock(local) if local.date() == today else local.strftime("%a")
        return {"tone": "warn", "text": f"Overdue: {label} ({since})"}
    state = meeting_state(lead, now)
    if state == "check":
        return {"tone": "warn", "text": "Did the call happen?"}
    meeting = f"Call on {lead['meeting_at'].astimezone(tz).strftime('%a')} {short_clock(lead['meeting_at'].astimezone(tz))}" \
        if state in ("soon", "upcoming") else None
    if state == "soon":
        return {"tone": "", "text": meeting}
    if nxt and (not meeting or nxt < lead["meeting_at"]):
        return {"tone": "", "text": f"{label} · {_when_words(nxt, now, tz)}"}
    if meeting:
        return {"tone": "", "text": meeting}
    if state == "unscheduled":
        return {"tone": "", "text": "Call booked, time not set"}
    if lead.get("status") == "new" and lead.get("call_attempts") and not lead.get("ever_reached"):
        return {"tone": "", "text": f"Tried {lead['call_attempts']}×"}
    return None


def queue(leads, now, tz):
    """Today's lead rows, ranked: 0 never-tried New lead under an hour · 1 booked call within the hour ·
    2 never-tried New lead waiting longer · 3 overdue follow-up · 4 did the call happen · 5 due later today.
    Each lead once, in its lowest bucket; test leads and closed leads left out."""
    end_of_day = _local_at(now.astimezone(tz).date() + timedelta(days=1), 0, tz)
    rows = []
    for l in leads:
        if not is_open(l):
            continue
        found = []
        if waiting(l):
            fresh = now - l["created_time"] < timedelta(minutes=60)
            found.append((0 if fresh else 2, l["created_time"], "call"))
        state = meeting_state(l, now)
        if state == "soon":
            found.append((1, l["meeting_at"], "meeting_soon"))
        elif state == "check":
            found.append((4, l["meeting_at"], "meeting_check"))
        nxt = l.get("next_step_at")
        if nxt and nxt <= now:
            found.append((3, nxt, "overdue"))
        elif nxt and nxt < end_of_day:
            found.append((5, nxt, "later"))
        if found:
            bucket, at, kind = min(found, key=lambda f: f[0])
            rows.append({"id": l["id"], "bucket": bucket, "at": at, "kind": kind, "lead": l})
    # Leads that look like junk (L2) wait behind the real ones inside their bucket.
    return sorted(rows, key=lambda r: (r["bucket"], bool(r["lead"].get("junk_flags")) and not r["lead"].get("junk_dismissed"), r["at"], r["id"]))


def call_stats(rows):
    live = [r for r in rows if not r.get("undone")]
    talked = sum(1 for r in live if r["outcome"] in REACHED)
    return {"calls": len(live), "talked": talked, "rate": round(100 * talked / len(live)) if live else None,
            "booked": sum(1 for r in live if r["outcome"] == "booked")}


def reminder_due(lead, now):
    """A next step reached its time (within a day) on an open lead."""
    at = lead.get("next_step_at")
    return bool(at) and is_open(lead) and at <= now < at + REMIND_FOR


def due_text(lead, tz):
    """The follow-up reminder: 'Call back Maria Lopez: due 3:00 PM' and what a call needs."""
    import replies
    title = f"{next_words(lead.get('next_step_kind'), lead.get('next_step_text'))} {_name(lead)}: due {words.clock(lead['next_step_at'].astimezone(tz))}"
    lines = [lead.get("business_type") or "Business not given"]
    if lead.get("phone"):
        lines.append(f"Phone: {replies.phone_display(lead['phone'])}")
    if lead.get("last_outcome") and lead.get("last_call_at"):
        lines.append(f"Last try: {OUTCOME_WORDS[lead['last_outcome']]}, {lead['last_call_at'].astimezone(tz).strftime('%a')} {words.clock(lead['last_call_at'].astimezone(tz))}")
    return title, lines


def _wait(lead, now):
    minutes = int((now - lead["created_time"]).total_seconds() // 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h"


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def digest_text(waiting_leads, due, calls_today, now, tz):
    """The 8 AM message: who waits for a first call, follow-ups due or overdue, and today's booked calls.
    None when there is nothing (nothing is sent)."""
    parts, lines = [], []
    if waiting_leads:
        parts.append(_count(len(waiting_leads), "lead waiting for a first call", "leads waiting for a first call"))
        lines += [f"{_name(l)}{', ' + l['business_type'] if l.get('business_type') else ''}: waiting {_wait(l, now)}" for l in waiting_leads]
    if due:
        parts.append(_count(len(due), "follow-up due", "follow-ups due"))
        for l in due:
            at = l["next_step_at"]
            when = f"overdue since {at.astimezone(tz).strftime('%a')}" if at.astimezone(tz).date() < now.astimezone(tz).date() \
                else f"due {words.clock(at.astimezone(tz))}"
            lines.append(f"{next_words(l.get('next_step_kind'), l.get('next_step_text'))} {_name(l)}: {when}")
    if calls_today:
        parts.append(_count(len(calls_today), "booked call", "booked calls"))
        lines += [f"Call at {words.clock(l['meeting_at'].astimezone(tz))}: {_name(l)}" for l in calls_today]
    if not parts:
        return None
    return "Today: " + ", ".join(parts), lines


def due_where(due, now, tz, alias="l"):
    """The ?due= filter of the leads list: (SQL, params). today = due on the account's today; overdue = past due;
    none = open leads already tried with no next step and no call booked; booked = a call was ever booked. A repeat
    is never followed up on its own (one linked after it was worked keeps its old step), so none of them list it."""
    a = alias
    open_sql = f"{a}.repeat_of IS NULL AND {a}.status IN ('new', 'contacted', 'qualified')"
    if due == "today":
        day = now.astimezone(tz).date()
        return f"{open_sql} AND {a}.next_step_at >= %s AND {a}.next_step_at < %s", [_local_at(day, 0, tz), _local_at(day + timedelta(days=1), 0, tz)]
    if due == "overdue":
        return f"{open_sql} AND {a}.next_step_at <= %s", [now]
    if due == "none":
        return (f"{open_sql} AND {a}.next_step_at IS NULL AND {a}.meeting_status IS DISTINCT FROM 'scheduled' "
                f"AND ({a}.first_contacted_at IS NOT NULL OR {a}.status <> 'new')"), []
    if due == "booked":
        return f"{a}.repeat_of IS NULL AND {a}.booked_at IS NOT NULL", []
    return None, []


# ---------------------------------------------------------------- database

FOLLOW_COLUMNS = ("call_attempts", "unanswered_streak", "ever_reached", "last_call_at", "last_outcome", "next_step_kind",
                  "next_step_text", "next_step_at", "next_step_by", "booked_at", "meeting_at", "meeting_status", "booking_source")
NEXT_COLS = ("next_step_kind", "next_step_text", "next_step_at", "next_step_by")
MEETING_COLS = ("booked_at", "meeting_at", "meeting_status", "booking_source")


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _snapshot(lead, cols):
    return {c: _iso(lead.get(c)) for c in cols}


def rel_words(dt, now, tz):
    """'today 4:00 PM', 'tomorrow 9:00 AM', else 'Thu, Nov 13, 2:00 PM'."""
    local, today = dt.astimezone(tz), now.astimezone(tz).date()
    if local.date() == today:
        return f"today {words.clock(local)}"
    if local.date() == today + timedelta(days=1):
        return f"tomorrow {words.clock(local)}"
    return words.day_time(local)


def state_for(lead, now, tz):
    """What the lead page's Follow-up box shows, its times worded in the account's time zone."""
    summary = {k: lead.get(k) for k in ("call_attempts", "unanswered_streak", "ever_reached", "last_call_at", "last_outcome")}
    if lead.get("last_call_at"):
        summary["last_words"] = f"{OUTCOME_WORDS.get(lead.get('last_outcome'), 'called')}, {_when_words(lead['last_call_at'], now, tz)}"
    nxt = None
    if lead.get("next_step_at"):
        nxt = {"kind": lead["next_step_kind"], "text": lead.get("next_step_text"), "at": lead["next_step_at"],
               "words": next_words(lead["next_step_kind"], lead.get("next_step_text")), "overdue": lead["next_step_at"] <= now,
               "when": rel_words(lead["next_step_at"], now, tz), "short": _when_words(lead["next_step_at"], now, tz)}
    meeting = None
    if lead.get("meeting_status"):
        at = lead.get("meeting_at")
        meeting = {"at": at, "status": lead["meeting_status"], "state": meeting_state(lead, now),
                   "source": lead.get("booking_source"), "booked_at": lead.get("booked_at"),
                   "when": words.day_time(at, tz) if at else None, "short": _when_words(at, now, tz) if at else None,
                   "on": _on_words(at, now, tz) if at else None}
    return {"summary": summary, "next": nxt, "meeting": meeting, "open": is_open(lead) or (lead.get("status") in OPEN),
            "suggestion": lost_suggestion({"unanswered_streak": lead.get("unanswered_streak") or 0, "ever_reached": lead.get("ever_reached")}, lead.get("status")),
            "chip": chip(lead, now, tz), "presets": presets(now, tz), "lost_notes": LOST_NOTES}


def _db():
    import db
    return db


def tracks_bookings():
    """Whether this account has ever booked a call with a real lead: booked figures, columns and the report step
    show only then."""
    return bool(_db().query("SELECT EXISTS (SELECT 1 FROM leads WHERE booked_at IS NOT NULL AND NOT is_test) AS yes", one=True)["yes"])


def _fingerprint(lead_id):
    row = _db().query("SELECT COUNT(*) AS n, COUNT(undone_at) AS u FROM lead_events WHERE lead_id = %s AND kind = 'call'", (lead_id,), one=True)
    return int(row["n"]), int(row["u"])


def recount(lead_id, recheck_contact=False):
    """Rebuild the call counters from the lead's events (idempotent; a write that raced this one is caught by the
    event count and counted again). recheck_contact: an undone event made the first contact, so the first try is
    worked out again from what is left (calls, stage moves out of New, emails sent by hand)."""
    db = _db()
    for _ in range(3):
        n, u = _fingerprint(lead_id)
        events = db.query("SELECT kind, outcome, at, details, undone_at FROM lead_events WHERE lead_id = %s AND kind IN ('call', 'stage')", (lead_id,))
        s = call_summary([e for e in events if e["kind"] == "call"])
        sets = ["call_attempts = %s", "unanswered_streak = %s", "ever_reached = %s", "last_call_at = %s", "last_outcome = %s"]
        params = [s["attempts"], s["unanswered_streak"], s["ever_reached"], s["last_call_at"], s["last_outcome"]]
        if recheck_contact:
            emails = [r["sent_at"] for r in db.query("SELECT sent_at FROM lead_replies WHERE lead_id = %s AND status = 'sent' AND NOT auto", (lead_id,))]
            sets.append("first_contacted_at = %s")
            params.append(first_contact_at([e for e in events if e["kind"] == "call"], [e for e in events if e["kind"] == "stage"], emails))
        done = db.execute(
            f"""UPDATE leads SET {', '.join(sets)} WHERE id = %s
                AND (SELECT COUNT(*) FROM lead_events WHERE lead_id = %s AND kind = 'call') = %s
                AND (SELECT COUNT(undone_at) FROM lead_events WHERE lead_id = %s AND kind = 'call') = %s RETURNING id""",
            params + [lead_id, lead_id, n, lead_id, u], returning=True)
        if done:
            return s
    return s


def _record(lead_id, kind, user, **kw):
    import lead_history
    return lead_history.record(lead_id, kind, user_id=user["id"] if user else None, actor=kw.pop("actor", None) or ("user" if user else "system"), **kw)


def set_next(lead, user, nxt):
    _db().execute("UPDATE leads SET next_step_kind = %s, next_step_text = %s, next_step_at = %s, next_step_by = %s WHERE id = %s",
                  (nxt["kind"], nxt["text"], nxt["at"], user["id"] if user else None, lead["id"]))
    return _record(lead["id"], "next_set", user, details={"next_kind": nxt["kind"], "next_text": nxt["text"], "next_at": _iso(nxt["at"])})


def done_next(lead, user):
    if not lead.get("next_step_at"):
        return None
    _db().execute("UPDATE leads SET next_step_kind = NULL, next_step_text = NULL, next_step_at = NULL, next_step_by = NULL WHERE id = %s", (lead["id"],))
    return _record(lead["id"], "next_done", user, details={"next_kind": lead["next_step_kind"], "next_text": lead.get("next_step_text"),
                                                           "next_at": _iso(lead["next_step_at"])})


def clear_next(lead, user, reason="removed", status=None):
    """reason 'closed': the lead went to Won or Lost, so the system closes its step."""
    if not lead.get("next_step_at"):
        return None
    _db().execute("UPDATE leads SET next_step_kind = NULL, next_step_text = NULL, next_step_at = NULL, next_step_by = NULL WHERE id = %s", (lead["id"],))
    closed = reason == "closed"
    return _record(lead["id"], "next_cleared", None if closed else user, actor="system" if closed else None,
                   details={"next_kind": lead["next_step_kind"], "next_text": lead.get("next_step_text"), "reason": reason, "status": status})


def set_meeting(lead, user, at, source="manual"):
    """Mark a call booked (or move it). The first booking time stays (the cost per booked call cohort)."""
    moved = lead.get("meeting_status") == "scheduled"
    _db().execute("""UPDATE leads SET booked_at = COALESCE(booked_at, now()), meeting_at = %s, meeting_status = 'scheduled',
                         booking_source = COALESCE(booking_source, %s) WHERE id = %s""", (at, source, lead["id"]))
    if moved:
        return _record(lead["id"], "call_moved", user, details={"meeting_at": _iso(at), "from": _iso(lead.get("meeting_at"))})
    return _record(lead["id"], "booked", user, details={"meeting_at": _iso(at), "source": source})


MEETING_EVENTS = {"held": "call_held", "no_show": "no_show", "canceled": "call_canceled"}


def meeting_outcome(lead, user, status):
    if status not in MEETING_EVENTS:
        raise Problem("Pick what happened to the call", "meeting")
    if not lead.get("meeting_status"):
        raise Problem("No call is booked for this lead", "meeting")
    _db().execute("UPDATE leads SET meeting_status = %s WHERE id = %s", (status, lead["id"]))
    return _record(lead["id"], MEETING_EVENTS[status], user, details={"meeting_at": _iso(lead.get("meeting_at"))})


def remove_meeting(lead, user):
    if not lead.get("meeting_status"):
        return None
    _db().execute("UPDATE leads SET booked_at = NULL, meeting_at = NULL, meeting_status = NULL, booking_source = NULL WHERE id = %s", (lead["id"],))
    return _record(lead["id"], "booking_removed", user, details={"before": _snapshot(lead, MEETING_COLS)})


def record_call(lead, user, outcome, note=None, meeting=None, nxt=None):
    """One call: its event, the booked call it set, the first try, the next step. Returns the call event id.
    `meeting` is the call's time (UTC or None for "not sure yet") when the outcome is booked."""
    db = _db()
    import lead_history
    note = (note or "").strip()[:2000] or None
    details = {"first_contact": lead.get("first_contacted_at") is None,
               "before": {**_snapshot(lead, NEXT_COLS), **_snapshot(lead, MEETING_COLS)}}
    if note:
        details["note"] = note
    if outcome == "booked":
        details["meeting_at"] = _iso(meeting)
    if nxt:
        details["next"] = {"kind": nxt["kind"], "text": nxt["text"], "at": _iso(nxt["at"])}
    event_id = lead_history.record(lead["id"], "call", outcome=outcome, details=details, user_id=user["id"])
    db.execute("UPDATE leads SET first_contacted_at = COALESCE(first_contacted_at, now()) WHERE id = %s", (lead["id"],))
    if outcome == "booked":
        db.execute("""UPDATE leads SET booked_at = COALESCE(booked_at, now()), meeting_at = %s, meeting_status = 'scheduled',
                          booking_source = COALESCE(booking_source, 'call') WHERE id = %s""", (meeting, lead["id"]))
    if note:
        db.execute("INSERT INTO lead_notes (lead_id, user_id, body) VALUES (%s, %s, %s)", (lead["id"], user["id"], note))
    if nxt:
        set_next(lead, user, nxt)
    recount(lead["id"])
    return event_id


def undo_call(lead, event, user):
    """Take a call back: its event is marked undone; the next step and booked call it set go back to what they
    were, unless someone changed them since. Returns False when another click already took it back."""
    db = _db()
    if not db.execute("UPDATE lead_events SET undone_at = now(), undone_by = %s WHERE id = %s AND undone_at IS NULL RETURNING id",
                      (user["id"], event["id"]), returning=True):
        return False
    d = event.get("details") or {}
    before = d.get("before") or {}
    if d.get("next") and _iso(lead.get("next_step_at")) == d["next"]["at"]:
        db.execute("UPDATE leads SET next_step_kind = %s, next_step_text = %s, next_step_at = %s, next_step_by = %s WHERE id = %s",
                   tuple(before.get(c) for c in NEXT_COLS) + (lead["id"],))
        db.execute("""UPDATE lead_events SET undone_at = now(), undone_by = %s WHERE lead_id = %s AND kind = 'next_set'
                      AND undone_at IS NULL AND at >= %s AND details->>'next_at' = %s""", (user["id"], lead["id"], event["at"], d["next"]["at"]))
    if event.get("outcome") == "booked" and _iso(lead.get("meeting_at")) == d.get("meeting_at"):
        db.execute("UPDATE leads SET booked_at = %s, meeting_at = %s, meeting_status = %s, booking_source = %s WHERE id = %s",
                   tuple(before.get(c) for c in MEETING_COLS) + (lead["id"],))
    recount(lead["id"], recheck_contact=bool(d.get("first_contact")))
    return True
