import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import account_info
import crm_events
import db
import followup
import jobs
import lead_history
import lead_quality as lq
import lead_quality_store
import leads
import mailer
import reminders
import replies
import today
from auth import admin_required, current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("leads", __name__, url_prefix="/api/leads")

STATUSES = ("new", "contacted", "qualified", "won", "lost")
DUE = ("today", "overdue", "none", "booked")
# What a client may change when Settings → Client access lets them work leads (00-PLAN C12).
CLIENT_FIELDS = {"status", "lost_reason", "lost_note", "next_step", "next_step_done", "meeting"}

LIST_COLUMNS = """l.id, l.created_time, l.full_name, l.email, l.phone, l.business_type,
                  l.ad_name, l.campaign_id, l.campaign_name, l.status, l.owner_id, l.is_test, l.is_organic,
                  l.first_contacted_at, l.emailed_at, l.status_changed_at, l.call_attempts, l.ever_reached,
                  l.next_step_kind, l.next_step_text, l.next_step_at, l.booked_at, l.meeting_at, l.meeting_status,
                  l.max_stage, l.lost_reason, l.repeat_of, l.earlier_lead_id, l.junk_flags, l.junk_dismissed, l.form_id,
                  (SELECT COUNT(*) FROM leads r WHERE r.repeat_of = l.id) AS repeats,
                  u.name AS owner_name"""
REPEAT_REFUSED = "This lead is a repeat of another lead; change the stage there"
REPEAT_WORK_REFUSED = "This lead is a repeat of another lead; log calls and next steps on that one"


def _scope(user, alias="l"):
    ids = visible_campaign_ids(user)
    if ids is None:
        return "TRUE", []
    return f"{alias}.campaign_id = ANY(%s)", [ids]


def _get_visible(lead_id, user):
    where, params = _scope(user)
    return db.query(
        f"SELECT l.*, u.name AS owner_name, s.name AS adset_name FROM leads l LEFT JOIN users u ON u.id = l.owner_id "
        f"LEFT JOIN adsets s ON s.id = l.adset_id "
        f"WHERE l.id = %s AND {where}",
        [lead_id] + params, one=True,
    )


