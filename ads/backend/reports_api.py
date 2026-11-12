"""Client reports (roadmap 7.3, W2): one account's week or month in the five-part order, for admins and
clients in the console, as a signed link anyone with it can open (90 days), and by email. Each period's
report is a `client_reports` row: its note, whether it waits for an admin's review, its sending state and
the frozen copy that went out (clients and links see that copy once it was sent)."""
import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import config
import db
import report_logic as rl
import settings_store
import words
from auth import admin_required, current_user, login_required
from util import api_error, log_activity

log = logging.getLogger(__name__)

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
KINDS = ("week", "month")
REVIEW_MODES = ("auto", "wait")
# Which leads count, everywhere in the report (L2 swaps in lead_quality.counted()).
LEAD_SCOPE = "NOT is_test"
STALE_CLAIM = timedelta(minutes=10)
RETRY_AFTER = timedelta(hours=1)
SHOWN_CHANGES = 15
PREVIEW_LINK = "[the report's own link, made when it goes out]"


def today():
    from experiments import account_today
    return account_today()


def stage_counts(start, end):
    """The leads received in these days (account's days) and how far they got."""
    row = db.query(f"""SELECT COUNT(*) AS received,
                              COUNT(*) FILTER (WHERE first_contacted_at IS NOT NULL OR status <> 'new') AS contacted,
                              COUNT(*) FILTER (WHERE status IN ('qualified', 'won')) AS qualified,
                              COUNT(*) FILTER (WHERE status = 'won') AS won,
                              percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM first_contacted_at - created_time) / 60)
                                  FILTER (WHERE first_contacted_at IS NOT NULL) AS median_minutes
                       FROM leads WHERE {LEAD_SCOPE} AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s""",
                   (account_info.tz_name(), start, end), one=True)
    return {"received": int(row["received"]), "contacted": int(row["contacted"]), "qualified": int(row["qualified"]),
            "won": int(row["won"]),
            "median_minutes": round(float(row["median_minutes"])) if row["median_minutes"] is not None else None}


def received_by_ad(start, end):
    """{ad id: leads received in these days}, counted like stage_counts (the report's ideas divide by it)."""
    return {r["ad_id"]: int(r["n"]) for r in db.query(
        f"""SELECT ad_id, COUNT(*) AS n FROM leads WHERE {LEAD_SCOPE} AND ad_id IS NOT NULL
            AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s GROUP BY ad_id""", (account_info.tz_name(), start, end))}


def totals(start, end):
    """Spend and Meta's numbers from ad_daily (`meta_leads` is Meta's lead count) next to the leads received:
    `leads` = `received`, so cost per lead and the funnel count the same people. `inbox` is an old alias."""
    t = db.query("""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                           COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS meta_leads, COALESCE(SUM(video_3s),0) AS video_3s
                    FROM ad_daily WHERE day BETWEEN %s AND %s""", (start, end), one=True)
    stages = stage_counts(start, end)
    return {**{k: int(v) for k, v in t.items()}, **stages, "leads": stages["received"], "inbox": stages["received"]}


def _changes(s, e, links):
    tz = account_info.tz_name()
    console = db.query("""SELECT m.created_at, (m.created_at AT TIME ZONE %s)::date AS day, m.level, m.entity_id, m.entity_name, m.action,
                                 m.old_value, m.new_value
                          FROM meta_changes m WHERE m.ok AND (m.created_at AT TIME ZONE %s)::date BETWEEN %s AND %s
                          ORDER BY m.created_at""", (tz, tz, s, e))
    import status_history
    outside = db.query("""SELECT level, entity_id, entity_name, field, old_value, new_value, at, (at AT TIME ZONE %s)::date AS day
                          FROM status_events WHERE source IN ('poll', 'webhook') AND change_id IS NULL AND old_value IS NOT NULL
                          AND field = ANY(%s) AND (at AT TIME ZONE %s)::date BETWEEN %s AND %s ORDER BY at""",
                       (tz, list(status_history.OUTSIDE_FIELDS), tz, s, e))
    items = rl.what_we_did(console, outside, account_info.currency(), account_info.tz())
    return [{**{k: v for k, v in i.items() if k not in ("at", "entity_id") or (links and k == "entity_id")},
             "day": i["day"].isoformat(), "at": i["at"].isoformat() if i.get("at") else None} for i in items]


