"""Home: what needs attention right now, and the day at a glance."""
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

import db
import insights
import meta_client
import settings_store
import today
from auth import current_user, login_required, visible_campaign_ids
from desk_api import bridge_status, bridge_with_status
from performance_api import cap_snapshot, daily_budget_cents, overview_data

bp = Blueprint("home", __name__, url_prefix="/api/home")
TODAY_TTL = 300


def today_by_campaign():
    """Spend and leads so far today, per campaign, cached for five minutes. Today waits on this read, so a
    short timeout, and a Meta that didn't answer isn't asked again for a couple of minutes (audit A3-121)."""
    snap = insights.stored_today()
    if snap and time.time() - snap["at"] < TODAY_TTL:
        return snap
    if not meta_client.recently_failed("today_snapshot"):
        try:
            return insights.pull_today(timeout=meta_client.READ_TIMEOUT)
        except meta_client.MetaError as exc:
            meta_client.remember_failure("today_snapshot", exc)
    return snap or {"at": None, "campaigns": {}}


CALL_ROWS = 6  # leads listed in the queue; the rest are counted with a link to Leads


def _extras(user):
    """What keeps the console running, for admins: Meta connection, stages Meta didn't take, Claude's line."""
    rows = []
    if user["role"] != "admin":
        return rows
    if not settings_store.get("meta_system_token") or not settings_store.get("meta_ad_account_id"):
        rows.append({"key": "sys:connect", "category": "system", "rule": "connect", "level": "bad",
                     "title": "This account isn't connected to Meta yet", "line": "Add its ad account and Page.",
                     "href": "/settings.html#meta", "action": "Open Settings"})
    failed = db.query("SELECT COUNT(*) AS n FROM crm_events WHERE status = 'failed' "
                      "AND created_at > now() - interval '14 days'", one=True)["n"]
    if failed:
        rows.append({"key": "sys:crm", "category": "system", "rule": "crm_failed", "level": "warn",
                     "title": f"{failed} lead stage{'s' if failed != 1 else ''} didn't reach Meta",
                     "line": "Settings shows why, with Try again.", "href": "/settings.html", "action": "Open Settings"})
    queued = db.query("SELECT COUNT(*) AS n FROM desk_tasks WHERE status = 'queued'", one=True)["n"]
    if queued and not bridge_status()["online"]:
        rows.append({"key": "sys:mac", "category": "system", "rule": "mac_offline", "level": "warn",
                     "title": f"{queued} request{'s' if queued != 1 else ''} for Claude waiting",
                     "line": "Your Mac is offline. Claude picks them up when it's back.", "href": "/desk.html", "action": "Open Claude"})
    return rows


def queue(user, scope_ids):
    """Today's one ranked queue: the Inbox's Needs action (never its FYI), with the leads to call drawn from
    Leads with what a call needs. Clients see status alerts and leads only (the Inbox already limits them)."""
    import inbox
    now = datetime.now(timezone.utc)
    rows = []
    items = inbox.items_for(user)
    for i in items:
        if not i["need"] or i["category"] == "leads":
            continue
        rows.append({"key": i["key"], "category": i["category"], "rule": i["rule"], "level": i["level"],
                     "title": i["title"], "line": (i["lines"] or [""])[0], "href": i["href"], "at": i["at"],
                     "subject": i.get("subject"), "proposal_id": i.get("proposal_id")})
    rows += [] if user["role"] == "client" else _extras(user)
    lw = "TRUE" if scope_ids is None else "campaign_id = ANY(%s)"
    lp = [] if scope_ids is None else [scope_ids]
    waiting = f"status = 'new' AND NOT is_test AND first_contacted_at IS NULL AND {lw}"
    total = db.query(f"SELECT COUNT(*) AS n FROM leads WHERE {waiting}", lp, one=True)["n"]
    leads = db.query(f"""SELECT id, full_name, business_type, ad_id, ad_name, phone, email, created_time, status,
                                first_contacted_at, is_test FROM leads WHERE {waiting}
                         ORDER BY created_time ASC LIMIT 200""", lp)
    for l in leads:
        rows.append({"key": f"lead:{l['id']}", "category": "leads", "rule": "new_lead", "level": today.urgency(l, now),
                     "bucket": today.lead_bucket(l, now), "at": l["created_time"], "title": l["full_name"] or "Unnamed",
                     "line": l["business_type"], "href": f"/leads.html#lead={l['id']}",
                     "lead": {k: l[k] for k in ("id", "phone", "email", "ad_id", "ad_name", "created_time")}})
    for r in rows:
        r["group"] = today.group_of(r["category"], r["rule"], r["level"])
    ranked = today.rank(rows)
    calls = [r for r in ranked if r["group"] == "call"]
    shown = {r["key"] for r in calls[:CALL_ROWS]}
    return [r for r in ranked if r["group"] != "call" or r["key"] in shown], int(total), inbox.counts(items)


