from flask import Blueprint, jsonify, request

import crm_events
import db
import jobs
import mailer
import replies
from auth import current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("leads", __name__, url_prefix="/api/leads")

STATUSES = ("new", "contacted", "qualified", "won", "lost")

LIST_COLUMNS = """l.id, l.created_time, l.full_name, l.email, l.phone, l.business_type,
                  l.ad_name, l.campaign_id, l.campaign_name, l.status, l.owner_id, l.is_test,
                  l.first_contacted_at, l.emailed_at, u.name AS owner_name"""


def _scope(user, alias="l"):
    ids = visible_campaign_ids(user)
    if ids is None:
        return "TRUE", []
    return f"{alias}.campaign_id = ANY(%s)", [ids]


def _get_visible(lead_id, user):
    where, params = _scope(user)
    return db.query(
        f"SELECT l.*, u.name AS owner_name FROM leads l LEFT JOIN users u ON u.id = l.owner_id "
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
    counts = db.query(
        f"SELECT l.status, COUNT(*) AS n FROM leads l WHERE {where} AND NOT l.is_test GROUP BY l.status",
        _scope(user)[1],
    )
    return jsonify({"leads": rows, "counts": {r["status"]: r["n"] for r in counts}})


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
    lead["history"] = db.query(
        "SELECT a.at, a.action, a.details, a.actor, u.name AS who FROM activity a "
        "LEFT JOIN users u ON u.id = a.user_id WHERE a.subject = %s AND a.action LIKE 'lead.%%' "
        "ORDER BY a.at",
        (str(lead_id),),
    )
    lead["assignable"] = db.query(
        """SELECT DISTINCT u.id, u.name FROM users u
           LEFT JOIN campaign_members cm ON cm.user_id = u.id
           WHERE u.is_active AND (u.role = 'admin' OR cm.campaign_id = %s) ORDER BY u.name""",
        (lead["campaign_id"],),
    )
    lead["meta_stages"] = crm_events.for_lead(lead_id) if crm_events.enabled() else None
    lead["replies"] = replies.for_lead(lead_id)
    return jsonify(lead)


def _set_status(lead, status):
    if status == lead["status"]:
        return
    db.execute(
        """UPDATE leads SET status = %s, status_changed_at = now(),
               first_contacted_at = COALESCE(first_contacted_at,
                   CASE WHEN %s <> 'new' THEN now() END)
           WHERE id = %s""",
        (status, status, lead["id"]),
    )
    log_activity("lead.status", subject=str(lead["id"]), details={"from": lead["status"], "to": status})
    if crm_events.enqueue(lead["id"], status):
        jobs.wake()


@bp.patch("/<int:lead_id>")
@login_required
def update_lead(lead_id):
    user = current_user()
    lead = _get_visible(lead_id, user)
    if not lead:
        return api_error("This lead doesn't exist or isn't in your campaigns", 404)
    data = request.get_json(silent=True) or {}
    if "status" in data:
        status = data["status"]
        if status not in STATUSES:
            return api_error("Pick one of: " + ", ".join(STATUSES), 400)
        _set_status(lead, status)
    if "owner_id" in data:
        owner = data["owner_id"]
        if owner is not None:
            ok = db.query("SELECT 1 FROM users WHERE id = %s AND is_active", (owner,), one=True)
            if not ok:
                return api_error("That teammate isn't active", 400)
        db.execute("UPDATE leads SET owner_id = %s WHERE id = %s", (owner, lead_id))
        log_activity("lead.owner", subject=str(lead_id), details={"owner_id": owner})
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
