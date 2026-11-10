"""Meta webhook endpoint. Answers fast; the lead itself is fetched by the worker."""
import json
import logging

from flask import Blueprint, abort, request

import db
import meta_client
import settings_store
import jobs

log = logging.getLogger(__name__)

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@bp.get("/meta")
def verify():
    """Meta's subscription handshake when the callback URL is saved."""
    expected = settings_store.get("meta_verify_token")
    if (request.args.get("hub.mode") == "subscribe" and expected
            and request.args.get("hub.verify_token") == expected):
        return request.args.get("hub.challenge", ""), 200, {"Content-Type": "text/plain"}
    abort(403)


def account_for_page(page_id):
    """The account whose Facebook Page the lead came from (account 1 when no account claims it)."""
    import account_ctx
    if page_id:
        for r in db.query("SELECT key, value FROM settings WHERE key = 'meta_page_id' OR key LIKE 'meta_page_id@%%'"):
            if r["value"] == page_id:
                return int(r["key"].split("@")[1]) if "@" in r["key"] else account_ctx.DEFAULT
    return account_ctx.DEFAULT


@bp.post("/meta")
def receive():
    raw = request.get_data()
    secret = settings_store.get("meta_app_secret")
    if not meta_client.signature_valid(raw, request.headers.get("X-Hub-Signature-256"), secret):
        log.warning("webhook rejected: bad or missing signature")
        abort(403)
    try:
        payload = json.loads(raw)
    except ValueError:
        abort(400)
    import account_ctx
    count = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            leadgen_id = str((change.get("value") or {}).get("leadgen_id") or "")
            page_id = str((change.get("value") or {}).get("page_id") or entry.get("id") or "")
            with account_ctx.use(account_for_page(page_id)):
                db.execute("INSERT INTO webhook_events (payload, leadgen_id) VALUES (%s, %s)",
                           (json.dumps(change), leadgen_id or None))
            count += 1
    if count:
        jobs.wake()
    return {"ok": True, "received": count}