def build(kind, start=None, for_admin=False, links=False):
    """links: the signed-in page links each ad, change and test; share links, emails and frozen copies carry no ids."""
    t = today()
    s, e = rl.period(kind, t, start)
    ps, pe = rl.previous(s, e, kind)
    now, before = totals(s, e), totals(ps, pe)
    target = settings_store.get("kpi_target_cents")
    target = int(target) if target else None
    # By name: a new version of an ad (the old one deleted) keeps the name and is the same ad to a client.
    every = db.query("""SELECT COALESCE(a.name, d.ad_name, 'Unnamed ad') AS name, SUM(d.spend_cents) AS spend_cents, SUM(d.leads) AS leads,
                               (ARRAY_AGG(a.id ORDER BY d.day DESC) FILTER (WHERE a.id IS NOT NULL))[1] AS id,
                               SUM(d.impressions) AS impressions, SUM(d.link_clicks) AS link_clicks, SUM(d.video_3s) AS video_3s
                        FROM ad_daily d LEFT JOIN ads a ON a.id = d.ad_id WHERE d.day BETWEEN %s AND %s
                        GROUP BY 1 HAVING SUM(d.spend_cents) > 0 ORDER BY 2 DESC, 1""", (s, e))
    ads = [{"name": a["name"], **({"id": a["id"]} if links else {}), "spend_cents": int(a["spend_cents"]), "leads": int(a["leads"]),
            "cpl_cents": round(int(a["spend_cents"]) / int(a["leads"])) if a["leads"] else None,
            "ctr": round(100 * int(a["link_clicks"]) / int(a["impressions"]), 2) if a["impressions"] else None,
            "hook": round(100 * int(a["video_3s"]) / int(a["impressions"]), 1) if a["impressions"] and a["video_3s"] else None}
           for a in every[:6]]
    changes = _changes(s, e, links)
    import experiments_api
    tests = experiments_api.summaries(db.query(
        f"SELECT {experiments_api.COLS} FROM experiments WHERE status = 'running' OR (closed_at AT TIME ZONE %s)::date BETWEEN %s AND %s",
        (account_info.tz_name(), s, e)))
    pending = db.query("""SELECT p.title FROM desk_proposals p WHERE p.status = 'pending' ORDER BY p.id DESC LIMIT 5""")
    ideas = None
    try:
        import concepts
        import concepts_api
        import targets
        rows = db.query("""SELECT d.ad_id AS id, SUM(d.spend_cents) AS spend_cents, SUM(d.impressions) AS impressions, SUM(d.leads) AS leads,
                                  SUM(d.video_3s) AS video_3s, SUM(d.thruplays) AS thruplays,
                                  SUM(d.impressions) FILTER (WHERE a.object_type = 'VIDEO' OR a.video_id IS NOT NULL) AS video_impressions
                           FROM ad_daily d LEFT JOIN ads a ON a.id = d.ad_id WHERE d.day BETWEEN %s AND %s GROUP BY d.ad_id""", (s, e))
        q = concepts_api.qualified_by_ad(s, e)
        got = received_by_ad(s, e)
        rows = [{k: (int(v or 0) if k != "id" else v) for k, v in r.items()} | {"qualified": q.get(r["id"], 0)} for r in rows]
        tags = concepts_api.tags_for([r["id"] for r in rows])
        # Judged like Creative › Ideas: the cost-per-lead target, else the groups' own average (audit A3-57).
        g = concepts.group(rows, tags, "hook", targets.lead_own())
        # The share qualified counts the console's leads only (qualified of received), never Meta's count.
        people = rl.idea_leads([{**r, "received": got.get(r["id"], 0)} for r in rows], tags, "hook", concepts.UNTAGGED)
        ideas = {"best": g["best"], "sure": g["best_confidence"], "clear": g["best_is_clear"],
                 "groups": [{"value": x["value"], "ads": x["ads"], "leads": x["leads"], "cpl_cents": x["cpl_cents"],
                             **people.get(x["value"], {"received": 0, "qualified": 0}),
                             "qualified_rate": (people[x["value"]]["qualified"] / people[x["value"]]["received"])
                             if people.get(x["value"], {}).get("received") else None} for x in g["groups"]]}
    except Exception:
        log.exception("report ideas not read")
        ideas = None
    import accounts_api
    return {
        "account": accounts_api.name_of(account_ctx.current()), "currency": account_info.currency(), "kind": kind, "start": s.isoformat(), "end": e.isoformat(),
        "previous": {"start": ps.isoformat(), "end": pe.isoformat()}, "complete": rl.complete(e, t),
        "headline": rl.headline(now, before, target, account_info.currency()), "target_cents": target, "now": now, "before": before,
        "funnel": rl.funnel([(rl.LEAD_STEP, now["received"]), ("Contacted", now["contacted"]), ("Qualified", now["qualified"]), ("Won", now["won"])]),
        "lead_gap": rl.lead_gap(now["received"], now["meta_leads"]),
        "ads": ads, "ads_total": len(every), "ideas": ideas,
        "changes": changes[-SHOWN_CHANGES:], "changes_more": max(0, len(changes) - SHOWN_CHANGES),
        "tests": [{"name": x["name"], **({"id": x["id"]} if links else {}), "status": x["status"], "note": x["judgement"]["note"] if x["status"] == "running" else (x["verdict"] or "")} for x in tests],
        # Claude's pending ideas are internal: clients and share links don't see their titles.
        "needs": [p["title"] for p in pending] if for_admin else [],
        "footnotes": rl.footnotes(s, e),
    }


