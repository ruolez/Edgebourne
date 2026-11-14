"""Home: what needs attention right now, and the day at a glance."""
import re
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

import account_info
import db
import lead_quality as lq
import followup
import insights
import meta_client
import settings_store
import today
from auth import current_user, login_required, visible_campaign_ids
from desk_api import bridge_status, bridge_with_status
from performance_api import cap_snapshot, daily_budget_cents, overview_data

bp = Blueprint("home", __name__, url_prefix="/api/home")


def today_by_campaign():
    """Spend and leads so far today, per campaign: read from Meta when the last read is over
    insights.TODAY_MAX_AGE old (FU-C). Today waits on this read, so a short timeout, and a Meta that didn't answer
    isn't asked again for a couple of minutes (audit A3-121); the stored numbers stand in."""
    read = insights.read_today()
    snap = insights.stored_today() or {"at": None, "campaigns": {}}
    return {**snap, "at": read["as_of"] or snap.get("at"), "error": read["error"]}


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
                     "line": "Settings shows why.", "href": "/settings.html#crm", "action": "Open Settings"})
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
        # Leads to call come from followup.queue below; a lead-quality alert (W1b) is an alert and stays.
        if not i["need"] or (i["category"] == "leads" and not i.get("alert_id")):
            continue
        rows.append({"key": i["key"], "category": i["category"], "rule": i["rule"], "level": i["level"],
                     "title": i["title"], "line": (i["lines"] or [""])[0], "href": i["href"], "at": i["at"],
                     "subject": i.get("subject"), "proposal_id": i.get("proposal_id"), "alert_id": i.get("alert_id"),
                     # W1: Got it / Diagnose with Claude on the row (admins); a snoozed problem is FYI, so never here.
                     **{k: i[k] for k in ("actions", "choices", "diagnose") if k in i}})
    rows += [] if user["role"] == "client" else _extras(user)
    _undo_flags(rows, user)
    leads_rows, total, follow = lead_rows(scope_ids, now)
    rows += leads_rows
    for r in rows:
        r["group"] = today.group_of(r["category"], r["rule"], r["level"])
    ranked = today.rank(rows)
    calls = [r for r in ranked if r["rule"] == "new_lead"]
    shown = {r["key"] for r in calls[:CALL_ROWS]}
    counts = {**inbox.counts(items), "snoozed": inbox.snoozed_count(items)}
    return [r for r in ranked if r["rule"] != "new_lead" or r["key"] in shown], int(total), counts, follow


def _undo_flags(rows, user):
    """D3: Put it back shows on a "didn't help" row only while there is still something to put back (not changed
    again since, not archived, no newer version), the same test History uses."""
    import change_checks_db
    ids = {}
    for r in rows:
        m = re.search(r"[?&]check=(\d+)", r.get("href") or "") if r["rule"] == "change_result" else None
        if m:
            ids[r["key"]] = int(m.group(1))
    if not ids:
        return
    found = change_checks_db.summary_for(sorted(set(ids.values())), client=user["role"] == "client")
    for r in rows:
        if r["key"] in ids:
            r["can_undo"] = bool((found.get(ids[r["key"]]) or {}).get("can_undo"))


# L1's lead rows: which Today group each bucket of followup.queue() lands in (00-PLAN S9), and its words.
LEAD_GROUP = {"call": "call", "meeting_soon": "call", "overdue": "follow", "meeting_check": "follow", "later": "later"}
LEAD_RULE = {"call": "new_lead", "meeting_soon": "meeting_soon", "overdue": "followup_overdue", "meeting_check": "meeting_check",
             "later": "followup_today"}


