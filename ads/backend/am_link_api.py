"""AM-A: the Ads Manager link's routes.

- /api/am-link*        : Settings → Ads Manager link (owner: the connection; owner and this account's admins: this account).
- /api/agent/link/*    : the Mac (bearer key). The server decides what is read and for which account: each pass is made
  for one console account and the ad account it is bound to, and a push is kept only under that pass. `X-Account` means
  nothing here, and a Claude desk run (`X-Desk-Claim`) is refused outright.

Reads only: no route here writes to Meta, and nothing read here turns into a Meta write."""
import json
import secrets
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import am_link
import db
import desk_api
import settings_store
from auth import admin_required, current_user, is_owner, owner_required
from util import api_error, log_activity

bp = Blueprint("am_link", __name__, url_prefix="/api/am-link")
agent_bp = Blueprint("am_link_agent", __name__, url_prefix="/api/agent/link")

PASS_HEADER = "X-Link-Pass"
LINK_BRIDGE = (3, 1)  # desk 3.1 carries the link client (amlink.py)
REDIRECT_URI = "http://127.0.0.1:47615/callback"  # loopback IP, not "localhost" (RFC 8252 §7.3; the Mac listens on 127.0.0.1)
PLAN_MAX = 25
STATES_FROM_MAC = ("not_connected", "connecting", "connected", "expired", "refused", "fallback")
RUN_COLS = "id, account_id, ad_account_id, kinds, scope, mode, status, error, pushed, created_at, finished_at, forced_by"


def utcnow():
    return datetime.now(timezone.utc)


def cut(text, n=300):
    text = " ".join(str(text or "").split())
    return text[:n] or None


# ---------------------------------------------------------------- shared reads

def link_row():
    return db.query("SELECT * FROM am_link WHERE id = 1", one=True)


def set_link(**fields):
    cols = ", ".join(f"{k} = %s" for k in fields)
    db.execute(f"UPDATE am_link SET {cols}, updated_at = now() WHERE id = 1", tuple(fields.values()))


def ad_account(account_id=None):
    return am_link.digits(settings_store.get("meta_ad_account_id", account_id=account_id))


def account_reading(account_id=None):
    """"on", "off" or "changed" (am_link.reading_on): only an ad account the owner approved is read with his login."""
    acct = account_ctx.current() if account_id is None else account_id
    return am_link.reading_on(settings_store.get("am_link_on", account_id=acct), ad_account(acct), acct == account_ctx.DEFAULT)


def account_on(account_id=None):
    return account_reading(account_id) == "on"


def last_reads():
    """{kind: (fetched_at, via)} of this account's latest account-level reads."""
    rows = db.query("SELECT kind, fetched_at, via FROM am_snapshots WHERE scope = ''")
    return {r["kind"]: (r["fetched_at"], r["via"]) for r in rows}


def last_pass_at():
    row = db.query("SELECT MAX(created_at) AS at FROM am_link_runs", one=True)
    return row["at"] if row else None


def own_entity_ids():
    """This account's synced campaign, ad set and ad ids (row-level security keeps them to the current account)."""
    rows = db.query("SELECT id FROM campaigns UNION SELECT id FROM adsets UNION SELECT id FROM ads")
    return {r["id"] for r in rows}


def helper_ok():
    return desk_api.version_tuple(settings_store.get("bridge_version") or "0") >= LINK_BRIDGE


def snapshot_source(kind, scope=""):
    """The source line of one stored kind in this account (AM-B / AM-E blocks use it): {words, fetched_at, stale, away}."""
    row = db.query("SELECT fetched_at, via FROM am_snapshots WHERE kind = %s AND scope = %s", (kind, scope), one=True)
    link = link_row()
    return am_link.source(row["fetched_at"] if row else None, link["state"], last_pass_at(), utcnow(), account_info.tz(),
                          row["via"] if row else "direct", kind=kind, mac_online=bool(desk_api.bridge_status().get("online")),
                          reading_on=account_on())


# ---------------------------------------------------------------- link_down alert (console-wide, under account 1)

def raise_link_down():
    import alerts
    with account_ctx.use(account_ctx.DEFAULT):
        found = alerts.link_alert(alerts.link_snapshot(utcnow()), alerts.saved_rules()["link_down"], account_info.today())
        if found:
            alerts.raise_found(found)


