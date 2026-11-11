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
    import hmac
    if (request.args.get("hub.mode") == "subscribe" and expected
            and hmac.compare_digest(str(request.args.get("hub.verify_token") or ""), expected)):
        return request.args.get("hub.challenge", ""), 200, {"Content-Type": "text/plain"}
    abort(403)


def account_for_page(page_id):
    """The account whose Facebook Page the lead came from. A Page no account names goes to account 1
    (Meta sometimes sends the Page's profile id rather than the id in Settings), logged so a client's
    Page that was never connected shows up instead of vanishing. Account 1's built-in Page counts, the
    lowest account number wins and a closed account never does (its worker doesn't run). None when only
    closed accounts name it: account 1's Page token can't read that Page's leads."""
    import account_ctx
    if page_id:
        holders = [(acct, closed) for acct, closed, value in settings_store.meta_holders("meta_page_id") if value == page_id]
        open_ones = [acct for acct, closed in holders if not closed]
        if open_ones:
            return open_ones[0]
        if holders:
            return None
        log.warning("webhook for Page %s, which no account names: filed under account 1", page_id)
    return account_ctx.DEFAULT


LEVEL_NAMES = {"AD": "ad", "ADGROUP": "ad", "AD_SET": "adset", "ADSET": "adset", "CAMPAIGN": "campaign",
               "CREATIVE": "creative", "AD_CREATIVE": "creative"}
STATUS_FIELDS = ("with_issues_ad_objects", "in_process_ad_objects", "field_changed", "effective_status",
                 "creative_fatigue", "ad_recommendations")


def parse_ad_account(payload):
    """Rows for each change in an ad_account webhook: which account, which object, at which level."""
    if payload.get("object") != "ad_account":
        return []
    out = []
    for entry in payload.get("entry", []):
        account = str(entry.get("id") or "").removeprefix("act_")
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            object_id = value.get("id") or value.get("object_id") or value.get("ad_id")
            kind = str(value.get("level") or value.get("object_type") or "").upper()
            detail = {k: value[k] for k in ("error_code", "error_summary", "error_message", "changed_fields", "status_name")
                      if k in value}
            out.append({"account": account, "field": change.get("field"), "object_id": str(object_id) if object_id else None,
                        "level": LEVEL_NAMES.get(kind) if object_id else None, "detail": detail})
    return out


def refetch_plan(rows):
    """Object ids to read again from Meta, grouped by level, each once."""
    plan = {}
    for r in rows:
        if r.get("object_id") and r.get("level"):
            ids = plan.setdefault(r["level"], [])
            if r["object_id"] not in ids:
                ids.append(r["object_id"])
    return plan


def account_for_ad_account(ad_account_id):
    """The console account that owns this Meta ad account, or None (never guessed: an unknown ad
    account's status changes are dropped and logged)."""
    import account_ctx
    with account_ctx.all_accounts():
        accounts = [r["id"] for r in db.query("SELECT id FROM accounts WHERE archived_at IS NULL ORDER BY id")]
    for acct in accounts:
        with account_ctx.use(acct):
            if str(settings_store.get("meta_ad_account_id") or "").removeprefix("act_") == ad_account_id:
                return acct
    return None


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
    return queue_events(payload)


def queue_events(payload):
    """Files each change of a signed webhook under the account it belongs to, for the worker."""
    import account_ctx
    count = 0
    for row in parse_ad_account(payload):
        acct = account_for_ad_account(row["account"])
        if acct is None:
            log.warning("status webhook for ad account %s, which no account names: dropped", row["account"])
            continue
        with account_ctx.use(acct):
            db.execute("INSERT INTO webhook_events (payload, kind, field, object_id) VALUES (%s, 'ad_account', %s, %s)",
                       (json.dumps({**row, "raw": payload}), row["field"], row["object_id"]))
        count += 1
    for entry in (payload.get("entry", []) if payload.get("object") != "ad_account" else []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            leadgen_id = str((change.get("value") or {}).get("leadgen_id") or "")
            page_id = str((change.get("value") or {}).get("page_id") or entry.get("id") or "")
            acct = account_for_page(page_id)
            if acct is None:
                log.warning("lead webhook for Page %s, which only a closed account names: dropped", page_id)
                continue
            with account_ctx.use(acct):
                db.execute("INSERT INTO webhook_events (payload, leadgen_id) VALUES (%s, %s)",
                           (json.dumps(change), leadgen_id or None))
            count += 1
    if count:
        jobs.wake()
    return {"ok": True, "received": count}
