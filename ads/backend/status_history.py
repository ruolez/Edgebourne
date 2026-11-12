"""Status history: what Meta said about each campaign, ad set and ad, and when it changed.

Sync used to overwrite status, review notes and issues on every pull. Now each upsert returns the row
as it was (atomically, under a row lock), the two are reduced to comparable snapshots, and every
difference is stored in status_events. The pure part (snapshots, diff, plain words) is unit tested."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import db
import links
import money_rules
import words

LEVELS = ("campaign", "adset", "ad")
TABLE = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
FIELDS = {
    "ad": ("effective_status", "configured_status", "review", "issues"),
    "adset": ("effective_status", "configured_status", "issues", "learning"),
    "campaign": ("effective_status", "configured_status", "issues"),
}
# Budget, bid, dates and audience (D2): compared once the console has stored them from a full read
# (setup_seen_at), so the first sync after the update records nothing.
SETUP = {
    "campaign": ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "start_time", "end_time"),
    "adset": ("daily_budget", "lifetime_budget", "bid_strategy", "bid_amount", "start_time", "end_time", "targeting"),
}
META_KEY = {"end_time": {"campaign": "stop_time", "adset": "end_time"}}  # everything else has the same name
MONEY_FIELDS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "bid_amount")
CENTS_FIELDS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_amount")
TIME_FIELDS = ("start_time", "end_time")
STORED_COL = {"daily_budget": "daily_budget_cents", "lifetime_budget": "lifetime_budget_cents", "spend_cap": "spend_cap_cents",
              "bid_strategy": "bid_strategy", "bid_amount": "bid_amount_cents", "start_time": "start_time",
              "end_time": {"campaign": "stop_time", "adset": "end_time"}, "targeting": "targeting_fp"}
# What counts as changed outside the console when Meta reports it: the switch and every setup field (W2's
# "What we did", D3's windows).
OUTSIDE_FIELDS = ("configured_status",) + tuple(dict.fromkeys(SETUP["campaign"] + SETUP["adset"]))
PREV_COLS = {
    "ad": "status, configured_status, effective_status, review_feedback, issues, creative_id, title, body",
    "adset": ("status, configured_status, effective_status, learning_stage, learning, issues, daily_budget_cents, "
              "lifetime_budget_cents, bid_strategy, bid_amount_cents, start_time, end_time, targeting_fp, targeting_summary, "
              "setup_seen_at"),
    "campaign": ("status, configured_status, effective_status, issues, daily_budget_cents, lifetime_budget_cents, bid_strategy, "
                 "spend_cap_cents, start_time, stop_time, setup_seen_at"),
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


def minute_utc(value):
    """A time Meta sent ('2026-11-30T23:59:00-0800') or a stored datetime, as UTC to the minute
    ('2026-12-01T07:59Z'), so the same moment in two offsets compares equal."""
    when = parse_time(value) if value not in (None, "") else None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


AUDIENCE_KEYS = ("geo_locations", "excluded_geo_locations", "age_min", "age_max", "genders", "locales", "flexible_spec",
                 "exclusions", "custom_audiences", "excluded_custom_audiences", "publisher_platforms", "facebook_positions",
                 "instagram_positions", "device_platforms")


def _normal(value):
    """Sorted, so a list Meta returns in another order is the same audience."""
    if isinstance(value, dict):
        return {k: _normal(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [_normal(v) for v in value]
        if items and all(isinstance(v, dict) for v in items):
            return sorted(items, key=lambda v: str(v.get("id") or v.get("key") or json.dumps(v, sort_keys=True)))
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    return value


def targeting_fingerprint(t):
    """A short hash of who an ad set reaches: only the keys a person sets (Meta's own defaults such as
    age_range or targeting_relaxation_types left out), lists sorted. None without an audience."""
    if not t:
        return None
    kept = {k: t[k] for k in AUDIENCE_KEYS if t.get(k) not in (None, [], {})}
    advantage = (t.get("targeting_automation") or {}).get("advantage_audience")
    if advantage is not None:
        kept["advantage_audience"] = advantage
    if not kept:
        return None
    return hashlib.sha256(json.dumps(_normal(kept), sort_keys=True).encode()).hexdigest()[:16]


def _cents(value):
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return None
    return cents or None


def _asked(meta):
    return set((meta.get("_fields") or "").split(",")) - {""}


def full_read(level, meta):
    """Whether Meta was asked for every setup field (the newer field set), so they can be compared and stored."""
    keys = {META_KEY.get(f, {}).get(level, f) for f in SETUP.get(level, ())}
    return bool(keys) and keys <= _asked(meta)


def snapshot(level, meta):
    """Comparable state of an entity as Meta returned it. Setup fields only when all of them were asked for
    (meta['_fields']); one asked for and left out by Meta was removed (an end date taken off)."""
    snap = {"effective_status": meta.get("effective_status"),
            "configured_status": meta.get("configured_status") or meta.get("status"),
            "issues": issues_summary(meta.get("issues_info"))}
    if level == "ad":
        snap["review"] = review_summary(meta.get("ad_review_feedback"))
    if level == "adset":
        snap["learning"] = (meta.get("learning_stage_info") or {}).get("status")
    out = {f: snap.get(f) for f in FIELDS[level]}
    asked = _asked(meta)
    keys = {f: META_KEY.get(f, {}).get(level, f) for f in SETUP.get(level, ())}
    if not keys or not set(keys.values()) <= asked:
        return out  # read with the older field set: setup fields aren't compared (nor marked as seen)
    for f, key in keys.items():
        value = meta.get(key)
        out[f] = (_cents(value) if f in CENTS_FIELDS else minute_utc(value) if f in TIME_FIELDS
                  else targeting_fingerprint(value) if f == "targeting" else (value or None))
    return out


def stored_snapshot(level, row):
    """Comparable state of an entity as the console stored it (columns added later fall back to the old ones).
    Setup fields only once a full read stored them (setup_seen_at)."""
    snap = {"effective_status": row.get("effective_status"),
            "configured_status": row.get("configured_status") or row.get("status"),
            "issues": issues_summary(row.get("issues"))}
    if level == "ad":
        snap["review"] = review_summary(row.get("review_feedback"))
    if level == "adset":
        snap["learning"] = (row.get("learning") or {}).get("status") or row.get("learning_stage")
    out = {f: snap.get(f) for f in FIELDS[level]}
    if row.get("setup_seen_at"):
        for f in SETUP.get(level, ()):
            col = STORED_COL[f] if isinstance(STORED_COL[f], str) else STORED_COL[f][level]
            value = row.get(col)
            out[f] = (_cents(value) if f in CENTS_FIELDS else minute_utc(value) if f in TIME_FIELDS else (value or None))
    return out


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
    fields = list(FIELDS[level]) + [f for f in SETUP.get(level, ()) if f in before and f in after]
    return [{"field": f, "old": before.get(f), "new": after.get(f), "backfill": False}
            for f in fields if before.get(f) != after.get(f)]


BUDGET_FIELDS = ("daily_budget", "lifetime_budget")


def explained_by_console(entity_id, ev, changes, now):
    """The meta_changes id of a recent write from this console that explains the event, else None: a switch
    for a status, our own budget write to that exact amount, or Meta's advice applied here (any amount)."""
    if ev["field"] in BUDGET_FIELDS:
        for ch in sorted(changes, key=lambda c: c["created_at"], reverse=True):
            if ch["entity_id"] != entity_id or not ch.get("ok") or now - ch["created_at"] > CONSOLE_WINDOW:
                continue
            if ch["action"] in ("recommendation", "recommendation_check") or (
                    ch["action"] == "budget" and ev["field"] == "daily_budget" and ch.get("new_value") == str(ev.get("new"))):
                return ch["id"]
        return None
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


