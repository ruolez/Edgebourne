"""QA: agency mode must never show one account's data in another (roadmap 7.1 leak test).

Seeds account 2 ("Burdanova QA") with marked data, then calls every GET route of the app as
(a) the admin on account 1, (b) the admin switched to account 2, (c) account 2's client, with
ids from the *other* account wherever a route takes one. Account 1 gets marked rows in the same
tables for the length of the run. Also checks that every table with an account_id is under
row-level security, and that writes aimed at account 1's ids from account 2 change nothing.
Prints a JSON verdict."""
import atexit
import json
import re
import secrets
from urllib.parse import quote

from werkzeug.security import generate_password_hash

import account_ctx
import auth
import db
import builds_api
from app import create_app

MARK2 = "ACCT2MARK"
MARK1 = "ACCT1MARK"  # rows put in account 1 for this run only (removed at exit)
ACCT1_MARKS = ["One simple system", "Free intro call - Leads", "SoCal business owners", MARK1]
# Tables with an account_id that are deliberately not limited by row-level security, and why.
RLS_EXEMPT = {"users": "an admin spans accounts; the code checks a person's account (auth, team_api)"}

app = create_app(run_migrations=False)


def once(table, row, key):
    """Insert a marked row unless one with the same `key` value is there; returns the row (tables with an id)."""
    cols = ", ".join(row)
    marks = ", ".join(["%s"] * len(row))
    db.execute(f"INSERT INTO {table} ({cols}) SELECT {marks} WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {key} = %s AND account_id = %s)",
               (*row.values(), row[key], row["account_id"]))
    if table != "inbox_reads":
        return db.query(f"SELECT * FROM {table} WHERE {key} = %s AND account_id = %s", (row[key], row["account_id"]), one=True)


def seed_marked(acct, mark, ad, campaign, lead, task, admin_id):
    """A marked row in each account-owned table the newer screens read (Inbox, History, versions, Claude, builds, CRM)."""
    proposal = once("desk_proposals", {"task_id": task, "kind": "status", "title": f"{mark} proposal", "entity_type": "ad", "entity_id": ad,
                                       "entity_name": f"{mark} ad", "proposed_value": "PAUSED", "status": "pending", "account_id": acct}, "title")
    once("desk_reports", {"task_id": task, "title": f"{mark} report", "body": f"{mark} report body", "account_id": acct}, "title")
    once("status_events", {"level": "ad", "entity_id": ad, "entity_name": f"{mark} ad", "campaign_id": campaign, "field": "review",
                           "new_value": f"{mark} review", "source": "console", "account_id": acct}, "new_value")
    change = once("meta_changes", {"user_id": admin_id, "level": "ad", "entity_id": ad, "entity_name": f"{mark} ad", "campaign_id": campaign,
                          "action": "status", "old_value": "ACTIVE", "new_value": f"{mark} change", "ok": True, "account_id": acct}, "new_value")
    once("ad_versions", {"ad_id": ad, "number": 900, "creative_id": f"{mark}creative", "label": f"{mark} version", "title": f"{mark} version",
                         "body": f"{mark} version body", "account_id": acct}, "label")
    view = once("saved_views", {"user_id": admin_id, "page": "ads", "name": f"{mark} view", "query": "level=ad", "shared": True, "account_id": acct}, "name")
    spec = json.dumps(builds_api.clean({"name": f"{mark} build", "daily_budget_cents": 1500, "form_id": "1132280359202136"}))
    build = once("campaign_builds", {"spec": spec, "status": "partial", "client_key": f"{mark}build", "created_by": admin_id, "account_id": acct}, "client_key")
    db.execute("UPDATE campaign_builds SET spec = %s WHERE id = %s", (spec, build["id"]))  # keeps up with the spec's shape
    once("alerts", {"rule": "qa", "dedupe_key": f"{mark}alert", "level": "warn", "title": f"{mark} alert", "kind": "event",
                    "entity_id": ad, "campaign_id": campaign, "account_id": acct}, "dedupe_key")
    # W1a: an open problem Claude can diagnose and an admin can snooze (its draft names the alert and the ad).
    problem = once("alerts", {"rule": "no_leads", "dedupe_key": f"{mark}problem", "level": "bad", "title": f"{mark} no leads", "kind": "condition",
                              "entity_id": campaign, "campaign_id": campaign, "account_id": acct}, "dedupe_key")
    once("lead_notes", {"lead_id": lead, "user_id": admin_id, "body": f"{mark} note", "account_id": acct}, "body")
    # A lead's history line (L1, never pruned): its words name the mark, so a leak shows in any lead's History.
    once("lead_events", {"lead_id": lead, "kind": "received", "actor": "meta", "details": json.dumps({"ad": f"{mark} event"}),
                         "account_id": acct}, "details")
    once("lead_replies", {"lead_id": lead, "user_id": admin_id, "to_email": "qa@example.com", "subject": f"{mark} reply", "body": f"{mark} reply",
                          "status": "sent", "account_id": acct}, "subject")
    activity = once("activity", {"user_id": admin_id, "actor": "qa", "action": "qa.mark", "subject": f"{mark} activity", "account_id": acct}, "subject")
    db.execute("UPDATE activity SET at = now() WHERE id = %s", (activity["id"],))  # History lists the latest 200 only
    once("inbox_reads", {"user_id": admin_id, "item_key": f"{mark}read", "account_id": acct}, "item_key")
    swipe = once("swipes", {"page_name": f"{mark} rival", "body": f"{mark} rival words", "source": "manual", "account_id": acct}, "page_name")
    # FU-D: a preview Claude attached (its name shows in the Claude page's list; its bytes only through its own route).
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    preview = once("desk_attachments", {"task_id": task, "kind": "image", "mime": "image/png", "name": f"{mark}preview.png", "caption": f"{mark} preview",
                                        "size_bytes": len(png), "sha256": "0" * 64, "width": 1, "height": 1, "body": png, "account_id": acct}, "name")
    # D1: a numbers check that stopped (its words show in Settings → Numbers vs Ads Manager's recent checks).
    once("numbers_runs", {"kind": "check", "start_day": "2026-10-01", "end_day": "2026-10-02", "finished_at": "2026-10-03T04:10:00Z", "ok": False,
                          "error": f"{mark} run", "account_id": acct}, "error")
    return {"proposal": proposal["id"], "view": view["id"], "build": build["id"], "swipe": swipe["id"], "alert": problem["id"],
            "change": change["id"], "attachment": preview["id"]}

