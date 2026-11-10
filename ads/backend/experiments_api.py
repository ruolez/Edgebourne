"""Experiments page API (admins): list, create, edit and close tests; the numbers come
from ad_daily and the leads inbox for the test's own dates."""
import json
from datetime import date

from flask import Blueprint, jsonify, request

import db
import experiments as ex
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("experiments", __name__, url_prefix="/api/experiments")

COLS = "id, name, hypothesis, metric, arms, start_day, end_day, target_cents, status, winner, verdict, notes, proposal_id, created_at, closed_at"


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
    return out


@bp.get("")
@admin_required
def listing():
    rows = db.query(f"SELECT {COLS} FROM experiments ORDER BY (status = 'running') DESC, start_day DESC, id DESC")
    return jsonify({"items": [summary(r) for r in rows], "metrics": {k: v["label"] for k, v in ex.METRICS.items()}})


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
