"""QA helper: drive the Mac's swipe endpoints with a throwaway key, then put the real key back."""
import json

import desk_api
import settings_store
from app import create_app

app = create_app(run_migrations=False)
old = settings_store.get("agent_key_hash")
settings_store.set("agent_key_hash", desk_api.key_hash("qa-agent-key"))
try:
    c = app.test_client()
    h = {"Authorization": "Bearer qa-agent-key"}
    watched = c.get("/api/agent/watched", headers=h).get_json()
    first = c.post("/api/agent/swipes", headers=h, json={"swipes": [
        {"library_id": "4440001112223", "page_name": "Acme Business Software", "body": "One app for quotes and invoices.",
         "started_on": "2026-08-01", "tags": {"hook": "Outcome promise"}},
        {"library_id": "4440001112224", "page_name": "Acme Business Software", "body": "Stop retyping orders."},
        {"page_name": "No text or link"}]}).get_json()
    again = c.post("/api/agent/swipes", headers=h, json={"swipes": [
        {"library_id": "4440001112223", "page_name": "Acme Business Software", "stopped_on": "2026-11-05"}]}).get_json()
    refused = c.get("/api/agent/watched", headers={"Authorization": "Bearer wrong"}).status_code
    print(json.dumps({"watched": [p["name"] for p in watched["pages"]], "first": first, "again": again, "refused": refused}))
finally:
    settings_store.set("agent_key_hash", old)