@bp.get("")
@login_required
def list_leads():
    user = current_user()
    where, params = _scope(user)
    clauses = [where]
    status = request.args.get("status")
    if status in STATUSES:
        clauses.append("l.status = %s")
        params.append(status)
    elif status == "open":
        clauses.append("l.status IN ('new', 'contacted', 'qualified')")
    if status in STATUSES or status == "open":
        clauses.append("l.repeat_of IS NULL")   # a repeat is listed (muted) only under All; its first lead says "Asked 2×"
    why = request.args.get("why")
    if status == "lost" and why in lq.REASON_KEYS:
        clauses.append("l.lost_reason = %s")
        params.append(why)
    elif status == "lost" and why == "none":
        clauses.append("l.lost_reason IS NULL")
    if request.args.get("tests") != "1":
        clauses.append("NOT l.is_test")
    source_clauses, source_params = leads.source_filter(request.args)
    clauses += source_clauses
    params += source_params
    q = (request.args.get("q") or "").strip()
    if q:
        clauses.append("(l.full_name ILIKE %s OR l.email ILIKE %s OR l.phone ILIKE %s "
                       "OR l.business_type ILIKE %s)")
        params += [f"%{q}%"] * 4
    now, tz = datetime.now(timezone.utc), account_info.tz()
    due = request.args.get("due")
    if due in DUE:
        due_sql, due_params = followup.due_where(due, now, tz)
        clauses.append(due_sql)
        params += due_params
    # Follow-ups list what comes due first; everything else the newest lead first.
    order = {"today": "l.next_step_at", "overdue": "l.next_step_at", "booked": "l.meeting_at DESC NULLS LAST"}.get(due, "l.created_time DESC")
    rows = db.query(
        f"SELECT {LIST_COLUMNS} FROM leads l LEFT JOIN users u ON u.id = l.owner_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY {order}, l.created_time DESC LIMIT 500",
        params,
    )
    for r in rows:
        r["urgency"] = today.urgency(r, now)  # the same rule as Today and the reminders
        r["chip"] = followup.chip(r, now, tz)
        r["junk"] = lq.is_junk(r)  # the one junk rule; the page shows the chip from this
    # The stage chips count the same source as the list (a campaign, ad set, ad or form), so a link that
    # narrows the list shows numbers that add up to what it lists.
    # The nav badge still counts every new lead (`everywhere`).
    source_sql = " AND ".join(source_clauses) or "TRUE"
    counts = db.query(
        f"""SELECT l.status, COUNT(*) FILTER (WHERE {source_sql}) AS n, COUNT(*) AS everywhere
            FROM leads l WHERE {where} AND {lq.counted()} GROUP BY l.status""",
        source_params + _scope(user)[1],
    )
    sources = db.query(
        f"""SELECT l.campaign_id, MAX(l.campaign_name) AS campaign_name, l.ad_id, MAX(l.ad_name) AS ad_name, COUNT(*) AS n
            FROM leads l WHERE {where} AND {lq.counted()} AND l.campaign_id IS NOT NULL
            GROUP BY l.campaign_id, l.ad_id ORDER BY 2, 4""", _scope(user)[1])
    # A repeat is listed under All (muted) but counts in no stage: the All chip counts it so it adds up to the list.
    repeats = db.query(f"""SELECT COUNT(*) AS n FROM leads l WHERE {where} AND NOT l.is_test AND l.repeat_of IS NOT NULL AND {source_sql}""",
                       _scope(user)[1] + source_params, one=True)["n"]
    why_counts = None
    if status == "lost":
        why_counts = {r["k"]: int(r["n"]) for r in db.query(
            f"""SELECT COALESCE(l.lost_reason, 'none') AS k, COUNT(*) AS n FROM leads l
                WHERE {where} AND {lq.counted()} AND l.status = 'lost' AND {source_sql} GROUP BY 1""", _scope(user)[1] + source_params)}
    return jsonify({"leads": rows, "counts": {r["status"]: r["n"] for r in counts}, "why_counts": why_counts, "repeats": int(repeats),
                    "new_everywhere": next((r["everywhere"] for r in counts if r["status"] == "new"), 0), "sources": sources,
                    "narrowed": _narrowed(request.args, user), "response": reminders.stats(*_scope(user)),
                    "follow": follow_counts(user, now, tz)})


def follow_counts(user, now, tz):
    """How many leads each follow-up filter holds (test leads left out)."""
    where, params = _scope(user)
    parts, args = [], []
    for key in DUE:
        sql, p = followup.due_where(key, now, tz)
        parts.append(f"COUNT(*) FILTER (WHERE {sql}) AS {key}")
        args += p
    row = db.query(f"SELECT {', '.join(parts)} FROM leads l WHERE {where} AND {lq.counted()}", args + params, one=True)
    return {"due_today": int(row["today"]), "overdue": int(row["overdue"]), "no_next": int(row["none"]), "booked": int(row["booked"])}


def _narrowed(args, user):
    """The ad set or form the list is narrowed to, by name (the campaign / ad picker can't show those)."""
    named = leads.source_named(args)
    if not named:
        return None
    kind, ref = named
    where, params = _scope(user)
    if kind == "adset":
        row = db.query(f"SELECT name FROM adsets s WHERE s.id = %s AND {_scope(user, 's')[0]}", [ref] + params, one=True)
    else:
        row = db.query(f"""SELECT (array_agg(l.form_name ORDER BY l.created_time DESC) FILTER (WHERE l.form_name IS NOT NULL))[1] AS name
                            FROM leads l WHERE l.form_id = %s AND {where}""", [ref] + params, one=True)
    return {"kind": kind, "id": ref, "name": (row or {}).get("name")}


