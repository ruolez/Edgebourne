"""Swipe file and watched Pages (admins), plus the Mac's side (agent): list watched Pages,
save ads it found."""
import json

from flask import Blueprint, jsonify, request

import db
import swipes as sw
from auth import admin_required, current_user
from desk_api import agent_required
from experiments import account_today
from util import api_error, log_activity

bp = Blueprint("swipes", __name__, url_prefix="/api")

COLS = "id, library_id, page_name, page_id, body, title, cta, media_url, started_on, stopped_on, platforms, notes, tags, source, first_saved_at, last_seen_at"


def upsert(fields, source, user_id=None):
    """Insert, or refresh a known Ad Library id (its dates and text may have moved on). Returns (id, new)."""
    if fields["library_id"]:
        old = db.query("SELECT id, notes, tags FROM swipes WHERE library_id = %s", (fields["library_id"],), one=True)
        if old:
            db.execute("""UPDATE swipes SET page_name = %s, page_id = COALESCE(%s, page_id), body = COALESCE(%s, body), title = COALESCE(%s, title),
                          cta = COALESCE(%s, cta), media_url = COALESCE(%s, media_url), started_on = COALESCE(%s, started_on), stopped_on = %s,
                          platforms = CASE WHEN %s::jsonb = '[]'::jsonb THEN platforms ELSE %s::jsonb END,
                          notes = COALESCE(notes, %s), tags = %s::jsonb || tags, last_seen_at = now() WHERE id = %s""",
                       (fields["page_name"], fields["page_id"], fields["body"], fields["title"], fields["cta"], fields["media_url"],
                        fields["started_on"], fields["stopped_on"], json.dumps(fields["platforms"]), json.dumps(fields["platforms"]),
                        fields["notes"], json.dumps(fields["tags"]), old["id"]))
            return old["id"], False
    row = db.execute(f"""INSERT INTO swipes (library_id, page_name, page_id, body, title, cta, media_url, started_on, stopped_on, platforms,
                                             notes, tags, source, saved_by)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (fields["library_id"], fields["page_name"], fields["page_id"], fields["body"], fields["title"], fields["cta"],
                      fields["media_url"], fields["started_on"], fields["stopped_on"], json.dumps(fields["platforms"]), fields["notes"],
                      json.dumps(fields["tags"]), source, user_id), returning=True)
    return row["id"], True


def listing():
    today = account_today()
    return [sw.view(r, today) for r in db.query(f"SELECT {COLS} FROM swipes ORDER BY last_seen_at DESC, id DESC")]


def listing_of(ids):
    today = account_today()
    return [sw.view(r, today) for r in db.query(f"SELECT {COLS} FROM swipes WHERE id = ANY(%s)", (ids,))]


@bp.get("/swipes")
@admin_required
def get_swipes():
    pages = db.query("SELECT id, name, page_id, search_terms, notes, last_checked_at FROM watched_pages ORDER BY name")
    return jsonify({"items": listing(), "watched": [{**p, "last_checked_at": p["last_checked_at"].isoformat() if p["last_checked_at"] else None} for p in pages],
                    "long_running_days": sw.LONG_RUNNING_DAYS})


@bp.post("/swipes")
@admin_required
def add_swipe():
    fields, err = sw.clean(request.get_json(silent=True) or {})
    if err:
        return api_error(err, 400)
    sid, new = upsert(fields, "manual", current_user()["id"])
    log_activity("swipe.saved", subject=str(sid), details={"page": fields["page_name"], "new": new})
    return jsonify({"id": sid, "new": new, "items": listing()}), 201 if new else 200


@bp.patch("/swipes/<int:sid>")
@admin_required
def edit_swipe(sid):
    data = request.get_json(silent=True) or {}
    if not db.query("SELECT 1 FROM swipes WHERE id = %s", (sid,), one=True):
        return api_error("Not found", 404)
    if "notes" in data:
        db.execute("UPDATE swipes SET notes = %s WHERE id = %s", (str(data["notes"] or "").strip()[:2000] or None, sid))
    if "tags" in data and isinstance(data["tags"], dict):
        tags = {k: " ".join(str(v).split())[:80] for k, v in data["tags"].items() if k in ("hook", "angle", "format", "offer") and str(v or "").strip()}
        db.execute("UPDATE swipes SET tags = %s WHERE id = %s", (json.dumps(tags), sid))
    return jsonify({"items": listing()})


@bp.delete("/swipes/<int:sid>")
@admin_required
def remove_swipe(sid):
    """Only removes it from this dashboard's swipe file; nothing on Meta."""
    db.execute("DELETE FROM swipes WHERE id = %s", (sid,))
    log_activity("swipe.removed", subject=str(sid))
    return jsonify({"items": listing()})


@bp.post("/watched")
@admin_required
def add_watched():
    data = request.get_json(silent=True) or {}
    name = " ".join(str(data.get("name") or "").split())[:200]
    if not name:
        return api_error("Give the Page's name", 400, field="name")
    page_id = str(data.get("page_id") or "").strip()
    if page_id and not page_id.isdigit():
        return api_error("A Page id is only digits (leave it empty if you don't know it)", 400, field="page_id")
    db.execute("INSERT INTO watched_pages (name, page_id, search_terms, notes) VALUES (%s, %s, %s, %s)",
               (name, page_id or None, str(data.get("search_terms") or "").strip()[:300] or None, str(data.get("notes") or "").strip()[:1000] or None))
    log_activity("watch.added", details={"name": name})
    return get_swipes()


@bp.delete("/watched/<int:wid>")
@admin_required
def remove_watched(wid):
    db.execute("DELETE FROM watched_pages WHERE id = %s", (wid,))
    return get_swipes()


# ---------------------------------------------------------------- the Mac (Claude)

@bp.get("/agent/watched")
@agent_required
def agent_watched():
    pages = db.query("SELECT id, name, page_id, search_terms, notes, last_checked_at FROM watched_pages ORDER BY name")
    known = {r["library_id"] for r in db.query("SELECT library_id FROM swipes WHERE library_id IS NOT NULL")}
    return jsonify({"pages": [{**p, "last_checked_at": p["last_checked_at"].isoformat() if p["last_checked_at"] else None} for p in pages],
                    "known_library_ids": sorted(known), "long_running_days": sw.LONG_RUNNING_DAYS})


@bp.post("/agent/swipes")
@agent_required
def agent_swipes():
    body = request.get_json(silent=True) or {}
    items = body.get("swipes")
    if not isinstance(items, list) or not items:
        return api_error("Send {\"swipes\": [...]}", 400)
    added, refreshed, skipped, saved = 0, 0, [], []
    for raw in items[:100]:
        fields, err = sw.clean(raw if isinstance(raw, dict) else {})
        if err:
            skipped.append(err)
            continue
        sid, new = upsert(fields, "claude")
        saved.append(sid)
        added += new
        refreshed += not new
    if isinstance(body.get("task_id"), int) and saved:
        # So the run's answer can show the ads it found.
        db.execute("UPDATE desk_tasks SET swipe_ids = ARRAY(SELECT DISTINCT unnest(swipe_ids || %s::int[])) WHERE id = %s", (saved, body["task_id"]))
    checked = {str(r.get("page_name") or "").strip().lower() for r in items if isinstance(r, dict)}
    for p in db.query("SELECT id, name FROM watched_pages"):
        if p["name"].lower() in checked:
            db.execute("UPDATE watched_pages SET last_checked_at = now() WHERE id = %s", (p["id"],))
    log_activity("swipe.agent", details={"added": added, "refreshed": refreshed, "skipped": len(skipped)})
    return jsonify({"added": added, "refreshed": refreshed, "skipped": skipped})
