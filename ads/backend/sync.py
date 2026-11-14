"""Mirror the ad account's campaigns so teammates can be assigned to them."""
import json

import audience_rules
import db
import edit_rules
import meta_client
import settings_store
import status_history


def cents(value):
    """Meta sends budgets as strings in minor units; "0" means not set."""
    return int(value) if value not in (None, "", "0") else None


def spend_cap(value):
    """A campaign's spend_cap in cents; Meta's 'no cap' value (edit_rules.NO_SPEND_CAP) is none."""
    c = cents(value)
    return None if c is None or str(value) == edit_rules.NO_SPEND_CAP else c


def _json(value):
    return json.dumps(value) if value not in (None, [], {}) else None


def _audience_part(t, key, names):
    items = [a for a in t.get(key) or [] if isinstance(a, dict) and a.get("id")]
    named = [a.get("name") or (names or {}).get(str(a["id"])) for a in items]
    if not items:
        return None
    return ", ".join(f"“{n}”" for n in named) if all(named) else f"{len(items)} audience{'s' if len(items) != 1 else ''}"


def audience_names(t):
    """{id: name} from the account's own list for audiences Meta's read named without a name (one query, only when needed)."""
    ids = [str(a["id"]) for k in ("custom_audiences", "excluded_custom_audiences") for a in (t or {}).get(k) or []
           if isinstance(a, dict) and a.get("id") and not a.get("name")]
    return {r["id"]: r["name"] for r in db.query("SELECT id, name FROM audiences WHERE id = ANY(%s)", (ids,))} if ids else {}


def summarize_targeting(t, audience_names=None):
    """A one-line, human description of an ad set's targeting (audiences named from Meta's read or the account's list)."""
    if not t:
        return None
    parts = []
    lo, hi = t.get("age_min"), t.get("age_max")
    if lo or hi:
        parts.append(f"Ages {lo or 18}–{hi or 65}{'+' if (hi or 65) >= 65 else ''}")
    geo = t.get("geo_locations") or {}
    places = [c.get("name") for c in geo.get("cities", []) if c.get("name")]
    places += [r.get("name") for r in geo.get("regions", []) if r.get("name")]
    pins = geo.get("custom_locations") or []
    if pins:
        radius = pins[0].get("radius")
        unit = pins[0].get("distance_unit", "mile")
        places.append(f"{len(pins)} area{'s' if len(pins) != 1 else ''}" + (f" ({radius} {unit}s)" if radius else ""))
    if not places and geo.get("countries"):
        places.append(", ".join(geo["countries"]))
    if places:
        parts.append(", ".join(places))
    interests = [i.get("name") for spec in t.get("flexible_spec", []) for key in ("interests", "behaviors", "work_positions")
                 for i in spec.get(key, []) if i.get("name")]
    if interests:
        parts.append("Hints: " + ", ".join(interests[:4]) + (f" +{len(interests) - 4}" if len(interests) > 4 else ""))
    if (t.get("targeting_automation") or {}).get("advantage_audience") == 1:
        parts.append("Advantage+ audience")
    for key, word in (("custom_audiences", "In"), ("excluded_custom_audiences", "Not in")):
        part = _audience_part(t, key, audience_names)
        if part:
            parts.append(f"{word} {part}")
    return " · ".join(parts) or None


ADSET_FIELDS = ("id,name,campaign_id,status,configured_status,effective_status,daily_budget,lifetime_budget,"
                "optimization_goal,learning_stage_info,targeting,issues_info,created_time,updated_time,"
                "bid_strategy,bid_amount,start_time,end_time,attribution_spec,destination_type,billing_event,"
                "frequency_control_specs,promoted_object")
ADSET_FIELDS_PLAIN = ("id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget,"
                      "optimization_goal,learning_stage_info,targeting")
