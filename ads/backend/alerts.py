"""Alerts: rules checked after every pull from Meta. Each alert is raised at most once per
thing (ad, campaign, account) per day, sent to the admins (Telegram, else email), shown on
Home → Needs attention, and closed by itself once the condition is gone.

`evaluate(snapshot, rules, today)` is pure; `snapshot()` reads it from the database. Thresholds
live in Settings → Alerts (settings key `alert_rules`, merged over DEFAULTS).
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account_info
import config
import db
import notify
import settings_store

log = logging.getLogger(__name__)

DEFAULTS = {
    "ad_rejected": {"on": True},
    "no_delivery": {"on": True, "hours": 24},
    "fatigue": {"on": True, "frequency": 3.0, "ctr_drop": 20, "cpm_rise": 20},
    "day_overspend": {"on": True, "times": 1.75},
    "week_overspend": {"on": True, "times": 7.0},
    "spend_cap": {"on": True, "percent": 80},
    "cpl_high": {"on": True, "target_cents": None, "times": 1.3},
    "no_leads": {"on": True, "days": 3},
    "tracking": {"on": True},
    "stale_data": {"on": True, "hours": 3},
    "events_quiet": {"on": True},
    "cap_soon": {"on": True, "days": 3},
    "pace_over": {"on": True, "percent": 15},
    "ad_approved": {"on": True},
    "learning_limited": {"on": True},
    "changed_outside": {"on": True},
}
MIN_IMPRESSIONS = 1000  # per 7-day window, before fatigue is judged


def rules_with(saved):
    out = {}
    for rule, defaults in DEFAULTS.items():
        mine = (saved or {}).get(rule) or {}
        merged = dict(defaults)
        for key, default in defaults.items():
            if key not in mine:
                continue
            value = mine[key]
            try:
                if key == "on":
                    merged[key] = bool(value)
                elif value in (None, ""):
                    merged[key] = None if default is None else default
                elif isinstance(default, float):
                    merged[key] = float(value)
                else:
                    merged[key] = int(float(value))
            except (TypeError, ValueError):
                pass
        out[rule] = merged
    return out


def _sum(rows, key):
    return sum(r.get(key) or 0 for r in rows)


def _last(rows, today, n):
    start = today - timedelta(days=n)
    return [r for r in rows if start <= r["day"] < today]


def _fatigue(rows, today, rule, people):
    """(frequency, ctr drop %, cpm rise %) when the ad looks tired, else None. `people`: different people
    who saw it in the last 7 days (Meta's unique reach); without it frequency can't be judged (audit A3-12)."""
    seen = [r for r in rows if (r.get("impressions") or 0) > 0]
    first = seen[:7]
    last = _last(rows, today, 7)
    if len(first) < 7 or not first or not last or first[-1]["day"] >= today - timedelta(days=7):
        return None
    fi, li = _sum(first, "impressions"), _sum(last, "impressions")
    if fi < MIN_IMPRESSIONS or li < MIN_IMPRESSIONS or not people or not _sum(first, "link_clicks"):
        return None
    freq = li / people
    ctr_f, ctr_l = _sum(first, "link_clicks") / fi, _sum(last, "link_clicks") / li
    cpm_f, cpm_l = _sum(first, "spend_cents") / fi, _sum(last, "spend_cents") / li
    if not cpm_f:
        return None
    drop, rise = (ctr_f - ctr_l) / ctr_f * 100, (cpm_l - cpm_f) / cpm_f * 100
    if freq > rule["frequency"] and drop >= rule["ctr_drop"] and rise >= rule["cpm_rise"]:
        return freq, drop, rise
    return None


def evaluate(snap, rules, today):
    found = []

    def money(cents):
        return account_info.money(cents, snap.get("currency") or "USD", whole=not cents % 100)

    def add(rule, entity, level, title, lines, campaign_id=None, href=None):
        found.append({"rule": rule, "entity_id": entity, "key": f"{rule}:{entity}:{today.isoformat()}", "level": level,
                      "title": title, "lines": lines, "campaign_id": campaign_id, "href": href})

    for ad in snap["ads"]:
        href = f"/ad.html?id={ad['id']}"
        rows = snap["ad_days"].get(ad["id"], [])
        if rules["ad_rejected"]["on"] and ad["effective_status"] in ("DISAPPROVED", "WITH_ISSUES"):
            add("ad_rejected", ad["id"], "bad", f"Meta stopped “{ad['name']}”",
                [f"Status: {ad['effective_status'].replace('_', ' ').lower()}. Open the ad to see why and fix it."], ad["campaign_id"], href)
        r = rules["no_delivery"]
        # Today's partial day counts here: an ad first shown today has been seen (audit A3-63).
        seen = _sum(rows, "impressions") or ad.get("today_impressions")
        if r["on"] and ad["effective_status"] == "ACTIVE" and ad["age_hours"] >= r["hours"] and not seen:
            add("no_delivery", ad["id"], "warn", f"“{ad['name']}” is on but nobody has seen it",
                [f"No impressions {ad['age_hours']:.0f} hours after it went live."], ad["campaign_id"], href)
        r = rules["fatigue"]
        tired = r["on"] and ad["effective_status"] == "ACTIVE" and _fatigue(rows, today, r, (snap.get("reach_7d") or {}).get(ad["id"]))
        if tired:
            freq, drop, rise = tired
            add("fatigue", ad["id"], "warn", f"“{ad['name']}” looks tired",
                [f"People see it about {freq:.1f} times a week; clicks are down {drop:.0f}% and cost per 1,000 views up {rise:.0f}% since its first week.",
                 "Time for a fresh version."], ad["campaign_id"], href)

    for c in snap["campaigns"]:
        budget = c.get("daily_budget_cents") or 0
        rows = snap["camp_days"].get(c["id"], [])
        week = _last(rows, today, 7)
        href = "/performance.html"
        r = rules["day_overspend"]
        spent_today = (snap.get("today_spend") or {}).get(c["id"], 0)
        if r["on"] and budget and spent_today > r["times"] * budget:
            add("day_overspend", c["id"], "info", f"{money(spent_today)} spent today on a {money(budget)} daily budget",
                ["Meta may spend up to 1.75× the daily budget on one day and evens it out over the week. Just a heads-up."], c["id"], href)
        r = rules["week_overspend"]
        if r["on"] and budget and len(week) == 7 and _sum(week, "spend_cents") > r["times"] * budget:
            add("week_overspend", c["id"], "warn", f"{money(_sum(week, 'spend_cents'))} spent in 7 days on a {money(budget)} daily budget",
                [f"That's more than {r['times']:g}× the daily budget. Check the budget and the schedule."], c["id"], href)
        r = rules["cpl_high"]
        spend, leads = _sum(week, "spend_cents"), _sum(week, "leads")
        if r["on"] and r["target_cents"] and spend >= 3 * r["target_cents"]:
            cpl = spend / leads if leads else None
            if cpl is None or cpl > r["times"] * r["target_cents"]:
                add("cpl_high", c["id"], "warn",
                    f"Leads cost {money(cpl) if cpl else 'more than ' + money(spend)} each in “{c['name']}”",
                    [f"Last 7 days: {money(spend)} spent, {leads} lead{'s' if leads != 1 else ''}; your target is {money(r['target_cents'])}."], c["id"], href)
        r = rules["no_leads"]
        recent = _last(rows, today, r["days"])
        if r["on"] and len(recent) == r["days"] and all((x.get("spend_cents") or 0) > 0 for x in recent) and not _sum(recent, "leads"):
            add("no_leads", c["id"], "bad", f"No leads for {r['days']} days in “{c['name']}”",
                [f"{money(_sum(recent, 'spend_cents'))} spent since {recent[0]['day'].strftime('%b %-d')} and not one lead. Check the form and the ads."], c["id"], href)

    r = rules["spend_cap"]
    cap = snap.get("cap")
    if r["on"] and cap and cap.get("limit_cents"):
        used = cap["spent_cents"] / cap["limit_cents"] * 100
        if used >= r["percent"]:
            done = used >= 100
            add("spend_cap", "account", "bad" if done else "warn",
                "The account spending limit is reached" if done else f"{used:.0f}% of the account spending limit is used",
                [f"{money(cap['spent_cents'])} of {money(cap['limit_cents'])}. Every ad stops when it's reached; raise it in Meta's billing settings if you want them to keep running."],
                None, "/performance.html")

    p = snap.get("pacing") or {}
    r = rules["cap_soon"]
    if r["on"] and p.get("cap_days") is not None and p["cap_days"] <= r["days"] and not (cap and cap["spent_cents"] >= cap["limit_cents"]):
        when = date.fromisoformat(p["cap_date"]).strftime("%a %b %-d")
        add("cap_soon", "account", "warn", f"The spending limit runs out in about {p['cap_days']} day{'s' if p['cap_days'] != 1 else ''}",
            [f"At the current pace every ad stops around {when}. Raise the limit in Meta's billing settings to keep them running."],
            None, "/performance.html")
    r = rules["pace_over"]
    if r["on"] and p.get("vs_target_pct") is not None and p["vs_target_pct"] > r["percent"]:
        add("pace_over", "account", "warn", f"This month is heading {p['vs_target_pct']}% over your target",
            [f"At the current pace the month ends near {money(p['projected_cents'])} against {money(p['target_cents'])}."],
            None, "/performance.html")

    r = rules["tracking"]
    two = [today - timedelta(days=1), today - timedelta(days=2)]
    meta = sum(snap["meta_leads"].get(d, 0) for d in two)
    inbox = sum(snap["inbox_leads"].get(d, 0) for d in two)
    if r["on"] and meta >= 2 and inbox == 0:
        add("tracking", "account", "bad", "Leads aren't reaching the inbox",
            [f"Meta counted {meta} leads in the last two days, but none arrived here. Check the Page connection in Settings → Meta."],
            None, "/settings.html")

    r = rules["events_quiet"]
    t = snap.get("tracking") or {}
    if r["on"] and t.get("state") == "quiet":
        add("events_quiet", "account", "warn", "Meta stopped receiving lead stages",
            [t.get("headline") or "Nothing has reached the dataset for two days.", "See Settings → Tracking health."], None, "/settings.html#tracking")

    r = rules["stale_data"]
    age = snap.get("last_pull_age_h")
    if r["on"] and snap.get("connected") and age is not None and age > r["hours"]:
        add("stale_data", "account", "warn", "Meta hasn't answered for a while",
            [f"The last pull from Meta was {age:.0f} hours ago. The token or the connection may need a look in Settings → Meta."],
            None, "/settings.html")
    return found


# ---------------------------------------------------------------- database side

def saved_rules():
    raw = settings_store.get("alert_rules")
    return rules_with(json.loads(raw) if raw else {})


def snapshot(now):
    import refresh_api
    tz = account_info.tz()
    today = now.astimezone(tz).date()
    # "No delivery" counts from when the ad last went live (approved or switched on), not from creation:
    # an ad can sit in review or off for days.
    ads = db.query("""SELECT a.id, a.name, a.campaign_id, a.effective_status,
                             GREATEST(a.created_time, (SELECT MAX(e.at) FROM status_events e WHERE e.entity_id = a.id
                                 AND e.field IN ('effective_status', 'created') AND e.new_value = 'ACTIVE'
                                 AND e.source <> 'backfill')) AS live_since
                      FROM ads a WHERE a.effective_status NOT IN ('DELETED', 'ARCHIVED')""")
    shown_today = {r["ad_id"]: int(r["n"]) for r in db.query(
        "SELECT ad_id, SUM(impressions) AS n FROM ad_daily WHERE day = %s GROUP BY ad_id", (today,))}
    for a in ads:
        a["age_hours"] = (now - a["live_since"]).total_seconds() / 3600 if a["live_since"] else 0
        a["today_impressions"] = shown_today.get(a["id"], 0)
    ad_days = {}
    for r in db.query("SELECT day, ad_id, spend_cents, impressions, reach, link_clicks, leads FROM ad_daily "
                      "WHERE day >= %s AND day < %s ORDER BY day", (today - timedelta(days=90), today)):
        ad_days.setdefault(r["ad_id"], []).append(r)
    camps = db.query("""SELECT c.id, c.name, COALESCE(c.daily_budget_cents,
                               (SELECT SUM(daily_budget_cents) FROM adsets s WHERE s.campaign_id = c.id AND s.effective_status = 'ACTIVE')) AS daily_budget_cents
                        FROM campaigns c WHERE c.effective_status = 'ACTIVE'""")
    camp_days = {}
    for r in db.query("SELECT day, campaign_id, SUM(spend_cents) AS spend_cents, SUM(leads) AS leads FROM ad_daily "
                      "WHERE day >= %s AND day < %s GROUP BY day, campaign_id ORDER BY day", (today - timedelta(days=14), today)):
        camp_days.setdefault(r["campaign_id"], []).append({"day": r["day"], "spend_cents": int(r["spend_cents"]), "leads": int(r["leads"])})
    import insights
    today_snap = insights.today_for(settings_store.get("today_snapshot"), today) or {}
    today_spend = {cid: v["spend_cents"] for cid, v in (today_snap.get("campaigns") or {}).items()}
    from performance_api import cap_snapshot, pacing_data
    meta_leads = {r["day"]: int(r["n"]) for r in db.query(
        "SELECT day, SUM(leads) AS n FROM ad_daily WHERE day >= %s AND day < %s GROUP BY day", (today - timedelta(days=3), today))}
    inbox = {r["day"]: int(r["n"]) for r in db.query(
        "SELECT (created_time AT TIME ZONE %s)::date AS day, COUNT(*) AS n FROM leads WHERE NOT is_test "
        "AND created_time > now() - interval '4 days' GROUP BY 1", (account_info.tz_name(),))}
    updated = refresh_api.last_updated(settings_store.get("last_refresh_at"), settings_store.get("last_performance_sync"))
    return today, {
        # Different people per ad over the same 7 days, from Meta (daily reach can't be added up); None when quiet.
        "reach_7d": insights.unique_reach("ad", today - timedelta(days=7), today - timedelta(days=1)),
        "ads": ads, "ad_days": ad_days, "campaigns": camps, "camp_days": camp_days, "today_spend": today_spend,
        "cap": cap_snapshot(), "meta_leads": meta_leads, "inbox_leads": inbox,
        "last_pull_age_h": (now.timestamp() - updated) / 3600 if updated else None,
        "connected": bool(settings_store.get("meta_system_token")),
        "currency": account_info.currency(),
        "pacing": pacing_data(None),
        "tracking": tracking_state(now),
    }


def tracking_state(now):
    """The tracking verdict from the last dataset read (no Meta call here)."""
    raw = settings_store.get("tracking_snapshot")
    data = json.loads(raw) if raw else {}
    if not data.get("dataset"):
        return {}
    import crm_events
    import tracking
    return tracking.assess(data["details"], data["events"], data["sources"], data["match"], crm_events.summary(), now,
                           settings_store.get("crm_send_enabled") == "1")


def run(now=None):
    """Check every rule; raise the new alerts, tell the admins, close the ones that are gone."""
    now = now or datetime.now(timezone.utc)
    today, snap = snapshot(now)
    import targets
    rules = saved_rules()
    rules["cpl_high"] = {**rules["cpl_high"], "target_cents": targets.lead()}  # Settings → Targets
    found = evaluate(snap, rules, today)
    raised = raise_found(found)
    opened = db.query("SELECT id, rule, entity_id FROM alerts WHERE resolved_at IS NULL AND kind = 'condition'")
    for alert_id in to_resolve(opened, found, snap):
        db.execute("UPDATE alerts SET resolved_at = now() WHERE id = %s", (alert_id,))
    return [a["key"] for _, a in raised]


def to_resolve(opened, found, snap):
    """Open condition alerts whose condition is gone. Fatigue can't be judged while Meta doesn't answer
    unique reach (reach_7d None, e.g. a rate-limit cooldown): those alerts stay open, or one hiccup would
    close them for the rest of the day (the dedupe key is per day)."""
    live = {(a["rule"], a["entity_id"]) for a in found}
    unjudged = {"fatigue"} if snap.get("reach_7d") is None else set()
    return [r["id"] for r in opened if (r["rule"], r["entity_id"]) not in live and r["rule"] not in unjudged]


def raise_found(found):
    """Store new alerts (once per dedupe key) and tell the admins; info alerts stay in the console."""
    raised = []
    for a in found:
        row = db.execute(
            "INSERT INTO alerts (rule, dedupe_key, level, title, lines, entity_id, campaign_id, href, kind, resolved_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END) "
            "ON CONFLICT (account_id, dedupe_key) DO NOTHING RETURNING id",
            (a["rule"], a["key"], a["level"], a["title"], json.dumps(a["lines"]), a["entity_id"], a["campaign_id"], a["href"],
             a.get("kind", "condition"), bool(a.get("resolved"))),
            returning=True)
        if row:
            raised.append((row["id"], a))
    if raised:
        people = notify.reach(notify.admin_ids(), "notify_alerts")
        for alert_id, a in raised:
            if a["level"] == "info":
                continue  # shown in the console only
            for uid, channel in people:
                notify.queue(uid, channel, "alert", a["title"], a["lines"], notify.link(a["href"] or "/home.html"),
                             "Open in the console", ref=str(alert_id), dedupe_key=f"alert:{alert_id}:{uid}")
    return raised


def open_alerts(scope_ids=None):
    """What Home → Needs attention shows: the newest open alert per rule and thing."""
    rows = db.query("SELECT DISTINCT ON (rule, entity_id) id, rule, level, title, lines, entity_id, campaign_id, href, created_at "
                    "FROM alerts WHERE resolved_at IS NULL AND created_at > now() - interval '3 days' "
                    "ORDER BY rule, entity_id, created_at DESC")
    return [r for r in rows if scope_ids is None or r["campaign_id"] in scope_ids]


def recent(limit=20):
    return db.query("SELECT id, rule, level, title, lines, href, created_at, resolved_at FROM alerts ORDER BY id DESC LIMIT %s", (limit,))
