"""Status history: what Meta said about each campaign, ad set and ad, and when it changed.

Sync used to overwrite status, review notes and issues on every pull. Now each upsert returns the row
as it was (atomically, under a row lock), the two are reduced to comparable snapshots, and every
difference is stored in status_events. The pure part (snapshots, diff, plain words) is unit tested."""
import json
from datetime import datetime, timedelta, timezone

import db

LEVELS = ("campaign", "adset", "ad")
TABLE = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
FIELDS = {
    "ad": ("effective_status", "configured_status", "review", "issues"),
    "adset": ("effective_status", "configured_status", "issues", "learning"),
    "campaign": ("effective_status", "configured_status", "issues"),
}
PREV_COLS = {
    "ad": "status, configured_status, effective_status, review_feedback, issues, creative_id, title, body",
    "adset": "status, configured_status, effective_status, learning_stage, learning, issues",
    "campaign": "status, configured_status, effective_status, issues",
}
NEW_WINDOW = timedelta(hours=48)       # first seen within 48 h of creation = a new entity, else backfill
CONSOLE_WINDOW = timedelta(minutes=10)  # a console write this recent explains a status change
REVIEW_STATES = ("IN_PROCESS", "PENDING_REVIEW")
OWN_STATES = ("ACTIVE", "PAUSED", "ARCHIVED", "DELETED")


# ---------------------------------------------------------------- pure

def review_summary(feedback):
    """Meta's ad_review_feedback as one comparable line of reason keys ('A; B; instagram: C')."""
    if not feedback:
        return None
    if isinstance(feedback, str):
        try:
            feedback = json.loads(feedback)
        except ValueError:
            return feedback
    keys = sorted((feedback.get("global") or {}).keys())
    for placement, reasons in sorted((feedback.get("placement_specific") or {}).items()):
        keys += [f"{placement}: {k}" for k in sorted((reasons or {}).keys())]
    return "; ".join(keys) or None


def issues_summary(issues):
    if not issues:
        return None
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except ValueError:
            return issues
    if isinstance(issues, dict):
        issues = [issues]
    parts = sorted({(i.get("error_summary") or i.get("error_message") or str(i.get("error_code") or "")).strip()
                    for i in issues if isinstance(i, dict)} - {""})
    return "; ".join(parts) or None


def snapshot(level, meta):
    """Comparable state of an entity as Meta returned it."""
    snap = {"effective_status": meta.get("effective_status"),
            "configured_status": meta.get("configured_status") or meta.get("status"),
            "issues": issues_summary(meta.get("issues_info"))}
    if level == "ad":
        snap["review"] = review_summary(meta.get("ad_review_feedback"))
    if level == "adset":
        snap["learning"] = (meta.get("learning_stage_info") or {}).get("status")
    return {f: snap.get(f) for f in FIELDS[level]}


def stored_snapshot(level, row):
    """Comparable state of an entity as the console stored it (columns added later fall back to the old ones)."""
    snap = {"effective_status": row.get("effective_status"),
            "configured_status": row.get("configured_status") or row.get("status"),
            "issues": issues_summary(row.get("issues"))}
    if level == "ad":
        snap["review"] = review_summary(row.get("review_feedback"))
    if level == "adset":
        snap["learning"] = (row.get("learning") or {}).get("status") or row.get("learning_stage")
    return {f: snap.get(f) for f in FIELDS[level]}


def parse_time(value):
    if value is None or isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(value, fmt)
        except (TypeError, ValueError):
            pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def diff(level, before, after, now, created_time):
    """Events between two snapshots. before=None is the first time the console sees the entity."""
    if before is None:
        created = parse_time(created_time)
        if created is not None and now - created < NEW_WINDOW:
            return [{"field": "created", "old": None, "new": after.get("effective_status"), "backfill": False}]
        return [{"field": "effective_status", "old": None, "new": after.get("effective_status"), "backfill": True}]
    return [{"field": f, "old": before.get(f), "new": after.get(f), "backfill": False}
            for f in FIELDS[level] if before.get(f) != after.get(f)]