# Budget, bid, dates and audience are stored only from a full read (setup_seen_at set, D2); a read with the
# older field set keeps what was stored.
_KEEP = "CASE WHEN EXCLUDED.setup_seen_at IS NOT NULL THEN EXCLUDED.{c} ELSE {t}.{c} END"
ADSET_UPSERT = """INSERT INTO adsets (id, name, campaign_id, status, configured_status, effective_status, daily_budget_cents,
                                   lifetime_budget_cents, optimization_goal, learning_stage, learning, issues,
                                   targeting_summary, created_time, updated_time, bid_strategy, bid_amount_cents,
                                   start_time, end_time, targeting_fp, targeting, placements_fp, attribution, destination_type,
                                   billing_event, frequency, audience_ids, excluded_audience_ids, setup_seen_at, edit_seen_at, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       CASE WHEN %s THEN now() END, CASE WHEN %s THEN now() END, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, campaign_id = EXCLUDED.campaign_id,
                   status = EXCLUDED.status,
                   effective_status = EXCLUDED.effective_status,
                   daily_budget_cents = EXCLUDED.daily_budget_cents,
                   lifetime_budget_cents = EXCLUDED.lifetime_budget_cents,
                   optimization_goal = EXCLUDED.optimization_goal, learning_stage = EXCLUDED.learning_stage,
                   learning = EXCLUDED.learning, issues = CASE WHEN %s THEN adsets.issues ELSE EXCLUDED.issues END,
                   targeting_summary = EXCLUDED.targeting_summary,
                   """ + ", ".join(f"{c} = " + _KEEP.format(c=c, t="adsets") for c in
                                   ("bid_strategy", "bid_amount_cents", "start_time", "end_time", "targeting_fp", "targeting",
                                    "placements_fp", "attribution", "destination_type", "billing_event", "frequency", "audience_ids",
                                    "excluded_audience_ids")) + """,
                   setup_seen_at = COALESCE(EXCLUDED.setup_seen_at, adsets.setup_seen_at),
                   edit_seen_at = COALESCE(EXCLUDED.edit_seen_at, adsets.edit_seen_at),
                   configured_status = COALESCE(EXCLUDED.configured_status, adsets.configured_status),
                   created_time = COALESCE(EXCLUDED.created_time, adsets.created_time),
                   updated_time = COALESCE(EXCLUDED.updated_time, adsets.updated_time), synced_at = now()
               """ + status_history.UNLESS_CONSOLE_WROTE.format(table="adsets")


PARTIAL = "_partial"  # set on rows read with the older field set: what that set lacks is kept as stored


def with_fallback(read, fields, fallback, shape="list"):
    """read(fields), or read(fallback) with every row marked PARTIAL when Meta refuses one of the newer
    fields. A request Meta didn't really answer is raised, never retried with fewer fields (audit A3-31).
    shape: "list" (a listing), "ids" (a ?ids= read, {id: object}) or "one" (one object read by id)."""
    try:
        return read(fields)
    except meta_client.MetaError as exc:
        if meta_client.transient(exc) or fallback == fields:
            raise
    rows = read(fallback)
    if shape == "one":
        return {**rows, PARTIAL: True}
    if shape == "ids":
        return {k: {**v, PARTIAL: True} for k, v in rows.items()}
    return [{**r, PARTIAL: True} for r in rows]


def listing(path, fields, fallback):
    """Meta's list with the newer fields; the older field set if Meta refuses one of them."""
    return with_fallback(lambda f: list(meta_client.paged(path, fields=f, limit=100)), fields, fallback)


def kept_issues(row, prev):
    """A row read with the older field set has no issues_info: keep the stored issues so nothing reads as cleared."""
    return {**row, "issues_info": (prev or {}).get("issues")} if row.get(PARTIAL) else row


def fields_read(row, fields, fallback):
    """The field set a row was read with (rows read with the older set are PARTIAL)."""
    return row.get("_fields") or (fallback if row.get(PARTIAL) else fields)


def _time(value):
    return status_history.parse_time(value) if value else None


def upsert_adset(a, source, listed_at):
    learning = a.get("learning_stage_info") or None
    a = {**a, "_fields": fields_read(a, ADSET_FIELDS, ADSET_FIELDS_PLAIN)}
    full = status_history.full_read("adset", a)
    prev, written = status_history.upsert_tracked("adset", a["id"], ADSET_UPSERT, (
        a["id"], a["name"], a.get("campaign_id"), a.get("status"), a.get("configured_status"), a.get("effective_status"),
        cents(a.get("daily_budget")), cents(a.get("lifetime_budget")), a.get("optimization_goal"),
        (learning or {}).get("status"), json.dumps(learning) if learning else None,
        json.dumps(a.get("issues_info")) if a.get("issues_info") else None,
        summarize_targeting(a.get("targeting"), audience_names(a.get("targeting"))), a.get("created_time"), a.get("updated_time"),
        a.get("bid_strategy") or None, cents(a.get("bid_amount")), _time(a.get("start_time")), _time(a.get("end_time")),
        status_history.targeting_fingerprint(a.get("targeting")), _json(edit_rules.kept_targeting(a.get("targeting"))),
        status_history.placements_fingerprint(a.get("targeting")), _json(a.get("attribution_spec")), a.get("destination_type"),
        a.get("billing_event"), _json(a.get("frequency_control_specs")),
        audience_rules.ids_in(a.get("targeting"), "custom_audiences"), audience_rules.ids_in(a.get("targeting"), "excluded_custom_audiences"), full, full,
        bool(a.get(PARTIAL)), listed_at))
    if not written:
        return []
    return status_history.track("adset", kept_issues(a, prev), prev, source)


