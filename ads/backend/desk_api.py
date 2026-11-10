"""AI desk. People type directions here; Claude on Eugene's Mac picks them up.

Two audiences:
- /api/desk/*  : the dashboard (admins, session cookie).
- /api/agent/* : the Mac bridge and Claude's desk.py helper (bearer key created in
  the dashboard, stored hashed here and in the Mac's Keychain there).

The Mac only ever pulls. Nothing here can spend money: proposals are recorded
for a person to approve (phase 4).
"""
import hashlib
import re
import json
import hmac
import logging
import secrets
import time
from functools import wraps

from flask import Blueprint, jsonify, request

import account_info
import config
import db
import desk_view
import schedules
import settings_store
from auth import admin_required, current_user, owner_required
from performance_api import overview_data
from util import api_error, log_activity

log = logging.getLogger(__name__)

bp = Blueprint("desk", __name__, url_prefix="/api/desk")
agent_bp = Blueprint("agent", __name__, url_prefix="/api/agent")

KINDS = ("question", "review", "research", "creative")
PROPOSAL_KINDS = ("budget", "status", "creative", "targeting", "experiment", "tags", "other")
ACTIVE = ("queued", "claimed", "running")
ONLINE_SECONDS = 90
STALE_MINUTES = 30
MAX_PROMPT = 4000
MAX_REPORT = 200_000
WAIT_MAX = 25

TASK_COLS = """t.id, t.kind, t.prompt, t.campaign_id, c.name AS campaign_name, t.status, t.progress,
               t.summary, t.error, t.created_at, t.claimed_at, t.finished_at, t.updated_at,
               u.name AS created_by_name, t.options, t.scorecard, t.archived_at, t.seen_at, t.queue_rank"""
TASK_FROM = "desk_tasks t LEFT JOIN campaigns c ON c.id = t.campaign_id LEFT JOIN users u ON u.id = t.created_by"


def key_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def bridge_status():
    seen = settings_store.get("bridge_last_seen")
    online = bool(seen) and (time.time() - float(seen)) < ONLINE_SECONDS
    return {
        "has_key": bool(settings_store.get("agent_key_hash")),
        "key_hint": settings_store.get("agent_key_hint"),
        "last_seen": float(seen) if seen else None,
        "online": online,
        "can_stop": not online or version_tuple(settings_store.get("bridge_version") or "0") >= STOP_BRIDGE,
        "host": settings_store.get("bridge_host"),
        "version": settings_store.get("bridge_version"),
        "outdated": bridge_outdated(),
        "claude_sign_in_failed": bool(settings_store.get("bridge_claude_error")),
    }


STOP_BRIDGE = (1, 8)  # desk 1.8 ends the Claude run when its request is stopped here
MIN_BRIDGE = (1, 6)  # desk 1.6 names the task's account; older ones answer every account as account 1
SIGN_IN_TROUBLE = re.compile(r"(invalid api key|oauth token (has )?expired|authentication_error|please run /login|"
                             r"setup-token|not logged in|401 unauthorized|credit balance)", re.I)


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:2])
    except ValueError:
        return (0, 0)


def bridge_outdated():
    """The Mac helper's version when it's too old for several accounts, else None."""
    v = settings_store.get("bridge_version")
    if not v or version_tuple(v) >= MIN_BRIDGE:
        return None
    with __import__("account_ctx").all_accounts():
        n = db.query("SELECT COUNT(*) AS n FROM accounts WHERE archived_at IS NULL", one=True)["n"]
    return v if n > 1 else None


def claude_sign_in_problem(error):
    """True when a failed run says Claude couldn't sign in on the Mac (expired setup-token)."""
    return bool(error and SIGN_IN_TROUBLE.search(error))


def note_claude_sign_in(status, error):
    if status == "done":
        if settings_store.get("bridge_claude_error"):
            settings_store.set("bridge_claude_error", None)
    elif claude_sign_in_problem(error):
        settings_store.set("bridge_claude_error", str(int(time.time())))


def expire_stale():
    """A task the Mac stopped reporting on (sleep, shutdown, crash) is marked failed
    instead of showing "working" forever (every account's)."""
    import account_ctx
    with account_ctx.all_accounts():
        _expire_stale()


