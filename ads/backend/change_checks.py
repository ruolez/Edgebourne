"""Did it work? (D3): for each change made from the console, the results before and after it over equal
windows of complete days (3, 7 and 14), judged with the minimum-data rule of Compare and Tests: a side is read
only once it has spent twice the target and has 3 results. Pure: no database, no Flask (change_checks_db reads).

A result never moves money. "Put it back" (`undo_plan`) only says what the existing confirmation dialog would
be filled in with."""
import re
from datetime import timedelta

import compare
import experiments
import words

HORIZONS = (3, 7, 14)
CHECKED = {"status", "budget", "update_creative", "restore_creative", "placement_media", "enhancement", "recommendation", "create"}
LEVELS = ("campaign", "adset", "ad")
DELTA_PCT = 10          # the smallest change worth a word
LEAN = experiments.LEAN
SPEND_TIMES = experiments.SPEND_TIMES
MIN_RESULTS = experiments.MIN_RESULTS
SETTLE_DAYS = 7         # qualified stages and Meta's late conversions keep arriving this long after a window
FAR_OVER = 3            # no leads after 3× the target looks worse (the cpl_high bar)
EXPERIMENT_METRIC = {"cpl_cents": "cpl", "cpq_cents": "cpql"}
EXPECT_METRIC = {"cpl": "cpl_cents", "cpq": "cpq_cents"}
METRIC_WORDS = {"cpl_cents": ("cost per lead", "per lead"), "cpq_cents": ("cost per qualified lead", "per qualified lead")}
# The console's words for each state (format.js OUTCOME says the same).
OUTCOME = {"better": "Worked", "lean_better": "Looks better, not sure yet", "same": "No clear change",
           "lean_worse": "Looks worse, not sure yet", "worse": "Didn't help", "too_early": "Too early to tell",
           "waiting": "Not checked yet", "on_target": "On target", "over_target": "Over target",
           "mixed": "Changed again too soon", "no_compare": "Nothing to compare", "stopped": "Off", "not_running": "Not running yet"}
CLASS = {"better": "good", "lean_better": "good", "on_target": "good", "worse": "bad", "lean_worse": "bad",
         "same": "flat", "over_target": "flat"}
WORSE = ("worse", "lean_worse")
SETTLED = ("mixed", "no_compare", "stopped")  # final once their window is complete: later numbers can't change them
GONE = ("ARCHIVED", "DELETED")
CREATIVE = re.compile(r"\(creative ([^)\s]+)\)")


# ---------------------------------------------------------------- what is measured where

def mode_for(change, entity):
    """(mode, scope_level, scope_id), or None when the change isn't checked. `entity` ({level, id, adset_id,
    campaign_id}) is read for parent ids only."""
    level, action = change.get("level"), change.get("action")
    if not change.get("ok") or level not in LEVELS or action not in CHECKED:
        return None
    eid = change.get("entity_id")
    entity = entity or {}
    if action in ("budget", "enhancement", "placement_media", "recommendation"):
        return ("self", level, eid)
    if action in ("update_creative", "restore_creative"):
        return ("version", "ad", eid) if level == "ad" else None
    if action == "create":
        return ("new", level, eid)
    # status
    if level == "campaign":
        return ("stopped" if change.get("new_value") == "PAUSED" else "new", "campaign", eid)
    parent = ("adset", entity.get("adset_id")) if level == "ad" else ("campaign", entity.get("campaign_id"))
    return ("parent", parent[0], parent[1]) if parent[1] else None


# ---------------------------------------------------------------- windows and sums

