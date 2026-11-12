"""Client reports (roadmap 7.3), pure parts: the period, the comparison, the funnel, the headline
and the footnotes. Structure from the meta-ads skill (references/14): business results first,
platform metrics only as the why, attribution named, complete days only."""
import base64
import hashlib
import hmac
import json
from datetime import date, datetime, time, timedelta

import status_history
import words

MEASUREMENT_CHANGE = date(2026, 11, 12)  # Meta starts measuring some website conversions on devices
SHARE_DAYS = 90
LEAD_STEP = "Leads received"  # the console's own count (00-PLAN C3)
SEND_HOUR = 8
NOTE_MAX = 2000
money = words.money


def period(kind, today, start=None):
    """(start, end) of the last complete Mon–Sun week or calendar month, or the one starting at `start`."""
    if kind == "month":
        first = (start or (today.replace(day=1) - timedelta(days=1))).replace(day=1)
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return first, nxt - timedelta(days=1)
    monday = start - timedelta(days=start.weekday()) if start else today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def recent_periods(kind, today, since=None, n=12):
    """The complete weeks or months to pick from, newest first: the default report, then the ones before it,
    back to the period holding `since` (the first day with data), at most n. Always at least the default."""
    out = [period(kind, today)]
    while len(out) < n:
        s, e = previous(*out[-1], kind)
        if since and e < since:
            break
        out.append((s, e))
    return out


def email_due(mode, local, last_sent):
    """(kind, start, end, key) of the report to email now, or None. Due from 8 AM the day after the
    week or month ends, and on any later day until it went out (a worker down on Monday catches up)."""
    if mode not in ("weekly", "monthly"):
        return None
    kind = "week" if mode == "weekly" else "month"
    s, e = period(kind, local.date())
    key = f"{kind}:{s.isoformat()}"
    if key == last_sent or (local.date() == e + timedelta(days=1) and local.hour < 8):
        return None
    return kind, s, e, key


def previous(start, end, kind):
    if kind == "month":
        return period("month", start, start=(start - timedelta(days=1)))
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def complete(end, today):
    """Only whole days count: the period must have ended before today."""
    return end < today


def funnel(steps):
    """Each step is (label, n) or (label, n, base_label); its rate is n as a share of the base step (the step
    before unless named), None when the base is 0. Items: {step, n, rate, of}. Every step counts the same people
    (the leads received, by arrival day) and every base holds its step, so no rate passes 100 (00-PLAN C2)."""
    out, seen = [], {}
    for i, step in enumerate(steps):
        label, n = step[0], step[1]
        of = step[2] if len(step) > 2 else (steps[i - 1][0] if i else None)
        if of is not None and of not in seen:
            raise ValueError(f"funnel step {label!r} names an unknown base {of!r}")
        base = seen.get(of)
        out.append({"step": label, "n": n, "rate": int(100 * n / base + 0.5) if base else None, "of": of})
        seen[label] = n
    return out


def lead_gap(received, meta):
    """Meta's lead count beside the leads that reached the console, in plain words; None when they agree."""
    if received == meta:
        return None
    if meta == 0:
        text = (f"Meta counted no leads from the ads; your leads list has {received} (from the form outside an ad, "
                "or not counted by Meta yet).")
    elif received < meta:
        text = (f"Meta counted {meta} lead{'s' if meta != 1 else ''}; {meta - received} of them didn't reach your leads list. "
                "Meta can count a lead on the day the ad was seen, and test entries are left out here.")
    else:
        text = (f"Meta counted {meta} lead{'s' if meta != 1 else ''}; your leads list has {received - meta} more (someone used the "
                "form outside an ad, or Meta counted it on another day).")
    return {"meta": meta, "received": received, "diff": received - meta, "text": text}


def headline(now, before, target_cents=None, currency="USD"):
    """Two business sentences: the KPI (cost per qualified lead when there are qualified leads,
    else cost per lead) against the target and the period before, and how many it rests on."""
    def m(cents):
        return money(cents, currency)

    def cost(p, key):
        return round(p["spend_cents"] / p[key]) if p.get(key) else None
    key, label = ("qualified", "qualified lead") if now.get("qualified") else ("leads", "lead")
    c_now, c_before = cost(now, key), cost(before, key)
    if c_now is None:
        first = f"{m(now['spend_cents'])} spent and no {label}s yet."
    else:
        first = f"Cost per {label} was {m(c_now)}"
        if target_cents:
            first += f" against the {m(target_cents)} target ({'under' if c_now <= target_cents else 'over'} by {m(abs(c_now - target_cents))})"
        if c_before is not None:
            first += f", {'down' if c_now < c_before else 'up' if c_now > c_before else 'level'} from {m(c_before)} the period before" if c_now != c_before else ", the same as the period before"
        first += "."
    n = now.get(key) or 0
    second = f"{n} {label}{'s' if n != 1 else ''} from {m(now['spend_cents'])} spent" + (
        "; at this volume the number is directional." if 0 < n < 10 else ".")
    return first + " " + second


