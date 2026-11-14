"""QA helper: what a conversation on the Claude page holds and shows, against the real database: files a person sends
with a message, pages Claude builds, ads and lead forms shown large. Plays the owner's browser and the Mac (a
throwaway key), removes every task and file it made and puts the real key back. Prints JSON: failed check names
and the number passed."""
import io
import json
import struct

import account_ctx
import attachments
import auth
import db
import desk_api
import settings_store
from app import create_app

app = create_app(run_migrations=False)
KEY = "qa-desk-media-key"
W = {"X-Requested-With": "ebads"}
N3, FORM = "120252672230740312", "1132280359202136"
PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 8, 10) + b"\x08\x06\x00\x00\x00" + b"\x00" * 40
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  \x00\x00\x00\x08moov" + b"\x00" * 40
PAGE = b"<!doctype html><html><head><style>h1{color:teal}</style></head><body><h1>Draft</h1><script>alert(1)</script></body></html>"
made, out = [], {}
rank = [-3_000_000]


def mac(version="3.2", token=None):
    return {"Authorization": f"Bearer {KEY}", "X-Bridge-Host": "qa", "X-Bridge-Version": version, **({"X-Desk-Claim": token} if token else {})}


def browser(user_id, account=1):
    c = app.test_client()
    with account_ctx.all_accounts():
        version = db.query("SELECT session_version FROM users WHERE id = %s", (user_id,), one=True)["session_version"]
    with c.session_transaction() as s:
        s["user_id"] = user_id
        s["sk"] = auth.new_session_key(user_id)
        s["sv"] = version
    c.set_cookie("ebads_account", str(account))
    return c