def sync_adsets(source="poll"):
    account = settings_store.get("meta_ad_account_id")
    listed_at = db.now()
    rows = listing(f"act_{account}/adsets", ADSET_FIELDS, ADSET_FIELDS_PLAIN)
    for a in rows:
        upsert_adset(a, source, listed_at)
    # Like ads: an ad set deleted in Ads Manager drops out of the listing; keep it, marked deleted.
    status_history.mark_missing("adset", [a["id"] for a in rows], source, listed_at)
    return len(rows)


CAMPAIGN_FIELDS = ("id,name,status,configured_status,effective_status,objective,daily_budget,lifetime_budget,"
                   "bid_strategy,issues_info,created_time,updated_time,spend_cap,start_time,stop_time,special_ad_categories")
CAMPAIGN_FIELDS_PLAIN = "id,name,status,effective_status,objective,daily_budget,lifetime_budget,bid_strategy"
CAMPAIGN_UPSERT = """INSERT INTO campaigns (id, name, status, configured_status, effective_status, objective,
                                      daily_budget_cents, lifetime_budget_cents, bid_strategy, issues,
                                      created_time, updated_time, spend_cap_cents, start_time, stop_time, special_ad_categories,
                                      setup_seen_at, edit_seen_at, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s THEN now() END, CASE WHEN %s THEN now() END, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
                   configured_status = COALESCE(EXCLUDED.configured_status, campaigns.configured_status),
                   effective_status = EXCLUDED.effective_status, objective = EXCLUDED.objective,
                   daily_budget_cents = EXCLUDED.daily_budget_cents,
                   lifetime_budget_cents = EXCLUDED.lifetime_budget_cents,
                   bid_strategy = EXCLUDED.bid_strategy, issues = CASE WHEN %s THEN campaigns.issues ELSE EXCLUDED.issues END,
                   """ + ", ".join(f"{c} = " + _KEEP.format(c=c, t="campaigns") for c in
                                   ("spend_cap_cents", "start_time", "stop_time", "special_ad_categories")) + """,
                   setup_seen_at = COALESCE(EXCLUDED.setup_seen_at, campaigns.setup_seen_at),
                   edit_seen_at = COALESCE(EXCLUDED.edit_seen_at, campaigns.edit_seen_at),
                   created_time = COALESCE(EXCLUDED.created_time, campaigns.created_time),
                   updated_time = COALESCE(EXCLUDED.updated_time, campaigns.updated_time), synced_at = now()
               """ + status_history.UNLESS_CONSOLE_WROTE.format(table="campaigns")


def upsert_campaign(c, source, listed_at):
    c = {**c, "_fields": fields_read(c, CAMPAIGN_FIELDS, CAMPAIGN_FIELDS_PLAIN)}
    full = status_history.full_read("campaign", c)
    prev, written = status_history.upsert_tracked("campaign", c["id"], CAMPAIGN_UPSERT, (
        c["id"], c["name"], c.get("status"), c.get("configured_status"), c.get("effective_status"), c.get("objective"),
        cents(c.get("daily_budget")), cents(c.get("lifetime_budget")), c.get("bid_strategy"),
        json.dumps(c.get("issues_info")) if c.get("issues_info") else None, c.get("created_time"), c.get("updated_time"),
        spend_cap(c.get("spend_cap")), _time(c.get("start_time")), _time(c.get("stop_time")),
        sorted(x for x in (c.get("special_ad_categories") or []) if x and x != "NONE") if full else None, full, full,
        bool(c.get(PARTIAL)), listed_at))
    if not written:
        return []
    return status_history.track("campaign", kept_issues(c, prev), prev, source)


def sync_campaigns(source="poll"):
    account = settings_store.get("meta_ad_account_id")
    listed_at = db.now()
    rows = listing(f"act_{account}/campaigns", CAMPAIGN_FIELDS, CAMPAIGN_FIELDS_PLAIN)
    for c in rows:
        upsert_campaign(c, source, listed_at)
    status_history.mark_missing("campaign", [c["id"] for c in rows], source, listed_at)
    settings_store.set("last_campaign_sync", __import__("datetime").datetime.utcnow().isoformat() + "Z")
    return len(rows)