def windows(first_changed, last_changed, today, horizon, prev_change=None, next_change=None):
    """Equal windows of complete days before and after a change. The days from `first_changed` to `last_changed`
    (the change day; for a new version, until Meta approved it) count for neither side. The after window stops the
    day before `next_change`, the before window starts the day after `prev_change`; both then take the shorter
    length."""
    yesterday = today - timedelta(days=1)
    after_start, after_end, cut_by = last_changed + timedelta(days=1), last_changed + timedelta(days=horizon), None
    if next_change is not None and next_change - timedelta(days=1) < after_end:
        after_end, cut_by = next_change - timedelta(days=1), next_change
    before_end, before_start = first_changed - timedelta(days=1), first_changed - timedelta(days=horizon)
    if prev_change is not None and prev_change + timedelta(days=1) > before_start:
        before_start = prev_change + timedelta(days=1)
    n = max(0, min((after_end - after_start).days + 1, (before_end - before_start).days + 1))
    if not n:
        return {"before": None, "after": None, "days": 0, "complete": True, "ready_on": after_start, "cut_by": cut_by}
    after = (after_start, after_start + timedelta(days=n - 1))
    return {"before": (before_end - timedelta(days=n - 1), before_end), "after": after, "days": n,
            "complete": after[1] <= yesterday, "ready_on": after[1] + timedelta(days=1), "cut_by": cut_by}


SUMS = ("spend_cents", "leads", "qualified", "impressions")


def totals(daily, start, end):
    out = {"days": (end - start).days + 1, **{k: 0 for k in SUMS}}
    for row in daily:
        if start <= row["day"] <= end:
            for k in SUMS:
                out[k] += int(row.get(k) or 0)
    return out


# ---------------------------------------------------------------- the verdict

def _ready(metric, side, target):
    return not experiments.needs(EXPERIMENT_METRIC[metric], side, target)


def _pick(sides, q_target, l_target):
    """cpq when a qualified target is set and every side can be read on it, else cpl. Returns (metric, target, note)."""
    if q_target and all(_ready("cpq_cents", s, q_target) for s in sides):
        return "cpq_cents", q_target, None
    return "cpl_cents", l_target, "qualified_short" if q_target else None


def judge(mode, before, after, q_target, l_target, currency="USD"):
    """The state of one horizon. `before` / `after`: totals (spend_cents, leads, qualified). Returns {state, metric,
    delta_pct, confidence, needs, notes, after_ready, target_cents, before, after} (sides with their rates)."""
    b = compare.rates(before) if before else None
    a = compare.rates(after) if after else None
    out = {"state": None, "metric": "cpl_cents", "delta_pct": None, "confidence": None, "needs": None, "notes": [],
           "after_ready": {}, "target_cents": l_target, "before": b, "after": a}
    if a:
        out["after_ready"] = {"cpl_cents": bool(l_target) and _ready("cpl_cents", a, l_target),
                              "cpq_cents": bool(q_target) and _ready("cpq_cents", a, q_target)}
    if mode == "stopped" or (mode == "parent" and a and not a["spend_cents"]):
        return {**out, "state": "stopped"}
    if mode == "new":
        if not a["spend_cents"]:
            return {**out, "state": "not_running"}
        if not l_target and not q_target:
            return {**out, "state": "too_early", "notes": ["no_target"]}
        metric, target, _ = _pick([a], q_target, l_target)
        need = experiments.needs(EXPERIMENT_METRIC[metric], a, target, currency)
        if need:
            return {**out, "state": "too_early", "metric": metric, "target_cents": target, "needs": need}
        return {**out, "metric": metric, "target_cents": target, "state": "on_target" if a[metric] <= target else "over_target"}
    if not b["spend_cents"]:
        return {**out, "state": "no_compare"}
    if not l_target:
        return {**out, "state": "too_early", "notes": ["no_target"]}
    if not a["leads"] and a["spend_cents"] >= FAR_OVER * l_target:
        return {**out, "state": "lean_worse", "notes": ["no_leads"]}
    metric, target, note = _pick([b, a], q_target, l_target)
    out.update(metric=metric, target_cents=target, notes=[note] if note else [])
    key = EXPERIMENT_METRIC[metric]
    after_needs, before_needs = experiments.needs(key, a, target, currency), experiments.needs(key, b, target, currency)
    if after_needs:
        return {**out, "state": "too_early", "needs": after_needs}
    if before_needs:
        return {**out, "state": "too_early", "needs": before_needs, "notes": out["notes"] + ["before_short"]}
    delta = compare._delta(a[metric], b[metric])
    sure = experiments.confidence(key, b, a)
    if abs(delta) < DELTA_PCT:
        state = "same"
    elif delta < 0:
        state = "better" if sure >= LEAN else "lean_better"
    else:
        state = "worse" if sure >= LEAN else "lean_worse"
    return {**out, "state": state, "delta_pct": delta, "confidence": sure}