with account_ctx.all_accounts():
    acct = db.query("SELECT id FROM accounts WHERE name = 'Burdanova QA'", one=True)
    if not acct:
        acct = db.execute("INSERT INTO accounts (name) VALUES ('Burdanova QA') RETURNING id", returning=True)
    A2 = acct["id"]
    ids = {"campaign": f"9{A2}0000000000001", "adset": f"9{A2}0000000000002", "ad": f"9{A2}0000000000003"}
    db.execute("INSERT INTO campaigns (id, name, status, effective_status, account_id) VALUES (%s, %s, 'ACTIVE', 'ACTIVE', %s) ON CONFLICT (id) DO NOTHING",
               (ids["campaign"], f"{MARK2} campaign", A2))
    db.execute("INSERT INTO adsets (id, name, campaign_id, status, effective_status, account_id) VALUES (%s, %s, %s, 'ACTIVE', 'ACTIVE', %s) ON CONFLICT (id) DO NOTHING",
               (ids["adset"], f"{MARK2} ad set", ids["campaign"], A2))
    db.execute("""INSERT INTO ads (id, name, campaign_id, adset_id, status, effective_status, account_id, title, body)
                  VALUES (%s, %s, %s, %s, 'ACTIVE', 'ACTIVE', %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
               (ids["ad"], f"{MARK2} ad", ids["campaign"], ids["adset"], A2, f"{MARK2} headline", f"{MARK2} body"))
    db.execute("""INSERT INTO ad_daily (day, ad_id, campaign_id, adset_id, ad_name, spend_cents, impressions, leads, account_id)
                  VALUES (CURRENT_DATE - 1, %s, %s, %s, %s, 4321, 999, 3, %s) ON CONFLICT DO NOTHING""",
               (ids["ad"], ids["campaign"], ids["adset"], f"{MARK2} ad", A2))
    lead = db.query("SELECT id FROM leads WHERE meta_lead_id = %s", (f"{MARK2}lead",), one=True) or db.execute(
        """INSERT INTO leads (meta_lead_id, created_time, full_name, email, phone, ad_id, ad_name, campaign_id, account_id)
           VALUES (%s, now(), %s, 'acct2@example.com', '+15550002222', %s, %s, %s, %s) RETURNING id""",
        (f"{MARK2}lead", f"{MARK2} Lead Person", ids["ad"], f"{MARK2} ad", ids["campaign"], A2), returning=True)
    # Its form carries the mark too, so the lead-form search (names read from leads) is walked as well.
    db.execute("UPDATE leads SET form_id = %s, form_name = %s WHERE id = %s", (f"{MARK2}form", f"{MARK2} form", lead["id"]))
    task = db.query("SELECT id FROM desk_tasks WHERE prompt = %s", (f"{MARK2} task",), one=True) or db.execute(
        "INSERT INTO desk_tasks (kind, prompt, status, summary, account_id) VALUES ('question', %s, 'done', %s, %s) RETURNING id",
        (f"{MARK2} task", f"{MARK2} summary", A2), returning=True)
    db.execute("INSERT INTO swipes (page_name, body, account_id) SELECT %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM swipes WHERE page_name = %s)",
               (f"{MARK2} competitor", f"{MARK2} swipe", A2, f"{MARK2} competitor"))
    db.execute("INSERT INTO ad_tags (ad_id, dimension, value, account_id) VALUES (%s, 'hook', %s, %s) ON CONFLICT DO NOTHING", (ids["ad"], f"{MARK2} hook", A2))
    exp = db.query("SELECT id FROM experiments WHERE name = %s", (f"{MARK2} test",), one=True) or db.execute(
        """INSERT INTO experiments (name, metric, arms, start_day, account_id) VALUES (%s, 'cpl', %s, CURRENT_DATE - 3, %s) RETURNING id""",
        (f"{MARK2} test", json.dumps([{"label": "A", "ad_ids": [ids["ad"]], "adset_ids": []}, {"label": "B", "ad_ids": [], "adset_ids": [ids["adset"]]}]), A2),
        returning=True)
    client_email = "client-qa@burdanova.test"
    client = db.query("SELECT id FROM users WHERE email = %s", (client_email,), one=True) or db.execute(
        "INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, 'Client QA', %s, 'client', %s) RETURNING id",
        (client_email, generate_password_hash(secrets.token_hex(8)), A2), returning=True)
    admin = db.query("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1", one=True)
    two = {"ad": ids["ad"], "adset": ids["adset"], "campaign": ids["campaign"], "lead": lead["id"], "task": task["id"], "exp": exp["id"],
           **seed_marked(A2, MARK2, ids["ad"], ids["campaign"], lead["id"], task["id"], admin["id"])}
    one = {"ad": "120252672229040312", "adset": "120252672227950312", "campaign": "120252638288040312",
           "lead": db.query("SELECT id FROM leads WHERE account_id = 1 ORDER BY id LIMIT 1", one=True)["id"]}
    # Account 1's marked rows exist only while this runs: later flows count account 1's proposals, views and alerts.
    def drop_mark1():
        with account_ctx.all_accounts():
            for t, col in (("desk_proposals", "title"), ("desk_reports", "title"), ("status_events", "new_value"), ("meta_changes", "new_value"),
                           ("ad_versions", "label"), ("saved_views", "name"), ("campaign_builds", "client_key"), ("alerts", "dedupe_key"),
                           ("lead_notes", "body"), ("lead_replies", "subject"), ("activity", "subject"), ("inbox_reads", "item_key"),
                           ("desk_attachments", "name"), ("desk_tasks", "prompt"), ("swipes", "page_name"), ("numbers_runs", "error")):
                db.execute(f"DELETE FROM {t} WHERE account_id = 1 AND {col} LIKE %s", (MARK1 + "%",))
            db.execute("DELETE FROM lead_events WHERE account_id = 1 AND details->>'ad' LIKE %s", (MARK1 + "%",))
    drop_mark1()
    atexit.register(drop_mark1)
    task1 = db.execute("INSERT INTO desk_tasks (kind, prompt, status, summary, account_id) VALUES ('question', %s, 'done', %s, 1) RETURNING id",
                       (f"{MARK1} task", f"{MARK1} summary"), returning=True)
    one.update(task=task1["id"], exp=(db.query("SELECT id FROM experiments WHERE account_id = 1 ORDER BY id LIMIT 1", one=True) or {"id": 1})["id"],
               **seed_marked(1, MARK1, one["ad"], one["campaign"], one["lead"], task1["id"], admin["id"]))

    # Row-level security on every table that holds account data (a new table that forgets it would leak).
    tables = db.query("""SELECT c.relname AS name, c.relrowsecurity AS rls,
                                COALESCE(array_agg(concat_ws(' | ', pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)))
                                         FILTER (WHERE p.oid IS NOT NULL), '{}') AS policies
                         FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                         JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'account_id' AND NOT a.attisdropped
                         LEFT JOIN pg_policy p ON p.polrelid = c.oid
                         WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') GROUP BY c.relname, c.relrowsecurity ORDER BY 1""")
    app_role_bypasses = db.query("SELECT rolsuper OR rolbypassrls AS b FROM pg_roles WHERE rolname = %s", (db.APP_ROLE,), one=True)["b"]