@bp.get("/<int:lead_id>")
@login_required
def get_lead(lead_id):
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    lead["notes"] = db.query(
        "SELECT n.id, n.body, n.created_at, u.name AS author FROM lead_notes n "
        "LEFT JOIN users u ON u.id = n.user_id WHERE n.lead_id = %s ORDER BY n.created_at",
        (lead_id,),
    )
    now, tz = datetime.now(timezone.utc), account_info.tz()
    lead["history"] = lead_history.for_lead(lead, tz)  # newest first, each line a sentence
    lead["history_gap"] = lead_history.gap_line(lead["created_time"], lead_history.kept_from(), tz)
    lead["urgency"] = today.urgency(lead, now)
    lead["follow"] = followup.state_for(lead, now, tz)
    lead["assignable"] = leads.staff_for(lead["campaign_id"])
    lead["meta_stages"] = crm_events.for_lead(lead_id) if crm_events.enabled() else None
    lead["replies"] = replies.for_lead(lead_id)
    _quality(lead, user, tz)
    return jsonify(lead)


def _quality(lead, user, tz):
    """L2 on the lead page: the person's other leads, why it looks like junk, the Lost reasons, who may correct."""
    lead["reasons"] = [{"value": k, "label": label, "hint": hint} for k, label, hint in lq.LOST_REASONS]
    lead["junk_text"] = lq.flag_text(lead.get("junk_flags") or []) if not lead.get("junk_dismissed") else ""
    lead["junk"] = lq.is_junk(lead)
    lead["can_correct"] = user["role"] == "admin"
    lead["family"] = None
    lead["earlier"] = None
    first = lead.get("repeat_of") or lead.get("earlier_lead_id")
    if first:
        root = _get_visible(first, user)
        if lead.get("repeat_of"):
            lead["family"] = {"can_see_root": bool(root), "root": {k: root[k] for k in (
                "id", "full_name", "created_time", "ad_name", "status", "max_stage", "owner_name")} if root else None}
        else:
            lead["earlier"] = ({"visible": True, **{k: root[k] for k in ("id", "created_time", "ad_name", "status", "lost_reason")},
                                "line": lq.asked_before(root, tz)} if root else {"visible": False})
    else:
        where, params = _scope(user, "r")
        rows = db.query(f"""SELECT r.id, r.created_time, r.ad_id, r.ad_name, r.answers FROM leads r
                            WHERE r.repeat_of = %s AND {where} ORDER BY r.created_time""", [lead["id"]] + params)
        hidden = db.query("SELECT COUNT(*) AS n FROM leads r WHERE r.repeat_of = %s", (lead["id"],), one=True)["n"] - len(rows)
        if rows or hidden:
            lead["family"] = {"repeats": rows, "hidden": hidden}
    # Unlinked after it arrived as a repeat: no automatic reply went out then, and none goes now.
    lead["no_auto_reply"] = bool(lead.get("repeat_checked") and lead.get("email")
                                 and not any(r.get("auto") for r in lead.get("replies") or [])
                                 and db.query("""SELECT 1 FROM lead_events WHERE lead_id = %s AND kind = 'repeat'
                                                  AND details->>'repeat' IS NULL""", (lead["id"],), one=True))


def _lead_body(lead_id, **extra):
    body = get_lead(lead_id).get_json()
    body.update(extra)
    return jsonify(body)


def _set_status(lead, status, reason=None, note=None):
    """Move the stage. Returns the history event's id (what Undo names), or None when nothing moved. Won or Lost
    closes the next step (its values are kept on the move, so Undo brings it back). The highest stage reached only
    rises (L2); a reason goes with Lost and leaves with it (the history keeps it)."""
    if status == lead["status"]:
        return None
    max_before = lead.get("max_stage") or "new"
    max_after = lq.raise_max(max_before, status)
    reason, note = (reason, note) if status == "lost" else (None, None)
    db.execute(
        """UPDATE leads SET status = %s, status_changed_at = now(),
               first_contacted_at = COALESCE(first_contacted_at,
                   CASE WHEN %s <> 'new' THEN now() END),
               max_stage = %s, max_stage_at = CASE WHEN %s THEN now() ELSE max_stage_at END,
               lost_reason = %s, lost_note = %s
           WHERE id = %s""",
        (status, status, max_after, max_after != max_before, reason, note, lead["id"]),
    )
    queued = crm_events.enqueue(lead["id"], status)
    before = lead.get("status_changed_at")
    details = {"from": lead["status"], "to": status, "changed_before": before.isoformat() if before else None,
               "first_contact": lead.get("first_contacted_at") is None and status != "new", "crm": queued,
               "max_before": max_before, "max_after": max_after,
               "reason_before": lead.get("lost_reason"), "note_before": lead.get("lost_note")}
    if reason:
        details["reason"] = reason
    if note:
        details["note"] = note
    closing = status in ("won", "lost") and lead.get("next_step_at")
    if closing:
        details["next_before"] = {c: (lead[c].isoformat() if isinstance(lead[c], datetime) else lead[c]) for c in followup.NEXT_COLS}
    event_id = lead_history.record(lead["id"], "stage", details=details)
    if closing:
        followup.clear_next(lead, None, reason="closed", status=status)
    if queued:
        jobs.wake()
    return event_id


