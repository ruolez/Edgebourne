"""Settings → Tracking health → Numbers vs Ads Manager (D1, admins): our stored days against Meta's own account totals,
Check now (Meta's totals only), Pull these days again (the days read again from Meta) and the nightly switch.
Read-only on Meta: nothing here changes an ad, a budget or a status, so meta_changes is untouched; the activity log
says who checked or pulled what."""
import logging
import threading
import time
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import db
import meta_client
import numbers_check as nc
import ranges
import refresh_api
import settings_store
import words
from auth import admin_required, current_user
from util import api_error, log_activity

log = logging.getLogger(__name__)
bp = Blueprint("numbers", __name__, url_prefix="/api/numbers")
PULL_WAIT = 45  # seconds a Pull waits for Meta in the request (nginx gives /api/ 120); a longer one goes on by itself

KIND_WORDS = {"nightly": "Every night", "check": "Check now", "pull": "Pulled again", "report": "Before a report"}
FOOTER = "Ads Manager's totals include ads you deleted. Spend can differ by a cent per ad from rounding."
NOT_CONNECTED = "Connect Meta first in Settings → Meta."
STATE_PILL = {"match": ["info", "Matches"], "off": ["warn", "Differs"], "unchecked": ["", "Not checked"], "couldnt": ["bad", "Couldn't check"]}


def _sentence(text):
    text = (text or "").strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _cooling_words(tz):
    until = meta_client.cooling_until()
    if not until:
        return None
    from datetime import datetime, timezone
    return words.clock(datetime.fromtimestamp(until, timezone.utc).astimezone(tz))


def _day_row(d, money):
    day = d["day"]
    return {"day": day.isoformat(), "label": words.weekday(day), "state": d["state"], "meta": d["meta"], "here": d["here"],
            "diff_spend_cents": d["diff_spend_cents"], "diff_leads": d["diff_leads"],
            "href": f"/performance.html?range=custom&start={day.isoformat()}&end={day.isoformat()}"}


def _run_row(r, money):
    return {"id": r["id"], "kind": r["kind"], "kind_label": KIND_WORDS[r["kind"]], "ok": r["ok"],
            "at": (r["finished_at"] or r["started_at"]).isoformat(), "by": r.get("by_name") or ("Every night" if r["kind"] == "nightly" else None),
            "start": r["start_day"].isoformat(), "end": r["end_day"].isoformat(), "parts_done": r["parts_done"], "parts_total": r["parts_total"],
            "changed": nc.changed_line(r["changed"] or [], money, nightly=r["kind"] == "nightly"), "error": r["error"]}


def _running_row(r):
    if not r:
        return None
    a, b = r["start_day"], r["end_day"]
    total = r["parts_total"] or 0
    progress = f" {r['parts_done']} of {total} parts read so far." if total > 1 else ""
    return {"id": r["id"], "kind": r["kind"], "start": a.isoformat(), "end": b.isoformat(), "parts_done": r["parts_done"], "parts_total": total,
            "line": f"Reading {ranges.label(a, b)} again from Meta.{progress} This page updates when it's done."}


def panel():
    """Everything the Settings panel shows, worded here so the page only lays it out."""
    tz = account_info.tz()
    money = nc.money_words()
    today = account_info.today()
    start, end = nc.check_window(today)
    days = nc.current(start, end)
    s = nc.summary(days)
    ok_run, newest = nc.last_run(ok_only=True), nc.last_run()
    failed = newest if newest and not newest["ok"] and (not ok_run or newest["id"] > ok_run["id"]) else None
    restated = nc.last_run(ok_only=True, kinds=nc.JUDGED_KINDS)
    state = "couldnt" if failed else s["state"] if ok_run else "unchecked"
    cooling = _cooling_words(tz)
    lines = []
    if not nc.connected():
        state, lines = "unchecked", [NOT_CONNECTED]
    elif state == "couldnt":
        lines.append(_sentence(f"Couldn't check: {failed['error'] or 'Meta did not answer'}") + (f" We'll try again after {cooling}." if cooling else ""))
    elif state == "unchecked":
        lines.append("Not checked yet. The first check runs tonight after 4 AM, or check now.")
    elif state == "match":
        if not s["meta_spend_cents"] and not s["meta_leads"]:
            lines.append(f"Nothing spent from {words.day(start)} to {words.day(end)}; nothing to compare.")
        else:
            lines.append(f"Checked {words.day_time(ok_run['finished_at'], tz)} for {ranges.label(start, end)}. Both say "
                         f"{money(s['meta_spend_cents'])} spent and {s['meta_leads']} lead{'s' if s['meta_leads'] != 1 else ''}.")
    else:
        lines.append(f"{nc.headline(s, money)}.")
        lines.append(f"Checked {words.day_time(ok_run['finished_at'], tz)} for {ranges.label(start, end)}.")
    restated_line = None
    if restated and restated["changed"] and (not ok_run or restated["id"] >= ok_run["id"] or state == "match"):
        restated_line = nc.changed_line(restated["changed"], money, nightly=restated["kind"] == "nightly")
    shown = [_day_row(d, money) for d in days if d["state"] in ("off", "newer")]
    off = [d["day"] for d in days if d["state"] == "off"]
    pull = None
    if off:
        a, b = off[0], off[-1]
        a = max(a, b - timedelta(days=nc.MAX_PULL_DAYS - 1))
        pull = {"start": a.isoformat(), "end": b.isoformat(), "label": ranges.label(a, b)}
    runs = db.query("""SELECT r.*, u.name AS by_name FROM numbers_runs r LEFT JOIN users u ON u.id = r.user_id
                       ORDER BY r.id DESC LIMIT 5""")
    return {"connected": nc.connected(), "enabled": settings_store.get("numbers_check") != "0",
            "unified": settings_store.get("insights_unified_attribution") != "0",
            "window": {"start": start.isoformat(), "end": end.isoformat(), "label": ranges.label(start, end)},
            "state": state, "pill": STATE_PILL[state], "headline": nc.headline(s, money), "lines": lines, "restated": restated_line,
            "summary": s, "days": shown, "pull": pull, "cooling_until": cooling, "footer": FOOTER, "running": _running_row(nc.running()),
            "runs": [_run_row(r, money) for r in runs]}


