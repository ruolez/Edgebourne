from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import crm_events
import db
import jobs
import lead_history
import leads
import mailer
import reminders
import replies
import today
from auth import current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("leads", __name__, url_prefix="/api/leads")

STATUSES = ("new", "contacted", "qualified", "won", "lost")

LIST_COLUMNS = """l.id, l.created_time, l.full_name, l.email, l.phone, l.business_type,
                  l.ad_name, l.campaign_id, l.campaign_name, l.status, l.owner_id, l.is_test, l.is_organic,
                  l.first_contacted_at, l.emailed_at, u.name AS owner_name"""


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
    rows = db.query(
        f"SELECT {LIST_COLUMNS} FROM leads l LEFT JOIN users u ON u.id = l.owner_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY l.created_time DESC LIMIT 500",
        params,
    )
    now = datetime.now(timezone.utc)
    for r in rows:
        r["urgency"] = today.urgency(r, now)  # the same rule as Today and the reminders
    # The stage chips count the same source as the list (a campaign, ad set, ad or form), so a link that
    # narrows the list shows numbers that add up to what it lists.
    # The nav badge still counts every new lead (`everywhere`).
    source_sql = " AND ".join(source_clauses) or "TRUE"
    counts = db.query(
        f"""SELECT l.status, COUNT(*) FILTER (WHERE {source_sql}) AS n, COUNT(*) AS everywhere
            FROM leads l WHERE {where} AND NOT l.is_test GROUP BY l.status""",
        source_params + _scope(user)[1],
    )
    sources = db.query(
        f"""SELECT l.campaign_id, MAX(l.campaign_name) AS campaign_name, l.ad_id, MAX(l.ad_name) AS ad_name, COUNT(*) AS n
            FROM leads l WHERE {where} AND NOT l.is_test AND l.campaign_id IS NOT NULL
            GROUP BY l.campaign_id, l.ad_id ORDER BY 2, 4""", _scope(user)[1])
    return jsonify({"leads": rows, "counts": {r["status"]: r["n"] for r in counts},
                    "new_everywhere": next((r["everywhere"] for r in counts if r["status"] == "new"), 0), "sources": sources,
                    "narrowed": _narrowed(request.args, user), "response": reminders.stats(*_scope(user))})


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
    rows = _history_rows(lead_id)
    owners = [r["details"].get("owner_id") for r in rows if r["action"] == "lead.owner" and r["details"].get("owner_id")]
    names = {u["id"]: u["name"] for u in db.query("SELECT id, name FROM users WHERE id = ANY(%s)", (owners,))} if owners else {}
    lead["history"] = [{"id": r["id"], "at": r["at"], "action": r["action"], "who": r["who"], "text": lead_history.describe(r, names)}
                       for r in reversed(rows)]  # newest first
    lead["urgency"] = today.urgency(lead, datetime.now(timezone.utc))
    lead["assignable"] = leads.staff_for(lead["campaign_id"])
    lead["meta_stages"] = crm_events.for_lead(lead_id) if crm_events.enabled() else None
    lead["replies"] = replies.for_lead(lead_id)
    return jsonify(lead)


def _history_rows(lead_id):
    return db.query(
        "SELECT a.id, a.at, a.action, a.details, a.actor, a.user_id, u.name AS who FROM activity a "
        "LEFT JOIN users u ON u.id = a.user_id WHERE a.subject = %s AND a.action LIKE 'lead.%%' "
        "ORDER BY a.at, a.id",
        (str(lead_id),),
    )


def _set_status(lead, status):
    """Move the stage. Returns the history line's id (what Undo names), or None when nothing moved."""
    if status == lead["status"]:
        return None
    db.execute(
        """UPDATE leads SET status = %s, status_changed_at = now(),
               first_contacted_at = COALESCE(first_contacted_at,
                   CASE WHEN %s <> 'new' THEN now() END)
           WHERE id = %s""",
        (status, status, lead["id"]),
    )
    queued = crm_events.enqueue(lead["id"], status)
    before = lead.get("status_changed_at")
    event_id = log_activity("lead.status", subject=str(lead["id"]), details={
        "from": lead["status"], "to": status, "changed_before": before.isoformat() if before else None,
        "first_contact": lead.get("first_contacted_at") is None and status != "new", "crm": queued})
    if queued:
        jobs.wake()
    return event_id


