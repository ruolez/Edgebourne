"""Ad accounts in one console (roadmap 7.1): which one a request works on, the list, adding one,
renaming, switching. Admins see every account; members and clients only their own. FU-A: adding one
picked from the ad accounts the console's Meta key reaches, and All accounts side by side."""
import re
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

import account_ctx
import adaccounts
import db
import meta_client
import settings_store
from auth import current_user, is_owner, login_required, owner_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")


def active_accounts():
    return db.query("SELECT id, name, created_at FROM accounts WHERE archived_at IS NULL ORDER BY id")


def closed(account_id):
    """True when the account was archived (its people lose access, its share links stop)."""
    if not account_id:
        return False
    with account_ctx.all_accounts():
        row = db.query("SELECT archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
    return not row or row["archived_at"] is not None


def clients_update_leads(account_id=None):
    """Settings → Client access: the account's clients may move leads through stages and add notes."""
    return settings_store.get("client_lead_updates", account_id=account_id) == "on"


def account_for(user):
    """The account a signed-in person works on: the owner's choice, everyone else's own.
    None when that account was closed."""
    if not user:
        return account_ctx.DEFAULT
    if not is_owner(user):
        own = user.get("account_id") or account_ctx.DEFAULT
        return None if closed(own) else own
    try:
        wanted = int(request.cookies.get(COOKIE) or account_ctx.DEFAULT)
    except ValueError:
        wanted = account_ctx.DEFAULT
    return wanted if any(a["id"] == wanted for a in active_accounts()) else account_ctx.DEFAULT


def choose_for_request():
    """before_request: the Mac names its account in a header (checked against the key); a person's
    session decides for them; webhooks decide from the Page in the payload."""
    path = request.path
    account_ctx.set_current(account_ctx.DEFAULT)  # gunicorn reuses threads: never inherit the last request's
    if (path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
            and not path.startswith("/api/agent/") and not _from_the_console()):
        return api_error("This request didn't come from the console", 403)
    m = re.match(r"^/api/agent/tasks/(\d+)", path)
    if m:
        # A task's calls run in the task's own account, whatever the Mac sends.
        with account_ctx.all_accounts():
            row = db.query("SELECT account_id FROM desk_tasks WHERE id = %s", (int(m.group(1)),), one=True)
        account_ctx.set_current(row["account_id"] if row else account_ctx.DEFAULT)
        return
    if path.startswith("/api/agent/"):
        try:
            account_ctx.set_current(int(request.headers.get("X-Account") or account_ctx.DEFAULT))
        except ValueError:
            account_ctx.set_current(account_ctx.DEFAULT)
        return
    if path.startswith("/api/") and session.get("user_id"):
        user = db.query("SELECT id, role, account_id FROM users WHERE id = %s AND is_active", (session["user_id"],), one=True)
        acct = account_for(user)
        if acct is None:
            if path == "/api/auth/logout":
                return None
            return api_error("This account was closed. Ask Edge Bourne if you need access again.", 403)
        account_ctx.set_current(acct)
        if user and user["role"] == "client" and request.method not in ("GET", "HEAD") and not CLIENT_MAY.match(path):
            if clients_update_leads(acct) and CLIENT_LEADS.match(path):
                return None
            return api_error("Your access is read-only. Ask Edge Bourne to make this change.", 403)


def _from_the_console():
    """Cross-site CSRF guard: a form on another site can't send JSON or custom headers without a
    CORS preflight, which this server never answers. The console's own requests always carry one."""
    return (request.headers.get("X-Requested-With") == "ebads"
            or (request.mimetype or "") == "application/json")


# The admin's chosen account lives in its own cookie, set only by switching: the session cookie is
# re-sent by every response, so a request that started before a switch could undo it. The value is
# only a choice; account_for() checks the person may use it (admins only, active accounts only).
COOKIE = "ebads_account"


def _with_choice(resp, account_id):
    import config
    resp.set_cookie(COOKIE, str(account_id), max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax",
                    secure=config.APP_BASE_URL.startswith("https://"))
    return resp


# What a client (read-only) may still do: sign out, their own password and notification settings,
# and their own Inbox read marks and saved views (both are rows of that person only).
CLIENT_MAY = re.compile(r"^/api/(auth/(logout|password|me)|me/(push|telegram)(/[a-z0-9]+)?|inbox/read|views(/\d+)?)$")
# With Settings → Client access on: moving a lead's stage, logging calls and next steps (and undoing them), notes.
CLIENT_LEADS = re.compile(r"^/api/leads/\d+(/notes|/calls|/events/\d+/undo|/not-junk)?$")


def name_of(account_id):
    row = db.query("SELECT name FROM accounts WHERE id = %s", (account_id,), one=True)
    return row["name"] if row else ""


@bp.get("")
@login_required
def listing():
    user = current_user()
    current = account_ctx.current()
    items = active_accounts() if is_owner(user) else [a for a in active_accounts() if a["id"] == current]
    return jsonify({"current": current, "items": [{"id": a["id"], "name": a["name"]} for a in items]})


@bp.post("")
@owner_required
def create():
    name = " ".join(str((request.get_json(silent=True) or {}).get("name") or "").split())[:120]
    if not name:
        return api_error("Give the account a name (the business it advertises)", 400, field="name")
    if name_taken(name):
        return api_error("Another account already has that name", 409, field="name")
    with account_ctx.all_accounts(), db.transaction() as cur:
        cur.execute("INSERT INTO accounts (name) VALUES (%s) RETURNING id", (name,))
        new = cur.fetchone()["id"]
        _seed_new_account(cur, new, name)
    log_activity("account.created", subject=str(new), details={"name": name})
    return _with_choice(jsonify({"id": new, "name": name}), new), 201


def _seed_new_account(cur, new, name):
    """Claude's regular checks (switched off) and the first-reply template, ready to use in a new account."""
    cur.execute("""INSERT INTO desk_schedules (account_id, name, about, kind, prompt, rule, enabled, position)
                   SELECT %s, name, about, kind, prompt, rule, FALSE, position FROM desk_schedules WHERE account_id = 1""", (new,))
    # The first-reply template, with this business's name instead of Edge Bourne's (check the wording).
    cur.execute("""INSERT INTO reply_templates (account_id, name, subject, body, position)
                   SELECT %s, name, replace(subject, 'Edge Bourne', %s), replace(body, 'Edge Bourne', %s), position
                   FROM reply_templates WHERE account_id = 1 ORDER BY position LIMIT 1""", (new, name, name))


# ---------------------------------------------------------------- FU-A: add an ad account picked from Meta's list

REACH_FIELDS = "account_id,name,currency,account_status,timezone_name,business{id,name}"
REACH_KEY = "adaccounts:reachable"
REACH_TTL = 60
FRESH_EVERY = 10  # seconds between two "Look again" reads
_fresh_at = {}


def _read_reach():
    """Meta's lists of ad accounts, read now with the owner's key (account 1's: run inside account_ctx.use(DEFAULT))."""
    reads = [("me/adaccounts", {"fields": REACH_FIELDS, "limit": 100})]
    business = settings_store.get("meta_business_id")
    if business:
        reads += [(f"{business}/{edge}", {"fields": REACH_FIELDS, "limit": 100}) for edge in ("owned_ad_accounts", "client_ad_accounts")]
    got = meta_client.read_many(reads)
    if isinstance(got[0], meta_client.MetaError):
        raise got[0]
    sources, partial = {"assigned": got[0]}, []
    for via, rows in zip(("owned", "client"), got[1:]):
        if isinstance(rows, meta_client.MetaError):
            partial.append(via)  # the System User may lack Business management: the assigned list still counts
        else:
            sources[via] = rows
    try:
        who = meta_client.get("me", fields="name", timeout=meta_client.READ_TIMEOUT).get("name")
    except meta_client.MetaError:
        who = None
    return {"sources": sources, "partial": partial, "system_user": who,
            "read_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def reachable(force=False):
    """Every ad account the owner's Meta key reaches, with the console account holding each and why one can't be
    added. Always read with account 1's key and Business, whichever account is open: an account added from this
    list has no key of its own and inherits that one (settings_store.INHERITED), so listing and binding must use
    the key the new account will read with. Meta's answer is kept a minute under account 1 (meta_cache)."""
    import account_info
    import insights_api
    import money_rules
    with account_ctx.use(account_ctx.DEFAULT):
        if force:
            raw = _read_reach()
            insights_api.store(REACH_KEY, raw)
        else:
            raw = insights_api.cached(REACH_KEY, REACH_TTL, _read_reach)
    with account_ctx.all_accounts():
        names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM accounts")}
    items = adaccounts.mark_used(adaccounts.merge(raw["sources"]), settings_store.meta_holders("meta_ad_account_id"), names)
    for i in items:
        i["blocked"] = adaccounts.blocked(i, account_info.currency_problem)
    return {"items": items, "partial": raw.get("partial") or [], "system_user": raw.get("system_user"),
            "read_at": raw.get("read_at"), "default_max_daily_cents": money_rules.MAX_DAILY_DEFAULT}


@bp.get("/reachable")
@owner_required
def reachable_listing():
    now = time.time()  # one list for every account (the owner's key), so one "Look again" pace too
    force = request.args.get("fresh") == "1" and now - _fresh_at.get(account_ctx.DEFAULT, 0) >= FRESH_EVERY
    if force:
        _fresh_at[account_ctx.DEFAULT] = now
    try:
        return jsonify(reachable(force=force))
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)


class _Refused(Exception):
    pass


@bp.post("/from-meta")
@owner_required
def create_from_meta():
    """A console account bound to an ad account the key reaches. The id is checked against a fresh read of Meta's
    lists (never the browser's word) and, under a lock, against every account that already holds it."""
    import account_info
    import jobs
    data = request.get_json(silent=True) or {}
    digits = adaccounts.act_digits(data.get("ad_account_id"))
    if not digits:
        return api_error("Pick an ad account from the list", 400, field="ad_account_id")
    try:
        reach = reachable(force=True)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    item = next((i for i in reach["items"] if i["id"] == digits), None)
    if not item:
        return api_error("This ad account isn't reachable with the console's Meta key any more. Look again.", 404, field="ad_account_id")
    if item["blocked"]:
        return api_error(item["blocked"], 409, field="ad_account_id")
    name = " ".join(str(data.get("name") or "").split())[:120] or adaccounts.default_name(item)
    if name_taken(name):
        return api_error("Another account already has that name", 409, field="name")
    key = "meta_ad_account_id"
    try:
        with account_ctx.all_accounts(), db.transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"adaccount:{digits}",))
            cur.execute(settings_store.HOLDER_ROWS_SQL, (key, f"{key}@%"))
            rows = cur.fetchall()
            cur.execute("SELECT id, name, archived_at IS NOT NULL AS closed FROM accounts ORDER BY id")
            accounts = cur.fetchall()
            held = adaccounts.mark_used([item], settings_store.holders_from(key, rows, accounts), {a["id"]: a["name"] for a in accounts})[0]
            again = adaccounts.blocked(held, account_info.currency_problem)
            if again:
                raise _Refused(again)
            cur.execute("INSERT INTO accounts (name) VALUES (%s) RETURNING id", (name,))
            new = cur.fetchone()["id"]
            _seed_new_account(cur, new, name)
            for k, v in ((key, digits), ("meta_business_id", item.get("business_id")), ("meta_ad_account_via", "picker")):
                if v:
                    cur.execute(settings_store.UPSERT_SQL, (settings_store.stored_key(k, new), str(v)))
    except _Refused as exc:
        return api_error(str(exc), 409, field="ad_account_id")
    details = {"name": name, "ad_account_id": digits, "via": "picker"}
    with account_ctx.use(new):
        log_activity("account.created", subject=str(new), details=details)
    log_activity("account.added_from_meta", subject=str(new), details=details)
    jobs.wake()  # the worker's next pass reads its time zone, currency and first results
    return _with_choice(jsonify({"id": new, "name": name, "ad_account_id": digits}), new), 201