def _expire_stale():
    db.execute(
        f"""UPDATE desk_tasks SET status = 'failed', finished_at = now(), updated_at = now(),
                   error = 'The Mac stopped reporting while working on this (asleep or offline). Ask again.'
            WHERE status IN ('claimed', 'running') AND updated_at < now() - interval '{STALE_MINUTES} minutes'"""
    )


def tasks_with_results(where="TRUE", params=(), limit=50):
    tasks = db.query(f"SELECT {TASK_COLS} FROM {TASK_FROM} WHERE {where} ORDER BY t.id DESC LIMIT %s",
                     list(params) + [limit])
    ids = [t["id"] for t in tasks]
    if not ids:
        return tasks
    reports = db.query("SELECT id, task_id, title, body, created_at FROM desk_reports "
                       "WHERE task_id = ANY(%s) ORDER BY id", (ids,))
    proposals = db.query("SELECT * FROM desk_proposals WHERE task_id = ANY(%s) ORDER BY id", (ids,))
    for t in tasks:
        t["reports"] = [r for r in reports if r["task_id"] == t["id"]]
        t["proposals"] = [p for p in proposals if p["task_id"] == t["id"]]
    return tasks


# ---------------------------------------------------------------- dashboard

def desk_story(tasks):
    """Adds to each proposal the ad it is about, what it became and its state in words;
    returns the ads involved and the ad families (desk_view)."""
    pids = [p["id"] for t in tasks for p in t["proposals"]]
    results = {r["proposal_id"]: r["entity_id"] for r in db.query(
        """SELECT proposal_id, entity_id FROM meta_changes
           WHERE action = 'create' AND ok AND proposal_id = ANY(%s)""", (pids,))} if pids else {}
    renders = [t for t in tasks if t["kind"] == "render"]
    by_task = {t["id"]: t for t in tasks}
    ad_ids = set(results.values())
    for t in tasks:
        if (t.get("options") or {}).get("ad_id"):
            ad_ids.add(t["options"]["ad_id"])
        for p in t["proposals"]:
            p["about_ad"] = desk_view.proposal_ad(p, t)
            if p["about_ad"]:
                ad_ids.add(p["about_ad"])
    ads = {a["id"]: a for a in db.query(
        """SELECT id, name, status, effective_status, thumbnail_url, image_url, object_type, title, body
           FROM ads WHERE id = ANY(%s)""", (list(ad_ids),))} if ad_ids else {}

    def state(p, task):
        made = results.get(p["id"])
        follow = desk_view.followup_for(p, renders)
        made_state = None
        if follow:
            p["followup_task"] = follow["id"]
            done = [q for q in by_task[follow["id"]]["proposals"] if q["kind"] == "creative"]
            if done:
                q = done[-1]
                made_state = desk_view.proposal_state(q, ads.get(results.get(q["id"])), None)
                p["made_proposal"] = q["id"]
                q["requested_by"] = p["id"]
        p["result_ad"] = made
        p["state"] = desk_view.proposal_state(p, ads.get(made), follow, made_state)

    for t in tasks:
        for p in t["proposals"]:
            state(p, t)
    return ads, desk_view.families(tasks, results)


@bp.get("")
@admin_required
def overview():
    expire_stale()
    # Anything still open is always here, however old; the rest is the recent history.
    tasks = tasks_with_results("""t.id IN (SELECT id FROM desk_tasks ORDER BY id DESC LIMIT 150)
                                  OR t.status IN ('queued', 'claimed', 'running')
                                  OR EXISTS (SELECT 1 FROM desk_proposals p WHERE p.task_id = t.id AND p.status = 'pending')""", [], 400)
    ads, families = desk_story(tasks)
    return jsonify({
        "bridge": bridge_status(),
        "tasks": tasks,
        "board": desk_view.board(tasks),
        "ads": ads,
        "families": families,
        "campaigns": db.query("SELECT id, name FROM campaigns ORDER BY name"),
    })


