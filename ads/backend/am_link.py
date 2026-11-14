"""AM-A: the Ads Manager link. Eugene's Mac reads what only Meta's Ads MCP server shows (drafts, error details,
benchmarks, unusual changes, tracking quality …) and pushes it here, one pass per console account, bound to the pass
this server handed out for that account and its ad account.

Pure: what is due (`due_kinds`), which push is kept (`push_refusal`), what Meta's answer becomes (`normalize`: listed
fields only, strings cut, ids digits only), the source line every screen shows (`source`), the link's state in words and
the `link_down` alert. Meta's text is data: it is never turned into HTML or a link here, and never altered either."""
import math
import re
from datetime import datetime, time, timedelta

import words

FAST_KINDS = ("drafts", "ad_errors")
DAILY_KINDS = ("benchmarks", "peers", "auction_ranking", "anomalies", "trend", "dataset_quality", "advertiser_context", "screenshots")
KINDS = FAST_KINDS + DAILY_KINDS
# Kinds kept in am_snapshots (latest per kind and scope). Drafts have their own table (AM-B, am_drafts; the snapshot keeps
# only the read's time and count), screenshots get theirs in AM-E: the plan asks only for kinds that have somewhere to go.
SNAPSHOT_KINDS = ("ad_errors", "benchmarks", "peers", "auction_ranking", "anomalies", "trend", "dataset_quality", "advertiser_context")
STORED_KINDS = ("drafts",) + SNAPSHOT_KINDS
MODES = ("direct", "claude")
FAST_MINUTES = {"direct": 15, "claude": 30}
DAILY_HOUR = 6                      # account time
CHECK_NOW_GAP = timedelta(minutes=2)
RUN_OPEN = timedelta(minutes=30)    # a pass not finished by then expires
AWAY_AFTER = timedelta(minutes=45)  # no pass for this long while connected = "the Mac has been away"
STALE_DAILY = timedelta(hours=30)
MAX_PUSH_BYTES = 2_000_000
STR_MAX = 300
LIST_MAX = {"drafts": 200, "ad_errors": 200, "anomalies": 50}
LIST_DEFAULT = 100

# The read tool of each kind on Meta's Ads MCP server (the Mac's amlink.LINK_TOOLS holds the same, tested there).
TOOLS = {
    "drafts": "ads_get_ad_entities", "ad_errors": "ads_get_errors",
    "benchmarks": "ads_insights_industry_benchmark", "peers": "ads_insights_performance_vs_peers",
    "auction_ranking": "ads_insights_auction_ranking_benchmarks", "anomalies": "ads_insights_anomaly_signal",
    "trend": "ads_insights_performance_trend", "dataset_quality": "ads_get_dataset_quality",
    "advertiser_context": "ads_insights_advertiser_context", "screenshots": "ads_get_ad_preview_screenshot",
}
DRAFT_PAGE = 25

# Whitelisted fields per kind (AM-E BENCH_FIELDS; pinned to Meta's real output after live check 2).
FIELDS = {
    "benchmarks": ("metric", "value", "peer_low", "peer_median", "peer_high", "industry", "region", "period"),
    "peers": ("metric", "value", "peer_value", "percentile", "direction", "period"),
    "auction_ranking": ("entity_id", "quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking", "period"),
    "trend": ("metric", "direction", "change_pct", "period", "entity_id"),
    "anomalies": ("entity_id", "level", "metric", "direction", "change_pct", "detected_on", "summary"),
    "ad_errors": ("entity_id", "level", "code", "summary", "message", "blocking", "since", "fix"),
    "dataset_quality": ("event", "match_quality", "freshness", "dedup_rate", "coverage", "advice"),
    "advertiser_context": ("vertical", "business_type", "region", "objective_mix", "maturity"),
}
# Where a kind's rows may sit in Meta's answer (a bare list is accepted too).
LIST_KEYS = {
    "ad_errors": ("errors", "ad_errors", "data"), "benchmarks": ("benchmarks", "data"), "peers": ("peers", "data"),
    "auction_ranking": ("rankings", "auction_ranking", "data"), "anomalies": ("anomalies", "signals", "data"),
    "trend": ("trends", "trend", "data"), "dataset_quality": ("events", "dataset_quality", "data"),
}
OBJECT_KINDS = {"advertiser_context": ("context", "advertiser_context")}
NOT_STORED = {"screenshots": "Meta's pictures aren't stored yet."}
KIND_WORDS = {"drafts": "Drafts", "ad_errors": "Meta's error messages", "benchmarks": "benchmarks", "peers": "how you compare",
              "auction_ranking": "auction rankings", "anomalies": "unusual changes", "trend": "trends",
              "dataset_quality": "tracking quality", "advertiser_context": "business context", "screenshots": "Meta's pictures"}


