"""How the Claude page reads Claude's work: which ad each proposal is about, what became
of it, which ads are versions of one another (a family), and which runs make up one
conversation. Pure functions; desk_api feeds them the rows."""
import re
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
           "applying": ("working", "Being applied on Meta"), "revised": ("declined", "Sent back to Claude")}


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


def thread_key(t):
    """A conversation is named after its first run."""
    return t.get("thread_id") or t["id"]


def _waiting(t):
    return [p for p in t["proposals"] if p["status"] == "pending"]


def _in_view(t):
    return not t.get("archived_at") or t["status"] in ("queued", "claimed", "running") or bool(_waiting(t))


def _thread(key, turns):
    """One conversation from its runs, oldest first. Cleared runs drop out; once every run is
    cleared the whole conversation shows under Cleared."""
    shown = [t for t in turns if _in_view(t)]
    cleared = not shown
    shown = shown or turns
    statuses = {t["status"] for t in shown}
    waiting = sum(len(_waiting(t)) for t in shown)
    if statuses & {"claimed", "running"}:
        state = "working"
    elif "queued" in statuses:
        state = "queued"
    elif waiting:
        state = "needs"
    else:
        state = {"failed": "failed", "cancelled": "stopped"}.get(shown[-1]["status"], "done")
    return {"id": key, "turns": [t["id"] for t in shown], "state": state, "waiting": waiting, "cleared": cleared,
            "fresh": [t["id"] for t in shown if is_fresh(t)], "last_at": shown[-1].get("finished_at") or shown[-1]["created_at"]}


def board(tasks):
    """Every conversation with its state, and the order the list shows them in."""
    groups = {}
    for t in sorted(tasks, key=lambda t: t["id"]):
        groups.setdefault(thread_key(t), []).append(t)
    threads = {key: _thread(key, turns) for key, turns in groups.items()}
    queued = sorted((t for t in tasks if t["status"] == "queued"), key=lambda t: (t.get("queue_rank") or 0, t["id"]))
    line = []
    for t in queued:
        key = thread_key(t)
        if threads[key]["state"] == "queued" and key not in line:
            line.append(key)
    newest = lambda keys: sorted(keys, key=lambda k: _time(threads[k]["last_at"]), reverse=True)  # noqa: E731
    return {"threads": threads, "queue": [t["id"] for t in queued], "line": line,
            "working": [k for k, t in threads.items() if t["state"] == "working"],
            "recent": newest(k for k, t in threads.items() if t["state"] in ("needs", "failed", "stopped", "done") and not t["cleared"]),
            "cleared": newest(k for k, t in threads.items() if t["cleared"])}


SUGGESTION_FIELDS = ("id", "kind", "title", "status", "rationale", "entity_name", "field", "current_value", "proposed_value", "payload", "failure")


def transcript(turns, limit=6, body=6000):
    """The conversation so far for a follow-up run: what was asked, said and decided, oldest first."""
    cut = lambda text: text if len(text) <= body else text[:body] + "…"  # noqa: E731
    return [{"id": t["id"], "kind": t["kind"], "you": t["prompt"], "status": t["status"], "claude": t.get("summary"), "error": t.get("error"),
             "reports": [{"title": r["title"], "body": cut(r["body"])} for r in t["reports"]],
             "suggestions": [{k: p.get(k) for k in SUGGESTION_FIELDS} for p in t["proposals"]]} for t in turns[-limit:]]


def resume_from(turns):
    """The latest earlier run the Mac actually started: its Claude session is the one to continue."""
    return next((t["id"] for t in reversed(turns) if t.get("claimed_at")), None)


def needs_follow_through(p):
    """Accepting these changes nothing by itself, so Claude has to pick them up."""
    return p["kind"] not in ("experiment", "tags") and not is_version_request(p)


def accepted_prompt(p):
    return f"I accepted your suggestion: {p['title']}" + (f"\nNext step you wrote: {p['expected']}" if p.get("expected") else "")


def accepted_run(p, tasks):
    """The run that accepting this suggestion started."""
    return next((t for t in tasks if ((t.get("options") or {}).get("accepted") or {}).get("id") == p["id"]), None)


def accepted_state(p, run):
    if run["status"] in ("queued", "claimed", "running"):
        return ("working", "Claude is on it")
    return {"done": ("done", "Claude answered below"), "failed": ("failed", "Claude didn't finish")}.get(run["status"], ("declined", "Stopped"))


def now(rows, show=5):
    """What the Mac is doing, for the status line on every page. rows = the open runs."""
    title = lambda t: (t.get("options") or {}).get("schedule") or str(t["prompt"]).split("\n")[0]  # noqa: E731
    live = next((t for t in rows if t["status"] in ("claimed", "running")), None)
    line = sorted((t for t in rows if t["status"] == "queued"), key=lambda t: (t.get("queue_rank") or 0, t["id"]))
    return {"working": live and {"id": live["id"], "thread": thread_key(live), "title": title(live), "progress": live["progress"],
                                 "since": live["claimed_at"] or live["created_at"]},
            "next": [{"id": t["id"], "thread": thread_key(t), "title": title(t)} for t in line[:show]], "queued": len(line)}


AD_CODE = re.compile(r"^([A-Z]{1,3}\d{1,3})\b")


def mentioned_ads(text, ads, limit=8):
    """Ad ids a response talks about, in reading order: by full name, or by short code ("N3").
    A bare code means the version that runs; "N1 · v2" means that version."""
    ads = [a for a in ads if a.get("effective_status") != "DELETED" and a.get("name")]
    found, lower = {}, (text or "").lower()
    for ad in sorted(ads, key=lambda a: len(a["name"]), reverse=True):
        name = ad["name"].lower()
        at = lower.find(name)
        if at >= 0:
            found[ad["id"]] = at
            lower = lower.replace(name, " " * len(name))
    groups = {}
    for ad in ads:
        m = AD_CODE.match(ad["name"])
        if m:
            groups.setdefault(m.group(1), []).append(ad)
    for code, members in groups.items():
        hit = re.search(rf"(?<![a-z0-9]){code.lower()}(?![a-z0-9])(?:\s*·\s*v(\d+))?", lower)
        if not hit:
            continue
        versioned = [a for a in members if hit.group(1) and a["name"].lower().endswith(f"v{hit.group(1)}")]
        running = [a for a in members if a.get("effective_status") == "ACTIVE"]
        pick = (versioned or running or members)[0]
        found.setdefault(pick["id"], hit.start())
    return sorted(found, key=found.get)[:limit]


REVIEW_ORDER = ("money", "live", "create", "mac", "local", "blocked")
PLAN_GROUPS = {"vertical": "live", "create": "create", "render": "mac", "experiment": "local", "tags": "local", "record": "mac"}


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
