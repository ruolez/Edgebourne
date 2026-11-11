"""Bulk changes: the same money rules as one-at-a-time, over a selection. A preview reads live values
and lists every line (current → new, or why it's skipped) with totals; the apply step only accepts the
signed plan from that preview (5 minutes), and re-reads each item before changing it. Pure."""
import base64
import hashlib
import hmac
import json

import money_rules

TTL = 300
MAX_ITEMS = 50


def spend_totals(contexts):
    """What a set of things turned on together can spend: each budget counted once, by the campaign or
    ad set that holds it (names aren't unique), daily and lifetime apart."""
    seen, budgets, daily, lifetime = set(), [], 0, 0
    for ctx in contexts:
        holder = ctx.get("holder")
        if not holder or holder in seen:
            continue
        seen.add(holder)
        budgets.append(ctx.get("where"))
        daily += ctx.get("daily_cents") or 0
        lifetime += ctx.get("lifetime_cents") or 0
    return {"daily_cents": daily, "lifetime_cents": lifetime, "budgets": budgets}


def status_lines(rows, value, contexts):
    lines, spending = [], []
    for r in rows:
        skip = None
        ctx = contexts.get(r["id"]) or {}
        if r["status"] in ("ARCHIVED", "DELETED"):
            skip = "Archived: it can't be turned on again" if value == "ACTIVE" else "Archived already"
        elif r["status"] == value:
            skip = "Already on" if value == "ACTIVE" else "Already off"
        elif value == "ACTIVE" and not ctx.get("idle") and not ctx.get("daily_cents") and not ctx.get("lifetime_cents"):
            skip = "Meta reports no budget for it, so it isn't turned on here"
        line = {"id": r["id"], "name": r["name"], "from": r["status"], "to": value, "skip": skip,
                "daily_cents": ctx.get("daily_cents"), "lifetime_cents": ctx.get("lifetime_cents"), "where": ctx.get("where")}
        lines.append(line)
        if not skip and value == "ACTIVE":
            spending.append(ctx)
    return lines, {"count": sum(1 for l in lines if not l["skip"]), **spend_totals(spending)}


def budget_lines(rows, mode, value, live, cap):
    lines = []
    for r in rows:
        cur = live.get(r["id"])
        if not cur:
            lines.append({"id": r["id"], "name": r["name"], "from": None, "to": None, "big": False, "pct": None,
                          "skip": "No daily budget of its own (it's set one level up)"})
            continue
        new = int(value) if mode == "set" else int(round(cur * (100 + float(value)) / 100))
        change = money_rules.budget_change(cur, new, cap)
        problem = money_rules.change_problem(change, accept_big=True)
        lines.append({"id": r["id"], "name": r["name"], "from": cur, "to": new, "big": change["big"], "pct": change["pct"],
                      "skip": problem})
    ok = [l for l in lines if not l["skip"]]
    return lines, {"count": len(ok), "from_cents": sum(l["from"] for l in ok), "to_cents": sum(l["to"] for l in ok),
                   "big": any(l["big"] for l in ok)}


def archive_lines(rows):
    lines = []
    for r in rows:
        skip = "Already archived" if r["status"] == "ARCHIVED" else "Turn it off first" if r["status"] == "ACTIVE" else None
        lines.append({"id": r["id"], "name": r["name"], "from": r["status"], "to": "ARCHIVED", "skip": skip})
    return lines, {"count": sum(1 for l in lines if not l["skip"])}


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sign(plan, secret, now):
    body = _b64(json.dumps({"plan": plan, "exp": int(now) + TTL}, sort_keys=True).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token, secret, now):
    try:
        body, sig = str(token).rsplit(".", 1)
    except ValueError:
        return None
    want = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    return data["plan"] if now <= data.get("exp", 0) else None