def isolated(t):
    """RLS on, at least one policy, and every expression of every policy is exactly account_id = app_account()
    (a whole-expression match, so a policy loosened with `OR ...` is flagged)."""
    exprs = [e.strip() for p in t["policies"] for e in p.split(" | ")]
    return t["rls"] and bool(exprs) and all(re.fullmatch(r"\(*account_id = app_account\(\)\)*", e) for e in exprs)


unisolated = [t["name"] for t in tables if t["name"] not in RLS_EXEMPT and not isolated(t)]


def fill(rule, other):
    """A GET route with its parameters filled with the other account's ids."""
    url = rule.rule
    for name in rule.arguments:
        v = {"ad_id": other["ad"], "adset_id": other["adset"], "campaign_id": other["campaign"], "entity_id": other["ad"], "level": "ad",
             "lead_id": other["lead"], "task_id": other["task"], "exp_id": other.get("exp", 1), "id": other["lead"],
             "proposal_id": other["proposal"], "build_id": other["build"], "view_id": other["view"], "number": 900,
             "change_id": other["change"], "att_id": other["attachment"]}.get(name, "1")
        url = re.sub(r"<(?:[a-z]+:)?" + name + ">", str(v), url)
    return url


# GET routes that read their ids from the query: asked with the other account's.
QUERY = {"/api/swipes/brief": lambda other: f"?ids={other['swipe']}&as=brief",
         "/api/diagnose/draft": lambda other: f"?alert_id={other['alert']}"}

SKIP = re.compile(r"^/api/(agent/|auth/logout)|/wait$|/stream$|^/webhooks/")


shown = {}  # label → routes that show the walking account's own mark (proof the seeds are reachable)
crashed = []  # a route that fails with a 5xx can't show whether it leaks


def walk(client, forbidden, other, label, own=None):
    leaks, checked = [], 0
    shown[label] = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or not rule.rule.startswith("/api/") or SKIP.search(rule.rule):
            continue
        url = fill(rule, other) + (QUERY[rule.rule](other) if rule.rule in QUERY else "")
        r = client.get(url)
        checked += 1
        # A preview's bytes (FU-D) aren't text; its name travels in Content-Disposition, so headers are read too.
        body = r.get_data().decode("utf-8", "replace") + str(r.headers)
        if rule.rule == "/api/search":  # the command menu's search, asked for each forbidden name (and its own)
            body += "".join(client.get(f"{url}?q={quote(m)}").get_data(as_text=True) for m in [*forbidden, own or ""] if len(m) >= 2)
        for mark in forbidden:
            if mark in body:
                leaks.append(f"{label}: {url} ({r.status_code}) shows {mark!r}")
        if own and own in body:
            shown[label].append(rule.rule)
        if r.status_code >= 500:
            crashed.append(f"{label}: {url} ({r.status_code})")
    return leaks, checked


_keys = {}


def session_for(client, user_id, account=None):
    if user_id not in _keys:
        _keys[user_id] = auth.new_session_key(user_id)
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["sk"] = _keys[user_id]
        # A password change (QA's FU-D block changes the owner's to the same one) bumps session_version.
        s["sv"] = db.query("SELECT session_version FROM users WHERE id = %s", (user_id,), one=True)["session_version"]
    client.set_cookie("ebads_account", str(account or 1))


