"""A lead's history (L1): the one writer and reader of `lead_events`, which is never pruned.

`describe`, `undo_text` and `undo_plan` are pure. A stage event's details carry what Undo needs: `from`, `to`,
`changed_before` (the old status_changed_at), `first_contact` (this move was the first try) and `crm` (the stages
it queued for Meta). A call's details carry its note, the booked call's time, the next step it set and what the
lead had `before`, so taking it back restores them. Undo marks an event, it never deletes one.
"""
import json
from datetime import datetime, timedelta

import words

UNDO_MINUTES = 10
UNDOABLE = ("call", "stage")
KINDS = ("received", "call", "stage", "owner", "note", "email", "email_auto", "alert_failed",
         "next_set", "next_done", "next_cleared",
         "booked", "call_moved", "call_canceled", "call_held", "no_show", "booking_removed",
         "lost_reason", "max_stage", "repeat", "returning", "linked", "unlinked", "not_junk")
STAGE_WORDS = {"new": "New", "contacted": "Contacted", "qualified": "Qualified", "won": "Won", "lost": "Lost"}
OUTCOME_WORDS = {"reached": "talked to them", "no_answer": "no answer", "voicemail": "left a voicemail",
                 "wrong_number": "wrong number", "booked": "booked a call"}
NEXT_WORDS = {"call_back": "Call back", "proposal": "Send a quote", "follow_up": "Follow up"}
# Settings → Activity keeps its old words for the kinds it already listed.
ACTIVITY = {"received": "lead.received", "stage": "lead.status", "owner": "lead.owner", "email": "lead.reply",
            "email_auto": "lead.reply_auto", "alert_failed": "lead.email_failed"}
NOTE_CHARS = 80


def stage(s):
    return STAGE_WORDS.get(s, str(s or "").capitalize())


def _time(value, tz):
    if not value:
        return None
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return words.day_time(dt, tz)


def _next(d):
    kind = d.get("next_kind")
    return (d.get("next_text") or "Something else") if kind == "other" else NEXT_WORDS.get(kind, "Follow up")


def _reason(key):
    import lead_quality
    return lead_quality.REASON_LABELS.get(key, str(key))


def _quoted(note):
    if not note:
        return ""
    return f" · ‘{note[:NOTE_CHARS].rstrip() + '…' if len(note) > NOTE_CHARS else note}’"


def describe(ev, tz, names=None):
    """One plain sentence per event. names: {user id: name} for people named by id only."""
    names = names or {}
    d = ev.get("details") or {}
    who = ev.get("who") or ("Meta" if ev.get("actor") == "meta" else "Someone")
    kind = ev.get("kind")
    if kind == "received":
        text = f"Received from Meta ({d['ad']})" if d.get("ad") else "Received from Meta"
    elif kind == "call":
        outcome = ev.get("outcome")
        if outcome == "booked":
            at = _time(d.get("meeting_at"), tz)
            what = f"booked a call for {at}" if at else "booked a call, time not set"
        else:
            what = OUTCOME_WORDS.get(outcome, "called")
        note = d.get("note") or ""
        if len(note) > NOTE_CHARS:
            note = note[:NOTE_CHARS].rstrip() + "…"
        text = f"{who} called: {what}" + (f" · ‘{note}’" if note else "")
    elif kind == "stage":
        reason = f" ({_reason(d['reason'])})" if d.get("reason") else ""
        text = f"{who} moved it from {stage(d.get('from'))} to {stage(d.get('to'))}{reason}" + (f": {d['note']}" if d.get("note") else "")
    elif kind == "lost_reason":
        text = f"{who} changed why it was lost: {_reason(d.get('to')) if d.get('to') else 'no reason given'}" + _quoted(d.get("note"))
    elif kind == "max_stage":
        text = f"{who} corrected how far it got: {stage(d.get('from'))} → {stage(d.get('to'))}"
    elif kind == "repeat":
        text = "They asked again: the new request is linked here" if d.get("repeat") else "Asked again: linked to their first lead"
    elif kind == "returning":
        text = "Asked before: linked to their earlier lead"
    elif kind == "linked":
        text = f"{who} linked a later lead from the same person" if d.get("repeat") else f"{who} marked it as the same person as an earlier lead"
    elif kind == "unlinked":
        text = f"{who} said it's not the same person"
    elif kind == "not_junk":
        text = f"{who} marked it as real, not junk"
    elif kind == "owner":
        to_id = d.get("to_id", d.get("owner_id"))
        if to_id:
            text = f"{who} gave it to {d.get('to_name') or d.get('owner_name') or names.get(to_id) or 'someone who has left'}"
        elif d.get("from_name") or names.get(d.get("from_id")):
            text = f"{who} took {d.get('from_name') or names.get(d.get('from_id'))} off it"
        else:
            text = f"{who} took the owner off"
    elif kind == "note":
        text = f"{who} added a note"
    elif kind == "email":
        text = f"{who} emailed them: {d.get('subject', '')}"
    elif kind == "email_auto":
        text = f"Automatic reply sent: {d.get('subject', '')}"
    elif kind == "alert_failed":
        text = "The new-lead email to the team couldn't be sent"
    elif kind == "next_set":
        text = f"Next step: {_next(d)}, {_time(d.get('next_at'), tz)}"
    elif kind == "next_done":
        text = f"Done: {_next(d)}"
    elif kind == "next_cleared":
        text = f"Next step closed: lead is {stage(d.get('status'))}" if d.get("reason") == "closed" else f"{who} removed the next step"
    elif kind == "booked":
        at = _time(d.get("meeting_at"), tz)
        text = f"{who} marked a call booked for {at}" if at else f"{who} marked a call booked, time not set"
    elif kind == "call_moved":
        at = _time(d.get("meeting_at"), tz)
        text = f"Call moved to {at}" if at else "Call moved, time not set"
    elif kind == "call_canceled":
        text = "Call canceled"
    elif kind == "call_held":
        text = "The call happened"
    elif kind == "no_show":
        text = "No-show"
    elif kind == "booking_removed":
        text = f"{who} removed the booked call"
    else:
        w = str(kind or "").replace("_", " ").strip()
        text = w[:1].upper() + w[1:] if w else "Changed"
    return text + (" (undone)" if ev.get("undone_at") else "")


