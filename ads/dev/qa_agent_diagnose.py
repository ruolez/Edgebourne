"""QA helper: play the Mac for a "Diagnose with Claude" run. Checks the tools the bridge would give a
`diagnose` run (read-only: Meta's read tools, the workspace and `desk`), reads the task the way the bridge
does, then posts a report and one `status` suggestion (turn the alert's ad off), as the skill would.
Usage: python qa_agent_diagnose.py <task id> <folder with bridge.py and desk>. Prints JSON."""
import importlib.machinery
import json
import os
import sys

import db
import desk_api
import settings_store
from app import create_app

task_id, bridge_dir = int(sys.argv[1]), sys.argv[2]
bridge = importlib.machinery.SourceFileLoader("bridge", os.path.join(bridge_dir, "bridge.py")).load_module()
SKILL, WORKDIR = "/Users/qa/.claude/skills/ads-desk", "/Users/qa/Desktop/Dev/meta-ads"

app = create_app(run_migrations=False)
H = {"Authorization": "Bearer qa-agent-key"}
old = settings_store.get("agent_key_hash")
settings_store.set("agent_key_hash", desk_api.key_hash("qa-agent-key"))
try:
    c = app.test_client()
    db.execute("UPDATE desk_tasks SET status = 'claimed' WHERE id = %s AND status = 'queued'", (task_id,))
    task = c.get(f"/api/agent/tasks/{task_id}", headers=H).get_json()
    tools = bridge.allowed_tools(SKILL, WORKDIR, task["kind"], web=True)
    writes = [t for t in tools if t.startswith(("WebFetch", "WebSearch")) or (t.startswith("Bash(") and "/desk:" not in t)
              or (t.startswith("mcp__") and not any(t.endswith("__" + r) for r in bridge.READ_TOOLS))
              or (t.startswith("Edit(") and "reports/desk" not in t)]
    alert = task["options"]["alert"]
    ad_id = alert.get("ad_id") or (task["options"].get("ad_id"))
    if not ad_id:
        row = db.query("SELECT id, name FROM ads WHERE campaign_id = %s AND effective_status = 'ACTIVE' ORDER BY name LIMIT 1",
                       (alert.get("campaign_id"),), one=True)
        ad_id = row and row["id"]
    ad = db.query("SELECT id, name, status FROM ads WHERE id = %s", (ad_id,), one=True)
    rep = c.post(f"/api/agent/tasks/{task_id}/report", headers=H, json={
        "title": "What's wrong", "body": "**What's wrong** QA: the alert still holds.\n\n**Why** QA numbers.\n\n**What to do** Turn the ad off."})
    added = c.post(f"/api/agent/tasks/{task_id}/proposals", headers=H, json={"proposals": [{
        "kind": "status", "title": f"Turn off {ad['name']}", "entity_type": "ad", "entity_id": ad["id"], "entity_name": ad["name"],
        "field": "status", "current_value": "ACTIVE", "proposed_value": "PAUSED", "rationale": "QA diagnosis.",
        "expected": "It stops spending.", "rollback": "ACTIVE"}]})
    done = c.post(f"/api/agent/tasks/{task_id}/status", headers=H, json={"status": "done", "summary": "QA: one suggestion waiting."})
    print(json.dumps({"kind": task["kind"], "read_only_kind": task["kind"] in bridge.READ_ONLY_KINDS, "writes": writes,
                      "rule": alert.get("rule"), "playbook": task["options"].get("playbook"), "alert_key": task["options"].get("alert_key"),
                      "ad": ad["id"], "report": rep.status_code, "added": added.get_json(), "done": done.status_code}))
finally:
    settings_store.set("agent_key_hash", old)