out = {"account2": A2}
c = app.test_client()
session_for(c, admin["id"], 1)
l1, n1 = walk(c, [MARK2], two, "admin on account 1", MARK1)
session_for(c, admin["id"], A2)
l2, n2 = walk(c, ACCT1_MARKS, one, "admin on account 2", MARK2)
l2b, _ = walk(c, ACCT1_MARKS, two, "admin on account 2, own ids", MARK2)  # routes that take an id reach the seeded rows
sees_own = MARK2 in c.get("/api/performance").get_data(as_text=True)
cc = app.test_client()
session_for(cc, client["id"])
l3, n3 = walk(cc, ACCT1_MARKS, one, "client of account 2")
client_sees_own = MARK2 in cc.get("/api/leads").get_data(as_text=True)
switch = cc.post("/api/accounts/switch", json={"id": 1}).status_code
cc.get("/api/me")
still = MARK2 in cc.get("/api/performance").get_data(as_text=True) and not any(m in cc.get("/api/performance").get_data(as_text=True) for m in ACCT1_MARKS)
writes = []
for rule in app.url_map.iter_rules():
    methods = (rule.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}
    if not methods or not rule.rule.startswith("/api/") or rule.rule.startswith("/api/agent/"):
        continue
    if rule.rule == "/api/auth/logout":
        continue
    for m in methods:
        session_for(cc, client["id"])
        status = cc.open(fill(rule, two), method=m, json={}).status_code
        if status != 403 and not re.match(r"^/api/(auth/(logout|password|me)|me/(push|telegram)(/.*)?|inbox/read|views(/<int:view_id>)?)$", rule.rule):
            writes.append(f"{m} {rule.rule} → {status}")

