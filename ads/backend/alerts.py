"""Alerts: rules checked after every pull from Meta. Each alert is raised at most once per
thing (ad, campaign, account) per day, sent to the admins (Telegram, else email), shown on
Home → Needs attention, and closed by itself once the condition is gone.

`evaluate(snapshot, rules, today)` is pure; `snapshot()` reads it from the database. Thresholds
live in Settings → Alerts (settings key `alert_rules`, merged over DEFAULTS).
"""
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account_info
import config
import db
import lead_quality as lq
import notify
import settings_store
import snooze

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
    "outside_edit": {"on": True},
    # D3: a change made from the console looks worse after 3, 7 or 14 complete days (good results are FYI only).
    "change_result": {"on": True},
    # W1b: how the leads the team worked turned out, over the 14 days that end 2 days ago (newer leads had no fair chance).
    "qualified_low": {"on": True, "percent": 20, "min_leads": 10},
    "junk_high": {"on": True, "percent": 30, "min_leads": 10},
    # D1: our stored days differ from Ads Manager's own totals after a night's (or a hand) pull; FYI once, warn when it stays.
    "numbers_off": {"on": True},
    # AM-A: the Mac's Ads Manager link needs a new login, is refused, or stopped finishing its reads (console-wide, account 1).
    "link_down": {"on": True, "hours": 6},
    # AM-B: drafts read from Ads Manager through the link; FYI only, raised and closed by the link's reads.
    "draft_new": {"on": True},
    "draft_problems": {"on": True},
}
# Conditions the link's reads own (am_link_api.push): the hourly run never closes them.
LINK_RULES = {"draft_problems"}
# Events that stay open until someone deals with them get a Done (00-PLAN C16).
DONE_OK = {"outside_edit", "change_result"}
# An outside budget change that broke a money rule closes by itself once the 3-day window has passed.
OUTSIDE_EDIT_OPEN = timedelta(hours=72)
MIN_IMPRESSIONS = 1000  # per 7-day window, before fatigue is judged
QUALITY_DAYS, QUALITY_LAG = 14, 2  # the lead-quality window: 14 days ending 2 days ago
QUALITY_AD_MIN = 5   # an ad is named on a lead-quality alert only with this many leads behind its rate
JUNK_MIN = 3         # never call a campaign junky on fewer junk leads than this


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


def _dry_streak(rows, today):
    """Days in a row, ending yesterday, with spend and no lead (a missing day ends the streak)."""
    by_day = {r["day"]: r for r in rows}
    n = 0
    while n < 14:
        r = by_day.get(today - timedelta(days=n + 1))
        if not r or (r.get("spend_cents") or 0) <= 0 or (r.get("leads") or 0) > 0:
            break
        n += 1
    return n


def lead_quality_groups(rows):
    """{campaign id: {name, leads, worked, qualified, junk, by_ad}} from counted leads (lead_quality.counted()).
    Worked = past New or Lost; qualified = the highest stage reached; junk = lead_quality.is_junk (the one rule)."""
    out = {}
    for r in rows:
        figures = {"leads": 1, "worked": int(lq.is_worked(r)), "qualified": int(r.get("max_stage") in ("qualified", "won")),
                   "junk": int(lq.is_junk(r))}
        c = out.setdefault(r["campaign_id"], {"name": r.get("campaign_name") or r["campaign_id"], "leads": 0, "worked": 0,
                                              "qualified": 0, "junk": 0, "_ads": {}})
        ad = c["_ads"].setdefault(r.get("ad_id"), {"ad_id": r.get("ad_id"), "ad_name": r.get("ad_name"), "leads": 0,
                                                   "worked": 0, "qualified": 0, "junk": 0})
        for k, v in figures.items():
            c[k] += v
            ad[k] += v
    for c in out.values():
        ads = c.pop("_ads")
        c["by_ad"] = sorted((a for key, a in ads.items() if key), key=lambda a: (-a["leads"], str(a["ad_name"] or a["ad_id"])))
    return out


def _share(n, d):
    return n / d * 100


def _whole(pct):
    return math.floor(pct + 0.5)  # 12.5% reads 13%, as people round


