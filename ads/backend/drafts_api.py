"""AM-B: Ads Manager drafts in the console (owner and account admins).

- `store` keeps what a link pass read (called by am_link_api's push, under the pass's account): rows upserted, a draft a
  complete read no longer lists marked gone, the Inbox's two FYI kinds raised and closed.
- `GET /api/drafts`: the open drafts as cards (what each holds, what's missing, Meta's problems, whether the console can
  finish it, a staged edit's old → new rows) with the source line.
- `GET /api/drafts/<id>/spec`: a builder's prefill (New campaign / New ad set / New ad). Nothing is created from it: the
  builder submits what the person keeps, cleaned and checked like typing, and creates it paused.
- `POST /api/drafts/<id>/check`: a fresh link read asked for (when the last is old) and the builder's check of the prefill.
- `POST /api/drafts/<id>/applied`: records an Apply the person made through the existing budget or on/off route.

No route here calls Meta's Ads MCP server or writes to Meta; the drafts stay in Ads Manager for Eugene to discard there."""
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_info
import am_drafts
import am_link_api
import db
import settings_store
from auth import admin_required, current_user, is_owner
from util import api_error, log_activity

bp = Blueprint("drafts", __name__, url_prefix="/api/drafts")

COLS = ("draft_id, object_type, parent_id, action, meta_status, validation_status, source, time_updated, fields, other_fields, problems, "
        "first_seen_at, last_seen_at, gone_at, run_id, finished_build_id, finished_entity, finished_by, finished_at, applied")
SHOWN = "gone_at IS NULL OR finished_at > now() - interval '7 days'"
FRESH = timedelta(minutes=5)       # older than this, Finish and Apply ask the Mac for a fresh read first
APPLIED_WITHIN = timedelta(minutes=10)
PAGES = {"campaign": "new-campaign", "adset": "new-adset", "ad": "new-ad"}
CHANGE_ACTIONS = {"daily_budget": "budget", "status": "status",
                  # AM-C: applied through the Edit form; its meta_changes value starts with edit_rules.change_text
                  "name": "rename", "bid_strategy": "bid_strategy", "bid_amount": "bid", "spend_cap": "spend_cap", "start_time": "schedule",
                  "end_time": "schedule", "stop_time": "schedule", "optimization_goal": "optimization"}
TABLES = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
ENTITY_PAGES = {"campaign": "/campaign.html?id=", "adset": "/adset.html?id=", "ad": "/ad.html?id="}


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- what the link read

