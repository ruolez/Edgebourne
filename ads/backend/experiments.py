"""Tests Eugene runs on the ads: what is being tried (the arms), the number that decides it,
and whether the data can call a winner yet. `judge` is pure; the rest reads the database.

Rules (from the workspace playbook): an arm can't be judged before it has spent twice the
target cost and has at least 3 results; a winner needs 95% confidence, never Meta's 65%."""
import math
from datetime import date, timedelta

import account_info
import db

METRICS = {
    # key: (label, what one result is, cost or rate, numerator for rates)
    "cpl": {"label": "Cost per lead", "result": "lead", "kind": "cost", "count": "leads"},
    "cpql": {"label": "Cost per qualified lead", "result": "qualified lead", "kind": "cost", "count": "qualified"},
    "ctr": {"label": "Click rate", "result": "click", "kind": "rate", "count": "link_clicks"},
    "hook": {"label": "Hook rate", "result": "3-second view", "kind": "rate", "count": "video_3s"},
}
MIN_RESULTS = 3            # cost metrics: each arm needs this many results
SPEND_TIMES = 2            # ...and this many times the target cost in spend
MIN_IMPRESSIONS = 1000     # rate metrics: each arm needs this many impressions
MIN_SUCCESSES = 20         # ...and this many clicks / views
MIN_DAYS = 3               # nothing is judged on fewer complete days
WIN = 95                   # % confidence to call a winner
LEAN = 80                  # % confidence to say one looks better
STATUSES = ("running", "done", "stopped")


def value(metric, arm):
    """The arm's number for the metric: cents per result, or a share (0-1); None when undefined."""
    m = METRICS[metric]
    n = arm.get(m["count"]) or 0
    if m["kind"] == "cost":
        return arm["spend_cents"] / n if n else None
    return n / arm["impressions"] if arm.get("impressions") else None


def _binom_two_sided(k, n, p):
    """Exact two-sided binomial test: chance of a split at least this uneven if both arms were equal."""
    if n == 0 or p <= 0 or p >= 1:
        return 1.0
    def pmf(i):
        return math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log(1 - p))
    observed = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= observed * (1 + 1e-9)))


def _two_proportion(x1, n1, x2, n2):
    if not n1 or not n2:
        return 1.0
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    return math.erfc(abs(x1 / n1 - x2 / n2) / se / math.sqrt(2))


def confidence(metric, a, b):
    """% sure the two arms really differ on the metric (1 - two-sided p)."""
    m = METRICS[metric]
    if m["kind"] == "cost":
        ka, kb = a.get(m["count"]) or 0, b.get(m["count"]) or 0
        spend = a["spend_cents"] + b["spend_cents"]
        p = _binom_two_sided(ka, ka + kb, a["spend_cents"] / spend) if spend else 1.0
    else:
        p = _two_proportion(a.get(m["count"]) or 0, a.get("impressions") or 0, b.get(m["count"]) or 0, b.get("impressions") or 0)
    return max(0, min(99, math.floor((1 - p) * 100)))


def _money(cents, currency):
    return account_info.money(cents, currency, whole=cents >= 1000)


def needs(metric, arm, target_cents, currency="USD"):
    """What the arm still needs before it can be judged ('' when it has enough)."""
    m = METRICS[metric]
    n = arm.get(m["count"]) or 0
    out = []
    if m["kind"] == "cost":
        if target_cents and arm["spend_cents"] < SPEND_TIMES * target_cents:
            out.append(f"{_money(SPEND_TIMES * target_cents - arm['spend_cents'], currency)} more spend")
        if n < MIN_RESULTS:
            out.append(f"{MIN_RESULTS - n} more {m['result']}{'' if MIN_RESULTS - n == 1 else 's'}")
    else:
        if (arm.get("impressions") or 0) < MIN_IMPRESSIONS:
            out.append(f"{MIN_IMPRESSIONS - (arm.get('impressions') or 0):,} more impressions")
        if n < MIN_SUCCESSES:
            out.append(f"{MIN_SUCCESSES - n} more {m['result']}{'' if MIN_SUCCESSES - n == 1 else 's'}")
    return " and ".join(out)


