"""Meta A/B tests (ad studies) for a tracked test: build and check the request (pure), create it,
read Meta's result back, end it early. Off unless Settings → Meta A/B tests is switched on.

Two kinds, chosen by what the arms are:
- every arm one ad set  → SPLIT_TEST: Meta splits the audience between the ad sets; they spend
  their own budgets, so nothing extra is spent, but paused ad sets don't deliver.
- every arm one ad      → SPLIT_TEST_V2 (creative test): Meta runs the ads to separate groups
  with a test budget of its own, on top of the campaign's budget.
A study never starts before tomorrow (account time zone), so there is always a day to undo it."""
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MIN_DAYS, MAX_DAYS = 3, 30
MIN_BUDGET_CENTS = 100
CREATIVE_MAX_CELLS = 7


class PlanError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def split(n):
    """Even whole-number shares that add up to 100 (the first groups take the remainder)."""
    base, extra = divmod(100, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def midnight(day, tz):
    return int(datetime.combine(day, time(0), ZoneInfo(tz)).timestamp())


def plan(exp, start, end, daily_budget_cents, today, tz, max_budget_cents=None):
    """The ad study request for a tracked test, and a plain summary of what it costs.
    Raises PlanError with the reason when it can't be run on Meta."""
    arms = exp["arms"]
    if any(len(a.get("ad_ids") or []) + len(a.get("adset_ids") or []) != 1 for a in arms):
        raise PlanError("On Meta, each arm has to be exactly one ad or exactly one ad set")
    kinds = {"ad" if a.get("ad_ids") else "adset" for a in arms}
    if len(kinds) != 1:
        raise PlanError("On Meta, the arms have to be all ads or all ad sets, not a mix")
    kind = kinds.pop()
    if kind == "ad" and len(arms) > CREATIVE_MAX_CELLS:
        raise PlanError(f"Meta compares at most {CREATIVE_MAX_CELLS} ads in one test")
    if start <= today:
        raise PlanError("A Meta test can start tomorrow at the earliest", "start_day")
    if end is None or end <= start:
        raise PlanError("Pick an end date after the start", "end_day")
    days = (end - start).days
    if days < MIN_DAYS or days > MAX_DAYS:
        raise PlanError(f"Run it for {MIN_DAYS} to {MAX_DAYS} days (7 or more gives Meta enough to judge)", "end_day")
    shares = split(len(arms))
    payload = {"name": f"{exp['name']} (Edge Bourne Ads #{exp['id']})"[:250],
               "description": (exp.get("hypothesis") or "")[:500],
               "start_time": midnight(start, tz), "end_time": midnight(end, tz)}
    if kind == "adset":
        payload["type"] = "SPLIT_TEST"
        payload["cells"] = [{"name": a["label"], "treatment_percentage": p, "adsets": a["adset_ids"]} for a, p in zip(arms, shares)]
        total = None
        summary = (f"Meta splits the people these ad sets reach into {len(arms)} groups that don't overlap, "
                   f"from {start:%b %-d} to {end:%b %-d} ({days} days). Each ad set keeps its own budget, so nothing "
                   "extra is spent; ad sets that are switched off don't deliver.")
    else:
        if not daily_budget_cents or daily_budget_cents < MIN_BUDGET_CENTS:
            raise PlanError("Give the test a daily budget of at least $1", "budget")
        if max_budget_cents and daily_budget_cents > max_budget_cents:
            raise PlanError(f"Keep the test budget at ${max_budget_cents / 100:,.2f} a day or less (twice the campaign's daily budget)", "budget")
        payload["type"] = "SPLIT_TEST_V2"
        payload["cells"] = [{"name": a["label"], "treatment_percentage": p, "ads": a["ad_ids"]} for a, p in zip(arms, shares)]
        payload["creative_test_config"] = {"daily_budget": daily_budget_cents}
        payload["cooldown_start_time"] = payload["start_time"]
        payload["observation_end_time"] = payload["end_time"]
        total = daily_budget_cents * days
        summary = (f"Meta shows these {len(arms)} ads to separate groups of people from {start:%b %-d} to {end:%b %-d} "
                   f"({days} days), with a test budget of ${daily_budget_cents / 100:,.2f} a day on top of the campaign's: "
                   f"up to ${total / 100:,.2f} in total.")
    return {"kind": kind, "days": days, "total_cents": total, "summary": summary, "payload": payload}


def graph_form(payload):
    """Ad study fields as Graph form values (lists and objects as JSON)."""
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in payload.items()}