def _lead_title(kind, l, tz, now):
    name = l["full_name"] or "Unnamed"
    if kind == "meeting_soon":
        return f"Call with {name} at {followup.short_clock(l['meeting_at'].astimezone(tz))}", l["business_type"]
    if kind == "meeting_check":
        return f"Did the call with {name} happen?", f"It was {followup._when_words(l['meeting_at'], now, tz)}"
    words_ = followup.next_words(l["next_step_kind"], l["next_step_text"])
    if kind == "overdue":
        return f"Overdue: {words_} {name}", f"since {followup._when_words(l['next_step_at'], now, tz)}" + (f" · {l['business_type']}" if l["business_type"] else "")
    if kind == "later":
        return f"{words_} {name} · {followup.short_clock(l['next_step_at'].astimezone(tz))}", l["business_type"]
    return name, l["business_type"]


def lead_rows(scope_ids, now):
    """The leads part of Today, ranked by followup.queue: leads to call, booked calls within the hour, overdue
    follow-ups, calls that may not have happened, follow-ups due later today. Also how many leads wait for a
    first call and the follow-up footer counts."""
    tz = account_info.tz()
    lw = "TRUE" if scope_ids is None else "campaign_id = ANY(%s)"
    lp = [] if scope_ids is None else [scope_ids]
    waiting = f"""status = 'new' AND first_contacted_at IS NULL AND meeting_status IS DISTINCT FROM 'scheduled' AND {lw}"""
    total = db.query(f"SELECT COUNT(*) AS n FROM leads l WHERE {lq.counted()} AND {waiting}", lp, one=True)["n"]
    end_of_day = followup.due_where("today", now, tz)[1][1]
    leads = db.query(f"""SELECT id, full_name, business_type, ad_id, ad_name, phone, email, created_time, status, status_changed_at,
                                first_contacted_at, is_test, next_step_kind, next_step_text, next_step_at, meeting_at, meeting_status,
                                booked_at, call_attempts, ever_reached, repeat_of, junk_flags, junk_dismissed
                         FROM leads WHERE NOT is_test AND repeat_of IS NULL AND status IN ('new', 'contacted', 'qualified') AND {lw}
                         AND ((status = 'new' AND first_contacted_at IS NULL) OR next_step_at < %s
                              OR (meeting_status = 'scheduled' AND meeting_at < %s))
                         ORDER BY created_time ASC LIMIT 300""", lp + [end_of_day, now + followup.MEETING_GRACE])
    rows = []
    for q in followup.queue(leads, now, tz):
        l, kind = q["lead"], q["kind"]
        title, line = _lead_title(kind, l, tz, now)
        level = today.urgency(l, now) if kind == "call" else "warn" if kind in ("overdue", "meeting_check", "meeting_soon") else "info"
        rows.append({"key": f"lead:{l['id']}", "category": "leads", "rule": LEAD_RULE[kind], "level": level, "bucket": q["bucket"],
                     "at": q["at"], "title": title, "line": line, "href": f"/leads.html#lead={l['id']}",
                     "lead": {k: l[k] for k in ("id", "full_name", "phone", "email", "ad_id", "ad_name", "created_time", "status",
                                                "next_step_kind", "next_step_text", "next_step_at", "meeting_at")}})
    sql, params = followup.due_where("none", now, tz)
    no_next = db.query(f"SELECT COUNT(*) AS n FROM leads l WHERE {sql} AND {lq.counted()} AND {lw.replace('campaign_id', 'l.campaign_id')}",
                       params + lp, one=True)["n"]
    follow = {"no_next": int(no_next), "due_today": sum(1 for r in rows if r["rule"] == "followup_today"),
              "overdue": sum(1 for r in rows if r["rule"] == "followup_overdue"), "presets": followup.presets(now, tz)}
    return rows, total, follow