# Audit 2: a member and an admin limited to account 2, writes aimed at account 1's ids, background
# threads, assignments and the cross-site guard.
with account_ctx.all_accounts():
    def user(email, role):
        return db.query("SELECT id FROM users WHERE email = %s", (email,), one=True) or db.execute(
            "INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (email, email.split("@")[0], generate_password_hash(secrets.token_hex(8)), role, A2), returning=True)
    member = user("member-qa@burdanova.test", "member")
    acct_admin = user("admin-qa@burdanova.test", "admin")
    db.execute("INSERT INTO campaign_members (campaign_id, user_id, account_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
               (ids["campaign"], member["id"], A2))
mc = app.test_client()
session_for(mc, member["id"])
l4, n4 = walk(mc, ACCT1_MARKS, one, "member of account 2")
ac = app.test_client()
session_for(ac, acct_admin["id"], 1)  # its cookie asks for account 1: it must not get it
l5, n5 = walk(ac, ACCT1_MARKS, one, "admin of account 2 only")
acct_admin_limits = {
    "switch_to_1": ac.post("/api/accounts/switch", json={"id": 1}).status_code,
    "all_accounts": ac.get("/api/accounts/all").status_code,
    "add_account": ac.post("/api/accounts", json={"name": "Nope"}).status_code,
    "console_meta_keys": ac.put("/api/settings/meta", json={"meta_app_secret": "x" * 32}).status_code,
    "smtp": ac.put("/api/settings/smtp", json={"smtp_host": "evil.example"}).status_code,
    "mac_key": ac.post("/api/desk/key", json={}).status_code,
    "edit_owner": ac.patch(f"/api/team/{admin['id']}", json={"reset_password": True}).status_code,
}
import meta_client

# FU-A: the ad account picker is the owner's alone; All accounts shows a non-owner their own account only.
with account_ctx.all_accounts():
    n_accounts = db.query("SELECT COUNT(*) AS n FROM accounts", one=True)["n"]
session_for(c, admin["id"], 1)
owner_view = c.get("/api/accounts/overview?range=30").get_json() or {}
acct1_row = next((r for r in owner_view.get("rows") or [] if r["id"] == 1), {})
session_for(cc, client["id"])
client_view = cc.get("/api/accounts/overview?range=30")
client_body = client_view.get_data(as_text=True)
with account_ctx.all_accounts():
    active_names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM accounts WHERE archived_at IS NULL")}
fua = {"reachable_owner": c.get("/api/accounts/reachable").status_code}
session_for(c, admin["id"], A2)
fua["reachable_switched_owner"] = c.get("/api/accounts/reachable").status_code
session_for(c, admin["id"], 1)
fua.update({
    "reachable_account_admin": ac.get("/api/accounts/reachable").status_code,
    "reachable_client": cc.get("/api/accounts/reachable").status_code,
    "from_meta_account_admin": ac.post("/api/accounts/from-meta", json={"ad_account_id": "2223334445556667"}).status_code,
    # Account 1's built-in ad account (config.META_DEFAULTS, usually not stored as a row) is taken.
    "from_meta_taken": c.post("/api/accounts/from-meta", json={"ad_account_id": __import__("config").META_DEFAULTS["meta_ad_account_id"]}).status_code,
    "owner_rows_named": sorted((r["id"], r["name"]) for r in owner_view.get("rows") or []) == sorted(active_names.items()),
    "client_rows": [r["id"] for r in (client_view.get_json() or {}).get("rows") or []],
    "client_sees_account1": [m for m in ["Edge Bourne", f'"spend_cents":{acct1_row.get("spend_cents")},', *ACCT1_MARKS] if m in client_body],
    "client_cap": [r.get("cap") for r in (client_view.get_json() or {}).get("rows") or []],
})
# The picker lists and binds with the owner's key even when the open account has a key of its own: an account added
# from it inherits the owner's key, so an ad account only the other key reaches is neither listed nor bound.
import settings_store
kept_token = settings_store.own("meta_system_token", account_id=A2)
settings_store.set("meta_system_token", "fake-own-key-qa", account_id=A2)
with account_ctx.all_accounts():
    db.execute("DELETE FROM meta_cache WHERE key = 'adaccounts:reachable'")
session_for(c, admin["id"], A2)
own_key_list = c.get("/api/accounts/reachable").get_json() or {}
fua["own_key_listed"] = [i["id"] for i in own_key_list.get("items") or [] if i["id"] == "6667778889990001"]
fua["own_key_bind"] = c.post("/api/accounts/from-meta", json={"ad_account_id": "6667778889990001"}).status_code
settings_store.set("meta_system_token", kept_token, account_id=A2)
with account_ctx.all_accounts():
    db.execute("DELETE FROM meta_cache WHERE key = 'adaccounts:reachable'")
session_for(c, admin["id"], 1)
with account_ctx.all_accounts():
    fua["accounts_added"] = db.query("SELECT COUNT(*) AS n FROM accounts", one=True)["n"] - n_accounts
session_for(c, admin["id"], 1)


def account1_state():
    """What account-2 writes aimed at account 1 must leave alone, read in account 1 (and on Meta)."""
    q = lambda sql, *a: db.query(sql, a)  # noqa: E731
    with account_ctx.use(1):
        return json.dumps({
            "proposal": q("SELECT status FROM desk_proposals WHERE id = %s", one["proposal"]),
            "tasks": q("SELECT id, status, queue_rank, archived_at FROM desk_tasks WHERE id >= %s ORDER BY id", one["task"]),
            "view": q("SELECT name, query, shared FROM saved_views WHERE id = %s", one["view"]),
            "build": q("SELECT status, made FROM campaign_builds WHERE id = %s", one["build"]),
            "versions": q("SELECT number, creative_id FROM ad_versions WHERE ad_id = %s ORDER BY number", one["ad"]),
            "tags": q("SELECT dimension, value FROM ad_tags WHERE ad_id = %s ORDER BY dimension", one["ad"]),
            "lead": q("SELECT status, (SELECT COUNT(*) FROM lead_notes WHERE lead_id = l.id) AS notes, "
                      "(SELECT COUNT(*) FROM lead_replies WHERE lead_id = l.id) AS replies FROM leads l WHERE id = %s", one["lead"]),
            "experiment": q("SELECT name, metric, arms FROM experiments WHERE id = %s", one["exp"]),
            "alert": q("SELECT resolved_at, quiet FROM alerts WHERE id = %s", one["alert"]),
            "snoozes": q("SELECT id, ended_at FROM alert_snoozes ORDER BY id"),
            "ads": q("SELECT COUNT(*) AS n FROM ads"),
            "meta_ad": meta_client.get(one["ad"], fields="status,name"),
            "meta_campaign": meta_client.get(one["campaign"], fields="status,daily_budget"),
            "meta_comments": [(x.get("id"), x.get("is_hidden"), x.get("comment_count"))
                              for x in meta_client.get(f"{story1}/comments", token=meta_client.page_token(),
                                                       fields="id,is_hidden,comment_count").get("data", [])],
        }, default=str, sort_keys=True)


cross = []
# A bulk change previewed on account 1, then applied after switching to account 2, must change nothing.
session_for(c, admin["id"], 1)
with account_ctx.use(1):
    live = meta_client.get(one["ad"], fields="status")["status"]
bulk_to = "PAUSED" if live == "ACTIVE" else "ACTIVE"
bulk_plan = c.post("/api/ads/bulk/preview", json={"action": "status", "level": "ad", "ids": [one["ad"]], "value": bulk_to}).get_json() or {}
if not bulk_plan.get("plan_token"):
    cross.append(f"bulk preview on account 1 made no plan to test with: {bulk_plan}")
# A real comment on account 1's ad post: the comment routes refuse an id that isn't on the post before any
# account check, so a made-up id could never show a leak.
import comments as comments_mod
with account_ctx.use(1):
    story1 = db.query("SELECT story_id FROM ads WHERE id = %s", (one["ad"],), one=True)["story_id"]
    comment1 = next(iter(meta_client.get(f"{story1}/comments", token=meta_client.page_token(), fields="id").get("data", [])), {}).get("id")
if not comments_mod.belongs(comment1, story1):
    cross.append(f"account 1's ad post has no comment to test with: {comment1!r} on {story1!r}")
state_before = account1_state()
session_for(c, admin["id"], A2)
for method, url, body in (("POST", f"/api/ads/ad/{one['ad']}/status", {"status": "PAUSED"}),
                          ("POST", f"/api/ads/campaign/{one['campaign']}/budget", {"daily_budget_cents": 2100}),
                          ("POST", f"/api/ads/ad/{one['ad']}/archive", {}),
                          ("POST", f"/api/ads/ad/{one['ad']}/duplicate", {}),
                          ("PATCH", f"/api/leads/{one['lead']}", {"status": "won"}),
                          ("POST", f"/api/leads/{one['lead']}/notes", {"body": "x"}),
                          ("POST", f"/api/leads/{one['lead']}/reply", {"subject": "x", "body": "x"}),
                          ("GET", f"/api/media/video/{one['ad']}%3Ffields%3Did", None),
                          ("POST", f"/api/proposals/{one['proposal']}/approve", {}),
                          ("POST", f"/api/proposals/{one['proposal']}/decline", {}),
                          ("POST", f"/api/ads/ad/{one['ad']}/versions/900/restore", {}),
                          ("POST", "/api/ads/bulk/preview", {"action": "status", "level": "ad", "ids": [one["ad"]], "value": bulk_to}),
                          ("POST", "/api/ads/bulk/apply", {"plan_token": bulk_plan.get("plan_token"), "accept_big": True,
                                                          "confirm_total_cents": (bulk_plan.get("totals") or {}).get("daily_cents")}),
                          ("PUT", f"/api/ads/ad/{one['ad']}/tags", {"tags": {"hook": f"{MARK2} hook"}}),
                          ("POST", f"/api/insights/ad/{one['ad']}/comments/{comment1}/reply", {"message": "x"}),
                          ("POST", f"/api/insights/ad/{one['ad']}/comments/{comment1}/hide", {"hidden": True}),
                          ("POST", f"/api/desk/tasks/{one['task']}/reply", {"prompt": "x"}),
                          ("POST", f"/api/desk/tasks/{one['task']}/again", {}),
                          ("POST", f"/api/desk/tasks/{one['task']}/clear", {}),
                          ("POST", f"/api/desk/attachments/{one['attachment']}/draft", {}),
                          ("POST", f"/api/desk/tasks/{one['task']}/reply", {"prompt": "x", "about_attachment": one["attachment"]}),
                          ("PATCH", f"/api/experiments/{one['exp']}", {"name": "x"}),
                          ("POST", f"/api/builds/{one['build']}/resume", {}),
                          ("POST", f"/api/builds/{one['build']}/publish", {}),
                          ("PATCH", f"/api/views/{one['view']}", {"name": "x"}),
                          ("DELETE", f"/api/views/{one['view']}", None),
                          ("POST", f"/api/alerts/{one['alert']}/snooze", {"mode": "worse"}),
                          ("DELETE", f"/api/alerts/{one['alert']}/snooze", None),
                          ("POST", f"/api/alerts/{one['alert']}/done", {}),
                          ("POST", "/api/diagnose", {"alert_id": one["alert"], "prompt": "x"}),
                          ("POST", "/api/diagnose", {"ad_id": one["ad"], "prompt": "x"})):
    r = c.open(url, method=method, json=body)
    applied = [x for x in ((r.get_json(silent=True) or {}).get("results") or []) if x.get("ok")] if url.endswith("/bulk/apply") else []
    # Refused means a 4xx. A 5xx got past the account check and only failed further on (account 2 has no Page
    # of its own to post a comment with, for one), so it counts as a leak too.
    if r.status_code >= 500 or (r.status_code < 400 and (not url.endswith("/bulk/apply") or applied)):
        cross.append(f"{method} {url} → {r.status_code}")
cross_changed = account1_state() != state_before
import ads_api
import insights
seen = []
if True:
    orig = insights.sync_structure
    insights.sync_structure = lambda: seen.append(account_ctx.current())
    delay, ads_api.RESYNC_DELAY = ads_api.RESYNC_DELAY, 0
    try:
        with account_ctx.use(A2):
            ads_api.resync_later()
        __import__("time").sleep(0.5)
    finally:
        insights.sync_structure = orig
        ads_api.RESYNC_DELAY = delay
with account_ctx.use(1):
    members_seen_from_1 = db.query("SELECT COUNT(*) AS n FROM campaign_members WHERE user_id = %s", (member["id"],), one=True)["n"]
# Audit 3: who hears about an account, which account owns a Meta asset, what a client sees of Claude.
import config
import leads as leads_mod
import notify as notify_mod
import settings_store
import webhooks
tenant = []
acct_admin_email = "admin-qa@burdanova.test"
db.execute("UPDATE users SET notify_new_leads = TRUE WHERE id = %s", (acct_admin["id"],))
with account_ctx.use(1):
    rec1, adm1, staff1 = leads_mod.recipients_for({"campaign_id": one["campaign"]}), notify_mod.admin_ids(), leads_mod.staff_for(one["campaign"])
with account_ctx.use(A2):
    rec2, adm2 = leads_mod.recipients_for({"campaign_id": ids["campaign"]}), notify_mod.admin_ids()
if acct_admin_email in rec1 or "member-qa@burdanova.test" in rec1 or acct_admin["id"] in adm1 or acct_admin["id"] in [u["id"] for u in staff1]:
    tenant.append(f"account 1's leads and alerts reach account 2's people: {rec1} {adm1}")
if acct_admin_email not in rec2 or acct_admin["id"] not in adm2 or admin["id"] not in adm2:
    tenant.append(f"account 2's own admin or the owner is missing from its recipients: {rec2} {adm2}")
before = {k: settings_store.own(k, account_id=A2) for k in ("meta_page_id", "meta_ad_account_id", "meta_dataset_id")}
session_for(c, admin["id"], A2)
for key, value in (("meta_page_id", config.META_DEFAULTS["meta_page_id"]), ("meta_ad_account_id", "act_" + config.META_DEFAULTS["meta_ad_account_id"]),
                   ("meta_dataset_id", config.META_DEFAULTS["meta_dataset_id"])):
    r = c.put("/api/settings/meta", json={key: value})
    if r.status_code != 409:
        tenant.append(f"the owner on account 2 could take Edge Bourne's {key}: {r.status_code}")
r = ac.put("/api/settings/meta", json={"meta_page_id": "555000111"})
if r.status_code != 403:
    tenant.append(f"an account admin on the owner's token could point the account at another Page: {r.status_code}")
for k, v in before.items():
    if settings_store.own(k, account_id=A2) != v:
        settings_store.set(k, v, account_id=A2)
        tenant.append(f"account 2's {k} changed")
# Routing: account 1's built-in Page stays its own; a closed account never wins, whatever the key order,
# and a Page only a closed account names is dropped rather than filed under account 1.
with account_ctx.all_accounts():
    closed_ids = [r["id"] for r in db.query("SELECT id FROM accounts WHERE archived_at IS NOT NULL ORDER BY id")] or [
        db.execute("INSERT INTO accounts (name, archived_at) VALUES ('QA Closed', now()) RETURNING id", returning=True)["id"]]
# Preferably one whose settings key sorts before account 2's (the old code took the first key in text order).
closed_first = next((x for x in closed_ids if f"meta_page_id@{x}" < f"meta_page_id@{A2}"), closed_ids[0])
qa_page = f"9{secrets.randbelow(10**9)}"
try:
    settings_store.set("meta_page_id", config.META_DEFAULTS["meta_page_id"], account_id=A2)
    routed_default = webhooks.account_for_page(config.META_DEFAULTS["meta_page_id"])
    settings_store.set("meta_page_id", qa_page, account_id=A2)
    settings_store.set("meta_page_id", qa_page, account_id=closed_first)
    routed_closed = webhooks.account_for_page(qa_page)
    settings_store.set("meta_page_id", before["meta_page_id"], account_id=A2)
    routed_only_closed = webhooks.account_for_page(qa_page)
finally:
    settings_store.set("meta_page_id", before["meta_page_id"], account_id=A2)
    settings_store.set("meta_page_id", None, account_id=closed_first)
if routed_default != 1 or routed_closed != A2 or routed_only_closed is not None:
    tenant.append(f"lead routing: Edge Bourne's Page → {routed_default}, a Page also named by closed account {closed_first} → "
                  f"{routed_closed}, a Page only it names → {routed_only_closed}")
# A client of account 2 never sees Claude's proposals (there's a pending one on its ad).
cc_proposals = cc.get(f"/api/ads/ad/{two['ad']}").get_json().get("proposals")
admin_proposals = c.get(f"/api/ads/ad/{two['ad']}").get_json().get("proposals")
for url in (f"/api/proposals/{two['proposal']}", f"/api/proposals/{two['proposal']}/check", f"/api/proposals/{two['proposal']}/preview"):
    if cc.get(url).status_code != 404:
        tenant.append(f"a client reads {url}")
if cc_proposals != [] or not admin_proposals or re.search(r'Claude suggests|"proposal_id": [0-9]', cc.get("/api/home").get_data(as_text=True)) \
        or re.search(r'"pending_proposals": [1-9]', json.dumps(cc.get("/api/ads").get_json())):
    tenant.append(f"a client sees Claude's proposals ({len(cc_proposals or [])}) or the admin doesn't ({len(admin_proposals or [])})")
# Failed Telegram deliveries are console-wide: only the owner sees them.
fail = db.execute("INSERT INTO notifications (user_id, channel, kind, title, status, last_error) VALUES (%s, 'telegram', 'qa', 'qa', 'failed', 'QA-TG-FAIL') "
                  "RETURNING id", (admin["id"],), returning=True)
try:
    owner_failed = (c.get("/api/settings").get_json()["telegram"]["failed"] or {}).get("last_error")
    acct_admin_failed = ac.get("/api/settings").get_json()["telegram"]["failed"]
finally:
    db.execute("DELETE FROM notifications WHERE id = %s", (fail["id"],))
if acct_admin_failed != {"n": 0, "last_error": None} or not owner_failed:
    tenant.append(f"Telegram failures: owner sees {owner_failed!r}, account admin sees {acct_admin_failed}")
# W2: a report note or hold from account 2's admin (its cookie still asking for account 1) lands in account 2
# only; a member reads and changes no report.
W2_NOTE = f"{MARK2} report note"
session_for(ac, acct_admin["id"], 1)
w2 = {"note": ac.put("/api/reports/note", json={"kind": "week", "note": W2_NOTE}).status_code,
      "hold": ac.post("/api/reports/hold", json={"kind": "week"}).status_code,
      "member_get": mc.get("/api/reports?kind=week").status_code,
      "member_note": mc.put("/api/reports/note", json={"kind": "week", "note": "x"}).status_code,
      "member_send": mc.post("/api/reports/send", json={"kind": "week", "when": "now", "expect_to": []}).status_code}
with account_ctx.use(1):
    w2_in_1 = db.query("SELECT COUNT(*) AS n FROM client_reports WHERE note = %s", (W2_NOTE,), one=True)["n"]
with account_ctx.use(A2):
    w2_in_2 = db.query("SELECT COUNT(*) AS n FROM client_reports WHERE note = %s AND status = 'waiting'", (W2_NOTE,), one=True)["n"]
    db.execute("DELETE FROM client_reports WHERE note = %s", (W2_NOTE,))
if w2 != {"note": 200, "hold": 200, "member_get": 403, "member_note": 403, "member_send": 403} or w2_in_1 or w2_in_2 != 1:
    tenant.append(f"report review writes: {w2}, rows in account 1: {w2_in_1}, in account 2: {w2_in_2}")
# L2: the same person in two accounts is two people. A lead stored in account 2 with the email and phone of an
# account-1 lead is never linked to it (explicit account_id in the match, RLS, composite foreign keys), and
# account 2's Lead quality names none of account 1's ads.
import leads as leads_mod
from datetime import datetime, timezone
SAME = {"field_data": [{"name": "full_name", "values": ["Leak QA Person"]}, {"name": "email", "values": ["leak-qa@qa.edgebourne.com"]},
                       {"name": "phone_number", "values": ["+16195557790"]}], "is_organic": True,
        "created_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")}