# ---------------------------------------------------------------- FU-A: All accounts side by side

def connected():
    """The open account has an ad account (account 1 counts its built-in one)."""
    if account_ctx.current() == account_ctx.DEFAULT:
        return bool(settings_store.get("meta_ad_account_id"))
    return bool(settings_store.own("meta_ad_account_id"))


def overview_row(user, account):
    """One account's figures over the shared range, read from stored data in that account (row-level security)."""
    import account_info
    import inbox
    import lead_quality as lq
    import numbers_check
    import performance_api
    import ranges
    key, start, end = performance_api.window_args(request.args)
    t = performance_api.window_totals(user, start, end)
    ids = visible_campaign_ids(user)
    scope, params = (lambda t: "TRUE", []) if ids is None else (lambda t: f"{t}.campaign_id = ANY(%s)", [ids])
    received = db.query(f"""SELECT COUNT(*) AS n FROM leads l WHERE {lq.counted()}
                            AND (l.created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {scope('l')}""",
                        [account_info.tz_name(), start, end] + params, one=True)["n"]
    delivering = db.query(f"SELECT COUNT(*) AS n FROM ads a WHERE a.effective_status = 'ACTIVE' AND {scope('a')}", params, one=True)["n"]
    admin = user["role"] == "admin"
    cap = performance_api.cap_snapshot() if admin else None
    source = numbers_check.source(user, start, end, meta_leads=t["leads"], received=received, scoped=ids is not None)
    return {"id": account["id"], "name": account["name"], "currency": account_info.currency(), "tz": account_info.tz_name(),
            "connected": connected(), "spend_cents": t["spend_cents"], "leads": t["leads"], "received": int(received),
            "cpl_cents": round(t["spend_cents"] / t["leads"]) if t["leads"] else None, "delivering": int(delivering),
            "needs_you": inbox.counts(inbox.items_for(user))["need"],
            "suggestions": db.query("SELECT COUNT(*) AS n FROM desk_proposals WHERE status = 'pending'", one=True)["n"] if admin else None,
            "cap": {"limit_cents": cap["limit_cents"], "spent_cents": cap["spent_cents"]} if cap else None,
            "synced_at": settings_store.get("last_performance_sync"), "behind": bool(source["meta"]["behind"]), "source": source,
            "range": {"key": key, "start": start.isoformat(), "end": end.isoformat(), "label": ranges.label(start, end)}}