def merge_results(objectives):
    """Meta's objectives each carry `results`: a list of JSON strings or objects. One dict."""
    out = {}
    for o in objectives or []:
        for r in o.get("results") or []:
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except ValueError:
                    continue
            if isinstance(r, dict):
                out.update(r)
    return out


def meta_verdict(results, arms):
    """Meta's answer in the arms' own names: {winner, confidence, high_performers, by_arm, note}."""
    by_id = {i: a["label"] for a in arms for i in (a.get("ad_ids") or []) + (a.get("adset_ids") or [])}
    conf = {by_id.get(str(k), str(k)): round(float(v) * 100) if float(v) <= 1 else round(float(v))
            for k, v in (results.get("confidence_by_ad_object_id") or {}).items() if v is not None}
    winner = by_id.get(str(results.get("winner_ad_object_id"))) if results.get("winner_ad_object_id") else None
    wconf = results.get("winner_confidence")
    wconf = None if wconf is None else (round(float(wconf) * 100) if float(wconf) <= 1 else round(float(wconf)))
    high = [by_id.get(str(i), str(i)) for i in results.get("high_performer_ids") or []]
    if winner:
        note = f"Meta's pick: {winner}" + (f" ({wconf}% confidence)" if wconf is not None else "") + "."
    elif high:
        note = f"Meta marks {', '.join(high)} as the high performer{'s' if len(high) > 1 else ''}" + \
               (f" ({', '.join(f'{k} {v}%' for k, v in conf.items())})" if conf else "") + "."
    else:
        note = "Meta hasn't picked a winner yet."
    return {"winner": winner, "confidence": wconf, "high_performers": high, "by_arm": conf, "note": note}


def study_state(study, now_ts):
    if study.get("ended_early_at"):
        return "ended"
    if now_ts < study["start_time"]:
        return "scheduled"
    return "running" if now_ts < study["end_time"] else "ended"


STALE_BOOKING_SECONDS = 600


def booking_unsettled(study, now_ts):
    """A booking with no study id that needs someone to look on Meta: Meta didn't answer, or the request
    was cut off (a restart) and left the claim behind. A booking still in flight is left alone."""
    if not study or study.get("id"):
        return False
    if study.get("unknown") or not study.get("at"):
        return True
    return now_ts - datetime.fromisoformat(study["at"]).timestamp() > STALE_BOOKING_SECONDS


# ---------------------------------------------------------------- Meta + database

def enabled():
    import settings_store
    return settings_store.get("meta_ab_tests") == "on"


def business_id():
    """The business portfolio that owns the ad account (studies live there)."""
    import meta_client
    import settings_store
    bid = settings_store.get("meta_business_id")
    if not bid:
        acc = meta_client.get(f"act_{settings_store.get('meta_ad_account_id')}", fields="business")
        bid = (acc.get("business") or {}).get("id")
        if not bid:
            raise PlanError("Meta didn't say which business owns the ad account, so a test can't be created")
        settings_store.set("meta_business_id", bid)
    return bid


def fetch(study):
    """Meta's view of the study and its result, merged into our stored copy."""
    import meta_client
    objectives = meta_client.get(f"{study['id']}/objectives", fields="id,name,results").get("data") or []
    results = merge_results(objectives)
    if not results:
        for o in objectives:
            results.update(merge_results([meta_client.get(o["id"], fields="results")]))
    return {**study, "results": results, "fetched_at": datetime.now().astimezone().isoformat()}


def sync_running(max_age_minutes=30):
    """Read Meta's results for running tests with a study (worker; at most every half hour each)."""
    import db
    rows = db.query("SELECT id, arms, meta_study FROM experiments WHERE status = 'running' AND meta_study IS NOT NULL")
    now = datetime.now().astimezone()
    for r in rows:
        s = r["meta_study"]
        if not s.get("id"):
            continue  # being created right now
        last = s.get("fetched_at")
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=max_age_minutes):
            continue
        try:
            db.execute("UPDATE experiments SET meta_study = %s WHERE id = %s", (json.dumps(fetch(s)), r["id"]))
        except Exception:  # Meta down or the study gone; try again next pass
            continue