@bp.post("/tasks")
@admin_required
def create_task():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind") or "question"
    prompt = (data.get("prompt") or "").strip()
    campaign_id = (data.get("campaign_id") or "").strip() or None
    if kind not in KINDS:
        return api_error("Pick what kind of help you want", 400, field="kind")
    if not prompt:
        return api_error("Tell Claude what you'd like", 400, field="prompt")
    if len(prompt) > MAX_PROMPT:
        return api_error(f"Keep it under {MAX_PROMPT} characters", 400, field="prompt")
    if campaign_id and not db.query("SELECT 1 FROM campaigns WHERE id = %s", (campaign_id,), one=True):
        return api_error("That campaign isn't synced yet", 400, field="campaign_id")
    task = db.execute(
        "INSERT INTO desk_tasks (kind, prompt, campaign_id, created_by) VALUES (%s, %s, %s, %s) RETURNING id",
        (kind, prompt, campaign_id, current_user()["id"]), returning=True,
    )
    log_activity("desk.task_created", subject=str(task["id"]), details={"kind": kind})
    return jsonify(tasks_with_results("t.id = %s", [task["id"]], 1)[0]), 201


@bp.get("/schedules")
@admin_required
def list_schedules():
    return jsonify({"schedules": schedules.listing(), "tz": account_info.tz_name()})


@bp.patch("/schedules/<int:sid>")
@admin_required
def update_schedule(sid):
    s = db.query("SELECT * FROM desk_schedules WHERE id = %s", (sid,), one=True)
    if not s:
        return api_error("That schedule doesn't exist", 404)
    data = request.get_json(silent=True) or {}
    rule = s["rule"]
    if "rule" in data:
        rule, bad = schedules.clean_rule(data["rule"] or {})
        if bad:
            return api_error("Check the schedule's timing", 400, field=bad)
    enabled = bool(data["enabled"]) if "enabled" in data else s["enabled"]
    from datetime import datetime, timezone
    nxt = schedules.next_run(rule, datetime.now(timezone.utc), schedules.tz()) if enabled else None
    db.execute("UPDATE desk_schedules SET rule = %s, enabled = %s, next_run_at = %s WHERE id = %s",
               (json.dumps(rule), enabled, nxt, sid))
    log_activity("desk.schedule", subject=str(sid), details={"name": s["name"], "enabled": enabled, "when": schedules.describe(rule)})
    return list_schedules()


@bp.post("/schedules/<int:sid>/run")
@admin_required
def run_schedule_now(sid):
    s = db.query("SELECT * FROM desk_schedules WHERE id = %s", (sid,), one=True)
    if not s:
        return api_error("That schedule doesn't exist", 404)
    task = db.execute("INSERT INTO desk_tasks (kind, prompt, created_by, options) VALUES (%s, %s, %s, %s) RETURNING id",
                      (s["kind"], s["prompt"], current_user()["id"], json.dumps({"schedule_id": sid, "schedule": s["name"]})), returning=True)
    db.execute("UPDATE desk_schedules SET last_task_id = %s WHERE id = %s", (task["id"], sid))
    log_activity("desk.task_created", subject=str(task["id"]), details={"kind": s["kind"], "schedule": s["name"]})
    return jsonify({"task_id": task["id"]})


@bp.post("/tasks/<int:task_id>/cancel")
@admin_required
def cancel_task(task_id):
    row = db.execute(
        "UPDATE desk_tasks SET status = 'cancelled', finished_at = now(), updated_at = now(), archived_at = now() "
        "WHERE id = %s AND status = 'queued' RETURNING id", (task_id,), returning=True,
    )
    if not row:
        return api_error("Only a task that hasn't started can be cancelled", 409)
    log_activity("desk.task_cancelled", subject=str(task_id))
    return jsonify({"ok": True})


@bp.post("/tasks/<int:task_id>/stop")
@admin_required
def stop_task(task_id):
    """Stops a run the Mac is on. The Mac sees it at its next keep-alive and ends Claude; anything
    Claude tries to post after this is refused."""
    if not bridge_status()["can_stop"]:
        return api_error("This Mac helper is too old to stop a run. Re-run ads/bridge/install.sh on the Mac.", 426)
    row = db.execute(
        """UPDATE desk_tasks SET status = 'cancelled', progress = NULL, finished_at = now(), updated_at = now(), archived_at = now()
           WHERE id = %s AND status IN ('claimed', 'running') RETURNING id""", (task_id,), returning=True)
    if not row:
        return api_error("This request isn't running any more", 409)
    log_activity("desk.task_stopped", subject=str(task_id))
    return jsonify({"ok": True})


