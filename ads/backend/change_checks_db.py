"""Did it work? (D3), the database side: reads a change, its scope's daily results and lead stages, works out
the 3-, 7- and 14-day results with change_checks (pure) and keeps them in `change_checks`. The worker recomputes
them until final and tells the Inbox. Read-only towards Meta: no Meta call, no Meta write."""
import json
import logging
from datetime import datetime, timedelta, timezone

import account_info
import change_checks as cc
import creative_versions
import db
import lead_quality as lq
import links
import settings_store
import status_history
import targets
import words

log = logging.getLogger(__name__)

BACKFILL_DAYS = 35
MAX_PER_PASS = 300
TABLE = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
COLUMN = {"campaign": "campaign_id", "adset": "adset_id", "ad": "ad_id"}
LEVEL_WORDS = {"campaign": "campaign", "adset": "ad set", "ad": "ad"}


def _money_whole(cents):
    return account_info.money(cents, whole=True)


def _money_exact(cents):
    """Whole dollars when there are no cents ("$40"), else exact ("$35.50")."""
    return account_info.money(cents, whole=not cents % 100) if cents is not None else "—"


def _local_day(at, tz):
    return at.astimezone(tz).date()


# ---------------------------------------------------------------- reads

def load_change(change_id):
    return db.query("""SELECT m.*, u.name AS user_name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                       WHERE m.id = %s""", (change_id,), one=True)


def entity_now(level, entity_id):
    """The entity as stored now, or None when it isn't (deleted from the console's copy)."""
    if level == "ad":
        sql = "SELECT 'ad' AS level, id, name, adset_id, campaign_id, status, effective_status, creative_id FROM ads WHERE id = %s"
    elif level == "adset":
        sql = ("SELECT 'adset' AS level, id, name, NULL AS adset_id, campaign_id, status, effective_status, daily_budget_cents "
               "FROM adsets WHERE id = %s")
    elif level == "campaign":
        sql = ("SELECT 'campaign' AS level, id, name, NULL AS adset_id, id AS campaign_id, status, effective_status, daily_budget_cents "
               "FROM campaigns WHERE id = %s")
    else:
        return None
    return db.query(sql, (entity_id,), one=True)


def _versions(ad, today, tz_name):
    rows = db.query("""SELECT number, creative_id, label, started_at, started_on FROM ad_versions WHERE ad_id = %s ORDER BY number""",
                    (ad["id"],))
    if not rows:
        return []
    ready = db.query("""SELECT at, (at AT TIME ZONE %s)::date AS day FROM status_events
                        WHERE level = 'ad' AND entity_id = %s AND field = 'effective_status' AND new_value = 'ACTIVE'
                          AND old_value IN ('IN_PROCESS', 'PENDING_REVIEW') ORDER BY at""", (tz_name, ad["id"]))
    return creative_versions.with_live_days(rows, ready, today, ad.get("effective_status") in creative_versions.REVIEW_STATES)


def _live_day(change, versions, first):
    """For a new version: the day Meta approved it (its results start the day after)."""
    made = cc.CREATIVE.search(str(change.get("new_value") or ""))
    hit = [v for v in versions if made and str(v["creative_id"]) == made.group(1) and v.get("started_on")]
    if not hit or not hit[-1].get("live_on"):
        return first
    return max(first, hit[-1]["live_on"])


def _family(scope_level, scope_id):
    """The scope with its parents: (ad, adset, campaign) ids, as far as known."""
    row = entity_now(scope_level, scope_id) or {}
    if scope_level == "ad":
        return scope_id, row.get("adset_id"), row.get("campaign_id")
    if scope_level == "adset":
        return None, scope_id, row.get("campaign_id")
    return None, None, scope_id