def _worst_ad(by_ad, size, bad, total):
    """The ad with the worst rate among those with enough leads behind it, unless it is every lead of the campaign.
    `bad(ad)` = the share that is bad for that ad (lower qualified, higher junk), bigger is worse."""
    judged = [a for a in by_ad if (a.get(size) or 0) >= QUALITY_AD_MIN and (a.get(size) or 0) < total]
    return max(judged, key=lambda a: (bad(a), a[size]), default=None)


def _lead_quality_alerts(lq_snap, rules, add):
    q, j = rules["qualified_low"], rules["junk_high"]
    for cid, c in lq_snap.items():
        href = f"/leads.html?campaign={cid}"
        worked, qualified = c.get("worked") or 0, c.get("qualified") or 0
        if q["on"] and worked and worked >= q["min_leads"] and _share(qualified, worked) < q["percent"]:
            rate = _share(qualified, worked)
            lines = [f"{qualified} of {worked} leads the team worked in the last {QUALITY_DAYS} days {'was' if qualified == 1 else 'were'} "
                     f"qualified. You're alerted below {q['percent']}%."]
            low = _worst_ad(c.get("by_ad") or [], "worked", lambda a: -_share(a["qualified"] or 0, a["worked"]), worked)
            if low:
                lines.append(f"Lowest: “{low['ad_name'] or low['ad_id']}”, {low['qualified'] or 0} of {low['worked']} qualified.")
            lines.append("Cheap leads that don't qualify cost more than they look.")
            add("qualified_low", cid, "warn", f"Only {_whole(rate)}% of leads from “{c['name']}” qualify", lines, cid, href,
                measure=round(rate, 1))
        leads, junk = c.get("leads") or 0, c.get("junk") or 0
        if j["on"] and leads and leads >= j["min_leads"] and junk >= JUNK_MIN and _share(junk, leads) > j["percent"]:
            rate = _share(junk, leads)
            lines = [f"{junk} of {leads} leads in the last {QUALITY_DAYS} days look like junk "
                     "(marked spam or fake, or fake-looking details and never contacted)."]
            high = _worst_ad([a for a in c.get("by_ad") or [] if a.get("junk")], "leads", lambda a: _share(a["junk"], a["leads"]), leads)
            if high:
                lines.append(f"Highest: “{high['ad_name'] or high['ad_id']}”, {high['junk']} of {high['leads']} look like junk.")
            # Every stage (spam is Lost, flagged junk is still New), junk only: the Leads list's junk filter.
            add("junk_high", cid, "warn", f"{_whole(rate)}% of leads from “{c['name']}” look like junk", lines, cid,
                f"{href}&status=all&junk=1", measure=round(rate, 1))


def _numbers_alert(numbers, rule, add, money):
    """D1: only a run that read the ad rows again judges (a Check now reads Meta's totals only); one run off is FYI,
    two in a row need action. The figure a snooze watches is how many days differ."""
    import numbers_check
    s = numbers.get("summary") or {}
    if not rule["on"] or s.get("state") != "off" or numbers.get("kind") not in numbers_check.JUDGED_KINDS:
        return
    lines = [numbers_check.day_line(o, money) for o in (s.get("off") or [])[:1]] + ["We pull these days again every night."]
    add("numbers_off", "account", "warn" if (numbers.get("off_runs") or 0) >= 2 else "info",
        f"Numbers differ from Ads Manager on {numbers_check.day_list(s['off_days'])}", lines, None, "/settings.html#numbers",
        measure=len(s["off_days"]))