@bp.post("/tasks/<int:task_id>/next")
@admin_required
def run_next(task_id):
    """Moves a queued request to the front of the line."""
    row = db.execute(
        """UPDATE desk_tasks SET queue_rank = (SELECT COALESCE(MIN(queue_rank), 0) - 1 FROM desk_tasks WHERE status = 'queued')
           WHERE id = %s AND status = 'queued' RETURNING id""", (task_id,), returning=True)
    if not row:
        return api_error("This request has already started", 409)
    return jsonify({"ok": True})


WAITING_SQL = "EXISTS (SELECT 1 FROM desk_proposals p WHERE p.task_id = desk_tasks.id AND p.status IN ('pending', 'applying'))"


@bp.post("/tasks/<int:task_id>/clear")
@admin_required
def clear_task(task_id):
    """Clears a finished request off the board (or puts it back). Kept for Claude and the ad's story."""
    if (request.get_json(silent=True) or {}).get("restore"):
        row = db.execute("UPDATE desk_tasks SET archived_at = NULL WHERE id = %s AND status IN ('done', 'failed', 'cancelled') RETURNING id",
                         (task_id,), returning=True)
    else:
        row = db.execute(f"""UPDATE desk_tasks SET archived_at = now(), seen_at = COALESCE(seen_at, now())
                             WHERE id = %s AND status IN ('done', 'failed', 'cancelled') AND NOT {WAITING_SQL} RETURNING id""",
                         (task_id,), returning=True)
    if not row:
        return api_error("Only a finished request with nothing waiting on you can be cleared", 409)
    return jsonify({"ok": True})


@bp.post("/clear")
@admin_required
def clear_tray():
    """Empties a tray: 'queue' cancels everything not started, 'finished' clears everything finished."""
    what = (request.get_json(silent=True) or {}).get("what")
    if what == "queue":
        rows = db.execute("""WITH c AS (UPDATE desk_tasks SET status = 'cancelled', finished_at = now(), updated_at = now(), archived_at = now()
                                        WHERE status = 'queued' RETURNING id) SELECT COUNT(*) AS n FROM c""", returning=True)
    elif what == "finished":
        rows = db.execute(f"""WITH c AS (UPDATE desk_tasks SET archived_at = now(), seen_at = COALESCE(seen_at, now())
                                         WHERE archived_at IS NULL AND status IN ('done', 'failed', 'cancelled') AND NOT {WAITING_SQL}
                                         RETURNING id) SELECT COUNT(*) AS n FROM c""", returning=True)
    else:
        return api_error("what must be queue or finished", 400)
    log_activity("desk.cleared", details={"what": what, "count": rows["n"]})
    return jsonify({"cleared": rows["n"]})


@bp.post("/tasks/<int:task_id>/seen")
@admin_required
def mark_seen(task_id):
    db.execute("UPDATE desk_tasks SET seen_at = now() WHERE id = %s AND seen_at IS NULL AND finished_at IS NOT NULL", (task_id,))
    return jsonify({"ok": True})


@bp.post("/tasks/<int:task_id>/again")
@admin_required
def ask_again(task_id):
    old = db.query("SELECT kind, prompt, campaign_id, options FROM desk_tasks WHERE id = %s", (task_id,), one=True)
    if not old:
        return api_error("Task not found", 404)
    task = db.execute(
        "INSERT INTO desk_tasks (kind, prompt, campaign_id, created_by, options) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (old["kind"], old["prompt"], old["campaign_id"], current_user()["id"], json.dumps(old["options"] or {})), returning=True,
    )
    log_activity("desk.task_created", subject=str(task["id"]), details={"kind": old["kind"], "again_of": task_id})
    return jsonify(tasks_with_results("t.id = %s", [task["id"]], 1)[0]), 201


