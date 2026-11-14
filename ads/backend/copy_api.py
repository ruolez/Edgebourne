"""AM-C: Make a paused copy of a campaign or an ad set, level by level (campaign -> each ad set -> each ad), all with
status_option=PAUSED, resumable like campaign builds (Meta's synchronous deep copy stops at 3 child ads; Edge Bourne's
campaign has 5). A step Meta didn't answer is adopted only through campaign_build.adoptable (same name, paused, same
parent, made since the job, not taken), never made twice. A copy that comes back on is switched off at once and named in
History. Owner and this account's admins only."""
import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import ads_api
import campaign_build as cb
import db
import insights
import meta_client
import money_rules
import settings_store
import status_history as sh
import targets
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("copies", __name__, url_prefix="/api/copy")

LEVELS = ("campaign", "adset")
GONE = ("ARCHIVED", "DELETED")
SUFFIX = " - copy"
TOP = json.dumps({"rename_strategy": "ONLY_TOP_LEVEL_RENAME", "rename_suffix": SUFFIX})
KEEP = json.dumps({"rename_strategy": "NO_RENAME"})
WORD = {"campaign": "campaign", "adset": "ad set", "ad": "ad"}


def _source(level, source_id):
    table = "campaigns" if level == "campaign" else "adsets"
    row = db.query(f"SELECT * FROM {table} WHERE id = %s", (source_id,), one=True) if level in LEVELS else None
    return row


def children(level, source_id):
    """What a copy can hold, read fresh: [{id, name, status, daily_budget, ads: [{id, name, status}]}] (an ad set level copy:
    one entry, the ad set itself)."""
    ads = list(meta_client.paged(f"{source_id}/ads", fields="id,name,status,adset_id", limit=200))
    if level == "adset":
        me = meta_client.get(source_id, fields="id,name,status,daily_budget,lifetime_budget,end_time,campaign_id")
        sets = [me]
    else:
        sets = list(meta_client.paged(f"{source_id}/adsets", fields="id,name,status,daily_budget,lifetime_budget,end_time", limit=100))
    return [{"id": str(s["id"]), "name": s.get("name"), "status": s.get("status"), "daily_budget": ads_api._cents_of(s.get("daily_budget")),
             "lifetime_budget": ads_api._cents_of(s.get("lifetime_budget")), "campaign_id": s.get("campaign_id"), "end_time": s.get("end_time"),
             "ads": [{"id": str(a["id"]), "name": a.get("name"), "status": a.get("status")} for a in ads if str(a.get("adset_id")) == str(s["id"])]}
            for s in sets]


def plan_view(level, row, sets):
    out = {"level": level, "source": {"id": row["id"], "name": row["name"], "status": row.get("status")}, "name": f"{row['name']}{SUFFIX}",
           "adsets": [{**s, "ticked": s["status"] not in GONE, "ads": [{**a, "ticked": a["status"] not in GONE} for a in s["ads"]]} for s in sets]}
    if level == "adset":
        out["campaigns"] = db.query("""SELECT id, name, daily_budget_cents FROM campaigns
                                       WHERE COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED') ORDER BY name""")
        out["target_campaign_id"] = row["campaign_id"]
    return out


@bp.post("/<level>/<source_id>/plan")
@admin_required
def plan(level, source_id):
    row = _source(level, source_id)
    if not row:
        return api_error("Not found", 404)
    try:
        sets = children(level, source_id)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta: {exc}", 400)
    return jsonify(plan_view(level, row, sets))


def per_day(daily, lifetime, end, now=None):
    """What a copy's budget can spend a day: the daily budget, or a lifetime budget's pace until its end (a copy starts at 0 spent)."""
    if daily:
        return daily
    if lifetime:
        end_at = datetime.strptime(sh.minute_utc(end), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) if end else None
        return money_rules.lifetime_pace(lifetime, 0, now or datetime.now(timezone.utc), end_at) or 0
    return 0


