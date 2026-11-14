"""What an admin does with an alert: Done on an event that waits for a person, Got it (snooze) / Wake it now,
and Diagnose with Claude (a read-only Desk run of kind `diagnose`). Nothing here changes Meta: snoozing only
stops the messages, and anything Claude suggests comes back as a suggestion accepted the usual way.
Admins only (account admins and the console's owners); row-level security keeps each account's own."""
import json
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import alerts
import db
import diagnose
import snooze
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("alert_actions", __name__, url_prefix="/api")

ALERT_COLS = ("id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at, kind, "
              "measure::float8 AS measure, quiet")
PROBLEM_STATES = ("DISAPPROVED", "WITH_ISSUES")
ACTIVE = ("queued", "claimed", "running")


def _alert(alert_id):
    return db.query(f"SELECT {ALERT_COLS} FROM alerts WHERE id = %s", (alert_id,), one=True)


def _newest_open(a):
    """The newest open row of this alert's problem: its figure is the snooze's baseline (a person may snooze from
    an older row of the episode)."""
    return db.query(f"""SELECT {ALERT_COLS} FROM alerts WHERE rule = %s AND entity_id IS NOT DISTINCT FROM %s
                        AND kind = 'condition' AND resolved_at IS NULL ORDER BY created_at DESC, id DESC LIMIT 1""",
                    (a["rule"], a["entity_id"]), one=True)


@bp.post("/alerts/<int:alert_id>/done")
@admin_required
def done(alert_id):
    """Done on an event that waits for a person (an outside budget change that broke a money rule)."""
    row = alerts.mark_done(alert_id)
    if not row:
        return api_error("This one is already closed, or it closes by itself", 409)
    log_activity("alert.done", subject=str(alert_id), details={"rule": row["rule"], "title": row["title"]})
    return jsonify({"ok": True})


@bp.post("/alerts/<int:alert_id>/snooze")
@admin_required
def snooze_alert(alert_id):
    a = _alert(alert_id)
    if not a:
        return api_error("That alert isn't here any more", 404)
    if a["resolved_at"] is not None:
        return api_error("This has already cleared.", 409)
    newest = _newest_open(a) or a
    offered = snooze.choices(newest)
    if not offered or not a["entity_id"]:
        return api_error("This one can't be snoozed.", 409)
    body = request.get_json(silent=True) or {}
    mode, days = body.get("mode"), body.get("days")
    pick = next((c for c in offered if c["mode"] == mode and (mode == "worse" or c["days"] == days)), None)
    if not pick:
        return api_error("Pick one of the choices shown", 400, field="mode")
    tz = account_info.tz()
    until = snooze.until_for(datetime.now(timezone.utc).astimezone(tz), pick["days"]) if pick["mode"] == "days" else None
    user = current_user()
    # A second admin who got there first wins: their snooze is returned as it is.
    row = db.execute("""INSERT INTO alert_snoozes (rule, entity_id, campaign_id, mode, until, baseline, baseline_level,
                                                   alert_id, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id, rule, entity_id) WHERE ended_at IS NULL DO NOTHING RETURNING id""",
                     (a["rule"], a["entity_id"], a["campaign_id"], pick["mode"], until, newest.get("measure"),
                      newest["level"] if newest["level"] in ("bad", "warn", "info") else "info", newest["id"], user["id"]),
                     returning=True)
    live = alerts.live_snoozes([a["rule"]]).get((a["rule"], a["entity_id"]))
    if row:
        log_activity("alert.snoozed", subject=str(alert_id),
                     details={"rule": a["rule"], "entity": a["entity_id"], "mode": pick["mode"], "until": until.isoformat() if until else None})
    return jsonify({"snooze": alerts.snooze_view(live, tz) if live else None, "already": not row})


@bp.delete("/alerts/<int:alert_id>/snooze")
@admin_required
def wake(alert_id):
    """Wake it now (also Undo and Settings): the problem is back in Needs action and its messages resume."""
    a = _alert(alert_id)
    live = a and alerts.live_snoozes([a["rule"]]).get((a["rule"], a["entity_id"]))
    if not live:
        return api_error("Nothing is snoozed here", 404)
    alerts.end_snooze(live["id"], "by_hand", current_user()["id"])
    log_activity("alert.woken", subject=str(alert_id), details={"rule": a["rule"], "entity": a["entity_id"]})
    return jsonify({"ok": True})