def undo_text(ev):
    """The line for putting an event back, shown at the time it was put back."""
    who = ev.get("undone_who") or "Someone"
    if ev.get("kind") == "call":
        return f"{who} took back the call"
    return f"{who} undid the move to {stage((ev.get('details') or {}).get('to'))}"


def _refuse(code, error):
    return {"ok": False, "code": code, "error": error}


def undo_plan(event, latest_stage_event_id, user_id, now):
    """What putting this call or stage move back restores, or why it can't be. The same person, within ten
    minutes; a stage move only while it is still the lead's last move."""
    d = event.get("details") or {}
    kind = event.get("kind")
    if kind not in UNDOABLE:
        return _refuse(400, "Only a call or a stage move can be undone")
    if event.get("undone_at"):
        return _refuse(409, "That was already undone")
    if event.get("user_id") != user_id:
        return _refuse(403, "Only the person who did it can undo it")
    if now - event["at"] >= timedelta(minutes=UNDO_MINUTES):
        return _refuse(409, "Too late to undo: log another call instead" if kind == "call" else "Too late to undo: move it back by hand")
    if kind == "call":
        return {"ok": True, "kind": "call", "first_contact": bool(d.get("first_contact"))}
    if event["id"] != latest_stage_event_id:
        return _refuse(409, "It has moved again since: move it back by hand")
    return {"ok": True, "kind": "stage", "status": d.get("from"), "to": d.get("to"), "status_changed_at": d.get("changed_before"),
            "first_contact": bool(d.get("first_contact")), "crm": list(d.get("crm") or [])}


# ---------------------------------------------------------------- database

def record(lead_id, kind, *, outcome=None, details=None, ref_id=None, actor=None, user_id=None, at=None, mirror=True):
    """Add an event to the lead's history; mirrored to `activity` (Settings → Activity). Returns its id."""
    import db
    from util import log_activity
    if user_id is None and actor in (None, "user"):
        try:
            from flask import session
            user_id = session.get("user_id")
        except RuntimeError:
            user_id = None
    actor = actor or ("user" if user_id else "system")
    row = db.execute(
        "INSERT INTO lead_events (lead_id, kind, outcome, details, ref_id, actor, user_id, at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now())) RETURNING id",
        (lead_id, kind, outcome, json.dumps(details or {}), ref_id, actor, user_id, at), returning=True)
    if mirror:
        log_activity(ACTIVITY.get(kind, f"lead.{kind}"), subject=str(lead_id), actor=actor, user_id=user_id,
                     details={**(details or {}), **({"outcome": outcome} if outcome else {}), "event_id": row["id"]})
    return row["id"]


def gap_line(created_time, kept_from, tz):
    """'History before May 16, 2026 was not kept.' for a lead older than the backfill window, else None."""
    if not kept_from or created_time >= kept_from:
        return None
    local = kept_from.astimezone(tz)
    return f"History before {local.strftime('%b')} {local.day}, {local.year} was not kept."


_KEPT_FROM = []


def kept_from():
    """Migration 039 copied 180 days of activity into lead_events; nothing older exists anywhere now."""
    if not _KEPT_FROM:
        import db
        row = db.query("SELECT applied_at FROM schema_migrations WHERE filename = '039_followups.sql'", one=True)
        _KEPT_FROM.append(row["applied_at"] - timedelta(days=180) if row else None)
    return _KEPT_FROM[0]


def events(lead_id):
    import db
    return db.query(
        """SELECT e.id, e.at, e.kind, e.outcome, e.details, e.actor, e.user_id, e.ref_id, e.undone_at, e.undone_by,
                  u.name AS who, v.name AS undone_who
           FROM lead_events e LEFT JOIN users u ON u.id = e.user_id LEFT JOIN users v ON v.id = e.undone_by
           WHERE e.lead_id = %s ORDER BY e.at, e.id""", (lead_id,))


def for_lead(lead, tz, rows=None):
    """The History list, newest first: {id, at, kind, text, undone, undo}. A lead stored without a `received`
    event (dev seed, QA) still starts with one."""
    import db
    rows = events(lead["id"]) if rows is None else rows
    ids = {(r["details"] or {}).get(k) for r in rows if r["kind"] == "owner" for k in ("to_id", "owner_id", "from_id")} - {None}
    names = {u["id"]: u["name"] for u in db.query("SELECT id, name FROM users WHERE id = ANY(%s)", (list(ids),))} if ids else {}
    out = [{"id": r["id"], "at": r["at"], "kind": r["kind"], "text": describe(r, tz, names), "undone": bool(r["undone_at"])} for r in rows]
    out += [{"id": None, "at": r["undone_at"], "kind": "undo", "text": undo_text(r), "undone": False}
            for r in rows if r["undone_at"] and r["kind"] in UNDOABLE]
    if not any(r["kind"] == "received" for r in rows):
        out.append({"id": None, "at": lead["created_time"], "kind": "received",
                    "text": describe({"kind": "received", "details": {"ad": lead.get("ad_name")}}, tz), "undone": False})
    return sorted(out, key=lambda h: (h["at"], h["id"] or 0), reverse=True)