@bp.post("/key")
@owner_required
def create_key():
    """A new Mac key; replaces the old one. Shown once, stored only as a hash."""
    token = "ebdesk_" + secrets.token_urlsafe(32)
    settings_store.set("agent_key_hash", key_hash(token))
    settings_store.set("agent_key_hint", token[-4:])
    log_activity("desk.key_created")
    return jsonify({"key": token, "bridge": bridge_status()})


@bp.delete("/key")
@owner_required
def revoke_key():
    settings_store.set("agent_key_hash", None)
    settings_store.set("agent_key_hint", None)
    log_activity("desk.key_revoked")
    return jsonify({"bridge": bridge_status()})


# ---------------------------------------------------------------- Mac agent

def agent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        stored = settings_store.get("agent_key_hash")
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if not stored or not token or not hmac.compare_digest(stored, key_hash(token)):
            return api_error("This Mac key isn't valid. Create a new one on the Claude page.", 401)
        settings_store.set("bridge_last_seen", str(time.time()))
        host = request.headers.get("X-Bridge-Host")
        if host:
            settings_store.set("bridge_host", host[:80])
            settings_store.set("bridge_version", (request.headers.get("X-Bridge-Version") or "")[:20])
        if bridge_outdated():
            return api_error(f"This Mac helper is too old for several ad accounts (needs "
                             f"{'.'.join(map(str, MIN_BRIDGE))}). Re-run ads/bridge/install.sh on the Mac.", 426)
        return f(*args, **kwargs)
    return wrapper


ADVICE_BRIDGE = (1, 7)  # desk 1.7 lets advice runs render (9:16 for Reels); older ones would only read


def claim_next():
    """The oldest queued task of any account (the Mac works for every account, one task at a time).
    An older Mac helper leaves advice runs waiting rather than run them without their tools."""
    import account_ctx
    skip = "" if version_tuple(settings_store.get("bridge_version") or "0") >= ADVICE_BRIDGE else " AND kind <> 'advice'"
    with account_ctx.all_accounts():
        return db.execute(
            f"""UPDATE desk_tasks SET status = 'claimed', claimed_at = now(), updated_at = now(),
                      progress = 'Picked up by the Mac'
               WHERE id = (SELECT id FROM desk_tasks WHERE status = 'queued'{skip}
                           ORDER BY queue_rank, id LIMIT 1 FOR UPDATE SKIP LOCKED)
               RETURNING id, account_id""",
            returning=True,
        )


def task_payload(task_id):
    rows = tasks_with_results("t.id = %s", [task_id], 1)
    return rows[0] if rows else None


@agent_bp.get("/wait")
@agent_required
def wait():
    """Long poll: returns the next task as soon as one is queued (claiming it), or
    204 after `timeout` seconds. timeout=0 is a plain check."""
    try:
        timeout = max(0, min(WAIT_MAX, int(request.args.get("timeout", "0"))))
    except ValueError:
        timeout = 0
    expire_stale()
    deadline = time.monotonic() + timeout
    while True:
        row = claim_next()
        if row:
            import account_ctx
            with account_ctx.use(row["account_id"]):
                return jsonify({**task_payload(row["id"]), "account_id": row["account_id"]})
        if time.monotonic() >= deadline:
            return ("", 204)
        time.sleep(1)


@agent_bp.get("/tasks/<int:task_id>")
@agent_required
def get_task(task_id):
    import account_ctx
    task = task_payload(task_id)
    return jsonify({**task, "account_id": account_ctx.current()}) if task else api_error("Task not found", 404)


@agent_bp.get("/queue")
@agent_required
def queue():
    import account_ctx
    expire_stale()
    with account_ctx.all_accounts():
        return jsonify({"queued": tasks_with_results("t.status = 'queued'", [], 20),
                        "active": tasks_with_results("t.status IN ('claimed', 'running')", [], 5)})


