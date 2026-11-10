"""New campaign wizard API (admins): check, create everything PAUSED (resumable), publish."""
import json

from flask import Blueprint, jsonify, request

import adset_build as ab
import adsets_api
import campaign_build as cb
import db
import meta_client
import settings_store
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("builds", __name__, url_prefix="/api/builds")


def running_daily_cents():
    return int(db.query("SELECT COALESCE(SUM(daily_budget_cents), 0) AS c FROM campaigns WHERE effective_status = 'ACTIVE'", one=True)["c"])


def templates():
    return {r["id"]: r for r in db.query("""SELECT id, name, title, body, cta_type, object_type FROM ads
                                            WHERE COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED') AND creative_id IS NOT NULL""")}


def forms_by_id():
    import forms_api
    try:
        return {f["id"]: f["name"] for f in forms_api.page_forms() if f.get("status") != "ARCHIVED"}
    except meta_client.MetaError:
        return {}


def clean(raw):
    ads = []
    for a in (raw.get("ads") or [])[:10]:
        if not isinstance(a, dict):
            continue
        media = a.get("media") if isinstance(a.get("media"), dict) else {"kind": "same"}
        ads.append({"name": str(a.get("name") or "")[:200], "title": str(a.get("title") or "")[:255], "body": str(a.get("body") or "")[:5000],
                    "template_ad_id": str(a.get("template_ad_id") or ""), "cta_type": a.get("cta_type") or None,
                    "media": {k: str(v)[:64] for k, v in media.items() if k in ("kind", "hash", "video_id")}})
    try:
        budget = int(raw.get("daily_budget_cents")) if raw.get("daily_budget_cents") not in (None, "") else None
    except (TypeError, ValueError):
        budget = None
    adset_raw = raw.get("adset") or {}
    return {"name": str(raw.get("name") or "")[:200], "daily_budget_cents": budget,
            "adset": {**adsets_api.clean(adset_raw), "template_adset_id": str(adset_raw.get("template_adset_id") or "")},
            "form_id": str(raw.get("form_id") or ""), "ads": ads}


def check(spec, forms=None):
    forms = forms if forms is not None else forms_by_id()
    tpl = templates()
    errs = cb.problems(spec, set(forms), set(tpl), running_daily_cents())
    if not spec["adset"]["template_adset_id"] or not db.query("SELECT 1 FROM adsets WHERE id = %s", (spec["adset"]["template_adset_id"],), one=True):
        errs.append(("adset", "Pick the ad set it starts from"))
    out = {"problems": [{"step": s, "message": m} for s, m in errs]}
    if not errs:
        out["review"] = cb.review(spec, forms.get(spec["form_id"], ""), {k: v["name"] for k, v in tpl.items()})
    return out


def load(build_id):
    return db.query("SELECT * FROM campaign_builds WHERE id = %s", (build_id,), one=True)


def view(b):
    made = b["made"] or {}
    status = {}
    for table, ids in (("campaigns", [made.get("campaign_id")]), ("adsets", [made.get("adset_id")]), ("ads", list((made.get("ads") or {}).values()))):
        for r in db.query(f"SELECT id, effective_status FROM {table} WHERE id = ANY(%s)", ([i for i in ids if i],)):
            status[r["id"]] = r["effective_status"]
    return {"id": b["id"], "status": b["status"], "error": b["error"], "made": made, "entity_status": status,
            "spec": b["spec"], "review": cb.review(b["spec"], forms_by_id().get(b["spec"]["form_id"], b["spec"]["form_id"]),
                                                    {k: v["name"] for k, v in templates().items()}),
            "created_at": b["created_at"].isoformat(), "published_at": b["published_at"].isoformat() if b["published_at"] else None}


def save(build_id, made, status, error=None):
    db.execute("UPDATE campaign_builds SET made = %s, status = %s, error = %s, updated_at = now() WHERE id = %s",
               (json.dumps(made), status, error, build_id))


