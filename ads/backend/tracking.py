"""Tracking health (roadmap 6.2), pure parts: what Meta's dataset has received, from where,
how well it matches people, and what that means for this account. Instant Form leads are
counted on Meta's side without any website code; the dataset matters because lead stages
(Contacted, Qualified, Won) sent from here teach Meta which leads become clients."""
from datetime import datetime, timezone

QUIET_HOURS = 48
GOOD_EMQ = 6.0
CRM_EVENTS = ("Lead", "Contacted", "Qualified", "Won", "Lost")


def parse_time(v):
    """Meta's last-fired times: ISO strings or Unix seconds; the Unix epoch means never."""
    if v in (None, "", 0, "0"):
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            t = datetime.fromtimestamp(int(v), timezone.utc)
        else:
            t = datetime.strptime(str(v), "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, OSError):
        return None
    return None if t.year < 2000 else t


def counts(stats_body):
    """/{dataset}/stats?aggregation=event → {event: count} over the buckets returned."""
    out = {}
    for bucket in (stats_body or {}).get("data") or []:
        for row in bucket.get("data") or []:
            name = row.get("value")
            if name:
                out[name] = out.get(name, 0) + int(row.get("count") or 0)
    return out


def sources(stats_body):
    """/{dataset}/stats?aggregation=event_source → {"server": n, "browser": n}."""
    out = {"server": 0, "browser": 0}
    for name, n in counts(stats_body).items():
        out["server" if "server" in name.lower() or name.upper() in ("CAPI", "SERVER_ONLY") else "browser"] += n
    return out


def quality(body):
    """Dataset quality → [{channel, event, emq}] with Event Match Quality on 0–10."""
    out = []
    for channel, items in (body or {}).items():
        if not isinstance(items, list):
            continue
        for it in items:
            emq = (it.get("event_match_quality") or {}).get("composite_score")
            if emq is not None:
                out.append({"channel": channel, "event": it.get("event_name"), "emq": round(float(emq), 1)})
    return out


def assess(details, event_counts, by_source, match, crm, now, crm_on):
    """The verdict: state ('not_set_up' | 'quiet' | 'weak' | 'ok'), a headline and what to do."""
    last = max([t for t in (parse_time(details.get("last_fired_time")), parse_time(details.get("server_last_fired_time"))) if t], default=None)
    total = sum(event_counts.values())
    todo = []
    if not crm_on:
        todo.append("Turn on Settings → Lead stages to Meta, so Meta learns which leads become clients.")
    if crm.get("failed"):
        todo.append(f"{crm['failed']} lead stage{'s' if crm['failed'] != 1 else ''} didn't reach Meta: see Lead stages to Meta below.")
    low = [m for m in match if m["emq"] < GOOD_EMQ]
    if low:
        todo.append(f"Match quality is {min(m['emq'] for m in low)}/10 for {', '.join(sorted({m['event'] or m['channel'] for m in low}))}; "
                    "below 6 Meta can't tie many events to people.")
    if last is None:
        return {"state": "not_set_up", "last": None, "total": 0, "todo": todo,
                "headline": "Meta has never received an event from this dataset. Form leads still count; "
                            "what's missing is Meta hearing which leads became clients."}
    hours = (now - last).total_seconds() / 3600
    server_share = round(100 * by_source["server"] / (by_source["server"] + by_source["browser"])) if (by_source["server"] + by_source["browser"]) else None
    base = {"last": last.isoformat(), "total": total, "server_share": server_share}
    if hours > QUIET_HOURS:
        return {**base, "state": "quiet", "todo": todo, "headline": f"Nothing has arrived for {int(hours // 24)} days. If stages are being sent, check Lead stages to Meta."}
    if low or crm.get("failed"):
        return {**base, "state": "weak", "todo": todo, "headline": "Events are arriving, with something to fix."}
    return {**base, "state": "ok", "todo": todo, "headline": "Events are arriving and match well."}