def link_epoch(account_id):
    """Bumped by "Stop all shared links": a link carries the epoch it was made in."""
    try:
        return int(settings_store.get("report_link_epoch", account_id=account_id) or 0)
    except ValueError:
        return 0


def share_token(kind, start, account_id):
    exp = (today() + timedelta(days=rl.SHARE_DAYS)).isoformat()
    return rl.sign(config.SECRET_KEY, {"a": account_id, "k": kind, "s": start, "exp": exp,
                                       "e": link_epoch(account_id)}), exp


def share_link(kind, start):
    token, _ = share_token(kind, start.isoformat(), account_ctx.current())
    return f"{config.APP_BASE_URL.rstrip('/')}/report.html?t={token}"


# ---------------------------------------------------------------- review state (W2)

def review_mode():
    m = settings_store.get("report_review")
    return m if m in REVIEW_MODES else "wait"


def emails_itself(kind):
    """This kind of report is set to be emailed every period (Settings → Clients and reports)."""
    return settings_store.get("report_email") == ("weekly" if kind == "week" else "monthly")


def clients_wait(kind):
    """A client waits for what goes out only when something will: this report is emailed and email is set up."""
    import mailer
    return emails_itself(kind) and mailer.configured()


def clients():
    return db.query("SELECT email, name FROM users WHERE role = 'client' AND is_active AND account_id = %s ORDER BY id",
                    (account_ctx.current(),))


def row_for(kind, s):
    return db.query("SELECT * FROM client_reports WHERE kind = %s AND start_day = %s", (kind, s), one=True)


def local_now():
    return datetime.now(timezone.utc).astimezone(account_info.tz())


def auto_at(kind, s, e, row, local):
    """When the worker emails this period by itself: emailing on for this kind, without review, the newest
    period, no row yet and before 8 AM on the day after it ends. Else None."""
    emailing = settings_store.get("report_email")
    if row or review_mode() != "auto" or emailing != ("weekly" if kind == "week" else "monthly"):
        return None
    if (s, e) != rl.period(kind, local.date()) or local.date() != e + timedelta(days=1) or local.hour >= rl.SEND_HOUR:
        return None
    return datetime.combine(e + timedelta(days=1), time(rl.SEND_HOUR), tzinfo=local.tzinfo)


def first_name(user_id):
    if not user_id:
        return None
    row = db.query("SELECT name FROM users WHERE id = %s", (user_id,), one=True)
    return (row["name"] or "").split()[0] if row and row["name"] else None


def _iso(value):
    return value.isoformat() if value else None


def review_payload(kind, s, e, row):
    import mailer
    local = local_now()
    to = [c["email"] for c in clients()]
    state = rl.review_state(row, review_mode(), to, mailer.configured(), rl.complete(e, today()),
                            auto_at(kind, s, e, row, local), local, kind, emailing=emails_itself(kind),
                            newest=(s, e) == rl.period(kind, today()))
    row = row or {}
    return {**state, "to": to, "mode": review_mode(), "emailing": settings_store.get("report_email") or "off",
            "later_when": words.day_time(rl.next_send_at(local), local.tzinfo),
            "note": row.get("note") or "", "note_at": _iso(row.get("note_at")), "note_by": first_name(row.get("note_by")),
            "sent_at": _iso(row.get("sent_at")), "round": row.get("round", 1), "last_error": row.get("last_error"),
            "has_sent": bool(row.get("snapshot"))}


def note_block(row):
    return {"text": row["note"], "by": first_name(row.get("note_by"))}


