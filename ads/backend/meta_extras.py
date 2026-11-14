"""AM-E: Meta's extra insights, read through the Ads Manager link (AM-A) and kept in am_snapshots / am_screens.

Pure: how you compare with similar advertisers (`comparison_rows`, `auction_lines`, `campaign_line`, `trend_line`), Meta's
unusual changes and error messages as alerts (`anomaly_alerts`, `error_alerts`, `to_close`), the ad page's error panel,
tracking quality in words, the business context Claude reads, which ads get Meta's picture and what a picture push holds.

Meta's words are data: whitelisted fields only, strings cut, never turned into HTML or a link here (the pages escape them),
and Claude gets them fenced as data in its snapshot."""
import base64
import binascii
import re
from datetime import date, timedelta

import attachments
import words

METRIC_WORDS = {"cost_per_lead": "Cost per lead", "ctr": "Click rate", "cpm": "Cost per 1,000 views", "cpc": "Cost per click",
                "frequency": "How often people see it", "spend": "Spend", "leads": "Leads", "impressions": "Views",
                "reach": "People reached", "link_clicks": "Link clicks", "cost_per_result": "Cost per result"}
MONEY_METRICS = {"cost_per_lead", "cpm", "cpc", "spend", "cost_per_result"}
PERCENT_METRICS = {"ctr"}
LOWER_BETTER = {"cost_per_lead", "cpm", "cpc", "cost_per_result"}
HIGHER_BETTER = {"ctr", "leads", "link_clicks"}
# Anomalies about cost or spend are money matters in the Inbox; the rest (views, delivery) are about ad status.
MONEY_ANOMALIES = MONEY_METRICS
RANK_WORDS = {"ABOVE_AVERAGE": "Above average", "AVERAGE": "Average", "BELOW_AVERAGE_35": "Below average (bottom 35 %)",
              "BELOW_AVERAGE_20": "Below average (bottom 20 %)", "BELOW_AVERAGE_10": "Below average (bottom 10 %)"}
RANK_FIELDS = (("quality_ranking", "Quality"), ("engagement_rate_ranking", "Engagement"), ("conversion_rate_ranking", "Conversions"))
VERDICT_WORDS = {"better": "better", "same": "about the same", "worse": "worse"}
DIRECTION_VERDICT = {"better": "better", "above": "better", "worse": "worse", "below": "worse", "same": "same", "similar": "same",
                     "average": "same"}
LINK_OWNED = ("meta_anomaly", "meta_ad_error")  # raised and closed by the link's reads, never by the hourly run
SUMMARY_MAX, MESSAGE_MAX, FIX_MAX = 300, 1000, 300
CONTEXT_MAX = 120
PICTURE_MAX = 3 * 1024 * 1024
PICTURE_MIMES = ("image/png", "image/jpeg", "image/webp")
SCREENS_PER_ACCOUNT = 12
SCREEN_FRESH = timedelta(days=1)
PAGES = {"ad": "/ad.html?id=", "adset": "/adset.html?id=", "campaign": "/campaign.html?id="}
METRIC_RE = re.compile(r"[a-z_]{1,40}")
PLACEMENT_RE = re.compile(r"[A-Za-z0-9_]{1,40}")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cut(text, n):
    return " ".join(str(text or "").split())[:n]


def subject_id(entity_id):
    """The campaign, ad set or ad an alert is about: an anomaly's entity carries its metric ("<id>:<metric>")."""
    return None if entity_id is None else str(entity_id).split(":", 1)[0]


def anomaly_category(metric):
    return "money" if metric in MONEY_ANOMALIES else "status"


# ---------------------------------------------------------------- how you compare

def _amount(value, currency):
    """Meta's amounts are in the currency itself (4.79), not cents."""
    cents = round(value * 100)
    return words.money(cents, currency, whole=not cents % 100)


def fmt_value(metric, value, currency):
    if metric in MONEY_METRICS:
        return _amount(value, currency)
    if metric in PERCENT_METRICS:
        return f"{value:g}%"
    return f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"


def _range(metric, low, high, currency):
    if metric in MONEY_METRICS:
        lo, hi = _amount(low, currency), _amount(high, currency)
        symbol = words.SYMBOLS.get((currency or "USD").upper())
        return f"{lo}–{hi}" if symbol else f"{lo.rsplit(' ', 1)[0]}–{hi}"
    if metric in PERCENT_METRICS:
        return f"{low:g}–{high:g}%"
    return f"{fmt_value(metric, low, currency)}–{fmt_value(metric, high, currency)}"


