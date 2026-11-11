"""Bulk changes over a selection: preview (live values, every line, totals, a signed plan) then apply
(only that plan, within 5 minutes, each item read again first). Same rules as one at a time: turning
on needs the daily total echoed back, a budget step over +20% needs a knowing yes, the ceiling holds,
archive only when off, no delete. Every write lands in meta_changes with the same bulk_id."""
import time
import uuid

from flask import Blueprint, jsonify, request

import ads_api
import bulk
import config
import db
import meta_client
from auth import current_user, login_required
from util import api_error, log_activity

bp = Blueprint("bulk", __name__, url_prefix="/api/ads/bulk")
ACTIONS = {"status": ("campaign", "adset", "ad"), "budget_set": ("campaign", "adset"), "budget_pct": ("campaign", "adset"),
           "archive": ("ad",)}


def _secret():
    return config.SECRET_KEY + ":bulk"


def _rows(user, level, ids):
    rows = []
    for i in ids:
        row = ads_api.entity(level, i)
        if row and ads_api.can_touch(user, row["campaign_id"]):
            rows.append(row)
    return rows


def _plan(user, data):
    action, level = data.get("action"), data.get("level")
    if action not in ACTIONS or level not in ACTIONS[action]:
        return None, api_error("That change can't be made to a selection", 400)
    if action == "archive" and user["role"] != "admin":
        return None, api_error("Only admins can archive ads", 403)
    ids = [str(i) for i in (data.get("ids") or [])][:bulk.MAX_ITEMS]
    rows = _rows(user, level, ids)
    if not rows:
        return None, api_error("Nothing selected that you can change", 400)
    value = data.get("value")
    try:
        if action == "status":
            value = str(value or "").upper()
            if value not in ("ACTIVE", "PAUSED"):
                return None, api_error("Choose on or off", 400)
            for r in rows:  # what Meta says now, not what the last pull stored
                r["status"] = meta_client.get(r["id"], fields="status").get("status") or r["status"]
            contexts = {r["id"]: ads_api.spend_context(level, r) for r in rows if value == "ACTIVE" and r["status"] == "PAUSED"}
            lines, totals = bulk.status_lines(rows, value, contexts)
        elif action in ("budget_set", "budget_pct"):
            value = int(value) if action == "budget_set" else float(value)
            live = {r["id"]: ads_api.fresh_budget(r["id"]) for r in rows}
            lines, totals = bulk.budget_lines(rows, "set" if action == "budget_set" else "pct", value, live, ads_api.ceiling())
        else:
            for r in rows:
                r["status"] = meta_client.get(r["id"], fields="status").get("status") or r["status"]
            lines, totals = bulk.archive_lines(rows)
    except (TypeError, ValueError):
        return None, api_error("Enter an amount", 400, field="value")
    except meta_client.MetaError as exc:
        return None, api_error(f"Couldn't read the live values from Meta: {exc}", 400)
    plan = {"action": action, "level": level, "value": value, "user": user["id"],
            "lines": [{"id": l["id"], "from": l["from"], "to": l["to"]} for l in lines if not l["skip"]], "totals": totals}
    return {"lines": lines, "totals": totals, "plan": plan}, None


@bp.post("/preview")
@login_required
def preview():
    user = current_user()
    if user["role"] == "client":
        return api_error("Read-only access", 403)
    out, err = _plan(user, request.get_json(silent=True) or {})
    if err:
        return err
    token = bulk.sign(out.pop("plan"), _secret(), time.time()) if out["totals"]["count"] else None
    return jsonify({**out, "plan_token": token})


@bp.post("/apply")
@login_required
def apply():
    user = current_user()
    if user["role"] == "client":
        return api_error("Read-only access", 403)
    data = request.get_json(silent=True) or {}
    plan = bulk.verify(data.get("plan_token"), _secret(), time.time())
    if not plan or plan.get("user") != user["id"]:
        return api_error("This preview has expired. Check the changes again.", 409)
    action, level, totals = plan["action"], plan["level"], plan["totals"]
    if action == "status" and plan["value"] == "ACTIVE" and totals.get("daily_cents"):
        try:
            echoed = int(data.get("confirm_total_cents"))
        except (TypeError, ValueError):
            echoed = None
        if echoed != totals["daily_cents"]:
            return api_error("Confirm the daily total first", 409)
    if action.startswith("budget") and totals.get("big") and not data.get("accept_big"):
        return api_error("Some steps are more than +20%: confirm them knowingly.", 409)
    bulk_id = str(uuid.uuid4())
    token = ads_api.BULK_ID.set(bulk_id)
    results = []
    try:
        for line in plan["lines"]:
            row = ads_api.entity(level, line["id"])
            if not row or not ads_api.can_touch(user, row["campaign_id"]):
                results.append({"id": line["id"], "ok": False, "error": "Not available any more"})
                continue
            try:
                if action == "status" or action == "archive":
                    live = meta_client.get(row["id"], fields="status").get("status")
                else:
                    live = ads_api.fresh_budget(row["id"])
            except meta_client.MetaError as exc:
                results.append({"id": line["id"], "name": row["name"], "ok": False, "error": str(exc)})
                if getattr(exc, "code", None) == "cooldown":
                    break
                continue
            if live != line["from"]:
                results.append({"id": line["id"], "name": row["name"], "ok": False, "error": "Changed on Meta since the preview: skipped"})
                continue
            row = {**row, "status": live} if action in ("status", "archive") else {**row, "daily_budget_cents": live}
            if action == "status":
                error = ads_api.apply_status(user, level, row, line["to"])
            elif action == "archive":
                try:
                    meta_client.post(row["id"], status="ARCHIVED")
                    db.execute("UPDATE ads SET status = 'ARCHIVED', effective_status = 'ARCHIVED' WHERE id = %s", (row["id"],))
                    ads_api.record(user, "ad", row, "archive", live, "ARCHIVED", True)
                    error = None
                except meta_client.MetaError as exc:
                    ads_api.record(user, "ad", row, "archive", live, "ARCHIVED", False, str(exc))
                    error = str(exc)
            else:
                error = ads_api.apply_budget(user, level, row, line["to"])
            results.append({"id": line["id"], "name": row["name"], "ok": not error, "error": error})
    finally:
        ads_api.BULK_ID.reset(token)
    if any(r["ok"] for r in results):
        ads_api.resync_later()
    log_activity("meta.bulk", details={"action": action, "level": level, "bulk_id": bulk_id,
                                       "done": sum(1 for r in results if r["ok"]), "total": len(results)})
    return jsonify({"bulk_id": bulk_id, "results": results, "done": sum(1 for r in results if r["ok"])})
