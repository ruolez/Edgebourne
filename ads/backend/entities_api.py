"""Campaign and ad set pages, timelines, side-by-side compare, global search and saved views."""
from datetime import timedelta

from flask import Blueprint, jsonify, request

import account_info
import ads_api
import compare
import db
import ranges
import status_history
import targets
import timeline
from auth import current_user, login_required, visible_campaign_ids
from util import api_error

bp = Blueprint("entities", __name__, url_prefix="/api")

LEVEL_TABLE = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
VIEW_PAGES = ("ads", "leads", "insights", "inbox")


def crumbs(level, row):
    out = []
    if level in ("adset", "ad") and row.get("campaign_id"):
        c = db.query("SELECT id, name FROM campaigns WHERE id = %s", (row["campaign_id"],), one=True)
        if c:
            out.append({"level": "campaign", "id": c["id"], "name": c["name"]})
    if level == "ad" and row.get("adset_id"):
        s = db.query("SELECT id, name FROM adsets WHERE id = %s", (row["adset_id"],), one=True)
        if s:
            out.append({"level": "adset", "id": s["id"], "name": s["name"]})
    out.append({"level": level, "id": row["id"], "name": row["name"]})
    return out


def timeline_for(level, entity_id):
    events = status_history.timeline(level, entity_id, limit=150)
    changes = db.query("""SELECT m.*, u.name AS user_name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                          WHERE m.entity_id = %s ORDER BY m.id DESC LIMIT 100""", (entity_id,))
    proposals = db.query("""SELECT id, title, status, decided_at FROM desk_proposals
                            WHERE entity_id = %s AND decided_at IS NOT NULL ORDER BY id DESC LIMIT 50""", (entity_id,))
    return timeline.merge(events, changes, proposals, money=account_info.money)


def _visible(level, entity_id):
    table = LEVEL_TABLE.get(level)
    if not table:
        return None, api_error("Unknown level", 400)
    row = db.query(f"SELECT * FROM {table} WHERE id = %s", (entity_id,), one=True)
    camp = row and (row["id"] if level == "campaign" else row.get("campaign_id"))
    if not row or not ads_api.can_touch(current_user(), camp):
        return None, api_error("Not found", 404)
    return row, None


def _series(where, params, start, end):
    rows = {r["day"].isoformat(): r for r in db.query(
        f"""SELECT day, SUM(spend_cents) AS spend_cents, SUM(leads) AS leads, SUM(impressions) AS impressions,
                   SUM(link_clicks) AS link_clicks FROM ad_daily WHERE day BETWEEN %s AND %s AND {where} GROUP BY day""",
        [start, end] + params)}
    out = []
    for i in range((end - start).days + 1):
        d = (start + timedelta(days=i)).isoformat()
        r = rows.get(d) or {}
        out.append({"day": d, **{k: int(r.get(k) or 0) for k in ("spend_cents", "leads", "impressions", "link_clicks")}})
    return out


def _detail(level, entity_id):
    row, err = _visible(level, entity_id)
    if err:
        return err
    key, start, end = ads_api.window_from(request.args)
    prev = ranges.previous(start, end, key) if request.args.get("vs") == "prev" else None
    campaign_id = entity_id if level == "campaign" else row["campaign_id"]
    data = ads_api.tree_data(current_user(), start, end, prev=prev, campaign_id=campaign_id,
                             adset_id=entity_id if level == "adset" else None, archived=request.args.get("archived") == "1")
    data["range"]["key"] = key
    camp = data["campaigns"][0] if data["campaigns"] else None
    node = camp if level == "campaign" else next((s for s in (camp or {}).get("adsets", []) if s["id"] == entity_id), None)
    if node is None:
        return api_error("Not found", 404)
    col = "campaign_id" if level == "campaign" else "adset_id"
    data.update({"level": level, "entity": node, "campaign": {k: v for k, v in (camp or {}).items() if k != "adsets"},
                 "crumbs": crumbs(level, row), "timeline": timeline_for(level, entity_id),
                 "series": _series(f"{col} = %s", [entity_id], start, end)})
    return jsonify(data)