def evaluate(snap, rules, today):
    found = []

    def money(cents):
        return account_info.money(cents, snap.get("currency") or "USD", whole=not cents % 100)

    def add(rule, entity, level, title, lines, campaign_id=None, href=None, measure=None):
        # measure: the figure the rule judged (snooze.WORSE), so a snoozed alert can tell "clearly worse".
        found.append({"rule": rule, "entity_id": entity, "key": f"{rule}:{entity}:{today.isoformat()}", "level": level,
                      "title": title, "lines": lines, "campaign_id": campaign_id, "href": href, "measure": measure})

    for ad in snap["ads"]:
        href = f"/ad.html?id={ad['id']}"
        rows = snap["ad_days"].get(ad["id"], [])
        if rules["ad_rejected"]["on"] and ad["effective_status"] in ("DISAPPROVED", "WITH_ISSUES"):
            add("ad_rejected", ad["id"], "bad", f"Meta stopped “{ad['name']}”",
                [f"Status: {ad['effective_status'].replace('_', ' ').lower()}. Open the ad to see why and fix it."], ad["campaign_id"], href,
                measure=2 if ad["effective_status"] == "DISAPPROVED" else 1)
        r = rules["no_delivery"]
        # Today's partial day counts here: an ad first shown today has been seen (audit A3-63).
        seen = _sum(rows, "impressions") or ad.get("today_impressions")
        if r["on"] and ad["effective_status"] == "ACTIVE" and ad["age_hours"] >= r["hours"] and not seen:
            add("no_delivery", ad["id"], "warn", f"“{ad['name']}” is on but nobody has seen it",
                [f"No views {ad['age_hours']:.0f} hours after it went live."], ad["campaign_id"], href, measure=round(ad["age_hours"]))
        r = rules["fatigue"]
        tired = r["on"] and ad["effective_status"] == "ACTIVE" and _fatigue(rows, today, r, (snap.get("reach_7d") or {}).get(ad["id"]))
        if tired:
            freq, drop, rise = tired
            add("fatigue", ad["id"], "warn", f"“{ad['name']}” looks tired",
                [f"People see it about {freq:.1f} times a week; clicks are down {drop:.0f}% and cost per 1,000 views up {rise:.0f}% since its first week.",
                 "Time for a fresh version."], ad["campaign_id"], href, measure=round(freq, 1))

    for c in snap["campaigns"]:
        budget = c.get("daily_budget_cents") or 0
        rows = snap["camp_days"].get(c["id"], [])
        week = _last(rows, today, 7)
        href = "/performance.html"
        r = rules["day_overspend"]
        spent_today = (snap.get("today_spend") or {}).get(c["id"], 0)
        if r["on"] and budget and spent_today > r["times"] * budget:
            add("day_overspend", c["id"], "info", f"{money(spent_today)} spent today on a {money(budget)} daily budget",
                ["Meta may spend up to 1.75× the daily budget on one day and evens it out over the week. Just a heads-up."], c["id"], href,
                measure=spent_today)
        r = rules["week_overspend"]
        if r["on"] and budget and len(week) == 7 and _sum(week, "spend_cents") > r["times"] * budget:
            add("week_overspend", c["id"], "warn", f"{money(_sum(week, 'spend_cents'))} spent in 7 days on a {money(budget)} daily budget",
                [f"That's more than {r['times']:g}× the daily budget. Check the budget and the schedule."], c["id"], href,
                measure=_sum(week, "spend_cents"))
        r = rules["cpl_high"]
        spend, leads = _sum(week, "spend_cents"), _sum(week, "leads")
        if r["on"] and r["target_cents"] and spend >= 3 * r["target_cents"]:
            cpl = spend / leads if leads else None
            if cpl is None or cpl > r["times"] * r["target_cents"]:
                add("cpl_high", c["id"], "warn",
                    f"Leads cost {money(cpl) if cpl else 'more than ' + money(spend)} each in “{c['name']}”",
                    [f"Last 7 days: {money(spend)} spent, {leads} lead{'s' if leads != 1 else ''}; your target is {money(r['target_cents'])}."], c["id"], href,
                    measure=round(cpl) if cpl else spend)
        r = rules["no_leads"]
        streak = _dry_streak(rows, today)
        if r["on"] and streak >= r["days"]:
            recent = _last(rows, today, streak)
            add("no_leads", c["id"], "bad", f"No leads for {streak} days in “{c['name']}”",
                [f"{money(_sum(recent, 'spend_cents'))} spent since {recent[0]['day'].strftime('%b %-d')} and not one lead. Check the form and the ads."],
                c["id"], href, measure=streak)

    r = rules["spend_cap"]
    cap = snap.get("cap")
    if r["on"] and cap and cap.get("limit_cents"):
        used = cap["spent_cents"] / cap["limit_cents"] * 100
        if used >= r["percent"]:
            done = used >= 100
            add("spend_cap", "account", "bad" if done else "warn",
                "The account spending limit is reached" if done else f"{used:.0f}% of the account spending limit is used",
                [f"{money(cap['spent_cents'])} of {money(cap['limit_cents'])}. Every ad stops when it's reached. Change the limit in Settings → Targets, or ask Claude."],
                None, "/settings.html#spend-limit", measure=round(used, 1))

    p = snap.get("pacing") or {}
    r = rules["cap_soon"]
    if r["on"] and p.get("cap_days") is not None and p["cap_days"] <= r["days"] and not (cap and cap["spent_cents"] >= cap["limit_cents"]):
        when = date.fromisoformat(p["cap_date"]).strftime("%a %b %-d")
        add("cap_soon", "account", "warn", f"The spending limit runs out in about {p['cap_days']} day{'s' if p['cap_days'] != 1 else ''}",
            [f"At the current pace every ad stops around {when}. Change the limit in Settings → Targets, or ask Claude."],
            None, "/settings.html#spend-limit", measure=p["cap_days"])
    r = rules["pace_over"]
    if r["on"] and p.get("vs_target_pct") is not None and p["vs_target_pct"] > r["percent"]:
        add("pace_over", "account", "warn", f"This month is heading {p['vs_target_pct']}% over your target",
            [f"At the current pace the month ends near {money(p['projected_cents'])} against {money(p['target_cents'])}."],
            None, "/performance.html", measure=p["vs_target_pct"])

    r = rules["tracking"]
    two = [today - timedelta(days=1), today - timedelta(days=2)]
    meta = sum(snap["meta_leads"].get(d, 0) for d in two)
    inbox = sum(snap["inbox_leads"].get(d, 0) for d in two)
    if r["on"] and meta >= 2 and inbox == 0:
        add("tracking", "account", "bad", "Leads aren't reaching your leads list",
            [f"Meta counted {meta} leads in the last two days, but none arrived here. Check the Page connection in Settings → Meta."],
            None, "/settings.html#meta", measure=meta)

    r = rules["events_quiet"]
    t = snap.get("tracking") or {}
    if r["on"] and t.get("state") == "quiet":
        add("events_quiet", "account", "warn", "Meta stopped receiving lead stages",
            [t.get("headline") or "Nothing has reached the dataset for two days.", "See Settings → Tracking health."], None, "/settings.html#tracking")

    _lead_quality_alerts(snap.get("lead_quality") or {}, rules, add)

    _numbers_alert(snap.get("numbers") or {}, rules["numbers_off"], add, money)

    for a in link_alert(snap.get("link"), rules["link_down"], today):
        add(a["rule"], a["entity_id"], a["level"], a["title"], a["lines"], None, a["href"], measure=a["measure"])

    r = rules["stale_data"]
    age = snap.get("last_pull_age_h")
    if r["on"] and snap.get("connected") and age is not None and age > r["hours"]:
        add("stale_data", "account", "warn", "Meta hasn't answered for a while",
            [f"The last pull from Meta was {age:.0f} hours ago. The token or the connection may need a look in Settings → Meta."],
            None, "/settings.html#meta", measure=round(age, 1))
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
        # Meta counts a repeat fill too, but never a form filled in without an ad (L2): repeats stay, organic goes.
        "SELECT (created_time AT TIME ZONE %s)::date AS day, COUNT(*) /* every fill */ AS n FROM leads WHERE NOT is_test AND NOT is_organic "
        "AND created_time > now() - interval '4 days' GROUP BY 1", (account_info.tz_name(),))}
    # W1b: counted leads of the running campaigns from the 14 days that end 2 days ago, by the account's calendar.
    start = datetime.combine(today - timedelta(days=QUALITY_DAYS + QUALITY_LAG), datetime.min.time(), tzinfo=tz)
    end = datetime.combine(today - timedelta(days=QUALITY_LAG), datetime.min.time(), tzinfo=tz)
    quality_rows = db.query(f"""SELECT l.campaign_id, c.name AS campaign_name, l.ad_id, l.ad_name, l.max_stage, l.status, l.lost_reason,
                                       l.junk_flags, l.junk_dismissed
                                FROM leads l JOIN campaigns c ON c.id = l.campaign_id AND c.effective_status = 'ACTIVE'
                                WHERE {lq.counted()} AND l.created_time >= %s AND l.created_time < %s""", (start, end))
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
        "lead_quality": lead_quality_groups(quality_rows),
        "numbers": numbers_state(),
        "link": link_snapshot(now),
    }