def store(run, rows, complete, fetched):
    """Keep one drafts read for the pass's account (the caller set it). Returns how many drafts were kept."""
    import alerts
    rows, dropped = am_drafts.keep_own(rows, am_link_api.own_entity_ids())
    if dropped:
        db.execute("UPDATE am_link_runs SET error = COALESCE(error, %s) WHERE id = %s",
                   (f"Drafts: {dropped} about ads outside this account left out", run["id"]))
    before = {r["draft_id"]: r for r in db.query(f"SELECT {COLS} FROM am_drafts")}
    for r in rows:
        db.execute("""INSERT INTO am_drafts (draft_id, object_type, parent_id, action, meta_status, validation_status, source, time_updated,
                                             fields, other_fields, problems, last_seen_at, run_id)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                      ON CONFLICT (account_id, draft_id) DO UPDATE SET object_type = EXCLUDED.object_type, parent_id = EXCLUDED.parent_id,
                          action = EXCLUDED.action, meta_status = EXCLUDED.meta_status, validation_status = EXCLUDED.validation_status,
                          source = EXCLUDED.source, time_updated = EXCLUDED.time_updated, fields = EXCLUDED.fields,
                          other_fields = EXCLUDED.other_fields, problems = EXCLUDED.problems, last_seen_at = EXCLUDED.last_seen_at,
                          run_id = EXCLUDED.run_id, gone_at = NULL""",
                   (r["draft_id"], r["object_type"], r["parent_id"], r["action"], r["meta_status"], r["validation_status"], r["source"],
                    r["time_updated"], json.dumps(r["fields"]), r["other_fields"], json.dumps(r["problems"]), fetched, run["id"]))
    if complete:  # only a read that came back whole may say a draft is gone (published or discarded in Ads Manager)
        db.execute("UPDATE am_drafts SET gone_at = %s WHERE gone_at IS NULL AND NOT (draft_id = ANY(%s))",
                   (fetched, [r["draft_id"] for r in rows]))
    after = [{**r, "finished_at": (before.get(r["draft_id"]) or {}).get("finished_at")} for r in rows]
    found, resolve = am_drafts.inbox_events({k: v for k, v in before.items() if v["gone_at"] is None}, after, complete,
                                            alerts.saved_rules(), account_info.today(), account_info.tz())
    if found:
        alerts.raise_found(found)
    # Closed when Meta's problems cleared, or the draft is gone or finished here (the pure rule plus what's stored now).
    finished = {r["draft_id"] for r in after if r["finished_at"]}
    clear = set(resolve) | {rid for rid, problems in am_drafts.root_problems(after).items() if not problems or rid in finished}
    if complete:
        clear |= {k for k in before if k not in {r["draft_id"] for r in rows}}
    if clear:
        db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'draft_problems' AND resolved_at IS NULL AND entity_id = ANY(%s)",
                   (sorted(clear),))
    return len(rows)


# ---------------------------------------------------------------- reading them

def rows_shown():
    """Open drafts and those finished lately, with what a finished one held when Ads Manager dropped it too."""
    return am_drafts.shown_rows(db.query(f"SELECT {COLS}, ({SHOWN}) AS shown FROM am_drafts ORDER BY time_updated DESC NULLS LAST"))


def live_rows(ids):
    """{id: {level, name, daily_budget_cents, status, effective_status}} of this account's campaigns, ad sets and ads named."""
    out = {}
    ids = sorted({i for i in ids if i})
    if not ids:
        return out
    for level, table in TABLES.items():
        budget = "daily_budget_cents" if level != "ad" else "NULL::int AS daily_budget_cents"
        for r in db.query(f"SELECT id, name, status, effective_status, {budget} FROM {table} WHERE id = ANY(%s)", (ids,)):
            out[r["id"]] = {**r, "level": level}
    return out


def blocked(node, live):
    """Why the console can't finish this draft here, or None (am_drafts.finishable plus where it would go)."""
    reason = am_drafts.finishable(node)
    if reason:
        return reason
    if node["object_type"] in ("adset", "ad"):
        parent = live.get(node["parent_live"] or "")
        want = "campaign" if node["object_type"] == "adset" else "adset"
        if not parent or parent["level"] != want or {parent["status"], parent["effective_status"]} & {"DELETED", "ARCHIVED"}:
            where = "campaign" if want == "campaign" else "ad set"
            return f"The {where} it goes in isn't in this account (or was deleted): open it in Ads Manager."
    return None


def finished_view(node):
    if not node.get("finished_at"):
        return None
    level, _, eid = (node.get("finished_entity") or "").partition(":")
    href = (ENTITY_PAGES[level] + eid) if level in ENTITY_PAGES and eid.isdigit() else (
        f"/new-campaign.html?build={node['finished_build_id']}" if node.get("finished_build_id") else None)
    who = db.query("SELECT name FROM users WHERE id = %s", (node["finished_by"],), one=True) if node.get("finished_by") else None
    return {"at": node["finished_at"].isoformat(), "href": href, "by": who and who["name"], "build_id": node.get("finished_build_id")}