def state_class(state):
    """good / bad / flat for the Inbox (one item per class and change), None when there's no result yet."""
    return CLASS.get(state)


def headline(rows):
    """The row a single line shows: the longest horizon that has been read, else the first check."""
    if not rows:
        return None
    read = [r for r in rows if r["state"] != "waiting"]
    return max(read, key=lambda r: r["horizon"]) if read else min(rows, key=lambda r: r["horizon"])


# ---------------------------------------------------------------- Claude's expectation

_METRIC_TEXT = re.compile(r"\b(?:cpql|cost per qualified lead|per qualified lead)\b|\b(?:cpl|cost per lead|per lead)\b", re.I)
_TARGET_TEXT = re.compile(r"\b(under|below|less than|at most|no more than|to)\s*\$?\s*(\d[\d,]*(?:\.\d{1,2})?)|(<=|≤|<)\s*\$?\s*(\d[\d,]*(?:\.\d{1,2})?)", re.I)
_DAYS_TEXT = re.compile(r"\b(3|7|14)\s*days?\b", re.I)
_LESS = ("under", "below", "less than", "<")


def expect_from_text(text):
    """Best effort on Claude's free-text `expected`: {metric, op, cents, days}, or None."""
    text = str(text or "")
    m = _METRIC_TEXT.search(text)
    if not m:
        return None
    found = m.group(0).lower()
    metric = "cpq" if found == "cpql" or "qualified" in found else "cpl"
    t = _TARGET_TEXT.search(text, m.end())
    if not t:
        return None
    word, amount = (t.group(1), t.group(2)) if t.group(1) else (t.group(3), t.group(4))
    try:
        cents = round(float(amount.replace(",", "")) * 100)
    except ValueError:
        return None
    days = _DAYS_TEXT.search(text)
    return clean_expect({"metric": metric, "op": "<" if word.lower() in _LESS else "<=", "cents": cents,
                         "days": int(days.group(1)) if days else 7})


def clean_expect(raw):
    """The structured expectation Claude sends with a suggestion: {metric: cpl|cpq, op: <|<=, cents, days: 3|7|14}."""
    if not isinstance(raw, dict):
        return None
    cents, days = raw.get("cents"), raw.get("days", 7)
    if raw.get("metric") not in EXPECT_METRIC or raw.get("op") not in ("<", "<="):
        return None
    if not isinstance(cents, int) or isinstance(cents, bool) or not 1 <= cents <= 10_000_000:
        return None
    if days is None:
        days = 7
    if isinstance(days, bool) or days not in HORIZONS:
        return None
    return {"metric": raw["metric"], "op": raw["op"], "cents": cents, "days": days}


def expectation_met(expect, check):
    """True / False once the after side can be read on that metric, else None."""
    key = EXPECT_METRIC.get((expect or {}).get("metric"))
    if not key or not (check or {}).get("after_ready", {}).get(key):
        return None
    got = (check.get("after") or {}).get(key)
    if got is None:
        return None
    return got < expect["cents"] if expect["op"] == "<" else got <= expect["cents"]


def expect_words(expect, money):
    """'cost per lead under $40'."""
    label = METRIC_WORDS[EXPECT_METRIC[expect["metric"]]][0]
    return f"{label} under {money(expect['cents'])}" if expect["op"] == "<" else f"{label} at most {money(expect['cents'])}"


def got_words(expect, row, money):
    """'$36 over 7 days', or None while that metric can't be read."""
    key = EXPECT_METRIC[expect["metric"]]
    if not (row or {}).get("after_ready", {}).get(key) or (row.get("after") or {}).get(key) is None:
        return None
    return f"{money(row['after'][key])} over {_days(row['days'])}"


# ---------------------------------------------------------------- words

def _days(n):
    return f"{n} day{'' if n == 1 else 's'}"