def link_alert(link, rule, today):
    """AM-A: the link_down alert from link_snapshot() (None outside account 1), as found-dicts."""
    import am_link
    if not link or not rule["on"]:
        return []
    a = am_link.link_down(link["state"], link["since"], link["mac_online"], link["now"], rule["hours"])
    if not a:
        return []
    return [{"rule": "link_down", "entity_id": "console", "key": f"link_down:console:{today.isoformat()}", "level": a["level"],
             "title": a["title"], "lines": a["lines"], "campaign_id": None, "href": "/settings.html#am-link", "measure": a["measure"]}]


def link_snapshot(now):
    """What link_alert judges: the console's link, raised under account 1 only (the Mac and its login are Eugene's)."""
    import account_ctx
    import desk_api
    if account_ctx.current() != account_ctx.DEFAULT:
        return None
    row = db.query("SELECT state, last_ok_at, connected_at FROM am_link WHERE id = 1", one=True)
    if not row:
        return None
    return {"state": row["state"], "since": row["last_ok_at"] or row["connected_at"], "mac_online": desk_api.bridge_status()["online"],
            "now": now}


def numbers_state():
    """D1: the verdict on the whole check window that the newest finished run left (no Meta call), the kind of that run,
    and how many runs in a row left the window off. A pull of one day never closes an alert for the other days."""
    import numbers_check
    v = numbers_check.verdict()
    if not v or not v.get("summary"):
        return {}
    return {"summary": v["summary"], "kind": v["kind"], "off_runs": int(settings_store.get("numbers_off_runs") or 0)}


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
    raised = raise_found(found, now)
    opened = db.query("SELECT id, rule, entity_id FROM alerts WHERE resolved_at IS NULL AND kind = 'condition'")
    for alert_id in to_resolve(opened, found, snap):
        db.execute("UPDATE alerts SET resolved_at = now() WHERE id = %s", (alert_id,))
    db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'outside_edit' AND kind = 'event' AND resolved_at IS NULL "
               "AND created_at < %s", (now - OUTSIDE_EDIT_OPEN,))
    # Snoozes of problems that are gone end (a return alerts as usual), unless Meta's data is stale.
    age = snap.get("last_pull_age_h")
    stale = age is not None and age > rules["stale_data"]["hours"]
    live = db.query("SELECT id, rule, entity_id, mode, until FROM alert_snoozes WHERE ended_at IS NULL")
    for sid, reason in snooze.sweep(live, {(a["rule"], a["entity_id"]) for a in found}, now, stale, unjudged(snap)):
        end_snooze(sid, reason)
    return [a["key"] for _, a in raised]