def card(node, live, act, currency):
    """What Ads → Campaigns shows of one draft (and everything under it)."""
    edit = node["action"] != "add"
    item = {"id": node["draft_id"], "type": node["object_type"], "kind": "edit" if edit else "new",
            "name": am_drafts.name_of(node, ((live.get(node["draft_id"]) or {}).get("name") or "Untitled draft") if edit else "Untitled draft"),
            "what": am_drafts.what_words(node, currency), "holds": am_drafts.holds_words(node),
            "missing": am_drafts.missing(node), "problems": am_drafts.all_problems(node)[:10],
            "validation_status": node.get("validation_status"),
            "edited_at": (am_drafts.last_edited(node) or node["last_seen_at"]).isoformat(),
            "gone": node.get("gone_at") is not None, "finished": finished_view(node),
            "other_fields": sorted({f for n in [node] + node["adsets"] + node["ads"] + [a for s in node["adsets"] for a in s["ads"]]
                                    for f in n.get("other_fields") or []}),
            "open_url": am_drafts.manager_url(act, node["object_type"], node["draft_id"])}
    if edit:
        target = live.get(node["draft_id"]) or {}
        item["edits"] = am_drafts.edit_rows(node, target)
        item["target"] = {"level": node["object_type"], "id": node["draft_id"], "name": target.get("name")}
        item["finish_blocked"] = None
    else:
        item["finish_blocked"] = blocked(node, live)
        item["finish_url"] = f"/{PAGES[node['object_type']]}.html?draft={node['draft_id']}"
        parent = live.get(node["parent_live"] or "")
        if parent:
            item["target"] = {"level": parent["level"], "id": node["parent_live"], "name": parent["name"]}
    return item


def draft_tree():
    rows = rows_shown()
    roots = am_drafts.tree(rows)
    ids = {r["draft_id"] for r in rows} | {r["parent_id"] for r in rows if r["parent_id"]}
    return roots, live_rows(ids)


def counts():
    """Today's line: open drafts and how many of them the console can finish (owner and account admins)."""
    roots, live = draft_tree()
    open_ = [n for n in roots if n.get("gone_at") is None and not n.get("finished_at")]
    return {"open": len(open_), "finishable": sum(1 for n in open_ if n["action"] == "add" and not blocked(n, live))}


def source():
    return am_link_api.snapshot_source("drafts")


@bp.get("")
@admin_required
def list_drafts():
    roots, live = draft_tree()
    act, currency = am_link_api.ad_account(), account_info.currency()
    cards = [card(n, live, act, currency) for n in roots]
    open_ = [c for c in cards if not c["gone"] and not c["finished"]]
    return jsonify({"drafts": cards, "open": len(open_), "finishable": sum(1 for c in open_ if c["kind"] == "new" and not c["finish_blocked"]),
                    "source": source(), "link": link_state()})


def link_state():
    link = am_link_api.link_row()
    return {"state": link["state"], "live": link["state"] in ("connected", "fallback"), "reading": am_link_api.account_on(),
            "can_check": am_link_api.can_check(is_owner(current_user()), "claude" if link["state"] == "fallback" else "direct",
                                               link["state"] in ("connected", "fallback"), am_link_api.account_on(), am_link_api.ad_account())}


# ---------------------------------------------------------------- one draft

def find(draft_id):
    """(the draft's node in the tree, live rows), or (None, None) when it isn't this account's (row-level security)."""
    if not str(draft_id).isdigit():
        return None, None
    rows = am_drafts.shown_rows(db.query(f"SELECT {COLS}, ({SHOWN} OR draft_id = %s) AS shown FROM am_drafts", (draft_id,)))
    roots = am_drafts.tree(rows)
    node = next((n for n in roots if n["draft_id"] == draft_id), None)
    if node is None:
        nested = any(r["draft_id"] == draft_id for r in rows)
        return ("nested" if nested else None), None
    ids = {r["draft_id"] for r in rows} | {r["parent_id"] for r in rows if r["parent_id"]}
    return node, live_rows(ids)


def known_forms():
    import builds_api
    return set(builds_api.forms_by_id())


