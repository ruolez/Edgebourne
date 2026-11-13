"""Got it: an admin snoozes an alert that keeps coming back (a tired ad, the spending limit nearly used).
A snoozed alert is still stored and shown in the Inbox, quietly, and sends no messages. It comes back by
itself when the promised day comes, when its figure gets clearly worse, or, once it clears, the next time
it happens. One snooze per problem (rule + thing) per account, shared by the account's admins.

Pure: `worse`, `decide`, `choices`, `offer`, `until_for`, `worse_hint`, `woke_line`, `snooze_words`, `apply`
and `sweep` take everything they need as arguments."""
from datetime import datetime, time, timedelta

import words

DAYS_DEFAULT = 3
WAKE_HOUR = 8  # a "days" snooze ends at 8 AM in the ad account's time zone
LEVELS = {"info": 0, "ok": 0, "warn": 1, "bad": 2}

# rule → (how its figure gets clearly worse, step). The figure is the alert's `measure`:
#   plus: measure ≥ baseline + step · times: measure > baseline and ≥ baseline × step · up: measure > baseline
#   bands: a higher band than the baseline's · down_to: measure ≤ step < baseline · level: the level only
#   share_down / share_up: a percent that moved `step` points the wrong way (stopping at 0 / 100), and moved at all
WORSE = {
    "ad_rejected": ("up", None),          # 1 = has issues, 2 = rejected
    "no_delivery": ("plus", 48),          # hours live, nobody has seen it
    "fatigue": ("plus", 1.0),             # views a person a week
    "week_overspend": ("times", 1.25),    # 7 days' spend, cents
    "spend_cap": ("bands", (95, 100)),    # % of the limit used
    "cap_soon": ("down_to", 1),           # days left
    "pace_over": ("plus", 15),            # % over the monthly target
    "cpl_high": ("times", 1.25),          # cost per lead, cents (no leads: the spend)
    "no_leads": ("times", 2),             # days in a row without a lead
    "stale_data": ("plus", 24),           # hours since Meta last answered
    "events_quiet": ("level", None),
    "tracking": ("level", None),          # Meta's leads in two days; "Remind me tomorrow" only
    "qualified_low": ("share_down", 10),  # % of the worked leads that qualified
    "junk_high": ("share_up", 15),        # % of the leads that look like junk
}
DAY_AT_MOST = {"tracking"}  # leads may be getting lost: one day at most, like a red money alert
EPS = 1e-9


def _band(value, edges):
    return sum(1 for e in edges if value >= e - EPS)


def worse(rule, baseline, measure, base_level, level):
    """Clearly worse than when it was snoozed: the level went up (warn → bad), or the rule's own step was
    crossed. An unknown baseline or figure judges on the level only."""
    if LEVELS.get(level, 0) > LEVELS.get(base_level, 0):
        return True
    how, step = WORSE.get(rule, ("level", None))
    if how == "level" or baseline is None or measure is None:
        return False
    b, m = float(baseline), float(measure)
    if how == "plus":
        return m - b >= step - EPS
    if how == "times":
        return m > b + EPS and m >= b * step - EPS
    if how == "up":
        return m > b + EPS
    if how == "bands":
        return _band(m, step) > _band(b, step)
    if how == "down_to":
        return m <= step + EPS < b
    if how == "share_down":
        return m < b - EPS and m <= max(b - step, 0) + EPS
    if how == "share_up":
        return m > b + EPS and m >= min(b + step, 100) - EPS
    return False


def decide(snooze, alert, now):
    """'wake_worse' | 'wake_expired' | 'quiet'. Worse wins over expired; "until it gets worse" never expires."""
    if worse(snooze["rule"], snooze.get("baseline"), alert.get("measure"), snooze["baseline_level"], alert["level"]):
        return "wake_worse"
    if snooze["mode"] == "days" and snooze.get("until") is not None and now >= snooze["until"]:
        return "wake_expired"
    return "quiet"


def _money_rule(rule):
    import inbox  # inbox builds its items with this module: imported when asked, not at load
    return inbox.category(rule) == "money"


def choices(alert):
    """What Got it offers for this alert: nothing for events, cleared or info alerts and rules without a
    figure to watch; one day at most for tracking and a money alert already red (00-PLAN §3)."""
    if (alert.get("kind") or "condition") != "condition" or alert.get("resolved_at") is not None:
        return []
    if LEVELS.get(alert.get("level"), 0) == 0 or alert.get("rule") not in WORSE:
        return []
    if alert["rule"] in DAY_AT_MOST or (alert["level"] == "bad" and _money_rule(alert["rule"])):
        return [{"mode": "days", "days": 1, "label": "Remind me tomorrow"}]
    return [{"mode": "days", "days": DAYS_DEFAULT, "label": f"In {DAYS_DEFAULT} days"},
            {"mode": "worse", "days": None, "label": "Only if it gets worse"}]


def until_for(now_local, days):
    """WAKE_HOUR local time on the date `days` after now_local's date (aware, the account's time zone)."""
    return datetime.combine(now_local.date() + timedelta(days=days), time(WAKE_HOUR), tzinfo=now_local.tzinfo)


def _money(cents):
    return words.money(round(cents), whole=not round(cents) % 100)


def _pct(value):
    return f"{round(value, 1):g}%"


def _qualified_hint(m):
    if m <= EPS:
        return "It ends by itself when leads qualify again."
    step = WORSE["qualified_low"][1]
    return "You'll hear again if none of them qualify." if m <= step + EPS else f"You'll hear again if it drops to {_pct(m - step)}."


def _junk_hint(m):
    step = WORSE["junk_high"][1]
    return "You'll hear again if every lead looks like junk." if m + step >= 100 - EPS else f"You'll hear again if junk reaches {_pct(m + step)}."