def _neighbours(change, scope_level, scope_id, lo, hi):
    """Other changes on the scope, its parents or its children between lo and hi: console changes that are
    checked, and changes made in Ads Manager (D2's status_events). [(at, source)]."""
    ad, adset, camp = _family(scope_level, scope_id)
    ids = [i for i in (ad, adset, camp) if i]
    if scope_level == "campaign":
        m_where, e_where, params = "(m.entity_id = %(c)s OR m.campaign_id = %(c)s)", "(e.entity_id = %(c)s OR e.campaign_id = %(c)s)", {"c": camp}
    elif scope_level == "adset":
        m_where = "(m.entity_id = ANY(%(ids)s) OR m.entity_id IN (SELECT id FROM ads WHERE adset_id = %(s)s))"
        e_where, params = "(e.entity_id = ANY(%(ids)s) OR e.adset_id = %(s)s)", {"ids": ids, "s": adset}
    else:
        m_where, e_where, params = "m.entity_id = ANY(%(ids)s)", "e.entity_id = ANY(%(ids)s)", {"ids": ids}
    params.update(lo=lo, hi=hi, me=change["id"], actions=sorted(cc.CHECKED), fields=list(status_history.OUTSIDE_FIELDS))
    console = db.query(f"""SELECT m.created_at AS at FROM meta_changes m WHERE {m_where} AND m.ok AND m.id <> %(me)s
                           AND m.action = ANY(%(actions)s) AND m.created_at BETWEEN %(lo)s AND %(hi)s""", params)
    outside = db.query(f"""SELECT e.at FROM status_events e WHERE {e_where} AND e.source IN ('poll', 'webhook')
                           AND e.field = ANY(%(fields)s) AND e.at BETWEEN %(lo)s AND %(hi)s""", params)
    return [(r["at"], "console") for r in console] + [(r["at"], "outside") for r in outside]


def _daily(scope_level, scope_id, start, end, tz_name):
    col = COLUMN[scope_level]
    rows = {r["day"]: dict(r) for r in db.query(
        f"""SELECT day, COALESCE(SUM(spend_cents), 0) AS spend_cents, COALESCE(SUM(leads), 0) AS leads,
                   COALESCE(SUM(impressions), 0) AS impressions
            FROM ad_daily WHERE {col} = %s AND day BETWEEN %s AND %s GROUP BY day""", (scope_id, start, end))}
    for r in db.query(f"""SELECT (created_time AT TIME ZONE %s)::date AS day, COUNT(*) FILTER (WHERE {lq.qualified()}) AS qualified
                          FROM leads l WHERE {lq.counted()} AND l.{col} = %s
                            AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s GROUP BY 1""",
                      (tz_name, scope_id, tz_name, start, end)):
        rows.setdefault(r["day"], {"day": r["day"], "spend_cents": 0, "leads": 0, "impressions": 0})["qualified"] = int(r["qualified"])
    return list(rows.values())


def _synced_day(tz):
    raw = settings_store.get("last_performance_sync")
    try:
        at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _local_day(at if at.tzinfo else at.replace(tzinfo=timezone.utc), tz)


def context():
    """What every change of a pass shares (read once per pass, not per change)."""
    tz = account_info.tz()
    return {"tz": tz, "tz_name": account_info.tz_name(), "today": account_info.today(), "q": targets.qualified(),
            "l": targets.lead(), "currency": account_info.currency(), "synced": _synced_day(tz),
            "tests": db.query("SELECT id, name, status, arms FROM experiments WHERE status = 'running'")}


def _test_running(change, entity, exps):
    if change["level"] not in ("ad", "adset") or not exps:
        return False
    import experiments
    ad_id = change["entity_id"] if change["level"] == "ad" else ""
    adset_id = (entity or {}).get("adset_id") if change["level"] == "ad" else change["entity_id"]
    return bool(experiments.containing(exps, ad_id, adset_id))


def _expect_of(change):
    if not change.get("proposal_id"):
        return None, None
    p = db.query("SELECT expect, expected FROM desk_proposals WHERE id = %s", (change["proposal_id"],), one=True)
    return (p["expect"], p["expected"]) if p else (None, None)


# ---------------------------------------------------------------- compute

def _range(w, side):
    span = w.get(side)
    return (span[0], span[1]) if span else (None, None)


def _notes(change, mode, w, judged, cut_outside, q_target, final, after_end, tz_day, stale, testing):
    out = []
    keys = (judged or {}).get("notes") or []
    if change["action"] == "budget":
        try:
            if int(change["new_value"]) > int(change["old_value"]) * 1.2:
                out.append("The change was bigger than +20%: Meta relearned for 3 days, so the first days are rough.")
        except (TypeError, ValueError):
            pass
    if "qualified_short" in keys and judged["state"] != "too_early":
        out.append("Too few qualified leads on one side yet, so this compares cost per lead.")
    if "before_short" in keys:
        out.append("The days before the change don't have enough data yet.")
    if q_target and after_end and not final and judged and judged["state"] not in ("too_early", "stopped", "not_running"):
        out.append(f"Qualified leads can still go up while the team works the leads (until {tz_day(after_end + timedelta(days=cc.SETTLE_DAYS))}).")
    if w.get("cut_by") and cut_outside:
        out.append(f"Changed in Ads Manager on {tz_day(w['cut_by'])}.")
    elif w.get("cut_by") and w["days"]:
        out.append(f"Changed again on {tz_day(w['cut_by'])}, so each side has {w['days']} day{'' if w['days'] == 1 else 's'}.")
    if testing:
        out.append(f"A test is running on this {LEVEL_WORDS[change['level']]}. See Tests for its verdict.")
    if stale:
        out.append("Waiting for Meta's numbers.")
    return out


