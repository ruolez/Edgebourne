"""The console's rules for money, in one place (audit A1, A3, A20). Pure: no database, no Meta.

Amounts are cents (hundredths of the account currency). The hard rules: a budget change shows
current → new from a fresh read, +20% at most in one step unless confirmed knowingly, and never
above the account's ceiling (Settings → Targets → highest daily budget)."""
import re

BIG_STEP = 0.20
MAX_DAILY_DEFAULT = 10000  # $100/day per campaign or ad set until an admin changes it

_AMOUNT = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(%)?")
_TARGET = re.compile(r"(?:\bto\b|→|->|=)\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)(?!\s*%)", re.I)


def _cents(raw):
    return int(round(float(raw.replace(",", "")) * 100))


def parse_budget_text(text):
    """The new daily budget a proposal names, in cents, or None when it isn't one clear amount.
    '$24/day' → 2400; 'from $20 to $24' → 2400; '+20% to $24/day' → 2400; 'raise 2x' → None."""
    if text is None:
        return None
    text = str(text)
    if re.search(r"\bor\b|/\s*\$|\?", text, re.I):
        return None  # "$40 or $50", "$40/$50", "$40?": a choice, not an amount
    target = _TARGET.findall(text)
    if len(target) == 1:
        return _cents(target[0])
    if target:
        return None
    amounts = [m.group(1) for m in _AMOUNT.finditer(text) if not m.group(2)]
    if len(amounts) != 1 or re.search(r"\d\s*x\b|×", text, re.I):
        return None
    return _cents(amounts[0])


def ceiling(saved):
    """The account's highest daily budget the console may set, in cents."""
    try:
        value = int(saved)
        return value if value >= 100 else MAX_DAILY_DEFAULT
    except (TypeError, ValueError):
        return MAX_DAILY_DEFAULT


def budget_change(old_cents, new_cents, cap_cents):
    """What a change from old to new means: {from, to, pct, big, over_cap, cap}."""
    pct = round((new_cents - old_cents) * 100 / old_cents) if old_cents else None
    return {"from": old_cents, "to": new_cents, "pct": pct,
            "big": bool(old_cents) and (new_cents - old_cents) / old_cents > BIG_STEP,
            "over_cap": new_cents > cap_cents, "cap": cap_cents}


def change_problem(change, accept_big):
    """Why the change can't go ahead as asked, or None."""
    if change["to"] is None or change["to"] < 100:
        return "The new daily budget must be at least 1.00"
    if change["over_cap"]:
        return (f"That's above this account's ceiling of {change['cap'] / 100:,.2f} a day "
                "(Settings → Targets → highest daily budget). Raise the ceiling first if you mean it.")
    if change["big"] and not accept_big:
        return f"That's +{change['pct']}%, more than +20% in one step: confirm it knowingly."
    return None


def recommendation_amount(extra):
    """Meta's `additional_budget` in cents when it's an unambiguous whole number of cents, else None.
    A decimal string ('50.00') or a tiny number (likely dollars, not cents) is refused, not guessed."""
    if isinstance(extra, bool) or extra is None:
        return None
    if isinstance(extra, int):
        value = extra
    elif isinstance(extra, str) and extra.strip().isdigit():
        value = int(extra.strip())
    else:
        return None
    return value if value >= 100 else None