def clean_plan(level, row, raw, sets, camp=None):
    """The person's picks, kept only where they name this source's own ad sets and ads (read fresh): (plan, problem). camp: the
    source campaign's budget read fresh from Meta ({daily_budget, lifetime_budget, stop_time}); every budget a copy carries,
    daily or lifetime (as its pace), is checked against the account's ceiling."""
    raw = raw if isinstance(raw, dict) else {}
    name = str(raw.get("name") or "").strip()[:200]
    if not name:
        return None, ("name", "Give the copy a name")
    by_set = {s["id"]: s for s in sets}
    picked = []
    for item in raw.get("adsets") or []:
        if not isinstance(item, dict) or str(item.get("id")) not in by_set:
            continue
        s = by_set[str(item["id"])]
        ad_ids = {a["id"] for a in s["ads"]}
        picked.append({"id": s["id"], "name": s["name"], "daily_budget": s["daily_budget"], "lifetime_budget": s["lifetime_budget"],
                       "end_time": s.get("end_time"),
                       "ads": [{"id": a, "name": next(x["name"] for x in s["ads"] if x["id"] == a)} for a in
                               dict.fromkeys(str(x) for x in item.get("ads") or []) if a in ad_ids]})
    if level == "adset" and not picked:
        picked = [{"id": sets[0]["id"], "name": sets[0]["name"], "daily_budget": sets[0]["daily_budget"],
                   "lifetime_budget": sets[0]["lifetime_budget"], "end_time": sets[0].get("end_time"), "ads": []}]
    out = {"name": name, "adsets": picked}
    cap = targets.ceiling()
    for s in picked:
        if per_day(s["daily_budget"], s["lifetime_budget"], s.get("end_time")) > cap:
            return None, ("adsets", f"“{s['name']}” has a budget above this account's ceiling of {cap / 100:,.2f} a day.")
    if level == "campaign":
        camp = camp or {}
        if per_day(ads_api._cents_of(camp.get("daily_budget")), ads_api._cents_of(camp.get("lifetime_budget")), camp.get("stop_time")) > cap:
            return None, ("name", f"The campaign's budget is above this account's ceiling of {cap / 100:,.2f} a day: lower it first.")
        return out, None
    target = db.query("""SELECT id, name, daily_budget_cents, lifetime_budget_cents FROM campaigns WHERE id = %s
                         AND COALESCE(effective_status, '') NOT IN ('DELETED', 'ARCHIVED')""",
                      (str(raw.get("target_campaign_id") or row["campaign_id"]),), one=True)
    if not target:
        return None, ("target", "Pick the campaign the copy goes in")
    out["target_campaign_id"] = target["id"]
    if not (target["daily_budget_cents"] or target["lifetime_budget_cents"]):
        s = picked[0]
        if not (s["daily_budget"] or s["lifetime_budget"]):
            return None, ("target", "That campaign has no budget of its own and this ad set's budget is on its campaign: "
                                    "pick a campaign with a budget.")
    return out, None


def steps(level, plan):
    out = ["campaign"] if level == "campaign" else []
    for s in plan["adsets"]:
        out.append(f"adset:{s['id']}")
        out += [f"ad:{a['id']}" for a in s["ads"]]
    return out


def load(job_id):
    return db.query("SELECT * FROM copy_jobs WHERE id = %s", (job_id,), one=True)


def view(job):
    made, plan = job["made"] or {}, job["plan"]
    names = {f"adset:{s['id']}": s["name"] for s in plan["adsets"]}
    names.update({f"ad:{a['id']}": a["name"] for s in plan["adsets"] for a in s["ads"]})

    def state(key):
        if key == "campaign":
            return "done" if made.get("campaign_id") else "todo"
        kind, src = key.split(":")
        return "done" if (made.get(f"{kind}s") or {}).get(src) else "todo"
    out_steps = []
    for key in steps(job["level"], plan):
        st = state(key)
        if st == "todo" and job["status"] == "partial" and not any(s["state"] == "failed" for s in out_steps):
            st = "failed"
        out_steps.append({"key": key, "label": plan["name"] if key == "campaign" else names.get(key, key), "kind": key.split(":")[0],
                          "state": st})
    top = ("campaign", made.get("campaign_id")) if job["level"] == "campaign" else ("adset", (made.get("adsets") or {}).get(plan["adsets"][0]["id"]))
    return {"id": job["id"], "level": job["level"], "status": job["status"], "error": job["error"], "steps": out_steps,
            "made": {k: v for k, v in made.items() if k not in ("unknown", "unguarded")}, "open": {"level": top[0], "id": top[1]} if top[1] else None,
            "source_id": job["source_id"], "name": plan["name"], "switched_off": made.get("guard") or []}


def save(job_id, made, status, error=None):
    db.execute("UPDATE copy_jobs SET made = %s, status = %s, error = %s, updated_at = now() WHERE id = %s",
               (json.dumps(made), status, error, job_id))