def explained_by_console(entity_id, ev, changes, now):
    """The meta_changes id of a recent status write from this console that explains the event, else None."""
    if ev["field"] not in ("configured_status", "effective_status") or ev["new"] not in OWN_STATES:
        return None
    if ev["field"] == "effective_status" and ev.get("old") in REVIEW_STATES + ("PREAPPROVED", "DISAPPROVED", "WITH_ISSUES"):
        return None  # leaving review or a rejection is Meta's doing, even right after our own switch
    for ch in sorted(changes, key=lambda c: c["created_at"], reverse=True):
        if (ch["entity_id"] == entity_id and ch["action"] == "status" and ch.get("ok")
                and ch.get("new_value") == ev["new"] and now - ch["created_at"] <= CONSOLE_WINDOW):
            return ch["id"]
    return None


STATE_WORDS = {"ACTIVE": "delivering", "IN_PROCESS": "in review", "PENDING_REVIEW": "in review", "PAUSED": "off",
               "PREAPPROVED": "approved", "DISAPPROVED": "rejected", "WITH_ISSUES": "has issues",
               "CAMPAIGN_PAUSED": "campaign off", "ADSET_PAUSED": "ad set off", "ARCHIVED": "archived",
               "DELETED": "deleted", "PENDING_BILLING_INFO": "waiting for billing details"}


def reason_words(summary):
    """'PERSONAL_ATTRIBUTES; instagram: PERSONAL_ATTRIBUTES' -> 'Personal attributes (also on Instagram)'."""
    seen, out = set(), []
    for part in (summary or "").split("; "):
        place, _, key = part.rpartition(": ")
        words = key.replace("_", " ").strip().capitalize()
        if words in seen:
            if place:
                out[[o.split(" (")[0] for o in out].index(words)] += f" (also on {place.title()})"
            continue
        seen.add(words)
        out.append(words + (f" ({place.title()})" if place else ""))
    return "; ".join(out)


def headline(ev):
    """One line of plain words for a timeline entry."""
    field, old, new = ev["field"], ev.get("old"), ev.get("new")
    if field == "created":
        return "Created · " + STATE_WORDS.get(new, (new or "").lower())
    if ev.get("backfill"):
        return "First seen · " + STATE_WORDS.get(new, (new or "").lower())
    if field == "effective_status":
        if new == "ACTIVE":
            if old in REVIEW_STATES or old == "PREAPPROVED":
                return "Approved · delivering"
            if old in ("DISAPPROVED", "WITH_ISSUES"):
                return "Fixed · delivering again"
            return "Delivering again" if old in ("PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED") else "Delivering"
        return {"DISAPPROVED": "Rejected by Meta", "WITH_ISSUES": "Has issues", "PAUSED": "Turned off",
                "IN_PROCESS": "Sent to review", "PENDING_REVIEW": "Sent to review",
                "PREAPPROVED": "Approved · waiting to start", "CAMPAIGN_PAUSED": "Stopped: campaign is off",
                "ADSET_PAUSED": "Stopped: ad set is off", "ARCHIVED": "Archived", "DELETED": "Deleted",
                "PENDING_BILLING_INFO": "Waiting for billing details"}.get(new, (new or "").title())
    if field == "configured_status":
        return {"ACTIVE": "Switched on", "PAUSED": "Switched off", "ARCHIVED": "Archived",
                "DELETED": "Deleted"}.get(new, f"Set to {new}")
    if field == "review":
        return "Meta's review notes cleared" if not new else f"Meta's reason: {reason_words(new)}"
    if field == "issues":
        return "Issues cleared" if not new else f"Issue: {new}"
    if field == "learning":
        return {"LEARNING": "Learning started", "SUCCESS": "Finished learning",
                "FAIL": "Learning limited"}.get(new, f"Learning: {new}")
    return f"{field}: {old} → {new}"


# ---------------------------------------------------------------- database