@bp.patch("/<int:lead_id>")
@login_required
def update_lead(lead_id):
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    data = request.get_json(silent=True) or {}
    if user["role"] == "client" and set(data) - {"status"}:
        return api_error("Clients can move a lead's stage, nothing else", 403)
    moved = None
    if "status" in data:
        status = data["status"]
        if status not in STATUSES:
            return api_error("Pick one of: " + ", ".join(STATUSES), 400)
        moved = _set_status(lead, status)
    if "owner_id" in data:
        owner = data["owner_id"]
        staff = {u["id"]: u["name"] for u in leads.staff_for(lead["campaign_id"])}
        if owner is not None and owner not in staff:
            return api_error("Pick someone who works on this lead's campaign", 400)
        db.execute("UPDATE leads SET owner_id = %s WHERE id = %s", (owner, lead_id))
        log_activity("lead.owner", subject=str(lead_id), details={"owner_id": owner, "owner_name": staff.get(owner)})
    out = get_lead(lead_id)
    if moved:
        body = out.get_json()
        body["undo"] = {"event_id": moved, "minutes": lead_history.UNDO_MINUTES}
        return jsonify(body)
    return out


@bp.post("/<int:lead_id>/events/<int:event_id>/undo")
@login_required
def undo_event(lead_id, event_id):
    """Undo a stage move: the same person, within ten minutes, while it is still the last move. The stages it
    queued for Meta are taken back only while still waiting; one already sent stays with Meta (no retraction)."""
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    rows = _history_rows(lead_id)
    event = next((r for r in rows if r["id"] == event_id), None)
    if not event:
        return api_error("That change isn't in this lead's history", 404)
    latest = max((r["id"] for r in rows if r["action"] == "lead.status"), default=None)
    plan = lead_history.undo_plan(event, latest, user["id"], datetime.now(timezone.utc))
    if not plan["ok"]:
        return api_error(plan["error"], plan["code"])
    # One transaction: claim the line (two clicks or two tabs put it back once) and move the lead back only
    # while it still sits where this move left it; a contact time from an email sent since stays.
    try:
        _, _, taken = db.run_in_transaction([
            ("UPDATE activity SET details = details || '{\"undone\": true}'::jsonb "
             "WHERE id = %s AND NOT (details ? 'undone') RETURNING id", (event_id,), True),
            ("""UPDATE leads SET status = %s, status_changed_at = COALESCE(%s::timestamptz, status_changed_at),
                   first_contacted_at = CASE WHEN %s THEN (SELECT MIN(r.sent_at) FROM lead_replies r
                       WHERE r.lead_id = leads.id AND r.status = 'sent' AND NOT r.auto) ELSE first_contacted_at END
                WHERE id = %s AND status = %s RETURNING id""",
             (plan["status"], plan["status_changed_at"], plan["clear_first_contact"], lead_id, plan["to"]), True),
            ("DELETE FROM crm_events WHERE lead_id = %s AND stage = ANY(%s) AND status = 'pending' RETURNING stage",
             (lead_id, plan["crm"] or [])),
        ])
    except db.NothingChanged as exc:
        if exc.step == 0:
            return api_error("That move was already undone", 409)
        return api_error("It has moved again since: move it back by hand", 409)
    gone = {r["stage"] for r in taken or []}
    kept = [s for s in plan["crm"] if s not in gone]
    log_activity("lead.status_undone", subject=str(lead_id), details={"from": plan["to"], "to": plan["status"], "event_id": event_id})
    body = get_lead(lead_id).get_json()
    body["undone"] = {"to": plan["status"], "meta_has": [s for s in kept if s != "new"]}
    return jsonify(body)


@bp.post("/<int:lead_id>/notes")
@login_required
def add_note(lead_id):
    user = current_user()
    if not _get_visible(lead_id, user):
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    body = ((request.get_json(silent=True) or {}).get("body") or "").strip()
    if not body:
        return api_error("Write something first", 400)
    db.execute("INSERT INTO lead_notes (lead_id, user_id, body) VALUES (%s, %s, %s)",
               (lead_id, user["id"], body[:5000]))
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