def digits(value):
    """'act_123' or '123' → '123'; anything else → None."""
    s = str(value or "").strip()
    s = s[4:] if s.startswith("act_") else s
    return s if re.fullmatch(r"\d{1,30}", s) else None


def tool_args(kind, ad_account_id, scope=None, after=None):
    """The arguments of one kind's read. Fixed here and on the Mac; checked against the tool's schema there."""
    if kind == "screenshots":
        return {"ad_id": str(scope)}
    args = {"ad_account_id": f"act_{ad_account_id}"}
    if kind == "drafts":
        args.update(object_state="draft", limit=DRAFT_PAGE)
        if after:
            args["after"] = after
    return args


def due_kinds(last_ok, now_local, mode, forced, kinds=STORED_KINDS):
    """The kinds one account's next pass reads. last_ok: {kind: aware datetime of the last kept read}.
    Fast kinds every FAST_MINUTES[mode]; daily kinds once per account day, from DAILY_HOUR (the boundary is built in
    the account's zone, so a 25-hour day still gets one read); never read = due now; Check now = every kind."""
    if forced:
        return list(kinds)
    boundary = datetime.combine(now_local.date(), time(DAILY_HOUR), tzinfo=now_local.tzinfo)
    out = []
    for kind in kinds:
        last = last_ok.get(kind)
        if last is None:
            out.append(kind)
        elif kind in FAST_KINDS:
            if now_local - last >= timedelta(minutes=FAST_MINUTES.get(mode, FAST_MINUTES["direct"])):
                out.append(kind)
        elif now_local >= boundary and last < boundary:
            out.append(kind)
    return out


def push_refusal(run, account_ad_account, body, now, size):
    """Why a push from the Mac is not kept, or None. run: the am_link_runs row the pass names (None = unknown)."""
    if run is None:
        return "This link pass isn't known."
    if run["status"] != "open":
        return "This link pass is finished."
    if now - run["created_at"] > RUN_OPEN:
        return "This link pass expired."
    if body.get("kind") not in (run.get("kinds") or []):
        return "This link pass didn't ask for that."
    if digits(body.get("ad_account_id")) != run["ad_account_id"]:
        return "This link pass is for another ad account."
    if digits(account_ad_account) != run["ad_account_id"]:
        return "This account was switched to another ad account after the pass was made."
    if size is not None and size > MAX_PUSH_BYTES:
        return "Meta's answer is too big to keep."
    if body.get("via") not in MODES:
        return "Say how it was read (direct or claude)."
    return None


