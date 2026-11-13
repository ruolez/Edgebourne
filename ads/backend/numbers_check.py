"""D1 Match Ads Manager: read older days again from Meta (Meta keeps correcting them), compare our day sums
with Meta's own account totals, and say where every number on a page comes from.

Read-only on Meta: insights GETs only. Nothing here changes an ad, a budget or a status.

The pure part (top) takes everything as arguments; the database part (below) runs inside the account that
account_ctx names, with that account's token and ad account from settings_store, never a module default."""
import json
import time
from datetime import date, datetime, timedelta

import insights
import meta_client
import words

TOLERANCE_CENTS_PER_ROW = 1        # ad-level spend is rounded per ad, the account total once
PART_DAYS = 7
NIGHT_HOUR = 4                      # account time; Meta has settled the day before by then
MAX_PULL_DAYS = 93
OLDEST_MONTHS = 37                  # Meta keeps insights 37 months
CHECK_OLD_HOURS = 36
NIGHT_RETRY_SECONDS = 1800
NIGHT_TRIES = 3
JUDGED_KINDS = ("nightly", "pull", "report")  # runs that read the ad rows again; a check only reads the totals
SLOW_DOWN = "Meta asked us to slow down."


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _days(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def check_window(today):
    """Last month and this month to yesterday, and never fewer than 28 days."""
    y = today - timedelta(days=1)
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    return min(y - timedelta(days=27), last_month), y


def parts(start, end, size=PART_DAYS):
    out = []
    while start <= end:
        out.append((start, min(end, start + timedelta(days=size - 1))))
        start += timedelta(days=size)
    return out


def day_totals(rows):
    """Meta's account rows (level=account, time_increment=1) → {day: {spend_cents, leads, impressions}}, leads counted
    the way the ad rows count them."""
    return {_d(r["date_start"]): {"spend_cents": insights.to_cents(r.get("spend")), "leads": insights.lead_count(r.get("actions")),
                                  "impressions": int(r.get("impressions") or 0)} for r in rows}


def _tolerance(rows):
    return max((rows or 0) * TOLERANCE_CENTS_PER_ROW, 1)


def compare(meta, stored, rows_per_day, newer, start, end):
    """One entry per day: Meta's total, ours, the difference (Meta − here) and the state: match | off | newer (our rows
    were read after Meta's total and differ: judged next check) | unchecked (no Meta total for the day)."""
    out = []
    for d in _days(start, end):
        m, h = meta.get(d), stored.get(d) or {"spend_cents": 0, "leads": 0}
        here = {"spend_cents": int(h.get("spend_cents") or 0), "leads": int(h.get("leads") or 0)}
        if m is None:
            out.append({"day": d, "meta": None, "here": here, "diff_spend_cents": None, "diff_leads": None, "state": "unchecked"})
            continue
        mm = {"spend_cents": int(m.get("spend_cents") or 0), "leads": int(m.get("leads") or 0)}
        ds, dl = mm["spend_cents"] - here["spend_cents"], mm["leads"] - here["leads"]
        same = abs(ds) <= _tolerance(rows_per_day.get(d)) and dl == 0
        out.append({"day": d, "meta": mm, "here": here, "diff_spend_cents": ds, "diff_leads": dl,
                    "state": "match" if same else "newer" if d in newer else "off"})
    return out


def summary(days):
    off = [d for d in days if d["state"] == "off"]
    checked = [d for d in days if d["state"] in ("match", "off", "newer")]
    return {"state": "off" if off else "match" if checked else "unchecked",
            "off_days": [d["day"].isoformat() for d in off],
            "newer_days": [d["day"].isoformat() for d in days if d["state"] == "newer"],
            "spend_off_cents": sum(abs(d["diff_spend_cents"]) for d in off),
            "leads_off": sum(abs(d["diff_leads"]) for d in off),
            "meta_spend_cents": sum(d["meta"]["spend_cents"] for d in checked),
            "meta_leads": sum(d["meta"]["leads"] for d in checked),
            "here_spend_cents": sum(d["here"]["spend_cents"] for d in checked),
            "here_leads": sum(d["here"]["leads"] for d in checked),
            "off": [{"day": d["day"].isoformat(), "meta_spend_cents": d["meta"]["spend_cents"], "meta_leads": d["meta"]["leads"],
                     "here_spend_cents": d["here"]["spend_cents"], "here_leads": d["here"]["leads"]} for d in off[:10]],
            "start": days[0]["day"].isoformat() if days else None, "end": days[-1]["day"].isoformat() if days else None,
            "days": len(days), "checked_days": len(checked)}


def newer_days(synced, fetched, judged_off=()):
    """Days whose ad rows were read after Meta's total for the day (judged at the next check). A day the last verdict
    found off stays off until Meta's total is read again: re-reading our rows alone proves nothing."""
    return {d for d, at in synced.items() if d in fetched and at > fetched[d] and d not in judged_off}


def judge(meta, stored, rows_per_day, synced, fetched, judged_off, start, end):
    """The verdict for [start, end] from what is stored: Meta's totals, our sums and when each was read."""
    return summary(compare(meta, stored, rows_per_day, newer_days(synced, fetched, judged_off), start, end))


def covers(start, end, window):
    """Whether a run that read [start, end] read every day of the check window."""
    return start <= window[0] and end >= window[1]


def _leads(n):
    return f"{n} lead{'s' if n != 1 else ''}"


def _plural_days(n):
    return f"{n} day{'s' if n != 1 else ''}"


def _amount(spend_cents, leads, money, sep=" and "):
    said = ([money(spend_cents)] if spend_cents else []) + ([_leads(leads)] if leads else [])
    return sep.join(said)


def headline(s, money):
    if not s or s.get("state") == "unchecked":
        return "Not checked yet"
    if s["state"] == "match":
        return "Matches Ads Manager"
    return f"Differs by {_amount(s['spend_off_cents'], s['leads_off'], money)} on {_plural_days(len(s['off_days']))}"


def day_list(days, shown=3):
    names = [words.day(_d(d)) for d in days]
    if len(names) > shown:
        return f"{', '.join(names[:shown])} and {len(names) - shown} more"
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def day_line(off, money):
    """One off day in the alert's words."""
    return (f"Ads Manager says {money(off['meta_spend_cents'])} and {_leads(off['meta_leads'])} for {words.day(_d(off['day']))}; "
            f"we have {money(off['here_spend_cents'])} and {off['here_leads']}.")


def restate_plan(stored_keys, fetched, part, meta_days):
    """{"upsert": the fetched rows, "zero": [(day, ad id)]}: rows we have that Meta no longer returns. A row is zeroed only
    when the part returned at least one row and, for its day, the fetched rows add up to Meta's account total: an empty
    or short answer is no proof (the same rule as the `if seen:` guard in sync_ads)."""
    if not fetched:
        return {"upsert": [], "zero": []}
    a, b = part
    by_day = {}
    for r in fetched:
        by_day.setdefault(_d(r["day"]), []).append(r)
    zero = []
    for d, ad in sorted(stored_keys):
        if not (a <= d <= b) or any(r["ad_id"] == ad for r in by_day.get(d, ())):
            continue
        m = meta_days.get(d)
        rows = by_day.get(d, [])
        if m is None:
            continue
        spend = sum(int(r.get("spend_cents") or 0) for r in rows)
        leads = sum(int(r.get("leads") or 0) for r in rows)
        if abs(spend - int(m.get("spend_cents") or 0)) <= _tolerance(len(rows)) and leads == int(m.get("leads") or 0):
            zero.append((d, ad))
    return {"upsert": list(fetched), "zero": zero}


def changes(before, after):
    """[{day, spend_cents, leads}] (after − before) for the days that moved, oldest first."""
    out = []
    zero = {"spend_cents": 0, "leads": 0}
    for d in sorted(set(before) | set(after)):
        b, a = before.get(d) or zero, after.get(d) or zero
        ds, dl = int(a["spend_cents"]) - int(b["spend_cents"]), int(a["leads"]) - int(b["leads"])
        if ds or dl:
            out.append({"day": d.isoformat(), "spend_cents": ds, "leads": dl})
    return out


def _signed(n, text):
    return f"{'+' if n > 0 else '−'}{text}"


def changed_line(changed, money, nightly):
    """"Last night Meta changed 3 older days; we updated them: +2 leads, −$1.10." or None when nothing moved."""
    if not changed:
        return None
    n = len(changed)
    leads, spend = sum(c["leads"] for c in changed), sum(c["spend_cents"] for c in changed)
    said = ([_signed(leads, _leads(abs(leads)))] if leads else []) + ([_signed(spend, money(abs(spend)))] if spend else [])
    head = f"{'Last night ' if nightly else ''}Meta changed {n} older day{'s' if n != 1 else ''}; we updated {'them' if n != 1 else 'it'}"
    head = head[0].upper() + head[1:]
    return f"{head}: {', '.join(said)}." if said else f"{head}."


def window_synced(day_synced):
    """The oldest of the per-day newest reads: every day on screen is at least this fresh."""
    return min(day_synced.values()) if day_synced else None


def freshness(now, last_pull, auto_minutes, last_check):
    limit = max(2 * auto_minutes, 30) * 60
    return {"behind": last_pull is None or now - last_pull > limit,
            "check_old": last_check is None or now - last_check > CHECK_OLD_HOURS * 3600}


def night_due(local, last_night):
    return local.hour >= NIGHT_HOUR and last_night != local.date().isoformat()


def night_should_run(local, last_night, tries, now):
    """Once a night from 4 AM; a failed night is tried again at most every 30 minutes, 3 times, then waits for the next."""
    if not night_due(local, last_night):
        return False
    t = tries if tries and tries.get("day") == local.date().isoformat() else None
    if t and (t.get("n", 0) >= NIGHT_TRIES or now - float(t.get("at") or 0) < NIGHT_RETRY_SECONDS):
        return False
    return True


def off_runs_after(prev, kind, state, covers):
    """Runs in a row that left the check window off (info → warn). `state` is the whole window's verdict after the run.
    Only a run that read every day of the window again counts (a pull of a few days says nothing about the rest); a window
    that matches clears, whatever the run."""
    if state == "match":
        return 0
    if kind in JUDGED_KINDS and covers and state == "off":
        return prev + 1
    return prev


def _months_back(d, months):
    m = d.year * 12 + d.month - 1 - months
    return date(m // 12, m % 12 + 1, 1)


def pull_range(start, end, today):
    """The days to pull again, or the plain reason they can't be."""
    if start > end:
        return "The first day comes after the last"
    if end >= today:
        return "Pick days up to yesterday"
    if start < _months_back(today, OLDEST_MONTHS):
        return "Meta only keeps the last 37 months"
    if (end - start).days + 1 > MAX_PULL_DAYS:
        return f"Pick at most {MAX_PULL_DAYS} days at a time"
    return start, end


def pair(meta_leads, received):
    return {"meta": int(meta_leads), "received": int(received), "differ": int(meta_leads) != int(received)}


def _iso(dt):
    return dt.isoformat() if dt else None


def source_info(*, synced, end, today, check, checked_at, fresh, scope_note, admin, pulled=None):
    """What every figure endpoint returns as `source.meta`. Teammates and clients get the state of the check, never the
    amounts that differ (nothing they can act on)."""
    out = {"synced_at": _iso(synced), "complete_to": min(end, today - timedelta(days=1)).isoformat(), "partial_today": end >= today,
           "behind": fresh["behind"], "pulled_at": _iso(pulled), "check": None}
    if check is not None:
        out["check"] = {"state": check["state"], "checked_at": _iso(checked_at), "off_days": len(check.get("off_days") or []),
                        "old": fresh["check_old"], "checked_days": check.get("checked_days"), "days": check.get("days"),
                        "spend_off_cents": check.get("spend_off_cents") if admin else None,
                        "leads_off": check.get("leads_off") if admin else None}
    return {"meta": out, "scope_note": bool(scope_note)}


def report_stamp(s, checked_at, tz, money, admin):
    """The line under a report's footnotes, and (admins only) the warning above it when days differ."""
    if not s or s.get("state") == "unchecked" or not checked_at:
        return {"state": "unchecked", "text": "Not checked against Meta's own totals yet.", "warning": None, "off_days": []}
    when = words.day_time(checked_at, tz)
    if s["state"] == "match":
        part = s.get("checked_days") is not None and s.get("days") and s["checked_days"] < s["days"]
        what = f"Checked {s['checked_days']} of {s['days']} days against" if part else "Checked against"
        return {"state": "match", "text": f"{what} Meta's own totals on {when}: they match.", "warning": None, "off_days": []}
    out = {"state": "off", "text": f"Checked against Meta's own totals on {when}: a few days are being checked again.",
           "warning": None, "off_days": []}
    if admin:
        each = [f"{words.day(_d(o['day']))} ({_amount(abs(o['meta_spend_cents'] - o['here_spend_cents']), abs(o['meta_leads'] - o['here_leads']), money, ', ')})"
                for o in (s.get("off") or [])[:3]]
        more = len(s["off_days"]) - len(each)
        if more > 0:
            listed = f"{', '.join(each)} and {more} more day{'s' if more != 1 else ''}"
        elif len(each) > 1:
            listed = f"{', '.join(each[:-1])} and {each[-1]}"
        else:
            listed = each[0] if each else ""
        out.update(warning=f"Meta's totals differ for {listed}. Pull these days again before sharing.", off_days=list(s["off_days"]))
    return out


def pull_message(n_days, s, money):
    head = f"Pulled {_plural_days(n_days)} again."
    if not s or s.get("state") == "unchecked":
        return head
    if s["state"] == "match":
        return f"{head} Matches Ads Manager now."
    return (f"{head} Still off by {_amount(s['spend_off_cents'], s['leads_off'], money)} on {day_list(s['off_days'])}: "
            "Meta's totals sometimes settle a day later.")


def _rate(exc):
    return exc.code == "cooldown" or exc.code in meta_client.RATE_CODES


def too_much_data(exc):
    """Meta's "reduce the amount of data you're asking for" refusal of a long ad-level read."""
    return "reduce the amount of data" in f"{exc} {exc.raw}".lower() or (exc.code == 1 and "data" in f"{exc}".lower())


def run_parts(part_list, fetch, plan, write, progress=None):
    """Read and write each part in turn. A part Meta finds too big is read one day at a time, once. Any other Meta error
    stops the run and keeps the finished parts (never retried in a loop). `progress(done, total)` after each part."""
    done, total = 0, len(part_list)
    for part in part_list:
        try:
            try:
                write(plan(part, fetch(part)))
            except meta_client.MetaError as exc:
                if not too_much_data(exc):
                    raise
                for d in _days(*part):
                    write(plan((d, d), fetch((d, d))))
            done += 1
            if progress:
                progress(done, total)
        except meta_client.MetaError as exc:
            reason = SLOW_DOWN if _rate(exc) else str(exc)
            return {"parts_done": done, "parts_total": total, "ok": False, "error": f"Stopped after {done} of {total} parts: {reason}"}
    return {"parts_done": done, "parts_total": total, "ok": True, "error": None}


# ---------------------------------------------------------------- database side

import account_ctx  # noqa: E402
import account_info  # noqa: E402
import db  # noqa: E402
import settings_store  # noqa: E402

ZERO_ROW = ("UPDATE ad_daily SET spend_cents = 0, impressions = 0, reach = 0, link_clicks = 0, leads = 0, clicks_all = 0, "
            "video_3s = 0, thruplays = 0, video_p25 = 0, video_p50 = 0, video_p75 = 0, video_p100 = 0, synced_at = now() "
            "WHERE day = %s AND ad_id = %s")


class Busy(Exception):
    """Another pull from Meta holds this account's lock."""


def connected():
    return bool(settings_store.get("meta_system_token") and settings_store.get("meta_ad_account_id"))


def money_words():
    currency = account_info.currency()
    return lambda c: words.money(c, currency)


def read_meta_totals(start, end):
    """Meta's own account total for every day from start to end (one call), stored; a day Meta leaves out had nothing."""
    account = settings_store.get("meta_ad_account_id")
    got = day_totals(meta_client.paged(f"act_{account}/insights", level="account", time_increment=1, fields="spend,impressions,actions",
                                       limit=500, time_range=json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
                                       **insights.insight_params()))
    zero = {"spend_cents": 0, "leads": 0, "impressions": 0}
    out = {d: got.get(d, zero) for d in _days(start, end)}
    days = list(out)
    db.execute("""INSERT INTO meta_day_totals (day, spend_cents, leads, impressions, fetched_at)
                  SELECT d, s, l, i, now() FROM unnest(%s::date[], %s::bigint[], %s::int[], %s::bigint[]) AS t(d, s, l, i)
                  ON CONFLICT (account_id, day) DO UPDATE SET spend_cents = EXCLUDED.spend_cents, leads = EXCLUDED.leads,
                      impressions = EXCLUDED.impressions, fetched_at = EXCLUDED.fetched_at""",
               (days, [out[d]["spend_cents"] for d in days], [out[d]["leads"] for d in days], [out[d]["impressions"] for d in days]))
    return out


def stored_totals(start, end):
    """(our sums per day, rows with spend per day, newest read per day) from ad_daily, the whole account (RLS scopes it)."""
    stored, rows, synced = {}, {}, {}
    for r in db.query("""SELECT day, SUM(spend_cents) AS s, SUM(leads) AS l, COUNT(*) FILTER (WHERE spend_cents > 0) AS n,
                                MAX(synced_at) AS at FROM ad_daily WHERE day BETWEEN %s AND %s GROUP BY day""", (start, end)):
        stored[r["day"]] = {"spend_cents": int(r["s"] or 0), "leads": int(r["l"] or 0)}
        rows[r["day"]] = int(r["n"])
        if r["at"]:
            synced[r["day"]] = r["at"]
    return stored, rows, synced


def meta_totals(start, end):
    meta, fetched = {}, {}
    for r in db.query("SELECT day, spend_cents, leads, fetched_at FROM meta_day_totals WHERE day BETWEEN %s AND %s", (start, end)):
        meta[r["day"]] = {"spend_cents": int(r["spend_cents"]), "leads": int(r["leads"])}
        fetched[r["day"]] = r["fetched_at"]
    return meta, fetched


def verdict():
    """The account-wide verdict after the newest finished run: {run_id, kind, summary} of the whole check window."""
    raw = settings_store.get("numbers_window")
    return json.loads(raw) if raw else None


def _judged_off():
    v = verdict()
    return {_d(d) for d in ((v or {}).get("summary") or {}).get("off_days") or []}


def current(start=None, end=None):
    if start is None:
        start, end = check_window(account_info.today())
    stored, rows, synced = stored_totals(start, end)
    meta, fetched = meta_totals(start, end)
    return compare(meta, stored, rows, newer_days(synced, fetched, _judged_off()), start, end)


def running():
    """A run still reading from Meta (started in the last 15 minutes: an older one died with its process)."""
    return db.query("""SELECT * FROM numbers_runs WHERE finished_at IS NULL AND started_at > now() - interval '15 minutes'
                       ORDER BY id DESC LIMIT 1""", one=True)


def last_run(ok_only=False, kinds=None):
    return db.query(f"""SELECT r.*, u.name AS by_name FROM numbers_runs r LEFT JOIN users u ON u.id = r.user_id
                        WHERE r.finished_at IS NOT NULL {"AND r.ok" if ok_only else ""}
                        {"AND r.kind = ANY(%s)" if kinds else ""} ORDER BY r.id DESC LIMIT 1""",
                    (list(kinds),) if kinds else None, one=True)


def _start_run(kind, start, end, user_id):
    return db.execute("INSERT INTO numbers_runs (kind, start_day, end_day, user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                      (kind, start, end, user_id), returning=True)["id"]


def _finish(run_id, kind, ok, error=None, parts_done=0, parts_total=0, changed=None, s=None, span=None):
    """Close the run. A run that finished also renews the account-wide verdict: the whole check window as stored now
    (a pull of a few days never stands in for the rest), and how many runs in a row left it off."""
    row = db.execute("""UPDATE numbers_runs SET finished_at = now(), ok = %s, error = %s, parts_done = %s, parts_total = %s,
                               changed = %s, summary = %s WHERE id = %s RETURNING *""",
                     (ok, error, parts_done, parts_total, json.dumps(changed) if changed is not None else None,
                      json.dumps(s) if s is not None else None, run_id), returning=True)
    if ok and s:
        window = check_window(account_info.today())
        ws = summary(current(*window))
        settings_store.set("numbers_window", json.dumps({"run_id": run_id, "kind": kind, "summary": ws}))
        prev = int(settings_store.get("numbers_off_runs") or 0)
        settings_store.set("numbers_off_runs", str(off_runs_after(prev, kind, ws["state"], covers(*(span or window), window))))
    return row


def _progress(run_id):
    def told(done, total):
        db.execute("UPDATE numbers_runs SET parts_done = %s, parts_total = %s WHERE id = %s", (done, total, run_id))
    return told


def restate(start, end, kind, user_id=None):
    """Read [start, end] again from Meta: the account totals (one call), then each 7-day part at ad level, written over
    the stored rows (and rows Meta no longer returns zeroed, under restate_plan's guard). Returns the finished run."""
    import refresh_api
    with refresh_api.holding_pull_lock(account_ctx.current()) as got:
        if not got:
            raise Busy()
        run_id = _start_run(kind, start, end, user_id)
        try:
            before, _, _ = stored_totals(start, end)
            try:
                meta = read_meta_totals(start, end)
            except meta_client.MetaError as exc:
                return _finish(run_id, kind, False, SLOW_DOWN if _rate(exc) else f"Couldn't read Meta's totals: {exc}")
            part_list = parts(start, end)

            def fetch(part):
                return insights.read_days(*part)

            def plan(part, rows):
                keys = {(r["day"], r["ad_id"]) for r in db.query("SELECT day, ad_id FROM ad_daily WHERE day BETWEEN %s AND %s", part)}
                return restate_plan(keys, rows, part, meta)

            def write(p):
                if not p["upsert"] and not p["zero"]:
                    return
                with db.transaction() as cur:
                    for v in p["upsert"]:
                        cur.execute(insights.UPSERT_DAILY, insights.daily_params(v))
                    for d, ad in p["zero"]:
                        cur.execute(ZERO_ROW, (d, ad))
            told = _progress(run_id)
            told(0, len(part_list))
            res = run_parts(part_list, fetch, plan, write, progress=told)
            # The rows just written are newer than the totals read before them: stamp the totals again, so the days this
            # run read are judged now (a day whose ad rows don't add up to Meta's own total is off, not "updated since").
            db.execute("UPDATE meta_day_totals SET fetched_at = now() WHERE day BETWEEN %s AND %s", (start, end))
            after, _, _ = stored_totals(start, end)
            return _finish(run_id, kind, res["ok"], res["error"], res["parts_done"], res["parts_total"], changes(before, after),
                           summary(current(start, end)), span=(start, end))
        except Exception as exc:
            _finish(run_id, kind, False, "Something went wrong while reading Meta. It will be tried again.")
            raise exc


def check(user_id=None):
    """Meta's account totals only (one call) for the check window, and the comparison. No ad rows are read."""
    start, end = check_window(account_info.today())
    run_id = _start_run("check", start, end, user_id)
    try:
        read_meta_totals(start, end)
    except meta_client.MetaError as exc:
        return _finish(run_id, "check", False, SLOW_DOWN if _rate(exc) else str(exc))
    return _finish(run_id, "check", True, s=summary(current(start, end)), span=(start, end))


def run_nightly():
    """The worker, once a night per account after 4 AM: read the check window again and compare. Returns the run, or None."""
    if settings_store.get("numbers_check") == "0" or not connected() or meta_client.cooling_until():
        return None
    local = account_info.local_now()
    raw = settings_store.get("numbers_night_try")
    tries = json.loads(raw) if raw else None
    if not night_should_run(local, settings_store.get("numbers_last_night"), tries, time.time()):
        return None
    try:
        run = restate(*check_window(local.date()), "nightly")
    except Busy:
        return None  # a pull holds the lock: the next pass tries
    if run and run["ok"]:
        settings_store.set("numbers_last_night", local.date().isoformat())
        settings_store.set("numbers_night_try", None)
    else:
        n = (tries or {}).get("n", 0) if (tries or {}).get("day") == local.date().isoformat() else 0
        settings_store.set("numbers_night_try", json.dumps({"day": local.date().isoformat(), "n": n + 1, "at": time.time()}))
    return run


def ensure_period(start, end):
    """Before a report is frozen (W2's claim step): pull the period again unless a run that read its days finished after
    the period ended. A failure never blocks the email; the stamp says what is known."""
    if not connected():
        return None
    today = account_info.today()
    end = min(end, today - timedelta(days=1))
    if start > end or isinstance(pull_range(start, end, today), str):
        return None
    covered = db.query("""SELECT 1 FROM numbers_runs WHERE ok AND kind = ANY(%s) AND start_day <= %s AND end_day >= %s
                          AND (finished_at AT TIME ZONE %s)::date > %s LIMIT 1""",
                       (list(JUDGED_KINDS), start, end, account_info.tz_name(), end), one=True)
    if covered:
        return None
    try:
        return restate(start, end, "report")
    except Busy:
        return None


def source(user, start, end, meta_leads=None, received=None, scoped=False):
    """The `source` every figure endpoint carries: when its days were read from Meta, how far they are complete, whether
    they match Ads Manager's own totals, and Meta's lead count next to the leads received."""
    import refresh_api
    today = account_info.today()
    y = today - timedelta(days=1)
    stored, rows, synced = stored_totals(start, end)
    check_, checked_at = None, None
    if start <= y:
        meta, fetched = meta_totals(start, min(end, y))
        if meta:
            check_ = judge(meta, stored, rows, synced, fetched, _judged_off(), start, min(end, y))
            checked_at = max(fetched.values())
    pulled = refresh_api.last_updated(settings_store.get("last_refresh_at"), settings_store.get("last_performance_sync"))
    fresh = freshness(time.time(), pulled, refresh_api.auto_minutes(settings_store.get("auto_refresh_minutes")),
                      checked_at.timestamp() if checked_at else None)
    from datetime import timezone
    out = source_info(synced=window_synced({d: at for d, at in synced.items() if d <= y}) or window_synced(synced), end=end, today=today,
                      check=check_, checked_at=checked_at, fresh=fresh, scope_note=scoped, admin=user["role"] == "admin",
                      pulled=datetime.fromtimestamp(pulled, timezone.utc) if pulled else None)
    if meta_leads is not None and received is not None:
        out["leads"] = pair(meta_leads, received)
    return out


def stamp_for(start, end, admin):
    """The report's stamp for its period (W2 freezes it into the copy that goes out)."""
    y = account_info.today() - timedelta(days=1)
    end = min(end, y)
    s, checked_at = None, None
    if start <= end:
        stored, rows, synced = stored_totals(start, end)
        meta, fetched = meta_totals(start, end)
        if meta:
            s = judge(meta, stored, rows, synced, fetched, _judged_off(), start, end)
            checked_at = max(fetched.values())  # when this period's days were last compared, not any check's
    return report_stamp(s, checked_at, account_info.tz(), money_words(), admin)