def footnotes(start, end, sent_on=None):
    notes = ["Leads are the people who reached your leads list from the lead forms (test entries left out), by the day they arrived; "
             "Meta's own count, under each ad set's attribution setting, is shown beside them. Qualified and won come from your "
             "leads list. In the table of ads, leads are Meta's count per ad.",
             "Complete days only, in the ad account's time zone. Conversion counts may include Meta's modelled conversions; reach and frequency are estimates."]
    if start < MEASUREMENT_CHANGE <= end:
        notes.append("From Nov 12, 2026 Meta also measures some website conversions on people's devices; figures before and after that date are not directly comparable. Instant Form leads are not affected.")
    if sent_on:
        notes.append(f"Figures as sent on {words.day(sent_on)}, {sent_on.year}.")
    return notes


# ---------------------------------------------------------------- What we did (W2, 00-PLAN C14)

LEVEL_WORDS = {"campaign": "Campaign", "adset": "Ad set", "ad": "Ad", "form": "Lead form", "study": "A/B test", "account": "Account"}
ACTION_WORDS = {"create": "created", "duplicate": "copied", "archive": "archived", "delete": "deleted",
                "enhancement": "automatic change", "placement_media": "9:16 video for Reels added",
                "update_creative": "new version put on the ad", "restore_creative": "earlier version put back",
                "recommendation": "Meta's suggestion applied", "comment_reply": "replied to a comment",
                "comment_hide": "hid a comment", "comment_show": "showed a comment", "end": "ended early"}
SWITCH_WORDS = {"ACTIVE": "turned on", "PAUSED": "turned off", "ARCHIVED": "archived", "DELETED": "deleted"}
BUDGET_ACTIONS = {"budget": "daily_budget", "lifetime_budget": "lifetime_budget"}


def _lower_first(text):
    return text[:1].lower() + text[1:] if text else text


def _setup_words(level, field, old, new, currency, tz):
    """History's words for a budget, bid, date or audience change (status_history.headline), first letter lowered."""
    text = status_history.setup_headline({"level": level, "field": field, "old": old, "new": new},
                                         lambda c: money(c, currency), tz)
    return _lower_first(text) if text else None


def what_we_did(console, outside, currency="USD", tz=None):
    """One dated list: the console's own writes to Meta (meta_changes, ok) and changes Meta saw made elsewhere
    (status_events from a poll or webhook). Items {day, where: console|outside, level, name, what, text, at}, by
    day then time; `entity_id` is carried when given. Outside rows end "(in Ads Manager)"; fields with no words
    (learning, review…) are left out."""
    items = []
    for c in console:
        action = c.get("action")
        if action == "status":
            what = SWITCH_WORDS.get(c.get("new_value"), "turned off")
        elif action in BUDGET_ACTIONS:
            what = _setup_words(c.get("level"), BUDGET_ACTIONS[action], c.get("old_value"), c.get("new_value"), currency, tz)
        else:
            what = ACTION_WORDS.get(action) or (action or "changed").replace("_", " ")
        items.append(("console", c, c.get("created_at"), what))
    for e in outside:
        field = e.get("field")
        if field == "configured_status":
            what = SWITCH_WORDS.get(e.get("new_value"))
        elif field in status_history.OUTSIDE_FIELDS:
            what = _setup_words(e.get("level"), field, e.get("old_value"), e.get("new_value"), currency, tz)
        else:
            what = None
        if what:
            items.append(("outside", e, e.get("at"), what))
    out = []
    for where, row, at, what in sorted(items, key=lambda x: (x[1]["day"], x[2] or datetime.min)):
        name = row.get("entity_name") or ""
        text = f"{LEVEL_WORDS.get(row.get('level'), row.get('level') or '')} “{name}”: {what}" + (" (in Ads Manager)" if where == "outside" else "")
        out.append({"day": row["day"], "where": where, "level": row.get("level"), "name": name, "what": what, "text": text, "at": at,
                    **({"entity_id": row["entity_id"]} if row.get("entity_id") else {})})
    return out


# ---------------------------------------------------------------- Review before sending (W2)

def period_label(kind, start):
    """'Week of Nov 9' / 'Month of Oct 1'."""
    start = date.fromisoformat(start) if isinstance(start, str) else start
    return f"{'Week' if kind == 'week' else 'Month'} of {words.day(start)}"


def email_text(report, first_name, link, note, round_=1):
    """(subject, body) of the client email: greeting, the note when there is one, the headline, the link."""
    subject = f"{report['account']}: your ads report, {period_label(report['kind'], report['start'])}" + (" (updated)" if round_ > 1 else "")
    parts = [f"Hi {first_name}," if first_name else "Hi,"]
    if note and note.strip():
        parts.append(note.strip())
    parts += [report["headline"], f"The full report: {link}\n(The link works for {SHARE_DAYS} days.)"]
    return subject, "\n\n".join(parts)


