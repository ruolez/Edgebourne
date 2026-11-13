"""FU-A: the Meta ad accounts the console's key can reach, merged from Meta's lists, marked with the console
account that already holds each one and why one can't be added. Pure: no database, no Meta."""

STATUS_WORDS = {1: "Active", 2: "Disabled", 3: "Payment problem", 7: "Under review by Meta", 8: "Payment due",
                9: "Grace period", 100: "Closing", 101: "Closed", 201: "Active", 202: "Closed"}
USABLE = {1, 3, 7, 8, 9, 201}  # Meta still runs or reports these; 2/100/101/202 can't be run from the console
SOURCES = ("assigned", "owned", "client")  # me/adaccounts, <business>/owned_ad_accounts, <business>/client_ad_accounts


def act_digits(value):
    """'act_123' / '123' / ' act_123 ' -> '123'; anything else -> None."""
    text = str(value if value is not None else "").strip()
    text = text[4:] if text.startswith("act_") else text
    return text if text.isdigit() and text.isascii() else None


def merge(sources):
    """{"assigned": rows, "owned": rows, "client": rows} as Meta lists them -> one entry per ad account, sorted by name."""
    out = {}
    for via in SOURCES:
        for r in sources.get(via) or []:
            digits = act_digits(r.get("account_id")) or act_digits(r.get("id"))
            if not digits:
                continue
            entry = out.get(digits)
            if entry is None:
                status = r.get("account_status")
                business = r.get("business") or {}
                entry = out[digits] = {"id": digits, "name": r.get("name") or "", "currency": str(r.get("currency") or "").upper(),
                                       "status": status, "status_words": STATUS_WORDS.get(status, "Unknown"),
                                       "timezone": r.get("timezone_name"), "business_name": business.get("name"),
                                       "business_id": business.get("id"), "via": []}
            if via not in entry["via"]:
                entry["via"].append(via)
    return sorted(out.values(), key=lambda i: (i["name"].casefold(), i["id"]))


def mark_used(items, holders, names):
    """holders = settings_store.meta_holders("meta_ad_account_id"); adds used_by {account_id, name, closed} or None."""
    held = {}
    for account_id, closed, value in holders:
        digits = act_digits(value)
        if digits and digits not in held:
            held[digits] = {"account_id": account_id, "name": names.get(account_id, f"Account {account_id}"), "closed": bool(closed)}
    return [{**i, "used_by": held.get(i["id"])} for i in items]


def blocked(item, currency_problem):
    """Why this ad account can't become a console account, in plain words, or None."""
    used = item.get("used_by")
    if used and used["closed"]:
        return f"{used['name']} (a closed account) still holds it: reopen that account instead."
    if used:
        return f"Already in the console as {used['name']}."
    problem = currency_problem(item.get("currency"))
    if problem:
        return problem
    status = item.get("status")
    if status is not None and status not in USABLE:
        return f"Meta says this ad account is {STATUS_WORDS.get(status, 'not usable')}."
    return None


def default_name(item):
    """The console account's suggested name: Meta's ad account name, or "Ad account <last 4>"."""
    name = " ".join(str(item.get("name") or "").split())[:120]
    return name or f"Ad account {str(item.get('id') or '')[-4:]}"


def overview_totals(rows):
    """All accounts: a total row only when every account shares one currency (amounts are never added across
    currencies); its cost per lead is total spend over total leads."""
    same = len({r.get("currency") for r in rows}) <= 1
    if not same or not rows:
        return {"same_currency": same, "totals": None}
    spend = sum(int(r.get("spend_cents") or 0) for r in rows)
    leads = sum(int(r.get("leads") or 0) for r in rows)
    return {"same_currency": True, "totals": {"spend_cents": spend, "leads": leads, "cpl_cents": round(spend / leads) if leads else None}}