# Ends each sync upsert (its last parameter is when the read from Meta started): a row this console wrote
# to Meta after that keeps what the console stored. Meta's answer may predate the write, and putting the old
# status or creative back would read as a change made outside the console (audit A3-67).
UNLESS_CONSOLE_WROTE = """WHERE NOT EXISTS (SELECT 1 FROM meta_changes m WHERE m.entity_id = {table}.id AND m.ok
                                         AND m.created_at > %s)
               RETURNING id"""


def upsert_tracked(level, entity_id, upsert_sql, params):
    """Run the INSERT … ON CONFLICT upsert for one entity: (the row as it was before or None when new,
    whether it was written). The row lock makes a webhook refetch, a poll and a manual refresh see each
    change once."""
    prev, wrote = db.run_in_transaction([
        (f"SELECT {PREV_COLS[level]} FROM {TABLE[level]} WHERE id = %s FOR UPDATE", (entity_id,)),
        (upsert_sql, params)])
    return (prev[0] if prev else None), bool(wrote)


def track(level, meta, prev, source, now=None):
    """Compare the stored row with what Meta returned and record the differences."""
    now = now or datetime.now(timezone.utc)
    before = stored_snapshot(level, prev) if prev else None
    events = diff(level, before, snapshot(level, meta), now, meta.get("created_time"))
    raw = {"review": meta.get("ad_review_feedback"), "issues": meta.get("issues_info"),
           "learning": meta.get("learning_stage_info")}
    for ev in events:
        if raw.get(ev["field"]):
            ev["detail"] = raw[ev["field"]]
    return record(level, meta, events, source, now)


def record(level, entity, events, source, now=None, detail=None):
    if not events:
        return []
    now = now or datetime.now(timezone.utc)
    changes = db.query(
        """SELECT id, entity_id, action, new_value, ok, created_at FROM meta_changes
           WHERE entity_id = %s AND action = 'status' AND created_at > now() - interval '15 minutes'""",
        (entity["id"],))
    out = []
    for ev in events:
        src, change_id = ("backfill", None) if ev.get("backfill") else (source, None)
        if src != "backfill":
            change_id = explained_by_console(entity["id"], ev, changes, now)
            if change_id:
                src = "console"
        row = db.execute(
            """INSERT INTO status_events (level, entity_id, entity_name, campaign_id, adset_id, field,
                                          old_value, new_value, source, detail, change_id, meta_time)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, at""",
            (level, entity["id"], entity.get("name"), entity.get("campaign_id") if level != "campaign" else entity["id"],
             entity.get("adset_id") if level == "ad" else (entity["id"] if level == "adset" else None),
             ev["field"], ev.get("old"), ev.get("new"), src,
             json.dumps(ev.get("detail") or detail) if (ev.get("detail") or detail) else None, change_id,
             parse_time(entity.get("updated_time"))),
            returning=True)
        out.append({**ev, "id": row["id"], "source": src, "level": level, "entity_id": entity["id"],
                    "entity_name": entity.get("name"), "campaign_id": entity.get("campaign_id"), "change_id": change_id})
    alert_on(level, entity, out, now)
    return out


def alert_on(level, entity, events, now):
    """Raise the alerts these changes deserve (approved, rejected, issues, learning limited, changed outside)."""
    import account_info
    import alerts
    try:
        today = now.astimezone(account_info.tz()).date()
        found = transitions(level, entity, events, alerts.saved_rules(), now, today)
        if found:
            alerts.raise_found(found)
    except Exception as exc:  # an alert must never break a sync
        import logging
        logging.getLogger(__name__).warning("status alert failed for %s: %s", entity.get("id"), exc)


def missing_verdicts(ids, found):
    """What to store for entities Meta's listing left out, from reading them by id: archived stays archived,
    deleted or no longer there is deleted, anything else still exists (the listing missed it) and is left alone."""
    out = {}
    for i in ids:
        status = (found.get(i) or {}).get("effective_status")
        if i not in found or status == "DELETED":
            out[i] = "DELETED"
        elif status == "ARCHIVED":
            out[i] = "ARCHIVED"
    return out


