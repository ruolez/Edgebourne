"""Did it work? (D3): one change's before/after results for the dialog. Read-only: no Meta call, and Put it back
only describes what the existing confirmation dialog would be filled in with."""
from datetime import timedelta

from flask import Blueprint, jsonify

import account_info
import ads_api
import change_checks as cc
import change_checks_db as ccdb
import db
import targets
import timeline
import words
from auth import current_user, login_required
from util import api_error

bp = Blueprint("change_checks", __name__, url_prefix="/api")


@bp.get("/changes/<int:change_id>/check")
@login_required
def change_check(change_id):
    user = current_user()
    change = ccdb.load_change(change_id)
    if not change or change["level"] not in cc.LEVELS or not ads_api.can_touch(user, change.get("campaign_id")):
        return api_error("Not found", 404)
    rows = ccdb.stored([change_id]).get(change_id) or []
    if not rows or not all(r["final"] for r in rows):
        ccdb.compute(change_id)
        rows = ccdb.stored([change_id]).get(change_id) or []
    if not rows:
        return api_error("This change isn't checked", 404)
    client = user["role"] == "client"
    first = rows[0]
    scope_row = ccdb.entity_now(first["scope_level"], first["scope_id"]) or {}
    tz = account_info.tz()
    day = words.day(change["created_at"].astimezone(tz))
    title = timeline.change_title(change, account_info.money)
    review = (first["before_end"] and first["after_start"]) and (
        change["created_at"].astimezone(tz).date(), first["after_start"] - timedelta(days=1))
    headline = cc.headline(rows)
    judged = next((r for r in sorted(rows, key=lambda r: -r["horizon"]) if r["metric"]), None)
    metric, target = (judged["metric"], judged["target_cents"]) if judged else ("cpl_cents", targets.lead())
    undone = ccdb.undone_by([change_id]).get(change_id)
    out = {"change": {"id": change["id"], "at": change["created_at"].isoformat(), "level": change["level"],
                      "entity_id": change["entity_id"], "entity_name": change.get("entity_name"), "action": change["action"],
                      "old": change.get("old_value"), "new": change.get("new_value"), "by": change.get("user_name"), "day": day},
           "title": title, "rows": [ccdb.row_public(r) for r in rows], "headline": ccdb.row_public(headline),
           "scope": {"level": first["scope_level"], "id": first["scope_id"], "name": scope_row.get("name")},
           "compared": cc.compared_words(first["mode"], first["scope_level"], scope_row.get("name") or "", change["level"],
                                         review if first["mode"] == "version" else None),
           "rule": cc.rule_words(metric, target, lambda c: account_info.money(c, whole=True)), "needs_target": not target,
           "undone_by": undone}
    if client:
        # Clients get nothing about Claude: not even whether an expectation was met on some horizon.
        for r in out["rows"] + [out["headline"]]:
            r.pop("expect_met", None)
        return jsonify(out)
    if change.get("proposal_id"):
        p = db.query("SELECT id, task_id, title, expect, expected FROM desk_proposals WHERE id = %s",
                    (change["proposal_id"],), one=True)
        if p:
            expect = cc.clean_expect(p["expect"]) if isinstance(p["expect"], dict) else None
            row = next((r for r in rows if expect and r["horizon"] == expect["days"]), None)
            money = lambda c: account_info.money(c, whole=not c % 100)  # noqa: E731
            out["proposal"] = {"id": p["id"], "task_id": p["task_id"], "title": p["title"]}
            out["expect"] = expect
            out["expected_text"] = p["expected"]
            if expect:
                out["expect_words"] = cc.expect_words(expect, money)
                out["got_words"] = cc.got_words(expect, {"days": row["days"], "after": row["after_totals"] or {},
                                                         "after_ready": row["after_ready"] or {}}, money) if row and row["state"] != "waiting" else None
                out["expect_met"] = row["expect_met"] if row else None
                out["expect_horizon"] = expect["days"]
    out["undo"] = {"plan": None, "reason": None} if undone else ccdb.plan_for(change)
    return jsonify(out)
