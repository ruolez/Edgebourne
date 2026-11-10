"""Performance view: spend, leads and cost per lead from Meta, joined with what the
team did with those leads in the inbox (qualified / won)."""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import config
import db
import insights
import pacing
import meta_client
import settings_store
from auth import admin_required, current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

bp = Blueprint("performance", __name__, url_prefix="/api/performance")

RANGES = {"7": 7, "14": 14, "30": 30}
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


def overview_data(user, days, campaign_id=None):
    """Everything the Performance page shows; also the AI desk's snapshot. `campaign_id`
    narrows it to one campaign the person can see."""
    (start, end), (prev_start, prev_end) = periods(date.today(), days)
    where, params = _scope_sql(user, "d.campaign_id")
    if campaign_id:
        where, params = f"({where}) AND d.campaign_id = %s", params + [campaign_id]

    totals = db.query(
        f"""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                   COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS leads
            FROM ad_daily d WHERE day BETWEEN %s AND %s AND {where}""",
        [start, end] + params, one=True,
    )
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
        series.append({"day": d, "spend_cents": int(r.get("spend_cents") or 0), "leads": int(r.get("leads") or 0)})

    lwhere, lparams = where.replace("d.campaign_id", "l.campaign_id"), params
    quality = db.query(
        f"""SELECT l.ad_id,
                   COUNT(*) AS inbox,
                   COUNT(*) FILTER (WHERE l.status IN ('qualified','won')) AS qualified,
                   COUNT(*) FILTER (WHERE l.status = 'won') AS won
            FROM leads l
            WHERE NOT l.is_test AND l.created_time::date BETWEEN %s AND %s AND {lwhere}
            GROUP BY l.ad_id""",
        [start, end] + lparams,
    )
    q_by_ad = {r["ad_id"]: r for r in quality}

    before = db.query(
        f"""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(leads),0) AS leads
            FROM ad_daily d WHERE day BETWEEN %s AND %s AND {where}""",
        [prev_start, prev_end] + params, one=True)
    before_q = db.query(
        f"""SELECT COUNT(*) FILTER (WHERE l.status IN ('qualified','won')) AS qualified FROM leads l
            WHERE NOT l.is_test AND l.created_time::date BETWEEN %s AND %s AND {lwhere}""",
        [prev_start, prev_end] + lparams, one=True)

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

    qualified_total = sum(int(r["qualified"]) for r in quality)
    alerts = []
    for ad in per_ad:
        if ad["effective_status"] in BAD_STATUSES:
            alerts.append({"level": "bad", "text": f"Meta stopped “{ad['name']}”: {ad['effective_status'].replace('_', ' ').lower()}. Open it in Ads Manager to see why."})
    cap = cap_snapshot() if user["role"] == "admin" else None
    if cap and cap["limit_cents"]:
        used = cap["spent_cents"] / cap["limit_cents"]
        if used >= 0.8:
            alerts.append({"level": "warn" if used < 1 else "bad",
                           "text": "The account spending limit is almost used up. Ads pause when it's reached."
                           if used < 1 else "The account spending limit is reached, so every ad is paused."})

    last, prev = (series[-1], series[-2]) if len(series) >= 2 else (None, None)
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "yesterday": last and {"day": last["day"], "spend_cents": last["spend_cents"], "leads": last["leads"],
                               "prev_spend_cents": prev["spend_cents"], "prev_leads": prev["leads"]},
        "totals": {**{k: int(v) for k, v in totals.items()}, "qualified": qualified_total},
        "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat(),
                     "spend_cents": int(before["spend_cents"]), "leads": int(before["leads"]),
                     "qualified": int(before_q["qualified"] or 0)},
        "series": series,
        "ads": per_ad,
        "cap": cap,
        "alerts": alerts,
        "last_sync": settings_store.get("last_performance_sync"),
    }


def pacing_data(scope_ids=None):
    """This month's pace for the campaigns in scope (None = the whole account, with the
    monthly target and the spending limit, which are account-wide)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(config.ACCOUNT_TZ)).date()
    where, params = ("TRUE", []) if scope_ids is None else ("campaign_id = ANY(%s)", [scope_ids])
    month_days = [(r["day"], int(r["c"])) for r in db.query(
        f"SELECT day, SUM(spend_cents) AS c FROM ad_daily WHERE day >= %s AND day < %s AND {where} GROUP BY day",
        [today.replace(day=1), today] + params)]
    recent = [int(r["c"]) for r in db.query(
        f"SELECT day, SUM(spend_cents) AS c FROM ad_daily WHERE day >= %s AND day < %s AND {where} GROUP BY day",
        [today - timedelta(days=7), today] + params)]
    cw = "TRUE" if scope_ids is None else "c.id = ANY(%s)"
    budget = db.query(f"""SELECT COALESCE(SUM(COALESCE(c.daily_budget_cents,
                             (SELECT SUM(daily_budget_cents) FROM adsets s WHERE s.campaign_id = c.id AND s.effective_status = 'ACTIVE'))), 0) AS c
                          FROM campaigns c WHERE c.effective_status = 'ACTIVE' AND {cw}""", params, one=True)["c"]
    raw = settings_store.get("today_snapshot")
    snap = json.loads(raw).get("campaigns", {}) if raw else {}
    so_far = sum(v["spend_cents"] for cid, v in snap.items() if scope_ids is None or cid in scope_ids)
    account = scope_ids is None
    cap = cap_snapshot() if account else None
    target = settings_store.get("monthly_target_cents") if account else None
    return pacing.pace(today, month_days, recent, int(budget or 0), int(target) if target else None,
                       cap["remaining_cents"] if cap and cap["limit_cents"] else None, so_far)


@bp.get("")
@login_required
def overview():
    user = current_user()
    days = RANGES.get(request.args.get("range", "7"), 7)
    campaign_id = request.args.get("campaign") or None
    if campaign_id:
        ids = visible_campaign_ids(user)
        if ids is not None and campaign_id not in ids:
            return api_error("Not found", 404)
    out = overview_data(user, days, campaign_id)
    (start, end), _ = periods(date.today(), days)
    out["campaigns"] = campaign_choices(user, start, end)
    out["campaign"] = campaign_id
    out["pacing"] = pacing_data(visible_campaign_ids(user))
    out["can_set_target"] = user["role"] == "admin"
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
