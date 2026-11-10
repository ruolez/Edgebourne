"""QA helper: post the Monday summary's benchmarks as the Mac would, with a throwaway key."""
import json

import desk_api
import settings_store
from app import create_app

app = create_app(run_migrations=False)
old = settings_store.get("agent_key_hash")
settings_store.set("agent_key_hash", desk_api.key_hash("qa-agent-key"))
try:
    c = app.test_client()
    r = c.post("/api/agent/benchmarks", headers={"Authorization": "Bearer qa-agent-key"}, json={
        "as_of": "2026-11-09", "summary": "Cheaper leads than similar advertisers; click rate about average.",
        "items": [{"label": "Cost per lead", "ours": "$4.79", "peers": "$18–$42", "note": "Professional services, US"},
                  {"label": "Click rate", "ours": "1.08%", "peers": "0.9–1.6%", "note": ""}, {"note": "no label, dropped"}]})
    print(json.dumps({"status": r.status_code, "body": r.get_json()}))
finally:
    settings_store.set("agent_key_hash", old)