def frozen(row):
    """The copy that went out, with the note it carries now (an edit after sending shows; no email goes)."""
    snap = dict(row["snapshot"])
    sent_on = date.fromisoformat(snap["as_sent"]) if snap.get("as_sent") else None
    snap["footnotes"] = rl.footnotes(date.fromisoformat(snap["start"]), date.fromisoformat(snap["end"]), sent_on)
    snap["note"] = note_block(row) if row.get("note") else None
    return snap


def latest_sent(kind):
    row = db.query("SELECT kind, start_day, end_day FROM client_reports WHERE kind = %s AND status = 'sent' ORDER BY start_day DESC LIMIT 1",
                   (kind,), one=True)
    return {"kind": row["kind"], "start": row["start_day"].isoformat(), "end": row["end_day"].isoformat()} if row else None


def report_for_viewer(kind, start, user):
    """The one place that decides live or frozen. Admins: today's figures with the review state and the saved
    note. Clients and share links: the copy that went out (stored with the first email that carried it, so a send
    that reached nobody shows nothing frozen); with review on and nothing sent, a waiting notice; otherwise today's
    figures without the note."""
    s, e = rl.period(kind, today(), start)
    row = row_for(kind, s)
    if user and user["role"] == "admin":
        r = build(kind, s, for_admin=True, links=True)
        r["review"] = review_payload(kind, s, e, row)
        r["note"] = note_block(row) if rl.note_visible(row, True) else None
        return r
    if row and row.get("snapshot"):
        return frozen(row)
    # A signed-in client waits for what goes out; a share link is an admin's choice to show the period.
    if user and not rl.client_can_open(review_mode(), row, clients_wait(kind)):
        import accounts_api
        return {"waiting": True, "kind": kind, "start": s.isoformat(), "end": e.isoformat(), "currency": account_info.currency(),
                "account": accounts_api.name_of(account_ctx.current()), "latest_sent": latest_sent(kind),
                "emailed": bool(settings_store.get("report_email"))}
    r = build(kind, s, links=bool(user))
    r["note"] = note_block(row) if rl.note_visible(row, False) else None
    return r


def periods_for(kind, user):
    """The earlier weeks or months to pick from, newest first. Admins see each one's state; clients of an
    account that reviews first only get the ones sent (and the newest, which says it's being prepared)."""
    first = db.query("SELECT MIN(day) AS d FROM ad_daily", one=True)["d"]
    spans = rl.recent_periods(kind, today(), since=first)
    rows = {r["start_day"]: r for r in db.query("SELECT start_day, status, sent_at, snapshot IS NOT NULL AS frozen FROM client_reports "
                                                 "WHERE kind = %s AND start_day >= %s", (kind, spans[-1][0]))}
    out = []
    for i, (s, e) in enumerate(spans):
        row = rows.get(s)
        p = {"start": s.isoformat(), "end": e.isoformat(), "label": rl.period_label(kind, s)}
        if user["role"] == "admin":
            p["status"] = row["status"] if row else None
            p["sent_at_label"] = words.day_time(row["sent_at"], account_info.tz()) if row and row["sent_at"] else None
        elif i and not rl.client_can_open(review_mode(), row, clients_wait(kind)) and not (row and row["frozen"]):
            continue
        out.append(p)
    return out


def _args():
    kind = request.args.get("kind", "week")
    if kind not in KINDS:
        return None, None, api_error("Pick week or month", 400)
    start = None
    if request.args.get("start"):
        try:
            start = date.fromisoformat(request.args["start"])
        except ValueError:
            return None, None, api_error("Use a date like 2026-11-02", 400)
    return kind, start, None


def _body_period(data):
    """(kind, start, end) of a JSON body's period, or an error response."""
    kind = data.get("kind")
    if kind not in KINDS:
        return None, None, None, api_error("Pick week or month", 400)
    try:
        start = date.fromisoformat(data["start"]) if data.get("start") else None
    except (TypeError, ValueError):
        return None, None, None, api_error("Use a date like 2026-11-02", 400)
    s, e = rl.period(kind, today(), start)
    return kind, s, e, None


@bp.get("")
@login_required
def get_report():
    kind, start, err = _args()
    if err:
        return err
    user = current_user()
    if user["role"] == "member":
        return api_error("Reports are for admins and clients", 403)
    return jsonify({**report_for_viewer(kind, start, user), "periods": periods_for(kind, user)})


@bp.get("/periods")
@login_required
def get_periods():
    kind, _, err = _args()
    if err:
        return err
    user = current_user()
    if user["role"] == "member":
        return api_error("Reports are for admins and clients", 403)
    return jsonify({"kind": kind, "periods": periods_for(kind, user)})