def mark_missing(level, seen, source="poll", listed_at=None):
    """Entities Meta no longer lists are kept, marked archived or deleted as Meta says when asked by id;
    record it. Rows another sync stored after this listing was read are left alone (audit A3-30)."""
    if not seen:
        return []
    table = TABLE[level]
    still = (f"NOT (id = ANY(%s)) AND COALESCE(status, '') <> 'ARCHIVED' AND COALESCE(effective_status, '') NOT IN "
             f"('DELETED', 'ARCHIVED') AND (%s::timestamptz IS NULL OR synced_at < %s)")
    ids = [r["id"] for r in db.query(f"SELECT id FROM {table} WHERE {still}", (seen, listed_at, listed_at))]
    if not ids:
        return []
    import insights
    import meta_client
    try:
        found = insights._fetch_many(ids, "id,status,effective_status", "id,status,effective_status")
    except meta_client.MetaError as exc:
        import logging
        logging.getLogger(__name__).info("missing %ss not checked with Meta: %s", level, exc)
        return []
    verdicts = missing_verdicts(ids, found)
    out = []
    for new in ("ARCHIVED", "DELETED"):
        mine = [i for i, v in verdicts.items() if v == new]
        if not mine:
            continue
        gone = db.query(
            f"""WITH gone AS (SELECT id, name, effective_status FROM {table} WHERE id = ANY(%s) AND {still} FOR UPDATE)
                UPDATE {table} t SET effective_status = %s, status = %s FROM gone
                WHERE t.id = gone.id RETURNING t.*, gone.effective_status AS was""",
            (mine, seen, listed_at, listed_at, new, new))
        for row in gone:
            out += record(level, row, [{"field": "effective_status", "old": row["was"], "new": new, "backfill": False}], source)
    return out


def timeline(level, entity_id, limit=100):
    rows = db.query(
        """SELECT e.id, e.level, e.entity_id, e.field, e.old_value, e.new_value, e.source, e.detail, e.at,
                  e.change_id, u.name AS by_name
           FROM status_events e LEFT JOIN meta_changes c ON c.id = e.change_id LEFT JOIN users u ON u.id = c.user_id
           WHERE e.entity_id = %s ORDER BY e.at DESC, e.id DESC LIMIT %s""", (entity_id, limit))
    for r in rows:
        r["headline"] = headline({"field": r["field"], "old": r["old_value"], "new": r["new_value"],
                                  "backfill": r["source"] == "backfill"})
    return rows


# ---------------------------------------------------------------- alerts from changes (pure)

LEVEL_WORDS = {"campaign": "Campaign", "adset": "Ad set", "ad": "Ad"}


def _href(level, entity):
    return f"/ad.html?id={entity['id']}" if level == "ad" else "/ads.html"


def _reason_lines(entity, events):
    review = next((e.get("new") for e in events if e["field"] == "review" and e.get("new")), None)
    feedback = entity.get("ad_review_feedback") or {}
    texts = list((feedback.get("global") or {}).values())
    for reasons in (feedback.get("placement_specific") or {}).values():
        texts += [t for t in (reasons or {}).values() if t not in texts]
    if not review:
        review = review_summary(feedback)
    line = f"Reason: {reason_words(review)}." if review else "Open the ad to see Meta's reason."
    if texts and texts[0]:
        line += " " + texts[0].strip()
    return [line, "Fix the words or picture and Meta reviews it again, or ask Claude for a fixed version."]


