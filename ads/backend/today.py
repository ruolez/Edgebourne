"""Today: one ranked queue of what needs the person now (00-PLAN shared piece S9).

Groups, in order: leads to call, ads with problems (and tracking that's broken), follow-ups (L1),
decisions (Claude's suggestions, a report waiting for review), money, keeping things running, later
today (L1). Each thing shows once. `waiting`, `urgency`, `lead_bucket`, `group_of` and `rank` are pure.

The lead urgency rule is the one Today, Leads and the reminders share: a lead waits for a first call
while it is New, nobody has tried it (a logged call, an email or a stage move; a note doesn't count) and no
call is booked; green until the 5-minute reminder, amber until the hour one, late after that.
"""

FRESH_MINUTES = 5
LATE_MINUTES = 60
GROUPS = ("call", "problems", "follow", "decide", "money", "system", "later")
OLDEST_FIRST = {"call", "follow", "later"}  # people waiting: the longest wait first
SEVERITY = {"bad": 0, "warn": 1}
DECIDE_RULES = {"proposal", "report_review"}


def waiting(lead):
    """New, not a test, nobody tried yet (a call, an email or a stage move), and no call booked (L1)."""
    # A repeat (L2) is worked on its first lead: it never waits for a call of its own.
    return (lead.get("status") == "new" and not lead.get("is_test") and not lead.get("first_contacted_at")
            and lead.get("meeting_status") != "scheduled" and not lead.get("repeat_of"))


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


# L1's lead rows (followup.queue buckets): first calls and a booked call within the hour are calls to make now,
# overdue follow-ups and "did the call happen" are follow-ups, the rest of today's follow-ups come last.
LEAD_GROUPS = {"new_lead": "call", "meeting_soon": "call", "followup_overdue": "follow", "meeting_check": "follow",
               "followup_today": "later"}


def group_of(category, rule, level):
    if category == "leads" and rule in LEAD_GROUPS:
        return LEAD_GROUPS[rule]
    if rule in DECIDE_RULES:
        return "decide"
    # A lead-quality alert (W1b) is a problem with the ads, not a lead to call.
    if category in ("status", "leads") or (category == "system" and level == "bad"):
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
