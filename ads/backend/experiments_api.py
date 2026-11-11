"""Experiments page API (admins): list, create, edit and close tests; the numbers come
from ad_daily and the leads inbox for the test's own dates."""
import json
from datetime import date, datetime

from flask import Blueprint, jsonify, request

import account_info
import db
import experiments as ex
import meta_client
import meta_tests as mt
import settings_store
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("experiments", __name__, url_prefix="/api/experiments")

COLS = "id, name, hypothesis, metric, arms, start_day, end_day, target_cents, status, winner, verdict, notes, proposal_id, created_at, closed_at, meta_study"


def _day(raw, field, required=False):
    if raw in (None, ""):
        return (None, None) if not required else (None, ("Pick the day it starts", field))
    try:
        return date.fromisoformat(str(raw)[:10]), None
    except ValueError:
        return None, ("Use a date like 2026-11-10", field)


def known_entities():
    ads = {r["id"] for r in db.query("SELECT id FROM ads")}
    sets = {r["id"] for r in db.query("SELECT id FROM adsets")}
    return ads, sets


def clean(data, partial=False):
    """Validate a create or edit. Returns (fields, None) or (None, (message, field))."""
    out = {}
    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()[:200]
        if not name:
            return None, ("Give the test a name", "name")
        out["name"] = name
    for key, n in (("hypothesis", 2000), ("notes", 4000), ("verdict", 2000)):
        if key in data:
            out[key] = str(data.get(key) or "").strip()[:n] or None
    if not partial or "metric" in data:
        if data.get("metric") not in ex.METRICS:
            return None, ("Pick the number that decides it", "metric")
        out["metric"] = data["metric"]
    if not partial or "start_day" in data:
        d, err = _day(data.get("start_day"), "start_day", required=True)
        if err:
            return None, err
        out["start_day"] = d
    if "end_day" in data:
        d, err = _day(data.get("end_day"), "end_day")
        if err:
            return None, err
        out["end_day"] = d
    if out.get("start_day") and out.get("end_day") and out["end_day"] < out["start_day"]:
        return None, ("The end comes before the start", "end_day")
    if "target_cents" in data:
        raw = data.get("target_cents")
        if raw in (None, ""):
            out["target_cents"] = None
        else:
            try:
                out["target_cents"] = int(raw)
            except (TypeError, ValueError):
                return None, ("Type the target in dollars, like 60", "target")
            if out["target_cents"] <= 0:
                return None, ("Type the target in dollars, like 60", "target")
    if not partial or "arms" in data:
        arms = data.get("arms") if isinstance(data.get("arms"), list) else []
        ads, sets = known_entities()
        clean_arms = []
        for i, a in enumerate(arms[:4]):
            if not isinstance(a, dict):
                continue
            ad_ids = [str(x) for x in (a.get("ad_ids") or []) if str(x) in ads][:20]
            set_ids = [str(x) for x in (a.get("adset_ids") or []) if str(x) in sets][:20]
            if not ad_ids and not set_ids:
                continue
            label = str(a.get("label") or "").strip()[:40] or "ABCD"[len(clean_arms)]
            clean_arms.append({"label": label, "name": str(a.get("name") or "").strip()[:200] or None,
                               "ad_ids": ad_ids, "adset_ids": set_ids})
        if len(clean_arms) < 2:
            return None, ("Pick an ad or ad set for at least two arms", "arms")
        if len({a["label"].lower() for a in clean_arms}) != len(clean_arms):
            return None, ("Give each arm its own name", "arms")
        out["arms"] = clean_arms
    if "status" in data:
        if data["status"] not in ex.STATUSES:
            return None, ("Unknown status", "status")
        out["status"] = data["status"]
    if "winner" in data:
        out["winner"] = str(data.get("winner") or "").strip()[:40] or None
    return out, None


