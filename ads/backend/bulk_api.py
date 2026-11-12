"""Bulk changes over a selection: preview (live values, every line, totals, a signed plan) then apply
(only that plan, within 5 minutes, each item read again first). Same rules as one at a time: turning
on needs the daily total echoed back, a budget step over +20% needs a knowing yes, the ceiling holds,
archive only when off, no delete. Every write lands in meta_changes with the same bulk_id."""
import time
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import ads_api
import bulk
import config
import db
import meta_client
import money_rules
import status_history
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


def live_nodes(ids, fields):
    """{id: node} for every id, read from Meta 50 at a time (?ids=) instead of one call each (audit A3-126).
    An id Meta leaves out fails the read, as a read of that one would: nothing falls back to stored values."""
    out = {}
    for chunk in (ids[i:i + 50] for i in range(0, len(ids), 50)):
        got = meta_client.get("", ids=",".join(chunk), fields=fields)
        missing = [i for i in chunk if not isinstance(got.get(i), dict)]
        if missing:
            raise meta_client.MetaError(f"Meta didn't return {', '.join(missing)}")
        out.update({i: got[i] for i in chunk})
    return out


def _live_statuses(level, rows):
    """Each row's status as Meta has it now, plus a memo for spend_context holding the parents read with it."""
    fields = "status" + (f",{ads_api.PARENT_FIELDS[level]}" if level in ads_api.PARENT_FIELDS else "")
    nodes = live_nodes([r["id"] for r in rows], fields)
    memo = {}
    if level in ads_api.PARENT_FIELDS:
        memo = {(i, ads_api.PARENT_FIELDS[level]): n for i, n in nodes.items()}
    return {i: n.get("status") for i, n in nodes.items()}, memo


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
            live, memo = _live_statuses(level, rows)
            for r in rows:  # what Meta says now, not what the last pull stored
                r["status"] = live[r["id"]] or r["status"]
            contexts = {r["id"]: ads_api.spend_context(level, r, memo) for r in rows if value == "ACTIVE" and r["status"] == "PAUSED"}
            lines, totals = bulk.status_lines(rows, value, contexts)
        elif action in ("budget_set", "budget_pct"):
            value = int(value) if action == "budget_set" else float(value)
            live = {i: ads_api._cents_of(n.get("daily_budget")) for i, n in live_nodes([r["id"] for r in rows], "daily_budget").items()}
            for r in rows:  # a budget changed in Ads Manager since the last read is recorded first, so the 3-day rule sees it (D2)
                ads_api.notice_budget(level, r, live.get(r["id"]))
            now = datetime.now(timezone.utc)
            lasts = status_history.last_budgets([r["id"] for r in rows], now)
            lines, totals = bulk.budget_lines(rows, "set" if action == "budget_set" else "pct", value, live, ads_api.ceiling(),
                                              lasts, now)
        else:
            live = live_nodes([r["id"] for r in rows], "status")
            for r in rows:
                r["status"] = live[r["id"]].get("status") or r["status"]
            lines, totals = bulk.archive_lines(rows)
    except (TypeError, ValueError):
        return None, api_error("Enter an amount", 400, field="value")
    except meta_client.MetaError as exc:
        return None, api_error(f"Couldn't read the live values from Meta: {exc}", 400)
    plan = {"action": action, "level": level, "value": value, "user": user["id"],
            "lines": [{"id": l["id"], "from": l["from"], "to": l["to"], **({"recent": True} if l.get("recent") else {})}
                      for l in lines if not l["skip"]], "totals": totals}
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
    if action == "status" and plan["value"] == "ACTIVE":
        for key, field in (("daily_cents", "confirm_total_cents"), ("lifetime_cents", "confirm_lifetime_cents")):
            try:
                echoed = int(data.get(field))
            except (TypeError, ValueError):
                echoed = None
            if totals.get(key) and echoed != totals[key]:
                return api_error("Confirm the total budget first", 409)
        # The budgets behind the confirmed total, read again now: a raise in Ads Manager since the
        # preview must be seen before anything goes on (audit A3-44, A3-75).
        try:
            rows = [row for row in (ads_api.entity(level, l["id"]) for l in plan["lines"]) if row]
            memo = {}
            if level in ads_api.PARENT_FIELDS and rows:
                memo = {(i, ads_api.PARENT_FIELDS[level]): n for i, n in live_nodes([r["id"] for r in rows], ads_api.PARENT_FIELDS[level]).items()}
            now = bulk.spend_totals([ads_api.spend_context(level, row, memo) for row in rows])
        except meta_client.MetaError as exc:
            return api_error(f"Couldn't read the budgets from Meta, so nothing was turned on: {exc}", 400)
        if (now["daily_cents"], now["lifetime_cents"]) != (totals.get("daily_cents") or 0, totals.get("lifetime_cents") or 0):
            return api_error("The budgets changed on Meta since the preview, so nothing was turned on. Check the changes again.", 409)
    if action.startswith("budget") and totals.get("big") and not data.get("accept_big"):
        return api_error("Some steps are more than +20%: confirm them knowingly.", 409)
    accept_recent = bool(data.get("accept_recent"))
    if action.startswith("budget") and totals.get("recent") and not accept_recent:
        return api_error("Some budgets changed less than 3 days ago: confirm them knowingly.", 409, code="recent_change")
    # The 3-day rule is read again now for every line: one that changed since the preview is refused without
    # the knowing yes, whatever the signed plan said (D2).
    now = datetime.now(timezone.utc)
    lasts = status_history.last_budgets([l["id"] for l in plan["lines"]], now) if action.startswith("budget") else {}
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
                    if live and live != row["daily_budget_cents"]:  # changed outside since the last read: recorded first (D2)
                        row = ads_api.notice_budget(level, row, live)
                        lasts[row["id"]] = ads_api.last_budget(row["id"], now)
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
                error = ads_api.apply_status(user, level, row, line["to"], live=live)
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
                change = money_rules.budget_change(live, line["to"], ads_api.ceiling(), lasts.get(row["id"]), now)
                # The knowing yes covers only the lines the preview flagged: one that became recent since is refused.
                if change["recent"] and not (accept_recent and line.get("recent")):
                    results.append({"id": line["id"], "name": row["name"], "ok": False,
                                    "error": "Changed less than 3 days ago since the preview: skipped. Check the changes again."})
                    continue
                error = ads_api.apply_budget(user, level, row, line["to"],
                                             accepted=money_rules.accepted(change, bool(data.get("accept_big")), accept_recent))
            results.append({"id": line["id"], "name": row["name"], "ok": not error, "error": ads_api.error_words(error)})
        if action == "status":
            ads_api.refresh_entities(level, [r["id"] for r in results if r["ok"]])
    finally:
        ads_api.BULK_ID.reset(token)
    if any(r["ok"] for r in results):
        ads_api.resync_later()
    log_activity("meta.bulk", details={"action": action, "level": level, "bulk_id": bulk_id,
                                       "done": sum(1 for r in results if r["ok"]), "total": len(results)})
    return jsonify({"bulk_id": bulk_id, "results": results, "done": sum(1 for r in results if r["ok"])})