@bp.get("/sent")
@admin_required
def get_sent():
    """What clients got for this period (See what was sent)."""
    kind, start, err = _args()
    if err:
        return err
    s, _ = rl.period(kind, today(), start)
    row = row_for(kind, s)
    if not row or not row.get("snapshot"):
        return api_error("Nothing was sent for this period yet", 404)
    return jsonify(frozen(row))


@bp.post("/share")
@admin_required
def share():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind") if data.get("kind") in KINDS else "week"
    try:
        start = date.fromisoformat(data["start"]) if data.get("start") else None
    except ValueError:
        return api_error("Use a date like 2026-11-02", 400)
    s, _ = rl.period(kind, today(), start)
    token, exp = share_token(kind, s.isoformat(), account_ctx.current())
    log_activity("report.shared", details={"kind": kind, "start": s.isoformat(), "expires": exp})
    return jsonify({"url": f"{config.APP_BASE_URL.rstrip('/')}/report.html?t={token}", "expires": exp})


@bp.get("/shared")
def shared():
    """Anyone with the link: no sign-in, read-only, one account, one period (the copy that went out, once sent)."""
    payload = rl.verify(config.SECRET_KEY, request.args.get("t", ""), today())
    import accounts_api
    if (not payload or accounts_api.closed(payload["a"])
            or payload.get("e", 0) != link_epoch(payload["a"])):
        return api_error("This report link isn't valid or has expired. Ask for a new one.", 404)
    with account_ctx.use(payload["a"]):
        return jsonify({**report_for_viewer(payload["k"], date.fromisoformat(payload["s"]), None), "shared_until": payload["exp"]})


@bp.post("/revoke")
@admin_required
def revoke():
    """Every link made so far for this account stops working; new ones work."""
    settings_store.set("report_link_epoch", str(link_epoch(account_ctx.current()) + 1))
    log_activity("report.links_revoked")
    return jsonify({"ok": True})


# ---------------------------------------------------------------- review routes (W2)

def ensure_row(kind, s, e):
    """The period's row, made when missing: set to go out at 8 AM when the worker would have sent it by itself
    then (so a note typed before 8 goes with it), otherwise waiting (a saved note never sends by itself)."""
    row = row_for(kind, s)
    if row:
        return row
    at = auto_at(kind, s, e, None, local_now())
    db.execute("INSERT INTO client_reports (kind, start_day, end_day, status, send_at) VALUES (%s, %s, %s, %s, %s) "
               "ON CONFLICT (account_id, kind, start_day) DO NOTHING", (kind, s, e, "scheduled" if at else "waiting", at))
    return row_for(kind, s)


def _clean_note(data):
    """(note or None, error response or None) from a body's `note`."""
    note = (data.get("note") or "").strip() if isinstance(data.get("note"), (str, type(None))) else ""
    if len(note) > rl.NOTE_MAX:
        return None, api_error(f"Keep the note under {rl.NOTE_MAX:,} characters", 400, field="note")
    return note or None, None


def _save_note(row, note):
    db.execute("UPDATE client_reports SET note = %s, note_by = %s, note_at = now() WHERE id = %s",
               (note, current_user()["id"], row["id"]))


def resolve_review(kind, s):
    db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'report_review' AND dedupe_key = %s AND resolved_at IS NULL",
               (f"report_review:{kind}:{s.isoformat()}",))


def review_item(kind, s, quiet=False):
    """Put the period under Needs action and on Today (an owner-closed event): reopen its item, or raise it.
    quiet: an admin did it themselves, so nobody gets a message."""
    key = f"report_review:{kind}:{s.isoformat()}"
    if db.execute("UPDATE alerts SET resolved_at = NULL WHERE rule = 'report_review' AND dedupe_key = %s RETURNING id",
                  (key,), returning=True):
        return
    import accounts_api
    _raise({**rl.review_alert(accounts_api.name_of(account_ctx.current()), kind, s, [c["email"] for c in clients()]),
            "resolved": False, "button": "Review it", "quiet": quiet})


def _state(kind, s, e):
    row = row_for(kind, s)
    return jsonify({"review": review_payload(kind, s, e, row), "note": note_block(row) if rl.note_visible(row, True) else None})