def _verdict(metric, value, bench, peer):
    """Only what Meta's own answer says: its direction word, else its percentile, else where we sit in its range."""
    direction = str((peer or {}).get("direction") or "").lower()
    if direction in DIRECTION_VERDICT:
        return DIRECTION_VERDICT[direction]
    pct = _num((peer or {}).get("percentile"))
    if pct is not None:
        return "better" if pct >= 60 else "worse" if pct <= 40 else "same"
    low, high = _num((bench or {}).get("peer_low")), _num((bench or {}).get("peer_high"))
    if value is None or low is None or high is None:
        return None
    if metric in LOWER_BETTER:
        return "better" if value < low else "worse" if value > high else "same"
    if metric in HIGHER_BETTER:
        return "better" if value > high else "worse" if value < low else "same"
    return None


def comparison_rows(benchmarks, peers, currency):
    """[{metric, label, ours, peers, verdict, note}] for Today, Results and the campaign page. A metric Meta gave no peer
    value for is left out (never guessed); money in the account's currency."""
    bench = {r.get("metric"): r for r in benchmarks or [] if isinstance(r, dict)}
    peer = {r.get("metric"): r for r in peers or [] if isinstance(r, dict)}
    out = []
    for metric in list(dict.fromkeys([*bench, *peer])):
        if metric not in METRIC_WORDS:
            continue
        b, p = bench.get(metric) or {}, peer.get(metric) or {}
        value = _num(b.get("value")) if _num(b.get("value")) is not None else _num(p.get("value"))
        low, high, median = _num(b.get("peer_low")), _num(b.get("peer_high")), _num(b.get("peer_median"))
        if low is not None and high is not None:
            theirs = _range(metric, low, high, currency)
        elif median is not None:
            theirs = fmt_value(metric, median, currency)
        elif _num(p.get("peer_value")) is not None:
            theirs = fmt_value(metric, p["peer_value"], currency)
        else:
            continue
        if value is None:
            continue
        note = ", ".join(_cut(b.get(k), 60) for k in ("industry", "region") if b.get(k))
        out.append({"metric": metric, "label": METRIC_WORDS[metric], "ours": fmt_value(metric, value, currency), "peers": theirs,
                    "verdict": _verdict(metric, value, b, p), "note": note or None})
    return out


def auction_lines(auction, known, ids=None):
    """Meta's auction rankings in words, per ad (or ad set / campaign) this account holds: [{entity_id, name, words}]."""
    out = []
    for r in auction or []:
        eid = str(r.get("entity_id") or "")
        if eid not in known or (ids is not None and eid not in ids):
            continue
        parts = [f"{label}: {RANK_WORDS[r[f]]}" for f, label in RANK_FIELDS if r.get(f) in RANK_WORDS]
        if parts:
            out.append({"entity_id": eid, "name": known[eid].get("name") or eid, "words": " · ".join(parts)})
    return out


def campaign_line(rows, auction):
    """One sentence under a campaign's figures (the comparison is the account's; the rankings are its own ads')."""
    lead = next((r for r in rows if r["metric"] == "cost_per_lead"), rows[0] if rows else None)
    if not lead:
        return None
    text = f"Your account vs similar advertisers: {lead['label'].lower()} {lead['ours']} against {lead['peers']}"
    text += f" ({VERDICT_WORDS[lead['verdict']]})." if lead.get("verdict") else "."
    quality = next((a for a in auction if a["words"].startswith("Quality:")), None)
    if quality:
        text += f" {quality['name']} quality: {quality['words'].split(' · ')[0].split(': ', 1)[1]}."
    return text


def trend_line(trends):
    """Results' line under the chart, from Meta's account-level trend (the first metric it named we have words for)."""
    for r in trends or []:
        metric, direction = r.get("metric"), str(r.get("direction") or "").lower()
        if metric not in METRIC_WORDS or direction not in ("up", "down", "flat"):
            continue
        days = re.fullmatch(r"last_(\d{1,3})d", str(r.get("period") or ""))
        over = f" over {days.group(1)} days" if days else ""
        pct = _num(r.get("change_pct"))
        how = {"up": "rising", "down": "falling", "flat": "steady"}[direction]
        tail = f" ({abs(pct):g} % {direction})" if pct is not None and direction != "flat" else ""
        return f"Meta sees {METRIC_WORDS[metric].lower()} {how}{over}{tail}."
    return None