l2_ids = {}
for acct, key in ((1, "LEAKQAl2a"), (A2, "LEAKQAl2b")):
    with account_ctx.use(acct):
        db.execute("DELETE FROM leads WHERE meta_lead_id = %s", (key,))
        l2_ids[acct], _ = leads_mod.store_lead({**SAME, "id": key})
        db.execute("UPDATE leads SET alerted_at = now() WHERE id = %s", (l2_ids[acct],))
with account_ctx.all_accounts():
    linked = db.query("SELECT id, repeat_of, earlier_lead_id FROM leads WHERE meta_lead_id IN ('LEAKQAl2a', 'LEAKQAl2b') AND (repeat_of IS NOT NULL OR earlier_lead_id IS NOT NULL)")
    a1_ads = [r["id"] for r in db.query("SELECT id FROM ads WHERE account_id = 1")]
session_for(c, admin["id"], A2)
q2 = c.get("/api/performance/quality?range=30&by=ad").get_data(as_text=True)
seen_ads = [a for a in a1_ads if a in q2]
cross_link = c.post(f"/api/leads/{l2_ids[A2]}/same-person", json={"other_id": l2_ids[1]}).status_code
if linked or seen_ads or cross_link != 404:
    tenant.append(f"lead quality across accounts: linked {linked}, account 1 ads in account 2's Lead quality {seen_ads}, link across {cross_link}")