@bp.get("")
@login_required
def home():
    user = current_user()
    scope_ids = visible_campaign_ids(user)
    so_far = today_by_campaign()
    import ranges
    today_d = account_info.today()
    week = ranges.window("7", today_d, live=True)
    perf = overview_data(user, 7, span=(week, ranges.previous(*week, "7")), live=True)
    today_rows = [v for cid, v in (so_far.get("campaigns") or {}).items() if scope_ids is None or cid in scope_ids]
    lw = "TRUE" if scope_ids is None else "campaign_id = ANY(%s)"
    lp = [] if scope_ids is None else [scope_ids]
    leads = db.query(f"""SELECT id, full_name, business_type, ad_name, status, created_time, is_test FROM leads
                         WHERE {lw} AND repeat_of IS NULL ORDER BY created_time DESC LIMIT 6""", lp)
    cw = "TRUE" if scope_ids is None else "m.campaign_id = ANY(%s)"
    changes = db.query(f"""SELECT m.id, m.level, m.entity_id, m.entity_name, m.action, m.old_value, m.new_value, m.ok,
                                  m.error, m.created_at, u.name AS user_name
                           FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                           WHERE {cw} ORDER BY m.id DESC LIMIT 6""", lp)
    ads = db.query(f"SELECT effective_status, COUNT(*) AS n FROM ads WHERE {lw} GROUP BY 1", lp)
    stages = db.query(f"""SELECT status, COUNT(*) AS n FROM leads l
                          WHERE {lq.counted()} AND status_changed_at > now() - interval '7 days' AND {lw}
                          GROUP BY status""", lp)
    waiting = db.query(f"SELECT COUNT(*) AS n FROM leads WHERE status = 'new' AND NOT is_test AND repeat_of IS NULL AND {lw}", lp, one=True)["n"]
    budget = daily_budget_cents(scope_ids)
    strip = [{"id": a["id"], "name": a["name"], "status": a["effective_status"], "thumbnail_url": a.get("thumbnail_url"),
              "spend_cents": int(a["spend_cents"]), "leads": int(a["leads"])}
             for a in perf["ads"] if a["effective_status"] not in ("DELETED", "ARCHIVED")][:8]
    # The strip's highlight is a judgment: the most leads over the week's complete days, never today so far (FU-C).
    done = ranges.settled(*week, today_d)
    best = db.query("""SELECT ad_id, SUM(leads) AS n FROM ad_daily WHERE ad_id = ANY(%s) AND day BETWEEN %s AND %s
                       GROUP BY ad_id HAVING SUM(leads) > 0 ORDER BY SUM(leads) DESC, ad_id LIMIT 1""",
                    ([a["id"] for a in strip[:5]], *done), one=True) if strip and done else None
    rows, waiting_calls, counts, follow = queue(user, scope_ids)
    out = {
        "queue": rows,
        "waiting_calls": waiting_calls,
        "follow": follow,
        "fyi_unread": counts["fyi_unread"],
        "snoozed": counts["snoozed"],
        "today": {"spend_cents": sum(r["spend_cents"] for r in today_rows), "leads": sum(r["leads"] for r in today_rows),
                  "as_of": so_far.get("at"), "error": so_far.get("error")},
        "yesterday": perf["yesterday"],
        "week": {**perf["totals"], "range": perf["range"]},
        "ads": {r["effective_status"] or "UNKNOWN": int(r["n"]) for r in ads},
        "leads": leads,
        "waiting": int(waiting),
        "stages": {r["status"]: int(r["n"]) for r in stages},
        "daily_budget_cents": budget,
        "ad_strip": strip,
        "ad_strip_best": best["ad_id"] if best else None,
        "changes": changes,
        "updated_at": settings_store.get("last_refresh_at") or settings_store.get("last_performance_sync"),
        "source": perf["source"],  # D1: the last 7 days, today so far included (FU-C), as read from Meta
    }
    if user["role"] == "admin":
        out["desk"] = db.query("""SELECT id, kind, prompt, status, summary, finished_at FROM desk_tasks
                                  ORDER BY id DESC LIMIT 3""")
        out["pending_proposals"] = db.query("SELECT COUNT(*) AS n FROM desk_proposals WHERE status = 'pending'", one=True)["n"]
        out["bridge"] = bridge_with_status()
        out["cap"] = cap_snapshot()
        import drafts_api
        out["drafts"] = drafts_api.counts()  # AM-B: Upkeep's "N drafts in Ads Manager" line
    return jsonify(out)
