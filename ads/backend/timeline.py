"""One timeline per campaign, ad set or ad: Meta's status changes, changes made from the console and
Claude's suggestions that were decided. Pure."""
import re

import desk_view
import marks

SOURCE = {"poll": "Meta", "webhook": "Meta", "backfill": "Meta", "console": None}
LEVELS = ("campaign", "adset", "ad")
CREATIVE_ID = re.compile(r"\s*\(creative [^)]*\)$")
ADVICE_ADD = re.compile(r"\(\+(\d+(?:\.\d+)?)/day\)")  # advice_api writes a budget raise as "(+6.00/day)"
# Rows that store Meta's advice title as their entity_name, so it can't name the ad set or campaign.
NAMELESS = ("recommendation", "recommendation_check")
TONE_RANK = {"bad": 3, "warn": 2, "ok": 1, "": 0}
# Budget, bid, dates and audience: made outside the console when Meta reports them (status_history.SETUP).
SETUP_FIELDS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "bid_amount", "start_time", "end_time", "targeting")
ACCEPTED = {"big": "more than +20%", "recent": "under 3 days since the last change"}
# A decided suggestion, in the console's words (suggest.js DECIDED says the same).
DECIDED = {"applied": "accepted and applied", "approved": "accepted", "declined": "declined",
           "failed": "accepted, but Meta refused", "revised": "sent back to Claude",
           "unknown": "accepted, but Meta didn't answer (check Ads Manager)", "expired": "expired"}
# desk_view.CHECK_REFUSED, as a sentence after "Claude's suggestion".
_WHY = desk_view.CHECK_REFUSED[1].split(": ", 1)
CHECKED = f"accepted, but {_WHY[0].lower()} ({_WHY[1]})"


def _tone(r):
    new = r.get("new_value")
    if r.get("field") in ("review", "issues"):
        return "bad" if new else "ok"
    if new in ("DISAPPROVED", "WITH_ISSUES") or (r.get("field") == "learning" and new == "FAIL"):
        return "bad"
    if new in ("IN_PROCESS", "PENDING_REVIEW"):
        return "warn"
    return "ok" if new == "ACTIVE" else ""


def _plain(value):
    return CREATIVE_ID.sub("", str(value or "")).strip()


def change_title(c, money):
    action, old, new, ok = c["action"], c.get("old_value"), c.get("new_value"), c.get("ok")
    if action == "status":
        on = new == "ACTIVE"
        return ("Turned it on" if on else "Turned it off") if ok else ("Tried to turn it on" if on else "Tried to turn it off")
    if action == "budget":
        try:
            words = f"Budget {money(int(old))} → {money(int(new))} a day"
        except (TypeError, ValueError):
            words = "Budget changed"
        return words if ok else "Tried to change the budget"
    if action == "recommendation_check":
        return "Meta's advice set a different budget than shown"
    tried = {"update_creative": "Tried to update the ad", "restore_creative": "Tried to switch back to an earlier version",
             "placement_media": "Tried to add a 9:16 video for Reels and Stories", "duplicate": "Tried to duplicate it",
             "enhancement": "Tried to change one of Meta's automatic changes", "create": "Tried to create it",
             "recommendation": "Tried to apply Meta's advice"}
    if not ok and action in tried:
        return tried[action]
    if action == "duplicate":
        return f"Duplicated as “{new}”"
    if action == "update_creative":
        return f"Updated the ad: {_plain(new)}" if _plain(new) else "Updated the ad"
    if action == "restore_creative":
        return _plain(new) or "Switched back to an earlier version"
    if action == "placement_media":
        return "Added a 9:16 video for Reels and Stories"
    if action == "enhancement":
        return f"Meta's automatic change: {_plain(new)}"
    if action == "create":
        return f"Created “{_plain(new)}”" if new else "Created"
    if action == "rename":
        return f"Renamed to “{new}”"
    if action == "recommendation":
        words = ADVICE_ADD.sub(lambda m: f"(+{money(round(float(m.group(1)) * 100))} a day)", _plain(new))
        return f"Applied Meta's advice: {words}" if words else "Applied Meta's advice"
    return {"archive": "Archived", "delete": "Deleted", "copy": "Copied", "subscribe": "Subscribed",
            "unsubscribe": "Unsubscribed", "comment_reply": "Replied to a comment", "comment_hide": "Hid a comment",
            "comment_show": "Showed a comment again"}.get(action, action.replace("_", " ").capitalize())


def _refusal(c):
    """Who stopped a failed change: the console's own read-back check ("… not used") or Meta."""
    if c["action"] == "recommendation_check":
        return c.get("error")  # Meta did it, differently: not a refusal
    why = "Not applied" if desk_view.refused_by_check(c.get("new_value")) else "Meta refused"
    return f"{why}: {c['error']}" if c.get("error") else why


def checked_refusals(changes):
    """Ids of suggestions whose change the console's own read-back check stopped (not Meta)."""
    return {c["proposal_id"] for c in changes
            if c.get("proposal_id") and not c.get("ok") and desk_view.refused_by_check(c.get("new_value"))}


