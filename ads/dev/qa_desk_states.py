"""QA helper: the Claude desk's task states and run passes against the real database (audit A3-7,
A3-29, A3-88, A3-119, A3-127). Plays the Mac with a throwaway key, removes every task it made and
puts the real key back. Prints JSON: each check's name → true/false, plus details."""
import json

import account_ctx
import db
import desk_api
import settings_store
from app import create_app

app = create_app(run_migrations=False)
KEY = "qa-desk-states-key"
MAC = {"Authorization": f"Bearer {KEY}", "X-Bridge-Host": "qa"}
made, out = [], {}
rank = [-2_000_000]


def task(prompt, account=1, kind="question", options=None, created_by=None, front=True):
    """A queued task; front=True puts it ahead of everything else in line (claimed next)."""
    rank[0] -= 1
    with account_ctx.all_accounts():
        r = db.execute("""INSERT INTO desk_tasks (account_id, kind, prompt, queue_rank, options, created_by)
                          VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                       (account, kind, f"QA states: {prompt}", rank[0] if front else 0, json.dumps(options or {}), created_by), returning=True)
    made.append(r["id"])
    return r["id"]


def row(tid):
    with account_ctx.all_accounts():
        return db.query("SELECT status, queue_rank, claim_hash, mentions FROM desk_tasks WHERE id = %s", (tid,), one=True)


def claim(c, version="2.0", claim_header=None):
    h = {**MAC, "X-Bridge-Version": version, **({"X-Desk-Claim": claim_header} if claim_header else {})}
    r = c.get("/api/agent/wait?timeout=0", headers=h)
    return r.status_code, (r.get_json() if r.status_code == 200 else None)


def run(token):
    return {**MAC, "X-Bridge-Version": "2.0", "X-Desk-Claim": token}


KEPT = ("agent_key_hash", "bridge_version", "bridge_last_seen", "bridge_host")
old = {k: settings_store.get(k) for k in KEPT}
settings_store.set("agent_key_hash", desk_api.key_hash(KEY))
try:
    c = app.test_client()

    # A helper without passes (before 2.0) runs only the owners' words: a teammate's request waits, and
    # the Claude page asks for the update.
    mine0 = task("the owner's, for an old helper", created_by=1)
    theirs0 = task("a teammate's, for an old helper", created_by=3)
    _, old0 = claim(c, "1.9")
    out["a helper without passes skips a teammate's request and takes the owner's"] = bool(old0) and old0["id"] == mine0
    out["the Claude page asks to update a helper without passes"] = desk_api.bridge_status()["needs_update"] is True
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = ANY(%s)", ([mine0, theirs0],))

    # A helper older than 1.9 leaves follow-ups in line and gets no pass; 2.0 takes them, with a pass.
    reply = task("a follow-up", options={"reply": True})
    plain = task("a plain question")
    _, older = claim(c, "1.7")
    out["an older helper skips a follow-up and gets no pass"] = bool(older) and older["id"] == plain and older.get("claim_token") is None
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = %s", (plain,))
    _, got = claim(c)
    token = got and got.get("claim_token")
    out["a 2.0 helper claims the follow-up with a pass, stored only hashed"] = (
        bool(got) and got["id"] == reply and bool(token) and row(reply)["claim_hash"] == desk_api.key_hash(token))
    out["a 2.0 helper needs no update and learns the request's business"] = (
        desk_api.bridge_status()["needs_update"] is False and bool(got) and got.get("account_name") == "Edge Bourne")

    # The run's pass reaches its own request only.
    other = task("someone else's request", front=False)
    out["the run reads its own request"] = c.get(f"/api/agent/tasks/{reply}", headers=run(token)).status_code == 200
    out["the run can't read another request"] = c.get(f"/api/agent/tasks/{other}", headers=run(token)).status_code == 403
    out["the run can't see the line or claim work"] = (
        c.get("/api/agent/queue", headers=run(token)).status_code == 403 and claim(c, claim_header=token)[0] == 403)
    out["the run can't report on another request"] = c.post(f"/api/agent/tasks/{other}/report", headers=run(token),
                                                           json={"title": "x", "body": "y"}).status_code == 403
    out["the Mac key alone can't use a request a run holds"] = c.post(f"/api/agent/tasks/{reply}/report", headers={**MAC, "X-Bridge-Version": "2.0"},
                                                                     json={"title": "x", "body": "y"}).status_code == 403
    out["the run reports on its own request"] = c.post(f"/api/agent/tasks/{reply}/report", headers=run(token),
                                                      json={"title": "Checked", "body": "Fine."}).status_code == 201
    out["a made-up pass is refused"] = c.get("/api/agent/snapshot", headers=run("not-a-pass")).status_code == 409

    # A run for account 2 answers for account 2, whatever account the call names.
    second = task("a Burdanova question", account=2)
    _, got2 = claim(c)
    snap = c.get("/api/agent/snapshot", headers={**run(got2["claim_token"]), "X-Account": "1"})
    out["a run's snapshot is its request's account"] = snap.status_code == 200 and snap.get_json()["account"]["id"] == 2 and got2["id"] == second

    # Stopped from the page: everything the run posts is refused, and the Mac can see it was stopped.
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = %s", (reply,))
    out["after Stop the run's report and keep-alive are refused"] = (
        c.post(f"/api/agent/tasks/{reply}/report", headers=run(token), json={"title": "x", "body": "y"}).status_code == 409
        and c.post(f"/api/agent/tasks/{reply}/status", headers=run(token), json={"status": "running"}).status_code == 409)
    seen = c.get(f"/api/agent/tasks/{reply}", headers=run(token))
    out["the Mac reads that it was stopped"] = seen.status_code == 200 and seen.get_json()["status"] == "cancelled"
    out["a stopped run's pass no longer reads the account"] = c.get("/api/agent/snapshot", headers=run(token)).status_code == 403

    # Claimed, but the Mac never said it started (the answer got lost): back in line, old pass dead.
    lost = task("an answer that got lost")
    _, got3 = claim(c)
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET claimed_at = now() - interval '4 minutes' WHERE id = %s", (lost,))
        desk_api._expire_stale()
    r3 = row(lost)
    out["a claim never started goes back in line"] = got3["id"] == lost and r3["status"] == "queued" and r3["claim_hash"] is None
    out["the lost claim's pass is dead"] = c.get(f"/api/agent/tasks/{lost}", headers=run(got3["claim_token"])).status_code == 409

    # Running but silent for 30 minutes: failed. Running and reporting: left alone.
    quiet, busy = task("quiet", front=False), task("busy", front=False)
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'running', claimed_at = now() - interval '40 minutes', updated_at = now() - interval '31 minutes' WHERE id = %s", (quiet,))
        db.execute("UPDATE desk_tasks SET status = 'running', claimed_at = now() - interval '40 minutes', updated_at = now() WHERE id = %s", (busy,))
        desk_api._expire_stale()
    out["a silent run fails, a reporting one keeps going"] = (row(quiet)["status"], row(busy)["status"]) == ("failed", "running")

    # Run next in account 2 goes ahead of account 1's line too (the Mac takes the next across accounts).
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = %s", (lost,))
    front1 = task("account 1's front")
    back2 = task("account 2's last", account=2, front=False)
    with c.session_transaction() as s:
        s["user_id"] = 1
    c.set_cookie("ebads_account", "2")
    moved = c.post(f"/api/desk/tasks/{back2}/next", headers={"X-Requested-With": "ebads"}).status_code
    out["Run next in account 2 puts it ahead of account 1's line"] = moved == 200 and row(back2)["queue_rank"] < row(front1)["queue_rank"]
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = ANY(%s) AND status = 'queued'", (made,))

    # Who asked: a teammate's request gets no web on the Mac; the owner's does.
    mine, theirs = task("the owner's", created_by=1, front=False), task("a teammate's", account=2, created_by=3, front=False)
    out["the owner's request is marked as the owner's, a teammate's isn't"] = (
        c.get(f"/api/agent/tasks/{mine}", headers={**MAC, "X-Bridge-Version": "2.0"}).get_json().get("from_owner") is True
        and c.get(f"/api/agent/tasks/{theirs}", headers={**MAC, "X-Bridge-Version": "2.0"}).get_json().get("from_owner") is False)

    # A finished answer stores the ads it names, once.
    with account_ctx.use(1):  # the test client's requests leave the last account set in this thread
        ad = db.query("SELECT id, name FROM ads WHERE effective_status <> 'DELETED' AND name IS NOT NULL ORDER BY id LIMIT 1", one=True)
    named = task("names an ad")
    _, got4 = claim(c)
    c.post(f"/api/agent/tasks/{named}/status", headers=run(got4["claim_token"]), json={"status": "done", "summary": f"Looked at {ad['name']}."})
    out["a finished answer stores the ads it names"] = got4["id"] == named and ad["id"] in (row(named)["mentions"] or [])

    # The page polls: an unchanged answer is a 304 with no body.
    c.set_cookie("ebads_account", "1")
    first = c.get("/api/desk")
    again = c.get("/api/desk", headers={"If-None-Match": first.headers.get("ETag") or "none"})
    out["an unchanged Claude page answers 304"] = first.status_code == 200 and again.status_code == 304 and not again.get_data()
finally:
    with account_ctx.all_accounts():
        if made:
            db.execute("DELETE FROM desk_reports WHERE task_id = ANY(%s)", (made,))
            db.execute("DELETE FROM desk_proposals WHERE task_id = ANY(%s)", (made,))
            db.execute("DELETE FROM desk_tasks WHERE id = ANY(%s)", (made,))
    for k, v in old.items():
        settings_store.set(k, v)
print(json.dumps({"failed": [k for k, v in out.items() if not v], "passed": len([v for v in out.values() if v])}))