@bp.get("/campaigns/<campaign_id>")
@login_required
def campaign_detail(campaign_id):
    return _detail("campaign", campaign_id)


@bp.get("/adsets/<adset_id>")
@login_required
def adset_detail(adset_id):
    return _detail("adset", adset_id)


@bp.get("/timeline/<level>/<entity_id>")
@login_required
def entity_timeline(level, entity_id):
    row, err = _visible(level, entity_id)
    if err:
        return err
    return jsonify({"items": timeline_for(level, entity_id), "crumbs": crumbs(level, row)})


# ---------------------------------------------------------------- compare

@bp.get("/compare")
@login_required
def compare_ads():
    ids = [i for i in (request.args.get("ids") or "").split(",") if i][:6]
    if len(ids) < 2:
        return api_error("Pick 2 to 6 ads to compare", 400)
    user = current_user()
    vis = visible_campaign_ids(user)
    rows = {r["id"]: r for r in db.query(
        """SELECT id, name, campaign_id, adset_id, status, effective_status, image_url, thumbnail_url, object_type, title, body
           FROM ads WHERE id = ANY(%s)""", (ids,)) if vis is None or r["campaign_id"] in vis}
    ids = [i for i in ids if i in rows]
    if len(ids) < 2:
        return api_error("Those ads aren't available to compare", 404)
    key, start, end = ads_api.window_from(request.args)
    prev = ranges.previous(start, end, key) if request.args.get("vs") == "prev" else None
    where, params = "ad_id = ANY(%s)", [ids]
    cur, qual = ads_api._metrics(where, params, start, end), ads_api._quality(where, params, start, end)
    if prev:
        cur_p, qual_p = ads_api._metrics(where, params, *prev), ads_api._quality(where, params, *prev)
    import insights
    reach_now = insights.unique_reach("ad", start, end)
    reach_before = insights.unique_reach("ad", *prev) if prev else None
    tags = {}
    for t in db.query("SELECT ad_id, dimension, value FROM ad_tags WHERE ad_id = ANY(%s)", (ids,)):
        tags.setdefault(t["ad_id"], {})[t["dimension"]] = t["value"]
    items = []
    for i in ids:
        item = {"id": i, **rows[i], "m": {**cur.get(i, {}), "qualified": qual.get(i, 0)}, "tags": tags.get(i, {}),
                "series": _series("ad_id = %s", [i], start, end)}
        if prev:
            item["prev"] = {**cur_p.get(i, {}), "qualified": qual_p.get(i, 0)}
        insights.apply_reach([item], reach_now, "m")
        if prev:
            insights.apply_reach([item], reach_before, "prev")
        items.append(item)
    shaped = compare.shape(items, targets.qualified(), targets.lead())
    out = {"range": {"key": key, "start": start.isoformat(), "end": end.isoformat(), "label": ranges.label(start, end)},
           "items": items, **shaped}
    if prev:
        out["prev_range"] = {"start": prev[0].isoformat(), "end": prev[1].isoformat(), "label": ranges.label(*prev)}
    return jsonify(out)


# ---------------------------------------------------------------- search

