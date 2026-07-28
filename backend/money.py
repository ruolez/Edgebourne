"""Money and quantity formatting for the billing module.

Storage is integer minor units everywhere: money in cents, quantities in
thousandths, tax rates in thousandths of a percent. No float and no Decimal is
ever stored, returned to a template, or handed to Stripe by this module.

    money        *_cents BIGINT       123456 -> $1,234.56
    quantity     qty_milli BIGINT       7500 -> 7.5
    tax rate     tax_rate_milli INT     8875 -> 8.875%

Decimal is used locally inside parse_money/parse_qty/parse_rate only, purely to
get exact ROUND_HALF_UP on user input, and never crosses the module boundary.
Rounding of computed amounts happens in SQL, not here; line_amount/tax_amount
exist only to mirror that SQL for client-side previews and validation.
"""

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import g

import db

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$",
    "AUD": "A$", "NZD": "NZ$", "CHF": "CHF ", "SEK": "SEK ", "NOK": "NOK ",
    "DKK": "DKK ", "PLN": "PLN ", "ZAR": "R", "MXN": "MX$", "BRL": "R$",
    "SGD": "S$", "HKD": "HK$", "INR": "₹", "AED": "AED ", "ILS": "₪",
}

# Currencies where the minor unit is not 1/100. v1 refuses these outright rather
# than pretending the *_cents columns mean something else for them.
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF", "TWD", "UGX", "XAF", "XOF"}

MAX_RATE_MILLI = 100_000  # 100.000%

_STRIP = re.compile(r"[\s,  $€£¥₹₪]")
# Signs are consumed by _to_decimal before this runs, so the remainder must be
# unsigned digits -- otherwise '--5' would round-trip to a positive 5.
_NUMERIC = re.compile(r"^(?:\d+(?:\.\d*)?|\.\d+)$")


class MoneyError(ValueError):
    """Unparseable user input. Route handlers flash the message."""


# --------------------------------------------------------------------------
# parsing: user input -> storage integers
# --------------------------------------------------------------------------

def _to_decimal(raw, label):
    """Normalize a user-typed number to a Decimal. Accepts '1,234.56', '$1234.56'
    and the accounting negative '(50)'. Rejects '1.2.3', '--5', '1e5'."""
    s = (raw or "").strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s = _STRIP.sub("", s)
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        negative, s = not negative, s[1:]
    if not s or not _NUMERIC.match(s):
        raise MoneyError(f"{label} must be a number, e.g. 1234.56")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise MoneyError(f"{label} must be a number, e.g. 1234.56")
    return -value if negative else value


def _blank(raw):
    return raw is None or str(raw).strip() == ""