def compute(change_id, today=None, ctx=None):
    """Works out and stores the three horizons of one change. Returns the rows (empty when it isn't checked)."""
    ctx = ctx or context()
    change = load_change(change_id)
    if not change:
        return []
    entity = entity_now(change["level"], change["entity_id"]) or {
        "level": change["level"], "id": change["entity_id"], "campaign_id": change.get("campaign_id"), "adset_id": None}
    picked = cc.mode_for(change, entity)
    if not picked:
        return []
    mode, scope_level, scope_id = picked
    tz, tz_name = ctx["tz"], ctx["tz_name"]
    today = today or ctx["today"]
    first = _local_day(change["created_at"], tz)
    last = first
    if mode == "version":
        last = _live_day(change, _versions(entity, today, tz_name), first)
    lo, hi = change["created_at"] - timedelta(days=16), change["created_at"] + timedelta(days=16 + (last - first).days)
    around = _neighbours(change, scope_level, scope_id, lo, hi)
    earlier = [(_local_day(at, tz), src) for at, src in around if at < change["created_at"] and _local_day(at, tz) < first]
    later = [(_local_day(at, tz), src) for at, src in around if at > change["created_at"]]
    prev = max(earlier)[0] if earlier else None
    nxt = min(later)[0] if later else None
    cut_outside = bool(nxt) and any(d == nxt and src == "outside" for d, src in later)
    daily = _daily(scope_level, scope_id, first - timedelta(days=max(cc.HORIZONS)), min(last + timedelta(days=max(cc.HORIZONS)),
                                                                                           today - timedelta(days=1)), tz_name)
    q_target, l_target, currency, synced = ctx["q"], ctx["l"], ctx["currency"], ctx["synced"]
    expect_raw, expected_text = _expect_of(change)
    expect = cc.clean_expect(expect_raw) if isinstance(expect_raw, dict) else None
    testing = _test_running(change, entity, ctx["tests"])
    yesterday = today - timedelta(days=1)
    rows = []
    for h in cc.HORIZONS:
        w = cc.windows(first, last, today, h, prev_change=None if mode == "new" else prev,
                       next_change=None if mode == "stopped" else nxt)
        if mode == "stopped":
            w["complete"] = True
        b_start, b_end = _range(w, "before")
        a_start, a_end = _range(w, "after")
        judged, before, after, stale = None, None, None, False
        if mode != "stopped" and not w["days"]:
            state = "mixed"
            if not w.get("cut_by"):
                w["cut_by"] = prev
        elif not w["complete"]:
            state = "waiting"
        elif mode != "stopped" and (synced is None or synced <= a_end):
            state, stale = "waiting", True
        else:
            before = cc.totals(daily, b_start, b_end) if b_start and mode != "new" else None
            after = cc.totals(daily, a_start, a_end) if a_start and mode != "stopped" else None
            judged = cc.judge(mode, before, after, q_target, l_target, currency)
            state = judged["state"]
        final = state not in ("waiting",) and ((a_end is not None and yesterday >= a_end + timedelta(days=cc.SETTLE_DAYS))
                                               or (state in cc.SETTLED and w["complete"]))
        check = {"state": state, "metric": (judged or {}).get("metric") or "cpl_cents", "days": w["days"],
                 "before": (judged or {}).get("before"), "after": (judged or {}).get("after"),
                 "delta_pct": (judged or {}).get("delta_pct"), "needs": (judged or {}).get("needs"),
                 "notes": (judged or {}).get("notes") or (["stale"] if stale else []), "cut_by": w.get("cut_by"), "changed_on": first,
                 "ready_on": w["ready_on"], "target_cents": (judged or {}).get("target_cents") or l_target,
                 "after_ready": (judged or {}).get("after_ready") or {}}
        row = {"change_id": change["id"], "horizon": h, "mode": mode, "scope_level": scope_level, "scope_id": scope_id,
               "state": state, "metric": check["metric"] if judged else None,
               "before_start": b_start, "before_end": b_end, "after_start": a_start, "after_end": a_end,
               "before_totals": check["before"], "after_totals": check["after"], "after_ready": check["after_ready"],
               "delta_pct": check["delta_pct"], "confidence": (judged or {}).get("confidence"), "needs": check["needs"],
               "target_cents": check["target_cents"] if judged else None, "days": w["days"], "cut_by": w.get("cut_by"),
               "sentence": cc.sentence(check, _money_whole, words.day),
               "notes": _notes(change, mode, w, judged, cut_outside, q_target, final, a_end, words.day, stale, testing),
               "expect_met": cc.expectation_met(expect, check) if expect and expect["days"] == h else None,
               "ready_on": w["ready_on"], "final": bool(final)}
        rows.append(row)
    _store(rows)
    for r in rows:
        r["expect"], r["expected_text"] = expect, expected_text
    return rows