def _value(v):
    """A kept value: bools, finite numbers, cut strings, short lists of those. Anything else is dropped (None)."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v if math.isfinite(v) else None
    if isinstance(v, str):
        return v[:STR_MAX]
    if isinstance(v, list):
        items = [_value(x) for x in v[:20] if not isinstance(x, (dict, list))]
        return [x for x in items if x is not None]
    return None


def _row(kind, raw):
    out = {}
    for key in FIELDS[kind]:
        if key not in raw:
            continue
        if key == "entity_id":
            ident = digits(raw[key])
            if ident is None:
                return None
            out[key] = ident
            continue
        v = _value(raw[key])
        if v is not None or raw[key] is None:
            out[key] = v
    return out


def normalize(kind, raw):
    """(whitelisted data, None) or (None, why). List kinds → {"rows": [...]}; the context → one object."""
    if kind in NOT_STORED:
        return None, NOT_STORED[kind]
    shape = "Meta's answer had an unexpected shape"
    if kind == "drafts":  # AM-B: the rows themselves go to am_drafts (am_drafts.normalize); this is the read's summary
        import am_drafts
        rows = am_drafts.normalize(raw)
        return (None, shape) if rows is None else ({"drafts": len(rows), "complete": am_drafts.is_complete(raw)}, None)
    if kind not in FIELDS:
        return None, "This isn't something the link reads."
    if kind in OBJECT_KINDS:
        if isinstance(raw, dict):
            inner = next((raw[k] for k in OBJECT_KINDS[kind] if isinstance(raw.get(k), dict)), raw)
            return _row(kind, inner) or {}, None
        return None, shape
    rows = raw if isinstance(raw, list) else next((raw[k] for k in LIST_KEYS[kind] if isinstance(raw, dict) and isinstance(raw.get(k), list)), None)
    if rows is None:
        return None, shape
    kept = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = _row(kind, r)
        if row:
            kept.append(row)
        if len(kept) >= LIST_MAX.get(kind, LIST_DEFAULT):
            break
    return {"rows": kept}, None


def clamp_fetched(fetched_at, run_created, now):
    """When the Mac read it, kept inside [the pass's start − 1 min, now]: a Mac clock can't date data in the future
    or make an old read look fresh."""
    if fetched_at is None:
        return now
    return min(max(fetched_at, run_created - timedelta(minutes=1)), now)


def _age(delta):
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 24 * 60:
        return f"{minutes // 60} h ago"
    days = minutes // (24 * 60)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _when(dt, now, tz):
    at, today = words.local(dt, tz), words.local(now, tz)
    return words.clock(at) if at.date() == today.date() else words.day_time(dt, tz)


def source(fetched_at, link_state, last_pass_at, now, tz, via="direct", kind=None, mac_online=True, reading_on=True):
    """The line under everything the link read: {"words", "fetched_at", "stale", "away"}.
    last_pass_at: when the server last handed this account a pass. "Away" only when the link works, this account is read
    and the Mac really is offline; a login to redo or a switch that is off is named as such, so Eugene checks the right thing."""
    live = link_state in ("connected", "fallback")
    linked = live or link_state in ("expired", "refused")
    away = bool(live and reading_on and not mac_online and last_pass_at is not None and now - last_pass_at > AWAY_AFTER)
    if fetched_at is None:
        text = ("Not read yet: connect the Ads Manager link in Settings." if not linked
                else "Not read yet: reconnect the Ads Manager link in Settings." if not live
                else "Not read yet: reading this account through the Mac is off." if not reading_on
                else "Not read yet: your Mac reads Ads Manager within 15 minutes.")
        return {"words": text, "fetched_at": None, "stale": True, "away": away}
    then = _when(fetched_at, now, tz)
    if link_state == "expired":
        text = f"Reconnect needed in Settings → Ads Manager link; this is from {then}."
    elif link_state == "refused":
        text = f"Meta won't let your Mac's helper in (Settings → Ads Manager link); this is from {then}."
    elif linked and not reading_on:
        text = f"Reading this account through the Mac is off; this is from {then}."
    elif away:
        text = f"Your Mac has been away since {_when(last_pass_at, now, tz)}; this is from then."
    else:
        text = f"From Ads Manager via {'Claude on ' if via == 'claude' else ''}your Mac, {_age(now - fetched_at)}"
        if not linked:
            text += "; the link isn't connected now"
    limit = STALE_DAILY if kind in DAILY_KINDS else AWAY_AFTER
    stale = away or not live or not reading_on or now - fetched_at > limit
    return {"words": text, "fetched_at": fetched_at.isoformat(), "stale": stale, "away": away}


def reading_on(stored, ad_account, is_default):
    """Whether one account is read through the Mac: "on", "off" or "changed" (the owner approved another ad account).
    stored: the account's am_link_on setting, the ad account id the owner approved (digits) or "0". The Mac reads with
    Eugene's own Facebook login, so only an ad account the owner approved is read; his own account (is_default) is read
    until switched off. Changing the account's ad account turns reading off until the owner approves the new one."""
    if not ad_account:
        return "off"
    if stored is None:
        return "on" if is_default else "off"
    approved = digits(stored) if stored not in ("0", "1") else None  # "1": an on switch that named no ad account
    if approved is None:
        return "off"
    return "on" if approved == ad_account else "changed"


ACCOUNT_KEYS = ("account_id", "ad_account_id")
FOREIGN_SCAN = 5000   # nodes looked at before an answer counts as too odd to keep
FOREIGN_DEPTH = 20


def foreign_account(raw, ad_account_id):
    """True when Meta's answer names an ad account other than the pass's anywhere in its account fields (or is too
    deep or big to check): such a push is refused. Text that merely mentions an id is data, not a field."""
    stack, seen = [(raw, 0)], 0
    while stack:
        node, depth = stack.pop()
        seen += 1
        if seen > FOREIGN_SCAN or depth > FOREIGN_DEPTH:
            return True
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ACCOUNT_KEYS and v not in (None, "") and not isinstance(v, (dict, list)):
                    if digits(v) != ad_account_id:
                        return True
                elif isinstance(v, (dict, list)):
                    stack.append((v, depth + 1))
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node if isinstance(v, (dict, list)))
    return False


