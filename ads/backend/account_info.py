"""The ad account's own clock and money. Meta reports days in the ad account's time zone and
amounts in its currency; both are read from Meta per account (insights.sync_account stores
them in `account_snapshot`) so a client in another time zone or currency gets its own days."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
import settings_store

# Meta stores these currencies without minor units (offset 1). Every amount in this console is
# kept as hundredths, so an account in one of them would be 100× off: refuse to connect it.
ZERO_DECIMAL = {"CLP", "COP", "CRC", "HUF", "ISK", "IDR", "JPY", "KRW", "PYG", "TWD", "VND"}


def snapshot():
    try:
        return json.loads(settings_store.get("account_snapshot") or "{}")
    except ValueError:
        return {}


def tz_name(snap=None):
    snap = snapshot() if snap is None else snap
    name = snap.get("timezone") or snap.get("timezone_name") or config.ACCOUNT_TZ
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return config.ACCOUNT_TZ
    return name


def tz():
    return ZoneInfo(tz_name())


def currency(snap=None):
    return ((snapshot() if snap is None else snap).get("currency") or "USD").upper()


SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def money(cents, code=None, whole=False):
    """An amount written in the account's currency (the one given, else this account's): "$1,234.50",
    "€20", "1,234.50 CAD". `whole` leaves the cents out. Every server-made sentence uses it."""
    import words
    if cents is None:
        return "—"
    return words.money(cents, code or currency(), whole)


def currency_problem(code):
    """Why the console can't run an account in this currency, or None."""
    code = (code or "").upper()
    if code in ZERO_DECIMAL:
        return (f"This ad account is in {code}, which Meta keeps without cents. The console only handles "
                "currencies with cents (USD, EUR, GBP, CAD, …) and won't run it, so amounts can't come out 100× off.")
    return None


def local_now(now=None, zone=None):
    return (now or datetime.now(timezone.utc)).astimezone(zone or tz())


def today(now=None, zone=None):
    """The ad account's today (Meta's day boundary), not the server's."""
    return local_now(now, zone).date()


def yesterday(now=None, zone=None):
    """The last complete day in the ad account's time zone."""
    return today(now, zone) - timedelta(days=1)