def sentence(check, money, day):
    """The plain line shown in History, on Claude's page, in the Inbox and sent to Claude."""
    state, metric = check["state"], check.get("metric") or "cpl_cents"
    label, per = METRIC_WORDS[metric]
    b, a, n = check.get("before") or {}, check.get("after") or {}, check.get("days")
    word = OUTCOME[state]
    if state == "waiting":
        if "stale" in (check.get("notes") or []):
            return "Not checked yet: waiting for Meta's numbers."
        return f"First check on {day(check['ready_on'])}"
    if state == "too_early":
        if "no_target" in (check.get("notes") or []):
            return f"{word}: set a cost-per-lead target in Settings → Targets to judge it."
        return f"{word}: needs {check['needs']}."
    if state == "lean_worse" and "no_leads" in (check.get("notes") or []):
        times = a["spend_cents"] // check["target_cents"] if check.get("target_cents") else FAR_OVER
        return f"{word}: no leads in {_days(n)} after spending {money(a['spend_cents'])} ({times}× your target)."
    if state in ("better", "lean_better", "same", "lean_worse", "worse"):
        line = f"{word}: {label} {money(b[metric])} → {money(a[metric])} over {_days(n)}"
        if state == "better":
            line += f" ({abs(check['delta_pct'])}% cheaper)"
        elif state == "worse":
            line += f" ({check['delta_pct']}% more)"
        return line + "."
    if state in ("on_target", "over_target"):
        return f"Got {money(a[metric])} {per} over its first {_days(n)} (target {money(check['target_cents'])})."
    if state == "mixed":
        return f"Changed again on {day(check['cut_by'])}, too soon to tell the two changes apart."
    if state == "no_compare":
        return "It hadn't run long enough before the change to compare."
    if state == "stopped":
        leads = b.get("leads") or 0
        got = "and got no leads" if not leads else (
            "for 1 lead" if leads == 1 else f"for {leads} leads ({money(b['cpl_cents'])} each)")
        return f"Off since {day(check['changed_on'])}. In the {_days(n)} before, it spent {money(b.get('spend_cents') or 0)} {got}."
    return "Hasn't spent anything yet."


def compared_words(mode, scope_level, scope_name, change_level, review):
    """The dialog's "what's compared" line. `review`: (first, last) days of the change for a new version."""
    level = {"campaign": "campaign", "adset": "ad set", "ad": "ad"}
    if mode == "self":
        return f"Compared on the {level[scope_level]} itself."
    if mode == "parent":
        return f"Compared on the {level[scope_level]} “{scope_name}”, which this {level[change_level]} is in."
    if mode == "version":
        if review and review[1] > review[0]:
            return f"The days Meta was reviewing the new version ({words.day(review[0])} – {words.day(review[1])}) count for neither side."
        return "The day of the switch counts for neither side."
    if mode == "stopped":
        return "It's off, so there's no after to compare."
    return "Its first days are compared with your target."


def rule_words(metric, target, money):
    """The minimum-data rule in one sentence."""
    if not target:
        return "Set a cost-per-lead target in Settings → Targets to judge results."
    what = "qualified leads" if metric == "cpq_cents" else "leads"
    return (f"Judged only once each side has spent at least {money(SPEND_TIMES * target)} ({SPEND_TIMES}× your "
            f"{money(target)} target) and has {MIN_RESULTS} {what}.")


def _verdict(state):
    word = OUTCOME[state]
    return word[0].lower() + word[1:]


def alert_title(change, name, state):
    """The Inbox title: "Budget raise on “Free intro call”: didn't help"."""
    action = change.get("action")
    if action == "budget":
        try:
            up = int(change.get("new_value")) > int(change.get("old_value"))
        except (TypeError, ValueError):
            up = True
        what = f"Budget {'raise' if up else 'cut'} on “{name}”"
    elif action == "status":
        what = f"Turning {'off' if change.get('new_value') == 'PAUSED' else 'on'} “{name}”"
    elif action == "update_creative":
        what = f"New version of “{name}”"
    elif action == "restore_creative":
        what = f"Switching “{name}” back to an earlier version"
    elif action == "placement_media":
        what = f"The 9:16 video on “{name}”"
    elif action == "enhancement":
        what = f"Meta's automatic change on “{name}”"
    elif action == "recommendation":
        what = f"Meta's advice on “{name}”"
    else:
        what = f"New {'ad set' if change.get('level') == 'adset' else change.get('level') or 'ad'} “{name}”"
    return f"{what}: {_verdict(state)}"


