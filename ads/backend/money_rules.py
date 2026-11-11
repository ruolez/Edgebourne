"""The console's rules for money, in one place (audit A1, A3, A20). Pure: no database, no Meta.

Amounts are cents (hundredths of the account currency). The hard rules: a budget change shows
current → new from a fresh read, +20% at most in one step unless confirmed knowingly, and never
above the account's ceiling (Settings → Targets → highest daily budget)."""
import re

BIG_STEP = 0.20
MAX_DAILY_DEFAULT = 10000  # $100/day per campaign or ad set until an admin changes it

_AMOUNT = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(%)?")
_NUM = r"[0-9][0-9,]*(?:\.[0-9]{1,2})?"
# Money is "$24" or "24/day", never "2x", "7-day", "20%" or "3 ad sets" (audit A3-23). A "." or ","
# that ends the sentence is fine; one followed by a digit is part of another number.
_NOT_MULT = r"(?![0-9]|[.,][0-9]|\s*(?:%|x\b|×|-\s*day))"
_MONEY = rf"(?:\$\s*({_NUM}){_NOT_MULT}|({_NUM})\s*/\s*day\b)"
_MONEY_RE = re.compile(_MONEY, re.I)
_TARGET = re.compile(rf"(?:\bto\b|→|->|=)\s*{_MONEY}", re.I)
# What may follow a bare number that is still an amount: the end, punctuation or a daily unit.
_BARE_OK = re.compile(r"\s*(?:$|[.,;:)!]|/\s*day\b|per\s+day\b|a\s+day\b|daily\b|dollars?\b|usd\b)", re.I)


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
    target = [a or b for a, b in _TARGET.findall(text)]
    if len(target) == 1:
        return _cents(target[0])
    if target:
        return None
    amounts = [m for m in _AMOUNT.finditer(text) if not m.group(2)]
    if len(amounts) != 1 or re.search(r"\d\s*x\b|×", text, re.I):
        return None
    m = amounts[0]
    money = _MONEY_RE.match(text, m.start()) if text[m.start()] == "$" else None
    if not money and not _BARE_OK.match(text, m.end(1)):
        return None  # "7-day", "3 ad sets": the one number counts something else
    return _cents(m.group(1))


def proposal_cents(text, structured=None):
    """The new daily budget of a Claude proposal: (cents, None), or (None, why it can't be applied).
    A structured amount (payload.proposed_cents) is used only when the words name that same amount."""
    words = (text or "").strip()
    parsed = parse_budget_text(text)
    if structured is None:
        if parsed:
            return parsed, None
        return None, (f"Claude's new budget isn't one clear amount (“{words}”), so it can't be applied as is. "
                      "Decline it, or change the budget yourself on the Ads page.")
    if not isinstance(structured, int) or isinstance(structured, bool) or structured < 100:
        return None, "Claude's amount in cents isn't a whole amount of at least 1.00, so it can't be applied. Decline it."
    named = {_cents(a or b) for a, b in _MONEY_RE.findall(words)}
    agrees = parsed == structured if parsed is not None else named == {structured}
    if not agrees:
        return None, (f"Claude's amount ({structured / 100:,.2f} a day) isn't what its words say (“{words}”), "
                      "so it can't be applied. Decline it and ask again.")
    return structured, None


def turn_on_problem(ctx, confirm_daily, confirm_lifetime):
    """Why something that spends can't be turned on yet, or None. ctx is spend_context (read fresh from
    Meta): every budget it can spend from, daily or lifetime, must have been shown and echoed back."""
    if ctx.get("idle"):
        return None  # a campaign with nothing on inside: turning it on spends nothing until an ad set is on
    if not ctx.get("daily_cents") and not ctx.get("lifetime_cents"):
        return "Meta reports no budget for this, so it wasn't turned on here. Check it in Ads Manager."
    for key, given in (("daily_cents", confirm_daily), ("lifetime_cents", confirm_lifetime)):
        try:
            given = int(given)
        except (TypeError, ValueError):
            given = None
        if ctx.get(key) and given != ctx[key]:
            return "Confirm the budget first"
    return None


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