@agent_bp.post("/tasks/<int:task_id>/status")
@agent_required
def set_status(task_id):
    """running (optionally with a progress line; also a keep-alive), done or failed."""
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("running", "done", "failed"):
        return api_error("status must be running, done or failed", 400)
    progress = (data.get("progress") or "").strip()[:300] or None
    summary = (data.get("summary") or "").strip()[:2000] or None
    error = (data.get("error") or "").strip()[:2000] or None
    if status == "running":
        row = db.execute(
            """UPDATE desk_tasks SET status = 'running', updated_at = now(), progress = COALESCE(%s, progress)
               WHERE id = %s AND status IN ('claimed', 'running') RETURNING id""",
            (progress, task_id), returning=True)
    else:
        row = db.execute(
            """UPDATE desk_tasks SET status = %s, finished_at = now(), updated_at = now(), progress = NULL,
                      summary = COALESCE(%s, summary), error = %s
               WHERE id = %s AND status IN ('claimed', 'running') RETURNING id""",
            (status, summary, error if status == "failed" else None, task_id), returning=True)
        if row:
            log_activity(f"desk.task_{status}", subject=str(task_id), actor="claude")
            note_claude_sign_in(status, error)
            try:
                tell_finished(task_id)
            except Exception:
                log.exception("desk task %s: couldn't queue the alert", task_id)
    if not row:
        return api_error("This task isn't open any more (finished, cancelled or timed out)", 409)
    return jsonify({"ok": True})


def tell_finished(task_id):
    """A finished run reaches its people's phones: the admins for scheduled runs, otherwise
    whoever asked. The summary is the message, so the skill writes it for that."""
    import notify
    t = db.query("SELECT id, kind, prompt, status, summary, error, created_by, options FROM desk_tasks WHERE id = %s", (task_id,), one=True)
    sched = (t["options"] or {}).get("schedule")
    people = notify.admin_ids() if sched or not t["created_by"] else [t["created_by"]]
    what = sched or (t["prompt"][:60] + ("…" if len(t["prompt"]) > 60 else ""))
    ok = t["status"] == "done"
    title = f"{what}: done" if ok else f"{what}: didn't finish"
    lines = [(t["summary"] if ok else t["error"]) or ("See the report." if ok else "No reason given.")]
    waiting = db.query("SELECT COUNT(*) AS n FROM desk_proposals WHERE task_id = %s AND status = 'pending'", (task_id,), one=True)["n"]
    if waiting:
        lines.append(f"{waiting} idea{'s' if waiting != 1 else ''} waiting for your decision.")
    for uid, channel in notify.reach(people, "notify_reminders"):
        notify.queue(uid, channel, "desk", title, lines, notify.link(f"/desk.html#r/{task_id}"),
                     "Open in the console", ref=str(task_id), dedupe_key=f"desk:{task_id}:{uid}")


def _open_task(task_id):
    return db.query("SELECT id FROM desk_tasks WHERE id = %s AND status IN ('claimed', 'running')",
                    (task_id,), one=True)


@agent_bp.post("/tasks/<int:task_id>/report")
@agent_required
def add_report(task_id):
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()[:200]
    body = (data.get("body") or "").strip()
    if not title or not body:
        return api_error("A report needs a title and a body", 400)
    if len(body) > MAX_REPORT:
        return api_error("The report is too long", 400)
    if not _open_task(task_id):
        return api_error("This task isn't open any more", 409)
    row = db.execute("INSERT INTO desk_reports (task_id, title, body) VALUES (%s, %s, %s) RETURNING id",
                     (task_id, title, body), returning=True)
    db.execute("UPDATE desk_tasks SET updated_at = now() WHERE id = %s", (task_id,))
    return jsonify({"id": row["id"]}), 201


def clean_proposal(p):
    def text(key, n=2000):
        v = p.get(key)
        return None if v is None else str(v).strip()[:n] or None
    kind = str(p.get("kind") or "other").strip().lower()
    if kind not in PROPOSAL_KINDS:
        kind = "other"
    out = {"kind": kind, "title": text("title", 200)}
    for key in ("entity_type", "entity_id", "entity_name", "field", "current_value", "proposed_value",
                "rationale", "expected", "rollback"):
        out[key] = text(key)
    out["payload"] = clean_payload(p.get("payload")) if kind == "creative" else None
    if kind == "experiment":
        out["payload"] = clean_experiment(p.get("payload"))
        if not out["payload"]:
            out["kind"] = "other"
    if kind == "tags":
        out["payload"] = clean_tags(p.get("payload"))
        if not out["payload"]:
            out["kind"] = "other"
    return out