@bp.put("/note")
@admin_required
def put_note():
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    note, err = _clean_note(data)
    if err:
        return err
    row = ensure_row(kind, s, e)
    if "note_at" in data and (data["note_at"] or None) != _iso(row.get("note_at")):
        return api_error("Someone else changed this note a moment ago. Reload to see it.", 409, code="note_changed")
    _save_note(row, note)
    log_activity("report.note_saved", details={"kind": kind, "start": s.isoformat(), "after_sending": row["status"] == "sent"})
    return _state(kind, s, e)


def _sendable(kind, e, expect_to):
    """An error response when this period can't go out now, else None."""
    import mailer
    if not rl.complete(e, today()):
        return api_error(f"You can send it once the {'week' if kind == 'week' else 'month'} is over.", 400)
    to = [c["email"] for c in clients()]
    if not to:
        return api_error("No clients on this account yet: add them on the Team page.", 400)
    if not mailer.configured():
        return api_error("Email isn't set up yet: Settings → Email.", 400)
    if not isinstance(expect_to, list) or sorted(map(str, expect_to)) != sorted(to):
        return api_error("The client list changed. Check who it goes to and try again.", 409, code="client_list", to=to)
    return None


@bp.post("/email-preview")
@admin_required
def email_preview():
    """The email as the first client would get it, with the note as typed (nothing saved, nothing sent)."""
    import mailer
    data = request.get_json(silent=True) or {}
    kind, s, _e, err = _body_period(data)
    if err:
        return err
    note, err = _clean_note(data)
    if err:
        return err
    people = clients()
    report = build(kind, s)
    row = row_for(kind, s)
    first = (people[0]["name"] or "").split()[0] if people and people[0]["name"] else None
    # A placeholder, not a working link: a real one is made only when the email goes (send_row).
    subject, text = rl.email_text(report, first, PREVIEW_LINK, note, round_=(row["round"] + 1) if row and row["status"] == "sent" else 1)
    m = mailer.smtp_settings()
    return jsonify({"to": [p["email"] for p in people], "from": m.get("from_email") or "", "subject": subject, "text": text})


@bp.post("/send")
@admin_required
def send():
    """Send now, or at 8 AM (the account's time). Refused unless the period is over, there are clients, email
    works and the client list is the one the admin saw."""
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    if data.get("when") not in ("now", "8am"):
        return api_error("Pick now or 8 AM", 400)
    note, err = _clean_note(data) if "note" in data else (None, None)
    if err:
        return err
    err = _sendable(kind, e, data.get("expect_to"))
    if err:
        return err
    row = ensure_row(kind, s, e)
    if row["status"] in ("sending", "sent"):
        return api_error("This report already went out. Use Send again to send today's figures.", 409, code="already_sent")
    if "note" in data and note != row.get("note"):
        _save_note(row, note)
    at = None if data["when"] == "now" else rl.next_send_at(local_now())
    db.execute("UPDATE client_reports SET status = 'scheduled', send_at = COALESCE(%s, now()), decided_by = %s, decided_at = now() "
               "WHERE id = %s AND status IN ('waiting', 'scheduled', 'skipped')", (at, current_user()["id"], row["id"]))
    log_activity("report.send_now" if at is None else "report.scheduled",
                 details={"kind": kind, "start": s.isoformat(), **({"at": at.isoformat()} if at else {})})
    if at is None:
        import jobs
        jobs.wake()
    return _state(kind, s, e)


@bp.post("/hold")
@admin_required
def hold():
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    row = ensure_row(kind, s, e)
    if row["status"] in ("sending", "sent"):
        return api_error("It's already on its way, so it can't be held.", 409)
    db.execute("UPDATE client_reports SET status = 'waiting', send_at = NULL, decided_by = %s, decided_at = now() WHERE id = %s",
               (current_user()["id"], row["id"]))
    if rl.complete(e, today()):
        review_item(kind, s, quiet=True)  # a held report stays in Needs action until someone decides
    log_activity("report.held", details={"kind": kind, "start": s.isoformat()})
    return _state(kind, s, e)


@bp.post("/skip")
@admin_required
def skip():
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    row = ensure_row(kind, s, e)
    if row["status"] in ("sending", "sent"):
        return api_error("It's already on its way.", 409)
    db.execute("UPDATE client_reports SET status = 'skipped', send_at = NULL, decided_by = %s, decided_at = now() WHERE id = %s",
               (current_user()["id"], row["id"]))
    resolve_review(kind, s)
    log_activity("report.skipped", details={"kind": kind, "start": s.isoformat()})
    return _state(kind, s, e)


