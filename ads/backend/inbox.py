"""Inbox: one feed of what changed and what's waiting, per person, with read/unread.

Items come from three places: alerts (status changes from Meta, money, tracking), new leads and
Claude's pending proposals. Each is either Needs action (`need`) or for your information (FYI):
Needs action = open problems (conditions), open warn/bad events (closed by their owner), waiting
suggestions and leads nobody has tried yet (the Today rule, `today.waiting`). A problem fixed since
moves to FYI and leaves the count. `build`, `pick`, `counts` and `category` are pure."""
from datetime import datetime, timedelta, timezone

import db
import today

CATEGORY = {
    "ad_rejected": "status", "ad_approved": "status", "learning_limited": "status", "no_delivery": "status",
    "fatigue": "status", "changed_outside": "status", "outside_edit": "money", "change_result": "money",
    "spend_cap": "money", "cap_soon": "money", "spend_limit_mismatch": "money", "pace_over": "money", "day_overspend": "money",
    "week_overspend": "money", "cpl_high": "money", "no_leads": "money",
    "tracking": "system", "events_quiet": "system", "stale_data": "system",
    "report_review": "system", "report_sent": "system", "numbers_off": "system", "link_down": "system",
    "draft_new": "status", "draft_problems": "status",
    "qualified_low": "leads", "junk_high": "leads",
}
CATEGORIES = ("status", "leads", "claude", "money", "system")
DAYS = 30


def category(rule):
    return CATEGORY.get(rule, "system")


FYI_WHILE_INFO = {"numbers_off", "link_down", "draft_problems"}  # D1 / AM-A: for information at first; it needs action once it stays (warn)
ADMIN_ONLY = {"draft_new", "draft_problems"}  # AM-B: drafts are the owner's and account admins' (clients never see them)


def _alert_needs(a):
    if a.get("resolved_at") is not None:
        return False
    if a["rule"] in FYI_WHILE_INFO and a["level"] == "info":
        return False
    return a.get("kind", "condition") == "condition" or a["level"] in ("warn", "bad")


DONE_OK = {"outside_edit", "change_result"}  # alerts.DONE_OK: open events a person closes with Done
DIAGNOSE_DAYS = 3  # Claude can still look into an alert this long after it cleared ("why did it happen")


def _alert_actions(a, item, snoozed, now, now_local, runs, money=None):
    """What an admin may do with this alert: Got it (snooze), Wake it now, Diagnose with Claude, Done."""
    import diagnose
    import snooze
    acts = []
    open_ = a.get("resolved_at") is None
    if open_ and not snoozed and snooze.choices(a):
        acts.append("snooze")
        item["choices"] = snooze.offer(a, now_local or now, **({"money": money} if money else {}))
    if snoozed:
        acts.append("wake")
    if diagnose.can_diagnose(a["rule"]) and (open_ or a["resolved_at"] > now - timedelta(days=DIAGNOSE_DAYS)):
        acts.append("diagnose")
        item["diagnose"] = (runs or {}).get(diagnose.episode_key(a["rule"], a.get("entity_id")))
    if a["rule"] in DONE_OK and open_ and a.get("kind") == "event":
        acts.append("done")
    return acts


def _since(item, first, here):
    import words
    item.update(since=first, since_day=words.day(words.local(first, here.tzinfo)), days_open=words.days_since(first, here))


