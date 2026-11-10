"""Mirror the ad account's campaigns so teammates can be assigned to them."""
import db
import meta_client
import settings_store


def cents(value):
    """Meta sends budgets as strings in minor units; "0" means not set."""
    return int(value) if value not in (None, "", "0") else None


def summarize_targeting(t):
    """A one-line, human description of an ad set's targeting."""
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
    return " · ".join(parts) or None


def sync_adsets():
    account = settings_store.get("meta_ad_account_id")
    n = 0
    seen = []
    for a in meta_client.paged(
        f"act_{account}/adsets",
        fields="id,name,campaign_id,status,effective_status,daily_budget,lifetime_budget,"
               "optimization_goal,learning_stage_info,targeting",
        limit=100,
    ):
        db.execute(
            """INSERT INTO adsets (id, name, campaign_id, status, effective_status, daily_budget_cents,
                                   lifetime_budget_cents, optimization_goal, learning_stage, targeting_summary, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, campaign_id = EXCLUDED.campaign_id,
                   status = EXCLUDED.status, effective_status = EXCLUDED.effective_status,
                   daily_budget_cents = EXCLUDED.daily_budget_cents,
                   lifetime_budget_cents = EXCLUDED.lifetime_budget_cents,
                   optimization_goal = EXCLUDED.optimization_goal, learning_stage = EXCLUDED.learning_stage,
                   targeting_summary = EXCLUDED.targeting_summary, synced_at = now()""",
            (a["id"], a["name"], a.get("campaign_id"), a.get("status"), a.get("effective_status"),
             cents(a.get("daily_budget")), cents(a.get("lifetime_budget")), a.get("optimization_goal"),
             (a.get("learning_stage_info") or {}).get("status"), summarize_targeting(a.get("targeting"))),
        )
        n += 1
        seen.append(a["id"])
    # Like ads: an ad set deleted in Ads Manager drops out of the listing; keep it, marked deleted.
    if seen:
        db.execute("UPDATE adsets SET effective_status = 'DELETED', status = 'DELETED' "
                   "WHERE NOT (id = ANY(%s)) AND COALESCE(status, '') <> 'ARCHIVED'", (seen,))
    return n


def sync_campaigns():
    account = settings_store.get("meta_ad_account_id")
    seen = 0
    ids = []
    for c in meta_client.paged(f"act_{account}/campaigns",
                               fields="id,name,status,effective_status,objective,daily_budget,lifetime_budget,bid_strategy",
                               limit=100):
        db.execute(
            """INSERT INTO campaigns (id, name, status, effective_status, objective,
                                      daily_budget_cents, lifetime_budget_cents, bid_strategy, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
                   effective_status = EXCLUDED.effective_status, objective = EXCLUDED.objective,
                   daily_budget_cents = EXCLUDED.daily_budget_cents,
                   lifetime_budget_cents = EXCLUDED.lifetime_budget_cents,
                   bid_strategy = EXCLUDED.bid_strategy, synced_at = now()""",
            (c["id"], c["name"], c.get("status"), c.get("effective_status"), c.get("objective"),
             cents(c.get("daily_budget")), cents(c.get("lifetime_budget")), c.get("bid_strategy")),
        )
        seen += 1
        ids.append(c["id"])
    if ids:
        db.execute("UPDATE campaigns SET effective_status = 'DELETED', status = 'DELETED' "
                   "WHERE NOT (id = ANY(%s)) AND COALESCE(status, '') <> 'ARCHIVED'", (ids,))
    settings_store.set("last_campaign_sync", __import__("datetime").datetime.utcnow().isoformat() + "Z")
    return seen