def find_made(job, kind, name, parent):
    """After Meta didn't answer a copy: the object that try may have made (cb.adoptable), or None."""
    account = settings_store.get("meta_ad_account_id")
    edge = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}[kind]
    try:
        found = list(meta_client.paged(f"act_{account}/{edge}", fields="id,name,campaign_id,adset_id,status,created_time", limit=200))
    except meta_client.MetaError as exc:
        raise meta_client.MetaError(f"couldn't look for it on Meta: {exc}", unknown=True) from None
    taken = set()
    for r in db.query("SELECT made FROM copy_jobs WHERE id <> %s", (job["id"],)):
        m = r["made"] or {}
        taken |= {m.get("campaign_id"), *(m.get("adsets") or {}).values(), *(m.get("ads") or {}).values()}
    for r in db.query("SELECT made FROM campaign_builds WHERE made IS NOT NULL"):
        m = r["made"] or {}
        taken |= {m.get("campaign_id"), m.get("adset_id"), *(m.get("ads") or {}).values()}
    return cb.adoptable(found, name, parent, job["created_at"], taken)


def guard_paused(user, kind, new_id, name, campaign_id, made):
    """A copy must come back off: read its status, and switch it off at once (named in History) if Meta made it on."""
    try:
        status = meta_client.get(new_id, fields="status").get("status")
    except meta_client.MetaError:
        status = None
    if status == "PAUSED":
        made["unguarded"] = [u for u in made.get("unguarded") or [] if u["id"] != new_id]
        return
    row = {"id": new_id, "name": name, "campaign_id": campaign_id}
    try:
        meta_client.post(new_id, status="PAUSED")
        ads_api.record(user, kind, row, "copy_guard", status or "unknown", "PAUSED", True)
        made.setdefault("guard", []).append(new_id)
        made["unguarded"] = [u for u in made.get("unguarded") or [] if u["id"] != new_id]
    except meta_client.MetaError as exc:
        ads_api.record(user, kind, row, "copy_guard", status or "unknown", "PAUSED", False, str(exc))
        unguarded = made.setdefault("unguarded", [])
        if not any(u["id"] == new_id for u in unguarded):
            unguarded.append({"kind": kind, "id": new_id, "name": name, "campaign_id": campaign_id})
        raise meta_client.MetaError(f"the copy came back on and couldn't be switched off: {exc}. Switch it off in Ads Manager now.")


def run(job_id, user):
    with db.try_lock(f"copy:{job_id}") as mine:
        if not mine:
            return False
        return _run(job_id, user)