def prefill(node, live):
    """(page, spec, notes) for the builder this draft opens."""
    tz, currency = account_info.tz(), account_info.currency()
    kind = node["object_type"]
    if kind == "campaign":
        spec, notes = am_drafts.to_campaign_spec(node, known_forms(), settings_store.get("meta_page_id"), tz, currency=currency)
    elif kind == "adset":
        parent = live[node["parent_live"]]
        spec, notes = am_drafts.to_adset_spec(node, {"id": node["parent_live"], "daily_budget_cents": parent["daily_budget_cents"]}, tz,
                                              currency=currency)
    else:
        spec, notes = am_drafts.to_ad_spec(node, known_forms())
    return PAGES[kind], spec, notes


def refusal(node, live, again=False):
    """(message, status, extra) when this draft can't be finished now, else None."""
    if node == "nested":
        return ("This draft is part of a bigger draft: finish the campaign it belongs to.", 409, {})
    if node is None:
        return ("That draft isn't in this account (or Ads Manager no longer has it).", 404, {})
    if node.get("gone_at"):  # published or discarded in Ads Manager: never make a second copy of it here
        if node.get("finished_at") and not again:
            return ("Already finished in the console: open it.", 409, {"finished": finished_view(node)})
        return ("Ads Manager no longer has this draft (it was published or discarded there).", 409, {})
    why = blocked(node, live) if node["action"] == "add" else am_drafts.finishable(node)
    if why:
        return (why, 409, {"open_url": am_drafts.manager_url(am_link_api.ad_account(), node["object_type"], node["draft_id"])})
    if node.get("finished_at") and not again:
        return ("Already finished in the console: open it.", 409, {"finished": finished_view(node)})
    return None


@bp.get("/<draft_id>/spec")
@admin_required
def spec(draft_id):
    node, live = find(draft_id)
    why = refusal(node, live, again=request.args.get("again") == "1")
    if why:
        return api_error(why[0], why[1], **why[2])
    page, filled, notes = prefill(node, live)
    return jsonify({"page": page, "spec": filled, "notes": notes, "source": source(),
                    "draft": {"id": node["draft_id"], "name": am_drafts.name_of(node), "read_at": node["last_seen_at"].isoformat(),
                              "open_url": am_drafts.manager_url(am_link_api.ad_account(), node["object_type"], node["draft_id"]),
                              "again": bool(node.get("finished_at"))}})


def ask_fresh_read():
    """Ask the Mac for a fresh read when the last drafts read is older than FRESH and Check now may run (never waits)."""
    src = source()
    at = src.get("fetched_at")
    if at and utcnow() - datetime.fromisoformat(at) < FRESH:
        return False
    link = link_state()
    # Only a direct link reads for free; through Claude (fallback) each read is a paid run, started only by Check now.
    if link["state"] != "connected" or not link["can_check"] or am_link_api.check_after():
        return False
    settings_store.set("am_link_checked_at", str(__import__("time").time()))
    settings_store.set("am_link_force", str(current_user()["id"]))
    log_activity("am_link.check", details={"for": "draft"})
    return True


@bp.post("/<draft_id>/check")
@admin_required
def check(draft_id):
    """Before Finish or Apply: a fresh link read asked for when the last is old, and (Finish) the builder's own check."""
    node, live = find(draft_id)
    if node is None:
        return api_error("That draft isn't in this account (or Ads Manager no longer has it).", 404)
    asked = ask_fresh_read()
    problems = []
    if node != "nested" and node["action"] == "add" and not refusal(node, live, again=True):
        page, filled, _ = prefill(node, live)
        if page == "new-campaign":
            import builds_api
            problems = builds_api.check(builds_api.clean(filled))["problems"]
    return jsonify({"asked": asked, "source": source(), "problems": problems})