# ---------------------------------------------------------------- Diagnose with Claude

def _names(entity_id):
    """{"ad"|"adset"|"campaign": {id, name}} for the thing an alert is about and what it sits in."""
    entity_id = str(entity_id).split(":", 1)[0] if entity_id else entity_id  # AM-E: an anomaly's "<id>:<metric>"
    if not entity_id or entity_id == "account":
        return {}
    ad = db.query("""SELECT a.id, a.name, a.adset_id, s.name AS adset_name, a.campaign_id, c.name AS campaign_name
                     FROM ads a LEFT JOIN adsets s ON s.id = a.adset_id LEFT JOIN campaigns c ON c.id = a.campaign_id
                     WHERE a.id = %s""", (entity_id,), one=True)
    if ad:
        return {"ad": {"id": ad["id"], "name": ad["name"]}, "adset": {"id": ad["adset_id"], "name": ad["adset_name"]},
                "campaign": {"id": ad["campaign_id"], "name": ad["campaign_name"]}}
    s = db.query("""SELECT s.id, s.name, s.campaign_id, c.name AS campaign_name FROM adsets s
                    LEFT JOIN campaigns c ON c.id = s.campaign_id WHERE s.id = %s""", (entity_id,), one=True)
    if s:
        return {"adset": {"id": s["id"], "name": s["name"]}, "campaign": {"id": s["campaign_id"], "name": s["campaign_name"]}}
    c = db.query("SELECT id, name FROM campaigns WHERE id = %s", (entity_id,), one=True)
    return {"campaign": {"id": c["id"], "name": c["name"]}} if c else {}


def _from_ad(ad_id):
    """An ad page's Diagnose: the ad's newest rejection alert while it counts, else one built from the ad itself."""
    ad = db.query("SELECT id, name, campaign_id, effective_status, issues FROM ads WHERE id = %s", (ad_id,), one=True)
    if not ad:
        return None, None
    a = db.query(f"""SELECT {ALERT_COLS} FROM alerts WHERE rule = 'ad_rejected' AND entity_id = %s
                     AND (resolved_at IS NULL OR resolved_at > now() - make_interval(days => %s))
                     ORDER BY created_at DESC, id DESC LIMIT 1""", (ad_id, DIAGNOSE_DAYS), one=True)
    if a:
        return a, ad
    if ad["effective_status"] not in PROBLEM_STATES:
        return None, ad
    import status_history
    rejected = ad["effective_status"] == "DISAPPROVED"
    issue = status_history.issues_summary(ad.get("issues")) if not rejected else None
    return {"id": None, "rule": "ad_rejected", "level": "bad", "kind": "condition", "entity_id": ad["id"], "campaign_id": ad["campaign_id"],
            "title": f"Meta rejected “{ad['name']}”" if rejected else f"“{ad['name']}” has a problem on Meta",
            "lines": [issue] if issue else [], "measure": 2 if rejected else 1, "resolved_at": None,
            "created_at": None}, ad


DIAGNOSE_DAYS = 3


def _subject():
    """(alert, ad, error response) for ?alert_id= / ?ad_id= or the same keys in a JSON body."""
    src = (request.get_json(silent=True) or {}) if request.method == "POST" else request.args
    alert_id, ad_id = src.get("alert_id"), src.get("ad_id")
    if alert_id not in (None, ""):
        try:
            a = _alert(int(alert_id))
        except (TypeError, ValueError):
            a = None
        if not a:
            return None, None, api_error("That alert isn't here any more", 404)
        if not diagnose.can_diagnose(a["rule"]):
            return None, None, api_error("Claude can't look into this one from the Mac.", 409)
        if a["resolved_at"] is not None and a["resolved_at"] < datetime.now(timezone.utc) - timedelta(days=DIAGNOSE_DAYS):
            return None, None, api_error("This cleared a while ago.", 409)
        return a, None, None
    if ad_id not in (None, ""):
        a, ad = _from_ad(str(ad_id))
        if not ad:
            return None, None, api_error("That ad isn't here", 404)
        if not a:
            return None, None, api_error("Meta isn't stopping this ad, so there's nothing to diagnose.", 409)
        return a, ad, None
    return None, None, api_error("Say which alert or ad", 400)