def transitions(level, entity, events, rules, now, today):
    """Alert dicts (same shape as alerts.evaluate) for changes worth telling someone about."""
    on = lambda rule: (rules.get(rule) or {}).get("on", True)
    name, eid = entity.get("name") or entity["id"], entity["id"]
    camp = entity["id"] if level == "campaign" else entity.get("campaign_id")
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    out = []

    def add(rule, key, alert_level, title, lines, kind="event", resolved=True):
        out.append({"rule": rule, "key": key, "level": alert_level, "title": title, "lines": lines, "entity_id": eid,
                    "campaign_id": camp, "href": _href(level, entity), "kind": kind, "resolved": resolved})

    for ev in events:
        if ev.get("backfill") or ev.get("source") == "backfill":
            continue
        field, old, new = ev["field"], ev.get("old"), ev.get("new")
        if level == "ad" and on("ad_approved") and new in ("ACTIVE", "PREAPPROVED") and (
                (field == "effective_status" and old in REVIEW_STATES) or field == "created"):
            add("ad_approved", f"ad_approved:{eid}:{stamp}", "ok", f"Meta approved “{name}”",
                ["It's delivering now." if new == "ACTIVE" else "It starts on its schedule."])
        elif level == "ad" and field in ("effective_status", "created") and new == "DISAPPROVED" and on("ad_rejected"):
            add("ad_rejected", f"ad_rejected:{eid}:{today.isoformat()}", "bad", f"Meta rejected “{name}”",
                _reason_lines(entity, events), kind="condition", resolved=False)
        elif field == "effective_status" and new == "WITH_ISSUES" and on("ad_rejected"):
            issue = issues_summary(entity.get("issues_info")) or "Meta reports a problem."
            if level == "ad":
                add("ad_rejected", f"ad_rejected:{eid}:{today.isoformat()}", "bad", f"“{name}” has a problem on Meta",
                    [issue, "It doesn't deliver until this is fixed."], kind="condition", resolved=False)
            else:
                add("ad_rejected", f"issues:{eid}:{today.isoformat()}", "bad",
                    f"{LEVEL_WORDS[level]} “{name}” has a problem on Meta", [issue, "Its ads don't deliver until this is fixed."])
        elif level == "adset" and field == "learning" and new == "FAIL" and on("learning_limited"):
            got = (entity.get("learning_stage_info") or {}).get("conversions")
            add("learning_limited", f"learning_limited:{eid}:{today.isoformat()}", "warn", f"Ad set “{name}” is learning limited",
                [f"{got if got is not None else 'Too few'} results since its last big edit; Meta wants about 50 a week to finish learning.",
                 "Usually: fewer ad sets, a bigger budget or a broader audience. Don't edit it often."])
        elif field == "configured_status" and ev.get("source") in ("poll", "webhook") and on("changed_outside") and old:
            word = {"ACTIVE": "on", "PAUSED": "off", "ARCHIVED": "archived", "DELETED": "deleted"}.get(new, (new or "").lower())
            verb = "switched " + word if word in ("on", "off") else word
            add("changed_outside", f"changed_outside:{eid}:{stamp}", "info",
                f"{LEVEL_WORDS[level]} “{name}” was {verb} outside this console",
                ["Someone changed it in Ads Manager (or through Claude on the Mac). Nothing to do if that was you."])
    return out


def process_webhooks(limit=200):
    """Worker job: Meta's ad-account webhooks say something changed; read those objects again."""
    import insights
    import settings_store
    import webhooks
    rows = db.query("SELECT id, payload FROM webhook_events WHERE kind = 'ad_account' AND processed_at IS NULL "
                    "ORDER BY id LIMIT %s", (limit,))
    if not rows:
        return 0
    plan = webhooks.refetch_plan([r["payload"] for r in rows])
    error = None
    for level, ids in plan.items():
        try:
            insights.sync_entities(level, ids, "webhook")
        except Exception as exc:
            error = str(exc)[:500]
    ids = [r["id"] for r in rows]
    if error:
        # Retried on the next pass; after an hour the poll has caught up anyway, so stop retrying.
        db.execute("UPDATE webhook_events SET error = %s, processed_at = CASE WHEN received_at < now() - interval '1 hour' "
                   "THEN now() END WHERE id = ANY(%s)", (error, ids))
        return 0
    db.execute("UPDATE webhook_events SET processed_at = now(), error = NULL WHERE id = ANY(%s)", (ids,))
    settings_store.set("meta_status_webhook_at", datetime.now(timezone.utc).isoformat())
    return len(ids)
