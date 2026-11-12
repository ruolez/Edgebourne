"""Inbox: one feed of what changed and what's waiting, per person, with read/unread.

Items come from three places: alerts (status changes from Meta, money, tracking), new leads and
Claude's pending proposals. Each is either Needs action (`need`) or for your information (FYI):
Needs action = open problems (conditions), open warn/bad events (closed by their owner), waiting
suggestions and leads nobody has tried yet (the Today rule, `today.waiting`). A problem fixed since
moves to FYI and leaves the count. `build`, `pick`, `counts` and `category` are pure."""
import db
import today

CATEGORY = {
    "ad_rejected": "status", "ad_approved": "status", "learning_limited": "status", "no_delivery": "status",
    "fatigue": "status", "changed_outside": "status", "outside_edit": "money",
    "spend_cap": "money", "cap_soon": "money", "pace_over": "money", "day_overspend": "money",
    "week_overspend": "money", "cpl_high": "money", "no_leads": "money",
    "tracking": "system", "events_quiet": "system", "stale_data": "system",
}
CATEGORIES = ("status", "leads", "claude", "money", "system")
DAYS = 30


def category(rule):
    return CATEGORY.get(rule, "system")


def _alert_needs(a):
    if a.get("resolved_at") is not None:
        return False
    return a.get("kind", "condition") == "condition" or a["level"] in ("warn", "bad")


DONE_OK = {"outside_edit"}  # alerts.DONE_OK: open events a person closes with Done


def build(alerts, leads, proposals, read_keys, can_close=False):
    """`can_close`: the person may close owner-closed events (admins): those items get the action "done"."""
    items = []
    episodes = set()  # a condition still open from an earlier day needs action once, as its newest row
    for a in sorted(alerts, key=lambda x: (x["created_at"], x["id"]), reverse=True):
        key = f"alert:{a['id']}"
        need = _alert_needs(a)
        if need and a.get("kind", "condition") == "condition":
            episode = (a["rule"], a.get("entity_id"))
            need = episode not in episodes
            episodes.add(episode)
        items.append({"key": key, "category": category(a["rule"]), "rule": a["rule"], "level": a["level"],
                      "title": a["title"], "lines": a.get("lines") or [], "href": a.get("href"), "at": a["created_at"],
                      "entity_id": a.get("entity_id"), "open": a.get("resolved_at") is None, "need": need,
                      "resolved": a.get("kind", "condition") == "condition" and a.get("resolved_at") is not None,
                      "unread": key not in read_keys, "alert_id": a["id"],
                      "actions": ["done"] if can_close and a["rule"] in DONE_OK and a.get("resolved_at") is None
                      and a.get("kind") == "event" else []})
    for l in leads:
        key = f"lead:{l['id']}"
        items.append({"key": key, "category": "leads", "rule": "new_lead", "level": "lead",
                      "title": f"New lead: {l.get('full_name') or 'no name'}",
                      "lines": [f"From {l['ad_name']}" if l.get("ad_name") else "From a lead form"],
                      "href": f"/leads.html#lead={l['id']}", "at": l["created_time"], "entity_id": None, "open": l["status"] == "new",
                      "need": today.waiting(l), "unread": l["status"] == "new" and key not in read_keys})
    for p in proposals:
        key = f"proposal:{p['id']}"
        items.append({"key": key, "category": "claude", "rule": "proposal", "level": "claude",
                      "title": f"Claude suggests: {p.get('summary') or 'a change'}",
                      "lines": [p["entity_name"]] if p.get("entity_name") else [], "href": f"/desk.html#p/{p['id']}",
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

def items_for(user):
    from auth import visible_campaign_ids
    ids = visible_campaign_ids(user)
    if ids is None:
        alerts = db.query("SELECT id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at, kind "
                          "FROM alerts WHERE created_at > now() - make_interval(days => %s) ORDER BY id DESC LIMIT 300", (DAYS,))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status, first_contacted_at, is_test FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' ORDER BY created_time DESC LIMIT 100")
    else:
        alerts = db.query("SELECT id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at, kind "
                          "FROM alerts WHERE created_at > now() - make_interval(days => %s) AND campaign_id = ANY(%s) "
                          "ORDER BY id DESC LIMIT 300", (DAYS, ids))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status, first_contacted_at, is_test FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' AND campaign_id = ANY(%s) ORDER BY created_time DESC LIMIT 100", (ids,))
    proposals = []
    if user["role"] != "client":
        # Claude's suggestions are internal: admins see them all, teammates those about their campaigns.
        mine = "" if ids is None else """AND COALESCE((SELECT a.campaign_id FROM ads a WHERE a.id = p.entity_id),
                                                  (SELECT s.campaign_id FROM adsets s WHERE s.id = p.entity_id),
                                                  (SELECT c.id FROM campaigns c WHERE c.id = p.entity_id)) = ANY(%s)"""
        proposals = db.query(f"""SELECT p.id, p.title AS summary, p.created_at, p.entity_id, p.entity_name FROM desk_proposals p
                                 WHERE p.status = 'pending' {mine} ORDER BY p.id DESC LIMIT 50""", None if ids is None else (ids,))
    if user["role"] == "client":
        alerts = [a for a in alerts if category(a["rule"]) == "status"]
    keys = item_keys(alerts, leads, proposals)
    reads = {r["item_key"] for r in db.query("SELECT item_key FROM inbox_reads WHERE user_id = %s AND item_key = ANY(%s)",
                                             (user["id"], keys))} if keys else set()
    items = build(alerts, leads, proposals, reads, can_close=user["role"] == "admin")
    ids = list({i["entity_id"] for i in items if i.get("entity_id")})
    known = {}
    if ids:
        for level, table in (("campaign", "campaigns"), ("adset", "adsets"), ("ad", "ads")):
            for r in db.query(f"SELECT id, name FROM {table} WHERE id = ANY(%s)", (ids,)):
                known[r["id"]] = {"level": level, "name": r["name"]}
    return with_subjects(items, known)


def mark_read(user, keys):
    if keys:
        db.execute("INSERT INTO inbox_reads (user_id, item_key) SELECT %s, unnest(%s::text[]) ON CONFLICT DO NOTHING",
                   (user["id"], list(keys)))