BID_WORDS = {"LOWEST_COST_WITHOUT_CAP": "Highest volume", "COST_CAP": "Cost per result goal",
             "LOWEST_COST_WITH_BID_CAP": "Bid cap", "LOWEST_COST_WITH_MIN_ROAS": "Return on ad spend goal"}


def bid_words(value):
    return BID_WORDS.get(value) or (value or "none").replace("_", " ").title()


def _usd(cents):
    return words.money(cents, "USD")


def setup_headline(ev, money=None, tz=None):
    """Plain words for a budget, bid, date or audience change, or None for other fields."""
    field, old, new = ev["field"], ev.get("old"), ev.get("new")
    money = money or _usd
    o, n = _cents(old), _cents(new)
    if field == "daily_budget":
        if o and n:
            return f"Budget {money(o)} → {money(n)} a day"
        if n:
            return f"Daily budget set: {money(n)} a day"
        return ("Daily budget removed: the ad sets have their own now" if ev.get("level") == "campaign"
                else "Daily budget removed: the campaign's budget is shared now" if ev.get("level") == "adset"
                else "Daily budget removed")
    if field == "lifetime_budget":
        return (f"Lifetime budget {money(o)} → {money(n)}" if o and n else f"Lifetime budget set: {money(n)}" if n
                else "Lifetime budget removed")
    if field == "spend_cap":
        return (f"Campaign spending limit {money(o)} → {money(n)}" if o and n else f"Campaign spending limit set: {money(n)}" if n
                else "Campaign spending limit removed")
    if field == "bid_strategy":
        return f"Bid strategy: {bid_words(old)} → {bid_words(new)}" if old else f"Bid strategy: {bid_words(new)}"
    if field == "bid_amount":
        return f"Bid amount {money(o)} → {money(n)}" if o and n else f"Bid amount set: {money(n)}" if n else "Bid amount removed"
    if field in TIME_FIELDS:
        at = lambda v: parse_time(v.replace("Z", "+00:00")).astimezone(tz or timezone.utc)  # noqa: E731
        if field == "start_time":
            if not new:
                return "Start time removed"
            when = at(new)
            return f"Start moved to {words.day(when)}, {words.clock(when)}"
        if not new:
            return "End date removed: runs until turned off"
        if not old:
            return f"End date set: {words.day(at(new))}"
        return f"End date moved: {words.day(at(old))} → {words.day(at(new))}"
    if field == "targeting":
        detail = ev.get("detail") if isinstance(ev.get("detail"), dict) else {}
        before, after = detail.get("before"), detail.get("after")
        if before and after and before != after:
            return f"Audience changed: {before} → {after}"
        return "Audience settings changed (see Ads Manager for the detail)"
    return None


