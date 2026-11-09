"""The Refresh button on every screen: pull the latest from Meta, then the page reloads its data.

One quick pass: ads and statuses, the last few days of results, today's spend and any form
leads the webhook missed. Throttled so repeated taps (or several people) don't hammer Meta.
The background worker runs the same pass by itself every few minutes (Settings, Automatic
refresh); open pages notice the newer data and reload it.
"""
import logging
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify

import db
import insights
import jobs
import leads
import meta_client
import settings_store
from auth import current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

log = logging.getLogger(__name__)
bp = Blueprint("refresh", __name__, url_prefix="/api/refresh")

MIN_GAP_SECONDS = 60
DAYS = 3
LEAD_DAYS = 7
LOCK_KEY = 7_204_311
AUTO_CHOICES = (5, 10, 15, 30, 60)
DEFAULT_AUTO_MINUTES = 15
AUTO_RETRY_SECONDS = 300


def refresh_due(last, now):
    try:
        last = float(last)
    except (TypeError, ValueError):
        return True
    return 0 <= now - last and now - last >= MIN_GAP_SECONDS


def auto_minutes(value):
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_AUTO_MINUTES
    return minutes if minutes in AUTO_CHOICES else DEFAULT_AUTO_MINUTES


def auto_due(last_pull, last_try, now, minutes):
    """Whether the worker should pull now: the interval has passed since the last pull (by
    anyone), and a failed automatic try is at least AUTO_RETRY_SECONDS old."""
    if last_try is not None and now - last_try < AUTO_RETRY_SECONDS:
        return False
    try:
        last_pull = float(last_pull)
    except (TypeError, ValueError):
        return True
    return now < last_pull or now - last_pull >= minutes * 60


def pull_latest(conn):
    """The quick pass. Returns None when another pass holds the lock; MetaError propagates."""
    if not jobs._locked(conn, LOCK_KEY):
        return None
    try:
        result = insights.sync_all(days=DAYS)
        settings_store.set("today_snapshot", None)
        new_leads = 0
        try:
            new_leads = leads.backfill(days=LEAD_DAYS)
        except meta_client.MetaError as exc:
            log.warning("refresh: lead catch-up failed: %s", exc)
        settings_store.set("last_refresh_at", str(time.time()))
        return {"ads": result.get("ads"), "new_leads": new_leads}
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def last_updated(refresh_at, sync_iso):
    """Epoch seconds of the newest of a manual refresh and the hourly sync, or None."""
    times = []
    try:
        times.append(float(refresh_at))
    except (TypeError, ValueError):
        pass
    if sync_iso:
        try:
            times.append(datetime.fromisoformat(sync_iso.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    return max(times) if times else None


def _status():
    return {"updated_at": last_updated(settings_store.get("last_refresh_at"), settings_store.get("last_performance_sync")),
            "server_now": time.time(),
            "auto_minutes": auto_minutes(settings_store.get("auto_refresh_minutes"))}


@bp.get("")
@login_required
def status():
    """What every page's frame needs: freshness, the new-lead badge, Claude's badge, the spending limit."""
    from performance_api import cap_snapshot
    user = current_user()
    ids = visible_campaign_ids(user)
    lw, lp = ("TRUE", []) if ids is None else ("campaign_id = ANY(%s)", [ids])
    out = {**_status(),
           "new_leads": int(db.query(f"SELECT COUNT(*) AS n FROM leads WHERE status = 'new' AND NOT is_test AND {lw}", lp, one=True)["n"])}
    if user["role"] == "admin":
        out["proposals"] = int(db.query("SELECT COUNT(*) AS n FROM desk_proposals WHERE status = 'pending'", one=True)["n"])
        out["cap"] = cap_snapshot()
    return jsonify(out)


@bp.post("")
@login_required
def refresh():
    if not settings_store.get("meta_system_token"):
        return api_error("Meta isn't connected yet. An admin can connect it in Settings.", 400)
    now = time.time()
    if not refresh_due(settings_store.get("last_refresh_at"), now):
        return jsonify({**_status(), "ran": False})
    try:
        pulled = pull_latest(db.get_db())
    except meta_client.MetaError as exc:
        return api_error(f"Meta didn't answer: {exc}", 502)
    if pulled is None:
        return jsonify({**_status(), "ran": False, "busy": True})
    user = current_user()
    log_activity("refresh", details={**pulled, "by": user["id"]})
    return jsonify({**_status(), "ran": True, "new_leads": pulled["new_leads"]})