# ---------------------------------------------------------------- Put it back

def _gone(entity_now, verb):
    if entity_now is None:
        return f"It isn't on Meta any more, so it can't be {verb} back."
    status = entity_now.get("status")
    if status in GONE or entity_now.get("effective_status") in GONE:
        return f"It's {'archived' if 'ARCHIVED' in (status, entity_now.get('effective_status')) else 'deleted'}, so it can't be {verb} back."
    return None


def _back_number(change, versions):
    """The version number a Put it back of a version change restores: the newest one with the old creative, else the
    one before the version the change made. None when neither is known."""
    made = CREATIVE.search(str(change.get("new_value") or ""))
    if not made:
        return None
    numbers = {v["number"] for v in versions}
    current = max((v["number"] for v in versions if str(v["creative_id"]) == made.group(1)), default=None)
    before = [v["number"] for v in versions if str(v["creative_id"]) == str(change.get("old_value")) and v["number"] != current]
    return max(before) if before else (current - 1 if current and current - 1 in numbers else None)


def reverses(change, value, versions=()):
    """Whether a write puts `change` back exactly: the old budget in cents, the old status, or (for a version change)
    the version {number, creative_id} with the old creative or the one Put it back would pick. Anything else is a
    plain new change, never a Put it back."""
    action = change.get("action")
    if action == "budget":
        try:
            return int(value) == int(change["old_value"])
        except (TypeError, ValueError, KeyError):
            return False
    if action == "status":
        return value is not None and value == change.get("old_value")
    if action in ("update_creative", "restore_creative") and isinstance(value, dict):
        if str(value.get("creative_id")) == str(change.get("old_value")):
            return True
        return value.get("number") is not None and value.get("number") == _back_number(change, list(versions))
    return False


def undo_plan(change, entity_now, versions, money):
    """What Put it back would fill the existing dialog with, while the change is still in place:
    {"plan": {...} | None, "reason": words | None}. Nothing here writes anything."""
    action, level, eid, name = change.get("action"), change.get("level"), change.get("entity_id"), change.get("entity_name")
    base = {"level": level, "id": eid, "name": name}
    if action == "budget":
        gone = _gone(entity_now, "changed")
        if gone:
            return {"plan": None, "reason": gone}
        try:
            old, new = int(change["old_value"]), int(change["new_value"])
        except (TypeError, ValueError, KeyError):
            return {"plan": None, "reason": "Change it back on the ad's page."}
        now = entity_now.get("daily_budget_cents")
        if now != new:
            return {"plan": None, "reason": f"The budget was changed again since: it's {money(now)} a day now." if now else
                    "The budget was changed again since."}
        return {"plan": {"kind": "budget", **base, "from_cents": new, "to_cents": old}, "reason": None}
    if action == "status":
        old, new = change.get("old_value"), change.get("new_value")
        if old not in ("ACTIVE", "PAUSED"):
            return {"plan": None, "reason": "Change it back on the ad's page."}
        gone = _gone(entity_now, "switched")
        if gone:
            return {"plan": None, "reason": gone}
        if entity_now.get("status") != new:
            return {"plan": None, "reason": f"It's already {'on' if old == 'ACTIVE' else 'off'} again."}
        return {"plan": {"kind": "status", **base, "to": old}, "reason": None}
    if action in ("update_creative", "restore_creative"):
        gone = _gone(entity_now, "switched")
        if gone:
            return {"plan": None, "reason": gone}
        made = CREATIVE.search(str(change.get("new_value") or ""))
        if not made or entity_now.get("creative_id") != made.group(1):
            return {"plan": None, "reason": "The ad has a newer version since."}
        number = _back_number(change, versions)
        if not number:
            return {"plan": None, "reason": "Change it back on the ad's page."}
        return {"plan": {"kind": "version", **base, "number": number}, "reason": None}
    return {"plan": None, "reason": "Change it back on the ad's page."}