def pick_benchmarks(link_fetched_at, monday_as_of):
    """Which comparison Today shows: the link's ("link") when it is newer than the Monday summary's day, else the old
    Monday table ("monday"), or nothing."""
    if link_fetched_at is None:
        return "monday" if monday_as_of else None
    if not monday_as_of:
        return "link"
    try:
        monday = date.fromisoformat(str(monday_as_of)[:10])
    except ValueError:
        return "link"
    return "link" if link_fetched_at.date() >= monday else "monday"


# ---------------------------------------------------------------- alerts

def _subject(eid, known):
    k = known.get(str(eid or ""))
    return (str(eid), k) if k else ("account", None)


def _pct_words(pct):
    return f"{abs(pct):g}"


def anomaly_alerts(anomalies, known, today, on=True):
    """alerts.raise_found-shaped dicts (rule meta_anomaly, warn, one per thing and metric per day). The thing is the ad,
    ad set or campaign Meta named when this account holds it, else the account. measure = the size of the change (%),
    so "Only if it gets worse" wakes on a bigger one."""
    if not on:
        return []
    best = {}
    for r in anomalies or []:
        metric = r.get("metric")
        if not isinstance(metric, str) or not METRIC_RE.fullmatch(metric) or metric not in METRIC_WORDS:
            continue
        pct = _num(r.get("change_pct"))
        direction = str(r.get("direction") or "").lower()
        if direction not in ("up", "down"):
            direction = "down" if pct is not None and pct < 0 else "up"
        eid, k = _subject(r.get("entity_id"), known)
        key = (eid, metric)
        size = abs(pct) if pct is not None else None
        if key in best and (best[key][0] or 0) >= (size or 0):
            continue
        best[key] = (size, r, k, direction)
    found = []
    for (eid, metric), (size, r, k, direction) in best.items():
        change = f" {direction} {_pct_words(size)} %" if size is not None else f" {'up' if direction == 'up' else 'down'}"
        where = f" on “{k['name']}”" if k else " across the account"
        lines = [_cut(r.get("summary"), SUMMARY_MAX)] if r.get("summary") else []
        try:
            spotted = date.fromisoformat(str(r.get("detected_on"))[:10])
        except ValueError:
            spotted = today
        lines.append(f"Spotted {words.weekday(spotted)}")
        found.append({"rule": "meta_anomaly", "entity_id": f"{eid}:{metric}", "key": f"meta_anomaly:{eid}:{metric}:{today.isoformat()}",
                      "level": "warn", "kind": "condition", "title": f"Meta noticed: {METRIC_WORDS[metric].lower()}{change}{where}",
                      "lines": lines, "campaign_id": k.get("campaign_id") if k else None,
                      "href": PAGES[k["level"]] + eid if k else "/performance.html", "measure": round(float(size), 1) if size is not None else None})
    return found


def error_alerts(errors, known, today, on=True):
    """meta_ad_error: one per thing Meta reports an error on; bad when Meta says it blocks delivery (never snoozable),
    else warn. Lines are Meta's summary in plain text; the ad page shows the whole message."""
    if not on:
        return []
    by = {}
    for r in errors or []:
        eid, k = _subject(r.get("entity_id"), known)
        by.setdefault(eid, (k, []))[1].append(r)
    found = []
    for eid, (k, rows) in by.items():
        rows = sorted(rows, key=lambda r: not r.get("blocking"))
        blocking = bool(rows[0].get("blocking"))
        name = k["name"] if k else "the account"
        title = f"Meta: “{name}” can't deliver until it's fixed" if blocking else f"Meta flags a problem on “{name}”"
        lines = [_cut(rows[0].get("summary") or rows[0].get("message") or "Meta reports an error.", SUMMARY_MAX)]
        if len(rows) > 1:
            lines.append(f"+{len(rows) - 1} more")
        found.append({"rule": "meta_ad_error", "entity_id": eid, "key": f"meta_ad_error:{eid}:{today.isoformat()}",
                      "level": "bad" if blocking else "warn", "kind": "condition", "title": title, "lines": lines,
                      "campaign_id": k.get("campaign_id") if k else None, "href": PAGES[k["level"]] + eid if k else "/ads.html",
                      "measure": 2 if blocking else 1})
    return found


def to_close(opened, found_pairs, read_at, stale, rules=LINK_OWNED):
    """Open link-owned alerts (of `rules`) that a read no longer lists: closed only by a fresh read newer than the alert.
    A stale read (the Mac away, the link down) closes nothing."""
    if stale:
        return []
    return [a["id"] for a in opened if a["rule"] in rules and (a["rule"], a["entity_id"]) not in found_pairs
            and (a.get("created_at") is None or a["created_at"] <= read_at)]