def _problem(p):
    return api_error(str(p), 400, field=p.field)


@bp.patch("/<int:lead_id>")
@login_required
def update_lead(lead_id):
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    data = request.get_json(silent=True) or {}
    if user["role"] == "client" and set(data) - CLIENT_FIELDS:
        return api_error("Clients can move a lead's stage and log calls, nothing else", 403)
    now, tz = datetime.now(timezone.utc), account_info.tz()
    # Check everything before anything changes: a bad time never leaves half a change behind.
    if "status" in data and data["status"] not in STATUSES:
        return api_error("Pick one of: " + ", ".join(STATUSES), 400)
    if "status" in data and lead.get("repeat_of") and data["status"] != lead["status"]:
        return api_error(REPEAT_REFUSED, 409)
    # A repeat isn't worked on its own (no reminders, not counted): clearing what it had before it was linked is fine.
    if lead.get("repeat_of") and (data.get("next_step") or data.get("meeting") is not None):
        return api_error(REPEAT_WORK_REFUSED, 409)
    new_status = data.get("status", lead["status"])
    reason_change = ("lost_reason" in data or "lost_note" in data) and "status" not in data
    if reason_change and lead["status"] != "lost":
        return api_error("Only a lost lead has a reason", 400, field="lost_reason")
    # Changing only the note keeps the reason, and the other way round.
    asked = {k: data[k] if k in data else (lead.get(k) if reason_change else None) for k in ("lost_reason", "lost_note")}
    reason, lost_note, problem = lq.clean_lost(new_status, asked["lost_reason"], asked["lost_note"])
    if problem:
        return api_error(problem, 400, field="lost_reason")
    if "max_stage" in data:
        if user["role"] != "admin":
            return api_error("Only an admin can correct how far a lead got. Ask an admin to correct it", 403)
        if data["max_stage"] not in lq.FUNNEL:
            return api_error("Pick one of: " + ", ".join(lq.FUNNEL), 400, field="max_stage")
    nxt = meeting = None
    try:
        if data.get("next_step"):
            nxt = followup.clean_next(data["next_step"], tz, now)
        if isinstance(data.get("meeting"), dict) and "status" not in data["meeting"]:
            meeting = followup.clean_meeting(data["meeting"], tz, now)
    except followup.Problem as p:
        return _problem(p)
    owner = data.get("owner_id")
    staff = {}
    if "owner_id" in data:
        staff = {u["id"]: u["name"] for u in leads.staff_for(lead["campaign_id"])}
        if owner is not None and owner not in staff:
            return api_error("Pick someone who works on this lead's campaign", 400)
    moved = None
    if "status" in data:
        moved = _set_status(lead, data["status"], reason=reason, note=lost_note)
        lead = _get_visible(lead_id, user)
    if reason_change and (reason, lost_note) != (lead.get("lost_reason"), lead.get("lost_note")):
        db.execute("UPDATE leads SET lost_reason = %s, lost_note = %s WHERE id = %s AND status = 'lost'", (reason, lost_note, lead_id))
        lead_history.record(lead_id, "lost_reason", details={"from": lead.get("lost_reason"), "to": reason, "note": lost_note,
                                                             "note_before": lead.get("lost_note")})
    if "max_stage" in data and data["max_stage"] != lead.get("max_stage"):
        # A correction never touches what Meta was already sent.
        db.execute("UPDATE leads SET max_stage = %s, max_stage_at = now() WHERE id = %s", (data["max_stage"], lead_id))
        lead_history.record(lead_id, "max_stage", details={"from": lead.get("max_stage"), "to": data["max_stage"]})
    if "owner_id" in data and owner != lead["owner_id"]:
        db.execute("UPDATE leads SET owner_id = %s WHERE id = %s", (owner, lead_id))
        lead_history.record(lead_id, "owner", details={"to_id": owner, "to_name": staff.get(owner), "from_id": lead["owner_id"],
                                                       "from_name": lead.get("owner_name"), "owner_id": owner, "owner_name": staff.get(owner)})
    try:
        if data.get("next_step_done"):
            followup.done_next(lead, user)
            lead = _get_visible(lead_id, user)
        if nxt:
            followup.set_next(lead, user, nxt)
        elif "next_step" in data and data["next_step"] is None:
            followup.clear_next(lead, user)
        if "meeting" in data:
            m = data["meeting"]
            if m is None:
                followup.remove_meeting(lead, user)
            elif "status" in m:
                followup.meeting_outcome(lead, user, m["status"])
            else:
                followup.set_meeting(lead, user, meeting)
    except followup.Problem as p:
        return _problem(p)
    if moved:
        return _lead_body(lead_id, undo={"event_id": moved, "minutes": lead_history.UNDO_MINUTES})
    return get_lead(lead_id)