def _context(a):
    tz = account_info.tz()
    first = a.get("created_at")
    if a.get("id") and a["kind"] == "condition":
        row = db.query("""SELECT MIN(created_at) AS first FROM alerts WHERE rule = %s AND entity_id IS NOT DISTINCT FROM %s
                          AND kind = 'condition' AND (resolved_at IS NULL) = %s""",
                       (a["rule"], a["entity_id"], a["resolved_at"] is None), one=True)
        first = row and row["first"] or first
    live = alerts.live_snoozes([a["rule"]]).get((a["rule"], a["entity_id"]))
    view = alerts.snooze_view(live, tz) if live else None
    ctx = diagnose.context(a, _names(a["entity_id"]), first, view)
    return ctx, diagnose.playbook(a["rule"]), tz


def _key(a):
    return diagnose.episode_key(a["rule"], a["entity_id"])


@bp.get("/diagnose/draft")
@admin_required
def draft():
    from desk_api import bridge_status, latest_runs
    a, _, err = _subject()
    if err:
        return err
    ctx, pb, tz = _context(a)
    b = bridge_status()
    return jsonify({"prompt": diagnose.prompt(ctx, pb, tz, datetime.now(timezone.utc)),
                    "playbook": {"skill": pb["skill"], "label": pb["label"]}, "alert_id": a.get("id"), "title": ctx["title"],
                    "run": latest_runs("diagnose", "alert_key", [_key(a)]).get(_key(a)),
                    "bridge": {"online": b["online"], "has_key": b["has_key"]}})


@bp.post("/diagnose")
@admin_required
def start():
    from desk_api import MAX_PROMPT, latest_runs
    a, ad, err = _subject()
    if err:
        return err
    text = ((request.get_json(silent=True) or {}).get("prompt") or "").strip()
    if not text:
        return api_error("Tell Claude what you'd like", 400, field="prompt")
    if len(text) > MAX_PROMPT:
        return api_error("Keep it under 4,000 characters", 400, field="prompt")
    key = _key(a)
    # One open run per problem: two quick taps (or two admins) file one.
    with db.try_lock(f"diagnose:{account_ctx.current()}:{key}") as mine:
        if not mine:
            # The other tap is filing the run right now: answer with that run once it is there.
            for _ in range(10):
                time.sleep(0.2)
                run = latest_runs("diagnose", "alert_key", [key]).get(key)
                if run and run["status"] in ACTIVE:
                    return jsonify({"task_id": run["id"], "already": True})
            return jsonify({"task_id": None, "already": True})
        return _file(a, ad, key, text, latest_runs)


def _file(a, ad, key, text, latest_runs):
    run = latest_runs("diagnose", "alert_key", [key]).get(key)
    if run and run["status"] in ACTIVE:
        return jsonify({"task_id": run["id"], "already": True})
    ctx, pb, _ = _context(a)
    names = ctx["names"]
    options = {"alert_key": key, "alert": ctx, "playbook": pb["skill"], "focus": pb["focus"], "source": "ad" if ad else "alert"}
    if "ad" in names:
        options.update(ad_id=names["ad"]["id"], ad_name=names["ad"]["name"])
    camp = a.get("campaign_id") or names.get("campaign", {}).get("id")
    if camp and not db.query("SELECT 1 FROM campaigns WHERE id = %s", (camp,), one=True):
        camp = None
    task = db.execute("INSERT INTO desk_tasks (kind, prompt, campaign_id, created_by, options) VALUES ('diagnose', %s, %s, %s, %s) RETURNING id",
                      (text, camp, current_user()["id"], json.dumps(options, default=str)), returning=True)
    log_activity("desk.task_created", subject=str(task["id"]), details={"kind": "diagnose", "rule": a["rule"]})
    return jsonify({"task_id": task["id"]}), 201
