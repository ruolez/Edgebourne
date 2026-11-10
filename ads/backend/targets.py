"""An account's targets, in one place (audit A19): Settings → Targets.

- cost per qualified lead (`kpi_target_cents`): the business goal; reports measure against it.
- cost per lead (`lead_target_cents`): any form lead. Alerts, By idea and Tests judge leads by it.
  Not set: the cost-per-lead alert uses the qualified-lead target, a ceiling every lead must stay
  under (a plain lead costing more than a qualified one should misses the goal whatever the
  quality); By idea and Tests use their own average, so "enough data" isn't set by a stricter goal.
- highest daily budget (`max_daily_budget_cents`): the most the console sets on one campaign or ad set.
- monthly spend target (`monthly_target_cents`): set on Results, read by pacing."""
import json

import money_rules
import settings_store


def _int(value):
    try:
        v = int(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def qualified():
    return _int(settings_store.get("kpi_target_cents"))


def lead_own():
    """The cost-per-lead target as set (an older one saved with the alert rule counts too)."""
    own = _int(settings_store.get("lead_target_cents"))
    if own:
        return own
    try:
        rules = json.loads(settings_store.get("alert_rules") or "{}")
    except ValueError:
        rules = {}
    return _int((rules.get("cpl_high") or {}).get("target_cents"))


def lead():
    """What leads are judged against: the cost-per-lead target, else the qualified-lead one."""
    return lead_own() or qualified()


def ceiling():
    return money_rules.ceiling(settings_store.get("max_daily_budget_cents"))


def view():
    return {"qualified_cents": qualified(), "lead_cents": lead_own(), "lead_used_cents": lead(),
            "max_daily_cents": ceiling(), "max_daily_default": money_rules.MAX_DAILY_DEFAULT,
            "monthly_cents": _int(settings_store.get("monthly_target_cents"))}
