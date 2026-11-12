"""Today: one ranked queue of what needs the person now (00-PLAN shared piece S9).

Groups, in order: leads to call, ads with problems (and tracking that's broken), follow-ups (L1),
decisions (Claude's suggestions, a report waiting for review), money, keeping things running, later
today (L1). Each thing shows once. `waiting`, `urgency`, `lead_bucket`, `group_of` and `rank` are pure.

The lead urgency rule is the one Today, Leads and the reminders share: a lead waits for a first call
while it is New and nobody has called, emailed or moved it; green until the 5-minute reminder, amber
until the hour one, late after that.
"""

FRESH_MINUTES = 5
LATE_MINUTES = 60
GROUPS = ("call", "problems", "follow", "decide", "money", "system", "later")
OLDEST_FIRST = {"call", "follow", "later"}  # people waiting: the longest wait first
SEVERITY = {"bad": 0, "warn": 1}
DECIDE_RULES = {"proposal", "report_review"}


def waiting(lead):
    return lead.get("status") == "new" and not lead.get("is_test") and not lead.get("first_contacted_at")


def _age_minutes(lead, now):
    return (now - lead["created_time"]).total_seconds() / 60


def urgency(lead, now):
    if not waiting(lead):
        return "done"
    age = _age_minutes(lead, now)
    return "fresh" if age < FRESH_MINUTES else "warm" if age < LATE_MINUTES else "late"


def lead_bucket(lead, now):
    """L1's buckets: 0 = the first hour (most likely to book), 2 = waiting longer."""
    return 0 if _age_minutes(lead, now) < LATE_MINUTES else 2


def group_of(category, rule, level):
    if category == "leads" and rule == "new_lead":
        return "call"
    if rule in DECIDE_RULES:
        return "decide"
    if category == "status" or (category == "system" and level == "bad"):
        return "problems"
    if category == "money":
        return "money"
    return "system"


def _sort_key(item):
    group = item.get("group")
    g = GROUPS.index(group) if group in GROUPS else len(GROUPS)
    at = item.get("at")
    t = at.timestamp() if at is not None else 0.0
    return (g, item.get("bucket") or 0, SEVERITY.get(item.get("level"), 2), at is None,
            t if group in OLDEST_FIRST else -t, str(item.get("key")))


def rank(items):
    """The queue in order; a thing listed twice keeps its highest place."""
    seen, out = set(), []
    for item in sorted(items, key=_sort_key):
        if item.get("key") in seen:
            continue
        seen.add(item.get("key"))
        out.append(item)
    return out