with account_ctx.all_accounts():
    db.execute("DELETE FROM leads WHERE meta_lead_id IN ('LEAKQAl2a', 'LEAKQAl2b')")
session_for(c, admin["id"], 1)
csrf = app.test_client()
session_for(csrf, admin["id"], 1)
csrf_status = csrf.post("/api/refresh", data="", content_type="text/plain").status_code
# FU-B: the account spending limit. A spend_limit suggestion in account 1 is neither seen nor accepted from account 2;
# teammates and clients can't read or change any limit; only the console's owner clears a pause.
with account_ctx.use(1):
    limit_pid = db.execute("""INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, proposed_value, payload, status)
                              VALUES (%s, 'spend_limit', 'LEAK QA limit', 'account', %s, '$999', %s, 'pending') RETURNING id""",
                           (one["task"], "act_" + str(settings_store.get("meta_ad_account_id", account_id=1)),
                            json.dumps({"proposed_cents": 99900})), returning=True)["id"]
session_for(ac, acct_admin["id"], 1)
session_for(mc, member["id"])
session_for(cc, client["id"])
fub = {"approve_from_2": ac.post(f"/api/proposals/{limit_pid}/approve", json={"from_cents": 15000, "to_cents": 99900}).status_code,
       "read_from_2": ac.get(f"/api/proposals/{limit_pid}").status_code,
       "check_from_2": ac.get(f"/api/proposals/{limit_pid}/check").status_code,
       "member_get": mc.get("/api/settings/spend-limit").status_code,
       "member_post": mc.post("/api/settings/spend-limit", json={"from_cents": 15000, "to_cents": 99900}).status_code,
       "client_get": cc.get("/api/settings/spend-limit").status_code,
       "client_post": cc.post("/api/settings/spend-limit", json={"from_cents": 15000, "to_cents": 99900}).status_code,
       "account_admin_unblock": ac.post("/api/settings/spend-limit/unblock", json={}).status_code}
