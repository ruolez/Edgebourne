"""Tests Eugene runs on the ads: what is being tried (the arms), the number that decides it,
and whether the data can call a winner yet. `judge` is pure; the rest reads the database.

Rules (from the workspace playbook): an arm can't be judged before it has spent twice the
target cost and has at least 3 results; a winner needs 95% confidence, never Meta's 65%."""
import math
from datetime import date, datetime, timedelta

import account_info
import db
import lead_quality as lq

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
            out.append(f"{MIN_IMPRESSIONS - (arm.get('impressions') or 0):,} more views")
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
        out["note"] = "Add a second side to compare."
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
        out["state"], out["note"] = "even", f"No {m['result']}s on any side yet."
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


NUMBERS = ("spend_cents", "impressions", "link_clicks", "leads", "video_3s")


def arm_sums(arms, daily, lead_rows):
    """Each arm's totals from rows per ad (ad_id, adset_id, the NUMBERS / qualified): a row counts for an arm
    when its ad or its ad set is in the arm, once even when both are, as `ad_id = ANY(..) OR adset_id = ANY(..)`."""
    out = []
    for arm in arms:
        ads, sets = set(arm.get("ad_ids") or []), set(arm.get("adset_ids") or [])
        mine = [r for r in daily if r["ad_id"] in ads or r["adset_id"] in sets]
        sums = {k: sum(int(r[k]) for r in mine) for k in NUMBERS}
        sums["qualified"] = sum(int(r["qualified"] or 0) for r in lead_rows if r["ad_id"] in ads or r["adset_id"] in sets)
        out.append(sums)
    return out


def arms_numbers(arms, start, end, tz=None):
    """Every arm's numbers for the window in two queries, not two per arm (audit A3-130)."""
    ads = sorted({i for a in arms for i in a.get("ad_ids") or []})
    sets = sorted({i for a in arms for i in a.get("adset_ids") or []})
    daily = db.query(
        """SELECT ad_id, adset_id, COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                  COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS leads,
                  COALESCE(SUM(video_3s),0) AS video_3s
           FROM ad_daily WHERE day BETWEEN %s AND %s AND (ad_id = ANY(%s) OR adset_id = ANY(%s)) GROUP BY ad_id, adset_id""",
        (start, end, ads, sets))
    lead_rows = db.query(
        f"""SELECT ad_id, adset_id, COUNT(*) FILTER (WHERE {lq.qualified()}) AS qualified FROM leads l
           WHERE {lq.counted()} AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s
             AND (ad_id = ANY(%s) OR adset_id = ANY(%s)) GROUP BY ad_id, adset_id""",
        (tz or account_info.tz_name(), start, end, ads, sets))
    return arm_sums(arms, daily, lead_rows)


def default_target(metric):
    """The account's cost-per-lead target (Settings → Targets), for a cost-per-lead test."""
    if metric != "cpl":
        return None
    import targets
    return targets.lead_own()


def arm_members(arm, ads, sets):
    """Each ad and ad set in an arm with its name (None when it's gone), so pages link to the ones still there."""
    return [{"level": "ad", "id": i, "name": ads.get(i), "gone": i not in ads} for i in arm.get("ad_ids") or []] + \
           [{"level": "adset", "id": i, "name": sets.get(i), "gone": i not in sets} for i in arm.get("adset_ids") or []]


def containing(exps, ad_id, adset_id=None):
    """The tests an ad takes part in, by itself or through its whole ad set: running ones first, then the newest."""
    def has(arm):
        return ad_id in (arm.get("ad_ids") or []) or (adset_id is not None and adset_id in (arm.get("adset_ids") or []))
    hits = [e for e in exps if any(has(a) for a in e.get("arms") or [])]
    hits.sort(key=lambda e: (e["status"] != "running", -e["id"]))
    return [{"id": e["id"], "name": e["name"], "status": e["status"]} for e in hits]


GONE = ("DELETED", "ARCHIVED")
MORE_LIKE = ("Write three new ads like {what}. It won the test “{test}” on {metric}: {note} "
             "Keep what made it work, try a different hook or visual for each, same offer.")


NEXT_STEP_DAYS = 14