@bp.get("")
@admin_required
def get_numbers():
    return jsonify(panel())


@bp.post("/check")
@admin_required
def check_now():
    if not nc.connected():
        return api_error(NOT_CONNECTED, 400)
    now = time.time()
    if not refresh_api.refresh_due(settings_store.get("numbers_last_check_at"), now):
        return jsonify({**panel(), "ran": False, "message": "Checked a moment ago. Try again in a minute."})
    cooling = _cooling_words(account_info.tz())
    if cooling:
        return api_error(f"Meta asked us to slow down. Try again after {cooling}.", 429, code="cooling")
    settings_store.set("numbers_last_check_at", str(now))
    run = nc.check(current_user()["id"])
    log_activity("numbers.check", details={"ok": run["ok"], "state": (run["summary"] or {}).get("state")})
    return jsonify({**panel(), "ran": True})


def _pull_window(data, today):
    """(start, end) from {start, end}, or from a report's {period: week|month, start}; or a plain error."""
    try:
        if data.get("period") in ("week", "month"):
            import report_logic as rl
            first = date.fromisoformat(data["start"]) if data.get("start") else None
            s, e = rl.period(data["period"], today, first)
            return s, min(e, today - timedelta(days=1))
        return date.fromisoformat(str(data.get("start"))), date.fromisoformat(str(data.get("end")))
    except (TypeError, ValueError, KeyError):
        return "Pick the days to pull again"


@bp.post("/pull")
@admin_required
def pull():
    if not nc.connected():
        return api_error(NOT_CONNECTED, 400)
    today = account_info.today()
    window = _pull_window(request.get_json(silent=True) or {}, today)
    window = window if isinstance(window, str) else nc.pull_range(*window, today)
    if isinstance(window, str):
        return api_error(window, 400)
    cooling = _cooling_words(account_info.tz())
    if cooling:
        return api_error(f"Meta asked us to slow down. Try again after {cooling}.", 429, code="cooling")
    start, end = window
    try:
        wait = min(PULL_WAIT, max(0.0, float((request.get_json(silent=True) or {}).get("wait", PULL_WAIT))))
    except (TypeError, ValueError):
        wait = PULL_WAIT
    # The pull runs in a thread of its own: a long one (up to 14 parts of 7 days) finishes after the answer has gone,
    # and the page follows it through GET /api/numbers (`running`).
    box, done = {}, threading.Event()
    threading.Thread(target=_pull_thread, args=(account_ctx.current(), start, end, current_user()["id"], box, done), daemon=True).start()
    done.wait(wait)
    pulled = {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1}
    if box.get("busy"):
        return api_error("Already pulling from Meta, one moment", 409, code="busy")
    if box.get("failed"):
        return api_error("Something went wrong while reading Meta. Try again in a few minutes.", 502)
    run = box.get("run")
    if not run:
        log_activity("numbers.pull", details={"start": pulled["start"], "end": pulled["end"], "running": True})
        return jsonify({**panel(), "ok": True, "running_pull": True, "pulled": pulled,
                        "message": f"Still reading {ranges.label(start, end)} from Meta. This page updates when it's done."}), 202
    money = nc.money_words()
    message = nc.pull_message(pulled["days"], run["summary"], money) if run["ok"] else _sentence(f"Couldn't pull every day: {run['error']}")
    log_activity("numbers.pull", details={"start": pulled["start"], "end": pulled["end"], "ok": run["ok"], "changed": run["changed"]})
    return jsonify({**panel(), "ok": bool(run["ok"]), "message": message, "pulled": pulled})


def _pull_thread(acct, start, end, user_id, box, done):
    """A plain thread with the account and a connection of its own (never the request's context, gotchas)."""
    try:
        with account_ctx.use(acct), db.reusing():
            box["run"] = nc.restate(start, end, "pull", user_id)
    except nc.Busy:
        box["busy"] = True
    except Exception:  # noqa: BLE001 - the run row already says it failed
        log.exception("numbers pull failed")
        box["failed"] = True
    finally:
        done.set()


@bp.put("/settings")
@admin_required
def put_settings():
    data = request.get_json(silent=True) or {}
    if "on" in data:
        settings_store.set("numbers_check", None if data["on"] else "0")
    if "unified" in data:
        settings_store.set("insights_unified_attribution", None if data["unified"] else "0")
    log_activity("settings.numbers_check", details={"on": settings_store.get("numbers_check") != "0",
                                                    "unified": settings_store.get("insights_unified_attribution") != "0"})
    return jsonify(panel())
