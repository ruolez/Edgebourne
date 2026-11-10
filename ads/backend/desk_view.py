"""How the Claude page reads Claude's work: which ad each proposal is about, what became
of it, and which ads are versions of one another (a family). Pure functions; desk_api
feeds them the rows."""
from datetime import datetime, timedelta

import money_rules

VERSION_REQUEST = "make a new version"
LINK_WINDOW = timedelta(minutes=5)
RESULT_STATES = {
    "ACTIVE": ("live", "On"), "IN_PROCESS": ("review", "In review at Meta"),
    "PENDING_REVIEW": ("review", "In review at Meta"), "ARCHIVED": ("archived", "Archived"),
    "DELETED": ("deleted", "Deleted"), "DISAPPROVED": ("failed", "Rejected by Meta"),
}
DECIDED = {"pending": ("waiting", "Waiting for you"), "declined": ("declined", "Declined"),
           "expired": ("expired", "Expired"), "failed": ("failed", "Meta refused it"),
           "applying": ("working", "Being applied on Meta")}


def _time(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def is_version_request(p):
    return p["kind"] == "other" and (p.get("title") or "").lower().startswith(VERSION_REQUEST)


def proposal_ad(p, task):
    """The ad a proposal is about, or None when it is about a campaign, ad set or the account."""
    template = (p.get("payload") or {}).get("template_ad_id")
    if template:
        return template
    if p.get("entity_type"):
        return p["entity_id"] if p["entity_type"] == "ad" else None
    return (task.get("options") or {}).get("ad_id")


def followup_for(p, render_tasks):
    """The render run started from a 'Make a new version' request."""
    if not is_version_request(p) or p["status"] != "approved":
        return None
    for t in render_tasks:
        opts = t.get("options") or {}
        if opts.get("from_proposal") == p["id"]:
            return t
        if ("from_proposal" not in opts and opts.get("from_task") == p["task_id"] and p.get("decided_at")
                and _time(t["created_at"]) >= _time(p["decided_at"]) - LINK_WINDOW):
            return t
    return None


def proposal_state(p, result_ad, followup, made_state=None):
    """(key, words) for one proposal; made_state is the state of what a version request made."""
    if p["status"] in DECIDED:
        return DECIDED[p["status"]]
    if p["status"] == "applied":
        if result_ad:
            return RESULT_STATES.get(result_ad.get("effective_status"), ("off", "Created, off"))
        return ("applied", "Applied on Meta")
    if followup:
        if followup["status"] in ("queued", "claimed", "running"):
            return ("working", "Claude is making it")
        if followup["status"] != "done":
            return ("failed", "Claude didn't finish")
        return made_state or ("done", "Made")
    return ("approved", "Approved")


def families(tasks, results):
    """Group runs and proposals by ad family: an ad plus every ad created from it.
    tasks come newest first, each with its proposals; results maps proposal id → created ad id."""
    parent = {}
    for t in tasks:
        for p in t["proposals"]:
            ad, made = proposal_ad(p, t), results.get(p["id"])
            if ad and made and made != ad:
                parent[made] = ad

    def root(ad):
        seen = set()
        while ad in parent and ad not in seen:
            seen.add(ad)
            ad = parent[ad]
        return ad

    fams = {}

    def fam(key):
        return fams.setdefault(key, {"root": key, "ads": [], "tasks": [], "proposals": [], "pending": 0, "order": len(fams)})

    for t in tasks:
        about = (t.get("options") or {}).get("ad_id")
        f = fam(root(about) if about else None)
        f["tasks"].append(t["id"])
        for p in t["proposals"]:
            ad = proposal_ad(p, t)
            g = fam(root(ad)) if ad else f
            g["proposals"].append(p["id"])
            g["pending"] += p["status"] == "pending"
    made_order = {ad: pid for pid, ad in results.items()}
    for key, f in fams.items():
        if key is not None:
            members = [a for a in set(made_order) if root(a) == key and a != key]
            f["ads"] = [key] + sorted(members, key=made_order.get)
    ordered = sorted(fams.values(), key=lambda f: (f["root"] is None, f["pending"] == 0, f["order"]))
    for f in ordered:
        del f["order"]
    return ordered


def is_fresh(t):
    """Finished and not looked at yet: never opened, and none of its suggestions decided."""
    return bool(t.get("finished_at")) and not t.get("seen_at") and t["status"] != "cancelled" \
        and all(p["status"] == "pending" for p in t["proposals"])


def board(tasks):
    """Each request in exactly one tray, in reading order. tasks come newest first."""
    out = {"needs_you": [], "working": [], "next": [], "finished": [], "cleared": [], "fresh": []}
    finished, cleared, queued = [], [], []
    for t in tasks:
        waiting = any(p["status"] == "pending" for p in t["proposals"])
        if t["status"] in ("claimed", "running"):
            out["working"].append(t["id"])
        elif t["status"] == "queued":
            queued.append(t)
        elif waiting:
            out["needs_you"].append(t["id"])
        elif t.get("archived_at"):
            cleared.append(t)
        else:
            finished.append(t)
            if is_fresh(t):
                out["fresh"].append(t["id"])
    out["next"] = [t["id"] for t in sorted(queued, key=lambda t: (t.get("queue_rank") or 0, t["id"]))]
    out["finished"] = [t["id"] for t in sorted(finished, key=lambda t: _time(t["finished_at"] or t["created_at"]), reverse=True)]
    out["cleared"] = [t["id"] for t in sorted(cleared, key=lambda t: _time(t["archived_at"]), reverse=True)]
    return out


REVIEW_ORDER = ("money", "live", "create", "mac", "local", "blocked")
PLAN_GROUPS = {"vertical": "live", "create": "create", "render": "mac", "experiment": "local", "tags": "local", "record": "local"}


def review_item(p, plan):
    """How one suggestion shows on the Accept sheet: its group, whether it starts ticked, the reason
    it can't be accepted, and the exact approval body. Starting to spend and a step over +20% are
    never ticked for you, nor is a budget that moved since Claude read it."""
    kind, blocked, needs_tick, body, note = plan["kind"], None, False, {}, None
    group = PLAN_GROUPS.get(kind)
    if kind == "unclear":
        blocked = plan["problem"]
    elif kind == "budget":
        group = "money"
        blocked = plan.get("problem")
        seen = money_rules.parse_budget_text(p.get("current_value"))
        if seen is not None and seen != plan["from"]:
            note = f"Claude saw ${seen / 100:,.2f} a day. It's ${plan['from'] / 100:,.2f} now."
        needs_tick = bool(plan.get("big") or note)
        body = {"from_cents": plan["from"], "to_cents": plan["to"], "accept_big": bool(plan.get("big"))}
    elif kind == "status":
        turning_on = plan["to"] == "ACTIVE"
        group = "money" if turning_on else "live"
        needs_tick = turning_on
        daily = (plan.get("spend") or {}).get("daily_cents")
        if turning_on and daily:
            body = {"confirm_daily_cents": daily}
    return {"id": p["id"], "task_id": p["task_id"], "title": p["title"], "kind": p["kind"], "entity_name": p.get("entity_name"),
            "group": "blocked" if blocked else group, "blocked": blocked, "needs_tick": needs_tick,
            "tick": not blocked and not needs_tick, "conflict": None, "note": note, "plan": plan, "body": body}


def _conflict_key(p, plan):
    target = p.get("entity_id") or plan.get("ad_id") or (p.get("payload") or {}).get("template_ad_id")
    return f"{plan['kind']}:{target}" if plan["kind"] in ("budget", "status", "vertical", "render") and target else None


def review(pairs):
    """The Accept sheet for (proposal, plan) pairs. Two suggestions that change the same thing can't
    both go through, so neither starts ticked and the sheet lets one be picked."""
    items = [review_item(p, plan) for p, plan in pairs]
    keys = [None if i["blocked"] else _conflict_key(p, plan) for i, (p, plan) in zip(items, pairs)]
    for item, key in zip(items, keys):
        if key and keys.count(key) > 1:
            item.update(conflict=key, tick=False, needs_tick=True)
    return sorted(items, key=lambda i: REVIEW_ORDER.index(i["group"]))