@bp.get("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    user = current_user()
    like = f"%{q}%"
    vis = visible_campaign_ids(user)
    cw, cp = ("TRUE", []) if vis is None else ("campaign_id = ANY(%s)", [vis])
    out = []
    for r in db.query(f"SELECT id, name, effective_status FROM campaigns WHERE name ILIKE %s AND {'TRUE' if vis is None else 'id = ANY(%s)'} "
                      "AND COALESCE(effective_status,'') <> 'DELETED' ORDER BY effective_status = 'ACTIVE' DESC, name LIMIT 6",
                      [like] + ([] if vis is None else [vis])):
        out.append({"type": "campaign", "id": r["id"], "title": r["name"], "sub": "Campaign", "href": f"/campaign.html?id={r['id']}"})
    for r in db.query(f"SELECT id, name FROM adsets WHERE name ILIKE %s AND {cw} AND COALESCE(effective_status,'') <> 'DELETED' "
                      "ORDER BY name LIMIT 6", [like] + cp):
        out.append({"type": "adset", "id": r["id"], "title": r["name"], "sub": "Ad set", "href": f"/adset.html?id={r['id']}"})
    for r in db.query(f"""SELECT a.id, a.name, s.name AS adset_name FROM ads a LEFT JOIN adsets s ON s.id = a.adset_id
                          WHERE a.name ILIKE %s AND {cw.replace('campaign_id', 'a.campaign_id')} AND COALESCE(a.effective_status,'') <> 'DELETED'
                          ORDER BY a.effective_status = 'ACTIVE' DESC, a.name LIMIT 8""", [like] + cp):
        out.append({"type": "ad", "id": r["id"], "title": r["name"], "sub": f"Ad · {r['adset_name'] or ''}".rstrip(" ·"),
                    "href": f"/ad.html?id={r['id']}"})
    for r in db.query(f"""SELECT id, full_name, email, ad_name FROM leads WHERE NOT is_test AND {cw}
                          AND (full_name ILIKE %s OR email ILIKE %s OR phone ILIKE %s) ORDER BY created_time DESC LIMIT 6""",
                      cp + [like, like, like]):
        out.append({"type": "lead", "id": r["id"], "title": r["full_name"] or r["email"] or "Lead",
                    "sub": f"Lead · {r['ad_name'] or r['email'] or ''}".rstrip(" ·"), "href": f"/leads.html#lead={r['id']}"})
    return jsonify({"items": out[:20]})


# ---------------------------------------------------------------- saved views

def _view_row(v, user):
    return {**v, "mine": v["user_id"] == user["id"]}


@bp.get("/views")
@login_required
def list_views():
    user = current_user()
    page = request.args.get("page")
    rows = db.query("SELECT * FROM saved_views WHERE (user_id = %s OR shared) AND (%s::text IS NULL OR page = %s) "
                    "ORDER BY position, id", (user["id"], page, page))
    return jsonify({"views": [_view_row(v, user) for v in rows]})


def _view_fields(data, partial=False):
    out = {}
    if not partial or "name" in data:
        name = (data.get("name") or "").strip()[:60]
        if not name:
            return None, api_error("Give the view a name", 400, field="name")
        out["name"] = name
    if not partial or "page" in data:
        if data.get("page") not in VIEW_PAGES:
            return None, api_error("Unknown page", 400)
        out["page"] = data["page"]
    if not partial or "query" in data:
        out["query"] = str(data.get("query") or "").lstrip("?")[:1000]
    if "shared" in data:
        out["shared"] = bool(data["shared"])
    if "position" in data:
        try:
            out["position"] = int(data["position"])
        except (TypeError, ValueError):
            pass
    return out, None


@bp.post("/views")
@login_required
def create_view():
    user = current_user()
    fields, err = _view_fields(request.get_json(silent=True) or {})
    if err:
        return err
    if user["role"] == "client":
        fields["shared"] = False
    row = db.execute("INSERT INTO saved_views (user_id, page, name, query, shared) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                     (user["id"], fields["page"], fields["name"], fields["query"], fields.get("shared", False)), returning=True)
    return jsonify(_view_row(row, user)), 201


@bp.patch("/views/<int:view_id>")
@login_required
def update_view(view_id):
    user = current_user()
    fields, err = _view_fields(request.get_json(silent=True) or {}, partial=True)
    if err:
        return err
    if not fields:
        return api_error("Nothing to change", 400)
    sets = ", ".join(f"{k} = %s" for k in fields)
    row = db.execute(f"UPDATE saved_views SET {sets} WHERE id = %s AND user_id = %s RETURNING *",
                     list(fields.values()) + [view_id, user["id"]], returning=True)
    if not row:
        return api_error("Only the person who saved a view can change it", 404)
    return jsonify(_view_row(row, user))


@bp.delete("/views/<int:view_id>")
@login_required
def delete_view(view_id):
    user = current_user()
    row = db.execute("DELETE FROM saved_views WHERE id = %s AND user_id = %s RETURNING id", (view_id, user["id"]), returning=True)
    if not row:
        return api_error("Only the person who saved a view can remove it", 404)
    return jsonify({"ok": True})
