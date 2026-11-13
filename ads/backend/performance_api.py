"""Performance view: spend, leads and cost per lead from Meta, joined with what the
team did with those leads in the inbox (qualified / won)."""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import config
import account_info
import db
import lead_quality as lq
import followup
import insights
import pacing
import ranges
import meta_client
import settings_store
from auth import admin_required, current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("performance", __name__, url_prefix="/api/performance")

RANGE_KEYS = ("today", "7", "14", "30", "mtd", "lastmonth")
BAD_STATUSES = {"DISAPPROVED", "WITH_ISSUES"}


def _scope_sql(user, column):
    ids = visible_campaign_ids(user)
    if ids is None:
        return "TRUE", []
    return f"{column} = ANY(%s)", [ids]


def cap_snapshot():
    raw = settings_store.get("account_snapshot")
    if not raw:
        return None
    snap = json.loads(raw)
    cap = snap.get("spend_cap_cents")
    spent = snap.get("amount_spent_cents") or 0
    return {"limit_cents": cap, "spent_cents": spent,
            "remaining_cents": None if cap is None else max(cap - spent, 0),
            "currency": snap.get("currency"), "timezone": snap.get("timezone")}


def periods(today, days):
    """(start, end) of the last `days` complete days, and of the same length just before.
    Complete days only: today is partial and conversions report late."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return (start, end), (start - timedelta(days=days), start - timedelta(days=1))


def campaign_choices(user, start, end):
    """Campaigns the person can see, with spend in the period, for the Results picker."""
    where, params = _scope_sql(user, "c.id")
    return [{**r, "spend_cents": int(r["spend_cents"])} for r in db.query(
        f"""SELECT c.id, c.name, c.effective_status,
                   COALESCE((SELECT SUM(spend_cents) FROM ad_daily d WHERE d.campaign_id = c.id AND d.day BETWEEN %s AND %s), 0) AS spend_cents
            FROM campaigns c WHERE {where} AND c.effective_status <> 'DELETED'
            ORDER BY spend_cents DESC, c.name""", [start, end] + params)]


def window_totals(user, start, end, campaign_id=None):
    """Spend, impressions, link clicks and Meta's leads over the window, for the campaigns the person can see
    (Results' totals and the All accounts rows)."""
    where, params = _scope_sql(user, "d.campaign_id")
    if campaign_id:
        where, params = f"({where}) AND d.campaign_id = %s", params + [campaign_id]
    row = db.query(
        f"""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                   COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS leads
            FROM ad_daily d WHERE day BETWEEN %s AND %s AND {where}""",
        [start, end] + params, one=True,
    )
    return {k: int(v) for k, v in row.items()}


def overview_data(user, days, campaign_id=None, span=None, live=False, settled=None):
    """Everything the Performance page shows; also the AI desk's snapshot. `campaign_id`
    narrows it to one campaign the person can see; `span` gives explicit windows, for months.
    live (screens only, FU-C): the window may include today, read from Meta first; `settled` then names its
    complete days, whose totals come back as `compare_now` (what "vs before" compares). The snapshot never
    passes live: Claude judges complete days."""
    today = account_info.today()
    (start, end), (prev_start, prev_end) = span or periods(today, days)
    where, params = _scope_sql(user, "d.campaign_id")
    if campaign_id:
        where, params = f"({where}) AND d.campaign_id = %s", params + [campaign_id]
    live_read = insights.read_today() if live and ranges.includes_today(start, end, today) else None

    totals = window_totals(user, start, end, campaign_id)
    by_day = db.query(
        f"""SELECT day, SUM(spend_cents) AS spend_cents, SUM(leads) AS leads, SUM(impressions) AS impressions
            FROM ad_daily d WHERE day BETWEEN %s AND %s AND {where} GROUP BY day ORDER BY day""",
        [start, end] + params,
    )
    filled = {r["day"].isoformat(): r for r in by_day}
    series = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        r = filled.get(d) or {}
        series.append({"day": d, "spend_cents": int(r.get("spend_cents") or 0), "leads": int(r.get("leads") or 0),
                       **({"partial": True} if d == today.isoformat() else {})})

    lwhere, lparams = where.replace("d.campaign_id", "l.campaign_id"), params
    quality = db.query(
        f"""SELECT l.ad_id,
                   COUNT(*) AS inbox,
                   COUNT(*) FILTER (WHERE {lq.qualified()}) AS qualified,
                   COUNT(*) FILTER (WHERE {lq.won()}) AS won,
                   COUNT(*) FILTER (WHERE l.booked_at IS NOT NULL) AS booked,
                   COUNT(*) FILTER (WHERE l.meeting_status = 'held') AS held,
                   COUNT(*) FILTER (WHERE l.meeting_status = 'no_show') AS no_show
            FROM leads l
            WHERE {lq.counted()} AND (l.created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {lwhere}
            GROUP BY l.ad_id""",
        [account_info.tz_name(), start, end] + lparams,
    )
    q_by_ad = {r["ad_id"]: r for r in quality}

    before = db.query(
        f"""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(leads),0) AS leads
            FROM ad_daily d WHERE day BETWEEN %s AND %s AND {where}""",
        [prev_start, prev_end] + params, one=True)
    before_q = db.query(
        f"""SELECT COUNT(*) FILTER (WHERE {lq.qualified()}) AS qualified,
                  COUNT(*) FILTER (WHERE l.booked_at IS NOT NULL) AS booked FROM leads l
            WHERE {lq.counted()} AND (l.created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {lwhere}""",
        [account_info.tz_name(), prev_start, prev_end] + lparams, one=True)

    per_ad = db.query(
        f"""SELECT a.id, a.campaign_id, COALESCE(a.name, MAX(d.ad_name)) AS name, a.effective_status, a.thumbnail_url,
                   COALESCE(SUM(d.spend_cents),0) AS spend_cents, COALESCE(SUM(d.impressions),0) AS impressions,
                   COALESCE(SUM(d.link_clicks),0) AS link_clicks, COALESCE(SUM(d.leads),0) AS leads
            FROM ads a LEFT JOIN ad_daily d ON d.ad_id = a.id AND d.day BETWEEN %s AND %s
            WHERE {where.replace('d.campaign_id', 'a.campaign_id')}
            GROUP BY a.id, a.campaign_id, a.name, a.effective_status, a.thumbnail_url
            ORDER BY spend_cents DESC, a.name""",
        [start, end] + params,
    )
    for ad in per_ad:
        q = q_by_ad.get(ad["id"], {})
        ad["qualified"] = int(q.get("qualified") or 0)
        ad["won"] = int(q.get("won") or 0)
        ad["inbox"] = int(q.get("inbox") or 0)
        ad["booked"] = int(q.get("booked") or 0)

    qualified_total = sum(int(r["qualified"]) for r in quality)
    booked = {k: sum(int(r[k]) for r in quality) for k in ("booked", "held", "no_show")}
    alerts = []
    for ad in per_ad:
        if ad["effective_status"] in BAD_STATUSES:
            alerts.append({"level": "bad", "text": f"Meta stopped “{ad['name']}”: {ad['effective_status'].replace('_', ' ').lower()}. Open it in Ads Manager to see why."})
    cap = cap_snapshot() if user["role"] == "admin" else None
    if cap and cap["limit_cents"]:
        used = cap["spent_cents"] / cap["limit_cents"]
        if used >= 0.8:
            alerts.append({"level": "warn" if used < 1 else "bad",
                           "text": ("The account spending limit is almost used up. Ads pause when it's reached."
                                    if used < 1 else "The account spending limit is reached, so every ad is paused.")
                           + " Change the limit in Settings → Targets, or ask Claude.",
                           "href": "/settings.html#spend-limit", "link": "Change the limit"})

    # The real yesterday (account clock), whatever the window: "Last month" ends weeks ago (audit A3-61).
    y = account_info.yesterday()
    two = {r["day"]: r for r in db.query(
        f"""SELECT day, SUM(spend_cents) AS spend_cents, SUM(leads) AS leads FROM ad_daily d
            WHERE day BETWEEN %s AND %s AND {where} GROUP BY day""", [y - timedelta(days=1), y] + params)}
    last, prev = ({"day": d.isoformat(), "spend_cents": int((two.get(d) or {}).get("spend_cents") or 0),
                   "leads": int((two.get(d) or {}).get("leads") or 0)} for d in (y, y - timedelta(days=1)))
    import numbers_check
    # D1: where these numbers come from, how fresh, whether Ads Manager agrees; Meta's leads next to the leads received.
    source = numbers_check.source(user, start, end, meta_leads=int(totals["leads"]), received=sum(int(r["inbox"]) for r in quality),
                                  scoped=bool(campaign_id) or visible_campaign_ids(user) is not None, live=live_read)
    compare_now = None
    if settled:
        now_t = window_totals(user, *settled, campaign_id)
        now_q = db.query(
            f"""SELECT COUNT(*) FILTER (WHERE {lq.qualified()}) AS qualified,
                      COUNT(*) FILTER (WHERE l.booked_at IS NOT NULL) AS booked FROM leads l
                WHERE {lq.counted()} AND (l.created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {lwhere}""",
            [account_info.tz_name(), *settled] + lparams, one=True)
        compare_now = {"start": settled[0].isoformat(), "end": settled[1].isoformat(), "spend_cents": now_t["spend_cents"],
                       "leads": now_t["leads"], "qualified": int(now_q["qualified"] or 0), "booked": int(now_q["booked"] or 0)}
    return {
        "compare_now": compare_now,
        "source": source,
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "yesterday": {"day": last["day"], "spend_cents": last["spend_cents"], "leads": last["leads"],
                      "prev_spend_cents": prev["spend_cents"], "prev_leads": prev["leads"]},
        "totals": {**{k: int(v) for k, v in totals.items()}, "qualified": qualified_total, **booked},
        "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat(),
                     "spend_cents": int(before["spend_cents"]), "leads": int(before["leads"]),
                     "qualified": int(before_q["qualified"] or 0), "booked": int(before_q["booked"] or 0)},
        # Booked calls (L1) show only once the account has booked one with a real lead.
        "tracks_bookings": followup.tracks_bookings(),
        "series": series,
        "ads": per_ad,
        "cap": cap,
        "alerts": alerts,
        "last_sync": settings_store.get("last_performance_sync"),
    }