@bp.post("/<draft_id>/applied")
@admin_required
def applied(draft_id):
    """The page applied one staged setting through the existing budget or on/off route: remember which change did it.
    Only an ok change of that setting on that object, by this person, in the last 10 minutes."""
    node, live = find(draft_id)
    if node in (None, "nested") or node["action"] == "add":
        return api_error("That staged change isn't in this account.", 404)
    data = request.get_json(silent=True) or {}
    field = data.get("field")
    if field not in CHANGE_ACTIONS or field not in (node.get("fields") or {}):
        return api_error("That setting isn't applied from here: change it in Ads Manager.", 400)
    user = current_user()
    change = db.query("""SELECT id, new_value FROM meta_changes WHERE entity_id = %s AND action = %s AND ok AND user_id = %s
                         AND created_at > %s ORDER BY id DESC LIMIT 1""",
                      (draft_id, CHANGE_ACTIONS[field], user["id"], utcnow() - APPLIED_WITHIN), one=True)
    if not change or (data.get("change_id") not in (None, "") and str(data["change_id"]) != str(change["id"])):
        return api_error("No change of that setting from you in the last 10 minutes.", 409)
    if not set_the_draft(field, change["new_value"], node["fields"][field].get("new")):  # another value typed: not the draft's
        return api_error("The change you made isn't the draft's value, so the draft's setting isn't applied.", 409)
    db.execute("UPDATE am_drafts SET applied = applied || %s WHERE draft_id = %s", (json.dumps({field: change["id"]}), draft_id))
    log_activity("draft.applied", subject=draft_id, details={"field": field, "change_id": change["id"]})
    return jsonify({"field": field, "change_id": change["id"]})


def set_the_draft(field, change_value, draft_value):
    """Whether a console change (its meta_changes new_value) set exactly the draft's value."""
    if field in ("daily_budget", "status", "name"):
        return change_value == str(draft_value)
    import edit_rules
    import timeline
    if field in ("start_time", "end_time", "stop_time") and isinstance(draft_value, (int, float)) and not isinstance(draft_value, bool):
        from datetime import datetime, timezone
        draft_value = datetime.fromtimestamp(draft_value, timezone.utc).isoformat()
    want = edit_rules.change_text(field, edit_rules.normal(field, draft_value))
    action = CHANGE_ACTIONS[field]
    got = " ".join(str(change_value or "").split(" ")[:timeline.EDIT_TOKENS.get(action, 1)])
    return got.split(" ")[:len(want.split(" "))] == want.split(" ")


# ---------------------------------------------------------------- the builders

def claim_problem(draft_id, kind, again):
    """Before a builder creates from a draft: (message, status, extra) when it may not, else None."""
    node, live = find(str(draft_id))
    if node not in (None, "nested") and node["object_type"] != kind:
        return ("That draft is for something else.", 400, {})
    return refusal(node, live, again=again)


def mark_finished(draft_id, entity, build_id=None):
    """The builder made something from this draft (paused): it is "Finished in the console", still in Ads Manager."""
    user = current_user()
    db.execute("""UPDATE am_drafts SET finished_entity = %s, finished_build_id = COALESCE(%s, finished_build_id), finished_by = %s,
                  finished_at = now() WHERE draft_id = %s""", (entity, build_id, user["id"], str(draft_id)))
    db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'draft_problems' AND resolved_at IS NULL AND entity_id = %s", (str(draft_id),))
    log_activity("draft.finished", subject=str(draft_id), details={"made": entity, "build_id": build_id})


def draft_ref(draft_id):
    """What a build made from a draft says about it (its success panel)."""
    row = db.query("SELECT draft_id, object_type, fields FROM am_drafts WHERE draft_id = %s", (str(draft_id),), one=True)
    if not row:
        return None
    return {"id": row["draft_id"], "name": am_drafts.name_of(row),
            "open_url": am_drafts.manager_url(am_link_api.ad_account(), row["object_type"], row["draft_id"])}