def _run(job_id, user):
    job = load(job_id)
    if job["status"] == "done":
        return True
    level, plan, made = job["level"], job["plan"], dict(job["made"] or {})
    made.setdefault("adsets", {})
    made.setdefault("ads", {})
    source = _source(level, job["source_id"]) or {"id": job["source_id"], "name": plan["name"]}
    for u in list(made.get("unguarded") or []):  # a copy that came back on and couldn't be switched off: that first, every time
        try:
            guard_paused(user, u["kind"], u["id"], u["name"], u["campaign_id"], made)
        except meta_client.MetaError as exc:
            save(job_id, made, "partial", str(exc))
            return False
        save(job_id, made, "running")
    for step in steps(level, plan):
        kind, _, src = step.partition(":")
        if (kind == "campaign" and made.get("campaign_id")) or (kind != "campaign" and made[f"{kind}s"].get(src)):
            continue
        maybe = made.get("unknown") == step
        try:
            if kind == "campaign":
                new_id = maybe and (find_made(job, "campaign", source["name"] + SUFFIX, None) or find_made(job, "campaign", plan["name"], None))
                if not new_id:
                    res = meta_client.post(f"{source['id']}/copies", deep_copy="false", status_option="PAUSED", rename_options=TOP)
                    new_id = res.get("copied_campaign_id") or (res.get("ad_object_ids") or [{}])[0].get("copied_id")
                    if not new_id:
                        raise meta_client.MetaError("Meta didn't return the copy's id")
                made["campaign_id"] = new_id
                save(job_id, made, "running")
                guard_paused(user, "campaign", new_id, plan["name"], new_id, made)
                if plan["name"] != source["name"] + SUFFIX:
                    meta_client.post(new_id, name=plan["name"])
                ads_api.record(user, "campaign", {"id": new_id, "name": plan["name"], "campaign_id": new_id}, "copy", source["name"], plan["name"], True)
            elif kind == "adset":
                s = next(x for x in plan["adsets"] if x["id"] == src)
                target = made.get("campaign_id") if level == "campaign" else job["target_campaign_id"]
                expect = s["name"] if level == "campaign" else s["name"] + SUFFIX
                new_id = maybe and find_made(job, "adset", expect, target)
                if not new_id:
                    res = meta_client.post(f"{src}/copies", campaign_id=target, deep_copy="false", status_option="PAUSED",
                                           rename_options=KEEP if level == "campaign" else TOP)
                    new_id = res.get("copied_adset_id") or (res.get("ad_object_ids") or [{}])[0].get("copied_id")
                    if not new_id:
                        raise meta_client.MetaError("Meta didn't return the copy's id")
                made["adsets"][src] = new_id
                save(job_id, made, "running")
                final = s["name"] if level == "campaign" else plan["name"]
                guard_paused(user, "adset", new_id, final, target, made)
                if level == "adset" and plan["name"] != expect:
                    meta_client.post(new_id, name=plan["name"])
                ads_api.record(user, "adset", {"id": new_id, "name": final, "campaign_id": target}, "copy", s["name"], final, True)
            else:
                s = next(x for x in plan["adsets"] if any(a["id"] == src for a in x["ads"]))
                a = next(x for x in s["ads"] if x["id"] == src)
                parent = made["adsets"][s["id"]]
                camp = made.get("campaign_id") if level == "campaign" else job["target_campaign_id"]
                new_id = maybe and find_made(job, "ad", a["name"], parent)
                if not new_id:
                    res = meta_client.post(f"{src}/copies", adset_id=parent, status_option="PAUSED", rename_options=KEEP)
                    new_id = res.get("copied_ad_id") or (res.get("ad_object_ids") or [{}])[0].get("copied_id")
                    if not new_id:
                        raise meta_client.MetaError("Meta didn't return the copy's id")
                made["ads"][src] = new_id
                save(job_id, made, "running")
                guard_paused(user, "ad", new_id, a["name"], camp, made)
                ads_api.record(user, "ad", {"id": new_id, "name": a["name"], "campaign_id": camp}, "copy", a["name"], a["name"], True)
        except meta_client.MetaError as exc:
            what = {"campaign": "the campaign"}.get(kind) or f"the {WORD[kind]} “{next((x['name'] for x in plan['adsets'] if x['id'] == src), None) or next((y['name'] for x in plan['adsets'] for y in x['ads'] if y['id'] == src), src)}”"
            if exc.unknown:
                made["unknown"] = step
            else:
                made.pop("unknown", None)
            save(job_id, made, "partial", (f"Meta didn't answer while copying {what}. It may exist already: Finish the copy looks for it "
                                           "before making another." if exc.unknown else f"Meta refused to copy {what}: {exc}"))
            ads_api.after_write("structure sync", insights.sync_structure)
            return False
        made.pop("unknown", None)
        save(job_id, made, "running")
    save(job_id, made, "done")
    ads_api.after_write("structure sync", insights.sync_structure)
    log_activity("copy.made", subject=job["source_id"], details={"level": level, "made": made})
    return True


@bp.post("/<level>/<source_id>")
@admin_required
def create(level, source_id):
    row = _source(level, source_id)
    if not row:
        return api_error("Not found", 404)
    raw = request.get_json(silent=True) or {}
    key = str(raw.get("client_key") or "")[:64] or None
    if key:
        same = db.query("SELECT id FROM copy_jobs WHERE client_key = %s", (key,), one=True)
        if same:
            return jsonify(view(load(same["id"])))
    try:
        sets = children(level, source_id)
        camp = meta_client.get(source_id, fields="daily_budget,lifetime_budget,stop_time") if level == "campaign" else None
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta, so nothing was copied: {exc}", 400)
    plan_, problem = clean_plan(level, row, raw.get("plan"), sets, camp)
    if problem:
        return api_error(problem[1], 400, field=problem[0])
    user = current_user()
    job = db.execute("""INSERT INTO copy_jobs (level, source_id, target_campaign_id, plan, client_key, created_by)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id""",
                     (level, source_id, plan_.get("target_campaign_id"), json.dumps(plan_), key, user["id"]), returning=True)
    if not job:
        job = db.query("SELECT id FROM copy_jobs WHERE client_key = %s", (key,), one=True)
        return jsonify(view(load(job["id"])))
    run(job["id"], user)
    return jsonify(view(load(job["id"]))), 201


@bp.get("/<int:job_id>")
@admin_required
def detail(job_id):
    job = load(job_id)
    return jsonify(view(job)) if job else api_error("Not found", 404)


@bp.post("/<int:job_id>/resume")
@admin_required
def resume(job_id):
    job = load(job_id)
    if not job:
        return api_error("Not found", 404)
    if job["status"] == "done":
        return api_error("The copy is already made", 409)
    run(job_id, current_user())
    return jsonify(view(load(job_id)))