def unjudged(snap):
    """Rules that couldn't be judged this time: their open alerts and snoozes stay as they are."""
    out = {"fatigue"} if snap.get("reach_7d") is None else set()
    n = snap.get("numbers") or {}
    # A Check now that finds days off neither raises nor closes: the next night or pull says whether they stay off.
    if n.get("kind") == "check" and (n.get("summary") or {}).get("state") == "off":
        out.add("numbers_off")
    return out


def end_snooze(snooze_id, reason, by=None):
    return db.execute("UPDATE alert_snoozes SET ended_at = now(), end_reason = %s, ended_by = %s WHERE id = %s AND ended_at IS NULL "
                      "RETURNING id, rule, entity_id", (reason, by, snooze_id), returning=True)


def live_snoozes(rules=None):
    """{(rule, entity_id): snooze} for the snoozes in force (one per problem), with who set them."""
    rows = db.query("""SELECT s.id, s.rule, s.entity_id, s.campaign_id, s.mode, s.until, s.baseline::float8 AS baseline,
                                s.baseline_level, s.alert_id, s.created_at, u.name AS by
                         FROM alert_snoozes s LEFT JOIN users u ON u.id = s.created_by
                         WHERE s.ended_at IS NULL AND (%s::text[] IS NULL OR s.rule = ANY(%s))""", (rules, rules))
    return {(r["rule"], r["entity_id"]): r for r in rows}


def snooze_view(s, tz):
    """What the Inbox, Today and Settings show of a snooze."""
    return {"id": s["id"], "mode": s["mode"], "until": s["until"].isoformat() if s.get("until") else None,
            "by": s.get("by"), "words": snooze.snooze_words(s, tz)}