def next_step(exp, live, meta=None, today=None):
    """What to do once a test has a winner (Meta's numbers called it, or Eugene picked one when finishing):
    the losing ads or ad sets still on, to turn off; the budget that pays for the winner, to raise; and a
    prompt for Claude to make more like it. Only offers: each one goes through the console's usual
    confirmation. live: {"ads", "adsets", "campaigns"} rows by id (status = the configured on/off).
    meta: the test's Meta study view ({"state", "end_day"}); while Meta's split still runs nothing is offered
    to switch off or fund, since that would spoil the paid study. A finished test offers its next step for
    NEXT_STEP_DAYS after it closed, so an old test doesn't keep asking about ads turned back on on purpose."""
    if exp["status"] == "done":
        closed = exp.get("closed_at")
        if isinstance(closed, str):
            closed = datetime.fromisoformat(closed)
        if isinstance(closed, datetime):
            closed = closed.date()
        if closed and today and (today - closed).days > NEXT_STEP_DAYS:
            return None
        won = exp.get("winner")
    elif exp["status"] == "running" and exp["judgement"]["state"] == "winner":
        won = exp["judgement"]["leader"]
    else:
        won = None
    labels = {a["label"]: a for a in exp["arms"]}
    winner = labels.get(won) or next((a for a in exp["arms"] if won and a["label"].lower() == won.lower()), None)
    if not winner:
        return None
    ads, sets, camps = live["ads"], live["adsets"], live["campaigns"]
    won_ads = [ads[i] for i in winner.get("ad_ids") or [] if i in ads]
    won_sets = [sets[i] for i in winner.get("adset_ids") or [] if i in sets]
    on = lambda r: r.get("status") == "ACTIVE" and r.get("effective_status") not in GONE  # noqa: E731
    turn_off = []
    for arm in exp["arms"]:
        if arm is winner:
            continue
        for i in arm.get("ad_ids") or []:
            if i in ads and on(ads[i]):
                turn_off.append({"level": "ad", "id": i, "name": ads[i]["name"], "side": arm["label"]})
        for i in arm.get("adset_ids") or []:
            holds_winner = any(a["adset_id"] == i for a in won_ads) or any(s["id"] == i for s in won_sets)
            if i in sets and on(sets[i]) and not holds_winner:
                turn_off.append({"level": "adset", "id": i, "name": sets[i]["name"], "side": arm["label"]})
    budgets = []
    for adset_id, campaign_id in [(a["adset_id"], a["campaign_id"]) for a in won_ads] + [(s["id"], s["campaign_id"]) for s in won_sets]:
        s, c = sets.get(adset_id), camps.get(campaign_id)
        holder = ("adset", s) if s and s.get("daily_budget_cents") else ("campaign", c) if c and c.get("daily_budget_cents") else None
        if not holder or any(b["id"] == holder[1]["id"] for b in budgets):
            continue
        level, row = holder
        # A loser still on under the same budget would get part of any raise.
        paid_by = lambda x: (ads[x["id"]] if x["level"] == "ad" else {"adset_id": x["id"], **sets[x["id"]]})[  # noqa: E731
            "adset_id" if level == "adset" else "campaign_id"]
        shared = [x["name"] for x in turn_off if paid_by(x) == row["id"]]
        budgets.append({"level": level, "id": row["id"], "name": row["name"], "daily_budget_cents": row["daily_budget_cents"], "shared_with": shared})
    first = won_ads[0] if won_ads else None
    what = f"“{first['name']}” (ad {first['id']})" if first else \
        f"the ones in the ad set “{won_sets[0]['name']}”" if won_sets else f"side {winner['label']}"
    j = exp["judgement"]
    if j["state"] == "winner" and j["leader"] == winner["label"]:
        note = j["note"]
    elif (exp.get("verdict") or "").strip():
        note = exp["verdict"].strip()
    else:
        note = f"{winner['label']} was picked as the winner."
    prompt = MORE_LIKE.format(what=what, test=exp["name"], metric=METRICS[exp["metric"]]["label"].lower(), note=note)[:4000]
    wait = None
    if meta and (meta.get("creating") or meta.get("state") in ("scheduled", "running")):
        turn_off, budgets = [], []
        wait = {"until": meta.get("end_day")}
    return {"winner": winner["label"], "turn_off": turn_off, "budgets": budgets, "wait": wait,
            "winner_off": bool(won_ads or won_sets) and not any(on(r) for r in won_ads + won_sets),
            "more_like": {"ad_id": first["id"] if first else None, "name": first["name"] if first else (won_sets[0]["name"] if won_sets else None),
                          "prompt": prompt}}


def account_today():
    return account_info.today()


def shared():
    """What every test's results read from the account, read once for a list of tests (audit A3-130)."""
    snap = account_info.snapshot()
    return {"today": account_today(), "tz": account_info.tz_name(snap), "currency": account_info.currency(snap),
            "cpl_target": default_target("cpl")}


def with_results(exp, today=None, ctx=None):
    ctx = ctx or shared()
    today = today or ctx["today"]
    start, end = window(exp, today)
    days_run = max(0, (end - start).days + 1)
    numbers = arms_numbers(exp["arms"], start, end, ctx["tz"]) if days_run else \
        [{**{k: 0 for k in NUMBERS}, "qualified": 0} for _ in exp["arms"]]
    arms = [{**a, **n} for a, n in zip(exp["arms"], numbers)]
    for a in arms:
        a["value"] = value(exp["metric"], a)
    target = exp.get("target_cents") or (ctx["cpl_target"] if exp["metric"] == "cpl" else None)
    out = {**exp, "arms": arms, "days_run": days_run, "window": {"start": start.isoformat(), "end": end.isoformat()},
           "judgement": judge(exp["metric"], arms, target, days_run, ctx["currency"])}
    for k in ("start_day", "end_day"):
        out[k] = exp[k].isoformat() if exp.get(k) else None
    return out
