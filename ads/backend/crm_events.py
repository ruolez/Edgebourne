"""Lead stages to Meta (Conversions API for CRM).

A stage change queues one row per stage in crm_events; the background worker sends the
due rows to the dataset when Settings → Meta has "Send lead stages to Meta" on. Meta
learns which leads became clients and can later optimise for them. Payload per
developers.facebook.com/docs/marketing-api/conversions-api/conversion-leads-integration/payload-specification"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import db
import meta_client
import settings_store
from util import log_activity

log = logging.getLogger(__name__)

STAGES = ("new", "contacted", "qualified", "won", "lost")
FUNNEL = ("new", "contacted", "qualified", "won")
EVENT_NAMES = {"new": "Lead", "contacted": "Contacted", "qualified": "Qualified", "won": "Won", "lost": "Lost"}
SOURCE_NAME = "Edge Bourne Ads Console"
META_LEAD_ID = re.compile(r"^\d{15,17}$")
MAX_AGE = timedelta(days=7)
GIVE_UP_AFTER = timedelta(hours=24)
BACKOFF_MINUTES = (1, 5, 15, 60, 180, 360)
META_INVALID_PARAMETER = 100
BATCH = 50


def stages_to_send(stage, already_sent):
    """Meta wants every earlier funnel stage before a later one, and the initial lead first."""
    if stage == "lost":
        wanted = ["new", "lost"]
    elif stage in FUNNEL:
        wanted = list(FUNNEL[: FUNNEL.index(stage) + 1])
    else:
        return []
    if stage in already_sent:
        return []
    return [s for s in wanted if s not in already_sent]


def event_time_for(changed_at, lead_created):
    """Meta discards a stage dated at or before the lead itself."""
    return max(changed_at, lead_created + timedelta(seconds=1))


def build_event(meta_lead_id, stage, event_time):
    lead_id = str(meta_lead_id or "")
    if not META_LEAD_ID.match(lead_id):
        return None, f"No valid Meta lead id ({lead_id or 'missing'}); Meta can't match it"
    return {
        "event_name": EVENT_NAMES[stage],
        "event_time": int(event_time.timestamp()),
        "action_source": "system_generated",
        "user_data": {"lead_id": int(lead_id)},
        "custom_data": {"event_source": "crm", "lead_event_source": SOURCE_NAME},
    }, None


def too_old(event_time, now):
    return now - event_time > MAX_AGE


def retry_at(attempts, queued_at, now, code):
    """When to try again after the given number of failed attempts; None = give up."""
    if code == META_INVALID_PARAMETER or now - queued_at > GIVE_UP_AFTER:
        return None
    return now + timedelta(minutes=BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES)) - 1])


def enabled():
    return settings_store.get("crm_send_enabled") == "1" and bool(settings_store.get("meta_dataset_id"))


def enqueue(lead_id, stage, changed_at=None):
    """Queue the stage (and any earlier ones Meta hasn't had) for one lead. Test leads never go."""
    lead = db.query("SELECT meta_lead_id, created_time, is_test FROM leads WHERE id = %s", (lead_id,), one=True)
    if not lead or lead["is_test"]:
        return 0
    sent = {r["stage"] for r in db.query("SELECT stage FROM crm_events WHERE lead_id = %s", (lead_id,))}
    at = event_time_for(changed_at or datetime.now(timezone.utc), lead["created_time"])
    stages = stages_to_send(stage, sent)
    for s in stages:
        db.execute(
            """INSERT INTO crm_events (lead_id, meta_lead_id, stage, event_time)
               VALUES (%s, %s, %s, %s) ON CONFLICT (lead_id, stage) DO NOTHING""",
            (lead_id, lead["meta_lead_id"], s, at),
        )
    return len(stages)


def _post(events, test_code=None):
    data = {"data": json.dumps(events)}
    if test_code:
        data["test_event_code"] = test_code
    return meta_client.post(f"{settings_store.get('meta_dataset_id')}/events", data=data)


def _finish(row, status, error=None):
    db.execute("UPDATE crm_events SET status = %s, last_error = %s, sent_at = CASE WHEN %s = 'sent' THEN now() END "
               "WHERE id = %s", (status, error, status, row["id"]))


def process_pending(now=None):
    """Send what's due, oldest first. A lead whose earlier stage fails waits, so Meta
    never gets 'Won' before 'Lead'."""
    if not enabled():
        return 0
    now = now or datetime.now(timezone.utc)
    rows = db.query("""SELECT id, lead_id, meta_lead_id, stage, event_time, attempts, created_at,
                              next_attempt_at <= %s AS due
                       FROM crm_events WHERE status = 'pending' ORDER BY lead_id, id LIMIT %s""", (now, BATCH))
    blocked, sent = set(), 0
    for row in rows:
        if row["lead_id"] in blocked:
            continue
        payload, reason = build_event(row["meta_lead_id"], row["stage"], row["event_time"])
        if reason or too_old(row["event_time"], now):
            _finish(row, "skipped", reason or "Older than 7 days; Meta no longer accepts it")
            continue
        if not row["due"]:
            blocked.add(row["lead_id"])
            continue
        try:
            _post([payload])
        except meta_client.MetaError as exc:
            blocked.add(row["lead_id"])
            attempts = row["attempts"] + 1
            again = retry_at(attempts, row["created_at"], now, exc.code)
            if again is None:
                _finish(row, "failed", str(exc))
                log_activity("crm.failed", subject=str(row["lead_id"]), actor="system",
                             details={"stage": row["stage"], "error": str(exc)})
            else:
                db.execute("UPDATE crm_events SET attempts = %s, next_attempt_at = %s, last_error = %s WHERE id = %s",
                           (attempts, again, str(exc), row["id"]))
            continue
        _finish(row, "sent")
        sent += 1
    return sent


def send_test(code):
    """One event with Meta's test code, for Events Manager → Test events. Not stored."""
    lead = db.query("SELECT meta_lead_id, created_time FROM leads ORDER BY created_time DESC LIMIT 1", one=True)
    if not lead:
        raise meta_client.MetaError("No lead yet to test with; send one from Meta's lead ads testing tool first")
    payload, reason = build_event(lead["meta_lead_id"], "new",
                                  event_time_for(datetime.now(timezone.utc), lead["created_time"]))
    if reason:
        raise meta_client.MetaError(reason)
    return _post([payload], test_code=code)


def summary():
    rows = db.query("SELECT status, COUNT(*) AS n FROM crm_events GROUP BY status")
    counts = {r["status"]: r["n"] for r in rows}
    last = db.query("SELECT last_error FROM crm_events WHERE last_error IS NOT NULL AND status IN ('pending','failed') "
                    "ORDER BY id DESC LIMIT 1", one=True)
    return {s: counts.get(s, 0) for s in ("pending", "sent", "failed", "skipped")} | {
        "last_error": last and last["last_error"]}


def for_lead(lead_id):
    return db.query("""SELECT stage, status, event_time, sent_at, last_error, attempts FROM crm_events
                       WHERE lead_id = %s ORDER BY id""", (lead_id,))