def with_snoozes(found, now):
    """The alerts as they are stored: a snoozed problem quietly, or as a wake-up when it got worse or its day
    came (the snooze ends then)."""
    rules = sorted({a["rule"] for a in found if a.get("kind", "condition") == "condition"})
    live = live_snoozes(rules) if rules else {}
    if not live:
        return found
    tz = account_info.tz()
    currency = account_info.currency()
    money = lambda c: account_info.money(round(c), currency, whole=not round(c) % 100)  # noqa: E731
    out = []
    for a in found:
        s = live.get((a["rule"], a["entity_id"])) if a.get("kind", "condition") == "condition" and not a.get("resolved") else None
        if not s:
            out.append(a)
            continue
        verdict = snooze.decide(s, a, now)
        if verdict != "quiet":
            end_snooze(s["id"], "worse" if verdict == "wake_worse" else "expired")
        out.append(snooze.apply(a, s, verdict, tz, money))
    return out


def mark_done(alert_id):
    """Done on an owner-closed event (DONE_OK): it leaves Needs action. Returns the alert, or None."""
    return db.execute("UPDATE alerts SET resolved_at = now() WHERE id = %s AND rule = ANY(%s) AND kind = 'event' "
                      "AND resolved_at IS NULL RETURNING id, rule, title", (alert_id, sorted(DONE_OK)), returning=True)


def to_resolve(opened, found, snap):
    """Open condition alerts whose condition is gone. Fatigue can't be judged while Meta doesn't answer
    unique reach (reach_7d None, e.g. a rate-limit cooldown): those alerts stay open, or one hiccup would
    close them for the rest of the day (the dedupe key is per day)."""
    live = {(a["rule"], a["entity_id"]) for a in found}
    skip = unjudged(snap) | LINK_RULES
    return [r["id"] for r in opened if (r["rule"], r["entity_id"]) not in live and r["rule"] not in skip]


def _insert(a, key):
    return db.execute(
        "INSERT INTO alerts (rule, dedupe_key, level, title, lines, entity_id, campaign_id, href, kind, resolved_at, measure, quiet) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END, %s, %s) "
        "ON CONFLICT (account_id, dedupe_key) DO NOTHING RETURNING id",
        (a["rule"], key, a["level"], a["title"], json.dumps(a["lines"]), a["entity_id"], a["campaign_id"], a["href"],
         a.get("kind", "condition"), bool(a.get("resolved")), a.get("measure"), bool(a.get("quiet"))),
        returning=True)


def raise_found(found, now=None):
    """Store new alerts (once per dedupe key) and tell the admins; info alerts and snoozed (quiet) ones stay in
    the console. A wake-up takes the day's key, or a key of its own when a quiet row already holds it."""
    raised = []
    for a in with_snoozes(found, now or datetime.now(timezone.utc)):
        row = _insert(a, a["key"])
        if not row and a.get("wake_key"):
            row = _insert(a, a["wake_key"])
        if row:
            raised.append((row["id"], a))
    if raised:
        people = notify.reach(notify.account_admin_ids(), "notify_alerts")
        for alert_id, a in raised:
            if a["level"] == "info" or a.get("quiet"):
                continue  # shown in the console only
            for uid, channel in people:
                notify.queue(uid, channel, "alert", a["title"], a["lines"], notify.link(a["href"] or "/home.html"),
                             a.get("button") or "Open in the console", ref=str(alert_id), dedupe_key=f"alert:{alert_id}:{uid}")
    return raised


def open_alerts(scope_ids=None):
    """What Home → Needs attention shows: the newest open alert per rule and thing."""
    rows = db.query("SELECT DISTINCT ON (rule, entity_id) id, rule, level, title, lines, entity_id, campaign_id, href, created_at "
                    "FROM alerts WHERE resolved_at IS NULL AND created_at > now() - interval '3 days' "
                    "ORDER BY rule, entity_id, created_at DESC")
    return [r for r in rows if scope_ids is None or r["campaign_id"] in scope_ids]


def recent(limit=20):
    return db.query("SELECT id, rule, level, title, lines, href, created_at, resolved_at FROM alerts ORDER BY id DESC LIMIT %s", (limit,))


def snoozed_now():
    """Settings → Alerts → Snoozed now: each snooze in force with its problem's newest alert."""
    tz = account_info.tz()
    out = []
    for s in sorted(live_snoozes().values(), key=lambda x: x["created_at"], reverse=True):
        a = db.query("SELECT id, title, href FROM alerts WHERE rule = %s AND entity_id = %s ORDER BY id DESC LIMIT 1",
                     (s["rule"], s["entity_id"]), one=True)
        if a:
            out.append({**snooze_view(s, tz), "alert_id": a["id"], "title": a["title"], "href": a["href"], "rule": s["rule"]})
    return out
