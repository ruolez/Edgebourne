"""A lead's history in plain sentences, and putting a stage move back (Undo).

`describe` and `undo_plan` are pure. A stage move is an `activity` row `lead.status` whose details carry
what Undo needs: `from`, `to`, `changed_before` (the old status_changed_at), `first_contact` (this move
was the first contact) and `crm` (the stages it queued for Meta). L1 moves this onto `lead_events`.
"""
from datetime import datetime, timedelta

UNDO_MINUTES = 10
STAGE_WORDS = {"new": "New", "contacted": "Contacted", "qualified": "Qualified", "won": "Won", "lost": "Lost"}


def stage(s):
    return STAGE_WORDS.get(s, str(s or "").capitalize())


def describe(row, names):
    """One line of history. names: {user id: name} for owners named by id only."""
    d = row.get("details") or {}
    who = row.get("who") or ("Meta" if row.get("actor") == "meta" else "Someone")
    action = row.get("action") or ""
    if action == "lead.received":
        return "Arrived from Meta"
    if action == "lead.status":
        return f"{who} moved it from {stage(d.get('from'))} to {stage(d.get('to'))}" + (" (undone)" if d.get("undone") else "")
    if action == "lead.status_undone":
        return f"{who} undid the move to {stage(d.get('from'))}"
    if action == "lead.owner":
        if not d.get("owner_id"):
            return f"{who} took the owner off"
        return f"{who} gave it to {d.get('owner_name') or names.get(d['owner_id']) or 'someone who has left'}"
    if action == "lead.reply":
        return f"{who} emailed them: {d.get('subject', '')}"
    if action == "lead.reply_auto":
        return f"Automatic reply sent: {d.get('subject', '')}"
    if action == "lead.email_failed":
        return "The alert email to the team couldn't be sent"
    words = action.removeprefix("lead.").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Changed"


def _refuse(code, error):
    return {"ok": False, "code": code, "error": error}


def undo_plan(event, latest_stage_event_id, user_id, now):
    """What putting this stage move back restores, or why it can't be."""
    d = event.get("details") or {}
    if event.get("action") != "lead.status":
        return _refuse(400, "Only a stage move can be undone")
    if d.get("undone"):
        return _refuse(409, "That move was already undone")
    if event.get("user_id") != user_id:
        return _refuse(403, "Only the person who moved it can undo that")
    if now - event["at"] >= timedelta(minutes=UNDO_MINUTES):
        return _refuse(409, "Too late to undo: move it back by hand")
    if event["id"] != latest_stage_event_id:
        return _refuse(409, "It has moved again since: move it back by hand")
    return {"ok": True, "status": d.get("from"), "to": d.get("to"), "status_changed_at": d.get("changed_before"),
            "clear_first_contact": bool(d.get("first_contact")), "crm": list(d.get("crm") or [])}


def parse_time(value):
    return datetime.fromisoformat(value) if value else None