def next_send_at(local_now, hour=SEND_HOUR):
    """The next `hour`:00 in local_now's zone: today if before it, else tomorrow (the zone gives the right offset)."""
    today_at = datetime.combine(local_now.date(), time(hour), tzinfo=local_now.tzinfo)
    if local_now < today_at:
        return today_at
    return datetime.combine(local_now.date() + timedelta(days=1), time(hour), tzinfo=local_now.tzinfo)


def who_label(emails):
    if not emails:
        return "nobody yet"
    if len(emails) == 1:
        return emails[0]
    if len(emails) == 2:
        return f"{emails[0]} and {emails[1]}"
    return f"{emails[0]} and {len(emails) - 1} others"


def review_state(row, mode, recipients, mail_ready, complete, auto_at, local_now, kind="week", emailing=True, newest=True):
    """What the review bar says and offers. `row`: the period's client_reports row or None; `mode`: auto|wait;
    `auto_at`: when the worker sends this period by itself (emailing on, without review, before 8 AM), else None;
    `emailing`: this kind of report is emailed by itself; `newest`: the latest complete period (the one that waits)."""
    tz = local_now.tzinfo
    status = (row or {}).get("status")
    who = who_label(recipients)
    later = "Send at 8 AM" if local_now.hour < SEND_HOUR else "Send tomorrow at 8 AM"

    def out(state, pill, line, actions):
        return {"status": state, "pill": pill, "line": line, "actions": actions, "later_label": later}
    if status == "sent":
        pill = ["ok", f"Sent {words.day_time(row['sent_at'], tz)}" if row.get("sent_at") else "Sent"]
        if not row.get("snapshot"):
            return out("sent", pill, "Sent before review was added; no copy was kept.", ["send_again"])
        return out("sent", pill, f"To {who_label(list(row.get('sent_to') or []))}. Clients see it as it was sent.", ["view_sent", "send_again"])
    if status == "sending" or (status == "scheduled" and row.get("send_at") and row["send_at"] <= local_now):
        return out("sending", ["info", "Sending…"], f"{len(row.get('sent_to') or [])} of {len(recipients)} sent.", [])
    if status == "skipped":
        return out("skipped", ["", "Not sending"], "You chose not to send this one.", ["undo_skip"])
    if status == "scheduled":
        return out("scheduled", ["info", f"Goes out {words.day_time(row['send_at'], tz)}"], f"To {who}.", ["send_now", "hold", "skip"])
    if not complete:
        return out("not_finished", ["", "Not finished yet"], f"You can send it once the {'week' if kind == 'week' else 'month'} is over.", [])
    if not recipients:
        return out("no_clients", ["", "No clients yet"], "No clients on this account yet: add them on the Team page.", [])
    if not mail_ready:
        return out("no_mail", ["bad", "Email isn't set up"], "Email isn't set up yet: Settings → Email.", [])
    if status == "waiting" or (mode != "auto" and emailing and newest):
        return out("waiting", ["warn", "Waiting for you"], f"Nothing goes to {who} until you press Send.", ["send_now", "send_later", "skip"])
    if auto_at:
        clock = words.clock(auto_at.astimezone(tz))
        return out("auto", ["info", f"Goes out at {clock}"],
                   f"It goes to {who} at {clock} without your review. Hold it to read it first.", ["send_now", "hold"])
    return out("not_sent", ["", "Not sent"], "This one wasn't emailed.", ["send_now", "send_later"])


def client_can_open(mode, row, emailing=True):
    """Clients see a period once it was sent, or any period when the account sends without review or doesn't
    email this report (nothing would ever release it to them)."""
    return (row or {}).get("status") == "sent" or mode == "auto" or not emailing


def idea_leads(ads, tags, dimension, untagged):
    """{idea: {received, qualified}}: the console's leads per ad ({id, received, qualified}) summed by the ad's tag,
    so an idea's share qualified counts one set of people (Meta's count per ad is a different one)."""
    out = {}
    for a in ads:
        value = (tags.get(a["id"]) or {}).get(dimension) or untagged
        g = out.setdefault(value, {"received": 0, "qualified": 0})
        g["received"] += a.get("received") or 0
        g["qualified"] += a.get("qualified") or 0
    return out


def note_visible(row, is_admin):
    """Admins always see the saved note; everyone else only once the report went out."""
    return bool(row and row.get("note") and (is_admin or row.get("status") == "sent"))


def review_alert(account, kind, start, recipients):
    """The Inbox / Today item for a report waiting for review (an owner-closed event, 00-PLAN C16)."""
    return {"rule": "report_review", "key": f"report_review:{kind}:{start.isoformat()}", "level": "warn",
            "title": f"{'Weekly' if kind == 'week' else 'Monthly'} report for {account} is waiting for you",
            "lines": [f"{period_label(kind, start)} · goes to {who_label(recipients)}", "Read it, add a note if you like, then press Send."],
            "href": f"/report.html?kind={kind}&start={start.isoformat()}#review"}


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
