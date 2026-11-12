"""Client reports (roadmap 7.3): one account's week or month in the five-part order, for admins and
clients in the console, as a signed link anyone with it can open (90 days), and by email."""
import json
import logging
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import config
import db
import report_logic as rl
import settings_store
from auth import admin_required, current_user, login_required
from util import api_error, log_activity

log = logging.getLogger(__name__)

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
KINDS = ("week", "month")


def today():
    from experiments import account_today
    return account_today()


def totals(start, end):
    t = db.query("""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                           COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(leads),0) AS leads, COALESCE(SUM(video_3s),0) AS video_3s
                    FROM ad_daily WHERE day BETWEEN %s AND %s""", (start, end), one=True)
    stages = db.query("""SELECT COUNT(*) AS inbox,
                                COUNT(*) FILTER (WHERE first_contacted_at IS NOT NULL OR status <> 'new') AS contacted,
                                COUNT(*) FILTER (WHERE status IN ('qualified', 'won')) AS qualified,
                                COUNT(*) FILTER (WHERE status = 'won') AS won,
                                percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM first_contacted_at - created_time) / 60)
                                    FILTER (WHERE first_contacted_at IS NOT NULL) AS median_minutes
                         FROM leads WHERE NOT is_test AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s""",
                      (account_info.tz_name(), start, end), one=True)
    return {**{k: int(v) for k, v in t.items()}, "inbox": int(stages["inbox"]), "contacted": int(stages["contacted"]),
            "qualified": int(stages["qualified"]), "won": int(stages["won"]),
            "median_minutes": round(float(stages["median_minutes"])) if stages["median_minutes"] is not None else None}


def build(kind, start=None, for_admin=False, links=False):
    """links: the signed-in page links each ad, change and test; share links and emails carry no ids."""
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
    changes = db.query("""SELECT m.created_at, (m.created_at AT TIME ZONE %s)::date AS day, m.level, m.entity_id, m.entity_name, m.action, m.old_value, m.new_value
                          FROM meta_changes m WHERE m.ok AND (m.created_at AT TIME ZONE %s)::date BETWEEN %s AND %s
                          ORDER BY m.created_at""", (account_info.tz_name(), account_info.tz_name(), s, e))
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
        q = {r["ad_id"]: int(r["n"]) for r in db.query(
            """SELECT ad_id, COUNT(*) AS n FROM leads WHERE NOT is_test AND status IN ('qualified', 'won')
               AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s GROUP BY ad_id""", (account_info.tz_name(), s, e))}
        rows = [{k: (int(v or 0) if k != "id" else v) for k, v in r.items()} | {"qualified": q.get(r["id"], 0)} for r in rows]
        # Judged like Results › By idea: the cost-per-lead target, else the groups' own average (audit A3-57).
        g = concepts.group(rows, concepts_api.tags_for([r["id"] for r in rows]), "hook", targets.lead_own())
        ideas = {"best": g["best"], "sure": g["best_confidence"], "clear": g["best_is_clear"],
                 "groups": [{"value": x["value"], "ads": x["ads"], "leads": x["leads"], "cpl_cents": x["cpl_cents"]} for x in g["groups"]]}
    except Exception:
        ideas = None
    import accounts_api
    return {
        "account": accounts_api.name_of(account_ctx.current()), "currency": account_info.currency(), "kind": kind, "start": s.isoformat(), "end": e.isoformat(),
        "previous": {"start": ps.isoformat(), "end": pe.isoformat()}, "complete": rl.complete(e, t),
        "headline": rl.headline(now, before, target, account_info.currency()), "target_cents": target, "now": now, "before": before,
        "funnel": rl.funnel(now["inbox"], now["contacted"], now["qualified"], now["won"]),
        "ads": ads, "ads_total": len(every), "ideas": ideas,
        "changes": [{**{k: v for k, v in c.items() if links or k != "entity_id"}, "created_at": c["created_at"].isoformat(), "day": c["day"].isoformat()}
                    for c in changes],
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


@bp.get("")
@login_required
def get_report():
    kind, start, err = _args()
    if err:
        return err
    if current_user()["role"] == "member":
        return api_error("Reports are for admins and clients", 403)
    first = db.query("SELECT MIN(day) AS d FROM ad_daily", one=True)["d"]
    # The earlier weeks or months to pick from (signed in only: a share link is one period).
    periods = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in rl.recent_periods(kind, today(), since=first)]
    return jsonify({**build(kind, start, for_admin=current_user()["role"] == "admin", links=True), "periods": periods})


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
    """Anyone with the link: no sign-in, read-only, one account, one period."""
    payload = rl.verify(config.SECRET_KEY, request.args.get("t", ""), today())
    import accounts_api
    if (not payload or accounts_api.closed(payload["a"])
            or payload.get("e", 0) != link_epoch(payload["a"])):
        return api_error("This report link isn't valid or has expired. Ask for a new one.", 404)
    with account_ctx.use(payload["a"]):
        return jsonify({**build(payload["k"], date.fromisoformat(payload["s"])), "shared_until": payload["exp"]})


