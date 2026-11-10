"""One timeline per campaign, ad set or ad: Meta's status changes, changes made from the console and
Claude's proposals that were decided. Pure."""

SOURCE = {"poll": "Meta", "webhook": "Meta", "backfill": "Meta", "console": None}


def _tone(r):
    new = r.get("new_value")
    if r.get("field") in ("review", "issues"):
        return "bad" if new else "ok"
    if new in ("DISAPPROVED", "WITH_ISSUES") or (r.get("field") == "learning" and new == "FAIL"):
        return "bad"
    if new in ("IN_PROCESS", "PENDING_REVIEW"):
        return "warn"
    return "ok" if new == "ACTIVE" else ""


def change_title(c, money):
    action, old, new = c["action"], c.get("old_value"), c.get("new_value")
    if action == "status":
        on = new == "ACTIVE"
        return ("Turned it on" if on else "Turned it off") if c.get("ok") else ("Tried to turn it on" if on else "Tried to turn it off")
    if action == "budget":
        try:
            words = f"Budget {money(int(old))} → {money(int(new))} a day"
        except (TypeError, ValueError):
            words = "Budget changed"
        return words if c.get("ok") else "Tried to change the budget"
    return {"archive": "Archived", "delete": "Deleted", "create": "Created", "copy": "Copied",
            "subscribe": "Subscribed", "unsubscribe": "Unsubscribed"}.get(action, action.replace("_", " ").capitalize())


def merge(status_events, changes, proposals, money):
    linked = {s.get("change_id") for s in status_events if s.get("change_id")}
    items = []
    for s in status_events:
        by = s.get("by_name") if s.get("source") == "console" else SOURCE.get(s.get("source"), "Meta")
        items.append({"kind": "status", "at": s["at"], "title": s["headline"], "sub": None, "by": by, "tone": _tone(s)})
    for c in changes:
        if c["action"] == "status" and c["id"] in linked and c.get("ok"):
            continue  # the status event already says it, with who did it
        items.append({"kind": "change", "at": c["created_at"], "title": change_title(c, money),
                      "sub": c.get("error") if not c.get("ok") else None, "by": c.get("user_name"),
                      "tone": "" if c.get("ok") else "bad"})
    for p in proposals:
        if not p.get("decided_at"):
            continue
        word = {"applied": "applied", "approved": "approved", "declined": "declined", "failed": "failed"}.get(p["status"], p["status"])
        items.append({"kind": "proposal", "at": p["decided_at"], "title": f"Claude's idea {word}: {p['title']}", "sub": None,
                      "by": None, "tone": "bad" if p["status"] == "failed" else ""})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items