COLS = ("change_id", "horizon", "mode", "scope_level", "scope_id", "state", "metric", "before_start", "before_end", "after_start",
        "after_end", "before_totals", "after_totals", "after_ready", "delta_pct", "confidence", "needs", "target_cents", "days",
        "cut_by", "sentence", "notes", "expect_met", "ready_on", "final")
JSON_COLS = ("before_totals", "after_totals", "after_ready", "notes")


def _store(rows):
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c not in ("change_id", "horizon"))
    for r in rows:
        values = [json.dumps(r[c]) if c in JSON_COLS and r[c] is not None else r[c] for c in COLS]
        db.execute(f"""INSERT INTO change_checks ({', '.join(COLS)}, computed_at) VALUES ({', '.join(['%s'] * len(COLS))}, now())
                       ON CONFLICT (account_id, change_id, horizon) DO UPDATE SET {sets}, computed_at = now()""", values)


# ---------------------------------------------------------------- reading results

def stored(change_ids):
    if not change_ids:
        return {}
    out = {}
    for r in db.query("SELECT * FROM change_checks WHERE change_id = ANY(%s) ORDER BY change_id, horizon", (list(change_ids),)):
        out.setdefault(r["change_id"], []).append(r)
    return out


def undone_by(change_ids):
    """{change id: {at, by, words}} for changes a later Put it back reversed."""
    if not change_ids:
        return {}
    tz = account_info.tz()
    out = {}
    for r in db.query("""SELECT m.undo_of, m.created_at, u.name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                         WHERE m.ok AND m.undo_of = ANY(%s) ORDER BY m.id""", (list(change_ids),)):
        if r["undo_of"] not in out:
            day = words.day(_local_day(r["created_at"], tz))
            out[r["undo_of"]] = {"at": r["created_at"].isoformat(), "by": r["name"],
                                 "words": f"Put back on {day}" + (f" by {r['name']}" if r["name"] else "")}
    return out


def _iso(d):
    return d.isoformat() if d else None


def row_public(r):
    """One horizon as the API shows it."""
    span = lambda s, e: {"start": _iso(s), "end": _iso(e), "label": words.day(s) if s == e else f"{words.day(s)} – {words.day(e)}"} if s else None  # noqa: E731
    return {"horizon": r["horizon"], "state": r["state"], "word": cc.OUTCOME[r["state"]], "sentence": r["sentence"],
            "metric": r["metric"], "days": r["days"], "before_span": span(r["before_start"], r["before_end"]),
            "after_span": span(r["after_start"], r["after_end"]), "before": r["before_totals"], "after": r["after_totals"],
            "delta_pct": r["delta_pct"], "confidence": r["confidence"], "needs": r["needs"], "notes": r["notes"] or [],
            "ready_on": _iso(r["ready_on"]), "ready_label": words.day(r["ready_on"]) if r["ready_on"] else None,
            "expect_met": r["expect_met"], "final": r["final"], "worse": r["state"] in cc.WORSE, "target_cents": r["target_cents"]}


def plan_for(change):
    """Put it back for one change: {plan, reason}."""
    now = entity_now(change["level"], change["entity_id"])
    versions = []
    if change["action"] in ("update_creative", "restore_creative") and now:
        versions = db.query("SELECT number, creative_id FROM ad_versions WHERE ad_id = %s ORDER BY number", (change["entity_id"],))
    return cc.undo_plan(change, now, versions, account_info.money)