def close_link_down():
    with account_ctx.use(account_ctx.DEFAULT):
        db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'link_down' AND resolved_at IS NULL")


# ---------------------------------------------------------------- Settings

def runs_view(limit=5):
    # AM-E: one ad's picture is a pass of its own (up to 12 a day); Settings lists the reads of the account.
    rows = db.query(f"SELECT {RUN_COLS} FROM am_link_runs WHERE scope IS NULL ORDER BY id DESC LIMIT %s", (limit,))
    return [{"id": r["id"], "at": r["created_at"].isoformat(), "kinds": list(r["kinds"]), "mode": r["mode"], "status": r["status"],
             "error": r["error"], "kept": sum(int(v) for v in (r["pushed"] or {}).values()), "forced": r["forced_by"] is not None}
            for r in rows]


def check_after():
    """Seconds until Check now may be pressed again in this account (0 = now)."""
    at = settings_store.get("am_link_checked_at")
    left = (float(at) + am_link.CHECK_NOW_GAP.total_seconds() - time.time()) if at else 0
    return max(0, int(left + 0.999))


def can_check(owner, mode, live, on, ad):
    """Check now: the link working, this account read, an ad account set. Through Claude every read is a paid Claude run
    on Eugene's Mac, so then only the owner may force one."""
    return bool(live and on and ad and (owner or mode == "direct"))


def view(user):
    """Account admins see only this account: its reads and their times, the link's state in words, and whether the Mac's
    helper can do it. The Facebook name, the Mac's comings and goings and other accounts' read times are the owner's."""
    owner = is_owner(user)
    link = link_row()
    now, tz = utcnow(), account_info.tz()
    bridge = desk_api.bridge_status()
    acct = account_ctx.current()
    name = db.query("SELECT name FROM accounts WHERE id = %s", (acct,), one=True)
    reads = last_reads()
    runs = runs_view()
    mode = "claude" if link["state"] == "fallback" else "direct"
    newest = max(reads.values(), key=lambda r: r[0], default=(None, "direct"))
    reading, ad = account_reading(), ad_account()
    live = link["state"] in ("connected", "fallback")
    out = {
        "owner": owner,
        "link": {"state": link["state"], "words": am_link.link_status_words(link["state"]), "helper_ok": helper_ok(), "mode": mode,
                 "last_ok_at": newest[0] and newest[0].isoformat()},
        "account": {"id": acct, "name": name and name["name"], "on": reading == "on", "reading": reading, "ad_account_id": ad,
                    "can_turn_on": owner, "no_access": settings_store.get("am_link_no_access") == "1",
                    "groups": am_link.kind_groups({k: v[0] for k, v in reads.items()}, mode, tz, now),
                    "source": am_link.source(newest[0], link["state"], last_pass_at(), now, tz, newest[1],
                                             mac_online=bool(bridge.get("online")), reading_on=reading == "on"),
                    "can_check": can_check(owner, mode, live, reading == "on", ad), "check_after": check_after(), "runs": runs},
    }
    if owner:
        out["link"].update(connected_as=link["connected_as"], connected_at=link["connected_at"] and link["connected_at"].isoformat(),
                           last_ok_at=link["last_ok_at"] and link["last_ok_at"].isoformat(),
                           helper_version=settings_store.get("bridge_version"), mac_online=bool(bridge.get("online")),
                           mac_set_up=bool(bridge.get("has_key")), scope=link["scope"],
                           last_error=link["last_error"], fallback_reason=link["fallback_reason"], use_app=link["use_app"],
                           client_kind=link["client_kind"], redirect_uri=REDIRECT_URI,
                           app_id_set=bool(settings_store.get("meta_app_id", account_id=account_ctx.DEFAULT)),
                           connect_requested_at=link["connect_requested_at"] and link["connect_requested_at"].isoformat())
    return out


@bp.get("")
@admin_required
def get_link():
    return jsonify(view(current_user()))


@bp.post("/connect")
@owner_required
def connect():
    user = current_user()
    if not helper_ok():
        return api_error("Update the Mac helper first (run ads/bridge/install.sh on the Mac), then press Connect.", 409)
    set_link(state="connecting", connect_requested_at=utcnow(), connect_requested_by=user["id"], last_error=None)
    log_activity("am_link.connect")
    return jsonify(view(user))