def error_panel(errors, tz):
    """The ad page's "What Meta says": [{summary, message, code, fix, since_words, blocking}], blocking first."""
    out = []
    for r in sorted(errors or [], key=lambda r: not r.get("blocking")):
        since = None
        try:
            since = f"Since {words.weekday(date.fromisoformat(str(r.get('since'))[:10]))}"
        except ValueError:
            pass
        out.append({"summary": _cut(r.get("summary"), SUMMARY_MAX) or "Meta reports an error.",
                    "message": str(r.get("message") or "")[:MESSAGE_MAX], "code": _cut(r.get("code"), 20) or None,
                    "fix": _cut(r.get("fix"), FIX_MAX) or None, "since_words": since, "blocking": bool(r.get("blocking"))})
    return out


# ---------------------------------------------------------------- tracking quality, context

def quality_rows(rows):
    """Meta's match quality per event: [{event, score, words, pct, band, advice}]; a score outside 0–10 is left out."""
    out = []
    for r in rows or []:
        score = _num(r.get("match_quality"))
        if score is None or not 0 <= score <= 10 or not r.get("event"):
            continue
        band = "good" if score >= 6 else "okay" if score >= 4 else "poor"
        out.append({"event": _cut(r["event"], 60), "score": round(score, 1), "words": f"{score:.1f} out of 10: {band}",
                    "pct": round(score * 10), "band": band, "advice": _cut(r.get("advice"), SUMMARY_MAX) or None})
    return out


CONTEXT_KEYS = ("vertical", "business_type", "region", "objective_mix", "maturity")


def context_block(ctx):
    """The business context Meta keeps, whitelisted and cut, for Claude's snapshot."""
    out = {}
    for k in CONTEXT_KEYS:
        v = (ctx or {}).get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v[:CONTEXT_MAX]
        elif isinstance(v, list):
            items = [str(x)[:CONTEXT_MAX] for x in v[:10] if isinstance(x, (str, int, float)) and not isinstance(x, bool)]
            if items:
                out[k] = items
    return out


# ---------------------------------------------------------------- Meta's picture

def screenshot_targets(ads, have, now, limit=SCREENS_PER_ACCOUNT):
    """Ad ids due a daily picture: the first `limit` delivering ads (callers list them busiest first) whose picture,
    or last try, is older than a day. have: {ad id: when its picture was read or last asked for}."""
    delivering = [a["id"] for a in ads if a.get("effective_status") == "ACTIVE"][:limit]
    return [i for i in delivering if have.get(i) is None or now - have[i] >= SCREEN_FRESH]


def _image_part(result):
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("images"), list):
        img = next((i for i in result["images"] if isinstance(i, dict)), None)
        return img and (img.get("data_b64"), result.get("placement") or img.get("placement"))
    if isinstance(result.get("content"), list):
        img = next((c for c in result["content"] if isinstance(c, dict) and c.get("type") == "image"), None)
        return img and (img.get("data"), result.get("placement"))
    if "data_b64" in result:
        return result.get("data_b64"), result.get("placement")
    return None


def picture(result):
    """({bytes, mime, placement, width, height}, None) or (None, why). The type comes from the bytes (PNG, JPEG or WebP;
    what Meta or the Mac says it is counts for nothing), 3 MB at most."""
    part = _image_part(result)
    if not part or not isinstance(part[0], str) or not part[0]:
        return None, "Meta's answer had no picture in it."
    if len(part[0]) > PICTURE_MAX * 4 // 3 + 8:
        return None, "Meta's picture is bigger than 3 MB; nothing was kept."
    try:
        data = base64.b64decode(part[0], validate=True)
    except (binascii.Error, ValueError):
        return None, "Meta's picture couldn't be read; nothing was kept."
    if len(data) > PICTURE_MAX:
        return None, "Meta's picture is bigger than 3 MB; nothing was kept."
    mime = attachments.sniff(data[:attachments.HEAD])
    if mime not in PICTURE_MIMES:
        return None, "Meta's picture isn't a PNG, JPEG or WebP image; nothing was kept."
    size = attachments.measure(mime, data)
    placement = part[1] if isinstance(part[1], str) and PLACEMENT_RE.fullmatch(part[1]) else ""
    return {"bytes": data, "mime": mime, "placement": placement, "width": size["width"], "height": size["height"]}, None
