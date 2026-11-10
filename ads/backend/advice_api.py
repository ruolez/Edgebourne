"""Meta's own advice on Today (admins): Opportunity Score, recommendations (some applied from
here, behind a confirmation), and the latest benchmarks Claude read on the Mac."""
import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import advice as av
import db
import meta_client
import settings_store
from auth import admin_required, current_user
from desk_api import agent_required
from util import api_error, log_activity

bp = Blueprint("advice", __name__, url_prefix="/api")

STALE_HOURS = 6


def _account():
    return settings_store.get("meta_ad_account_id")


def refresh():
    """Read the score and the recommendations from Meta and keep them (with the previous score)."""
    acc = _account()
    score = meta_client.get(f"act_{acc}", fields="opportunity_score").get("opportunity_score")
    recs = av.flatten(meta_client.get(f"act_{acc}/recommendations"))
    old = json.loads(settings_store.get("meta_advice") or "{}")
    data = {"score": score, "previous_score": old.get("score") if old.get("score") != score else old.get("previous_score"),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "items": recs}
    settings_store.set("meta_advice", json.dumps(data))
    return data


def refresh_if_stale(hours=STALE_HOURS):
    old = json.loads(settings_store.get("meta_advice") or "{}")
    if old.get("fetched_at") and (datetime.now(timezone.utc) - datetime.fromisoformat(old["fetched_at"])).total_seconds() < hours * 3600:
        return old
    return refresh()


def budgets():
    out = {r["id"]: r["c"] for r in db.query("SELECT id, daily_budget_cents AS c FROM campaigns WHERE daily_budget_cents IS NOT NULL")}
    out.update({r["id"]: r["c"] for r in db.query("SELECT id, daily_budget_cents AS c FROM adsets WHERE daily_budget_cents IS NOT NULL")})
    return out


def view(data):
    return {"score": data.get("score"), "previous_score": data.get("previous_score"), "fetched_at": data.get("fetched_at"),
            "items": av.ranked(data.get("items") or [], budgets()),
            "benchmarks": json.loads(settings_store.get("meta_benchmarks") or "null")}


@bp.get("/advice")
@admin_required
def get_advice():
    try:
        data = refresh() if request.args.get("fresh") else refresh_if_stale()
    except meta_client.MetaError as exc:
        data = json.loads(settings_store.get("meta_advice") or "{}")
        if not data:
            return jsonify({"error_note": f"Meta didn't answer: {exc}", **view({})})
    return jsonify(view(data))


@bp.post("/advice/apply")
@admin_required
def apply():
    """Apply one recommendation Meta offers through its API. Checked against a fresh read, so a
    signature Meta has since replaced isn't applied blind."""
    body = request.get_json(silent=True) or {}
    sig = str(body.get("signature") or "")
    try:
        fresh = view(refresh())
    except meta_client.MetaError as exc:
        return api_error(f"Meta didn't answer: {exc}", 400)
    rec = next((r for r in fresh["items"] if r["signature"] == sig), None)
    if not rec:
        return api_error("Meta has changed this suggestion since you looked. Check the list again.", 409)
    if not rec["can_apply"]:
        return api_error("This one is done in Ads Manager, not here.", 409)
    if rec["budget"] and rec["budget"]["big"] and not body.get("accept_big"):
        return api_error(f"That's +{rec['budget']['pct']}%, more than +20%: confirm it knowingly.", 409)
    import ads_api
    user = current_user()
    level = "adset" if rec["object_ids"] and db.query("SELECT 1 FROM adsets WHERE id = %s", (rec["object_ids"][0],), one=True) else "campaign"
    row = {"id": rec["object_ids"][0] if rec["object_ids"] else _account(), "name": rec["label"], "campaign_id": None}
    new_value = rec["label"] + (f" (+{rec['budget']['add'] / 100:.2f}/day)" if rec["budget"] and rec["budget"]["add"] else "")
    try:
        meta_client.post(f"act_{_account()}/recommendations", data={"recommendation_signature": sig, "extra_data": json.dumps(av.extra_data(rec))})
    except meta_client.MetaError as exc:
        ads_api.record(user, level, row, "recommendation", None, new_value, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    ads_api.record(user, level, row, "recommendation", rec["budget"]["from"] if rec["budget"] else None, new_value, True)
    try:
        import insights
        insights.sync_structure()
    except meta_client.MetaError:
        pass
    return jsonify(view(refresh()))


@bp.post("/agent/benchmarks")
@agent_required
def agent_benchmarks():
    """The Monday summary's benchmarks from the Mac (industry, peers, auction ranking): MCP-only."""
    data = request.get_json(silent=True) or {}
    items = [{"label": str(i.get("label") or "")[:120], "ours": str(i.get("ours") or "")[:60], "peers": str(i.get("peers") or "")[:60],
              "note": str(i.get("note") or "")[:300]} for i in (data.get("items") or [])[:12] if isinstance(i, dict) and i.get("label")]
    if not items:
        return api_error("Send {\"items\": [{\"label\", \"ours\", \"peers\", \"note\"}]}", 400)
    saved = {"as_of": str(data.get("as_of") or datetime.now(timezone.utc).date().isoformat())[:10], "items": items,
             "summary": str(data.get("summary") or "")[:600] or None}
    settings_store.set("meta_benchmarks", json.dumps(saved))
    log_activity("benchmarks.saved", details={"items": len(items)})
    return jsonify({"saved": len(items)})