def accepted_words(accepted):
    """'Confirmed knowingly: more than +20% and under 3 days since the last change' for the warnings a person
    confirmed on purpose, else None."""
    said = [ACCEPTED[a] for a in ("big", "recent") if a in (accepted or [])]
    return f"Confirmed knowingly: {' and '.join(said)}" if said else None


def _status_by(s):
    if s.get("source") == "console":
        return s.get("by_name")
    if s.get("field") in SETUP_FIELDS and s.get("source") in ("poll", "webhook"):
        return ((s.get("detail") or {}) if isinstance(s.get("detail"), dict) else {}).get("actor") or "Ads Manager"
    return SOURCE.get(s.get("source"), "Meta")


def _with_cat(item):
    item["cat"] = marks.category(item)
    return item


def _elsewhere(level, entity_id, name, subject):
    if subject is None or not entity_id or entity_id == subject or level not in LEVELS:
        return None
    return {"level": level, "id": entity_id, "name": name}


def _status_items(status_events):
    """One line per status change. A switch made here records two events (what was asked, what Meta did)
    under one change id: the request is the line, Meta's answer its second line."""
    items, pairs = [], {}
    for s in status_events:
        console = s.get("source") == "console"
        item = _with_cat({"kind": "status", "at": s["at"], "title": s["headline"], "sub": None, "by": _status_by(s),
                          "source": "console" if console else "meta", "tone": _tone(s), "level": s.get("level"),
                          "entity_id": s.get("entity_id"), "entity_name": s.get("entity_name"), "field": s.get("field"),
                          "old": s.get("old_value"), "new": s.get("new_value")})
        cid = s.get("change_id")
        first = pairs.get(cid) if cid else None
        if first is None:
            if cid:
                pairs[cid] = item
            item["_field"] = s.get("field")
            items.append(item)
            continue
        lead, other = (item, first) if s.get("field") == "configured_status" and first["_field"] != "configured_status" else (first, item)
        first.update(title=lead["title"], sub=other["title"], at=max(first["at"], item["at"]),
                     tone=max(first["tone"], item["tone"], key=lambda t: TONE_RANK.get(t, 0)))
    for i in items:
        i.pop("_field", None)
    return items


def merge(status_events, changes, proposals, money, subject=None, names=None, versions=(), checks=None):
    """Newest first. With `subject` (the page's own id), a change or suggestion about its ad set or campaign
    says where it happened (`on`), so the page can link there; `names` gives those ids' names. Every item
    carries `cat` (money | switch | edit | meta) and what it is about (`level`, `entity_id`, `entity_name`).
    `versions` (ad_versions rows with `ad_name`) add "Version N started"; `checks` is kept for "Did it work?"."""
    names = names or {}
    linked = {s.get("change_id") for s in status_events if s.get("change_id")}
    checked = checked_refusals(changes)
    items = _status_items(status_events)
    for c in changes:
        if c["action"] == "status" and c["id"] in linked and c.get("ok"):
            continue  # the status event already says it, with who did it
        name = names.get(c.get("entity_id")) or (None if c["action"] in NAMELESS else c.get("entity_name"))
        items.append(_with_cat({"kind": "change", "at": c["created_at"], "title": change_title(c, money),
                                "sub": accepted_words(c.get("accepted")) if c.get("ok") else _refusal(c), "by": c.get("user_name"),
                                "source": "console", "tone": "" if c.get("ok") else "bad", "proposal_id": c.get("proposal_id"),
                                "on": _elsewhere(c.get("level"), c.get("entity_id"), name, subject),
                                "level": c.get("level"), "entity_id": c.get("entity_id"), "entity_name": name,
                                "field": c["action"], "old": c.get("old_value"), "new": c.get("new_value")}))
    for p in proposals:
        if not p.get("decided_at"):
            continue
        word = CHECKED if p["status"] == "failed" and (p.get("checked") or p["id"] in checked) else DECIDED.get(p["status"], p["status"])
        items.append({"kind": "proposal", "at": p["decided_at"], "title": f"Claude's suggestion {word}: {p['title']}", "sub": None,
                      "by": None, "source": "claude", "tone": "bad" if p["status"] == "failed" else "",
                      "proposal_id": p["id"], "task_id": p.get("task_id"),
                      "on": _elsewhere(p.get("entity_type"), p.get("entity_id"),
                                       names.get(p.get("entity_id")) or p.get("entity_name"), subject),
                      "cat": None, "level": p.get("entity_type"), "entity_id": p.get("entity_id"),
                      "entity_name": names.get(p.get("entity_id")) or p.get("entity_name")})
    for v in versions:
        label = f": {v['label']}" if v.get("label") else ""
        items.append(_with_cat({"kind": "version", "at": v["started_at"], "title": f"Version {v['number']} started{label}",
                                "sub": None, "by": None, "source": "console", "tone": "", "level": "ad",
                                "entity_id": v["ad_id"], "entity_name": v.get("ad_name"), "field": "version",
                                "old": None, "new": v["number"], "proposal_id": v.get("proposal_id")}))
    items.sort(key=lambda i: i["at"], reverse=True)
    return items