@bp.post("/disconnect")
@owner_required
def disconnect():
    """Disconnect, or Cancel while waiting for the Mac. Only a Mac that may hold a login (it signed in once, and its helper
    has the link) is asked to delete it ("off" until it confirms); otherwise there is nothing to wait for."""
    link = link_row()
    if link["connected_at"] is None or not helper_ok():
        set_link(state="not_connected", connect_requested_at=None, client_kind=None, connected_as=None, fallback_reason=None,
                 last_error=None, scope=None)
    else:
        set_link(state="off", connect_requested_at=None, client_kind=None)
    log_activity("am_link.disconnect")
    return jsonify(view(current_user()))


@bp.patch("")
@owner_required
def update_link():
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("use_app"), bool):
        return api_error("Send {\"use_app\": true or false}", 400)
    set_link(use_app=data["use_app"])
    log_activity("am_link.use_app", details={"on": data["use_app"]})
    return jsonify(view(current_user()))


@bp.patch("/account")
@admin_required
def update_account():
    """Off: this account's admins may. On: only the owner, for the ad account the account holds now (the Mac reads with
    his own Facebook login, so he decides which ad accounts it reads for whom)."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("on"), bool):
        return api_error("Send {\"on\": true or false}", 400)
    if data["on"]:
        if not is_owner(current_user()):
            return api_error("Only the console owner can switch reading through the Mac on.", 403)
        if not ad_account():
            return api_error("This account has no ad account yet (Settings → Meta connection).", 409)
    settings_store.set("am_link_on", ad_account() if data["on"] else "0")
    log_activity("am_link.account", details={"on": data["on"], "ad_account_id": ad_account() if data["on"] else None})
    return jsonify(view(current_user()))


@bp.post("/check")
@admin_required
def check_now():
    """Check Ads Manager now: the next plan reads every kind for this account (within a second while the Mac waits)."""
    link = link_row()
    if link["state"] not in ("connected", "fallback"):
        return api_error("Connect the Ads Manager link first (Settings → Ads Manager link).", 409)
    if not account_on():
        return api_error("Reading this account through the Mac is off. Switch it on first.", 409)
    if not ad_account():
        return api_error("This account has no ad account yet (Settings → Meta connection).", 409)
    if link["state"] == "fallback" and not is_owner(current_user()):
        return api_error("Through Claude each read is a Claude run on the owner's Mac, so only the owner can ask for one now.", 403)
    if check_after():
        return api_error("Checked a moment ago. Try again in a minute.", 429)
    settings_store.set("am_link_checked_at", str(time.time()))
    settings_store.set("am_link_force", str(current_user()["id"]))
    log_activity("am_link.check")
    return jsonify(view(current_user()))


# ---------------------------------------------------------------- the Mac

def link_agent(f):
    """The Mac's key, never a Claude desk run's pass: a run reads Meta for its own request, it never feeds the link."""
    inner = desk_api.agent_required(f)

    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get(desk_api.CLAIM_HEADER):
            return api_error("A Claude desk run can't use the Ads Manager link", 403)
        return inner(*args, **kwargs)
    return wrapper


def run_for_pass():
    """The am_link_runs row the X-Link-Pass header names (any account), or None."""
    token = request.headers.get(PASS_HEADER) or ""
    if not token:
        return None
    with account_ctx.all_accounts():
        return db.query(f"SELECT {RUN_COLS} FROM am_link_runs WHERE pass_hash = %s", (desk_api.key_hash(token),), one=True)


def expire_open():
    with account_ctx.all_accounts():
        db.execute("UPDATE am_link_runs SET status = 'expired', finished_at = now(), error = 'Not finished within 30 minutes' "
                   "WHERE status = 'open' AND created_at < now() - %s", (am_link.RUN_OPEN,))


SCREENS_ASKED = "am_screens_asked"  # AM-E: {ad id: when Get Meta's picture was pressed}, handed out before anything else
ASK_KEEP = 1800  # seconds an unanswered ask stays in the queue
ASK_GAP = 120    # one ask per ad per 2 minutes


def screens_asked():
    try:
        raw = json.loads(settings_store.get(SCREENS_ASKED) or "{}")
    except ValueError:
        raw = {}
    now = time.time()
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, (int, float)) and now - v < ASK_KEEP}


def ask_screen(ad_id):
    """Get Meta's picture: the next plan reads this ad's picture first. Returns seconds to wait when asked a moment ago."""
    asked = screens_asked()
    last = db.query("SELECT EXTRACT(EPOCH FROM now() - MAX(created_at)) AS ago FROM am_link_runs WHERE scope = %s", (ad_id,), one=True)
    ago = min([time.time() - asked[ad_id]] if ad_id in asked else [], default=None)
    for a in (ago, float(last["ago"]) if last and last["ago"] is not None else None):
        if a is not None and a < ASK_GAP:
            return int(ASK_GAP - a) + 1
    asked[ad_id] = time.time()
    settings_store.set(SCREENS_ASKED, json.dumps(dict(sorted(asked.items(), key=lambda kv: kv[1])[-10:])))
    return 0


def asked_screen():
    """The ad whose picture someone asked for (oldest ask first) that this account holds, or None."""
    asked = screens_asked()
    if not asked:
        return None
    held = {r["id"] for r in db.query("SELECT id FROM ads WHERE id = ANY(%s)", (list(asked),))}
    return next((ad_id for ad_id, _ in sorted(asked.items(), key=lambda kv: kv[1]) if ad_id in held), None)


def daily_screen(now):
    """The next ad of the daily round (meta_extras.screenshot_targets: the busiest delivering ads), or None."""
    import meta_extras
    ads = db.query("""SELECT a.id, a.effective_status FROM ads a
                      LEFT JOIN (SELECT ad_id, SUM(spend_cents) AS s FROM ad_daily WHERE day >= CURRENT_DATE - 7 GROUP BY ad_id) d
                          ON d.ad_id = a.id
                      WHERE a.effective_status = 'ACTIVE' ORDER BY COALESCE(d.s, 0) DESC, a.id""")
    have = {}
    for r in db.query("""SELECT ad_id AS id, MAX(fetched_at) AS at FROM am_screens GROUP BY ad_id
                         UNION ALL SELECT scope, MAX(created_at) FROM am_link_runs WHERE scope IS NOT NULL GROUP BY scope"""):
        if r["at"] is not None:
            have[r["id"]] = max(have.get(r["id"]) or r["at"], r["at"])
    due = meta_extras.screenshot_targets(ads, have, now)
    return due[0] if due else None


def drop_ask(ad_id):
    asked = screens_asked()
    if asked.pop(ad_id, None) is not None:
        settings_store.set(SCREENS_ASKED, json.dumps(asked))


def make_runs(mode):
    """One pass per open account whose ad account is set, whose switch is on, that has no pass open and has something due.
    AM-E: a pass may instead read one ad's picture (scope = the ad): an ask from the ad page first, the daily round only
    when nothing else is due. Pictures are read by the Mac's own link only (a Claude run can't pass an image on)."""
    now = utcnow()
    with account_ctx.all_accounts():
        accounts = [r["id"] for r in db.query("SELECT id FROM accounts WHERE archived_at IS NULL ORDER BY id")]
    out = []
    for acct in accounts:
        with account_ctx.use(acct):
            ad = ad_account()
            if not ad or not account_on():
                continue
            if db.query("SELECT 1 FROM am_link_runs WHERE status = 'open' LIMIT 1", one=True):
                continue
            forced = settings_store.get("am_link_force")
            scope = asked_screen() if mode == "direct" else None
            asked = scope is not None
            kinds = ["screenshots"] if asked else am_link.due_kinds({k: v[0] for k, v in last_reads().items()},
                                                                     now.astimezone(account_info.tz()), mode, bool(forced))
            if not kinds and mode == "direct":
                scope = daily_screen(now)
                kinds = ["screenshots"] if scope else []
            if not kinds:
                continue
            account_pass = scope is None
            token = secrets.token_urlsafe(32)
            # Two plans at once (a long poll still running while the Mac asks again): the unique index on open passes
            # lets only one of them make this account's pass.
            row = db.execute("INSERT INTO am_link_runs (account_id, pass_hash, ad_account_id, kinds, scope, mode, forced_by) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (account_id) WHERE status = 'open' DO NOTHING RETURNING id",
                             (acct, desk_api.key_hash(token), ad, kinds, scope, mode,
                              int(forced) if account_pass and forced and forced.isdigit() else None),
                             returning=True)
            if not row:
                continue
            if forced and account_pass:
                settings_store.set("am_link_force", None)
            if asked:
                drop_ask(scope)
            out.append({"pass": token, "run_id": row["id"], "account_id": acct, "ad_account_id": ad, "kinds": kinds, "scope": scope})
    return out


def make_plan():
    link = link_row()
    connect = None
    if link["connect_requested_at"] and link["state"] == "connecting":
        app_id = settings_store.get("meta_app_id", account_id=account_ctx.DEFAULT) if link["use_app"] else None
        connect = {"use_app": bool(link["use_app"] and app_id), "app_id": app_id or None, "redirect_uri": REDIRECT_URI,
                   "requested_at": link["connect_requested_at"].isoformat()}
    mode = "claude" if link["state"] == "fallback" else "direct"
    runs = make_runs(mode) if link["state"] in ("connected", "fallback") and not connect else []
    return {"mode": mode, "state": link["state"], "connect": connect, "disconnect": link["state"] == "off", "runs": runs}


@agent_bp.get("/plan")
@link_agent
def link_plan():
    """Long poll (like /api/agent/wait): what the Mac should read now, or nothing after `timeout` seconds."""
    try:
        timeout = max(0, min(PLAN_MAX, int(request.args.get("timeout", "0"))))
    except ValueError:
        timeout = 0
    version = (request.headers.get("X-Bridge-Version") or "")[:20]
    if version:
        set_link(helper_version=version)
    expire_open()
    deadline = time.monotonic() + timeout
    while True:
        plan = make_plan()
        if plan["runs"] or plan["connect"] or plan["disconnect"] or time.monotonic() >= deadline:
            return jsonify(plan)
        time.sleep(1)


@agent_bp.post("/status")
@link_agent
def link_status():
    """The Mac says how its login stands (console-wide)."""
    data = request.get_json(silent=True) or {}
    state = data.get("state")
    if state not in STATES_FROM_MAC:
        return api_error(f"state must be one of {', '.join(STATES_FROM_MAC)}", 400)
    link = link_row()
    if link["state"] == "off" and state != "not_connected":
        return jsonify({"state": "off", "ignored": True})  # a disconnect is waiting: only its confirmation counts
    if link["state"] == "not_connected" and not link["connect_requested_at"] and state in ("connected", "fallback"):
        # A login that finished after Cancel: the Mac is asked to delete it again.
        set_link(state="off")
        return jsonify({"state": "off", "ignored": True})
    kind = data.get("client_kind") if data.get("client_kind") in ("dcr", "app", "claude") else link["client_kind"]
    fields = {"state": state, "client_kind": kind, "last_error": cut(data.get("error")),
              "scope": cut(data.get("scope"), 200) if state == "connected" and data.get("scope") else link["scope"],
              "fallback_reason": cut(data.get("fallback_reason")) if state == "fallback" else None}
    if state != "connecting":
        fields["connect_requested_at"] = None
    if state == "connected":
        fields["connected_as"] = cut(data.get("connected_as"), 120) or link["connected_as"]
        if link["state"] != "connected":
            fields["connected_at"] = utcnow()
    if state == "fallback" and not link["connected_at"]:
        fields["connected_at"] = utcnow()
    if state == "not_connected":
        fields.update(connected_as=None, connected_at=None, client_kind=None, fallback_reason=None, scope=None)
    set_link(**fields)
    if state != link["state"]:
        with account_ctx.use(account_ctx.DEFAULT):
            log_activity("am_link.state", details={"from": link["state"], "to": state}, actor="mac")
    if state in ("expired", "refused"):
        raise_link_down()
    elif state in ("connected", "fallback", "not_connected"):
        close_link_down()
    return jsonify({"state": state})


@agent_bp.get("/runs/<int:run_id>")
@link_agent
def link_run(run_id):
    """What one pass reads, with the tool and the arguments per kind (the fallback Claude run prints this)."""
    run = run_for_pass()
    if not run or run["id"] != run_id:
        return api_error("This link pass is for another read", 403)
    return jsonify({"run_id": run["id"], "account_id": run["account_id"], "ad_account_id": f"act_{run['ad_account_id']}",
                    "kinds": list(run["kinds"]), "mode": run["mode"], "status": run["status"],
                    "reads": [{"kind": k, "tool": am_link.TOOLS[k], "arguments": am_link.tool_args(k, run["ad_account_id"], run["scope"])}
                              for k in run["kinds"]]})


def _when(value):
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@agent_bp.post("/push")
@link_agent
def link_push():
    """One kind's raw answer from Meta. Kept only under the pass's account, for that account's current ad account, for a
    kind the pass asked for, within 30 minutes, and only the whitelisted fields of it."""
    run = run_for_pass()
    if not run:
        return api_error("This link pass isn't known.", 409)
    account_ctx.set_current(run["account_id"])
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return api_error("Send JSON {kind, ad_account_id, fetched_at, via, tool, result}", 400)
    now = utcnow()
    why = am_link.push_refusal(run, ad_account(), body, now, request.content_length)
    if why:
        return api_error(why, 409)
    kind = body["kind"]
    if am_link.foreign_account(body.get("result"), run["ad_account_id"]):
        why = "Meta's answer names another ad account; nothing was kept."
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s", (f"{am_link.KIND_WORDS[kind]}: {why}", run["id"]))
        return api_error(why, 409)
    if kind == "screenshots":
        return keep_picture(run, body, now)
    data, why = am_link.normalize(kind, body.get("result"))
    if why:
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s", (f"{am_link.KIND_WORDS[kind]}: {why}", run["id"]))
        return api_error(why, 422)
    data, dropped = am_link.keep_own(data, own_entity_ids(), run["ad_account_id"])
    if dropped:
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s",
                   (f"{am_link.KIND_WORDS[kind]}: {dropped} row{'s' if dropped != 1 else ''} about ads outside this account left out", run["id"]))
    fetched = am_link.clamp_fetched(_when(body.get("fetched_at")), run["created_at"], now)
    if kind == "drafts":  # AM-B: the drafts themselves go to am_drafts; the snapshot keeps the read's time and count
        import am_drafts
        import drafts_api
        data = {"drafts": drafts_api.store(run, am_drafts.normalize(body.get("result")), data["complete"], fetched), "complete": data["complete"]}
    db.execute("""INSERT INTO am_snapshots (kind, scope, data, fetched_at, run_id, via) VALUES (%s, '', %s, %s, %s, %s)
                  ON CONFLICT (account_id, kind, scope) DO UPDATE SET data = EXCLUDED.data, fetched_at = EXCLUDED.fetched_at,
                      run_id = EXCLUDED.run_id, via = EXCLUDED.via""",
               (kind, json.dumps(data), fetched, run["id"], body["via"]))
    kept = len(data.get("rows", [])) if "rows" in data else data["drafts"] if kind == "drafts" else 1
    db.execute("UPDATE am_link_runs SET pushed = pushed || %s WHERE id = %s", (json.dumps({kind: kept}), run["id"]))
    set_link(last_ok_at=now)
    if kind in LINK_ALERTS:
        link_alerts(kind, data["rows"])
    return jsonify({"kept": kept, "kind": kind})


# ---------------------------------------------------------------- AM-E: alerts and pictures from a push

LINK_ALERTS = {"anomalies": "meta_anomaly", "ad_errors": "meta_ad_error"}


def known_entities():
    """{id: {level, name, campaign_id}} of this account's campaigns, ad sets and ads (row-level security)."""
    out = {}
    for level, sql in (("campaign", "SELECT id, name, id AS campaign_id FROM campaigns"),
                       ("adset", "SELECT id, name, campaign_id FROM adsets"), ("ad", "SELECT id, name, campaign_id FROM ads")):
        for r in db.query(sql):
            out[r["id"]] = {"level": level, "name": r["name"], "campaign_id": r["campaign_id"]}
    return out