@bp.get("/overview")
@login_required
def overview():
    """All accounts: the owner sees every open account, everyone else only their own (one row)."""
    user = current_user()
    accounts = active_accounts() if is_owner(user) else [{"id": account_ctx.current(), "name": name_of(account_ctx.current())}]
    rows = []
    for a in accounts:
        with account_ctx.use(a["id"]):
            rows.append(overview_row(user, a))
    here = next((r for r in rows if r["id"] == account_ctx.current()), rows[0])
    return jsonify({"range": here["range"], "rows": rows, "own_days": len({r["tz"] for r in rows}) > 1, "current": account_ctx.current(),
                    **adaccounts.overview_totals(rows)})


@bp.patch("/<int:account_id>")
@owner_required
def rename(account_id):
    """Rename, or close (archived: its people lose access, its share links stop, the worker skips it)."""
    data = request.get_json(silent=True) or {}
    with account_ctx.all_accounts():
        row = db.query("SELECT id, name, archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
        if not row:
            return api_error("No such account", 404)
        if "archived" in data:
            if account_id == account_ctx.DEFAULT:
                return api_error("Edge Bourne's own account can't be closed", 400)
            db.execute("UPDATE accounts SET archived_at = CASE WHEN %s THEN COALESCE(archived_at, now()) END WHERE id = %s",
                       (bool(data["archived"]), account_id))
            log_activity("account.archived" if data["archived"] else "account.reopened", subject=str(account_id))
        if "name" in data:
            name = " ".join(str(data.get("name") or "").split())[:120]
            if not name:
                return api_error("Give the account a name", 400, field="name")
            if name_taken(name, account_id):
                return api_error("Another account already has that name", 409, field="name")
            db.execute("UPDATE accounts SET name = %s WHERE id = %s", (name, account_id))
            log_activity("account.renamed", subject=str(account_id), details={"name": name})
        row = db.query("SELECT id, name, archived_at FROM accounts WHERE id = %s", (account_id,), one=True)
    return jsonify({"id": row["id"], "name": row["name"], "archived": row["archived_at"] is not None})


def name_taken(name, except_id=None):
    with account_ctx.all_accounts():
        return db.query("SELECT 1 FROM accounts WHERE lower(name) = lower(%s) AND archived_at IS NULL AND id <> %s",
                        (name, except_id or 0), one=True) is not None


@bp.get("/all")
@owner_required
def all_accounts_listing():
    """Settings → Accounts: every account with its state, closed ones included."""
    import account_info
    with account_ctx.all_accounts():
        rows = db.query("SELECT id, name, created_at, archived_at FROM accounts ORDER BY archived_at IS NOT NULL, id")
    held = {acct: adaccounts.act_digits(value) for acct, _, value in settings_store.meta_holders("meta_ad_account_id")}
    out = []
    for r in rows:
        ad = held.get(r["id"])
        with account_ctx.use(r["id"]):
            currency = account_info.currency() if ad else None
        out.append({"id": r["id"], "name": r["name"], "archived": r["archived_at"] is not None, "ad_account_id": ad, "currency": currency})
    return jsonify({"items": out})


@bp.post("/switch")
@owner_required
def switch():
    wanted = (request.get_json(silent=True) or {}).get("id")
    if not any(a["id"] == wanted for a in active_accounts()):
        return api_error("No such account", 404)
    return _with_choice(jsonify({"current": wanted, "name": name_of(wanted)}), wanted)
