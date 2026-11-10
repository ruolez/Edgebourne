"""Client reports (roadmap 7.3), pure parts: the period, the comparison, the funnel, the headline
and the footnotes. Structure from the meta-ads skill (references/14): business results first,
platform metrics only as the why, attribution named, complete days only."""
import base64
import hashlib
import hmac
import json
from datetime import date, timedelta

MEASUREMENT_CHANGE = date(2026, 11, 12)  # Meta starts measuring some website conversions on devices
SHARE_DAYS = 90


def period(kind, today, start=None):
    """(start, end) of the last complete Mon–Sun week or calendar month, or the one starting at `start`."""
    if kind == "month":
        first = (start or (today.replace(day=1) - timedelta(days=1))).replace(day=1)
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return first, nxt - timedelta(days=1)
    monday = start - timedelta(days=start.weekday()) if start else today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def previous(start, end, kind):
    if kind == "month":
        return period("month", start, start=(start - timedelta(days=1)))
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def complete(end, today):
    """Only whole days count: the period must have ended before today."""
    return end < today


def funnel(leads, contacted, qualified, won):
    """Each step with its share of the step before (None when there was nothing to convert)."""
    steps = [("Leads", leads), ("Contacted", contacted), ("Qualified", qualified), ("Won", won)]
    out = []
    for i, (name, n) in enumerate(steps):
        prev = steps[i - 1][1] if i else None
        out.append({"step": name, "n": n, "rate": round(100 * n / prev) if prev else None})
    return out


def money(cents):
    return f"${cents / 100:,.2f}" if cents is not None else "—"


def headline(now, before, target_cents=None):
    """Two business sentences: the KPI (cost per qualified lead when there are qualified leads,
    else cost per lead) against the target and the period before, and how many it rests on."""
    def cost(p, key):
        return round(p["spend_cents"] / p[key]) if p.get(key) else None
    key, label = ("qualified", "qualified lead") if now.get("qualified") else ("leads", "lead")
    c_now, c_before = cost(now, key), cost(before, key)
    if c_now is None:
        first = f"{money(now['spend_cents'])} spent and no {label}s yet."
    else:
        first = f"Cost per {label} was {money(c_now)}"
        if target_cents:
            first += f" against the {money(target_cents)} target ({'under' if c_now <= target_cents else 'over'} by {money(abs(c_now - target_cents))})"
        if c_before is not None:
            first += f", {'down' if c_now < c_before else 'up' if c_now > c_before else 'level'} from {money(c_before)} the period before" if c_now != c_before else ", the same as the period before"
        first += "."
    n = now.get(key) or 0
    second = f"{n} {label}{'s' if n != 1 else ''} from {money(now['spend_cents'])} spent" + (
        "; at this volume the number is directional." if 0 < n < 10 else ".")
    return first + " " + second


def footnotes(start, end):
    notes = ["Leads are Meta-reported (Instant Forms) under each ad set's attribution setting; qualified and won come from the lead inbox, by the day the lead arrived.",
             "Complete days only, in the ad account's time zone. Conversion counts may include Meta's modelled conversions; reach and frequency are estimates."]
    if start < MEASUREMENT_CHANGE <= end:
        notes.append("From Nov 12, 2026 Meta also measures some website conversions on people's devices; figures before and after that date are not directly comparable. Instant Form leads are not affected.")
    return notes


def sign(secret, payload):
    """A share link token: the payload and an HMAC, URL-safe."""
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=").decode()
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{mac}"


def verify(secret, token, today):
    """The payload of a valid, unexpired token, else None."""
    try:
        body, mac = str(token).rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(mac, hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if date.fromisoformat(payload["exp"]) < today:
        return None
    return payload
