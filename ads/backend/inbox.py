"""Inbox: one feed of what changed and what's waiting, per person, with read/unread.

Items come from three places: alerts (status changes from Meta, money, tracking), new leads and
Claude's pending proposals. `build`, `pick`, `counts` and `category` are pure."""
import db

CATEGORY = {
    "ad_rejected": "status", "ad_approved": "status", "learning_limited": "status", "no_delivery": "status",
    "fatigue": "status", "changed_outside": "status",
    "spend_cap": "money", "cap_soon": "money", "pace_over": "money", "day_overspend": "money",
    "week_overspend": "money", "cpl_high": "money", "no_leads": "money",
    "tracking": "system", "events_quiet": "system", "stale_data": "system",
}
CATEGORIES = ("status", "leads", "claude", "money", "system")
DAYS = 30


def category(rule):
    return CATEGORY.get(rule, "system")


def build(alerts, leads, proposals, read_keys):
    items = []
    for a in alerts:
        key = f"alert:{a['id']}"
        items.append({"key": key, "category": category(a["rule"]), "rule": a["rule"], "level": a["level"],
                      "title": a["title"], "lines": a.get("lines") or [], "href": a.get("href"), "at": a["created_at"],
                      "entity_id": a.get("entity_id"), "open": a.get("resolved_at") is None, "unread": key not in read_keys})
    for l in leads:
        key = f"lead:{l['id']}"
        items.append({"key": key, "category": "leads", "rule": "new_lead", "level": "lead",
                      "title": f"New lead: {l.get('full_name') or 'no name'}",
                      "lines": [f"From {l['ad_name']}" if l.get("ad_name") else "From a lead form"],
                      "href": f"/leads.html#lead={l['id']}", "at": l["created_time"], "entity_id": None, "open": l["status"] == "new",
                      "unread": l["status"] == "new" and key not in read_keys})
    for p in proposals:
        key = f"proposal:{p['id']}"
        items.append({"key": key, "category": "claude", "rule": "proposal", "level": "claude",
                      "title": f"Claude suggests: {p.get('summary') or 'a change'}",
                      "lines": [p["entity_name"]] if p.get("entity_name") else [], "href": "/desk.html#waiting",
                      "at": p["created_at"], "entity_id": p.get("entity_id"), "open": True, "unread": key not in read_keys})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items


def pick(items, filt, kind):
    return [i for i in items if (filt != "unread" or i["unread"]) and (kind in (None, "", "all") or i["category"] == kind)]


def counts(items):
    out = {"unread": sum(1 for i in items if i["unread"])}
    for c in CATEGORIES:
        out[c] = sum(1 for i in items if i["unread"] and i["category"] == c)
    return out


# ---------------------------------------------------------------- database

def items_for(user):
    from auth import visible_campaign_ids
    ids = visible_campaign_ids(user)
    if ids is None:
        alerts = db.query("SELECT id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at "
                          "FROM alerts WHERE created_at > now() - make_interval(days => %s) ORDER BY id DESC LIMIT 300", (DAYS,))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' ORDER BY created_time DESC LIMIT 100")
    else:
        alerts = db.query("SELECT id, rule, level, title, lines, href, entity_id, campaign_id, created_at, resolved_at "
                          "FROM alerts WHERE created_at > now() - make_interval(days => %s) AND campaign_id = ANY(%s) "
                          "ORDER BY id DESC LIMIT 300", (DAYS, ids))
        leads = db.query("SELECT id, full_name, ad_name, created_time, status FROM leads WHERE NOT is_test "
                         "AND created_time > now() - interval '7 days' AND campaign_id = ANY(%s) ORDER BY created_time DESC LIMIT 100", (ids,))
    proposals = []
    if user["role"] == "admin":
        proposals = db.query("""SELECT p.id, p.title AS summary, p.created_at, p.entity_id, p.entity_name FROM desk_proposals p
                                WHERE p.status = 'pending' ORDER BY p.id DESC LIMIT 50""")
    if user["role"] == "client":
        alerts = [a for a in alerts if category(a["rule"]) == "status"]
    reads = {r["item_key"] for r in db.query("SELECT item_key FROM inbox_reads WHERE user_id = %s", (user["id"],))}
    return build(alerts, leads, proposals, reads)


def mark_read(user, keys):
    for key in keys:
        db.execute("INSERT INTO inbox_reads (user_id, item_key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user["id"], key))