def build(alerts, leads, proposals, read_keys, can_close=False, snoozes=None, runs=None, now=None, now_local=None, client=False,
          money=None):
    """`can_close`: the person is an admin, who may snooze, wake, diagnose and close owner-closed events.
    `snoozes`: {(rule, entity_id): snooze view} in force; `runs`: {episode key: latest diagnose run}.
    A problem open for days is one item (its newest row, `since` its first); an earlier episode that cleared
    keeps its newest row. A snoozed problem is FYI and quiet rows are never new. Clients get none of it."""
    now = now or datetime.now(timezone.utc)
    here = now_local or now  # days are counted by the account's calendar (diagnose.prompt counts the same way)
    snoozes = snoozes or {}
    items = []
    episodes = {}  # (rule, entity) -> {"open": item, "closed": item}
    for a in sorted(alerts, key=lambda x: (x["created_at"], x["id"]), reverse=True):
        key = f"alert:{a['id']}"
        condition = a.get("kind", "condition") == "condition"
        if condition:
            kept = episodes.setdefault((a["rule"], a.get("entity_id")), {})
            slot = "open" if a.get("resolved_at") is None else "closed"
            if slot in kept:
                # The item stands for every row of its episode, so a link to an older row still finds it.
                kept[slot]["ids"].append(a["id"])
                if slot == "open":
                    _since(kept["open"], a["created_at"], here)
                continue
        snoozed = snoozes.get((a["rule"], a.get("entity_id"))) if condition and a.get("resolved_at") is None else None
        item = {"key": key, "category": category(a["rule"]), "rule": a["rule"], "level": a["level"],
                "title": a["title"], "lines": a.get("lines") or [], "href": a.get("href"), "at": a["created_at"],
                "entity_id": a.get("entity_id"), "open": a.get("resolved_at") is None, "need": _alert_needs(a) and not snoozed,
                "resolved": condition and a.get("resolved_at") is not None,
                "unread": key not in read_keys and not a.get("quiet"), "alert_id": a["id"]}
        if condition:
            item["ids"] = [a["id"]]
            _since(item, a["created_at"], here)
            kept[slot] = item
        if not client:
            item["snooze"] = snoozed
            item["actions"] = _alert_actions(a, item, snoozed, now, now_local, runs, money) if can_close else []
        items.append(item)
    for l in leads:
        key = f"lead:{l['id']}"
        if l.get("repeat_of"):  # L2: someone asking again is worked on their first lead, so it is only for your information
            items.append({"key": key, "category": "leads", "rule": "lead_repeat", "level": "info",
                          "title": f"{l.get('full_name') or 'Someone'} asked again",
                          "lines": [f"From {l['ad_name']}" if l.get("ad_name") else "From a lead form", "Work it on their first lead"],
                          "href": f"/leads.html#lead={l['repeat_of']}", "at": l["created_time"], "entity_id": None, "open": False,
                          "need": False, "unread": key not in read_keys})
            continue
        items.append({"key": key, "category": "leads", "rule": "new_lead", "level": "lead",
                      "title": f"New lead: {l.get('full_name') or 'no name'}",
                      "lines": [f"From {l['ad_name']}" if l.get("ad_name") else "From a lead form"],
                      "href": f"/leads.html#lead={l['id']}", "at": l["created_time"], "entity_id": None, "open": l["status"] == "new",
                      "need": today.waiting(l), "unread": l["status"] == "new" and key not in read_keys})
    for p in proposals:
        key = f"proposal:{p['id']}"
        # A suggestion from Diagnose with Claude says which alert it answers.
        lines = [f"From: {p['alert_title']}"] if p.get("alert_title") else [p["entity_name"]] if p.get("entity_name") else []
        items.append({"key": key, "category": "claude", "rule": "proposal", "level": "claude",
                      "title": f"Claude suggests: {p.get('summary') or 'a change'}",
                      "lines": lines, "href": f"/desk.html#p/{p['id']}",
                      "at": p["created_at"], "entity_id": p.get("entity_id"), "open": True, "need": True,
                      "proposal_id": p["id"], "unread": key not in read_keys})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items


def with_subjects(items, known):
    """Each item names the campaign, ad set or ad it is about (known: {id: {level, name}}), or None."""
    for i in items:
        k = known.get(i.get("entity_id")) if i.get("entity_id") else None
        i["subject"] = {"level": k["level"], "id": i["entity_id"], "name": k["name"]} if k else None
    return items


def item_keys(alerts, leads, proposals):
    """The keys build() gives these items: the only read marks worth loading (audit A3-131)."""
    return [f"alert:{a['id']}" for a in alerts] + [f"lead:{l['id']}" for l in leads] + [f"proposal:{p['id']}" for p in proposals]


BOXES = ("need", "fyi", "all")


def in_box(item, box):
    return box not in ("need", "fyi") or item["need"] == (box == "need")


def pick(items, filt, kind, box="all"):
    return [i for i in items if in_box(i, box) and (filt != "unread" or i["unread"]) and (kind in (None, "", "all") or i["category"] == kind)]


def counts(items):
    """unread: everything unread (the old badge). need_unread drives the badge now: what needs you and is new."""
    out = {"unread": sum(1 for i in items if i["unread"])}
    for c in CATEGORIES:
        out[c] = sum(1 for i in items if i["unread"] and i["category"] == c)
    out["need"] = sum(1 for i in items if i["need"])
    out["need_unread"] = sum(1 for i in items if i["need"] and i["unread"])
    out["fyi"] = sum(1 for i in items if not i["need"])
    out["fyi_unread"] = sum(1 for i in items if not i["need"] and i["unread"])
    return out