def judge(metric, arms, target_cents=None, days_run=0, currency="USD"):
    """arms: [{label, spend_cents, impressions, link_clicks, leads, qualified, video_3s}].
    Returns the state ('early' | 'even' | 'leaning' | 'winner'), the leader, how much better it is,
    the confidence, what each arm still needs and one plain sentence."""
    m = METRICS[metric]
    lower_better = m["kind"] == "cost"
    if target_cents is None and lower_better:
        total_n = sum(a.get(m["count"]) or 0 for a in arms)
        target_cents = round(sum(a["spend_cents"] for a in arms) / total_n) if total_n else None
    short = {a["label"]: needs(metric, a, target_cents, currency) for a in arms}
    ranked = sorted(arms, key=lambda a: (value(metric, a) is None, (value(metric, a) or 0) * (1 if lower_better else -1)))
    out = {"state": "early", "leader": None, "runner_up": None, "diff_pct": None, "confidence": None,
           "needs": {k: v for k, v in short.items() if v}, "target_cents": target_cents}
    if len(arms) < 2:
        out["note"] = "Add a second arm to compare."
        return out
    lead, second = ranked[0], ranked[1]
    lv, sv = value(metric, lead), value(metric, second)
    if lv is not None:
        out["leader"], out["runner_up"] = lead["label"], second["label"]
        if sv:
            out["diff_pct"] = round(((sv - lv) / sv if lower_better else (lv - sv) / sv) * 100)
        out["confidence"] = confidence(metric, lead, second)
    better = f"{out['diff_pct']}% {'cheaper' if lower_better else 'higher'}" if out["diff_pct"] is not None else "ahead"
    if out["needs"] or days_run < MIN_DAYS:
        waits = [f"{k} needs {v}" for k, v in out["needs"].items()]
        if days_run < MIN_DAYS:
            waits.insert(0, f"it needs {MIN_DAYS - days_run} more full day{'' if MIN_DAYS - days_run == 1 else 's'}")
        lean = f" {lead['label']} is ahead so far ({better})." if out["leader"] and out["diff_pct"] else ""
        out["note"] = f"Too early to call: {'; '.join(waits)}.{lean}"
        return out
    if lv is None:
        out["state"], out["note"] = "even", f"No {m['result']}s in any arm yet."
        return out
    c = out["confidence"]
    if c >= WIN:
        out["state"] = "winner"
        out["note"] = f"{lead['label']} wins: {better}, {c}% sure."
    elif c >= LEAN:
        out["state"] = "leaning"
        out["note"] = f"{lead['label']} looks better ({better}, {c}% sure), but not enough to call it. Keep it running."
    else:
        out["state"] = "even"
        out["note"] = (f"No clear difference yet: {lead['label']} is {better} so far, which could easily be chance."
                       if c < 50 else f"No clear difference yet: {lead['label']} is {better}, but only {c}% sure.")
    return out


# ---------------------------------------------------------------- database

def window(exp, today):
    """Complete days the test covers: start to the planned end or yesterday, whichever is first."""
    end = today - timedelta(days=1)
    if exp.get("end_day") and exp["end_day"] < end:
        end = exp["end_day"]
    return exp["start_day"], end


def arm_numbers(arm, start, end):
    ads, sets = arm.get("ad_ids") or [], arm.get("adset_ids") or []
    row = db.query(
        """SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                  COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS leads,
                  COALESCE(SUM(video_3s),0) AS video_3s
           FROM ad_daily WHERE day BETWEEN %s AND %s AND (ad_id = ANY(%s) OR adset_id = ANY(%s))""",
        (start, end, ads, sets), one=True)
    q = db.query(
        """SELECT COUNT(*) FILTER (WHERE status IN ('qualified','won')) AS qualified FROM leads
           WHERE NOT is_test AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s
             AND (ad_id = ANY(%s) OR adset_id = ANY(%s))""",
        (account_info.tz_name(), start, end, ads, sets), one=True)
    return {**{k: int(v) for k, v in row.items()}, "qualified": int(q["qualified"] or 0)}


def default_target(metric):
    """The account's cost-per-lead target (Settings → Targets), for a cost-per-lead test."""
    if metric != "cpl":
        return None
    import targets
    return targets.lead_own()


def account_today():
    return account_info.today()


def with_results(exp, today=None):
    today = today or account_today()
    start, end = window(exp, today)
    days_run = max(0, (end - start).days + 1)
    arms = [{**a, **(arm_numbers(a, start, end) if days_run else
                     {"spend_cents": 0, "impressions": 0, "link_clicks": 0, "leads": 0, "video_3s": 0, "qualified": 0})}
            for a in exp["arms"]]
    for a in arms:
        a["value"] = value(exp["metric"], a)
    target = exp.get("target_cents") or default_target(exp["metric"])
    out = {**exp, "arms": arms, "days_run": days_run, "window": {"start": start.isoformat(), "end": end.isoformat()},
           "judgement": judge(exp["metric"], arms, target, days_run, account_info.currency())}
    for k in ("start_day", "end_day"):
        out[k] = exp[k].isoformat() if exp.get(k) else None
    return out