def link_alerts(kind, rows):
    """A fresh read of Meta's unusual changes or error messages: new ones are raised (snoozes as usual), the ones it no
    longer lists close and their snoozes end. Only a read closes them (alerts.LINK_RULES), never the hourly run."""
    import alerts
    import meta_extras
    import snooze
    rule = LINK_ALERTS[kind]
    make = meta_extras.anomaly_alerts if kind == "anomalies" else meta_extras.error_alerts
    found = make(rows, known_entities(), account_info.today(), on=alerts.saved_rules()[rule]["on"])
    if found:
        alerts.raise_found(found)
    now = utcnow()
    pairs = {(a["rule"], a["entity_id"]) for a in found}
    opened = db.query("SELECT id, rule, entity_id, created_at FROM alerts WHERE resolved_at IS NULL AND kind = 'condition' AND rule = %s", (rule,))
    gone = meta_extras.to_close(opened, pairs, now, stale=False, rules={rule})
    if gone:
        db.execute("UPDATE alerts SET resolved_at = now() WHERE id = ANY(%s)", (gone,))
    live = db.query("SELECT id, rule, entity_id, mode, until FROM alert_snoozes WHERE ended_at IS NULL AND rule = %s", (rule,))
    for sid, reason in snooze.sweep(live, pairs, now, False):
        alerts.end_snooze(sid, reason)


