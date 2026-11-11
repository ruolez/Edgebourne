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

from werkzeug.security import generate_password_hash

import account_ctx
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
    once("meta_changes", {"user_id": admin_id, "level": "ad", "entity_id": ad, "entity_name": f"{mark} ad", "campaign_id": campaign,
                          "action": "status", "old_value": "ACTIVE", "new_value": f"{mark} change", "ok": True, "account_id": acct}, "new_value")
    once("ad_versions", {"ad_id": ad, "number": 900, "creative_id": f"{mark}creative", "label": f"{mark} version", "title": f"{mark} version",
                         "body": f"{mark} version body", "account_id": acct}, "label")
    view = once("saved_views", {"user_id": admin_id, "page": "ads", "name": f"{mark} view", "query": "level=ad", "shared": True, "account_id": acct}, "name")
    spec = json.dumps(builds_api.clean({"name": f"{mark} build", "daily_budget_cents": 1500, "form_id": "1132280359202136"}))
    build = once("campaign_builds", {"spec": spec, "status": "partial", "client_key": f"{mark}build", "created_by": admin_id, "account_id": acct}, "client_key")
    db.execute("UPDATE campaign_builds SET spec = %s WHERE id = %s", (spec, build["id"]))  # keeps up with the spec's shape
    once("alerts", {"rule": "qa", "dedupe_key": f"{mark}alert", "level": "warn", "title": f"{mark} alert", "kind": "event",
                    "entity_id": ad, "campaign_id": campaign, "account_id": acct}, "dedupe_key")
    once("lead_notes", {"lead_id": lead, "user_id": admin_id, "body": f"{mark} note", "account_id": acct}, "body")
    once("lead_replies", {"lead_id": lead, "user_id": admin_id, "to_email": "qa@example.com", "subject": f"{mark} reply", "body": f"{mark} reply",
                          "status": "sent", "account_id": acct}, "subject")
    once("activity", {"user_id": admin_id, "actor": "qa", "action": "qa.mark", "subject": f"{mark} activity", "account_id": acct}, "subject")
    once("inbox_reads", {"user_id": admin_id, "item_key": f"{mark}read", "account_id": acct}, "item_key")
    return {"proposal": proposal["id"], "view": view["id"], "build": build["id"]}

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
                           ("desk_tasks", "prompt")):
                db.execute(f"DELETE FROM {t} WHERE account_id = 1 AND {col} LIKE %s", (MARK1 + "%",))
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
             "proposal_id": other["proposal"], "build_id": other["build"], "view_id": other["view"], "number": 900}.get(name, "1")
        url = re.sub(r"<(?:[a-z]+:)?" + name + ">", str(v), url)
    return url


SKIP = re.compile(r"^/api/(agent/|auth/logout)|/wait$|/stream$|^/webhooks/")


shown = {}  # label → routes that show the walking account's own mark (proof the seeds are reachable)
crashed = []  # a route that fails with a 5xx can't show whether it leaks


def walk(client, forbidden, other, label, own=None):
    leaks, checked = [], 0
    shown[label] = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or not rule.rule.startswith("/api/") or SKIP.search(rule.rule):
            continue
        url = fill(rule, other)
        r = client.get(url)
        checked += 1
        body = r.get_data(as_text=True)
        for mark in forbidden:
            if mark in body:
                leaks.append(f"{label}: {url} ({r.status_code}) shows {mark!r}")
        if own and own in body:
            shown[label].append(rule.rule)
        if r.status_code >= 500:
            crashed.append(f"{label}: {url} ({r.status_code})")
    return leaks, checked


def session_for(client, user_id, account=None):
    with client.session_transaction() as s:
        s["user_id"] = user_id
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
        if status != 403 and not re.match(r"^/api/(auth/(logout|password|me)|me/push(/.*)?)$", rule.rule):
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
                          ("PATCH", f"/api/experiments/{one['exp']}", {"name": "x"}),
                          ("POST", f"/api/builds/{one['build']}/resume", {}),
                          ("POST", f"/api/builds/{one['build']}/publish", {}),
                          ("PATCH", f"/api/views/{one['view']}", {"name": "x"}),
                          ("DELETE", f"/api/views/{one['view']}", None)):
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
    try:
        with account_ctx.use(A2):
            ads_api.resync_later()
        __import__("time").sleep(0.3)
    finally:
        insights.sync_structure = orig
with account_ctx.use(1):
    members_seen_from_1 = db.query("SELECT COUNT(*) AS n FROM campaign_members WHERE user_id = %s", (member["id"],), one=True)["n"]
csrf = app.test_client()
session_for(csrf, admin["id"], 1)
csrf_status = csrf.post("/api/refresh", data="", content_type="text/plain").status_code
out.update({"leaks": l1 + l2 + l2b + l3, "routes_checked": [n1, n2, n3], "admin_sees_account2_on_account2": sees_own,
            "client_sees_own_leads": client_sees_own, "client_switch_status": switch, "client_stays_on_own_account": still,
            "client_writes_not_refused": writes,
            "member_and_account_admin_routes": [n4, n5], "leaks_member_and_account_admin": l4 + l5,
            "account_admin_limits": acct_admin_limits, "cross_account_writes": cross, "cross_account_writes_changed_account1": cross_changed,
            "tables_without_isolation": unisolated, "isolated_tables": len(tables) - len(unisolated) - len(RLS_EXEMPT),
            "app_role_bypasses_rls": app_role_bypasses,
            "resync_thread_account": seen, "account2_assignments_seen_from_1": members_seen_from_1,
            "csrf_without_header": csrf_status, "routes_showing_own_mark": shown, "routes_crashed": crashed})
print(json.dumps(out))
