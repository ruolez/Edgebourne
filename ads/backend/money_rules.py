"""The console's rules for money, in one place (audit A1, A3, A20). Pure: no database, no Meta.

Amounts are cents (hundredths of the account currency). The hard rules: a budget change shows
current → new from a fresh read, +20% at most in one step unless confirmed knowingly, and never
above the account's ceiling (Settings → Targets → highest daily budget)."""
import re
from datetime import timedelta

BIG_STEP = 0.20
RECENT = timedelta(hours=72)  # rule 6: one budget change at least 3 days apart; no setting, never loosened
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


def last_budget_change(rows):
    """The latest real budget change of one budget, or None. rows: [{at, field: daily_budget|lifetime_budget,
    old, new (cents or None), by, where: console|outside, proposal_id}] from console writes and Meta's records."""
    real = [r for r in rows if r.get("old") != r.get("new")]
    return max(real, key=lambda r: r["at"]) if real else None


def recency(last, now, old_cents, new_cents):
    """How a change from old to new sits against the last one: {recent, raise, rollback, hours, ok_after}, or
    None without a last change. Rollback = back to exactly the budget before the last change."""
    if last is None:
        return None
    return {"recent": now - last["at"] < RECENT, "raise": new_cents > (old_cents or 0),
            "rollback": last.get("old") is not None and new_cents == last["old"],
            "hours": int((now - last["at"]).total_seconds() // 3600), "ok_after": last["at"] + RECENT}


def budget_change(old_cents, new_cents, cap_cents, last=None, now=None):
    """What a change from old to new means: {from, to, pct, big, over_cap, cap, recent, rollback, last}.
    recent: a raise less than 3 days after the last change that isn't a rollback (a cut never is)."""
    pct = round((new_cents - old_cents) * 100 / old_cents) if old_cents else None
    rec = recency(last, now, old_cents, new_cents) if last is not None and now is not None else None
    out = {"from": old_cents, "to": new_cents, "pct": pct,
           "big": bool(old_cents) and (new_cents - old_cents) / old_cents > BIG_STEP,
           "over_cap": new_cents > cap_cents, "cap": cap_cents,
           "recent": bool(rec and rec["recent"] and rec["raise"] and not rec["rollback"]),
           "rollback": bool(rec and rec["rollback"]), "last": last if rec else None}
    if rec:
        out["hours"] = rec["hours"]
        out["ok_after"] = rec["ok_after"]
    return out


def since_words(hours):
    if hours < 1:
        return "less than an hour ago"
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    return f"{hours // 24} day{'s' if hours // 24 != 1 else ''} ago"


def change_problem(change, accept_big, accept_recent=False):
    """Why the change can't go ahead as asked, or None. The ceiling first, then +20%, then the 3-day rule."""
    if change["to"] is None or change["to"] < 100:
        return "The new daily budget must be at least 1.00"
    if change["over_cap"]:
        return (f"That's above this account's ceiling of {change['cap'] / 100:,.2f} a day "
                "(Settings → Targets → highest daily budget). Raise the ceiling first if you mean it.")
    if change["big"] and not accept_big:
        return f"That's +{change['pct']}%, more than +20% in one step: confirm it knowingly."
    if change.get("recent") and not accept_recent:
        last = change["last"]
        was = f"{last['old'] / 100:,.2f} → {last['new'] / 100:,.2f} a day" if last.get("old") and last.get("new") else "a new amount"
        return (f"The budget last changed {since_words(change['hours'])} ({was}). Raising it again this soon "
                "makes results hard to read: confirm it knowingly.")
    return None


def accepted(change, accept_big, accept_recent):
    """The warnings a person confirmed knowingly for this change, as stored on meta_changes.accepted."""
    out = (["big"] if change.get("big") and accept_big else []) + (["recent"] if change.get("recent") and accept_recent else [])
    return out or None


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


# ---------------------------------------------------------------- the ad account spending limit (FU-B)
# Meta's Ad Account reference (checked 2026-11-12 and 2026-11-13): the READ field spend_cap is "in basic unit of the
# currency, e.g. cents for USD"; the UPDATE parameter spend_cap is a float "in standard denomination, e.g. 23.50 for
# USD $23.50". So the console reads cents and writes dollars, through these two functions only (a ratchet test holds it).

LIMIT_MIN_HEADROOM = 1  # cents: a new limit must be above what's already spent, by at least this
LIMIT_DAILY = "daily"  # limit_words: the words name an amount per day, a budget, not the account's limit
LIMIT_UNCLEAR = "unclear"  # limit_words: not one clear amount
LIMIT_BIG_FACTOR = 2  # a raise past this × the current limit needs a second, separate yes (like a removal)


def _whole_cents(value):
    return isinstance(value, int) and not isinstance(value, bool)


def spend_cap_cents(raw):
    """Meta's READ value of an ad account's spend_cap (minor units, a numeric string) in cents; None = no limit
    ("0", "" or missing). Anything else (a decimal like "150.00", junk, a negative) raises ValueError: never guessed."""
    if raw is None or raw == "" or raw == 0:
        return None
    if _whole_cents(raw):
        if raw < 0:
            raise ValueError(f"spend_cap {raw!r} is negative")
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value or None
    raise ValueError(f"spend_cap {raw!r} isn't a whole number of minor units")


def spend_cap_param(cents, currency):
    """THE ONLY place that turns cents into Meta's spend_cap WRITE unit (standard denomination): 20000 → "200.00",
    None → "0" (no limit). Refuses a zero-decimal currency (100× off), and 0, negatives or non-integers: 0 would
    remove the limit on Meta, so removing is only ever spelled None."""
    import account_info
    if (currency or "").upper() in account_info.ZERO_DECIMAL:
        raise ValueError(f"{currency} has no cents: the console never writes its spending limit")
    if cents is None:
        return "0"
    if not _whole_cents(cents) or cents <= 0:
        raise ValueError(f"spending limit {cents!r} isn't a whole number of cents above 0")
    return f"{cents // 100}.{cents % 100:02d}"


def readback_ok(intended_cents, raw_read):
    """Meta's stored spend_cap, read back after a write, is exactly the cents we meant (None = no limit)."""
    try:
        return spend_cap_cents(raw_read) == intended_cents if raw_read is not None else False
    except ValueError:
        return False


def spend_limit_change(old_cents, new_cents, spent_cents, rate_cents, currency="USD"):
    """What changing the account's limit from old to new means at the current pace. left_* = limit − spent (None
    without a limit), days_* = whole days that lasts at `rate_cents` a day (None without a pace or a limit)."""
    def left(limit):
        return None if limit is None else limit - spent_cents

    def days(limit):
        return None if limit is None or not rate_cents or rate_cents <= 0 else max(limit - spent_cents, 0) // rate_cents
    big = old_cents is not None and new_cents is not None and new_cents > LIMIT_BIG_FACTOR * old_cents
    return {"from": old_cents, "to": new_cents, "spent": spent_cents, "remove": new_cents is None,
            "left_now": left(old_cents), "left_after": left(new_cents), "days_now": days(old_cents),
            "days_after": days(new_cents), "rate": rate_cents, "currency": currency, "big": big}


def spend_limit_problem(change, confirm_remove, accept_big=False):
    """Why the limit can't be changed as asked, in plain words, or None. A removal and a raise past
    LIMIT_BIG_FACTOR × the current limit (almost the same as none) each need their own second yes."""
    import words
    to, spent = change["to"], change["spent"]
    if to is not None and to < 100:
        return "The new limit must be at least 1.00."
    if to is not None and to < spent + LIMIT_MIN_HEADROOM:
        said = words.money(spent, change.get("currency"))
        return f"That's at or below what's already spent ({said}): Meta would stop every ad at once. Pick more than {said}."
    if change["remove"] and change["from"] is None:
        return "There's no limit already."
    if change["remove"] and not confirm_remove:
        return "Removing the limit needs its own confirmation."
    if to == change["from"]:
        return "That's already the limit."
    if change.get("big") and not accept_big:
        return "Raising the limit to more than double needs its own confirmation."
    return None


def limit_account_problem(entity_id, current_act):
    """A spending-limit suggestion names an ad account; when it's accepted that must still be this account's one
    (an admin may have pointed the account at another ad account since). None, or why it can't be applied."""
    if entity_id and current_act and entity_id == current_act and current_act != "act_None":
        return None
    return (f"This suggestion was for another ad account ({entity_id or 'none named'}); this account's is "
            f"{current_act} now. Decline it and ask again.")


def limit_read_words(raw, currency=None):
    """What Meta holds, read as a raw spend_cap, in words: "$200.00", "no limit", or, when it can't be read,
    "an amount the console can't read ('200.00')" (never called "no limit")."""
    import words
    try:
        cents = spend_cap_cents(raw)
    except ValueError:
        return f"an amount the console can't read ({raw!r})"
    return "no limit" if cents is None else words.money(cents, currency)


_PER_DAY = re.compile(r"/\s*day\b|\ba\s+day\b|\bper\s+day\b|\bdaily\b|\beach\s+day\b|\bevery\s+day\b", re.I)
_REMOVE = re.compile(r"\bno\s+(?:spending\s+)?limit\b|\bremove\b.*\blimit\b|\bunlimited\b", re.I)


def limit_words(text):
    """The total limit a spend_limit suggestion names: "$200" / "to $200" / "200 dollars" → 20000; "no limit" /
    "remove the limit" → None; anything per day → LIMIT_DAILY (that's a budget); otherwise LIMIT_UNCLEAR
    (budget words' rules: "or", "?", two amounts, a percentage → not an amount)."""
    text = "" if text is None else str(text)
    if _PER_DAY.search(text):
        return LIMIT_DAILY
    if _REMOVE.search(text):
        return None if not re.search(r"\d", text) else LIMIT_UNCLEAR
    cents = parse_budget_text(text)
    return cents if cents is not None else LIMIT_UNCLEAR


def limit_action(text, payload):
    """Accepting a spend_limit suggestion: ("spend_limit", cents | None for no limit), or ("unclear", why). The
    structured amount is used only when the words name that same amount (as for budgets)."""
    words_said = (text or "").strip()
    named = limit_words(text)
    payload = payload if isinstance(payload, dict) else {}
    if named == LIMIT_DAILY:
        return "unclear", "This reads as a daily budget, not the account spending limit. Decline it and ask again."
    cents, remove = payload.get("proposed_cents"), payload.get("remove") is True
    if remove and cents is None:
        if named is None:
            return "spend_limit", None
        return "unclear", f"Claude's words (“{words_said}”) don't say to remove the limit, so it can't be applied. Decline it and ask again."
    if not _whole_cents(cents) or cents < 100 or "remove" in payload:
        return "unclear", "Claude's new limit isn't a whole amount of at least 1.00, so it can't be applied. Decline it and ask again."
    if named != cents:
        return "unclear", (f"Claude's amount ({cents / 100:,.2f}) isn't what its words say (“{words_said}”), "
                           "so it can't be applied. Decline it and ask again.")
    return "spend_limit", cents