def daily_budget_cents(scope_ids=None):
    """What the campaigns that are on may spend a day: each campaign's own budget, else its active ad
    sets' (Today, Results pacing and the alerts count it the same way; audit A3-59)."""
    cw, params = ("TRUE", []) if scope_ids is None else ("c.id = ANY(%s)", [scope_ids])
    return int(db.query(f"""SELECT COALESCE(SUM(COALESCE(c.daily_budget_cents,
                                (SELECT SUM(daily_budget_cents) FROM adsets s WHERE s.campaign_id = c.id AND s.effective_status = 'ACTIVE'))), 0) AS c
                             FROM campaigns c WHERE c.effective_status = 'ACTIVE' AND {cw}""", params, one=True)["c"] or 0)


def pacing_data(scope_ids=None):
    """This month's pace for the campaigns in scope (None = the whole account, with the
    monthly target and the spending limit, which are account-wide)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    today = datetime.now(timezone.utc).astimezone(account_info.tz()).date()
    where, params = ("TRUE", []) if scope_ids is None else ("campaign_id = ANY(%s)", [scope_ids])
    month_days = [(r["day"], int(r["c"])) for r in db.query(
        f"SELECT day, SUM(spend_cents) AS c FROM ad_daily WHERE day >= %s AND day < %s AND {where} GROUP BY day",
        [today.replace(day=1), today] + params)]
    spent = {r["day"]: int(r["c"]) for r in db.query(
        f"SELECT day, SUM(spend_cents) AS c FROM ad_daily WHERE day >= %s AND day < %s AND {where} GROUP BY day",
        [today - timedelta(days=7), today] + params)}
    first = db.query(f"SELECT MIN(day) AS d FROM ad_daily WHERE spend_cents > 0 AND {where}", params, one=True)["d"]
    recent = pacing.last_days(spent, today, first)
    budget = daily_budget_cents(scope_ids)
    snap = (insights.today_for(settings_store.get("today_snapshot"), today) or {}).get("campaigns", {})
    so_far = sum(v["spend_cents"] for cid, v in snap.items() if scope_ids is None or cid in scope_ids)
    account = scope_ids is None
    cap = cap_snapshot() if account else None
    target = settings_store.get("monthly_target_cents") if account else None
    return pacing.pace(today, month_days, recent, budget, int(target) if target else None,
                       cap["remaining_cents"] if cap and cap["limit_cents"] else None, so_far)


def window_args(args, live=False):
    """(key, start, end) from ?range=, or ?range=custom&start=&end= (a day linked from Settings → Numbers vs Ads Manager).
    live: the window a screen shows, today so far included (FU-C)."""
    key = args.get("range", "7")
    if key == "custom" and args.get("start"):
        start, end = ranges.window("custom", account_info.today(), args.get("start"), args.get("end") or args.get("start"), live=live)
        return key, start, end
    key = key if key in RANGE_KEYS else "7"
    return (key, *ranges.window(key, account_info.today(), live=live))


def hours_before(campaign_ids, now=None):
    """Yesterday up to the hour it is now (account clock), for the campaigns given (None: all): what Today is
    compared with. None when Meta's hourly totals aren't there."""
    rows = insights.yesterday_hours("campaign")
    if rows is None:
        return None
    hour = account_info.local_now(now).hour
    mine = [r for r in rows if campaign_ids is None or r.get("campaign_id") in campaign_ids]
    return {**ranges.same_hours(mine, hour), "by": ranges.by_hour_words(hour)}


def compare_info(plan, key):
    """What "vs before" means for this window, in the page's words (FU-C)."""
    before = plan["before"]
    out = {"mode": plan["mode"], "note": plan["note"], "before_label": ranges.label(*before),
           "before_days": (before[1] - before[0]).days + 1}
    if plan["mode"] == "days" and plan["note"]:
        out["now_label"] = ranges.label(*plan["now"])
    return out


