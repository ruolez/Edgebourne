"""Tracking health (admins): the dataset's events, sources, match quality, and the lead stages
this console has sent. Read from Meta every 6 hours by the worker, or on "Check now"."""
import json
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import crm_events
import db
import meta_client
import settings_store
import tracking as tr
from auth import admin_required
from util import api_error

bp = Blueprint("tracking", __name__, url_prefix="/api")

STALE_HOURS = 6
DAYS = 7


def read_meta(dataset):
    """Everything Meta says about the dataset. Quality is best effort: not every dataset has it."""
    since = str(int(time.time()) - DAYS * 86400)
    details = meta_client.get(dataset, fields="name,last_fired_time,server_last_fired_time,is_unavailable")
    events = tr.counts(meta_client.get(f"{dataset}/stats", aggregation="event", start_time=since))
    try:
        by_source = tr.sources(meta_client.get(f"{dataset}/stats", aggregation="event_source", start_time=since))
    except meta_client.MetaError:
        by_source = {"server": 0, "browser": 0}
    try:
        match = tr.quality(meta_client.get("dataset_quality", dataset_id=dataset,
                                           fields="web{event_name,event_match_quality},crm{event_name,event_match_quality}"))
    except meta_client.MetaError:
        match = []
    return {"details": details, "events": events, "sources": by_source, "match": match}


def refresh():
    dataset = settings_store.get("meta_dataset_id")
    if not dataset:
        data = {"dataset": None, "fetched_at": datetime.now(timezone.utc).isoformat()}
    else:
        data = {"dataset": dataset, **read_meta(dataset), "fetched_at": datetime.now(timezone.utc).isoformat()}
    settings_store.set("tracking_snapshot", json.dumps(data))
    return data


def refresh_if_stale():
    old = json.loads(settings_store.get("tracking_snapshot") or "{}")
    if old.get("fetched_at") and (datetime.now(timezone.utc) - datetime.fromisoformat(old["fetched_at"])).total_seconds() < STALE_HOURS * 3600:
        return old
    return refresh()


def view(data):
    import meta_extras_api
    return {**_view(data), "meta_quality": meta_extras_api.quality_view()}  # AM-E: Meta's match quality per event (the link)


def _view(data):
    crm = crm_events.summary()
    crm_on = settings_store.get("crm_send_enabled") == "1"
    stages = {crm_events.EVENT_NAMES.get(r["stage"], r["stage"]): int(r["n"]) for r in db.query(
        "SELECT stage, COUNT(*) AS n FROM crm_events WHERE status = 'sent' AND sent_at > now() - interval '7 days' GROUP BY stage")}
    if not data.get("dataset"):
        return {"dataset": None, "crm": crm, "crm_on": crm_on, "sent_by_stage": stages, "fetched_at": data.get("fetched_at"),
                "assessment": {"state": "not_set_up", "headline": "No dataset is chosen yet.",
                               "todo": ["Add the Dataset ID under Settings → Lead stages to Meta."]}}
    a = tr.assess(data["details"], data["events"], data["sources"], data["match"], crm, datetime.now(timezone.utc), crm_on)
    return {"dataset": data["dataset"], "name": data["details"].get("name"), "events": data["events"], "sources": data["sources"],
            "match": data["match"], "crm": crm, "crm_on": crm_on, "sent_by_stage": stages, "days": DAYS,
            "fetched_at": data["fetched_at"], "assessment": a}


@bp.get("/tracking")
@admin_required
def get_tracking():
    try:
        data = refresh() if request.args.get("fresh") else refresh_if_stale()
    except meta_client.MetaError as exc:
        data = json.loads(settings_store.get("tracking_snapshot") or "{}")
        if not data.get("dataset"):
            return api_error(f"Meta didn't answer: {exc}", 400)
    return jsonify(view(data))