def summary_for(change_ids, client=False):
    """{change id: {state, word, sentence, ready_on, worse, horizon, put_back, can_undo}}: the headline of each change
    that has a result, for History and Claude's page. Read-only."""
    rows = stored(change_ids)
    if not rows:
        return {}
    undone = undone_by(list(rows))
    worse = [cid for cid, rs in rows.items() if cc.headline(rs)["state"] in cc.WORSE and cid not in undone]
    changes = {c["id"]: c for c in db.query("SELECT * FROM meta_changes WHERE id = ANY(%s)", (worse,))} if worse and not client else {}
    out = {}
    for cid, rs in rows.items():
        h = cc.headline(rs)
        out[cid] = {"state": h["state"], "word": cc.OUTCOME[h["state"]], "sentence": h["sentence"], "horizon": h["horizon"],
                    "ready_on": _iso(h["ready_on"]), "worse": h["state"] in cc.WORSE,
                    "put_back": (undone.get(cid) or {}).get("words"),
                    "can_undo": bool(cid in changes and plan_for(changes[cid])["plan"])}
    return out


def proposal_checks(proposals):
    """Claude's applied suggestions: the result of the change each one made, with what Claude expected and whether it
    was met ({proposal id: check})."""
    pids = [p["id"] for p in proposals if p.get("status") == "applied"]
    if not pids:
        return {}
    made = db.query("""SELECT DISTINCT ON (proposal_id) id, proposal_id FROM meta_changes
                       WHERE ok AND proposal_id = ANY(%s) AND action = ANY(%s) ORDER BY proposal_id, id""", (pids, sorted(cc.CHECKED)))
    if not made:
        return {}
    by_change = summary_for([m["id"] for m in made])
    rows = stored([m["id"] for m in made])
    expects = {p["id"]: p for p in proposals}
    out = {}
    for m in made:
        if m["id"] not in by_change:
            continue
        check = {**by_change[m["id"]], "change_id": m["id"]}
        p = expects.get(m["proposal_id"]) or {}
        expect = cc.clean_expect(p.get("expect")) if isinstance(p.get("expect"), dict) else None
        if expect:
            row = next((r for r in rows[m["id"]] if r["horizon"] == expect["days"]), None)
            got = cc.got_words(expect, _check_of(row), _money_exact) if row and row["state"] != "waiting" else None
            check.update(expected=cc.expect_words(expect, _money_exact), got=got, expect_met=row["expect_met"] if row else None)
        elif p.get("expected"):
            check.update(expected_text=p["expected"])
        out[m["proposal_id"]] = check
    return out


def _check_of(row):
    return {"days": row["days"], "after": row["after_totals"] or {}, "after_ready": row["after_ready"] or {}}


# ---------------------------------------------------------------- Inbox

def _alert_for(change, rows):
    h = cc.headline(rows)
    cls = cc.state_class(h["state"]) if h else None
    if not cls:
        return None
    name = (entity_now(change["level"], change["entity_id"]) or {}).get("name") or change.get("entity_name") or change["entity_id"]
    lines = [h["sentence"]]
    if h["before_start"] and h["after_start"]:
        lines.append(f"Before {_label(h['before_start'], h['before_end'])} · After {_label(h['after_start'], h['after_end'])}")
    elif h["after_start"]:
        lines.append(f"Its first days: {_label(h['after_start'], h['after_end'])}")
    bad = cls == "bad"
    return {"rule": "change_result", "key": f"change_result:{change['id']}:{cls}", "level": "warn" if bad else "info",
            "title": cc.alert_title(change, name, h["state"]), "lines": lines, "entity_id": change["entity_id"],
            "campaign_id": change.get("campaign_id"), "href": links.history_href(change["level"], change["entity_id"], check=change["id"]),
            "kind": "event", "resolved": not bad, "measure": None}


def _label(s, e):
    return words.day(s) if s == e else f"{words.day(s)} – {words.day(e)}"


def raise_results(change, rows):
    """One Inbox item per change and kind of result (good / bad / flat). "Didn't help" stays open until put back or
    Done and is emailed like other alerts; good and flat results are FYI."""
    import alerts
    if not (alerts.saved_rules().get("change_result") or {}).get("on", True):
        return []
    if undone_by([change["id"]]):
        return []
    a = _alert_for(change, rows)
    return alerts.raise_found([a]) if a else []


