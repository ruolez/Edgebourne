"""QA helper: the Claude desk's task states and run passes against the real database (audit A3-7,
A3-29, A3-88, A3-119, A3-127). Plays the Mac with a throwaway key, removes every task it made and
puts the real key back. Prints JSON: each check's name → true/false, plus details."""
import json

import account_ctx
import auth
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
        s["sk"] = auth.new_session_key(1)
        s["sv"] = db.query("SELECT session_version FROM users WHERE id = 1", one=True)["session_version"]
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

    # ---------------------------------------------------------------- FU-D: full access, decided by the server
    import io
    import struct
    full = {}
    W = {"X-Requested-With": "ebads"}

    def owner_client(account=1):
        oc = app.test_client()
        key = auth.new_session_key(1)
        with oc.session_transaction() as s:
            s["user_id"] = 1
            s["sk"] = key
            s["sv"] = db.query("SELECT session_version FROM users WHERE id = 1", one=True)["session_version"]
        oc.set_cookie("ebads_account", str(account))
        return oc, desk_api.key_hash(key)

    def unlock(kh, on=True):
        db.execute("UPDATE user_sessions SET full_until = CASE WHEN %s THEN now() + interval '2 hours' END WHERE key_hash = %s", (on, kh))

    def ask(cl, prompt, body=None):
        r = cl.post("/api/desk/tasks", headers=W, json={"kind": "question", "prompt": f"QA FU-D: {prompt}", **(body or {})})
        tid = r.get_json()["id"]
        made.append(tid)
        front(tid)
        return tid

    def front(tid):
        rank[0] -= 1
        with account_ctx.all_accounts():
            db.execute("UPDATE desk_tasks SET queue_rank = %s WHERE id = %s", (rank[0], tid))

    def stored(tid):
        with account_ctx.all_accounts():
            return db.query("SELECT full_session, access, access_note, status FROM desk_tasks WHERE id = %s", (tid,), one=True)

    def take(version="3.0"):
        code, got = claim(c, version)
        return got or {}

    def done(tid, token, version="3.0"):
        c.post(f"/api/agent/tasks/{tid}/status", headers={**run(token), "X-Bridge-Version": version}, json={"status": "done", "summary": "ok"})

    oc, okh = owner_client()
    unlock(okh)
    # 1. The owner, unlocked, types a question; a 3.0 helper claims it: full in the claim and in a fresh read with the pass.
    t1 = ask(oc, "full one")
    g1 = take()
    read1 = c.get(f"/api/agent/tasks/{t1}", headers={**run(g1.get("claim_token")), "X-Bridge-Version": "3.0"}).get_json() or {}
    full["the owner's own typed request, unlocked, claimed by desk 3.0 runs with full access"] = (
        g1.get("id") == t1 and g1.get("access") == "full" and read1.get("access") == "full" and "full_session" not in g1 and "full_session" not in read1)
    # 9. Previews: only with the pass, only while open, typed from the bytes, size-capped.
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 4, 5) + b"\x08\x06\x00\x00\x00" + b"\x00" * 40
    up = lambda tid, data, name, hdr: c.post(f"/api/agent/tasks/{tid}/attachments", headers=hdr,
                                             data={"file": (io.BytesIO(data), name), "caption": "QA 4:5 static"}, content_type="multipart/form-data")
    no_pass = up(t1, png, "a.png", {**MAC, "X-Bridge-Version": "3.0"}).status_code
    with_pass = up(t1, png, "a.png", {**run(g1["claim_token"]), "X-Bridge-Version": "3.0"})
    gif = up(t1, b"GIF89a" + b"\x00" * 40, "a.png", {**run(g1["claim_token"]), "X-Bridge-Version": "3.0"})
    big = up(t1, b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp41\x00\x00\x00\x08free" + b"\x00" * (61 * 1024 * 1024), "b.mp4",
             {**run(g1["claim_token"]), "X-Bridge-Version": "3.0"})
    att = (with_pass.get_json() or {}).get("id")
    full["a preview needs the run's pass, is typed from its bytes (a GIF named .png refused) and size-capped (61 MB refused)"] = (
        no_pass == 403 and with_pass.status_code == 201 and (with_pass.get_json() or {}).get("width") == 4 and gif.status_code == 400
        and "Only JPG, PNG, WebP images or MP4 videos" in (gif.get_json() or {}).get("error", "") and big.status_code == 400)
    ranged = oc.get(f"/api/desk/attachments/{att}", headers={"Range": "bytes=0-1"})
    whole = oc.get(f"/api/desk/attachments/{att}")
    full["the owner reads the preview same origin, typed, private, with Range requests"] = (
        ranged.status_code == 206 and ranged.get_data() == png[:2] and whole.status_code == 200 and whole.mimetype == "image/png"
        and whole.headers.get("Cache-Control") == "private, max-age=3600" and "inline" in whole.headers.get("Content-Disposition", ""))
    listed = [a for t in (oc.get("/api/desk").get_json() or {}).get("tasks", []) if t["id"] == t1 for a in t.get("attachments", [])]
    full["the Claude page lists the preview without its bytes"] = listed[:1] == [{"id": att, "task_id": t1, "kind": "image", "name": "a.png",
                                                                                "caption": "QA 4:5 static", "width": 4, "height": 5, "duration_ms": None,
                                                                                "pruned": False, "drafted": False, "next": None}]
    done(t1, g1["claim_token"])
    full["a finished request takes no more previews"] = up(t1, png, "a.png", {**run(g1["claim_token"]), "X-Bridge-Version": "3.0"}).status_code == 409

    # 2. The same request on a helper older than 3.0: sandboxed, with the update note.
    t2 = ask(oc, "old helper")
    g2 = take("2.6")
    full["a helper older than 3.0 runs it with the usual tools and says it needs the update"] = (
        g2.get("id") == t2 and g2.get("access") == "sandbox" and stored(t2)["access_note"] == "Your Mac helper needs the update for full access (desk 3.0).")
    done(t2, g2.get("claim_token"), "2.6")
    # 3. Locked between asking and the claim.
    t3 = ask(oc, "locked before claim")
    unlock(okh, False)
    g3 = take()
    full["locked before the Mac picked it up: usual tools, said so"] = (
        g3.get("id") == t3 and g3.get("access") == "sandbox" and stored(t3)["access_note"] == "Full access was locked before your Mac picked this up.")
    done(t3, g3.get("claim_token"))
    # 5 (refusal). Locked: a new request isn't marked at all; Lock now with the route works for the owner only.
    t3b = ask(oc, "asked while locked")
    full["asked while locked: never marked for full access"] = stored(t3b)["full_session"] is None
    # 4. Signed out before the claim (the sign-in's row is gone).
    unlock(okh)
    t4 = ask(oc, "signed out before claim")
    oc.post("/api/auth/logout", headers=W)
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = %s", (t3b,))
    g4 = take()
    full["signed out before the Mac picked it up: usual tools, said so"] = (
        g4.get("id") == t4 and g4.get("access") == "sandbox" and "signed out" in (stored(t4)["access_note"] or ""))
    done(t4, g4.get("claim_token"))
    # 7. A body asking for full access gets nothing (an account admin, and the owner while locked).
    oc, okh = owner_client(2)
    ac = app.test_client()
    with ac.session_transaction() as s:
        s["user_id"] = 4
        s["sk"] = auth.new_session_key(4)
        s["sv"] = db.query("SELECT session_version FROM users WHERE id = 4", one=True)["session_version"]
    forged = {"full": True, "access": "full", "options": {"access": "full"}}
    t7 = ask(ac, "an account admin asks for full", forged)
    t7b = ask(oc, "the owner, locked, asks for full", forged)
    full["a request body can't ask for full access (an account admin, or the owner while locked)"] = (
        stored(t7)["full_session"] is None and stored(t7b)["full_session"] is None)
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = ANY(%s)", ([t7, t7b],))
    # 5a. In another account nothing is marked: its admins read the answers and its people write the Meta names a run
    # reads (security review). /me names the one account where full access works.
    unlock(okh)
    t5x = ask(oc, "a conversation in account 2")
    g5x = take()
    full["in another account the owner's own typed request, unlocked, is never marked and runs with the usual tools"] = (
        stored(t5x)["full_session"] is None and g5x.get("id") == t5x and g5x.get("access") == "sandbox"
        and (oc.get("/api/auth/me").get_json() or {}).get("full_access", {}).get("home", {}).get("id") == 1)
    done(t5x, g5x.get("claim_token"))
    # A second owner (admin of every account) made later never gets the flag.
    from werkzeug.security import generate_password_hash
    second = db.query("SELECT id FROM users WHERE email = 'qa-second-owner@edgebourne.test'", one=True) or db.execute(
        "INSERT INTO users (email, name, password_hash, role) VALUES ('qa-second-owner@edgebourne.test', 'QA Second Owner', %s, 'admin') RETURNING id",
        (generate_password_hash("qa-second-owner-pass"),), returning=True)
    db.execute("UPDATE users SET is_active = TRUE, account_id = NULL, role = 'admin', full_access_allowed = FALSE, password_hash = %s WHERE id = %s",
               (generate_password_hash("qa-second-owner-pass"), second["id"]))
    so = app.test_client()
    with so.session_transaction() as s:
        s["user_id"] = second["id"]
        s["sk"] = auth.new_session_key(second["id"])
        s["sv"] = db.query("SELECT session_version FROM users WHERE id = %s", (second["id"],), one=True)["session_version"]
    so.set_cookie("ebads_account", "1")
    # 5. Someone else (the second owner) replies in the owner's conversation: the owner's next turn runs with the usual tools.
    oc, okh = owner_client(1)
    unlock(okh)
    t5 = ask(oc, "a conversation in account 1")
    g5 = take()
    done(t5, g5.get("claim_token"))
    r5 = so.post(f"/api/desk/tasks/{t5}/reply", headers=W, json={"prompt": "QA FU-D: the second owner adds a line"})
    t5a = r5.get_json()["id"]
    made.append(t5a)
    front(t5a)
    g5a = take()
    done(t5a, g5a.get("claim_token"))
    r5b = oc.post(f"/api/desk/tasks/{t5}/reply", headers=W, json={"prompt": "QA FU-D: the owner's next turn"})
    t5b = r5b.get_json()["id"]
    made.append(t5b)
    front(t5b)
    g5b = take()
    full["after someone else wrote in the conversation, the owner's next turn runs with the usual tools"] = (
        g5.get("access") == "full" and stored(t5a)["full_session"] is None and stored(t5b)["full_session"] is not None
        and g5b.get("id") == t5b and g5b.get("access") == "sandbox"
        and stored(t5b)["access_note"] == "Someone else wrote in this conversation, so it ran with the usual tools.")
    done(t5b, g5b.get("claim_token"))
    # A claim whose answer was lost goes back in line as sandbox: only a new claim's own decision can raise it again,
    # so a lock in between holds (review: a requeued row kept 'full').
    t5r = ask(oc, "claimed, answer lost, locked, claimed again")
    g5r = take()
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET claimed_at = now() - interval '10 minutes' WHERE id = %s", (t5r,))
        desk_api._expire_stale()
    requeued = stored(t5r)
    unlock(okh, False)
    front(t5r)
    g5r2 = take()
    full["a requeued claim starts again with the usual tools, and a lock before the second claim holds"] = (
        g5r.get("access") == "full" and requeued["status"] == "queued" and requeued["access"] == "sandbox" and requeued["access_note"] is None
        and g5r2.get("id") == t5r and g5r2.get("access") == "sandbox" and stored(t5r)["access_note"] == "Full access was locked before your Mac picked this up.")
    done(t5r, g5r2.get("claim_token"))
    unlock(okh)
    # Words from a link (?ask=, Tests' "Make more like this") and the Research page never run with full access; a
    # conversation a link started keeps later turns on the usual tools too.
    t5p = ask(oc, "made more like this from a test name", {"origin": "prefill"})
    t5q = ask(oc, "a Research page question", {"origin": "research", "kind": "research"})
    g5p = take()
    done(t5p, g5p.get("claim_token"))
    g5q = take()
    done(t5q, g5q.get("claim_token"))
    r5p = oc.post(f"/api/desk/tasks/{t5p}/reply", headers=W, json={"prompt": "QA FU-D: my own words after a link"})
    t5pr = r5p.get_json()["id"]
    made.append(t5pr)
    front(t5pr)
    g5pr = take()
    with account_ctx.all_accounts():
        opts = {r["id"]: r["options"] for r in db.query("SELECT id, options FROM desk_tasks WHERE id = ANY(%s)", ([t5p, t5q],))}
    full["a link's words and the Research page keep the usual tools; a conversation a link started stays on them"] = (
        stored(t5p)["full_session"] is None and stored(t5q)["full_session"] is None and opts == {t5p: {"prefill": True}, t5q: {"research_page": True}}
        and [g5p.get("access"), g5q.get("access")] == ["sandbox", "sandbox"] and stored(t5pr)["full_session"] is not None
        and g5pr.get("id") == t5pr and g5pr.get("access") == "sandbox" and "your own typing" in (stored(t5pr)["access_note"] or ""))
    done(t5pr, g5pr.get("claim_token"))
    # Nobody else resets the flagged owner's password, changes his access or deactivates him; a temporary password
    # (an admin's reset) never unlocks (security review: a second owner could reset him, sign in and unlock).
    team = [so.patch("/api/team/1", headers=W, json=body).status_code for body in
            ({"reset_password": True}, {"role": "account_admin"}, {"is_active": False}, {"role": "admin"})]
    db.execute("UPDATE users SET must_change_password = TRUE WHERE id = 1")
    try:
        tc, tkh = owner_client()
        temp = tc.post("/api/auth/full-access", headers=W, json={"password": "localdev-pass-123"})
    finally:
        db.execute("UPDATE users SET must_change_password = FALSE WHERE id = 1")
    full["nobody else can reset the full-access owner's password, change his access or deactivate him; a temporary password never unlocks"] = (
        team == [403, 403, 403, 200] and db.query("SELECT is_active AND role = 'admin' AND account_id IS NULL AS ok FROM users WHERE id = 1", one=True)["ok"]
        and temp.status_code == 403 and "Choose your own password" in (temp.get_json() or {}).get("error", "")
        and not db.query("SELECT 1 FROM user_sessions WHERE key_hash = %s AND full_until IS NOT NULL", (tkh,), one=True))
    # 6. Started while unlocked, but not typed by him: Diagnose, a schedule's Run now, a swipe brief, the follow-through after Accept.
    oc, okh = owner_client(1)
    unlock(okh)
    with account_ctx.use(1):
        camp = db.query("SELECT id FROM campaigns ORDER BY id LIMIT 1", one=True)["id"]
        alert = db.execute("""INSERT INTO alerts (rule, dedupe_key, level, title, kind, entity_id, campaign_id)
                              VALUES ('no_leads', %s, 'bad', 'QA FU-D no leads', 'condition', %s, %s) RETURNING id""",
                           (f"qa-fud-{rank[0]}", camp, camp), returning=True)["id"]
    diag = oc.post("/api/diagnose", headers=W, json={"alert_id": alert, "prompt": "QA FU-D: look into it"}).get_json() or {}
    sched = oc.post("/api/desk/schedules/1/run", headers=W).get_json() or {}
    brief = oc.post("/api/desk/tasks", headers=W, json={"kind": "creative", "prompt": "QA FU-D: brief from swipes", "origin": "brief"}).get_json() or {}
    with account_ctx.use(1):
        base = db.execute("INSERT INTO desk_tasks (kind, prompt, status, created_by) VALUES ('question', 'QA FU-D: base', 'done', 1) RETURNING id", returning=True)["id"]
        made.append(base)
        prop = db.execute("INSERT INTO desk_proposals (task_id, kind, title, status) VALUES (%s, 'other', 'QA FU-D follow', 'approved') RETURNING id",
                          (base,), returning=True)["id"]
    follow = oc.post(f"/api/desk/proposals/{prop}/continue", headers=W).get_json() or {}
    autos = [diag.get("task_id"), sched.get("task_id"), brief.get("id"), follow.get("task_id")]
    made.extend([x for x in autos if x])
    got_autos = []
    for tid in autos:
        if tid:
            front(tid)
            g = take()
            got_autos.append((g.get("id") == tid, g.get("access"), stored(tid)["full_session"], stored(tid)["access_note"]))
            done(tid, g.get("claim_token"))
    full["Diagnose, a schedule, a swipe brief and the follow-through after Accept never run with full access (no note)"] = (
        all(autos) and got_autos == [(True, "sandbox", None, None)] * 4)
    with account_ctx.use(1):
        db.execute("DELETE FROM alerts WHERE id = %s", (alert,))
    # 8. A pass reaches only its own request.
    t8a, t8b = ask(oc, "pass A"), ask(oc, "pass B")
    g8 = take()
    full["the pass of request A can't read request B"] = (
        c.get(f"/api/agent/tasks/{t8b if g8.get('id') == t8a else t8a}", headers={**run(g8.get("claim_token")), "X-Bridge-Version": "3.0"}).status_code == 403)
    with account_ctx.all_accounts():
        db.execute("UPDATE desk_tasks SET status = 'cancelled' WHERE id = ANY(%s)", ([t8a, t8b],))
    # Who may turn it on, and five wrong passwords.
    roles = {}
    for uid in (4, 3, 2):
        rc = app.test_client()
        with rc.session_transaction() as s:
            s["user_id"] = uid
            s["sk"] = auth.new_session_key(uid)
            s["sv"] = db.query("SELECT session_version FROM users WHERE id = %s", (uid,), one=True)["session_version"]
        rc.set_cookie("ebads_account", "2")
        roles[uid] = (rc.post("/api/auth/full-access", headers=W, json={"password": "x"}).status_code,
                      rc.delete("/api/auth/full-access", headers=W).status_code, "full_access" in (rc.get("/api/auth/me").get_json() or {}))
    full["an account admin, a teammate and a client can't turn it on or lock it, and /me doesn't mention it"] = roles == {4: (403, 403, False), 3: (403, 403, False), 2: (403, 403, False)}
    cl2 = app.test_client()
    with cl2.session_transaction() as s:
        s["user_id"] = 2
        s["sk"] = auth.new_session_key(2)
        s["sv"] = db.query("SELECT session_version FROM users WHERE id = 2", one=True)["session_version"]
    full["a client is told its access is read-only"] = "read-only" in (cl2.post("/api/auth/full-access", headers=W, json={"password": "x"}).get_json() or {}).get("error", "")
    so_post = so.post("/api/auth/full-access", headers=W, json={"password": "qa-second-owner-pass"})
    full["a second owner, even with the right password, can't turn it on (/me: not allowed)"] = (
        so_post.status_code == 403 and (so.get("/api/auth/me").get_json() or {}).get("full_access") == {"allowed": False})
    try:  # gone again, so Team and the owners' lists stay as they were
        db.execute("DELETE FROM users WHERE id = %s", (second["id"],))
    except Exception:
        db.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (second["id"],))
    wc, wkh = owner_client()
    tries = [wc.post("/api/auth/full-access", headers=W, json={"password": f"wrong-{i}"}) for i in range(6)]
    full["five wrong passwords block the sixth try with the time to wait"] = (
        [t.status_code for t in tries] == [400, 400, 400, 400, 429, 429] and "isn't right" in tries[0].get_json()["error"]
        and "Too many wrong passwords. Try again after" in tries[5].get_json()["error"] and not db.query(
            "SELECT 1 FROM user_sessions WHERE key_hash = %s AND full_until IS NOT NULL", (wkh,), one=True))
    # Wrong passwords sent at once still count one by one (a row lock on the sign-in): eight at once, at most four 400s.
    from concurrent.futures import ThreadPoolExecutor
    pkey = auth.new_session_key(1)
    pkh = desk_api.key_hash(pkey)

    def burst(i):
        bc = app.test_client()
        with bc.session_transaction() as s:
            s["user_id"] = 1
            s["sk"] = pkey
            s["sv"] = db.query("SELECT session_version FROM users WHERE id = 1", one=True)["session_version"]
        return bc.post("/api/auth/full-access", headers=W, json={"password": f"wrong-at-once-{i}"}).status_code

    with ThreadPoolExecutor(8) as pool:
        codes = sorted(pool.map(burst, range(8)))
    counted = db.query("SELECT full_fails FROM user_sessions WHERE key_hash = %s", (pkh,), one=True)["full_fails"]
    full["eight wrong passwords sent at once count one by one: four refused, the rest blocked, five counted"] = (
        codes == [400] * 4 + [429] * 4 and counted == 5)
    # Upload as draft: the media library, then New ad with it picked; a second tap reuses it.
    d1 = oc.post(f"/api/desk/attachments/{att}/draft", headers=W)
    d2 = oc.post(f"/api/desk/attachments/{att}/draft", headers=W)
    nxt = (d1.get_json() or {}).get("next") or ""
    full["Upload as draft puts the preview in the media library and opens New ad with it; a second tap reuses it"] = (
        d1.status_code == 201 and nxt.startswith("/new-ad.html?media=image:") and "from=%2Fdesk.html%23r%2F" in nxt
        and d2.status_code == 200 and (d2.get_json() or {}).get("next") == nxt)
    out.update(full)
finally:
    with account_ctx.all_accounts():
        if made:
            db.execute("DELETE FROM desk_reports WHERE task_id = ANY(%s)", (made,))
            db.execute("DELETE FROM desk_proposals WHERE task_id = ANY(%s)", (made,))
            db.execute("DELETE FROM desk_tasks WHERE id = ANY(%s)", (made,))
    for k, v in old.items():
        settings_store.set(k, v)
print(json.dumps({"failed": [k for k, v in out.items() if not v], "passed": len([v for v in out.values() if v])}))