def parse_money(raw, *, allow_negative=False, default=None, label="Amount"):
    """'$1,234.56' -> 123456. Blank input returns `default` (pass default=0 for
    optional fields); a blank with default=None raises."""
    if _blank(raw):
        if default is None:
            raise MoneyError(f"{label} is required.")
        return default
    value = _to_decimal(raw, label)
    cents = int(value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if cents < 0 and not allow_negative:
        raise MoneyError(f"{label} cannot be negative.")
    return cents


def parse_qty(raw, *, default=1000, label="Quantity"):
    """'7.5' -> 7500 (thousandths)."""
    if _blank(raw):
        return default
    value = _to_decimal(raw, label)
    if value < 0:
        raise MoneyError(f"{label} cannot be negative.")
    return int(value.scaleb(3).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_rate(raw, *, default=0, label="Tax rate"):
    """'8.875' or '8.875%' -> 8875 (thousandths of a percent)."""
    if _blank(raw):
        return default
    value = _to_decimal(str(raw).replace("%", ""), label)
    milli = int(value.scaleb(3).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if not 0 <= milli <= MAX_RATE_MILLI:
        raise MoneyError(f"{label} must be between 0 and 100.")
    return milli


# --------------------------------------------------------------------------
# formatting: storage integers -> display strings
# --------------------------------------------------------------------------

def _grouped(cents):
    """Absolute value of `cents` as '1,234.56'."""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{whole:,}.{frac:02d}"


def format_money(cents, currency=None, symbol=True, blank_zero=False):
    """123456 -> '$1,234.56'. None renders as an em dash (LEFT JOINs make NULLs)."""
    if cents is None:
        return "—"
    cents = int(cents)
    if blank_zero and cents == 0:
        return ""
    body = _grouped(cents)
    if symbol:
        body = currency_symbol(currency or default_currency()) + body
    return ("-" + body) if cents < 0 else body


def format_money_plain(cents, currency=None):
    """123456 -> '1234.56'. For <input value=...> and CSV: no symbol and no
    thousands separator, so it round-trips through parse_money()."""
    if cents is None:
        return ""
    cents = int(cents)
    whole, frac = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{whole}.{frac:02d}"


def _trim(value, places):
    text = f"{abs(int(value)) // (10 ** places)}"
    frac = f"{abs(int(value)) % (10 ** places):0{places}d}".rstrip("0")
    out = f"{text}.{frac}" if frac else text
    return ("-" + out) if int(value) < 0 else out


def format_qty(qty_milli):
    """7500 -> '7.5'; 1000 -> '1'."""
    return "" if qty_milli is None else _trim(qty_milli, 3)


def format_rate(rate_milli):
    """8875 -> '8.875'; 0 -> '0'."""
    return "" if rate_milli is None else _trim(rate_milli, 3)


# --------------------------------------------------------------------------
# arithmetic: Python mirrors of the SQL, for previews and validation only
# --------------------------------------------------------------------------

def line_amount(qty_milli, unit_price_cents):
    """Mirror of the invoice_lines.amount_cents generated column. Must agree
    with the SQL exactly -- both are round-half-up on an exact rational."""
    value = Decimal(int(qty_milli)) * Decimal(int(unit_price_cents)) / Decimal(1000)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def tax_amount(base_cents, rate_milli):
    """Mirror of the tax expression in billing.recompute_totals(). Tax is applied
    to a whole rate-group's base, never per line -- see that function."""
    value = Decimal(int(base_cents)) * Decimal(int(rate_milli)) / Decimal(100_000)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------
# currency
# --------------------------------------------------------------------------

def default_currency():
    """The `billing_currency` setting, cached per request the same way app.py
    caches settings_all() -- otherwise every cell of a 50-row list SELECTs."""
    if "billing_currency" not in g:
        try:
            g.billing_currency = (db.get_setting("billing_currency", "USD") or "USD").upper()
        except Exception:
            g.billing_currency = "USD"
    return g.billing_currency


def currency_symbol(code):
    code = (code or "USD").upper()
    return CURRENCY_SYMBOLS.get(code, code + " ")


def minor_units(code):
    return 0 if (code or "").upper() in ZERO_DECIMAL else 2


def check_supported(code):
    """v1 stores money as hundredths. A zero-decimal currency would silently mean
    something else in every *_cents column, so refuse it outright."""
    code = (code or "").upper()
    if len(code) != 3 or not code.isalpha():
        raise MoneyError("Currency must be a 3-letter code, e.g. USD.")
    if code in ZERO_DECIMAL:
        raise MoneyError(f"{code} is a zero-decimal currency and is not supported yet.")
    return code


# --------------------------------------------------------------------------
# Jinja wiring
# --------------------------------------------------------------------------

def register_filters(app):
    """Called once from create_app()."""
    app.add_template_filter(format_money, "money")
    app.add_template_filter(format_money_plain, "money_plain")
    app.add_template_filter(format_qty, "qty")
    app.add_template_filter(format_rate, "rate")
    app.add_template_global(currency_symbol, "currency_symbol")
    app.add_template_global(default_currency, "default_currency")
