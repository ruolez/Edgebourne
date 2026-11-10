"""Dev: post a signed Meta ad_account webhook to the local backend, as Meta would.
docker cp ads/dev/status_webhook.py edgebourne-ads-backend:/tmp/ && docker exec -w /app edgebourne-ads-backend python /tmp/status_webhook.py <object id> <field> [AD|AD_SET|CAMPAIGN]"""
import sys; sys.path.insert(0, "/app")
import hashlib, hmac, json, sys, requests
import settings_store
ad, field = sys.argv[1], sys.argv[2]
body = json.dumps({"object": "ad_account", "entry": [{"id": "act_" + settings_store.get("meta_ad_account_id"), "time": 1762790000,
        "changes": [{"field": field, "value": {"id": ad, "level": (sys.argv[3] if len(sys.argv) > 3 else "AD"), "error_code": 1487, "error_summary": "Ad rejected (QA)"}}]}]}).encode()
sig = "sha256=" + hmac.new(settings_store.get("meta_app_secret").encode(), body, hashlib.sha256).hexdigest()
r = requests.post("http://localhost:5000/webhooks/meta", data=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
print(r.status_code, r.text.strip())
