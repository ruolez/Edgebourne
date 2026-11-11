"""QA helper: play the Mac for a polish run. Posts copy variants the way the skill does (no update
flag, so the server has to make them updates of the polished ad), plus one update of an ad that
already shows different media per placement. Prints JSON."""
import json
import sys

import db
import desk_api
import settings_store
from app import create_app

app = create_app(run_migrations=False)
task_id, placed_ad = int(sys.argv[1]), sys.argv[2]
H = {"Authorization": "Bearer qa-agent-key"}
old = settings_store.get("agent_key_hash")
settings_store.set("agent_key_hash", desk_api.key_hash("qa-agent-key"))
try:
    c = app.test_client()
    db.execute("UPDATE desk_tasks SET status = 'claimed' WHERE id = %s AND status = 'queued'", (task_id,))
    task = c.get(f"/api/agent/tasks/{task_id}", headers=H).get_json()
    ad = task["options"]["ad_id"]

    def words(letter, template=ad, **extra):
        return {"kind": "creative", "title": f"New headline {letter}", "rationale": "Shorter hook.",
                "payload": {"template_ad_id": template, "media": {"kind": "same"}, "name": f"Variant {letter}",
                            "title": f"Headline {letter}", "body": f"Primary text {letter}.", **extra}}

    proposals = [words("A"), words("B"), words("C"), words("D", placed_ad, update_ad=True)]
    r = c.post(f"/api/agent/tasks/{task_id}/proposals", headers=H, json={"proposals": proposals})
    done = c.post(f"/api/agent/tasks/{task_id}/status", headers=H, json={"status": "done", "summary": "Three new headlines."})
    rows = db.query("SELECT id, title, payload FROM desk_proposals WHERE task_id = %s ORDER BY id", (task_id,))
    print(json.dumps({"ad": ad, "added": r.get_json(), "done": done.status_code,
                      "proposals": {p["title"][-1]: {"id": p["id"], "update": p["payload"].get("update_ad")} for p in rows}}))
finally:
    settings_store.set("agent_key_hash", old)