def clean_tags(raw):
    """Concept tags Claude suggests for one ad: {"ad_id": "...", "tags": {"hook": "Question", ...}}."""
    import concepts
    if not isinstance(raw, dict) or not db.query("SELECT 1 FROM ads WHERE id = %s", (str(raw.get("ad_id") or ""),), one=True):
        return None
    tags = {d: concepts.clean_value(v) for d, v in (raw.get("tags") or {}).items() if d in concepts.DIMENSIONS and concepts.clean_value(v)}
    return {"ad_id": str(raw["ad_id"]), "tags": tags} if tags else None


def clean_experiment(raw):
    """A test Claude suggests tracking: same fields as the Tests page form. Invalid → None."""
    import experiments_api
    if not isinstance(raw, dict):
        return None
    fields, err = experiments_api.clean({**raw, "start_day": raw.get("start_day") or experiments_api.ex.account_today().isoformat()})
    if err:
        return None
    ads, sets = experiments_api.names_for(fields["arms"])
    for a in fields["arms"]:
        a["names"] = [ads.get(i, "an ad") for i in a["ad_ids"]] + [f"Ad set: {sets.get(i, '')}" for i in a["adset_ids"]]
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in fields.items() if k not in ("status", "winner", "verdict")}


def clean_payload(raw):
    """A new ad Claude suggests: the ad it starts from, the words, and the media
    ('same' = keep the starting ad's image or video)."""
    if not isinstance(raw, dict):
        return None
    def text(key, n):
        v = raw.get(key)
        return str(v).strip()[:n] if v not in (None, "") else None
    vertical = raw.get("vertical") if isinstance(raw.get("vertical"), dict) else {}
    if "update_ad" in raw or vertical:
        # Meta's Reels advice: put a 9:16 video on the running ad itself (same words, same form).
        vid = str(vertical.get("video_id") or "")
        if raw.get("update_ad") is not True or not vid.isdigit() or not text("template_ad_id", 32):
            return None
        return {"template_ad_id": text("template_ad_id", 32), "update_ad": True, "vertical": {"video_id": vid[:32]},
                "name": text("name", 200)}
    media = raw.get("media") if isinstance(raw.get("media"), dict) else {"kind": "same"}
    kind = media.get("kind") if media.get("kind") in ("same", "image", "video") else "same"
    clean_media = {"kind": kind}
    if kind == "image" and media.get("hash"):
        clean_media["hash"] = str(media["hash"])[:64]
    elif kind == "video" and media.get("video_id"):
        clean_media["video_id"] = str(media["video_id"])[:32]
    elif kind != "same":
        clean_media = {"kind": "same"}
    out = {"template_ad_id": text("template_ad_id", 32), "adset_id": text("adset_id", 32),
           "name": text("name", 200), "title": text("title", 255), "body": text("body", 5000),
           "cta_type": text("cta_type", 32), "media": clean_media, "preview_url": text("preview_url", 1000)}
    return out if out["template_ad_id"] and out["title"] and out["body"] else None


@agent_bp.post("/tasks/<int:task_id>/proposals")
@agent_required
def add_proposals(task_id):
    data = request.get_json(silent=True) or {}
    items = data.get("proposals") if isinstance(data.get("proposals"), list) else []
    items = [clean_proposal(p) for p in items[:20] if isinstance(p, dict)]
    if not items or any(not p["title"] for p in items):
        return api_error("Each proposal needs at least a title", 400)
    if not _open_task(task_id):
        return api_error("This task isn't open any more", 409)
    cols = list(items[0].keys())
    for p in items:
        values = [json.dumps(p[c]) if c == "payload" and p[c] is not None else p[c] for c in cols]
        db.execute(f"INSERT INTO desk_proposals (task_id, {', '.join(cols)}) VALUES (%s, {', '.join(['%s'] * len(cols))})",
                   [task_id] + values)
    db.execute("UPDATE desk_tasks SET updated_at = now() WHERE id = %s", (task_id,))
    return jsonify({"added": len(items)}), 201