def keep_picture(run, body, now):
    """One ad's picture as Ads Manager renders it: only for an ad of the pass's account (the pass names it), typed from its
    bytes (PNG, JPEG or WebP), 3 MB at most. Anything else is refused and the older picture stays. The pass asks for
    Meta's default view, so the picture is kept as that ('') whatever placement Meta's answer names."""
    import hashlib
    import meta_extras
    ad_id = run.get("scope")
    if not ad_id or not db.query("SELECT 1 FROM ads WHERE id = %s", (ad_id,), one=True):
        why = "This ad isn't in this account; nothing was kept."
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s", (f"Meta's picture: {why}", run["id"]))
        return api_error(why, 409)
    pic, why = meta_extras.picture(body.get("result"))
    if why:
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s", (f"Meta's picture: {why}", run["id"]))
        return api_error(why, 422)
    fetched = am_link.clamp_fetched(_when(body.get("fetched_at")), run["created_at"], now)
    db.execute("""INSERT INTO am_screens (ad_id, placement, mime, width, height, size_bytes, sha256, body, fetched_at, run_id, via)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                  ON CONFLICT (account_id, ad_id, placement) DO UPDATE SET mime = EXCLUDED.mime, width = EXCLUDED.width,
                      height = EXCLUDED.height, size_bytes = EXCLUDED.size_bytes, sha256 = EXCLUDED.sha256, body = EXCLUDED.body,
                      fetched_at = EXCLUDED.fetched_at, run_id = EXCLUDED.run_id, via = EXCLUDED.via""",
               (ad_id, "", pic["mime"], pic["width"], pic["height"], len(pic["bytes"]),
                hashlib.sha256(pic["bytes"]).hexdigest(), pic["bytes"], fetched, run["id"], body["via"]))
    db.execute("UPDATE am_link_runs SET pushed = pushed || %s WHERE id = %s", (json.dumps({"screenshots": 1}), run["id"]))
    set_link(last_ok_at=now)
    return jsonify({"kept": 1, "kind": "screenshots"})


@agent_bp.post("/finish")
@link_agent
def link_finish():
    run = run_for_pass()
    if not run:
        return api_error("This link pass isn't known.", 409)
    account_ctx.set_current(run["account_id"])
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("done", "failed", "no_access"):
        return api_error("status must be done, failed or no_access", 400)
    if run["status"] != "open":
        return api_error("This link pass is finished.", 409)
    error = cut(data.get("error")) or ("Your Facebook login on the Mac can't see this ad account." if status == "no_access" else None)
    row = db.execute("UPDATE am_link_runs SET status = %s, error = COALESCE(%s, error), finished_at = now() WHERE id = %s RETURNING pushed",
                     (status, error, run["id"]), returning=True)
    settings_store.set("am_link_no_access", "1" if status == "no_access" else None)
    if row and row["pushed"]:
        set_link(last_ok_at=utcnow())
        close_link_down()
    return jsonify({"status": status})