def add(c, data, name):
    return c.post("/api/desk/uploads", headers=W, data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


def ask(c, prompt, files=None, reply_to=None):
    path = f"/api/desk/tasks/{reply_to}/reply" if reply_to else "/api/desk/tasks"
    r = c.post(path, headers=W, json={"kind": "question", "prompt": f"QA media: {prompt}", "files": files})
    if r.status_code == 201:
        made.append(r.get_json()["id"])
        rank[0] -= 1
        with account_ctx.all_accounts():
            db.execute("UPDATE desk_tasks SET queue_rank = %s WHERE id = %s", (rank[0], made[-1]))
    return r


def claim(m, version="3.2"):
    r = m.get("/api/agent/wait?timeout=0", headers=mac(version))
    return r.get_json() if r.status_code == 200 else {}


def page_task(c, tid):
    return next((t for t in (c.get("/api/desk").get_json() or {}).get("tasks", []) if t["id"] == tid), {})


KEPT = ("agent_key_hash", "bridge_version", "bridge_last_seen", "bridge_host")
old = {k: settings_store.get(k) for k in KEPT}
settings_store.set("agent_key_hash", desk_api.key_hash(KEY))
try:
    m = app.test_client()
    owner, admin2 = browser(1), browser(4, account=2)

    # 1. Adding files to a message: typed from the bytes, the person's own, sent once.
    png, mov = add(owner, PNG, "ad I like.png"), add(owner, MOV, "clip.MOV")
    html, gif, none = add(owner, PAGE, "page.png"), add(owner, b"GIF89a" + b"\x00" * 40, "a.png"), owner.post("/api/desk/uploads", headers=W)
    f_png, f_mov = (png.get_json() or {}).get("id"), (mov.get_json() or {}).get("id")
    out["a picture and a phone's .mov are taken, typed from their bytes; a page, a GIF or nothing is refused"] = (
        png.status_code == 201 and (png.get_json() or {}).get("kind") == "image" and (png.get_json() or {}).get("width") == 8
        and mov.status_code == 201 and (mov.get_json() or {}).get("kind") == "video"
        and [html.status_code, gif.status_code, none.status_code] == [400, 400, 400]
        and "JPG, PNG or WebP pictures and MP4 or MOV videos" in (html.get_json() or {}).get("error", ""))
    out["a file being added is in no conversation yet"] = not any(
        f["id"] in (f_png, f_mov) for t in (owner.get("/api/desk").get_json() or {}).get("tasks", []) for f in t.get("files", []) + t.get("attachments", []))
    stolen = ask(admin2, "someone else's file", [f_png])
    odd = [ask(owner, "odd ids", v).status_code for v in ("7", [True], [f_png] * 1 + ["x"], list(range(1, attachments.MAX_FILES + 2)))]
    out["only the person who added a file can send it, and only whole ids pass"] = stolen.status_code == 409 and odd == [400, 400, 400, 400]
    t1 = ask(owner, "cut this clip to nine seconds", [f_png, f_mov])
    task1 = (t1.get_json() or {})
    again = ask(owner, "the same files again", [f_png])
    out["a message is sent with its files, which then belong to it and to no other message"] = (
        t1.status_code == 201 and [f["id"] for f in task1.get("files", [])] == [f_png, f_mov] and task1.get("attachments") == []
        and task1["files"][0] == {"id": f_png, "task_id": task1["id"], "kind": "image", "name": "ad I like.png", "caption": None, "width": 8, "height": 10,
                                  "duration_ms": None, "pruned": False, "drafted": False, "next": None, "source": "user"}
        and again.status_code == 409)
    T1 = task1.get("id")
    spare = (add(owner, PNG, "spare.png").get_json() or {}).get("id")
    gone = owner.delete(f"/api/desk/uploads/{spare}", headers=W).status_code
    kept = owner.delete(f"/api/desk/uploads/{f_png}", headers=W).status_code
    out["a file can be taken back out before sending, never after"] = (
        gone == 200 and kept == 200 and ask(owner, "the removed one", [spare]).status_code == 409
        and db.query("SELECT 1 FROM desk_attachments WHERE id = %s", (f_png,), one=True) is not None)

    # 2. The Mac: an older helper leaves a message with files in line; 3.2 takes it and fetches them with its pass.
    old_take = claim(m, "3.1")
    out["a helper before 3.2 leaves a message with files in line, and the Claude page says to update"] = (
        old_take.get("id") != T1 and desk_api.bridge_status()["can_show"] is False)
    if old_take.get("id"):
        with account_ctx.all_accounts():
            db.execute("UPDATE desk_tasks SET status = 'queued', claim_hash = NULL, claimed_at = NULL WHERE id = %s", (old_take["id"],))
    got = claim(m)
    token = got.get("claim_token")
    out["a 3.2 helper takes it and is told which files came with the message"] = (
        got.get("id") == T1 and [(f["name"], f["kind"]) for f in got.get("files", [])] == [("ad I like.png", "image"), ("clip.MOV", "video")]
        and desk_api.bridge_status()["can_show"] is True)
    listed = m.get(f"/api/agent/tasks/{T1}/files", headers=mac(token=token)).get_json() or {}
    body = m.get(f"/api/agent/tasks/{T1}/files/{f_mov}", headers=mac(token=token))
    no_pass = m.get(f"/api/agent/tasks/{T1}/files/{f_mov}", headers=mac()).status_code
    out["the run fetches its conversation's files byte for byte, only with its pass"] = (
        [(f["id"], f["mime"], f["size_bytes"]) for f in listed.get("files", [])] == [(f_png, "image/png", len(PNG)), (f_mov, "video/quicktime", len(MOV))]
        and body.status_code == 200 and body.get_data() == MOV and body.mimetype == "video/quicktime" and no_pass == 403)

    # 3. Showing what is in the account: an ad as Meta shows it, a lead form.
    show = lambda b: m.post(f"/api/agent/tasks/{T1}/shows", headers=mac(token=token), json=b)  # noqa: E731
    s_ad = show({"type": "ad", "id": N3, "placement": "reels", "caption": "The one that runs"})
    s_form = show({"type": "form", "id": FORM})
    bad = [show(b).status_code for b in ({"type": "ad", "id": "999"}, {"type": "form", "id": "999"}, {"type": "ad", "id": "act_1"},
                                         {"type": "campaign", "id": N3}, {"type": "form", "id": FORM, "placement": "feed"})]
    shown = page_task(owner, T1)
    out["an ad and a lead form of this account are shown large, by name; anything else is refused"] = (
        s_ad.status_code == 201 and s_form.status_code == 201 and bad == [404, 404, 400, 400, 400]
        and shown.get("shows") == [{"type": "ad", "id": N3, "caption": "The one that runs", "placement": "INSTAGRAM_REELS", "name": "N3 - Same work twice"},
                                   {"type": "form", "id": FORM, "caption": None, "placement": None, "name": "EB | Free AI workflow review"}]
        and N3 in ((owner.get("/api/desk").get_json() or {}).get("ads") or {}))

    # 4. A page Claude built: taken only when the Mac says it is one, served with scripts off, never as a plain file.
    up = lambda data, name, fields: m.post(f"/api/agent/tasks/{T1}/attachments", headers=mac(token=token),  # noqa: E731
                                           data={"file": (io.BytesIO(data), name), **fields}, content_type="multipart/form-data")
    page = up(PAGE, "landing.html", {"kind": "page", "caption": "Landing page draft"})
    guessed, fake, clip = up(PAGE, "landing.html", {}), up(PNG, "landing.html", {"kind": "page"}), up(MOV, "clip.mov", {})
    pid = (page.get_json() or {}).get("id")
    out["a page is stored only when declared as one and really HTML; a .mov is never one of Claude's previews"] = (
        page.status_code == 201 and (page.get_json() or {}).get("kind") == "page" and [guessed.status_code, fake.status_code, clip.status_code] == [400, 400, 400])
    plain, framed = owner.get(f"/api/desk/attachments/{pid}"), owner.get(f"/api/desk/attachments/{pid}/page")
    csp = framed.headers.get("Content-Security-Policy", "")
    wrong = owner.get(f"/api/desk/attachments/{f_png}/page").status_code
    out["a page never comes from the plain file address; its own address answers with no origin, no scripts, no requests"] = (
        plain.status_code == 404 and framed.status_code == 200 and framed.mimetype == "text/html" and framed.get_data() == PAGE
        and csp.startswith("sandbox;") and "default-src 'none'" in csp and "frame-ancestors 'self'" in csp and "script" not in csp and wrong == 404)
    on_page = page_task(owner, T1)
    out["the Claude page lists Claude's page under its answer and the person's files in their message"] = (
        [(a["id"], a["kind"], a["source"]) for a in on_page.get("attachments", [])] == [(pid, "page", "claude")]
        and [f["id"] for f in on_page.get("files", [])] == [f_png, f_mov])
    draft = owner.post(f"/api/desk/attachments/{pid}/draft", headers=W)
    out["a page has no Upload as draft"] = draft.status_code == 400

    # 5. Who can look: the account's admins, never another account, a teammate or a client.
    people = [db.execute("""INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, 'x', %s, 1) RETURNING id""",
                         (f"qa-media-{role}@example.com", f"QA media {role}", role), returning=True)["id"] for role in ("member", "client")]
    mate, client = browser(people[0]), browser(people[1])
    looks = [c.get(path).status_code for c in (admin2, mate, client) for path in (f"/api/desk/attachments/{pid}/page", f"/api/desk/attachments/{f_png}")]
    out["another account, a teammate and a client get neither the page nor the file"] = looks == [404, 404, 403, 403, 403, 403]

    # 6. A follow-up in the same conversation still reaches the earlier files; another conversation never does.
    m.post(f"/api/agent/tasks/{T1}/status", headers=mac(token=token), json={"status": "done", "summary": "ok"})
    t2 = ask(owner, "and make it square", reply_to=T1)
    other = ask(owner, "another conversation")
    T2, T3 = (t2.get_json() or {}).get("id"), (other.get_json() or {}).get("id")
    taken = {g.get("id"): g for g in (claim(m), claim(m))}  # whichever order the line gives them in
    got2, got3 = taken.get(T2, {}), taken.get(T3, {})
    earlier = [f for turn in got2.get("thread", []) for f in turn.get("files", [])]
    files2 = m.get(f"/api/agent/tasks/{T2}/files", headers=mac(token=got2.get("claim_token"))).get_json() or {}
    out["a follow-up is told the earlier message's files and can fetch them again"] = (
        got2.get("id") == T2 and earlier == [{"id": f_png, "name": "ad I like.png", "kind": "image"}, {"id": f_mov, "name": "clip.MOV", "kind": "video"}]
        and [f["id"] for f in files2.get("files", [])] == [f_png, f_mov])
    cross = m.get(f"/api/agent/tasks/{T3}/files/{f_mov}", headers=mac(token=got3.get("claim_token"))).status_code
    reach = m.get(f"/api/agent/tasks/{T1}/files/{f_mov}", headers=mac(token=got3.get("claim_token"))).status_code
    out["a run never reaches another conversation's files"] = got3.get("id") == T3 and cross == 404 and reach == 403
    late = m.post(f"/api/agent/tasks/{T1}/shows", headers=mac(token=token), json={"type": "ad", "id": N3}).status_code
    out["a finished request shows nothing more"] = late == 409
finally:
    with account_ctx.all_accounts():
        if made:
            db.execute("DELETE FROM desk_tasks WHERE id = ANY(%s)", (made,))
        db.execute("DELETE FROM desk_attachments WHERE task_id IS NULL AND name IN ('ad I like.png', 'clip.MOV', 'spare.png')")
        db.execute("DELETE FROM users WHERE email LIKE 'qa-media-%@example.com'")
    for k, v in old.items():
        settings_store.set(k, v)
print(json.dumps({"failed": [k for k, v in out.items() if not v], "passed": len([v for v in out.values() if v])}))