def _logged_words(outcome, nxt, meeting, moved, tz):
    """The toast after a call: "Logged: no answer. Next: Call back at 2 PM." / "Call booked for Thu 2 PM."."""
    now = datetime.now(timezone.utc)
    if outcome == "booked":
        text = f"Call booked for {followup._when_words(meeting, now, tz)}." if meeting else "Call booked, time not set yet."
    else:
        text = f"Logged: {followup.OUTCOME_WORDS[outcome]}."
    if moved:
        text += " Moved to Contacted."
    if nxt:
        local = nxt["at"].astimezone(tz)
        when = f"at {followup.short_clock(local)}" if local.date() == now.astimezone(tz).date() else f"on {followup._when_words(nxt['at'], now, tz)}"
        text += f" Next: {followup.next_words(nxt['kind'], nxt['text'])} {when}."
    return text


@bp.post("/<int:lead_id>/calls")
@login_required
def log_call(lead_id):
    """A call and how it went (L1). Talked to them or Booked a call on a New lead also moves it to Contacted, the
    same human stage move as the buttons (Eugene, 2026-11-11), which sends Contacted to Meta when that is on."""
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    if lead.get("repeat_of"):
        return api_error(REPEAT_WORK_REFUSED, 409)
    data = request.get_json(silent=True) or {}
    outcome = data.get("outcome")
    if outcome not in followup.OUTCOMES:
        return api_error("Pick how the call went", 400, field="outcome")
    now, tz = datetime.now(timezone.utc), account_info.tz()
    try:
        meeting = followup.clean_meeting(data.get("meeting") or {"unscheduled": True}, tz, now) if outcome == "booked" else None
        nxt = followup.clean_next(data["next_step"], tz, now) if data.get("next_step") and outcome != "booked" else None
    except followup.Problem as p:
        return _problem(p)
    event_id = followup.record_call(lead, user, outcome, note=data.get("note"), meeting=meeting, nxt=nxt)
    moved = None
    if outcome in followup.REACHED and lead["status"] == "new":
        moved = _set_status(_get_visible(lead_id, user), "contacted")
        db.execute("UPDATE lead_events SET details = details || %s::jsonb WHERE id = %s", (json.dumps({"stage_event": moved}), event_id))
    return _lead_body(lead_id, undo={"event_id": event_id, "minutes": lead_history.UNDO_MINUTES},
                      logged={"outcome": outcome, "moved": bool(moved), "text": _logged_words(outcome, nxt, meeting, moved, tz)})


