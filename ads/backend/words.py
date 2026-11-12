"""The console's words for money, days and how long ago, one way everywhere (server side; format.js
has the client twins). Pure: callers pass the account's currency and time zone."""
from datetime import datetime, timezone

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def money(cents, currency="USD", whole=False):
    """'$1,234.50', '€20', '1,234.50 CAD'; '—' for no amount."""
    if cents is None:
        return "—"
    code = (currency or "USD").upper()
    amount = f"{cents / 100:,.{0 if whole else 2}f}"
    symbol = SYMBOLS.get(code)
    return f"{symbol}{amount}" if symbol else f"{amount} {code}"


def day(d):
    """'Nov 9'."""
    return f"{d.strftime('%b')} {d.day}"


def weekday(d):
    """'Fri, Nov 14'."""
    return f"{d.strftime('%a')}, {day(d)}"


def clock(dt):
    """'2:00 PM'."""
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def local(dt, tz=None):
    return dt.astimezone(tz or timezone.utc) if dt.tzinfo else dt


def days_since(first, now):
    """Whole days from `first` to `now`, by the calendar of `now`'s time zone (pass now in the account's zone):
    one count for the Inbox's "Open since" and the Diagnose request."""
    first = first.astimezone(now.tzinfo) if first.tzinfo and now.tzinfo else first
    return (now.date() - first.date()).days


def day_time(dt, tz=None):
    """'Thu, Nov 13, 2:00 PM' in the account's time zone."""
    dt = local(dt, tz)
    return f"{weekday(dt)}, {clock(dt)}"


def ago(dt, now=None):
    """'today' (under an hour), '5 hours ago', '1 day ago', '2 days ago'."""
    hours = int(((now or datetime.now(timezone.utc)) - dt).total_seconds() // 3600)
    if hours < 1:
        return "today"
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"