@bp.post("/unskip")
@admin_required
def unskip():
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    row = db.execute("UPDATE client_reports SET status = 'waiting', decided_by = %s, decided_at = now() "
                     "WHERE kind = %s AND start_day = %s AND status = 'skipped' RETURNING id", (current_user()["id"], kind, s), returning=True)
    if not row:
        return api_error("Nothing to undo: it isn't set aside any more.", 409)
    review_item(kind, s, quiet=True)
    log_activity("report.unskipped", details={"kind": kind, "start": s.isoformat()})
    return _state(kind, s, e)


@bp.post("/resend")
@admin_required
def resend():
    """Send again with today's figures: everyone gets a new email marked updated; the frozen copy is taken again."""
    data = request.get_json(silent=True) or {}
    kind, s, e, err = _body_period(data)
    if err:
        return err
    err = _sendable(kind, e, data.get("expect_to"))
    if err:
        return err
    row = db.execute("UPDATE client_reports SET status = 'scheduled', send_at = now(), round = round + 1, sent_to = '{}', "
                     "decided_by = %s, decided_at = now(), last_error = NULL WHERE kind = %s AND start_day = %s AND status = 'sent' RETURNING id",
                     (current_user()["id"], kind, s), returning=True)
    if not row:
        return api_error("Only a report that went out can be sent again.", 409)
    log_activity("report.resent", details={"kind": kind, "start": s.isoformat()})
    import jobs
    jobs.wake()
    return _state(kind, s, e)


@bp.get("/settings")
@admin_required
def get_settings():
    t = settings_store.get("kpi_target_cents")
    scheduled = db.query("SELECT kind, start_day, send_at FROM client_reports WHERE status = 'scheduled' ORDER BY send_at")
    return jsonify({"target_cents": int(t) if t else None, "email": settings_store.get("report_email") or "off", "review": review_mode(),
                    "clients": [u["email"] for u in clients()],
                    "waiting": db.query("SELECT COUNT(*) AS n FROM client_reports WHERE status = 'waiting'", one=True)["n"],
                    "scheduled": [{"kind": r["kind"], "start": r["start_day"].isoformat(),
                                   "when": words.day_time(r["send_at"], account_info.tz()) if r["send_at"] else None} for r in scheduled]})


@bp.put("/settings")
@admin_required
def put_settings():
    data = request.get_json(silent=True) or {}
    if "target_dollars" in data:
        raw = str(data.get("target_dollars") or "").strip().replace("$", "")
        if raw:
            try:
                cents = round(float(raw) * 100)
                assert cents > 0
            except (ValueError, AssertionError):
                return api_error("Type the target in dollars, like 60", 400, field="target")
            settings_store.set("kpi_target_cents", str(cents))
        else:
            settings_store.set("kpi_target_cents", None)
    if "email" in data:
        if data["email"] not in ("off", "weekly", "monthly"):
            return api_error("Pick off, weekly or monthly", 400, field="email")
        settings_store.set("report_email", None if data["email"] == "off" else data["email"])
    if "review" in data:
        if data["review"] not in REVIEW_MODES:
            return api_error("Pick wait for me or send without review", 400, field="review")
        settings_store.set("report_review", data["review"])
    log_activity("settings.reports", details={k: data.get(k) for k in ("target_dollars", "email", "review")})
    return get_settings()


# ---------------------------------------------------------------- worker (W2)

def _raise(alert):
    import alerts
    alerts.raise_found([{**alert, "entity_id": None, "campaign_id": None, "kind": "event"}])