@bp.get("")
@login_required
def home():
    user = current_user()
    scope_ids = visible_campaign_ids(user)
    perf = overview_data(user, 7)
    so_far = today_by_campaign()
    today_rows = [v for cid, v in (so_far.get("campaigns") or {}).items() if scope_ids is None or cid in scope_ids]
    lw = "TRUE" if scope_ids is None else "campaign_id = ANY(%s)"
    lp = [] if scope_ids is None else [scope_ids]
    leads = db.query(f"""SELECT id, full_name, business_type, ad_name, status, created_time, is_test FROM leads
                         WHERE {lw} ORDER BY created_time DESC LIMIT 6""", lp)
    cw = "TRUE" if scope_ids is None else "m.campaign_id = ANY(%s)"
    changes = db.query(f"""SELECT m.id, m.level, m.entity_id, m.entity_name, m.action, m.old_value, m.new_value, m.ok,
                                  m.error, m.created_at, u.name AS user_name
                           FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                           WHERE {cw} ORDER BY m.id DESC LIMIT 6""", lp)
    ads = db.query(f"SELECT effective_status, COUNT(*) AS n FROM ads WHERE {lw} GROUP BY 1", lp)
    stages = db.query(f"""SELECT status, COUNT(*) AS n FROM leads
                          WHERE NOT is_test AND status_changed_at > now() - interval '7 days' AND {lw}
                          GROUP BY status""", lp)
    waiting = db.query(f"SELECT COUNT(*) AS n FROM leads WHERE status = 'new' AND NOT is_test AND {lw}", lp, one=True)["n"]
    budget = daily_budget_cents(scope_ids)
    strip = [{"id": a["id"], "name": a["name"], "status": a["effective_status"], "thumbnail_url": a.get("thumbnail_url"),
              "spend_cents": int(a["spend_cents"]), "leads": int(a["leads"])}
             for a in perf["ads"] if a["effective_status"] not in ("DELETED", "ARCHIVED")][:8]
    rows, waiting_calls, counts = queue(user, scope_ids)
    out = {
        "queue": rows,
        "waiting_calls": waiting_calls,
        "fyi_unread": counts["fyi_unread"],
        "today": {"spend_cents": sum(r["spend_cents"] for r in today_rows), "leads": sum(r["leads"] for r in today_rows),
                  "as_of": so_far.get("at")},
        "yesterday": perf["yesterday"],
        "week": {**perf["totals"], "range": perf["range"]},
        "ads": {r["effective_status"] or "UNKNOWN": int(r["n"]) for r in ads},
        "leads": leads,
        "waiting": int(waiting),
        "stages": {r["status"]: int(r["n"]) for r in stages},
        "daily_budget_cents": budget,
        "ad_strip": strip,
        "changes": changes,
        "updated_at": settings_store.get("last_refresh_at") or settings_store.get("last_performance_sync"),
    }
    if user["role"] == "admin":
        out["desk"] = db.query("""SELECT id, kind, prompt, status, summary, finished_at FROM desk_tasks
                                  ORDER BY id DESC LIMIT 3""")
        out["pending_proposals"] = db.query("SELECT COUNT(*) AS n FROM desk_proposals WHERE status = 'pending'", one=True)["n"]
        out["bridge"] = bridge_with_status()
        out["cap"] = cap_snapshot()
    return jsonify(out)