@bp.post("/revoke")
@admin_required
def revoke():
    """Every link made so far for this account stops working; new ones work."""
    settings_store.set("report_link_epoch", str(link_epoch(account_ctx.current()) + 1))
    log_activity("report.links_revoked")
    return jsonify({"ok": True})


@bp.get("/settings")
@admin_required
def get_settings():
    t = settings_store.get("kpi_target_cents")
    return jsonify({"target_cents": int(t) if t else None, "email": settings_store.get("report_email") or "off",
                    "clients": [u["email"] for u in db.query("SELECT email FROM users WHERE role = 'client' AND is_active AND account_id = %s",
                                                             (account_ctx.current(),))]})


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
    log_activity("settings.reports", details={k: data.get(k) for k in ("target_dollars", "email")})
    return get_settings()


def send_due(now=None):
    """Worker, per account: from 8 AM on Monday (weekly) or the 1st (monthly), email the account's
    clients a link to the period that just ended. Once per period and person; a failed send is
    tried again an hour later, a missed day is caught up."""
    import json as _json
    import mailer
    mode = settings_store.get("report_email")
    if not mode or not mailer.configured():
        return 0
    local = (now or datetime.now(timezone.utc)).astimezone(account_info.tz())
    due = rl.email_due(mode, local, settings_store.get("report_last_sent"))
    if not due:
        return 0
    kind, s, _e, key = due
    try:
        state = _json.loads(settings_store.get("report_sent_to") or "{}")
    except ValueError:
        state = {}
    if state.get("key") != key:
        state = {"key": key, "to": [], "retry_at": 0}
    if state.get("retry_at", 0) > local.timestamp():
        return 0
    people = db.query("SELECT email, name FROM users WHERE role = 'client' AND is_active AND account_id = %s",
                      (account_ctx.current(),))
    todo = [p for p in people if p["email"] not in state["to"]]
    sent = 0
    if todo:
        report = build(kind, s)
        token, _ = share_token(kind, s.isoformat(), account_ctx.current())
        link = f"{config.APP_BASE_URL.rstrip('/')}/report.html?t={token}"
        label = f"{'Week' if kind == 'week' else 'Month'} of {s.strftime('%b %-d')}"
        for p in todo:
            try:
                mailer.send(p["email"], f"{report['account']}: your ads report, {label}",
                            f"Hi {p['name'].split()[0]},\n\n{report['headline']}\n\nThe full report: {link}\n"
                            f"(The link works for {rl.SHARE_DAYS} days.)")
            except mailer.MailError as exc:
                state["retry_at"] = local.timestamp() + 3600
                log.info("report email to %s not sent: %s", p["email"], exc)
                continue
            state["to"].append(p["email"])
            settings_store.set("report_sent_to", _json.dumps(state))  # a pass that stops here won't mail them again
            sent += 1
    if len(state["to"]) >= len(people):
        settings_store.set("report_last_sent", key)
        state = {}
    settings_store.set("report_sent_to", _json.dumps(state) if state else None)
    if sent:
        log_activity("report.emailed", details={"period": key, "to": sent})
    return sent