def send_row(row_id, now):
    """Send one scheduled report: claim it (one pass only), freeze the client view on the round's first claim,
    then mail each active client not reached yet, saving each address as it goes (a crash resends to at most
    the one in flight). Any failure puts it back an hour later. Returns how many emails went."""
    import mailer
    row = db.execute("UPDATE client_reports SET status = 'sending', claimed_at = now(), attempts = attempts + 1 "
                     "WHERE id = %s AND status = 'scheduled' RETURNING *", (row_id,), returning=True)
    if not row:
        return 0
    kind, s = row["kind"], row["start_day"]
    snap = row["snapshot"]
    fresh = not snap or snap.get("round") != row["round"]
    if fresh:
        try:
            import numbers_check  # D1, once built: re-read Meta's days of this period first
            numbers_check.ensure_period(s, row["end_day"])
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 - a failed check never blocks the email
            log.exception("numbers check before the report failed")
        snap = {**build(kind, s), "round": row["round"], "as_sent": local_now().date().isoformat()}
    link = share_link(kind, s)
    done, sent, problem = list(row["sent_to"] or []), 0, None
    for p in clients():  # read now: a client removed meanwhile is skipped, one added is included
        if p["email"] in done:
            continue
        first = (p["name"] or "").split()[0] if p["name"] else None
        subject, text = rl.email_text(snap, first, link, row["note"], row["round"])
        try:
            mailer.send(p["email"], subject, text)
        except Exception as exc:  # noqa: BLE001 - MailError or anything else: try again later
            problem = str(exc)
            log.info("report email to %s not sent: %s", p["email"], exc)
            continue
        if fresh:
            # Clients and links see this copy (and the note) from the first email that carried it, never before.
            db.execute("UPDATE client_reports SET sent_to = array_append(sent_to, %s), snapshot = %s WHERE id = %s",
                       (p["email"], json.dumps(snap, default=str), row_id))
            fresh = False
        else:
            db.execute("UPDATE client_reports SET sent_to = array_append(sent_to, %s) WHERE id = %s", (p["email"], row_id))
        done.append(p["email"])
        sent += 1
    left = [p["email"] for p in clients() if p["email"] not in done]
    if not done and not problem:
        # Nobody left to send it to: it waits for an admin (Needs action) instead of retrying every hour.
        db.execute("UPDATE client_reports SET status = 'waiting', send_at = NULL, last_error = %s WHERE id = %s",
                   ("No clients to send it to", row_id))
        review_item(kind, s)
    elif problem or left:
        db.execute("UPDATE client_reports SET status = 'scheduled', send_at = %s, last_error = %s WHERE id = %s",
                   (now + RETRY_AFTER, problem or "Some clients were added meanwhile", row_id))
    else:
        db.execute("UPDATE client_reports SET status = 'sent', sent_at = now(), last_error = NULL WHERE id = %s", (row_id,))
        resolve_review(kind, s)
        _raise({"rule": "report_sent", "key": f"report_sent:{kind}:{s.isoformat()}:{row['round']}", "level": "info", "resolved": True,
                "title": f"{'Weekly' if kind == 'week' else 'Monthly'} report sent to {len(done)} client{'s' if len(done) != 1 else ''}",
                "lines": [f"{rl.period_label(kind, s)} · to {rl.who_label(done)}"], "href": f"/report.html?kind={kind}&start={s.isoformat()}"})
    if sent:
        log_activity("report.emailed", details={"period": f"{kind}:{s.isoformat()}", "to": sent, "round": row["round"]})
    return sent


def send_due(now=None):
    """Worker, per account (quick pass, every 30 s and at once after Send now): put stale claims back, send what
    is due, then open the period that just came due: sent at once without review, or waiting for an admin."""
    import mailer
    now = now or datetime.now(timezone.utc)
    db.execute("UPDATE client_reports SET status = 'scheduled', send_at = now() WHERE status = 'sending' AND claimed_at < now() - %s",
               (STALE_CLAIM,))
    sent = 0
    for r in db.query("SELECT id FROM client_reports WHERE status = 'scheduled' AND send_at <= %s ORDER BY send_at", (now,)):
        sent += send_row(r["id"], now)
    emailing = settings_store.get("report_email")
    if not emailing or not mailer.configured():
        return sent
    due = rl.email_due(emailing, now.astimezone(account_info.tz()), None)
    if not due:
        return sent
    kind, s, e, _key = due
    to = [c["email"] for c in clients()]
    existing = row_for(kind, s)
    if not to or (existing and (review_mode() == "auto" or existing["status"] != "waiting")):
        return sent
    if review_mode() == "auto":
        row = db.execute("INSERT INTO client_reports (kind, start_day, end_day, status, send_at) VALUES (%s, %s, %s, 'scheduled', %s) "
                         "ON CONFLICT (account_id, kind, start_day) DO NOTHING RETURNING id", (kind, s, e, now), returning=True)
        return sent + (send_row(row["id"], now) if row else 0)
    if not existing:
        if not db.execute("INSERT INTO client_reports (kind, start_day, end_day, status) VALUES (%s, %s, %s, 'waiting') "
                          "ON CONFLICT (account_id, kind, start_day) DO NOTHING RETURNING id", (kind, s, e), returning=True):
            return sent
        log_activity("report.waiting", details={"kind": kind, "start": s.isoformat()})
    # Once per period (a row made by a note typed before 8 AM gets its item too); a closed item stays closed.
    if not db.query("SELECT 1 FROM alerts WHERE dedupe_key = %s", (f"report_review:{kind}:{s.isoformat()}",), one=True):
        review_item(kind, s)
    return sent