@bp.get("")
@login_required
def overview():
    user = current_user()
    key, start, end = window_args(request.args, live=True)
    days = (end - start).days + 1
    campaign_id = request.args.get("campaign") or None
    if campaign_id:
        ids = visible_campaign_ids(user)
        if ids is not None and campaign_id not in ids:
            return api_error("Not found", 404)
    today = account_info.today()
    plan = ranges.compare_plan(key, start, end, today)
    out = overview_data(user, days, campaign_id, span=((start, end), plan["before"]), live=True,
                        settled=plan["now"] if plan["note"] else None)
    out["compare"] = compare_info(plan, key)
    if plan["mode"] == "hours":
        ids = visible_campaign_ids(user)
        scope = [campaign_id] if campaign_id else ids
        hrs = hours_before(scope)
        out["compare"]["by"] = hrs["by"] if hrs else None
        out["previous"] = {**out["previous"], **({"spend_cents": hrs["spend_cents"], "leads": hrs["leads"]} if hrs else
                                                 {"spend_cents": None, "leads": None}), "qualified": None, "booked": None}
    import status_history
    out.update(status_history.marks_payload(user, {"campaigns": [campaign_id], "ad_meta_only": True} if campaign_id
                                            else {"account": True, "ad_meta_only": True}, start, end))
    out["range"].update(key=key, label=ranges.label(start, end, today=today))
    out["campaigns"] = campaign_choices(user, start, end)
    out["campaign"] = campaign_id
    out["pacing"] = pacing_data(visible_campaign_ids(user))
    out["can_set_target"] = user["role"] == "admin"
    return jsonify(out)


