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


def fix_runs():
    """The latest "Fix with Claude" run per piece of advice, with its proposals still waiting."""
    rows = db.query("""SELECT t.id, t.status, t.options->>'advice_key' AS k,
                              (SELECT COUNT(*) FROM desk_proposals p WHERE p.task_id = t.id AND p.status = 'pending') AS waiting
                       FROM desk_tasks t WHERE t.kind = 'advice' ORDER BY t.id DESC LIMIT 100""")
    out = {}
    for r in rows:
        out.setdefault(r["k"], {"id": r["id"], "status": r["status"], "waiting": r["waiting"]})
    return out


def view(data):
    items = av.ranked(data.get("items") or [], budgets())
    runs = fix_runs()
    for r in items:
        r["fix_run"] = runs.get(r["key"])
    return {"score": data.get("score"), "previous_score": data.get("previous_score"), "fetched_at": data.get("fetched_at"),
            "items": items, "benchmarks": json.loads(settings_store.get("meta_benchmarks") or "null")}


def ads_under(object_ids):
    """The running ads an advice names (it may name ads, ad sets or campaigns)."""
    return db.query("""SELECT id, name, adset_id, campaign_id, effective_status FROM ads
                       WHERE (id = ANY(%s) OR adset_id = ANY(%s) OR campaign_id = ANY(%s))
                         AND effective_status IN ('ACTIVE', 'PENDING_REVIEW', 'IN_PROCESS', 'WITH_ISSUES')
                       ORDER BY name""", (object_ids, object_ids, object_ids))


@bp.post("/advice/fix")
@admin_required
def fix():
    """Hand one piece of advice to Claude on the Mac (a Desk run, kind 'advice'). Claude does the
    work and sends proposals back; nothing changes on Meta until one is approved."""
    key = str((request.get_json(silent=True) or {}).get("key") or "")
    data = json.loads(settings_store.get("meta_advice") or "{}")
    rec = next((r for r in view(data)["items"] if r["key"] == key), None) if data else None
    if not rec:
        return api_error("Meta has changed this suggestion since you looked. Check the list again.", 409)
    if not rec["can_fix"]:
        return api_error("This one is applied here with Apply.", 409)
    run = rec["fix_run"]
    if run and run["status"] in ("queued", "claimed", "running"):
        return jsonify({"task_id": run["id"], "already": True})
    ads = ads_under(rec["object_ids"])
    campaign = next((a["campaign_id"] for a in ads), None)
    if not campaign and rec["object_ids"]:
        found = db.query("SELECT campaign_id FROM adsets WHERE id = ANY(%s) UNION SELECT id FROM campaigns WHERE id = ANY(%s) LIMIT 1",
                         (rec["object_ids"], rec["object_ids"]), one=True)
        campaign = found and found["campaign_id"]
    advice = {k: rec[k] for k in ("type", "label", "body", "lift", "points", "object_ids", "url", "fix")}
    options = {"advice_key": key, "advice": advice,
               "ads": [{"id": a["id"], "name": a["name"], "adset_id": a["adset_id"]} for a in ads]}
    task = db.execute("INSERT INTO desk_tasks (kind, prompt, campaign_id, created_by, options) VALUES ('advice', %s, %s, %s, %s) RETURNING id",
                      (av.fix_prompt(rec), campaign, current_user()["id"], json.dumps(options)), returning=True)
    log_activity("desk.task_created", subject=str(task["id"]), details={"kind": "advice", "advice": rec["type"]})
    return jsonify({"task_id": task["id"]}), 201


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
    step = rec["budget"]
    if rec["type"] == "SCALE_GOOD_CAMPAIGN":
        # Raising a budget: only with an amount we can show and Eugene confirmed (audit A3).
        if not step or step["to"] is None:
            return api_error("Meta didn't say clearly how much it would add, so this isn't applied here. "
                             "Change the budget yourself on the Ads page, or apply it in Ads Manager.", 409)
        if body.get("confirm_to") is None or int(body["confirm_to"]) != step["to"]:
            return api_error("Meta's amount changed since you looked. Check the suggestion again.", 409)
        import money_rules
        change = money_rules.budget_change(step["from"], step["to"], money_rules.ceiling(settings_store.get("max_daily_budget_cents")))
        problem = money_rules.change_problem(change, bool(body.get("accept_big")))
        if problem:
            return api_error(problem, 409)
    import ads_api
    user = current_user()
    level = ("account" if not rec["object_ids"] else
             "adset" if db.query("SELECT 1 FROM adsets WHERE id = %s", (rec["object_ids"][0],), one=True) else "campaign")
    row = {"id": rec["object_ids"][0] if rec["object_ids"] else _account(), "name": rec["label"], "campaign_id": None}
    new_value = rec["label"] + (f" (+{rec['budget']['add'] / 100:.2f}/day)" if rec["budget"] and rec["budget"]["add"] else "")
    try:
        meta_client.post(f"act_{_account()}/recommendations", data={"recommendation_signature": sig, "extra_data": json.dumps(av.extra_data(rec))})
    except meta_client.MetaError as exc:
        ads_api.record(user, level, row, "recommendation", None, new_value, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    ads_api.record(user, level, row, "recommendation", rec["budget"]["from"] if rec["budget"] else None, new_value, True)
    if step and step["to"] and rec["object_ids"]:
        try:  # read back what Meta set: if it isn't what was shown, say so in the change log
            now = ads_api.fresh_budget(rec["object_ids"][0])
            if now and now != step["to"]:
                ads_api.record(user, level, row, "recommendation_check", step["to"], now, False,
                               f"Meta set {now / 100:,.2f} a day, not the {step['to'] / 100:,.2f} shown")
        except meta_client.MetaError:
            pass
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