def create(fields, user_id, proposal_id=None):
    fields = {**fields, "arms": json.dumps(fields["arms"]), "created_by": user_id, "proposal_id": proposal_id}
    cols = list(fields)
    row = db.execute(f"INSERT INTO experiments ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                     [fields[c] for c in cols], returning=True)
    return row["id"]


def load(exp_id):
    return db.query(f"SELECT {COLS} FROM experiments WHERE id = %s", (exp_id,), one=True)


def names_for(arms):
    ids = {i for a in arms for i in a.get("ad_ids") or []}
    set_ids = {i for a in arms for i in a.get("adset_ids") or []}
    ads = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM ads WHERE id = ANY(%s)", (list(ids),))} if ids else {}
    sets = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM adsets WHERE id = ANY(%s)", (list(set_ids),))} if set_ids else {}
    return ads, sets


def summary(exp):
    out = ex.with_results(exp)
    ads, sets = names_for(exp["arms"])
    for a in out["arms"]:
        a["names"] = [ads.get(i, "an ad that's gone") for i in a.get("ad_ids") or []] + \
                     [f"Ad set: {sets.get(i, 'gone')}" for i in a.get("adset_ids") or []]
    for k in ("created_at", "closed_at"):
        out[k] = exp[k].isoformat() if exp.get(k) else None
    out["metric_label"] = ex.METRICS[exp["metric"]]["label"]
    out["meta"] = meta_view(exp)
    out.pop("meta_study", None)
    return out


def meta_view(exp):
    s = exp.get("meta_study")
    if not s:
        return None
    if not s.get("id"):
        return {"creating": True, "unknown": mt.booking_unsettled(s, datetime.now().timestamp())}
    return {"id": s["id"], "kind": s["kind"], "start_day": s["start_day"], "end_day": s["end_day"],
            "daily_budget_cents": s.get("daily_budget_cents"), "total_cents": s.get("total_cents"),
            "state": mt.study_state(s, datetime.now().timestamp()), "fetched_at": s.get("fetched_at"),
            "ended_early_at": s.get("ended_early_at"), "verdict": mt.meta_verdict(s.get("results") or {}, exp["arms"])}


@bp.get("")
@admin_required
def listing():
    rows = db.query(f"SELECT {COLS} FROM experiments ORDER BY (status = 'running') DESC, start_day DESC, id DESC")
    return jsonify({"items": [summary(r) for r in rows], "metrics": {k: v["label"] for k, v in ex.METRICS.items()},
                    "meta_enabled": mt.enabled()})


@bp.get("/choices")
@admin_required
def choices():
    """Ad sets with their ads, to pick arms from (deleted ones left out)."""
    sets = db.query("""SELECT s.id, s.name, s.effective_status, c.name AS campaign_name FROM adsets s
                       LEFT JOIN campaigns c ON c.id = s.campaign_id
                       WHERE COALESCE(s.effective_status, '') NOT IN ('DELETED', 'ARCHIVED') ORDER BY c.name, s.name""")
    ads = db.query("""SELECT id, name, adset_id, effective_status FROM ads
                      WHERE COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED') ORDER BY name""")
    by_set = {}
    for a in ads:
        by_set.setdefault(a["adset_id"], []).append(a)
    return jsonify({"adsets": [{**s, "ads": by_set.get(s["id"], [])} for s in sets]})


@bp.get("/<int:exp_id>")
@admin_required
def detail(exp_id):
    exp = load(exp_id)
    if not exp:
        return api_error("Test not found", 404)
    return jsonify(summary(exp))


@bp.post("")
@admin_required
def add():
    fields, err = clean(request.get_json(silent=True) or {})
    if err:
        return api_error(err[0], 400, field=err[1])
    exp_id = create(fields, current_user()["id"])
    log_activity("experiment.created", subject=str(exp_id), details={"name": fields["name"]})
    return jsonify(summary(load(exp_id))), 201


@bp.patch("/<int:exp_id>")
@admin_required
def edit(exp_id):
    exp = load(exp_id)
    if not exp:
        return api_error("Test not found", 404)
    data = request.get_json(silent=True) or {}
    fields, err = clean(data, partial=True)
    if err:
        return api_error(err[0], 400, field=err[1])
    start = fields.get("start_day", exp["start_day"])
    end = fields.get("end_day", exp["end_day"])
    if end and end < start:
        return api_error("The end comes before the start", 400, field="end_day")
    if "winner" in fields and fields["winner"] and fields["winner"] not in [a["label"] for a in fields.get("arms", exp["arms"])]:
        return api_error("Pick one of the arms as the winner", 400, field="winner")
    if not fields:
        return jsonify(summary(exp))
    if "arms" in fields and exp.get("meta_study") and fields["arms"] != exp["arms"]:
        return api_error("This test runs on Meta, so its arms can't change", 409, field="arms")
    if "arms" in fields:
        fields["arms"] = json.dumps(fields["arms"])
    if fields.get("status") == "running":
        fields.setdefault("winner", None)
    sets = [f"{k} = %s" for k in fields]
    if "status" in fields:
        sets.append("closed_at = " + ("NULL" if fields["status"] == "running" else "COALESCE(closed_at, now())"))
    db.execute(f"UPDATE experiments SET {', '.join(sets)}, updated_at = now() WHERE id = %s", list(fields.values()) + [exp_id])
    log_activity("experiment.updated", subject=str(exp_id), details={k: str(v)[:200] for k, v in fields.items() if k != "arms"})
    return jsonify(summary(load(exp_id)))


# ---------------------------------------------------------------- on Meta (roadmap 3.2)

def _budget_cap(exp):
    """Twice the daily budget the arms run on (the campaign's, or their ad sets' when the campaign
    has none), and never above the account's ceiling."""
    import money_rules
    cap = money_rules.ceiling(settings_store.get("max_daily_budget_cents"))
    ids = [i for a in exp["arms"] for i in a.get("ad_ids") or []]
    row = db.query("""SELECT MAX(COALESCE(c.daily_budget_cents, s.daily_budget_cents)) AS b FROM ads a
                      JOIN campaigns c ON c.id = a.campaign_id LEFT JOIN adsets s ON s.id = a.adset_id
                      WHERE a.id = ANY(%s)""", (ids,), one=True) if ids else None
    return min(2 * row["b"], cap) if row and row["b"] else cap


def _plan(exp, data):
    start, err = _day(data.get("start_day"), "start_day", required=True)
    if err:
        raise mt.PlanError(*err)
    end, err = _day(data.get("end_day"), "end_day")
    if err:
        raise mt.PlanError(*err)
    try:
        budget = int(data["daily_budget_cents"]) if data.get("daily_budget_cents") not in (None, "") else None
    except (TypeError, ValueError):
        raise mt.PlanError("Type the daily budget in dollars, like 10", "budget")
    return mt.plan(exp, start, end, budget, ex.account_today(), _tz(), _budget_cap(exp))


def _tz():
    import config
    return account_info.tz_name()


@bp.post("/<int:exp_id>/meta/plan")
@admin_required
def meta_plan(exp_id):
    """What running this test on Meta would do and cost. Reads nothing from Meta, writes nothing."""
    exp = load(exp_id)
    if not exp:
        return api_error("Test not found", 404)
    try:
        p = _plan(exp, request.get_json(silent=True) or {})
    except mt.PlanError as e:
        return api_error(str(e), 400, field=e.field)
    return jsonify({k: p[k] for k in ("kind", "days", "total_cents", "summary")} | {"enabled": mt.enabled()})


@bp.post("/<int:exp_id>/meta")
@admin_required
def meta_create(exp_id):
    """Create the A/B test on Meta. Needs the Settings switch on and the cost confirmed as shown."""
    if not mt.enabled():
        return api_error("Meta A/B tests are switched off. An admin turns them on in Settings → Meta A/B tests.", 403)
    exp = load(exp_id)
    if not exp:
        return api_error("Test not found", 404)
    if exp["status"] != "running":
        return api_error("Only a running test can go on Meta", 409)
    if mt.booking_unsettled(exp.get("meta_study"), datetime.now().timestamp()):
        return api_error("Meta didn't answer when this test was booked, so it may be on Meta already. "
                         "Use “Look for it on Meta” first.", 409)
    if exp.get("meta_study"):
        return api_error("This test is already on Meta", 409)
    data = request.get_json(silent=True) or {}
    try:
        p = _plan(exp, data)
    except mt.PlanError as e:
        return api_error(str(e), 400, field=e.field)
    if p["total_cents"] != (data.get("confirm_total_cents") if p["total_cents"] is not None else None):
        return api_error("The cost changed since you looked. Check it again and confirm.", 409)
    import ads_api
    user = current_user()
    row = {"id": str(exp_id), "name": exp["name"], "campaign_id": None}
    payload = p["payload"]
    booking = {"type": payload["type"], "kind": p["kind"], "name": payload["name"], "start_time": payload["start_time"],
               "end_time": payload["end_time"], "start_day": data["start_day"], "end_day": data["end_day"],
               "daily_budget_cents": (payload.get("creative_test_config") or {}).get("daily_budget"), "total_cents": p["total_cents"]}
    # Claimed first: a second click while Meta is answering gets "already being created", not a second study.
    # The claim carries the booking, so one a restart cut off can still be looked for on Meta.
    claim = {**booking, "creating": True, "at": datetime.now().astimezone().isoformat()}
    if not db.execute("""UPDATE experiments SET meta_study = %s WHERE id = %s AND meta_study IS NULL
                         RETURNING id""", (json.dumps(claim), exp_id), returning=True):
        return api_error("This test is already being put on Meta", 409)
    try:
        study = meta_client.post(f"{mt.business_id()}/ad_studies", data=mt.graph_form(payload))
    except (meta_client.MetaError, mt.PlanError) as exc:
        ads_api.record(user, "study", row, "create", None, p["summary"], False, str(exc))
        if getattr(exc, "unknown", False):
            # Meta may have booked it (with its own test budget): the claim stays until someone looks (audit A3-73, A3-114).
            db.execute("UPDATE experiments SET meta_study = %s WHERE id = %s", (json.dumps({**claim, "unknown": True}), exp_id))
            return api_error(f"{exc} The test is marked “may be on Meta”: look for it there before booking it again.", 400)
        db.execute("UPDATE experiments SET meta_study = NULL WHERE id = %s", (exp_id,))
        return api_error(f"Meta refused: {exc}", 400)
    stored = {**booking, "id": study["id"], "created_at": datetime.now().astimezone().isoformat(), "results": {}}
    db.execute("UPDATE experiments SET meta_study = %s, updated_at = now() WHERE id = %s", (json.dumps(stored), exp_id))
    ads_api.record(user, "study", {**row, "id": study["id"]}, "create", None, p["summary"], True)
    return jsonify(summary(load(exp_id))), 201


@bp.post("/<int:exp_id>/meta/find")
@admin_required
def meta_find(exp_id):
    """After Meta didn't answer a booking: adopt the study when Meta has it (by its exact name), otherwise
    free the test so it can be booked again."""
    exp = load(exp_id)
    pending = (exp or {}).get("meta_study") or {}
    if not mt.booking_unsettled(pending, datetime.now().timestamp()):
        return api_error("There's nothing to look for on this test", 409)
    try:
        found = [x for x in meta_client.paged(f"{mt.business_id()}/ad_studies", fields="id,name", limit=100)
                 if x.get("name") == pending.get("name")]
    except (meta_client.MetaError, mt.PlanError) as exc:
        return api_error(f"Couldn't look on Meta just now: {exc}", 400)
    if found:
        stored = {k: v for k, v in pending.items() if k not in ("creating", "unknown", "at")}
        stored.update(id=found[0]["id"], created_at=pending.get("at"), results={})
        db.execute("""UPDATE experiments SET meta_study = %s, updated_at = now() WHERE id = %s AND meta_study->>'id' IS NULL""",
                   (json.dumps(stored), exp_id))
        log_activity("experiment.meta_found", subject=str(exp_id), details={"study": found[0]["id"]})
    else:
        db.execute("""UPDATE experiments SET meta_study = NULL WHERE id = %s AND meta_study->>'id' IS NULL
                      AND meta_study->>'at' IS NOT DISTINCT FROM %s""", (exp_id, pending.get("at")))
        log_activity("experiment.meta_not_found", subject=str(exp_id))
    return jsonify({**summary(load(exp_id)), "found": bool(found)})


@bp.post("/<int:exp_id>/meta/refresh")
@admin_required
def meta_refresh(exp_id):
    exp = load(exp_id)
    if not exp or not (exp.get("meta_study") or {}).get("id"):
        return api_error("This test isn't on Meta", 404)
    try:
        fresh = mt.fetch(exp["meta_study"])
    except meta_client.MetaError as exc:
        return api_error(f"Meta didn't answer: {exc}", 400)
    db.execute("UPDATE experiments SET meta_study = %s WHERE id = %s", (json.dumps(fresh), exp_id))
    return jsonify(summary(load(exp_id)))


@bp.post("/<int:exp_id>/meta/end")
@admin_required
def meta_end(exp_id):
    """End a running Meta test now (moves its end time; nothing is deleted)."""
    exp = load(exp_id)
    if not exp or not (exp.get("meta_study") or {}).get("id"):
        return api_error("This test isn't on Meta", 404)
    s = exp["meta_study"]
    now = int(datetime.now().timestamp())
    state = mt.study_state(s, now)
    if state == "scheduled":
        return api_error("It hasn't started yet. To cancel it, delete it in Ads Manager → Experiments.", 409)
    if state == "ended":
        return api_error("It has already ended", 409)
    import ads_api
    user = current_user()
    end = now + 60
    try:
        meta_client.post(s["id"], data={"end_time": end})
    except meta_client.MetaError as exc:
        ads_api.record(user, "study", {"id": s["id"], "name": exp["name"]}, "end", s["end_time"], end, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    s = {**s, "end_time": end, "ended_early_at": datetime.now().astimezone().isoformat()}
    db.execute("UPDATE experiments SET meta_study = %s WHERE id = %s", (json.dumps(s), exp_id))
    ads_api.record(user, "study", {"id": s["id"], "name": exp["name"]}, "end", None, "ended early", True)
    return jsonify(summary(load(exp_id)))
