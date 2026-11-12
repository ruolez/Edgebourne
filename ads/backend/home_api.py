"""Home: what needs attention right now, and the day at a glance."""
import time

from flask import Blueprint, jsonify

import db
import insights
import meta_client
import settings_store
from auth import current_user, login_required, visible_campaign_ids
from desk_api import bridge_status
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


def attention(user, scope_ids):
    """What Today asks of the person. `kind` is the Inbox category (status, leads, claude, money, system): it picks the icon."""
    items = []
    import alerts
    import inbox
    for a in alerts.open_alerts(scope_ids):
        if a["campaign_id"] is None and user["role"] != "admin":
            continue
        items.append({"level": a["level"], "kind": inbox.category(a["rule"]), "text": a["title"] + (f". {a['lines'][0]}" if a["lines"] else ""),
                      "href": a["href"] or "/home.html", "action": "Open"})
    lw = "TRUE" if scope_ids is None else "campaign_id = ANY(%s)"
    lp = [] if scope_ids is None else [scope_ids]
    waiting = db.query(f"SELECT COUNT(*) AS n FROM leads WHERE status = 'new' AND NOT is_test "
                       f"AND created_time < now() - interval '1 hour' AND {lw}", lp, one=True)["n"]
    if waiting:
        items.append({"level": "warn", "kind": "leads", "text": f"{waiting} lead{'s' if waiting != 1 else ''} waiting more than an hour for a first call.",
                      "href": "/leads.html", "action": "Open leads"})
    # Claude's proposals are internal: a client isn't told they exist.
    pend = [] if user["role"] == "client" else db.query("SELECT entity_id FROM desk_proposals WHERE status = 'pending'")
    mine = [p for p in pend if scope_ids is None or (p["entity_id"] and _campaign_of(p["entity_id"]) in scope_ids)]
    if mine:
        items.append({"level": "claude", "kind": "claude", "text": f"Claude has {len(mine)} suggestion{'s' if len(mine) != 1 else ''} waiting for your decision.",
                      "href": "/desk.html" if user["role"] == "admin" else "/ads.html", "action": "Review"})
    if user["role"] == "admin":
        if not settings_store.get("meta_system_token") or not settings_store.get("meta_ad_account_id"):
            items.append({"level": "bad", "kind": "system", "text": "This account isn't connected to Meta yet: add its ad account and Page.",
                          "href": "/settings.html#meta", "action": "Open Settings"})
        failed = db.query("SELECT COUNT(*) AS n FROM crm_events WHERE status = 'failed' "
                          "AND created_at > now() - interval '14 days'", one=True)["n"]
        if failed:
            items.append({"level": "warn", "kind": "system", "text": f"{failed} lead stage{'s' if failed != 1 else ''} didn't reach Meta.",
                          "href": "/settings.html", "action": "Open Settings"})
        queued = db.query("SELECT COUNT(*) AS n FROM desk_tasks WHERE status = 'queued'", one=True)["n"]
        if queued and not bridge_status()["online"]:
            items.append({"level": "warn", "kind": "claude", "text": f"{queued} request{'s' if queued != 1 else ''} for Claude waiting: your Mac is offline.",
                          "href": "/desk.html", "action": "Open Claude"})
    return items


def _campaign_of(entity_id):
    for table, col in (("ads", "campaign_id"), ("adsets", "campaign_id"), ("campaigns", "id")):
        row = db.query(f"SELECT {col} AS c FROM {table} WHERE id = %s", (entity_id,), one=True)
        if row:
            return row["c"]
    return None


@bp.get("")
@login_required
def home():
    user = current_user()
    scope_ids = visible_campaign_ids(user)
    perf = overview_data(user, 7)
    today = today_by_campaign()
    today_rows = [v for cid, v in (today.get("campaigns") or {}).items() if scope_ids is None or cid in scope_ids]
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
    call = db.query(f"""SELECT id, full_name, business_type, ad_id, ad_name, phone, email, created_time FROM leads
                        WHERE status = 'new' AND NOT is_test AND {lw}
                        ORDER BY created_time ASC LIMIT 5""", lp)
    stages = db.query(f"""SELECT status, COUNT(*) AS n FROM leads
                          WHERE NOT is_test AND status_changed_at > now() - interval '7 days' AND {lw}
                          GROUP BY status""", lp)
    waiting = db.query(f"SELECT COUNT(*) AS n FROM leads WHERE status = 'new' AND NOT is_test AND {lw}", lp, one=True)["n"]
    budget = daily_budget_cents(scope_ids)
    strip = [{"id": a["id"], "name": a["name"], "status": a["effective_status"], "thumbnail_url": a.get("thumbnail_url"),
              "spend_cents": int(a["spend_cents"]), "leads": int(a["leads"])}
             for a in perf["ads"] if a["effective_status"] not in ("DELETED", "ARCHIVED")][:8]
    out = {
        "attention": attention(user, scope_ids),
        "today": {"spend_cents": sum(r["spend_cents"] for r in today_rows), "leads": sum(r["leads"] for r in today_rows),
                  "as_of": today.get("at")},
        "yesterday": perf["yesterday"],
        "week": {**perf["totals"], "range": perf["range"]},
        "ads": {r["effective_status"] or "UNKNOWN": int(r["n"]) for r in ads},
        "leads": leads,
        "call": call,
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
        out["bridge"] = bridge_status()
        out["cap"] = cap_snapshot()
    return jsonify(out)