def headline(ev, money=None, tz=None):
    """One line of plain words for a timeline entry."""
    field, old, new = ev["field"], ev.get("old"), ev.get("new")
    setup = setup_headline(ev, money, tz)
    if setup and not ev.get("backfill"):
        return setup
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
        return {"DISAPPROVED": "Rejected", "WITH_ISSUES": "Has issues", "PAUSED": "Turned off",
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
        if ev["field"] == "targeting":
            import sync
            ev["detail"] = {"before": (prev or {}).get("targeting_summary"), "after": sync.summarize_targeting(meta.get("targeting"))}
    return record(level, meta, events, source, now)


def record(level, entity, events, source, now=None, detail=None):
    if not events:
        return []
    now = now or datetime.now(timezone.utc)
    changes = db.query(
        """SELECT id, entity_id, action, new_value, ok, created_at FROM meta_changes
           WHERE entity_id = %s AND action IN ('status', 'budget', 'recommendation', 'recommendation_check')
             AND created_at > now() - interval '15 minutes'""",
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
             ev["field"], None if ev.get("old") is None else str(ev["old"]), None if ev.get("new") is None else str(ev["new"]), src,
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
    import settings_store
    try:
        tz = account_info.tz()
        today = now.astimezone(tz).date()
        context = None
        if any(e["field"] in SETUP.get(level, ()) and e.get("source") in ("poll", "webhook") for e in events):
            mine = {e["id"] for e in events}
            rows = [r for r in budget_rows([entity["id"]], now - timedelta(days=90)) if r.get("event_id") not in mine]
            context = {"cap_cents": money_rules.ceiling(settings_store.get("max_daily_budget_cents")),
                       "last_budget": money_rules.last_budget_change(rows)}
        found = transitions(level, entity, events, alerts.saved_rules(), now, today, money=account_info.money,
                            context=context, tz=tz)
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


EVENT_COLS = """e.id, e.level, e.entity_id, e.entity_name, e.campaign_id, e.adset_id, e.field, e.old_value, e.new_value,
                e.source, e.detail, e.at, e.change_id, u.name AS by_name"""


def with_headlines(rows):
    import account_info
    tz = account_info.tz()
    for r in rows:
        r["headline"] = headline({"field": r["field"], "old": r["old_value"], "new": r["new_value"], "level": r.get("level"),
                                  "detail": r.get("detail"), "backfill": r["source"] == "backfill"},
                                 money=account_info.money, tz=tz)
    return rows


def timeline(level, entity_id, limit=100):
    rows = db.query(
        f"""SELECT {EVENT_COLS}
           FROM status_events e LEFT JOIN meta_changes c ON c.id = e.change_id LEFT JOIN users u ON u.id = c.user_id
           WHERE e.entity_id = %s ORDER BY e.at DESC, e.id DESC LIMIT %s""", (entity_id, limit))
    return with_headlines(rows)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def budget_rows(entity_ids, since):
    """Budget history for the 3-day rule (money_rules.last_budget_change rows): the console's own budget writes
    plus every daily or lifetime budget change Meta reported (a change from Meta's advice shows up as a
    console event with numbers). `at` of an event is Meta's own update time when that is earlier."""
    if not entity_ids:
        return []
    rows = db.query(
        """SELECT m.entity_id, m.created_at AS at, 'daily_budget' AS field, m.old_value, m.new_value, 'console' AS where_,
                  u.name AS by, m.proposal_id, NULL::bigint AS event_id
           FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
           WHERE m.action = 'budget' AND m.ok AND m.entity_id = ANY(%s) AND m.created_at >= %s
           UNION ALL
           SELECT e.entity_id, LEAST(COALESCE(e.meta_time, e.at), e.at), e.field, e.old_value, e.new_value,
                  CASE WHEN e.source = 'console' THEN 'console' ELSE 'outside' END,
                  CASE WHEN e.source = 'console' THEN u.name ELSE COALESCE(e.detail->>'actor', 'Ads Manager') END,
                  c.proposal_id, e.id
           FROM status_events e LEFT JOIN meta_changes c ON c.id = e.change_id LEFT JOIN users u ON u.id = c.user_id
           WHERE e.field IN ('daily_budget', 'lifetime_budget') AND e.source <> 'backfill'
             AND e.entity_id = ANY(%s) AND e.at >= %s""", (list(entity_ids), since, list(entity_ids), since))
    return [{"at": r["at"], "field": r["field"], "old": _int(r["old_value"]), "new": _int(r["new_value"]),
             "by": r["by"], "where": r["where_"], "proposal_id": r["proposal_id"], "entity_id": r["entity_id"],
             "event_id": r["event_id"]} for r in rows]


def last_budgets(entity_ids, now=None):
    """{entity id: its last real budget change in the last 90 days} for the 3-day rule."""
    now = now or datetime.now(timezone.utc)
    rows = budget_rows(entity_ids, now - timedelta(days=90))
    out = {}
    for eid in entity_ids:
        last = money_rules.last_budget_change([r for r in rows if r["entity_id"] == eid])
        if last:
            out[eid] = last
    return out


def note_live_budget(level, entity_id, live_cents, source="poll"):
    """A fresh read found a daily budget that differs from the stored one: store it and record the change as
    made outside the console, in one step under the row lock, before anything else uses the stored value.
    Nothing is recorded before the first full read stored the setup fields (setup_seen_at)."""
    rows = db.query(
        f"""WITH old AS (SELECT id, name, {'id' if level == 'campaign' else 'campaign_id'} AS campaign_id, daily_budget_cents,
                                setup_seen_at FROM {TABLE[level]}
                         WHERE id = %s FOR UPDATE)
            UPDATE {TABLE[level]} t SET daily_budget_cents = %s FROM old
            WHERE t.id = old.id AND old.daily_budget_cents IS DISTINCT FROM %s
            RETURNING old.id, old.name, old.campaign_id, old.daily_budget_cents AS was, old.setup_seen_at""",
        (entity_id, live_cents, live_cents))
    if not rows or not rows[0]["setup_seen_at"]:
        return []
    r = rows[0]
    entity = {"id": r["id"], "name": r["name"], "campaign_id": r["id"] if level == "campaign" else r["campaign_id"]}
    return record(level, entity, [{"field": "daily_budget", "old": r["was"], "new": live_cents, "backfill": False,
                                   "detail": {"noticed": "budget check"}}], source)


def changes_in(scope, start, end, viewer, tz, for_client=False):
    """The chart-worthy changes (timeline items) around the days [start, end] (account days); marks_payload
    groups them by day and lists the newest. scope:
       campaigns: everything under these campaigns · adsets: everything under these ad sets ·
       entities: these ids' own changes · parents: only budget and on/off of these ids ·
       account: everything (Results) · ad_meta_only: ads count only for new, approved, rejected and versions.
    Teammates see their campaigns only; account-wide items (Meta's advice at account level) are for admins."""
    import account_info
    import auth
    import marks
    import timeline as tl
    lo = datetime.combine(start, datetime.min.time(), tz) - timedelta(hours=1)
    hi = datetime.combine(end, datetime.max.time(), tz) + timedelta(hours=1)
    conds, params = [], []
    if scope.get("account"):
        conds.append("TRUE")
    for key, col in (("campaigns", "campaign_id"), ("adsets", "adset_id"), ("entities", "entity_id"), ("parents", "entity_id")):
        ids = [i for i in scope.get(key) or () if i]
        if ids:
            # Meta's advice applied here names the campaign as its entity, without a campaign id.
            conds.append(f"(x.{col} = ANY(%s) OR x.entity_id = ANY(%s))" if col != "entity_id" else "x.entity_id = ANY(%s)")
            params += [ids, ids] if col != "entity_id" else [ids]
    if not conds:
        return []
    where = "(" + " OR ".join(conds) + ")"
    events = with_headlines(db.query(
        f"""SELECT {EVENT_COLS} FROM status_events e LEFT JOIN meta_changes c ON c.id = e.change_id
                LEFT JOIN users u ON u.id = c.user_id, LATERAL (SELECT e.campaign_id, e.adset_id, e.entity_id) x
            WHERE e.at BETWEEN %s AND %s AND e.source <> 'backfill' AND {where}""", [lo, hi] + params))
    # meta_changes keeps the campaign id; an ad set's own id is entity_id, its ads are found through ads.adset_id.
    changes = db.query(
        f"""SELECT m.*, u.name AS user_name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id,
                LATERAL (SELECT m.campaign_id, COALESCE((SELECT a.adset_id FROM ads a WHERE a.id = m.entity_id), m.entity_id) AS adset_id,
                                m.entity_id) x
            WHERE m.created_at BETWEEN %s AND %s AND m.ok
              AND m.action NOT IN ('update_creative', 'restore_creative') AND {where}""", [lo, hi] + params)
    versions = db.query(
        f"""SELECT v.ad_id, a.name AS ad_name, a.campaign_id, v.number, v.label, v.started_at, v.proposal_id FROM ad_versions v
                JOIN ads a ON a.id = v.ad_id, LATERAL (SELECT a.campaign_id, a.adset_id, a.id AS entity_id) x
            WHERE v.number > 1 AND v.started_at BETWEEN %s AND %s AND {where}""", [lo, hi] + params)
    if for_client:
        for c in changes:
            c["proposal_id"] = None
    items = tl.merge(events, changes, [], money=account_info.money, versions=versions)
    parents = set(scope.get("parents") or ())
    own = set(scope.get("entities") or ())
    visible = auth.visible_campaign_ids(viewer)

    def keep(i):
        if i["entity_id"] in parents and i["entity_id"] not in own and i["cat"] not in ("money", "switch"):
            return False
        if scope.get("ad_meta_only") and i.get("level") == "ad" and not (
                i["kind"] == "version" or i.get("field") == "created"
                or (i.get("field") == "effective_status" and i.get("new") in ("ACTIVE", "DISAPPROVED")
                    and i.get("old") in ("IN_PROCESS", "PENDING_REVIEW", "PREAPPROVED", None))
                or (i.get("field") == "effective_status" and i.get("new") == "DISAPPROVED")):
            return False
        return True
    items = [i for i in items if keep(i) and (viewer.get("role") == "admin" or i.get("level") in LEVELS)]
    if visible is not None:
        # Teammates and clients: their campaigns only; account-wide items (no campaign) are for admins.
        campaign = {r["entity_id"]: r.get("campaign_id") for r in events + changes if r.get("campaign_id")}
        campaign.update({v["ad_id"]: v.get("campaign_id") for v in versions})
        allowed = set(visible)
        items = [i for i in items if campaign.get(i["entity_id"]) in allowed]
    return marks.chart_worthy(items)


def marks_payload(user, scope, start, end):
    """{marks, marks_summary, marks_list} for a page's daily charts over [start, end] (account days): the marks
    per day for the charts, and the newest changes of the period for the list under them."""
    import account_info
    import marks
    from datetime import date
    tz, for_client = account_info.tz(), user.get("role") == "client"
    items = changes_in(scope, start, end, user, tz, for_client=for_client)
    m = marks.by_day(items, tz, start, end, for_client=for_client)
    return {"marks": m, "marks_summary": marks.summary_words(m, lambda d: words.day(date.fromisoformat(d))),
            "marks_list": marks.latest(items, tz, start, end, for_client=for_client)}


def marks_scope(level, row):
    """Which changes a campaign, ad set or ad page charts: everything inside it, plus the budget and on/off
    of what it sits in (a shared campaign budget drives its ad sets)."""
    if level == "campaign":
        return {"campaigns": [row["id"]]}
    if level == "adset":
        return {"adsets": [row["id"]], "parents": [row.get("campaign_id")]}
    return {"entities": [row["id"]], "parents": [p for p in (row.get("adset_id"), row.get("campaign_id")) if p]}


LEVEL_WORDS = {"campaign": "Campaign", "adset": "Ad set", "ad": "Ad"}


def _href(level, entity):
    """Where an alert about this opens: the ad itself, or the campaign's or ad set's page (9.3 entity links)."""
    if level == "ad":
        return f"/ad.html?id={entity['id']}"
    return f"/{'campaign' if level == 'campaign' else 'adset'}.html?id={entity['id']}"


def _rule_lines(ev, ctx, now, money, tz):
    """For a budget change made outside: which console money rules it breaks, in plain words."""
    if ev["field"] not in BUDGET_FIELDS:
        return []
    old, new = _cents(ev.get("old")), _cents(ev.get("new"))
    if not new:
        return []
    cap = (ctx or {}).get("cap_cents") or money_rules.MAX_DAILY_DEFAULT
    last = (ctx or {}).get("last_budget")
    change = money_rules.budget_change(old or 0, new, cap, last, now)
    lines = []
    if old and change["big"]:
        lines.append(f"That's +{change['pct']}%, more than the +20% step the console allows at once.")
    if ev["field"] == "daily_budget" and change["over_cap"]:
        lines.append(f"It's above the highest daily budget set in Settings ({money(cap)}).")
    if old and change["recent"]:
        hours = change["hours"]
        gap = f"{hours // 24} day{'s' if hours // 24 != 1 else ''}" if hours >= 24 else f"{max(hours, 1)} hour{'s' if hours > 1 else ''}"
        was = f"{money(last['old'])} → {money(last['new'])}" if last.get("old") and last.get("new") else "a new amount"
        when = words.day(last["at"].astimezone(tz or timezone.utc))
        lines.append(f"The budget had changed only {gap} before ({when}, {was}).")
    return lines


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


def outside_title(ev, money, tz):
    """'Budget changed in Ads Manager: $20.00 → $30.00 a day', 'End date set in Ads Manager: Nov 30'."""
    field, old, new = ev["field"], ev.get("old"), ev.get("new")
    if field == "targeting":
        return "Audience changed in Ads Manager"
    if field in TIME_FIELDS:
        thing = "Start" if field == "start_time" else "End date"
        if not new:
            return f"{thing} removed in Ads Manager"
        at = lambda v: parse_time(v.replace("Z", "+00:00")).astimezone(tz or timezone.utc)  # noqa: E731
        when = (lambda d: f"{words.day(d)}, {words.clock(d)}") if field == "start_time" else (lambda d: words.day(d))
        if not old or field == "start_time":
            return f"{thing} {'set' if not old else 'moved'} in Ads Manager: {when(at(new))}"
        return f"{thing} moved in Ads Manager: {when(at(old))} → {when(at(new))}"
    if field == "bid_strategy":
        return f"Bid strategy changed in Ads Manager: {bid_words(old)} → {bid_words(new)}"
    o, n = _cents(old), _cents(new)
    thing, unit = {"daily_budget": ("Daily budget", " a day"), "lifetime_budget": ("Lifetime budget", ""),
                   "spend_cap": ("Campaign spending limit", ""), "bid_amount": ("Bid amount", "")}[field]
    if o and n:
        return f"{'Budget' if field == 'daily_budget' else thing} changed in Ads Manager: {money(o)} → {money(n)}{unit}"
    if n:
        return f"{thing} set in Ads Manager: {money(n)}{unit}"
    return f"{thing} removed in Ads Manager"


def transitions(level, entity, events, rules, now, today, money=None, context=None, tz=None):
    """Alert dicts (same shape as alerts.evaluate) for changes worth telling someone about. `context` for
    budget changes made outside: {cap_cents, last_budget} (the change before these)."""
    on = lambda rule: (rules.get(rule) or {}).get("on", True)
    name, eid = entity.get("name") or entity["id"], entity["id"]
    camp = entity["id"] if level == "campaign" else entity.get("campaign_id")
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    money = money or _usd
    out = []

    def add(rule, key, alert_level, title, lines, kind="event", resolved=True, href=None):
        out.append({"rule": rule, "key": key, "level": alert_level, "title": title, "lines": lines, "entity_id": eid,
                    "campaign_id": camp, "href": href or _href(level, entity), "kind": kind, "resolved": resolved})

    setup = [e for e in events if e["field"] in SETUP.get(level, ()) and e.get("source") in ("poll", "webhook")
             and not e.get("backfill")]
    if setup and on("outside_edit"):
        ordered = sorted(setup, key=lambda e: SETUP[level].index(e["field"]))
        rule_lines = [line for e in ordered for line in _rule_lines(e, context, now, money, tz)]
        named = f"{LEVEL_WORDS[level]} “{name}”"
        if len(ordered) == 1:
            title, change_lines = outside_title({**ordered[0], "level": level}, money, tz), []
        else:
            title = f"{named} changed in Ads Manager"
            change_lines = [setup_headline({**e, "level": level}, money, tz) for e in ordered]
        warn = bool(rule_lines)
        add("outside_edit", f"outside_edit:{eid}:{stamp}", "warn" if warn else "info", title,
            [named] + change_lines + rule_lines +
            ["Made outside this console (Ads Manager, or Claude on the Mac). Nothing to do if that was you."],
            resolved=not warn, href=links.history_href(level, eid) if level != "ad" else None)

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
                ["Someone changed it in Ads Manager (or through Claude on the Mac). Nothing to do if that was you."],
                href=links.history_href(level, eid))
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