with account_ctx.use(1):
    fub["status_in_1"] = db.query("SELECT status FROM desk_proposals WHERE id = %s", (limit_pid,), one=True)["status"]
    db.execute("DELETE FROM desk_proposals WHERE id = %s", (limit_pid,))
# FU-D: a preview is read only in its own account; clients and teammates never reach the Claude page's routes.
session_for(c, admin["id"], A2)
session_for(ac, acct_admin["id"], 1)
session_for(mc, member["id"])
session_for(cc, client["id"])
fud = {"switched_owner_reads_account1": c.get(f"/api/desk/attachments/{one['attachment']}").status_code,
       "account2_admin_reads_account1": ac.get(f"/api/desk/attachments/{one['attachment']}").status_code,
       "account2_admin_reads_own": ac.get(f"/api/desk/attachments/{two['attachment']}").status_code,
       "client_reads_own": cc.get(f"/api/desk/attachments/{two['attachment']}").status_code,
       "member_reads_own": mc.get(f"/api/desk/attachments/{two['attachment']}").status_code,
       "client_turns_on": cc.post("/api/auth/full-access", json={"password": "x"}).status_code,
       "account2_admin_turns_on": ac.post("/api/auth/full-access", json={"password": "x"}).status_code,
       "desk_lists_account1_preview": MARK1 + "preview" in c.get("/api/desk").get_data(as_text=True)}
session_for(c, admin["id"], 1)
out.update({"leaks": l1 + l2 + l2b + l3, "full_access": fud, "routes_checked": [n1, n2, n3], "admin_sees_account2_on_account2": sees_own,
            "client_sees_own_leads": client_sees_own, "client_switch_status": switch, "client_stays_on_own_account": still,
            "client_writes_not_refused": writes,
            "member_and_account_admin_routes": [n4, n5], "leaks_member_and_account_admin": l4 + l5,
            "account_admin_limits": acct_admin_limits, "cross_account_writes": cross, "cross_account_writes_changed_account1": cross_changed,
            "tables_without_isolation": unisolated, "isolated_tables": len(tables) - len(unisolated) - len(RLS_EXEMPT),
            "app_role_bypasses_rls": app_role_bypasses,
            "resync_thread_account": seen, "account2_assignments_seen_from_1": members_seen_from_1,
            "csrf_without_header": csrf_status, "routes_showing_own_mark": shown, "routes_crashed": crashed,
            "tenant_problems": tenant, "second_account": fua, "spend_limit": fub})
print(json.dumps(out))