def keep_own(data, own_ids, ad_account_id):
    """(data, dropped): rows about a campaign, ad set or ad this account doesn't hold are dropped (the ad account itself
    and rows without an entity stay). own_ids: the account's synced campaign, ad set and ad ids."""
    if "rows" not in data:
        return data, 0
    kept = [r for r in data["rows"] if "entity_id" not in r or r["entity_id"] == ad_account_id or r["entity_id"] in own_ids]
    return {**data, "rows": kept}, len(data["rows"]) - len(kept)


STATE_WORDS = {
    "not_connected": "Not connected",
    "connecting": "Waiting for your Mac to open the Facebook page…",
    "connected": "Connected",
    "expired": "Reconnect needed: Meta asked for a new login",
    "refused": "Meta won't let the Mac's helper in",
    "fallback": "Working through Claude on your Mac",
    "off": "Disconnecting: your Mac removes its Facebook login next time it checks in",
}


def link_status_words(state, client_kind=None, fallback_reason=None):
    """The one sentence Settings shows for the link (the reason is shown apart, under "Why")."""
    return STATE_WORDS.get(state, STATE_WORDS["not_connected"])


def link_down(state, since, mac_online, now, hours):
    """The `link_down` alert (console-wide, under account 1), or None. since: the last good pass (else when it connected).
    FYI at first; a warning once it has lasted a day. A Mac that is away is the Mac's matter, not the link's."""
    lasted = int((now - since).total_seconds() // 3600) if since else None
    level = "warn" if lasted is not None and lasted >= 24 else "info"
    if state == "expired":
        return {"level": level, "title": "Ads Manager link: reconnect needed", "measure": lasted,
                "lines": ["Meta asked for a new Facebook login on your Mac. Open Settings → Ads Manager link and press Reconnect."]}
    if state == "refused":
        return {"level": level, "title": "Ads Manager link: Meta won't let your Mac in", "measure": lasted,
                "lines": ["Drafts and Meta's extra numbers aren't being read. Open Settings → Ads Manager link."]}
    if state in ("connected", "fallback") and mac_online and lasted is not None and lasted >= hours:
        return {"level": level, "title": f"Ads Manager hasn't been read for {lasted} hours", "measure": lasted,
                "lines": ["Your Mac is online but its reads of Ads Manager aren't finishing. Open Settings → Ads Manager link and press Check Ads Manager now."]}
    return None


def kind_groups(last, mode, tz, now, kinds=STORED_KINDS):
    """Settings' table of what is read and when: one row for the 15-minute kinds, one for the daily ones."""
    out = []
    for group, members in (("fast", [k for k in kinds if k in FAST_KINDS]), ("daily", [k for k in kinds if k in DAILY_KINDS])):
        if not members:
            continue
        names = [KIND_WORDS[k] for k in members]
        label = names[0][:1].upper() + names[0][1:] + ("" if len(names) == 1 else (", " + ", ".join(names[1:-1]) if len(names) > 2 else "") + f" and {names[-1]}")
        every = (f"every {FAST_MINUTES['direct']} minutes (every {FAST_MINUTES['claude']} through Claude)" if group == "fast"
                 else "once a day")
        times = [last.get(k) for k in members]
        oldest = None if any(t is None for t in times) else min(times)
        out.append({"group": group, "label": label, "every": every, "kinds": members,
                    "last": oldest.isoformat() if oldest else None, "last_words": _when(oldest, now, tz) if oldest else "not read yet"})
    return out