QUALITY_BY = ("ad", "form", "answer")


def question_label(key):
    """'what_kind_of_business_do_you_run?' → 'What kind of business do you run?'"""
    text = str(key or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Question"


def questions_in(leads):
    """The form questions seen in these leads (contact fields left out), with how many different answers each has."""
    seen = {}
    for l in leads:
        for a in l.get("answers") or []:
            name = a.get("name")
            if not name or str(name).strip().lower() in lq.CONTACT_FIELDS:
                continue
            value = ", ".join(str(v) for v in a.get("values") or [] if v not in (None, "")).strip().lower()
            seen.setdefault(name, set()).add(value)
    return [{"name": k, "label": question_label(k), "distinct": len(v)} for k, v in seen.items()]


@bp.get("/quality")
@login_required
def quality():
    """Results → Lead quality (L2): what happened to the leads from each ad, form or answer over the page's range
    and campaign. Counts only (clients see it too): no names, emails, phones or notes."""
    import lead_quality_store
    user = current_user()
    key, start, end = window_args(request.args, live=True)
    ids = visible_campaign_ids(user)
    campaign_id = request.args.get("campaign") or None
    if campaign_id and ids is not None and campaign_id not in ids:
        return api_error("Not found", 404)
    by = request.args.get("by") if request.args.get("by") in QUALITY_BY else "ad"
    leads = lead_quality_store.leads_for_window(ids, start, end, campaign_id)
    where, params = _scope_sql(user, "d.campaign_id")
    if campaign_id:
        where, params = f"{where} AND d.campaign_id = %s", params + [campaign_id]

    def spent_in(a, b):
        return db.query(f"""SELECT d.ad_id, COALESCE(MAX(a.name), MAX(d.ad_name)) AS name, MAX(a.effective_status) AS status,
                                   COALESCE(SUM(d.spend_cents), 0) AS spend_cents, COALESCE(SUM(d.leads), 0) AS leads
                            FROM ad_daily d LEFT JOIN ads a ON a.id = d.ad_id
                            WHERE d.day BETWEEN %s AND %s AND {where} GROUP BY d.ad_id""", [a, b] + params)
    spent = spent_in(start, end)
    ad_spend = {r["ad_id"]: int(r["spend_cents"]) for r in spent}
    with_leads = {l["ad_id"] for l in leads}
    # A deleted ad shows only when it brought leads in the range; its spend stays in the totals.
    shown = {k: v for k, v in ad_spend.items() if k in with_leads or next(r["status"] for r in spent if r["ad_id"] == k) != "DELETED"}
    questions = questions_in(leads)
    question = request.args.get("question") if by == "answer" else None
    if by == "answer" and question not in {q["name"] for q in questions}:
        fits = [q for q in questions if q["distinct"] <= lq.ANSWER_GROUPS_MAX]
        question = (fits or questions or [{"name": None}])[0]["name"]
    spend = shown if by == "ad" else lq.form_spend(leads, ad_spend) if by == "form" else {}
    target = settings_store.get("kpi_target_cents")
    target = int(target) if target else None
    out = lq.summarize(leads, spend, by, question, target, meta_leads=sum(int(r["leads"]) for r in spent),
                       total_spend_cents=sum(ad_spend.values()), labels={r["ad_id"]: r["name"] for r in spent} if by == "ad" else None)
    currency = account_info.currency()
    # The verdict judges complete days only (FU-C): today's leads and spend are still coming in.
    today = account_info.today()
    part = ranges.settled(start, end, today)
    judged = out
    if part is None:
        verdict = {"name": None, "text": "No verdict for today alone: lead quality is judged on complete days only."}
    else:
        if part != (start, end):
            p_spent = spent_in(*part)
            p_spend = {r["ad_id"]: int(r["spend_cents"]) for r in p_spent}
            p_leads = lead_quality_store.leads_for_window(ids, *part, campaign_id)
            p_with = {l["ad_id"] for l in p_leads}
            p_shown = {k: v for k, v in p_spend.items() if k in p_with or next(r["status"] for r in p_spent if r["ad_id"] == k) != "DELETED"}
            judged = lq.summarize(p_leads, p_shown if by == "ad" else lq.form_spend(p_leads, p_spend) if by == "form" else {}, by, question,
                                  target, meta_leads=sum(int(r["leads"]) for r in p_spent), total_spend_cents=sum(p_spend.values()),
                                  labels={r["ad_id"]: r["name"] for r in p_spent} if by == "ad" else None)
        verdict = lq.verdict(judged, target, currency)
    out.update(verdict=verdict, best=judged.get("best") if part else None,
               verdict_through=part[1].isoformat() if part and part[1] < end else None, today_only=part is None,
               junk_note=lq.junk_note(out["totals"], currency), questions=questions,
               reasons=[{"value": k, "label": label} for k, label, _ in lq.LOST_REASONS], range={"start": start.isoformat(), "end": end.isoformat()})
    return jsonify(out)


@bp.put("/target")
@admin_required
def set_target():
    raw = (request.get_json(silent=True) or {}).get("dollars")
    if raw in (None, ""):
        settings_store.set("monthly_target_cents", None)
    else:
        try:
            cents = round(float(raw) * 100)
        except (TypeError, ValueError):
            return api_error("Type the monthly amount in dollars, like 600", 400, field="dollars")
        if cents <= 0:
            return api_error("Type the monthly amount in dollars, like 600", 400, field="dollars")
        settings_store.set("monthly_target_cents", str(cents))
    log_activity("settings.monthly_target", details={"cents": settings_store.get("monthly_target_cents")})
    return jsonify(pacing_data(None))


@bp.post("/sync")
@admin_required
def sync_now():
    import account_ctx
    import refresh_api
    # The account's pull lock (D1): a Refresh or a numbers pull finishes first (waited for up to 30 s).
    with refresh_api.holding_pull_lock(account_ctx.current(), wait=30) as mine:
        if not mine:
            return api_error("Already pulling from Meta, one moment", 409, code="busy")
        try:
            result = insights.sync_all(days=30)
        except meta_client.MetaError as exc:
            return api_error(str(exc), 400)
    log_activity("sync.performance", details=result)
    return jsonify(result)


@bp.get("/cap")
@admin_required
def cap():
    return jsonify(cap_snapshot())
