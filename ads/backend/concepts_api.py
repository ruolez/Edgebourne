"""Concept tags and results by concept (roadmap 5.1)."""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import concepts as c
import account_info
import db
from auth import current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("concepts", __name__, url_prefix="/api")

RANGES = {"7": 7, "14": 14, "30": 30, "90": 90}


def tags_for(ad_ids=None):
    rows = db.query("SELECT ad_id, dimension, value, source FROM ad_tags" + (" WHERE ad_id = ANY(%s)" if ad_ids is not None else ""),
                    (list(ad_ids),) if ad_ids is not None else None)
    out = {}
    for r in rows:
        out.setdefault(r["ad_id"], {})[r["dimension"]] = r["value"]
    return out


def save_tags(ad_id, changes, source):
    existing = tags_for([ad_id]).get(ad_id, {})
    up, down = c.merge(existing, changes, source)
    for dim, value, src in up:
        db.execute("""INSERT INTO ad_tags (ad_id, dimension, value, source) VALUES (%s, %s, %s, %s)
                      ON CONFLICT (ad_id, dimension) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source, updated_at = now()""",
                   (ad_id, dim, value, src))
    for dim in down:
        db.execute("DELETE FROM ad_tags WHERE ad_id = %s AND dimension = %s", (ad_id, dim))
    if up or down:
        log_activity("ad.tags", subject=ad_id, details={"set": {d: v for d, v, _ in up}, "removed": down, "source": source})
    return tags_for([ad_id]).get(ad_id, {})


def copy_tags(from_ad, to_ad):
    """A new ad started from another keeps its concept (marked copied, editable)."""
    db.execute("""INSERT INTO ad_tags (ad_id, dimension, value, source)
                  SELECT %s, dimension, value, 'copied' FROM ad_tags WHERE ad_id = %s ON CONFLICT DO NOTHING""", (to_ad, from_ad))


def known_values():
    out = {d: [] for d in c.DIMENSIONS}
    for r in db.query("SELECT dimension, value, COUNT(*) AS n FROM ad_tags GROUP BY 1, 2 ORDER BY 3 DESC, 2"):
        out[r["dimension"]].append(r["value"])
    return out


def _can_see(user, ad_id):
    row = db.query("SELECT campaign_id FROM ads WHERE id = %s", (ad_id,), one=True)
    ids = visible_campaign_ids(user)
    return row and (ids is None or row["campaign_id"] in ids)


@bp.get("/ads/ad/<ad_id>/tags")
@login_required
def get_tags(ad_id):
    if not _can_see(current_user(), ad_id):
        return api_error("Ad not found", 404)
    return jsonify({"tags": tags_for([ad_id]).get(ad_id, {}), "dimensions": c.DIMENSIONS, "order": list(c.DIMENSIONS), "known": known_values()})


@bp.put("/ads/ad/<ad_id>/tags")
@login_required
def put_tags(ad_id):
    if not _can_see(current_user(), ad_id):
        return api_error("Ad not found", 404)
    tags = save_tags(ad_id, (request.get_json(silent=True) or {}).get("tags") or {}, "manual")
    return jsonify({"tags": tags, "dimensions": c.DIMENSIONS, "order": list(c.DIMENSIONS), "known": known_values()})


@bp.get("/concepts")
@login_required
def by_concept():
    user = current_user()
    dim = request.args.get("by", "hook")
    if dim not in c.DIMENSIONS:
        return api_error("Unknown dimension", 400)
    days = RANGES.get(request.args.get("range", "30"), 30)
    end = account_info.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    ids = visible_campaign_ids(user)
    where, params = ("TRUE", []) if ids is None else ("a.campaign_id = ANY(%s)", [ids])
    ads = db.query(f"""SELECT a.id, a.name, COALESCE(SUM(d.spend_cents),0) AS spend_cents, COALESCE(SUM(d.impressions),0) AS impressions,
                              COALESCE(SUM(d.leads),0) AS leads, COALESCE(SUM(d.video_3s),0) AS video_3s, COALESCE(SUM(d.thruplays),0) AS thruplays,
                              COALESCE(SUM(d.impressions) FILTER (WHERE a.object_type = 'VIDEO' OR a.video_id IS NOT NULL),0) AS video_impressions
                       FROM ads a JOIN ad_daily d ON d.ad_id = a.id AND d.day BETWEEN %s AND %s
                       WHERE {where} GROUP BY a.id, a.name HAVING SUM(d.spend_cents) > 0""", [start, end] + params)
    q = {r["ad_id"]: int(r["n"]) for r in db.query(
        """SELECT ad_id, COUNT(*) AS n FROM leads WHERE NOT is_test AND status IN ('qualified', 'won')
           AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s GROUP BY ad_id""",
        (account_info.tz_name(), start, end))}
    rows = [{**{k: int(v) if k not in ("id", "name") else v for k, v in a.items()}, "qualified": q.get(a["id"], 0)} for a in ads]
    import targets
    target = targets.lead_own()  # none set: the groups' own average (see targets.py)
    tags = tags_for([r["id"] for r in rows])
    out = c.group(rows, tags, dim, target)
    names = {}
    for r in rows:
        names.setdefault((tags.get(r["id"]) or {}).get(dim) or c.UNTAGGED, []).append(r["name"])
    for g in out["groups"]:
        g["ad_names"] = sorted(names.get(g["value"], []))
    return jsonify({**out, "by": dim, "dimensions": c.DIMENSIONS, "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
                    "untagged_ads": len(names.get(c.UNTAGGED, []))})
