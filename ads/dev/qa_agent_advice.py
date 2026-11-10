"""QA helper: play the Mac for a "Fix with Claude" run on Meta's Reels advice. Reads the task the
way the bridge does, picks a 9:16 video for two of its ads (another library video stands in for
the render) and posts the update proposals the skill would. Prints JSON."""
import json
import sys

import db
import desk_api
import meta_client
import settings_store
from app import create_app

app = create_app(run_migrations=False)
task_id = int(sys.argv[1])
H = {"Authorization": "Bearer qa-agent-key"}
old = settings_store.get("agent_key_hash")
settings_store.set("agent_key_hash", desk_api.key_hash("qa-agent-key"))
try:
    c = app.test_client()
    db.execute("UPDATE desk_tasks SET status = 'claimed' WHERE id = %s AND status = 'queued'", (task_id,))
    task = c.get(f"/api/agent/tasks/{task_id}", headers=H).get_json()
    with app.app_context():
        library = [v["id"] for v in meta_client.paged(f"act_{settings_store.get('meta_ad_account_id')}/advideos", fields="id", limit=200)]
        picks = []
        for ad in sorted(task["options"]["ads"], key=lambda a: a["name"])[2:4]:  # N3 and N4
            cid = db.query("SELECT creative_id FROM ads WHERE id = %s", (ad["id"],), one=True)["creative_id"]
            own = meta_client.get(cid, fields="object_story_spec")["object_story_spec"]["video_data"]["video_id"]
            picks.append((ad, next(v for v in library if v != own)))
    proposals = [{"kind": "creative", "title": f"9:16 for Reels: {ad['name']}",
                  "rationale": "Meta: 8% lower cost per result with a 9:16 video in Reels.",
                  "expected": "Feeds keep the 4:5 video; Reels and Stories show the 9:16 one. Meta reviews the ad again.",
                  "payload": {"template_ad_id": ad["id"], "update_ad": True, "vertical": {"video_id": vid},
                              "name": f"{ad['name']} · 9:16 Reels"}} for ad, vid in picks]
    r = c.post(f"/api/agent/tasks/{task_id}/proposals", headers=H, json={"proposals": proposals})
    done = c.post(f"/api/agent/tasks/{task_id}/status", headers=H,
                  json={"status": "done", "summary": "9:16 versions of 2 ads ready to approve."})
    print(json.dumps({"task": {k: task.get(k) for k in ("kind", "prompt", "campaign_id")}, "ads": [a["name"] for a in task["options"]["ads"]],
                      "advice": task["options"]["advice"]["type"], "added": r.get_json(), "done": done.status_code,
                      "picks": [[a["id"], v] for a, v in picks]}))
finally:
    settings_store.set("agent_key_hash", old)