@agent_bp.get("/snapshot")
@agent_required
def snapshot():
    """What the dashboard knows that Meta doesn't: lead quality from the inbox.
    No names, emails or phone numbers: Claude doesn't need them to judge ads."""
    try:
        days = int(request.args.get("range", "7"))
    except ValueError:
        days = 7
    days = days if days in (7, 14, 30) else 7
    perf = overview_data({"id": None, "role": "admin"}, days)
    stages = db.query(
        """SELECT COALESCE(ad_name, 'unknown ad') AS ad, status, COUNT(*) AS n FROM leads
           WHERE NOT is_test AND created_time >= now() - %s * interval '1 day'
           GROUP BY 1, 2 ORDER BY 1, 2""", (days,))
    types = db.query(
        """SELECT COALESCE(NULLIF(business_type, ''), 'not given') AS business_type, COUNT(*) AS n,
                  COUNT(*) FILTER (WHERE status IN ('qualified', 'won')) AS qualified
           FROM leads WHERE NOT is_test AND created_time >= now() - %s * interval '1 day'
           GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", (days,))
    speed = db.query(
        """SELECT COUNT(*) FILTER (WHERE first_contacted_at IS NOT NULL) AS contacted,
                  COUNT(*) AS total,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM first_contacted_at - created_time) / 60)
                      FILTER (WHERE first_contacted_at IS NOT NULL) AS median_minutes_to_contact
           FROM leads WHERE NOT is_test AND created_time >= now() - %s * interval '1 day'""", (days,), one=True)
    import experiments_api
    tests = [experiments_api.summary(r) for r in db.query(
        f"SELECT {experiments_api.COLS} FROM experiments WHERE status = 'running' OR closed_at > now() - interval '30 days' ORDER BY start_day DESC")]
    import concepts_api
    perf_tags = concepts_api.tags_for([a["id"] for a in perf["ads"]])
    for a in perf["ads"]:
        a["tags"] = perf_tags.get(a["id"], {})
    import account_ctx
    import accounts_api
    return jsonify({"account": {"id": account_ctx.current(), "name": accounts_api.name_of(account_ctx.current())},
                    "performance": perf, "lead_stages_by_ad": stages, "lead_business_types": types,
                    "speed_to_lead": speed, "campaigns": db.query("SELECT * FROM campaigns ORDER BY name"),
                    "experiments": tests})


@agent_bp.get("/history")
@agent_required
def history():
    """Recent finished work, so a new run knows what was already said and proposed."""
    rows = tasks_with_results("t.status = 'done'", [], 10)
    for t in rows:
        t["reports"] = [{"title": r["title"], "created_at": r["created_at"]} for r in t["reports"]]
    return jsonify(rows)


@agent_bp.post("/tasks/<int:task_id>/scorecard")
@agent_required
def add_scorecard(task_id):
    """A polish run's results: one row per pass with a 1-5 score, findings and fixes."""
    data = request.get_json(silent=True) or {}
    rows = data.get("passes") if isinstance(data.get("passes"), list) else []
    clean = []
    for r in rows[:20]:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        try:
            score = max(1, min(5, int(r.get("score"))))
        except (TypeError, ValueError):
            score = None
        clean.append({"id": str(r["id"])[:40], "label": str(r.get("label") or r["id"])[:80], "score": score,
                      "verdict": str(r.get("verdict") or "")[:300],
                      "findings": [str(x)[:500] for x in (r.get("findings") or [])][:8],
                      "fixes": [str(x)[:500] for x in (r.get("fixes") or [])][:8]})
    if not clean:
        return api_error("A scorecard needs at least one pass with an id", 400)
    if not _open_task(task_id):
        return api_error("This task isn't open any more", 409)
    scores = [r["score"] for r in clean if r["score"]]
    card = {"passes": clean, "overall": round(sum(scores) / len(scores), 1) if scores else None,
            "headline": str(data.get("headline") or "")[:300]}
    db.execute("UPDATE desk_tasks SET scorecard = %s, updated_at = now() WHERE id = %s", (json.dumps(card), task_id))
    return jsonify({"ok": True, "overall": card["overall"]})


@agent_bp.post("/media/upload")
@agent_required
def agent_upload():
    """A rendered image or video from a 'Make a new version' run, into the ad account's
    media library (nothing is shown to anyone until an ad using it is approved and turned on)."""
    import ads_api
    return ads_api.upload_file(request.files.get("file"), actor="claude")