def run(build_id, user):
    """Create whatever is still missing, in order. Stops at the first refusal; what exists stays (paused)."""
    import ads_api
    import insights
    b = load(build_id)
    spec, made = b["spec"], dict(b["made"] or {})
    made.setdefault("ads", {})
    account = settings_store.get("meta_ad_account_id")
    for step in cb.next_steps(made, len(spec["ads"])):
        try:
            if step == "campaign":
                body = cb.campaign_payload(spec)
                res = meta_client.post(f"act_{account}/campaigns", data={k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in body.items()})
                made["campaign_id"] = res["id"]
                ads_api.record(user, "campaign", {"id": res["id"], "name": spec["name"], "campaign_id": res["id"]}, "create", None,
                               f"{spec['name']} (paused, {cb.dollars(spec['daily_budget_cents'])}/day)", True)
                insights.sync_structure()
            elif step == "adset":
                s = spec["adset"]
                tpl = adsets_api.template(s["template_adset_id"])
                body = ab.payload(s, tpl, {"id": made["campaign_id"], "daily_budget_cents": spec["daily_budget_cents"]},
                                  settings_store.get("meta_page_id"))
                res = meta_client.post(f"act_{account}/adsets", data={k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in body.items()})
                made["adset_id"] = res["id"]
                ads_api.record(user, "adset", {"id": res["id"], "name": s["name"], "campaign_id": made["campaign_id"]}, "create", None,
                               f"{s['name']} (paused)", True)
                insights.sync_structure()
            else:
                i = int(step.split(":")[1])
                ad = spec["ads"][i]
                ad_id, err = ads_api.create_ad_from(user, {**ad, "adset_id": made["adset_id"], "form_id": spec["form_id"]})
                if err:
                    raise meta_client.MetaError(err[0])
                made["ads"][str(i)] = ad_id
        except meta_client.MetaError as exc:
            what = {"campaign": "the campaign", "adset": "the ad set"}.get(step, f"ad {int(step.split(':')[1]) + 1}")
            save(build_id, made, "partial", f"Meta refused {what}: {exc}")
            return False
        save(build_id, made, "partial")
    save(build_id, made, "created")
    log_activity("build.created", subject=str(build_id), details={"made": made})
    return True


@bp.get("/options")
@admin_required
def options():
    o = adsets_api.options().get_json()
    tpl = sorted(templates().values(), key=lambda t: t["name"])
    return jsonify({**o, "templates": tpl, "forms": [{"id": k, "name": v} for k, v in forms_by_id().items()],
                    "running_daily_cents": running_daily_cents(), "max_ads": cb.MAX_ADS, "cta_types": list(cb.CTA_FOR_FORMS),
                    "builds": [{"id": r["id"], "name": r["spec"].get("name"), "status": r["status"], "created_at": r["created_at"].isoformat()}
                               for r in db.query("SELECT id, spec, status, created_at FROM campaign_builds ORDER BY id DESC LIMIT 5")]})


@bp.post("/check")
@admin_required
def check_only():
    return jsonify(check(clean(request.get_json(silent=True) or {})))


@bp.post("")
@admin_required
def create():
    spec = clean(request.get_json(silent=True) or {})
    result = check(spec)
    if result["problems"]:
        p = result["problems"][0]
        return jsonify({"error": p["message"], "field": p["step"], **result}), 400
    user = current_user()
    b = db.execute("INSERT INTO campaign_builds (spec, created_by) VALUES (%s, %s) RETURNING id", (json.dumps(spec), user["id"]), returning=True)
    run(b["id"], user)
    return jsonify(view(load(b["id"]))), 201


@bp.get("/<int:build_id>")
@admin_required
def detail(build_id):
    b = load(build_id)
    return jsonify(view(b)) if b else api_error("Not found", 404)


@bp.post("/<int:build_id>/resume")
@admin_required
def resume(build_id):
    b = load(build_id)
    if not b:
        return api_error("Not found", 404)
    if b["status"] != "partial":
        return api_error("Nothing left to create", 409)
    run(build_id, current_user())
    return jsonify(view(load(build_id)))


def typed_matches(typed, cents):
    try:
        return round(float(str(typed).replace("$", "").replace(",", "").strip()) * 100) == int(cents)
    except ValueError:
        return False


@bp.post("/<int:build_id>/publish")
@admin_required
def publish(build_id):
    """Turn everything on: ads, then the ad set, then the campaign. Needs the daily budget typed."""
    import ads_api
    b = load(build_id)
    if not b:
        return api_error("Not found", 404)
    if b["status"] != "created":
        return api_error("Create everything first" if b["status"] == "partial" else "It's already published", 409)
    budget = b["spec"]["daily_budget_cents"]
    if not typed_matches((request.get_json(silent=True) or {}).get("typed"), budget):
        return api_error(f"Type the daily budget, {cb.dollars(budget)}, to publish", 400, field="typed")
    user = current_user()
    for level, eid in cb.publish_order(b["made"]):
        row = ads_api.entity(level, eid)
        if not row:
            return api_error("The new campaign isn't synced yet. Try again in a minute.", 409)
        err = ads_api.apply_status(user, level, row, "ACTIVE")
        if err:
            db.execute("UPDATE campaign_builds SET error = %s WHERE id = %s", (f"Meta refused turning on a {level}: {err}", build_id))
            return api_error(f"Meta refused turning on the {level}: {err}. What was already on stays on; the campaign is still off.", 400)
    db.execute("UPDATE campaign_builds SET status = 'published', error = NULL, published_at = now() WHERE id = %s", (build_id,))
    log_activity("build.published", subject=str(build_id), details={"budget_cents": budget})
    return jsonify(view(load(build_id)))