def kinds(items):
    """How many of the listed items are of each kind (the filter chips)."""
    return {c: sum(1 for i in items if i["category"] == c) for c in CATEGORIES}


# ---------------------------------------------------------------- database

ALERT_COLS = ("id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at, kind, "
              "measure::float8 AS measure, quiet")


def items_for(user):
    import account_info
    import alerts as alert_rules
    from auth import visible_campaign_ids
    from desk_api import latest_runs
    ids = visible_campaign_ids(user)
    if ids is None:
        alerts = db.query(f"SELECT {ALERT_COLS} FROM alerts WHERE created_at > now() - make_interval(days => %s) "
                          "ORDER BY id DESC LIMIT 300", (DAYS,))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status, first_contacted_at, meeting_status, is_test, repeat_of FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' ORDER BY created_time DESC LIMIT 100")
    else:
        alerts = db.query(f"SELECT {ALERT_COLS} FROM alerts WHERE created_at > now() - make_interval(days => %s) AND campaign_id = ANY(%s) "
                          "ORDER BY id DESC LIMIT 300", (DAYS, ids))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status, first_contacted_at, meeting_status, is_test, repeat_of FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' AND campaign_id = ANY(%s) ORDER BY created_time DESC LIMIT 100", (ids,))
    proposals = []
    if user["role"] != "client":
        # Claude's suggestions are internal: admins see them all, teammates those about their campaigns.
        mine = "" if ids is None else """AND COALESCE((SELECT a.campaign_id FROM ads a WHERE a.id = p.entity_id),
                                                  (SELECT s.campaign_id FROM adsets s WHERE s.id = p.entity_id),
                                                  (SELECT c.id FROM campaigns c WHERE c.id = p.entity_id)) = ANY(%s)"""
        proposals = db.query(f"""SELECT p.id, p.title AS summary, p.created_at, p.entity_id, p.entity_name,
                                        CASE WHEN t.kind = 'diagnose' THEN t.options->'alert'->>'title' END AS alert_title
                                 FROM desk_proposals p LEFT JOIN desk_tasks t ON t.id = p.task_id
                                 WHERE p.status = 'pending' {mine} ORDER BY p.id DESC LIMIT 50""", None if ids is None else (ids,))
    client = user["role"] == "client"
    if client:
        alerts = [a for a in alerts if category(a["rule"]) == "status" and a["rule"] not in ADMIN_ONLY]
    keys = item_keys(alerts, leads, proposals)
    reads = {r["item_key"] for r in db.query("SELECT item_key FROM inbox_reads WHERE user_id = %s AND item_key = ANY(%s)",
                                             (user["id"], keys))} if keys else set()
    admin = user["role"] == "admin"
    tz = account_info.tz()
    snoozes = {} if client else {pair: alert_rules.snooze_view(s, tz) for pair, s in alert_rules.live_snoozes().items()}
    runs = latest_runs("diagnose", "alert_key") if admin else None
    now = datetime.now(timezone.utc)
    currency = account_info.currency()
    items = build(alerts, leads, proposals, reads, can_close=admin, snoozes=snoozes, runs=runs, now=now,
                  now_local=now.astimezone(tz), client=client,
                  money=lambda c: account_info.money(round(c), currency, whole=not round(c) % 100))
    ids = list({i["entity_id"] for i in items if i.get("entity_id")})
    known = {}
    if ids:
        for level, table in (("campaign", "campaigns"), ("adset", "adsets"), ("ad", "ads")):
            for r in db.query(f"SELECT id, name FROM {table} WHERE id = ANY(%s)", (ids,)):
                known[r["id"]] = {"level": level, "name": r["name"]}
    return with_subjects(items, known)


def snoozed_count(items):
    """Snoozed problems in this person's feed (Today's quiet line)."""
    return sum(1 for i in items if i.get("snooze"))


def mark_read(user, keys):
    if keys:
        db.execute("INSERT INTO inbox_reads (user_id, item_key) SELECT %s, unnest(%s::text[]) ON CONFLICT DO NOTHING",
                   (user["id"], list(keys)))
