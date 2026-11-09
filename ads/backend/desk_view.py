"""How the Claude page reads Claude's work: which ad each proposal is about, what became
of it, and which ads are versions of one another (a family). Pure functions; desk_api
feeds them the rows."""
from datetime import datetime, timedelta

VERSION_REQUEST = "make a new version"
LINK_WINDOW = timedelta(minutes=5)
RESULT_STATES = {
    "ACTIVE": ("live", "On"), "IN_PROCESS": ("review", "In review at Meta"),
    "PENDING_REVIEW": ("review", "In review at Meta"), "ARCHIVED": ("archived", "Archived"),
    "DELETED": ("deleted", "Deleted"), "DISAPPROVED": ("failed", "Rejected by Meta"),
}
DECIDED = {"pending": ("waiting", "Waiting for you"), "declined": ("declined", "Declined"),
           "expired": ("expired", "Expired"), "failed": ("failed", "Meta refused it")}


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
