"""QA: agency mode must never show one account's data in another (roadmap 7.1 leak test).

Seeds account 2 ("Burdanova QA") with marked data, then calls every GET route of the app as
(a) the admin on account 1, (b) the admin switched to account 2, (c) account 2's client, with
ids from the *other* account wherever a route takes one. Prints a JSON verdict."""
import json
import re
import secrets

from werkzeug.security import generate_password_hash

import account_ctx
import db
from app import create_app

MARK2 = "ACCT2MARK"
ACCT1_MARKS = ["One simple system", "Free intro call - Leads", "SoCal business owners"]

app = create_app(run_migrations=False)

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
    one = {"ad": "120252672229040312", "adset": "120252672227950312", "campaign": "120252638288040312",
           "lead": db.query("SELECT id FROM leads WHERE account_id = 1 ORDER BY id LIMIT 1", one=True)["id"],
           "task": db.query("SELECT id FROM desk_tasks WHERE account_id = 1 ORDER BY id DESC LIMIT 1", one=True)["id"]}
two = {"ad": ids["ad"], "adset": ids["adset"], "campaign": ids["campaign"], "lead": lead["id"], "task": task["id"], "exp": exp["id"]}


def fill(rule, other):
    """A GET route with its parameters filled with the other account's ids."""
    url = rule.rule
    for name in rule.arguments:
        v = {"ad_id": other["ad"], "adset_id": other["adset"], "campaign_id": other["campaign"], "entity_id": other["ad"],
             "lead_id": other["lead"], "task_id": other["task"], "exp_id": other.get("exp", 1), "id": other["lead"]}.get(name, "1")
        url = re.sub(r"<(?:[a-z]+:)?" + name + ">", str(v), url)
    return url


SKIP = re.compile(r"^/api/(agent/|auth/logout)|/wait$|/stream$|^/webhooks/")


def walk(client, forbidden, other, label):
    leaks, checked = [], 0
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
    return leaks, checked


def session_for(client, user_id, account=None):
    with client.session_transaction() as s:
        s["user_id"] = user_id
    client.set_cookie("ebads_account", str(account or 1))


out = {"account2": A2}
c = app.test_client()
session_for(c, admin["id"], 1)
l1, n1 = walk(c, [MARK2], two, "admin on account 1")
session_for(c, admin["id"], A2)
l2, n2 = walk(c, ACCT1_MARKS, one, "admin on account 2")
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
        if status != 403 and not re.match(r"^/api/(auth/(logout|password|me)|me/push(/.*)?|accounts/switch)$", rule.rule):
            writes.append(f"{m} {rule.rule} → {status}")
out.update({"leaks": l1 + l2 + l3, "routes_checked": [n1, n2, n3], "admin_sees_account2_on_account2": sees_own,
            "client_sees_own_leads": client_sees_own, "client_switch_status": switch, "client_stays_on_own_account": still,
            "client_writes_not_refused": writes})
print(json.dumps(out))