def _undo_stage(lead_id, event, plan, user):
    """Put a stage move back in one transaction: claim the event (two clicks or two tabs put it back once), move
    the lead back only while it still sits where this move left it, take back stages still waiting for Meta.
    Returns (stages Meta already has, None) or (None, refusal)."""
    d = event.get("details") or {}
    now_max = (db.query("SELECT max_stage FROM leads WHERE id = %s", (lead_id,), one=True) or {}).get("max_stage") or "new"
    back_reason = d.get("reason_before") if plan["status"] == "lost" else None
    try:
        _, _, taken = db.run_in_transaction([
            ("UPDATE lead_events SET undone_at = now(), undone_by = %s WHERE id = %s AND undone_at IS NULL RETURNING id",
             (user["id"], event["id"]), True),
            ("""UPDATE leads SET status = %s, status_changed_at = COALESCE(%s::timestamptz, status_changed_at),
                       max_stage = %s, lost_reason = %s, lost_note = %s
                WHERE id = %s AND status = %s RETURNING id""",
             (plan["status"], plan["status_changed_at"], lq.undo_max(now_max, d), back_reason,
              d.get("note_before") if back_reason else None, lead_id, plan["to"]), True),
            ("DELETE FROM crm_events WHERE lead_id = %s AND stage = ANY(%s) AND status = 'pending' RETURNING stage",
             (lead_id, plan["crm"] or [])),
        ])
    except db.NothingChanged as exc:
        return None, ("That was already undone" if exc.step == 0 else "It has moved again since: move it back by hand")
    nb = (event.get("details") or {}).get("next_before")
    if nb and nb.get("next_step_at"):
        restored = db.execute("""UPDATE leads SET next_step_kind = %s, next_step_text = %s, next_step_at = %s, next_step_by = %s
                                 WHERE id = %s AND next_step_at IS NULL RETURNING id""", tuple(nb.get(c) for c in followup.NEXT_COLS) + (lead_id,), returning=True)
        if restored:  # the step is back, so the "Next step closed: lead is Lost" line the move wrote is undone too
            db.execute("""UPDATE lead_events SET undone_at = now(), undone_by = %s
                          WHERE lead_id = %s AND kind = 'next_cleared' AND undone_at IS NULL AND details->>'reason' = 'closed' AND at >= %s""",
                       (user["id"], lead_id, event["at"]))
    if plan["first_contact"]:
        followup.recount(lead_id, recheck_contact=True)
    log_activity("lead.status_undone", subject=str(lead_id), details={"from": plan["to"], "to": plan["status"], "event_id": event["id"]})
    gone = {r["stage"] for r in taken or []}
    return [s for s in plan["crm"] if s not in gone and s != "new"], None


def _event(lead_id, event_id):
    return db.query("SELECT id, at, kind, outcome, details, user_id, undone_at FROM lead_events WHERE id = %s AND lead_id = %s",
                    (event_id, lead_id), one=True)


def _latest_stage(lead_id):
    return db.query("SELECT MAX(id) AS id FROM lead_events WHERE lead_id = %s AND kind = 'stage'", (lead_id,), one=True)["id"]


@bp.post("/<int:lead_id>/events/<int:event_id>/undo")
@login_required
def undo_event(lead_id, event_id):
    """Undo a call or a stage move: the same person, within ten minutes; a stage move while it is still the last
    one. Stages queued for Meta are taken back only while still waiting; one already sent stays with Meta (no
    retraction). Taking back a call also puts back the move to Contacted it made, when that is still possible."""
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    event = _event(lead_id, event_id)
    if not event:
        return api_error("That change isn't in this lead's history", 404)
    now = datetime.now(timezone.utc)
    plan = lead_history.undo_plan(event, _latest_stage(lead_id), user["id"], now)
    if not plan["ok"]:
        return api_error(plan["error"], plan["code"])
    if plan["kind"] == "call":
        if not followup.undo_call(lead, event, user):
            return api_error("That was already undone", 409)
        undone = {"kind": "call", "to": None, "meta_has": []}
        stage_id = (event.get("details") or {}).get("stage_event")
        stage_ev = _event(lead_id, stage_id) if stage_id else None
        if stage_ev:
            splan = lead_history.undo_plan(stage_ev, _latest_stage(lead_id), user["id"], now)
            if splan["ok"]:
                kept, refused = _undo_stage(lead_id, stage_ev, splan, user)
                if not refused:
                    undone.update(to=splan["status"], meta_has=kept)
            if plan["first_contact"]:  # the move it made counted as a try too: work the first try out again
                followup.recount(lead_id, recheck_contact=True)
        return _lead_body(lead_id, undone=undone)
    kept, refused = _undo_stage(lead_id, event, plan, user)
    if refused:
        return api_error(refused, 409)
    return _lead_body(lead_id, undone={"kind": "stage", "to": plan["status"], "meta_has": kept})