ENDS = {
    "events_quiet": "It ends by itself when lead stages reach Meta again.",
}


def worse_hint(rule, measure, money=_money):
    """The sentence under "Only if it gets worse", in plain words."""
    if rule in ENDS:
        return ENDS[rule]
    if rule == "ad_rejected" and measure is not None and float(measure) >= 2:
        return "It ends by itself when the ad is approved or switched off."
    if measure is None:
        return "You'll hear again if it turns red."
    m = float(measure)
    return {
        "ad_rejected": lambda: "You'll hear again if Meta rejects it outright.",
        "no_delivery": lambda: "You'll hear again if it's still unseen 2 days from now.",
        "fatigue": lambda: f"You'll hear again if people see it {m + 1:.1f} times a week.",
        "week_overspend": lambda: f"You'll hear again if 7 days' spend passes {money(m * 1.25)}.",
        "spend_cap": lambda: "You'll hear again at 95% of the limit." if m < 95 else "You'll hear again when the limit is reached.",
        "cap_soon": lambda: "You'll hear again a day before it runs out.",
        "pace_over": lambda: f"You'll hear again if the month heads {m + 15:g}% over.",
        "cpl_high": lambda: f"You'll hear again if a lead costs {money(m * 1.25)} or more.",
        "no_leads": lambda: f"You'll hear again after {int(m * 2)} days without a lead.",
        "stale_data": lambda: "You'll hear again if Meta is still silent a day from now.",
        "qualified_low": lambda: _qualified_hint(m),
        "junk_high": lambda: _junk_hint(m),
    }.get(rule, lambda: "You'll hear again if it turns red.")()


def offer(alert, now_local, money=_money):
    """choices() with the line under each button: until when, and what brings it back."""
    out = []
    for c in choices(alert):
        if c["mode"] == "days":
            until = until_for(now_local, c["days"])
            if c["days"] == 1:
                hint = ("Leads may be getting lost, so this can only wait a day." if alert["rule"] in DAY_AT_MOST
                        else "This costs money every day, so it can only wait a day.")
            else:
                hint = f"Stays in the Inbox without messages until {words.weekday(until)}. Comes back sooner if it gets worse."
            out.append({**c, "until": until.isoformat(), "hint": hint})
        else:
            said = worse_hint(alert["rule"], alert.get("measure"), money)
            tail = "" if "ends by itself" in said else " It ends by itself when this clears up."
            out.append({**c, "until": None, "hint": f"No messages while it stays like this. {said}{tail}"})
    return out


def measure_words(rule, m, money=_money):
    """The figure as people read it ("82%", "$80"), or None when there's no good way to say it."""
    if m is None:
        return None
    m = float(m)
    return {
        "spend_cap": lambda: f"{m:.0f}%",
        "pace_over": lambda: f"{m:.0f}% over",
        "cpl_high": lambda: money(m),
        "week_overspend": lambda: money(m),
        "no_leads": lambda: f"{m:.0f} days without a lead",
        "fatigue": lambda: f"{m:.1f} views a person",
        "no_delivery": lambda: f"{m:.0f} hours unseen",
        "cap_soon": lambda: f"{m:g} days left",
        "stale_data": lambda: f"{m:.0f} hours without Meta",
        "ad_rejected": lambda: "rejected" if m >= 2 else "has issues",
        "qualified_low": lambda: f"{int(m + 0.5)}% qualified",  # rounded half up, as the alert's title
        "junk_high": lambda: f"{int(m + 0.5)}% junk",
    }.get(rule, lambda: None)()


def woke_line(snooze, verdict, tz, money=_money):
    """First line of a wake-up message."""
    on = words.day(words.local(snooze["created_at"], tz))
    if verdict == "wake_expired":
        return f"You asked to be reminded on {on}."
    at = measure_words(snooze["rule"], snooze.get("baseline"), money)
    return f"You snoozed this at {at} on {on}." if at else f"You snoozed this on {on}."


def snooze_words(snooze, tz):
    """The chip: "Snoozed until Fri, Nov 14" / "Snoozed until it gets worse"."""
    if snooze["mode"] == "days" and snooze.get("until") is not None:
        return f"Snoozed until {words.weekday(words.local(snooze['until'], tz))}"
    return "Snoozed until it gets worse"


PREFIX = {"wake_worse": "Worse: ", "wake_expired": "Back as promised: "}


def apply(alert, snooze, verdict, tz, money=_money):
    """The alert as raise_found stores it: quiet (shown, never sent), or a wake-up that says why it is back.
    A wake-up gets a key of its own (`wake_key`) for when a quiet row already took the day's key."""
    if verdict == "quiet":
        return {**alert, "quiet": True}
    return {**alert, "quiet": False, "title": PREFIX[verdict] + alert["title"],
            "lines": [woke_line(snooze, verdict, tz, money)] + list(alert.get("lines") or []),
            "wake_key": f"{alert['key']}:w{snooze['id']}"}


def sweep(live, found_pairs, now, stale, unjudged=()):
    """[(snooze id, end reason)] for live snoozes whose condition is gone: 'expired' when a days snooze's
    date has passed anyway, else 'cleared'. Nothing ends while Meta's data is stale (an outage must not reset
    every snooze and then re-alert them all), nor for a rule that couldn't be judged this time."""
    if stale:
        return []
    out = []
    for s in live:
        if (s["rule"], s["entity_id"]) in found_pairs or s["rule"] in unjudged:
            continue
        expired = s["mode"] == "days" and s.get("until") is not None and s["until"] <= now
        out.append((s["id"], "expired" if expired else "cleared"))
    return out