def close_put_back(change_id):
    """Put it back done: the change's "didn't help" item leaves Needs action."""
    db.execute("""UPDATE alerts SET resolved_at = now() WHERE rule = 'change_result' AND resolved_at IS NULL
                  AND dedupe_key LIKE %s""", (f"change_result:{int(change_id)}:%",))


def run(today=None):
    """Worker: checks changes from the last 35 days that have none yet and every result that isn't final, oldest
    first, and tells the Inbox. Returns how many changes it looked at."""
    ids = [r["id"] for r in db.query(
        """SELECT id FROM (
               SELECT m.id FROM meta_changes m
               WHERE m.ok AND m.action = ANY(%s) AND m.level IN ('campaign', 'adset', 'ad')
                 AND m.created_at > now() - %s * interval '1 day'
                 AND NOT EXISTS (SELECT 1 FROM change_checks c WHERE c.change_id = m.id)
               UNION SELECT DISTINCT change_id FROM change_checks WHERE NOT final) x
           ORDER BY id LIMIT %s""", (sorted(cc.CHECKED), BACKFILL_DAYS, MAX_PER_PASS))]
    ctx = context()
    for cid in ids:
        try:
            rows = compute(cid, today, ctx)
            if rows:
                raise_results(load_change(cid), rows)
        except Exception:
            log.exception("did it work: change %s failed", cid)
    db.execute("""UPDATE alerts a SET resolved_at = now() WHERE a.rule = 'change_result' AND a.resolved_at IS NULL
                  AND EXISTS (SELECT 1 FROM meta_changes m WHERE m.ok AND m.undo_of::text = split_part(a.dedupe_key, ':', 2))""")
    return len(ids)


# ---------------------------------------------------------------- Claude on the Mac

def _by(c):
    return "claude" if c.get("proposal_id") else "bulk" if c.get("bulk_id") else "console"


def outcomes(days=60, limit=100):
    """What happened after each checked change (newest first), and Claude's suggestions that were declined or sent
    back. Numbers and words only: no lead names, emails or phones."""
    changes = db.query("""SELECT m.id, m.created_at, m.level, m.entity_id, m.entity_name, m.action, m.old_value, m.new_value,
                                 m.proposal_id, m.bulk_id
                          FROM meta_changes m WHERE m.ok AND m.created_at > now() - %s * interval '1 day'
                            AND EXISTS (SELECT 1 FROM change_checks c WHERE c.change_id = m.id)
                          ORDER BY m.id DESC LIMIT %s""", (days, limit))
    rows = stored([c["id"] for c in changes])
    undone = undone_by([c["id"] for c in changes])
    pids = [c["proposal_id"] for c in changes if c["proposal_id"]]
    props = {p["id"]: p for p in db.query("SELECT id, title, kind, expected, expect FROM desk_proposals WHERE id = ANY(%s)", (pids,))} if pids else {}
    items = []
    for c in changes:
        h = cc.headline(rows.get(c["id"]) or [])
        if not h:
            continue
        p = props.get(c["proposal_id"])
        items.append({"change": {"id": c["id"], "at": c["created_at"].isoformat(), "level": c["level"], "entity_id": c["entity_id"],
                                 "entity_name": c["entity_name"], "action": c["action"], "old": c["old_value"], "new": c["new_value"], "by": _by(c)},
                      "proposal": {"id": p["id"], "title": p["title"], "kind": p["kind"], "expected": p["expected"], "expect": p["expect"]} if p else None,
                      "result": {"horizon": h["horizon"], "state": h["state"], "metric": h["metric"], "before": h["before_totals"],
                                 "after": h["after_totals"], "delta_pct": h["delta_pct"], "confidence": h["confidence"],
                                 "sentence": h["sentence"], "expect_met": next((r["expect_met"] for r in rows[c["id"]] if r["expect_met"] is not None), None)},
                      "put_back": c["id"] in undone})
    return items


def declined(days=60, limit=50):
    return [{"proposal": {"id": p["id"], "title": p["title"], "kind": p["kind"], "expected": p["expected"], "expect": p["expect"]},
             "status": p["status"], "decided_at": p["decided_at"].isoformat()}
            for p in db.query("""SELECT id, title, kind, expected, expect, status, decided_at FROM desk_proposals
                                 WHERE status IN ('declined', 'revised') AND decided_at > now() - %s * interval '1 day'
                                 ORDER BY decided_at DESC LIMIT %s""", (days, limit))]