def _staff_only(user):
    return api_error("Only the team can link or unlink leads", 403) if user["role"] == "client" else None


@bp.post("/<int:lead_id>/same-person")
@login_required
def same_person(lead_id):
    """'Same person as…': the older person stays the first lead; the newer one folds into it (L2)."""
    user = current_user()
    refused = _staff_only(user)
    if refused:
        return refused
    lead = _get_visible(lead_id, user)
    other_id = (request.get_json(silent=True) or {}).get("other_id")
    other = _get_visible(other_id, user) if isinstance(other_id, int) else None
    if not lead or not other:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    if lead["is_test"] or other["is_test"]:
        return api_error("Test leads can't be linked", 400)
    # The link is made between the first leads of both people: each must be one this person can see too.
    if any(x.get("repeat_of") and not _get_visible(x["repeat_of"], user) for x in (lead, other)):
        return api_error("One of them asked before in another campaign: an admin can link them", 404)
    try:
        root_id, folded = lead_quality_store.hand_link(lead, other)
    except lead_quality_store.Refused as exc:
        return api_error(str(exc), 400)
    root = _get_visible(root_id, user)
    return _lead_body(lead_id, linked={"root_id": root_id, "folded_id": folded, "root_name": root["full_name"] if root else None})


@bp.delete("/<int:lead_id>/same-person")
@login_required
def not_same_person(lead_id):
    """'Not the same person': counted on its own from now on, never linked again by itself."""
    user = current_user()
    refused = _staff_only(user)
    if refused:
        return refused
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    try:
        lead_quality_store.unlink(lead)
    except lead_quality_store.Refused as exc:
        return api_error(str(exc), 400)
    return get_lead(lead_id)


@bp.post("/<int:lead_id>/not-junk")
@login_required
def not_junk(lead_id):
    """'It's real': the junk chip goes and the lead isn't counted as junk."""
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    if user["role"] == "client" and not __import__("accounts_api").clients_update_leads():
        return api_error("Clients only look at leads here", 403)
    if not lead["junk_dismissed"]:
        db.execute("UPDATE leads SET junk_dismissed = TRUE WHERE id = %s", (lead_id,))
        lead_history.record(lead_id, "not_junk")
    return get_lead(lead_id)


@bp.post("/<int:lead_id>/notes")
@login_required
def add_note(lead_id):
    user = current_user()
    if not _get_visible(lead_id, user):
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    body = ((request.get_json(silent=True) or {}).get("body") or "").strip()
    if not body:
        return api_error("Write something first", 400)
    note = db.execute("INSERT INTO lead_notes (lead_id, user_id, body) VALUES (%s, %s, %s) RETURNING id",
                      (lead_id, user["id"], body[:5000]), returning=True)
    lead_history.record(lead_id, "note", ref_id=note["id"], mirror=False)
    return get_lead(lead_id)


@bp.get("/<int:lead_id>/reply")
@login_required
def reply_draft(lead_id):
    """The composer on the lead page: a template filled in for this lead."""
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    tid = request.args.get("template", type=int)
    return jsonify({**replies.draft(lead, user, tid),
                     "templates": [{"id": t["id"], "name": t["name"]} for t in replies.templates()],
                     "mail_ready": mailer.configured()})


@bp.post("/<int:lead_id>/reply")
@login_required
def send_reply(lead_id):
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    if not replies.EMAIL.match((lead["email"] or "").strip()):
        return api_error("This lead didn't leave an email address", 400)
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not subject:
        return api_error("Add a subject", 400, field="subject")
    if not body:
        return api_error("Write the email first", 400, field="body")
    try:
        replies.send_now(lead, user, subject[:300], body[:20000], data.get("template_id"))
    except mailer.MailError as exc:
        return api_error(str(exc), 502)
    if data.get("mark_contacted") and lead["status"] == "new":
        _set_status(lead, "contacted")
    return get_lead(lead_id)
