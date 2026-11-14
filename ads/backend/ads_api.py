"""Ads page: see every campaign, ad set and ad with its results, preview ads as
Meta renders them, and make changes: on/off, budgets, duplicate, new ads from
uploaded media, and Claude's proposals. Admins can change everything; teammates
the campaigns assigned to them. Every write to Meta lands in meta_changes."""
import html
import json
import logging
import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_ctx
import account_info
import change_checks
import change_checks_db
import money_rules
import ranges
import db
import lead_quality as lq
import delivery
import desk_view
import followup
import creative_build
import insights
import meta_client
import settings_store
import status_history
import timeline
from auth import admin_required, current_user, login_required, visible_campaign_ids
from util import api_error, log_activity

log = logging.getLogger(__name__)
bp = Blueprint("ads", __name__, url_prefix="/api")

LEVELS = {"campaign": "campaigns", "adset": "adsets", "ad": "ads"}
RANGES = {"7": 7, "14": 14, "30": 30}
PREVIEW_FORMATS = [
    ("MOBILE_FEED_STANDARD", "Facebook feed"),
    ("INSTAGRAM_STANDARD", "Instagram feed"),
    ("INSTAGRAM_STORY", "Instagram Stories"),
    ("INSTAGRAM_REELS", "Instagram Reels"),
    ("FACEBOOK_STORY_MOBILE", "Facebook Stories"),
    ("FACEBOOK_REELS_MOBILE", "Facebook Reels"),
    ("DESKTOP_FEED_STANDARD", "Facebook desktop"),
]
CTA_TYPES = ["BOOK_TRAVEL", "SIGN_UP", "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SUBSCRIBE", "DOWNLOAD", "CONTACT_US"]
IMAGE_TYPES = {"image/jpeg", "image/png"}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
MAX_IMAGE = 30 * 1024 * 1024
MAX_VIDEO = 250 * 1024 * 1024


# ---------------------------------------------------------------- pure helpers

def proposal_action(p, entity, apply_as=None):
    """What approving a proposal does on Meta: ("status", "PAUSED"), ("budget", cents)
    or None when it isn't something the dashboard can apply by itself. New words or media
    update the ad or make a new one as Claude proposed; `apply_as` ("update" / "new") overrides."""
    payload = p.get("payload") or {}
    if p["kind"] == "spend_limit":  # FU-B: the ad account's own limit; no campaign, ad set or ad behind it
        return money_rules.limit_action(p.get("proposed_value"), payload)
    if p["kind"] == "creative" and payload.get("update_ad") and (payload.get("vertical") or {}).get("video_id"):
        return ("vertical", payload)
    if p["kind"] == "creative" and payload.get("template_ad_id") and payload.get("body") and payload.get("title"):
        update = apply_as == "update" or (payload.get("update_ad") and apply_as != "new")
        return ("update" if update else "create", payload)
    if not entity or not p.get("entity_id"):
        return None
    if p["kind"] == "status":
        value = (p.get("proposed_value") or "").strip().upper()
        value = {"OFF": "PAUSED", "PAUSE": "PAUSED", "ON": "ACTIVE", "RESUME": "ACTIVE"}.get(value, value)
        return ("status", value) if value in ("ACTIVE", "PAUSED") else None
    if p["kind"] == "budget" and entity.get("daily_budget_cents"):
        cents, why = money_rules.proposal_cents(p.get("proposed_value"), payload.get("proposed_cents"))
        return ("budget", cents) if cents else ("unclear", why)
    return None


def proposal_target_id(p):
    """The Meta id approving a proposal acts on, so permission is checked on what is written: a creative
    change writes to the ad in its payload, whatever entity_id says (audit A3-49, A3-78)."""
    template = (p.get("payload") or {}).get("template_ad_id")
    if p["kind"] == "creative" and template:
        return template
    return p.get("entity_id") or template


def build_story_spec(template, media, body, title, cta_type=None, form_id=None):
    """A new object_story_spec from an existing ad's: same Page, Instagram identity and
    button (lead form, or `form_id` instead), new media and words."""
    old_media = template.get("video_data") or template.get("link_data") or {}
    cta = json.loads(json.dumps(old_media.get("call_to_action") or {}))
    if cta_type:
        cta["type"] = cta_type
    if form_id:
        cta.setdefault("value", {})["lead_gen_form_id"] = form_id
    spec = {k: template[k] for k in ("page_id", "instagram_user_id", "instagram_actor_id") if template.get(k)}
    if media["kind"] == "video":
        data = {"video_id": media["video_id"], "message": body, "title": title}
        if media.get("thumbnail_url"):
            data["image_url"] = media["thumbnail_url"]
        if cta:
            data["call_to_action"] = cta
        spec["video_data"] = data
    else:
        link = old_media.get("link") or (cta.get("value") or {}).get("link") or "http://fb.me/"
        data = {"image_hash": media["hash"], "message": body, "name": title, "link": link}
        if cta:
            data["call_to_action"] = cta
        spec["link_data"] = data
    return spec


def preview_src(body_html):
    m = re.search(r'src="([^"]+)"', body_html or "")
    return html.unescape(m.group(1)) if m else None


def preview_size(body_html):
    w = re.search(r'width="(\d+)"', body_html or "")
    h = re.search(r'height="(\d+)"', body_html or "")
    return (int(w.group(1)) if w else None, int(h.group(1)) if h else None)


# ---------------------------------------------------------------- access

def _scope(user, column):
    ids = visible_campaign_ids(user)
    return ("TRUE", []) if ids is None else (f"{column} = ANY(%s)", [ids])


def entity(level, entity_id):
    table = LEVELS.get(level)
    if not table:
        return None
    campaign_col = "id" if level == "campaign" else "campaign_id"
    budget = "daily_budget_cents, " if level != "ad" else "NULL::int AS daily_budget_cents, "
    return db.query(f"SELECT id, name, status, effective_status, {budget}{campaign_col} AS campaign_id "
                    f"FROM {table} WHERE id = %s", (entity_id,), one=True)


def find_entity(entity_id):
    for level in ("ad", "adset", "campaign"):
        row = entity(level, entity_id)
        if row:
            return level, row
    return None, None


REMOVALS = {"archive": "ARCHIVED", "delete": "DELETED"}


REMOVAL_WORDS = {"ad": "ad", "adset": "ad set", "campaign": "campaign"}


def removal_problem(user, row, action, typed_name, level="ad"):
    """Archive and delete are admin-only (owner or this account's admin), only for what is off, and delete needs the
    name typed. Meta lets an archived one go on to deleted, never back. AM-C: campaigns and ad sets the same way."""
    word = REMOVAL_WORDS[level]
    if action not in REMOVALS:
        return "Unknown action"
    if user.get("role") != "admin":
        return f"Only an admin can archive or delete {word}s"
    if row["status"] == "DELETED":
        return "It's already deleted"
    if row["status"] == REMOVALS[action]:
        return "It's already archived"
    if row["status"] == "ACTIVE":
        return f"Switch the {word} off first"
    if action == "delete" and (typed_name or "").strip() != row["name"].strip():
        return f"Type the {word}'s name exactly to delete it"
    return None


def can_touch(user, campaign_id):
    ids = visible_campaign_ids(user)
    return ids is None or campaign_id in ids


BULK_ID = __import__("contextvars").ContextVar("bulk_id", default=None)  # set while a bulk change runs

# Error prefixes for the write helpers: NOT_SENT = refused before anything reached Meta (a proposal stays
# waiting); UNKNOWN = Meta didn't answer a write, so it may have happened (never sent again blind);
# CHECKED = the console's own read-back check refused the copy Meta stored, so the running ad wasn't
# switched (Meta refused nothing, audit A3-109).
NOT_SENT = "\x00"
UNKNOWN = "\x01"
CHECKED = "\x02"


def error_words(error):
    """A write helper's error without its prefix, for people."""
    return error[1:] if error and error[0] in (NOT_SENT, UNKNOWN, CHECKED) else error


def write_error(error):
    """The API answer for a write helper's error."""
    if error.startswith(NOT_SENT):
        return api_error(error_words(error), 409)
    if error.startswith(CHECKED):
        return api_error(f"Not applied: {error_words(error)}", 400)
    return api_error(error_words(error) if error.startswith(UNKNOWN) else f"Meta refused: {error}", 400)


def after_write(what, fn, *args):
    """Local bookkeeping after Meta accepted a write: a failure here is logged, never raised, so a request
    can't end as if nothing had been sent (audit A3-40, A3-68)."""
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        log.exception("after the write to Meta: %s failed", what)


def record(user, level, row, action, old, new, ok, error=None, proposal_id=None, entity_id=None, accepted=None, undo_of=None):
    """One write to Meta in meta_changes. `accepted`: the warnings confirmed knowingly ('big', 'recent'); `undo_of`: the
    change a Put it back reverses (D3, checked by `undo_target`)."""
    db.execute(
        """INSERT INTO meta_changes (user_id, level, entity_id, entity_name, campaign_id, action, old_value,
                                     new_value, ok, error, proposal_id, bulk_id, accepted, undo_of)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (user["id"] if user else None, level, entity_id or row["id"], row.get("name"), row.get("campaign_id"),
         action, None if old is None else str(old), None if new is None else str(new), ok, error, proposal_id,
         BULK_ID.get(), list(accepted) if accepted else None, undo_of))
    if ok and undo_of:
        after_write("close the put-back result", change_checks_db.close_put_back, undo_of)
    log_activity(f"meta.{action}" + ("" if ok else "_failed"), subject=entity_id or row["id"],
                 details={"level": level, "name": row.get("name"), "old": old, "new": new, "error": error,
                          **({"accepted": list(accepted)} if accepted else {})})


RESYNC_DELAY = 3  # seconds after the last write: a burst of switches gives one re-read (audit A3-125)
_resync_due = {}  # account id -> when its next re-read starts; None while one runs with nothing queued
_resync_guard = threading.Lock()


def resync_later():
    """Re-read the structure in the background a moment after the last write, at most one at a time per
    account."""
    if BULK_ID.get():
        return  # a bulk change resyncs once at the end
    acct = account_ctx.current()
    with _resync_guard:
        start = acct not in _resync_due
        _resync_due[acct] = __import__("time").time() + RESYNC_DELAY
    if start:
        threading.Thread(target=_resync_runner, args=(acct,), daemon=True).start()


def _resync_runner(acct):
    """A plain thread starts with an empty context: it never sees the request's app context or database
    connection (audit A3-48), so it sets the account and opens (and closes) a connection of its own."""
    import time
    while True:
        with _resync_guard:
            due = _resync_due[acct]
            if due is None:
                del _resync_due[acct]
                return
            wait = due - time.time()
            if wait <= 0:
                _resync_due[acct] = None
        if wait > 0:
            time.sleep(wait)
            continue
        try:
            with db.try_lock(f"resync:{acct}") as mine:
                if mine:
                    with account_ctx.use(acct), db.reusing():
                        insights.sync_structure()
        except Exception as exc:
            log.info("resync after change failed: %s", exc)
            mine = True
        if not mine:  # another gunicorn worker is re-reading this account: try again after it, never alongside
            with _resync_guard:
                _resync_due[acct] = time.time() + RESYNC_DELAY


REFRESH_FIELDS = "id,name,status,configured_status,effective_status"


def refresh_entity(level, entity_id):
    """Re-read the status right after a change from the console and record what moved."""
    try:
        fresh = meta_client.get(entity_id, fields=REFRESH_FIELDS)
    except meta_client.MetaError:
        return
    _store_fresh(level, entity_id, fresh)


def refresh_entities(level, ids):
    """refresh_entity for a bulk change's items, read 50 at a time instead of one by one (audit A3-126)."""
    for chunk in (ids[i:i + 50] for i in range(0, len(ids), 50)):
        try:
            got = meta_client.get("", ids=",".join(chunk), fields=REFRESH_FIELDS)
        except meta_client.MetaError as exc:
            if meta_client.transient(exc):
                return  # no answer: the resync after the change records it
            got = {}  # one of them is gone (Meta refuses the whole read then): one by one
        for entity_id in chunk:
            if got.get(entity_id):
                after_write("status refresh", _store_fresh, level, entity_id, got[entity_id])
            else:
                after_write("status refresh", refresh_entity, level, entity_id)


def _store_fresh(level, entity_id, fresh):
    table = LEVELS[level]
    prev_rows, _ = db.run_in_transaction([
        (f"SELECT * FROM {table} WHERE id = %s FOR UPDATE", (entity_id,)),
        (f"UPDATE {table} SET status = %s, configured_status = %s, effective_status = %s WHERE id = %s",
         (fresh.get("status"), fresh.get("configured_status") or fresh.get("status"), fresh.get("effective_status"), entity_id))])
    if not prev_rows:
        return
    prev = prev_rows[0]
    before = status_history.stored_snapshot(level, prev)
    after = dict(before, effective_status=fresh.get("effective_status"),
                 configured_status=fresh.get("configured_status") or fresh.get("status"))
    events = [e for e in status_history.diff(level, before, after, datetime.now(timezone.utc), None)
              if e["field"] in ("effective_status", "configured_status")]
    status_history.record(level, {"id": entity_id, "name": prev.get("name"),
                                  "campaign_id": entity_id if level == "campaign" else prev.get("campaign_id"),
                                  "adset_id": prev.get("adset_id")}, events, "console")


# ---------------------------------------------------------------- fresh reads (audit A1, A20)

def _cents_of(value):
    try:
        return int(value) if value not in (None, "", "0") else None
    except (TypeError, ValueError):
        return None


def fresh_budget(entity_id):
    """The daily budget Meta has right now for a campaign or ad set (None when it has none)."""
    return _cents_of(meta_client.get(entity_id, fields="daily_budget").get("daily_budget"))


def notice_budget(level, row, live):
    """A fresh read of the daily budget, before any money rule uses it: when it differs from the stored one it
    was changed outside the console since the last read, so it is recorded as such first (D2) and the 3-day rule
    sees it. Returns the row with the live amount."""
    if not live:
        return row
    if live != row.get("daily_budget_cents"):
        status_history.note_live_budget(level, row["id"], live)
    return {**row, "daily_budget_cents": live}


def forget_budget(level, entity_id):
    """Meta says this has no daily budget now (moved to the other level, or to a lifetime budget): the
    stored one is wrong and is never used as the current amount (audit A3-76)."""
    db.execute(f"UPDATE {LEVELS[level]} SET daily_budget_cents = NULL WHERE id = %s", (entity_id,))
    return ("Meta says this has no daily budget of its own now (it moved to the other level, or to a lifetime "
            "budget), so nothing was changed. Refresh the page, or change it in Ads Manager.")


PARENT_FIELDS = {"ad": "adset_id,campaign_id", "adset": "campaign_id"}


def spend_context(level, row, memo=None):
    """What turning this on can spend, read fresh from Meta: {daily_cents, lifetime_cents, end_time, where,
    holder}. The budget lives on the ad set or on the campaign (or on each ad set of a campaign without
    one); `holder` is the id that holds it, so two budgets with the same name are both counted. `idle`:
    a campaign with no ad set on, which spends nothing until one is turned on.
    `memo`: one dict shared by the items of one request, so ads in the same ad set read its budget once
    (audit A3-126); a bulk change can put each item's parents in it from one read ({(id, fields): node})."""
    memo = {} if memo is None else memo

    def read(eid, fields):
        if (eid, fields) not in memo:
            memo[eid, fields] = meta_client.get(eid, fields=fields)
        return memo[eid, fields]
    if level == "ad":
        node = read(row["id"], PARENT_FIELDS["ad"])
        chain = [("adset", node.get("adset_id")), ("campaign", node.get("campaign_id"))]
    elif level == "adset":
        node = read(row["id"], PARENT_FIELDS["adset"])
        chain = [("adset", row["id"]), ("campaign", node.get("campaign_id"))]
    else:
        chain = [("campaign", row["id"])]
    for lvl, eid in chain:
        if not eid:
            continue
        end_key = "stop_time" if lvl == "campaign" else "end_time"  # Meta: a campaign has stop_time, an ad set end_time
        node = read(eid, f"daily_budget,lifetime_budget,{end_key}")
        daily, lifetime = _cents_of(node.get("daily_budget")), _cents_of(node.get("lifetime_budget"))
        if daily or lifetime:
            name = (entity(lvl, eid) or {}).get("name") or eid
            return {"daily_cents": daily, "lifetime_cents": lifetime, "end_time": node.get(end_key) if lifetime else None,
                    "where": f"{'the ad set' if lvl == 'adset' else 'the campaign'} “{name}”", "holder": eid}
    if level == "campaign":
        if (row["id"], "adsets") not in memo:
            memo[row["id"], "adsets"] = list(meta_client.paged(f"{row['id']}/adsets", fields="daily_budget,lifetime_budget,status", limit=100))
        on = [a for a in memo[row["id"], "adsets"] if a.get("status") == "ACTIVE"]
        if not on:
            return {"daily_cents": None, "lifetime_cents": None, "end_time": None, "where": None, "holder": None, "idle": True}
        daily = sum(_cents_of(a.get("daily_budget")) or 0 for a in on)
        lifetime = sum(_cents_of(a.get("lifetime_budget")) or 0 for a in on)
        if daily or lifetime:
            return {"daily_cents": daily or None, "lifetime_cents": lifetime or None, "end_time": None,
                    "where": f"the ad sets of “{row.get('name') or row['id']}”", "holder": f"{row['id']}/adsets"}
    return {"daily_cents": None, "lifetime_cents": None, "end_time": None, "where": None, "holder": None}


def ceiling():
    return money_rules.ceiling(settings_store.get("max_daily_budget_cents"))


def last_budget(entity_id, now=None):
    """The last real change of this budget (console writes and Meta's records, 90 days), read now: the 3-day
    rule is always checked against the database at write time, never against an earlier preview."""
    return status_history.last_budgets([entity_id], now).get(entity_id)


def last_public(last):
    """A last budget change as the API shows it: {at, field, from, to, by, where} (+ day in words)."""
    if not last:
        return None
    import words
    return {"at": last["at"].isoformat(), "field": last["field"], "from": last.get("old"), "to": last.get("new"),
            "by": last.get("by"), "where": last.get("where"), "day": words.day(last["at"].astimezone(account_info.tz()))}


def change_public(change):
    """budget_change for the API: the last change readable, its times as ISO strings."""
    out = {k: v for k, v in change.items() if k not in ("last", "ok_after")}
    out["last"] = last_public(change.get("last"))
    out["ok_after"] = change["ok_after"].isoformat() if change.get("ok_after") else None
    if out["last"]:
        out["last_day"] = out["last"]["day"]
    return out


# ---------------------------------------------------------------- changes (shared with proposals)

def undo_target(raw, entity_id, actions, value, versions=()):
    """The change a Put it back names, when it is an applied change of this account (RLS), on this same thing, of the
    matching kind, and this write (`value`) restores exactly what it replaced (change_checks.reverses); else None
    (the write goes ahead as a plain change). It never skips any check."""
    try:
        change_id = int(raw)
    except (TypeError, ValueError):
        return None
    row = db.query("""SELECT id, action, old_value, new_value FROM meta_changes
                      WHERE id = %s AND ok AND entity_id = %s AND action = ANY(%s)""",
                   (change_id, entity_id, list(actions)), one=True)
    return row["id"] if row and change_checks.reverses(row, value, versions) else None


def apply_status(user, level, row, status, proposal_id=None, live=None, undo_of=None):
    """Switch on or off, compared with Meta's status read now (the stored one can be minutes old; audit
    A3-19, A3-22) unless the caller has just read it (`live`). Returns None, or what went wrong
    (NOT_SENT / UNKNOWN prefixed as above)."""
    if live is None:
        try:
            live = meta_client.get(row["id"], fields="status").get("status")
        except meta_client.MetaError as exc:
            return NOT_SENT + f"Couldn't read the status from Meta, so nothing was changed: {exc}"
    old = live or row["status"]
    if old == status:
        # Already so on Meta: nothing to send. The stored status was stale; the next read corrects it.
        log_activity("meta.status_already", subject=row["id"], details={"level": level, "name": row.get("name"), "status": status})
        resync_later()
        return None
    try:
        meta_client.post(row["id"], status=status)
    except meta_client.MetaError as exc:
        record(user, level, row, "status", old, status, False, str(exc), proposal_id)
        return (UNKNOWN if exc.unknown else "") + str(exc)
    record(user, level, row, "status", old, status, True, proposal_id=proposal_id, undo_of=undo_of)
    if not BULK_ID.get():  # a bulk change re-reads its items together at the end
        after_write("status refresh", refresh_entity, level, row["id"])
    resync_later()
    return None


def apply_budget(user, level, row, cents, proposal_id=None, accepted=None, undo_of=None):
    old = row["daily_budget_cents"]
    if not old:
        return NOT_SENT + "This one has no daily budget of its own (the budget is set one level up)."
    try:
        meta_client.post(row["id"], daily_budget=str(int(cents)))
    except meta_client.MetaError as exc:
        record(user, level, row, "budget", old, cents, False, str(exc), proposal_id)
        return (UNKNOWN if exc.unknown else "") + str(exc)
    record(user, level, row, "budget", old, cents, True, proposal_id=proposal_id, accepted=accepted, undo_of=undo_of)
    after_write("stored budget", db.execute, f"UPDATE {LEVELS[level]} SET daily_budget_cents = %s WHERE id = %s", (int(cents), row["id"]))
    return None


# ---------------------------------------------------------------- read

def _metrics(where, params, start, end):
    rows = db.query(
        f"""SELECT ad_id, COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                   COALESCE(SUM(reach),0) AS reach, COALESCE(SUM(link_clicks),0) AS link_clicks,
                   COALESCE(SUM(leads),0) AS leads, COALESCE(SUM(video_3s),0) AS video_3s,
                   COALESCE(SUM(thruplays),0) AS thruplays,
                   COALESCE(SUM(impressions) FILTER (WHERE EXISTS (SELECT 1 FROM ads v WHERE v.id = ad_daily.ad_id
                                                                   AND (v.object_type = 'VIDEO' OR v.video_id IS NOT NULL))),0) AS video_impressions
            FROM ad_daily WHERE day BETWEEN %s AND %s AND {where} GROUP BY ad_id""",
        [start, end] + params)
    return {r["ad_id"]: {k: int(v) for k, v in r.items() if k != "ad_id"} for r in rows}


def _sum(items):
    keys = ("spend_cents", "impressions", "reach", "link_clicks", "leads", "qualified", "booked", "video_3s", "thruplays", "video_impressions")
    return {k: sum(i["m"].get(k, 0) for i in items) for k in keys}


def window_from(args, live=False):
    """(key, start, end) from ?range=today|7|14|30|mtd|lastmonth|custom&from=&to=: complete days, or with live
    (what a screen shows, FU-C) through today so far."""
    key = args.get("range", "7")
    start, end = ranges.window(key, account_info.today(), args.get("from"), args.get("to"), live=live)
    return key, start, end


def live_window(args, scope_ids=None, adset_id=None):
    """A screen's window and how it compares (FU-C): (key, start, end, prev, settled, hours, live read). `prev` is the
    window "vs before" uses (vs=prev), `settled` the complete days it is compared on when today is in the window,
    `hours` yesterday up to this hour for Today. Today's rows are read from Meta first when the window has today."""
    key, start, end = window_from(args, live=True)
    today = account_info.today()
    plan = ranges.compare_plan(key, start, end, today)
    live = insights.read_today() if ranges.includes_today(start, end, today) else None
    want = args.get("vs") == "prev"
    prev = plan["before"] if want and plan["mode"] == "days" else None
    settled = plan["now"] if want and plan["note"] else None
    hours = None
    if want and plan["mode"] == "hours":
        rows = insights.yesterday_hours("adset" if adset_id else "campaign")
        if rows is not None:
            hour = account_info.local_now().hour
            key_ = "adset_id" if adset_id else "campaign_id"
            mine = [r for r in rows if (r.get(key_) == adset_id if adset_id else scope_ids is None or r.get(key_) in scope_ids)]
            hours = {**ranges.same_hours(mine, hour), "by": ranges.by_hour_words(hour)}
            if not adset_id:
                # Each campaign's own, so the Ads page can compare one picked campaign by the hour too.
                hours["campaigns"] = {cid: ranges.same_hours([r for r in mine if r.get("campaign_id") == cid], hour)
                                      for cid in {r.get("campaign_id") for r in mine if r.get("campaign_id")}}
        else:
            hours = {"by": None}
    return key, start, end, prev, settled, hours, live


def compare_payload(out, start, end, prev, settled, hours):
    """What the page needs to say how "vs before" was read (FU-C)."""
    today = account_info.today()
    out["range"]["label"] = ranges.label(start, end, today=today)
    if hours is not None:
        out["compare"] = {"mode": "hours", "by": hours.get("by")}
        if hours.get("by"):
            out["totals"]["prev"] = {k: hours[k] for k in ("spend_cents", "leads", "impressions", "link_clicks")}
            out["totals"]["cmp"] = out["totals"]["m"]
            if "campaigns" in hours:
                out["hours_by_campaign"] = hours["campaigns"]
    elif settled:
        out["compare"] = {"mode": "days", "note": "complete days", "now_label": ranges.label(*settled)}
    elif prev:
        out["compare"] = {"mode": "days", "note": None}


def _quality(aw, ap, start, end):
    return {r["ad_id"]: int(r["n"]) for r in db.query(
        f"""SELECT ad_id, COUNT(*) AS n FROM leads l WHERE {lq.counted()} AND {lq.qualified()}
            AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {aw} GROUP BY ad_id""",
        [account_info.tz_name(), start, end] + ap)}


def _booked(aw, ap, start, end):
    """Leads that booked a call, by the day the lead arrived (L1), per ad."""
    return {r["ad_id"]: int(r["n"]) for r in db.query(
        f"""SELECT ad_id, COUNT(*) AS n FROM leads l WHERE {lq.counted()} AND booked_at IS NOT NULL
            AND (created_time AT TIME ZONE %s)::date BETWEEN %s AND %s AND {aw} GROUP BY ad_id""",
        [account_info.tz_name(), start, end] + ap)}


def tree_data(user, start, end, prev=None, campaign_id=None, adset_id=None, archived=False, settled=None, hours=False):
    """Campaign → ad set → ad with each level's results for the window (and the window before, when
    prev=(start, end) is given), limited to what the person may see. settled (FU-C): the window's complete days
    when it includes today; each level then also carries `cmp`, its results over them, which "vs before"
    compares with `prev` (like with like). hours: Today, compared by the hour in the totals only, each row
    marked `vs_note` so its "vs before" cell says why it is empty."""
    days = (end - start).days + 1
    cw, cp = _scope(user, "id")
    aw, ap = _scope(user, "campaign_id")
    if campaign_id:
        cw, cp = f"{cw} AND id = %s", cp + [campaign_id]
        aw, ap = f"{aw} AND campaign_id = %s", ap + [campaign_id]
    sw, sp = (f"{aw} AND id = %s", ap + [adset_id]) if adset_id else (aw, ap)
    xw, xp = (f"{aw} AND adset_id = %s", ap + [adset_id]) if adset_id else (aw, ap)
    hidden = ("DELETED",) if archived else ("DELETED", "ARCHIVED")
    # Deleted (and, unless asked for, archived) campaigns and ad sets are left out like their ads, except the
    # one whose page this is; what they spent still counts in the totals (audit A3-104).
    shown = "(NOT (COALESCE(effective_status, '') = ANY(%s)) OR id = %s)"
    campaigns = db.query(f"SELECT * FROM campaigns WHERE {cw} AND {shown} ORDER BY effective_status = 'ACTIVE' DESC, name",
                         cp + [list(hidden), campaign_id])
    adsets = db.query(f"SELECT * FROM adsets WHERE {sw} AND {shown} ORDER BY name", sp + [list(hidden), adset_id])
    ads = db.query(f"""SELECT id, name, campaign_id, adset_id, status, configured_status, effective_status, image_url,
                              thumbnail_url, title, object_type, review_feedback, issues, created_time, updated_time
                       FROM ads WHERE {xw} AND NOT (COALESCE(effective_status, '') = ANY(%s)) ORDER BY name""",
                   xp + [list(hidden)])
    # Everything "Show archived" would bring back: ads, and ad sets or campaigns archived on their own.
    archived_n = sum(db.query(q, p, one=True)["n"] for q, p in (
        (f"SELECT COUNT(*) AS n FROM ads WHERE {xw} AND effective_status = 'ARCHIVED'", xp),
        (f"SELECT COUNT(*) AS n FROM adsets WHERE {sw} AND effective_status = 'ARCHIVED' AND id IS DISTINCT FROM %s", sp + [adset_id]),
        (f"SELECT COUNT(*) AS n FROM campaigns WHERE {cw} AND effective_status = 'ARCHIVED' AND id IS DISTINCT FROM %s", cp + [campaign_id])))
    metrics = _metrics(xw, xp, start, end)
    quality = _quality(xw, xp, start, end)
    booked = _booked(xw, xp, start, end)
    if prev:
        metrics_prev, quality_prev, booked_prev = _metrics(xw, xp, *prev), _quality(xw, xp, *prev), _booked(xw, xp, *prev)
    if settled:
        metrics_cmp, quality_cmp, booked_cmp = _metrics(xw, xp, *settled), _quality(xw, xp, *settled), _booked(xw, xp, *settled)
    lifetime = {r["ad_id"]: int(r["impressions"]) for r in db.query(
        f"SELECT ad_id, SUM(impressions) AS impressions FROM ad_daily WHERE {xw} GROUP BY ad_id", xp)}
    pending = {} if user["role"] == "client" else {r["eid"]: int(r["n"]) for r in db.query(
        """SELECT COALESCE(entity_id, payload->>'template_ad_id') AS eid, COUNT(*) AS n FROM desk_proposals
           WHERE status = 'pending' AND COALESCE(entity_id, payload->>'template_ad_id') IS NOT NULL GROUP BY 1""")}
    daily = {}
    for r in db.query(f"""SELECT ad_id, day, spend_cents, leads FROM ad_daily
                          WHERE day BETWEEN %s AND %s AND {xw} ORDER BY day""", [start, end] + xp):
        daily.setdefault(r["ad_id"], {})[r["day"].isoformat()] = (int(r["spend_cents"]), int(r["leads"]))
    days_list = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    # The Delivery track: the last 14 complete days, whatever the window (audit A3-66, A3-132).
    today = account_info.today()
    today_iso = today.isoformat()
    track_days = [today - timedelta(days=14 - i) for i in range(14)]
    delivered = {}
    for r in db.query(f"SELECT ad_id, day FROM ad_daily WHERE day BETWEEN %s AND %s AND spend_cents > 0 AND {xw}",
                      [track_days[0], track_days[-1]] + xp):
        delivered.setdefault(r["ad_id"], set()).add(r["day"])
    for ad in ads:
        ad["m"] = {**metrics.get(ad["id"], {}), "qualified": quality.get(ad["id"], 0), "booked": booked.get(ad["id"], 0)}
        if prev:
            ad["prev"] = {**metrics_prev.get(ad["id"], {}), "qualified": quality_prev.get(ad["id"], 0), "booked": booked_prev.get(ad["id"], 0)}
        if settled:
            ad["cmp"] = {**metrics_cmp.get(ad["id"], {}), "qualified": quality_cmp.get(ad["id"], 0), "booked": booked_cmp.get(ad["id"], 0)}
        if hours:
            ad["vs_note"] = "hours"
        d = daily.get(ad["id"], {})
        ad["spark"] = [{"day": k, "spend_cents": d.get(k, (0, 0))[0], "leads": d.get(k, (0, 0))[1],
                        **({"partial": True} if k == today_iso else {})} for k in days_list]
        ad["track"] = [{"day": t.isoformat(), "on": t in delivered.get(ad["id"], ())} for t in track_days]
        ad["lifetime_impressions"] = lifetime.get(ad["id"], 0)
        ad["pending_proposals"] = pending.get(ad["id"], 0)
    # Totals count every ad's spend, archived and deleted ones included (they spent real money).
    every = db.query(f"SELECT id, adset_id, campaign_id FROM ads WHERE {xw}", xp)
    every_m = [{"adset_id": a["adset_id"], "campaign_id": a["campaign_id"],
                "m": {**metrics.get(a["id"], {}), "qualified": quality.get(a["id"], 0), "booked": booked.get(a["id"], 0)},
                "p": {**metrics_prev.get(a["id"], {}), "qualified": quality_prev.get(a["id"], 0), "booked": booked_prev.get(a["id"], 0)} if prev else {},
                "c": {**metrics_cmp.get(a["id"], {}), "qualified": quality_cmp.get(a["id"], 0), "booked": booked_cmp.get(a["id"], 0)} if settled else {}}
               for a in every]
    for s in adsets:
        s["ads"] = [a for a in ads if a["adset_id"] == s["id"]]
        mine = [a for a in every_m if a["adset_id"] == s["id"]]
        s["m"] = _sum(mine)
        if prev:
            s["prev"] = _sum([{"m": a["p"]} for a in mine])
        if settled:
            s["cmp"] = _sum([{"m": a["c"]} for a in mine])
        if hours:
            s["vs_note"] = "hours"
        s["pending_proposals"] = pending.get(s["id"], 0)
    for c in campaigns:
        c["adsets"] = [s for s in adsets if s["campaign_id"] == c["id"]]
        mine = [a for a in every_m if a["campaign_id"] == c["id"]]
        c["m"] = _sum(mine)
        if prev:
            c["prev"] = _sum([{"m": a["p"]} for a in mine])
        if settled:
            c["cmp"] = _sum([{"m": a["c"]} for a in mine])
        if hours:
            c["vs_note"] = "hours"
        c["pending_proposals"] = pending.get(c["id"], 0)
        c["can_control"] = can_touch(user, c["id"]) and user["role"] != "client"
    # The account's unique reach covers every campaign: only for people who see them all.
    whole = not campaign_id and visible_campaign_ids(user) is None
    # Unique people from Meta (daily reach can't be added up) for the window, the one before, today and since
    # it started, all read together (audit A3-46). Today changes through the day, so it's kept 10 minutes.
    wanted = {}
    for level in ("ad", "adset", "campaign") + (("account",) if whole else ()):
        wanted[level, "m"] = (level, start, end, None, 1800)
        if prev:
            wanted[level, "prev"] = (level, *prev, None, 1800)
        wanted[level, "today"] = (level, today, today, None, 600)
        wanted[level, "ever"] = (level, None, None, "maximum", 1800)
    reach = insights.reach_many(wanted)
    # The daily sum where Meta is quiet.
    for level, rows_, in (("ad", ads), ("adset", adsets), ("campaign", campaigns)):
        insights.apply_reach(rows_, reach[level, "m"], "m")
        if prev:
            insights.apply_reach(rows_, reach[level, "prev"], "prev")
    # Today and since it started, next to the window: views add up, people come from Meta.
    views = {r["ad_id"]: (int(r["today"]), int(r["ever"])) for r in db.query(
        f"""SELECT ad_id, COALESCE(SUM(impressions) FILTER (WHERE day = %s), 0) AS today, COALESCE(SUM(impressions), 0) AS ever
            FROM ad_daily WHERE {xw} GROUP BY ad_id""", [today] + xp)}
    for level, rows_ in (("ad", ads), ("adset", adsets), ("campaign", campaigns)):
        r_today, r_ever = reach[level, "today"], reach[level, "ever"]
        for row in rows_:
            ids = [row["id"]] if level == "ad" else [a["id"] for a in every if a[f"{level}_id"] == row["id"]]
            v_today = sum(views.get(i, (0, 0))[0] for i in ids)
            v_ever = sum(views.get(i, (0, 0))[1] for i in ids)
            row["today"] = {"impressions": v_today, "reach": (r_today or {}).get(row["id"], 0) if r_today is not None else None}
            row["ever"] = {"impressions": v_ever, "reach": (r_ever or {}).get(row["id"], 0) if r_ever is not None else None}
    acct_today, acct_ever = (reach["account", "today"], reach["account", "ever"]) if whole else (None, None)
    reach_total = (reach["account", "m"] or {}).get("account") if whole else None
    import targets
    all_views = [views.get(a["id"], (0, 0)) for a in every]
    out = {"reach_total": reach_total,
           # Every ad in scope, listed or not (deleted versions spent real money): the page's header figures.
           "totals": {"m": _sum(every_m), "prev": _sum([{"m": a["p"]} for a in every_m]) if prev else None,
                      "cmp": _sum([{"m": a["c"]} for a in every_m]) if settled else None},
           "today_total": {"impressions": sum(v[0] for v in all_views), "reach": (acct_today or {}).get("account")} if not campaign_id else None,
           "ever_total": {"impressions": sum(v[1] for v in all_views), "reach": (acct_ever or {}).get("account")} if not campaign_id else None,
           "prev_reach_total": (reach["account", "prev"] or {}).get("account") if prev and whole else None,
           "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days, "label": ranges.label(start, end)},
           "target_qualified_cents": targets.qualified(), "tracks_bookings": followup.tracks_bookings(), "campaigns": campaigns, "last_sync": settings_store.get("last_performance_sync"), "archived": archived_n}
    if prev:
        out["prev_range"] = {"start": prev[0].isoformat(), "end": prev[1].isoformat(), "label": ranges.label(*prev)}
    return out


@bp.get("/ads")
@login_required
def tree():
    user = current_user()
    key, start, end, prev, settled, hours, live = live_window(request.args, visible_campaign_ids(user))
    out = tree_data(user, start, end, prev=prev, archived=request.args.get("archived") == "1", settled=settled, hours=hours is not None)
    out["range"]["key"] = key
    compare_payload(out, start, end, prev, settled, hours)
    import numbers_check
    out["source"] = numbers_check.source(user, start, end, scoped=visible_campaign_ids(user) is not None, live=live)
    return jsonify(out)


def ad_funnel(ad_id):
    """The watch funnel since it started, from the stored days (no Meta call)."""
    row = db.query("""SELECT COALESCE(SUM(impressions),0) AS impressions, COALESCE(SUM(video_3s),0) AS video_3s,
                             COALESCE(SUM(thruplays),0) AS thruplays, COALESCE(SUM(video_p25),0) AS p25,
                             COALESCE(SUM(video_p50),0) AS p50, COALESCE(SUM(video_p75),0) AS p75,
                             COALESCE(SUM(video_p100),0) AS p100, COALESCE(SUM(clicks_all),0) AS clicks_all,
                             COALESCE(SUM(link_clicks),0) AS link_clicks, COALESCE(SUM(reach),0) AS reach
                      FROM ad_daily WHERE ad_id = %s""", (ad_id,), one=True)
    return {k: int(v) for k, v in row.items()}


def ad_window():
    """The ad page's dates (?range=, last 30 days when none is given), through today so far (FU-C)."""
    return ranges.window(request.args.get("range", "30"), account_info.today(), request.args.get("from"), request.args.get("to"), live=True)


def _ad_series(ad_id):
    """The ad's spend and leads per day over ?range= (the shared date range); today's point is flagged partial."""
    start, end = ad_window()
    rows = {r["day"].isoformat(): r for r in db.query(
        "SELECT day, spend_cents, impressions, link_clicks, leads FROM ad_daily WHERE ad_id = %s AND day BETWEEN %s AND %s",
        (ad_id, start, end))}
    return ranges.daily_series(rows, start, end, ("spend_cents", "leads", "impressions", "link_clicks"), today=account_info.today())


def _ad_live(start, end):
    return insights.read_today() if ranges.includes_today(start, end, account_info.today()) else None


@bp.get("/ads/ad/<ad_id>/series")
@login_required
def ad_series(ad_id):
    ad = db.query("SELECT id, campaign_id, adset_id FROM ads WHERE id = %s", (ad_id,), one=True)
    if not ad or not can_touch(current_user(), ad["campaign_id"]):
        return api_error("Ad not found", 404)
    start, end = ad_window()
    live = _ad_live(start, end)
    import numbers_check
    return jsonify({"series": _ad_series(ad_id), "source": numbers_check.source(current_user(), start, end, scoped=True, live=live),
                    **status_history.marks_payload(
        current_user(), status_history.marks_scope("ad", {"id": ad_id, "campaign_id": ad["campaign_id"], "adset_id": ad.get("adset_id")}),
        start, end)})


@bp.get("/ads/ad/<ad_id>")
@login_required
def ad_detail(ad_id):
    user = current_user()
    ad = db.query("""SELECT a.*, s.name AS adset_name, s.targeting_summary, s.learning_stage,
                            c.name AS campaign_name, c.daily_budget_cents AS campaign_budget_cents,
                            s.daily_budget_cents AS adset_budget_cents
                     FROM ads a LEFT JOIN adsets s ON s.id = a.adset_id LEFT JOIN campaigns c ON c.id = a.campaign_id
                     WHERE a.id = %s""", (ad_id,), one=True)
    if not ad or not can_touch(user, ad["campaign_id"]):
        return api_error("Ad not found", 404)
    win = ad_window()
    live = _ad_live(*win)
    series = _ad_series(ad_id)
    totals = db.query("""SELECT COALESCE(SUM(spend_cents),0) AS spend_cents, COALESCE(SUM(impressions),0) AS impressions,
                                COALESCE(SUM(reach),0) AS reach, COALESCE(SUM(link_clicks),0) AS link_clicks,
                                COALESCE(SUM(leads),0) AS leads FROM ad_daily WHERE ad_id = %s""", (ad_id,), one=True)
    life = {k: int(v) for k, v in totals.items()}
    today_row = db.query("SELECT impressions, reach FROM ad_daily WHERE ad_id = %s AND day = %s", (ad_id, account_info.today()), one=True)
    life["today_impressions"] = int(today_row["impressions"]) if today_row else 0
    life["today_reach"] = int(today_row["reach"]) if today_row else 0  # one day's reach is already unique
    unique = insights.lifetime_reach(ad_id)
    if unique is not None:
        life["reach"] = unique
    else:
        life["reach_summed"] = True
    leads = db.query("""SELECT id, full_name, business_type, status, created_time, is_test FROM leads
                        WHERE ad_id = %s ORDER BY created_time DESC LIMIT 50""", (ad_id,))
    # Claude's proposals and the directions behind them are internal: clients never see them.
    proposals = [] if user["role"] == "client" else db.query(
        """SELECT p.*, t.prompt FROM desk_proposals p JOIN desk_tasks t ON t.id = p.task_id
           WHERE p.entity_id IN (%s, %s, %s) OR p.payload->>'template_ad_id' = %s
           ORDER BY p.id DESC LIMIT 20""",
        (ad_id, ad["adset_id"], ad["campaign_id"], ad_id))
    changes = db.query("""SELECT m.*, u.name AS user_name FROM meta_changes m LEFT JOIN users u ON u.id = m.user_id
                          WHERE m.entity_id IN (%s, %s, %s) ORDER BY m.id DESC LIMIT 30""",
                       (ad_id, ad["adset_id"], ad["campaign_id"]))
    ad["can_control"] = current_user()["role"] != "client"
    if user["role"] == "client":  # which change came from one of Claude's suggestions is internal too
        for c in changes:
            c["proposal_id"] = None
    else:  # a card says "Not applied" when the console's own check stopped it, as the Claude page does
        stopped = timeline.checked_refusals(changes)
        checks = change_checks_db.proposal_checks(proposals)  # D3: what happened after an applied suggestion
        for p in proposals:
            p["checked"] = p["id"] in stopped
            p["check"] = checks.get(p["id"])
    # The tests it is in (the Tests page is for admins), so the ad page links to them.
    tests = []
    if user["role"] == "admin":
        import experiments
        tests = experiments.containing(db.query("SELECT id, name, status, arms FROM experiments ORDER BY id DESC LIMIT 200"),
                                       ad_id, ad["adset_id"])
    import versions_api
    # The Delivery track (the manager's 14 complete days) and the status in words lead the Overview.
    today = account_info.today()
    track_days = [today - timedelta(days=14 - i) for i in range(14)]
    spent = {r["day"] for r in db.query("SELECT day FROM ad_daily WHERE ad_id = %s AND day BETWEEN %s AND %s AND spend_cents > 0",
                                        (ad_id, track_days[0], track_days[-1]))}
    ad["track"] = [{"day": t.isoformat(), "on": t in spent} for t in track_days]
    status_rows = status_history.timeline("ad", ad_id)
    # Claude's latest check or new version of this ad, so the Overview says what Claude is doing with it.
    claude_run = None if user["role"] == "client" else db.query(
        """SELECT id, kind, status, created_at, finished_at, (scorecard->>'overall') AS score FROM desk_tasks
           WHERE kind IN ('polish', 'render') AND options->>'ad_id' = %s ORDER BY id DESC LIMIT 1""", (ad_id,), one=True)
    # The funnel comes with the page, so the first paint doesn't wait on Meta's rankings (audit A3-123).
    return jsonify({"ad": ad, "series": series, "lifetime": life, "funnel": ad_funnel(ad_id), "versions": versions_api.for_ad(ad),
                    "leads": leads, "proposals": proposals, "changes": changes, "tests": tests,
                    "status": delivery.explain(ad, ad.get("learning_stage"), ad["track"]),
                    "timeline": status_rows, "claude_run": claude_run,
                    "history": timeline.merge(status_rows, changes, proposals, money=account_info.money, subject=ad_id,
                                              names={ad["adset_id"]: ad.get("adset_name"), ad["campaign_id"]: ad.get("campaign_name")},
                                              checks=change_checks_db.summary_for([c["id"] for c in changes], client=user["role"] == "client")),
                    **status_history.marks_payload(user, status_history.marks_scope("ad", ad), *win),
                    "formats": [{"id": f, "label": label} for f, label in PREVIEW_FORMATS],
                    "source": __import__("numbers_check").source(user, *win, scoped=True, live=live),
                    **__import__("meta_extras_api").ad_extras(ad, user)})  # AM-E: Meta's error details and picture


@bp.get("/ads/ad/<ad_id>/preview")
@login_required
def ad_preview(ad_id):
    row = entity("ad", ad_id)
    if not row or not can_touch(current_user(), row["campaign_id"]):
        return api_error("Ad not found", 404)
    fmt = request.args.get("format", "MOBILE_FEED_STANDARD")
    if fmt not in dict(PREVIEW_FORMATS):
        return api_error("Unknown preview format", 400)
    try:
        body = meta_client.get(f"{ad_id}/previews", ad_format=fmt)
    except meta_client.MetaError as exc:
        return api_error(f"Meta couldn't render this preview: {exc}", 400)
    data = (body.get("data") or [{}])[0]
    src = preview_src(data.get("body"))
    if not src:
        return api_error("Meta has no preview for this placement", 404)
    width, height = preview_size(data.get("body"))
    return jsonify({"src": src, "format": fmt, "width": width, "height": height})


# ---------------------------------------------------------------- write

def _target(level, entity_id):
    if level not in LEVELS:
        return None, api_error("Unknown level", 400)
    row = entity(level, entity_id)
    if not row:
        return None, api_error("Not found. Refresh the page.", 404)
    if not can_touch(current_user(), row["campaign_id"]):
        return None, api_error("This campaign isn't assigned to you", 403)
    return row, None


@bp.post("/ads/<level>/<entity_id>/status")
@login_required
def set_status(level, entity_id):
    row, err = _target(level, entity_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").upper()
    if status not in ("ACTIVE", "PAUSED"):
        return api_error("status must be ACTIVE or PAUSED", 400)
    if status == "ACTIVE":
        problem = turn_on_problem(level, row, data)
        if problem:
            return api_error(problem[0], problem[1], **(problem[2] if len(problem) > 2 else {}))
    error = apply_status(current_user(), level, row, status, undo_of=undo_target(data.get("undo_of"), row["id"], ("status",), status))
    if error:
        return write_error(error)
    return jsonify(entity(level, entity_id))


def turn_on_problem(level, row, data):
    """Turning something on spends money: the person must have seen what it can spend, daily or lifetime,
    read fresh now and echoed back (confirm_daily_cents / confirm_lifetime_cents). Returns
    (message, status, extra) or None."""
    try:
        ctx = spend_context(level, row)
    except meta_client.MetaError as exc:
        return (f"Couldn't read the budget from Meta, so it wasn't turned on: {exc}", 400)
    problem = money_rules.turn_on_problem(ctx, data.get("confirm_daily_cents"), data.get("confirm_lifetime_cents"))
    return (problem, 409, {"spend": ctx}) if problem else None


@bp.get("/ads/<level>/<entity_id>/spend")
@login_required
def spend(level, entity_id):
    """For the turn-on confirmation: what it can spend a day, fresh from Meta."""
    row, err = _target(level, entity_id)
    if err:
        return err
    try:
        return jsonify(spend_context(level, row))
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the budget from Meta: {exc}", 400)


@bp.post("/ads/ad/<ad_id>/archive")
@login_required
def archive_ad(ad_id):
    return _remove(ad_id, "archive")


@bp.post("/ads/ad/<ad_id>/delete")
@login_required
def delete_ad(ad_id):
    return _remove(ad_id, "delete")


def _remove(ad_id, action):
    row, err = _target("ad", ad_id)
    if err:
        return err
    user = current_user()
    problem = removal_problem(user, row, action, (request.get_json(silent=True) or {}).get("name"))
    if problem:
        return api_error(problem, 400, field="name" if "name" in problem else None)
    status = REMOVALS[action]
    try:
        meta_client.post(ad_id, status=status)
    except meta_client.MetaError as exc:
        record(user, "ad", row, action, row["status"], status, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    db.execute("UPDATE ads SET status = %s, effective_status = %s WHERE id = %s", (status, status, ad_id))
    record(user, "ad", row, action, row["status"], status, True)
    return jsonify(entity("ad", ad_id))


@bp.get("/ads/<level>/<entity_id>/budget/last")
@login_required
def budget_last(level, entity_id):
    """For the budget dialog: the last change of this budget and whether a raise now is under 3 days after
    it. From the database only (no Meta call); the write checks it again."""
    user = current_user()
    if user["role"] == "client":
        return api_error("Read-only access", 403)
    if level not in ("campaign", "adset"):
        return api_error("Budgets live on campaigns or ad sets", 400)
    row = entity(level, entity_id)
    if not row or not can_touch(user, row["campaign_id"]):
        return api_error("Not found", 404)
    now = datetime.now(timezone.utc)
    last = last_budget(entity_id, now)
    rec = money_rules.recency(last, now, row["daily_budget_cents"], row["daily_budget_cents"]) if last else None
    return jsonify({"daily_budget_cents": row["daily_budget_cents"], "last": last_public(last),
                    "recent": bool(rec and rec["recent"]), "ok_after": rec["ok_after"].isoformat() if rec else None,
                    "hours": rec["hours"] if rec else None})


@bp.post("/ads/<level>/<entity_id>/budget")
@login_required
def set_budget(level, entity_id):
    if level not in ("campaign", "adset"):
        return api_error("Budgets live on campaigns or ad sets", 400)
    row, err = _target(level, entity_id)
    if err:
        return err
    if {row.get("status"), row.get("effective_status")} & {"DELETED", "ARCHIVED"}:
        return api_error("This one is deleted or archived on Meta, so its budget can't be changed.", 409, field="budget")
    data = request.get_json(silent=True) or {}
    try:
        cents = int(data.get("daily_budget_cents"))
    except (TypeError, ValueError):
        return api_error("Enter the new daily budget in dollars", 400, field="budget")
    try:
        seen = int(data.get("from_cents"))
    except (TypeError, ValueError):
        seen = None
    try:
        live = fresh_budget(entity_id)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the budget from Meta: {exc}", 400)
    if not live:
        return api_error(forget_budget(level, entity_id), 409, field="budget")
    row = notice_budget(level, row, live)
    # The step confirmed must be the real one: whatever the stored value says (audit A3-77, A3-113).
    if seen != live:
        return api_error(f"The budget on Meta is {live / 100:,.2f} a day now, not what the page showed. "
                         "Check the new amount again.", 409, field="budget", live_cents=live)
    now = datetime.now(timezone.utc)
    change = money_rules.budget_change(live, cents, ceiling(), last_budget(entity_id, now), now)
    accept_big, accept_recent = bool(data.get("accept_big")), bool(data.get("accept_recent"))
    problem = money_rules.change_problem(change, accept_big, accept_recent)
    if problem:
        knowing = (change["big"] or change["recent"]) and not change["over_cap"] and cents >= 100
        extra = {"code": "recent_change", "last": last_public(change["last"])} if knowing and not (change["big"] and not accept_big) else {}
        return api_error(problem, 409 if knowing else 400, field="budget", **extra)
    error = apply_budget(current_user(), level, row, cents, accepted=money_rules.accepted(change, accept_big, accept_recent),
                         undo_of=undo_target(data.get("undo_of"), row["id"], ("budget",), cents))
    if error:
        return write_error(error)
    return jsonify(entity(level, entity_id))


@bp.post("/ads/ad/<ad_id>/duplicate")
@login_required
def duplicate(ad_id):
    row, err = _target("ad", ad_id)
    if err:
        return err
    name = ((request.get_json(silent=True) or {}).get("name") or f"{row['name']} - copy").strip()[:200]
    user = current_user()
    try:
        out = meta_client.post(f"{ad_id}/copies", status_option="PAUSED")
        new_id = out.get("copied_ad_id") or (out.get("ad_object_ids") or [{}])[0].get("copied_id")
        if not new_id:
            raise meta_client.MetaError("Meta didn't return the new ad's id")
    except meta_client.MetaError as exc:
        record(user, "ad", row, "duplicate", row["name"], name, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    record(user, "ad", {**row, "name": name}, "duplicate", row["name"], name, True, entity_id=new_id)
    renamed = True
    try:  # the copy exists (paused) even if naming it fails: keep its id and say so
        meta_client.post(new_id, name=name)
    except meta_client.MetaError as exc:
        renamed = False
        record(user, "ad", {**row, "name": name}, "rename", f"{row['name']} - Copy", name, False, str(exc), entity_id=new_id)
    try:
        insights.sync_structure()
    except meta_client.MetaError:
        pass
    return jsonify({"id": new_id, "renamed": renamed}), 201


# ---------------------------------------------------------------- media + new ads

def _account():
    return settings_store.get("meta_ad_account_id")


def _may_create(user):
    ids = visible_campaign_ids(user)
    return ids is None or bool(ids)


@bp.get("/media")
@login_required
def media_library():
    if not _may_create(current_user()):
        return api_error("No campaigns are assigned to you", 403)
    try:
        images = meta_client.get(f"act_{_account()}/adimages", fields="hash,url,name,width,height,created_time",
                                 limit=60).get("data", [])
        videos = meta_client.get(f"act_{_account()}/advideos", fields="id,title,picture,length,created_time,status",
                                 limit=60).get("data", [])
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't load the media library: {exc}", 400)
    items = [{"kind": "image", "hash": i["hash"], "url": i.get("url"), "name": i.get("name"),
              "width": i.get("width"), "height": i.get("height"), "created_time": i.get("created_time")} for i in images]
    items += [{"kind": "video", "video_id": v["id"], "url": v.get("picture"), "name": v.get("title"),
               "length": v.get("length"), "created_time": v.get("created_time"),
               "ready": ((v.get("status") or {}).get("video_status") == "ready")} for v in videos]
    items.sort(key=lambda i: i.get("created_time") or "", reverse=True)
    return jsonify({"items": items})


def _upload_video(path, size, name):
    account = _account()
    start = meta_client.post(f"act_{account}/advideos", upload_phase="start", file_size=str(size), timeout=60, video=True)
    session, video_id = start["upload_session_id"], start["video_id"]
    lo, hi = int(start["start_offset"]), int(start["end_offset"])
    with open(path, "rb") as fh:
        while lo < hi:
            fh.seek(lo)
            chunk = fh.read(hi - lo)
            step = meta_client.post(f"act_{account}/advideos", data={"upload_phase": "transfer",
                                    "upload_session_id": session, "start_offset": str(lo)},
                                    files={"video_file_chunk": (name, chunk, "application/octet-stream")},
                                    timeout=300, video=True)
            lo, hi = int(step["start_offset"]), int(step["end_offset"])
    meta_client.post(f"act_{account}/advideos", upload_phase="finish", upload_session_id=session, title=name,
                     timeout=60, video=True)
    return video_id


def upload_file(f, actor=None):
    if not f or not f.filename:
        return api_error("Choose a file", 400)
    if f.mimetype not in IMAGE_TYPES | VIDEO_TYPES:
        return api_error("Use a JPG or PNG image, or an MP4 or MOV video", 400)
    fd, path = tempfile.mkstemp(prefix="ebads-upload-")
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        result, problem = upload_path(path, os.path.basename(f.filename), f.mimetype, actor=actor)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return api_error(*problem) if problem else (jsonify(result), 201)


def upload_path(path, name, mime, actor=None):
    """One file on disk into the ad account's media library: (result, None) or (None, (message, status)).
    Logged like every upload (activity + meta_changes); the caller removes the file. Also used by Upload as draft
    under a Claude preview (FU-D)."""
    kind = "image" if mime in IMAGE_TYPES else "video" if mime in VIDEO_TYPES else None
    if not kind:
        return None, ("Use a JPG or PNG image, or an MP4 or MOV video", 400)
    name = os.path.basename(name or "")[:120] or f"upload.{mime.split('/')[1]}"
    try:
        size = os.path.getsize(path)
        if size > (MAX_IMAGE if kind == "image" else MAX_VIDEO):
            return None, ("That file is too big (images up to 30 MB, videos up to 250 MB)", 400)
        if kind == "image":
            with open(path, "rb") as fh:
                out = meta_client.post(f"act_{_account()}/adimages", files={"filename": (name, fh, mime)}, timeout=120)
            img = next(iter((out.get("images") or {}).values()), {})
            result = {"kind": "image", "hash": img.get("hash"), "url": img.get("url"), "name": name}
        else:
            result = {"kind": "video", "video_id": _upload_video(path, size, name), "name": name, "ready": False}
    except meta_client.MetaError as exc:
        return None, (f"Meta refused the upload: {exc}", 400)
    log_activity("meta.media_uploaded", subject=result.get("hash") or result.get("video_id"),
                 details={"kind": kind, "name": name}, actor=actor)
    try:
        from auth import current_user as _cu
        record(_cu() if actor is None else None, "account", {"id": _account(), "name": name, "campaign_id": None},
               "upload", None, f"{kind}: {name}", True, entity_id=result.get("hash") or result.get("video_id"))
    except Exception:  # noqa: BLE001 - the upload worked; the log line is extra
        log.info("upload not logged in meta_changes")
    return result, None


@bp.post("/media/upload")
@login_required
def upload():
    if not _may_create(current_user()):
        return api_error("No campaigns are assigned to you", 403)
    return upload_file(request.files.get("file"))


def _video_state(video_id):
    v = meta_client.get(video_id, fields="status,thumbnails{uri,is_preferred,width},picture")
    thumbs = (v.get("thumbnails") or {}).get("data", [])
    best = next((t for t in thumbs if t.get("is_preferred")), None) or (thumbs[0] if thumbs else {})
    return {"video_id": video_id, "ready": (v.get("status") or {}).get("video_status") == "ready",
            "processing": (v.get("status") or {}).get("processing_progress"),
            "thumbnail_url": best.get("uri") or v.get("picture")}


_videos_seen = {}  # account id -> (unix time read, set of video ids in its library)


def account_video(video_id):
    """True when the id is a video in this account's own library (digits only). Without the check,
    any signed-in person could make the console read any Graph node the System User can see."""
    import time
    if not str(video_id).isdigit():
        return False
    acct = account_ctx.current()
    at, ids = _videos_seen.get(acct, (0.0, set()))
    if video_id in ids:
        return True
    if time.time() - at < 20:  # just read: it isn't there
        return False
    ids = {v["id"] for v in meta_client.paged(f"act_{_account()}/advideos", fields="id", limit=200)}
    _videos_seen[acct] = (time.time(), ids)
    return video_id in ids


@bp.get("/media/video/<video_id>")
@login_required
def video_status(video_id):
    if not _may_create(current_user()) or current_user()["role"] == "client":
        return api_error("No campaigns are assigned to you", 403)
    try:
        if not account_video(video_id):
            return api_error("That video isn't in this account's media library", 404)
        return jsonify(_video_state(video_id))
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)


@bp.get("/ads/new/options")
@login_required
def new_options():
    user = current_user()
    # Only ad sets a new ad can go into (Meta refuses deleted and archived ones), delivering first.
    aw, ap = _scope(user, "s.campaign_id")
    adsets = db.query(f"""SELECT s.id, s.name, s.effective_status, c.name AS campaign_name FROM adsets s
                          JOIN campaigns c ON c.id = s.campaign_id
                          WHERE {aw} AND COALESCE(s.effective_status, '') NOT IN ('DELETED', 'ARCHIVED')
                            AND COALESCE(c.effective_status, '') NOT IN ('DELETED', 'ARCHIVED')
                          ORDER BY (s.effective_status IS NOT DISTINCT FROM 'ACTIVE') DESC, c.name, s.name""", ap)
    tw, tp = _scope(user, "campaign_id")
    templates = db.query(f"""SELECT id, name, adset_id, title, body, cta_type, image_url, object_type
                             FROM ads WHERE {tw} AND COALESCE(effective_status, '') <> 'DELETED'
                             ORDER BY (effective_status IS NOT DISTINCT FROM 'ACTIVE') DESC, (effective_status IS NOT DISTINCT FROM 'ARCHIVED'),
                                      created_time DESC NULLS LAST""", tp)
    return jsonify({"adsets": adsets, "templates": templates, "cta_types": CTA_TYPES})


def template_media(spec):
    """The image or video an existing ad's story spec uses, in build_story_spec's shape."""
    if spec.get("video_data"):
        v = spec["video_data"]
        return {"kind": "video", "video_id": v.get("video_id"), "thumbnail_url": v.get("image_url")}
    if spec.get("link_data"):
        return {"kind": "image", "hash": spec["link_data"].get("image_hash")}
    return None


def prepare_creative(user, data):
    """Check the inputs and build the creative an ad would get, from an existing ad's setup
    with new media and words. Returns (ctx, None) or (None, (message, http_status)); Meta
    errors propagate. Used to create the ad and to preview it before it exists."""
    adset_id = data.get("adset_id")
    template = db.query("SELECT id, name, adset_id, creative_id, campaign_id FROM ads WHERE id = %s",
                        (data.get("template_ad_id"),), one=True) if data.get("template_ad_id") else None
    if data.get("template_ad_id") and not template:
        return None, ("The ad it starts from isn't there any more. Pick another.", 400)
    if template and not adset_id:
        adset_id = template["adset_id"]
    adset = db.query("""SELECT s.id, s.name, s.campaign_id,
                                 s.effective_status IN ('DELETED', 'ARCHIVED') OR c.effective_status IN ('DELETED', 'ARCHIVED') AS gone
                          FROM adsets s JOIN campaigns c ON c.id = s.campaign_id WHERE s.id = %s""", (adset_id,), one=True)
    if not adset:
        return None, ("Pick the ad set", 400)
    if not can_touch(user, adset["campaign_id"]) or (template and not can_touch(user, template["campaign_id"])):
        return None, ("This campaign isn't assigned to you", 403)
    if adset.pop("gone"):
        return None, ("That ad set was deleted or archived on Meta. Pick another.", 400)
    name = (data.get("name") or "").strip()[:200]
    body = (data.get("body") or "").strip()
    title = (data.get("title") or "").strip()[:255]
    media = dict(data.get("media") or {})
    cta = data.get("cta_type") or None
    form_id = str(data.get("form_id") or "").strip() or None
    missing = creative_build.problems({**data, "adset_id": adset_id}, CTA_TYPES)
    if missing:
        return None, (missing[0][1], 400)
    if template:
        try:
            tpl = meta_client.get(template["creative_id"], fields="object_story_spec,degrees_of_freedom_spec")
        except meta_client.MetaError:
            tpl = meta_client.get(template["creative_id"], fields="object_story_spec")
    else:
        # From scratch (a new account's first ads): the account's Page, the chosen lead form, no
        # Advantage+ creative changes (the skill's advice for a first test).
        page = settings_store.get("meta_page_id")
        if not page:
            return None, ("Add this account's Facebook Page in Settings → Meta first", 400)
        cta = cta or "SIGN_UP"
        tpl = {"object_story_spec": {"page_id": page}}
    story = tpl.get("object_story_spec")
    if not story:
        return None, ("That ad can't be used as a starting point (it has no single image or video). Pick another.", 400)
    if media["kind"] == "same":
        media = template_media(story)
        if not media:
            return None, ("Couldn't find the starting ad's image or video", 400)
    elif media["kind"] == "video":
        if not account_video(str(media["video_id"])):
            return None, ("That video isn't in this account's media library", 400)
        state = _video_state(media["video_id"])
        if not state["ready"]:
            return None, ("Meta is still processing that video. Try again in a minute.", 409)
        media["thumbnail_url"] = state["thumbnail_url"]
    return {"name": name, "adset": adset, "template": template,
            "spec": build_story_spec(story, media, body, title, cta, form_id),
            "dof": tpl.get("degrees_of_freedom_spec")}, None


def create_ad_from(user, data, proposal_id=None, sync=True):
    """Create an ad (always switched off). Returns (ad_id, None) or (None, (message, http_status, outcome)):
    outcome "not_sent" (refused before anything reached Meta: a check or a read), "refused" (Meta said no)
    or "unknown" (Meta didn't answer a write, so the ad may exist). Only writes land in meta_changes."""
    try:
        ctx, err = prepare_creative(user, data)
    except meta_client.MetaError as exc:
        return None, (f"Couldn't read from Meta, so nothing was created: {exc}", 400, "not_sent")
    if err:
        return None, (*err, "not_sent")
    name = ctx["name"]
    row = {"id": (ctx["template"] or ctx["adset"])["id"], "name": name, "campaign_id": ctx["adset"]["campaign_id"]}
    payload = {"name": f"{name} creative", "object_story_spec": json.dumps(ctx["spec"])}
    if ctx["dof"]:
        payload["degrees_of_freedom_spec"] = json.dumps(ctx["dof"])
    try:
        creative = meta_client.post(f"act_{_account()}/adcreatives", data=payload)
        ad = meta_client.post(f"act_{_account()}/ads", data={
            "name": name, "adset_id": ctx["adset"]["id"], "status": "PAUSED",
            "creative": json.dumps({"creative_id": creative["id"]})})
    except meta_client.MetaError as exc:
        record(user, "ad", row, "create", None, name, False, str(exc), proposal_id)
        return None, (str(exc), 400, "unknown") if exc.unknown else (f"Meta refused: {exc}", 400, "refused")
    record(user, "ad", {**row, "id": ad["id"]}, "create", None, name, True, proposal_id=proposal_id)
    import concepts_api
    if ctx["template"]:
        after_write("copying tags", concepts_api.copy_tags, ctx["template"]["id"], ad["id"])
    if sync:
        after_write("structure sync", insights.sync_structure)
    return ad["id"], None


def new_ad_problems(user, data):
    """[(field, message)] for New ad, without asking Meta: the checks that run before the ad is created,
    every one at once (9.4e: the page marks each field before anything is sent)."""
    out = creative_build.problems(data, CTA_TYPES)
    adset_id = str(data.get("adset_id") or "")
    if adset_id and not any(f == "adset_id" for f, _ in out):
        adset = db.query("""SELECT s.campaign_id, s.effective_status IN ('DELETED', 'ARCHIVED') OR c.effective_status IN ('DELETED', 'ARCHIVED') AS gone
                            FROM adsets s JOIN campaigns c ON c.id = s.campaign_id WHERE s.id = %s""", (adset_id,), one=True)
        if not adset or not can_touch(user, adset["campaign_id"]):
            out.insert(0, ("adset_id", "Pick the ad set it goes in"))
        elif adset["gone"]:
            out.insert(0, ("adset_id", "That ad set was deleted or archived on Meta. Pick another."))
    tpl = str(data.get("template_ad_id") or "")
    if tpl:
        row = db.query("SELECT campaign_id FROM ads WHERE id = %s", (tpl,), one=True)
        if not row or not can_touch(user, row["campaign_id"]):
            out.insert(1 if out and out[0][0] == "adset_id" else 0, ("template_ad_id", "The ad it starts from isn't there any more. Pick another."))
    elif not settings_store.get("meta_page_id"):
        out.insert(0, ("template_ad_id", "Add this account's Facebook Page in Settings → Meta first"))
    return out


@bp.post("/ads/new/check")
@login_required
def check_new_ad():
    user = current_user()
    if user["role"] == "client" or not _may_create(user):
        return api_error("No campaigns are assigned to you", 403)
    return jsonify({"problems": [{"field": f, "message": m} for f, m in new_ad_problems(user, request.get_json(silent=True) or {})]})


@bp.post("/ads/new")
@login_required
def create_ad():
    data = request.get_json(silent=True) or {}
    user = current_user()
    draft_id = str(data.get("draft_id") or "")[:30] or None  # AM-B: filled in from an Ads Manager draft (owner and admins)
    if draft_id:
        import drafts_api
        if user["role"] != "admin":
            return api_error("Only admins finish drafts from Ads Manager", 403)
        why = drafts_api.claim_problem(draft_id, "ad", bool(data.get("again")))
        if why:
            return api_error(why[0], why[1], **why[2])
    ad_id, err = create_ad_from(user, data)
    if err:
        return api_error(err[0], err[1])
    if draft_id:
        drafts_api.mark_finished(draft_id, f"ad:{ad_id}")
    return jsonify({"id": ad_id}), 201


# ---------------------------------------------------------------- proposals

def proposal_target(p):
    tid = proposal_target_id(p)
    return find_entity(tid) if tid else (None, None)


def proposal_plan(p, apply_as=None):
    """What approving does, read fresh from Meta, for the confirmation (audit A1, A20)."""
    if p["kind"] in ("experiment", "tags"):
        return {"kind": p["kind"]}
    if p["kind"] == "spend_limit":
        import spend_limit
        kind, value = proposal_action(p, None)
        # The ad account it names must still be this account's: an admin may have pointed it at another one since.
        wrong = money_rules.limit_account_problem(p.get("entity_id"), spend_limit.act())
        if kind == "unclear" or wrong:
            return {"kind": "unclear", "problem": value if kind == "unclear" else wrong}
        return {"kind": "spend_limit", **spend_limit.plan(value, remove=value is None)}
    level, row = proposal_target(p)
    action = proposal_action(p, row, apply_as)
    if not action:
        return {"kind": "record"}
    kind, value = action
    if kind == "create":
        return {"kind": "create"}
    if kind == "update":
        ad = db.query("SELECT name, effective_status FROM ads WHERE id = %s", (value["template_ad_id"],), one=True)
        if not ad:
            return {"kind": "unclear", "problem": "The ad this was made for isn't there any more."}
        return {"kind": "update", "name": ad["name"], "live": ad["effective_status"] == "ACTIVE", "ad_id": value["template_ad_id"]}
    if kind == "vertical":
        ad = db.query("SELECT name, effective_status FROM ads WHERE id = %s", (value["template_ad_id"],), one=True)
        if not ad:
            return {"kind": "unclear", "problem": "The ad this was made for isn't there any more."}
        return {"kind": "vertical", "name": ad["name"], "live": ad["effective_status"] == "ACTIVE"}
    if kind == "unclear":
        return {"kind": "unclear", "problem": value}
    if kind == "status":
        live = meta_client.get(row["id"], fields="status").get("status") or row["status"]
        out = {"kind": "status", "to": value, "name": row["name"], "level": level, "from": live, "already": live == value}
        if value == "ACTIVE":
            out["spend"] = spend_context(level, row)
        return out
    live = fresh_budget(row["id"])
    if not live:
        return {"kind": "unclear", "problem": forget_budget(level, row["id"])}
    notice_budget(level, row, live)
    now = datetime.now(timezone.utc)
    change = money_rules.budget_change(live, value, ceiling(), last_budget(row["id"], now), now)
    return {"kind": "budget", "name": row["name"], "level": level, **change_public(change),
            "problem": money_rules.change_problem(change, True, True)}


@bp.get("/proposals/<int:proposal_id>/check")
@login_required
def check_proposal(proposal_id):
    p = db.query("SELECT * FROM desk_proposals WHERE id = %s", (proposal_id,), one=True)
    if not p or current_user()["role"] == "client":
        return api_error("Suggestion not found", 404)
    level, row = proposal_target(p)
    if row and not can_touch(current_user(), row["campaign_id"]):
        return api_error("Suggestion not found", 404)
    if p["kind"] == "spend_limit" and current_user()["role"] != "admin":
        return api_error(LIMIT_ADMINS, 403)
    try:
        return jsonify(proposal_plan(p, request.args.get("as")))
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the live budget from Meta: {exc}", 400)


def review_plan(p):
    """proposal_plan, plus "Make a new version" requests, which start a run on the Mac."""
    if desk_view.is_version_request(p):
        task = db.query("SELECT id, options FROM desk_tasks WHERE id = %s", (p["task_id"],), one=True)
        ad = desk_view.proposal_ad(p, task)
        if ad:
            return {"kind": "render", "ad_id": ad, "from_task": task["id"], "note": p.get("rationale") or p["title"]}
    return proposal_plan(p)


@bp.post("/proposals/review")
@login_required
def review_proposals():
    """One fresh read of Meta for everything about to be accepted together. Applying still goes
    through /approve one by one, so every money rule holds for each."""
    ids = [int(i) for i in (request.get_json(silent=True) or {}).get("ids") or [] if str(i).isdigit()][:100]
    rows = db.query("SELECT * FROM desk_proposals WHERE id = ANY(%s) AND status = 'pending' ORDER BY id", (ids,))
    user = current_user()
    pairs = []
    for p in rows:
        level, row = proposal_target(p)
        if (row and not can_touch(user, row["campaign_id"])) or (not row and user["role"] != "admin" and p["kind"] != "tags"):
            continue
        try:
            pairs.append((p, review_plan(p)))
        except meta_client.MetaError as exc:
            pairs.append((p, {"kind": "unclear", "problem": f"Couldn't read Meta just now, so this one waits: {exc}"}))
    return jsonify({"items": desk_view.review(pairs, account_info.currency()), "gone": len(ids) - len(rows)})


@bp.post("/proposals/<int:proposal_id>/undecline")
@login_required
def undecline(proposal_id):
    """The Undo after a decline: only the person who declined, within ten minutes."""
    done = db.execute("""UPDATE desk_proposals SET status = 'pending', decided_by = NULL, decided_at = NULL
                         WHERE id = %s AND status = 'declined' AND decided_by = %s AND decided_at > now() - interval '10 minutes'
                         RETURNING id""", (proposal_id, current_user()["id"]), returning=True)
    if not done:
        return api_error("It's too late to undo that", 409)
    log_activity("proposal.undeclined", subject=str(proposal_id))
    return jsonify({"status": "pending"})


@bp.post("/proposals/<int:proposal_id>/<decision>")
@login_required
def decide(proposal_id, decision):
    if decision not in ("approve", "decline"):
        return api_error("Accept or decline only", 400)
    user = current_user()
    p = db.query("SELECT * FROM desk_proposals WHERE id = %s", (proposal_id,), one=True)
    if not p:
        return api_error("Suggestion not found", 404)
    if p["status"] != "pending":
        return api_error("This suggestion was already decided", 409)
    level, row = proposal_target(p)
    if row and not can_touch(user, row["campaign_id"]):
        return api_error("This campaign isn't assigned to you", 403)
    if p["kind"] == "spend_limit" and user["role"] != "admin":
        return api_error(LIMIT_ADMINS, 403)
    if not row and user["role"] != "admin" and p["kind"] not in ("tags",):
        return api_error("Only admins can decide account-wide suggestions", 403)
    if decision == "decline":
        done = db.execute("""UPDATE desk_proposals SET status = 'declined', decided_by = %s, decided_at = now()
                             WHERE id = %s AND status = 'pending' RETURNING id""", (user["id"], proposal_id), returning=True)
        if not done:
            return api_error("This suggestion was already decided", 409)
        log_activity("proposal.declined", subject=str(proposal_id), details={"title": p["title"]})
        return jsonify({"status": "declined"})
    # Claimed before anything reaches Meta: a double click or a second tab gets a 409, not a second ad.
    claimed = db.execute("""UPDATE desk_proposals SET status = 'applying', applying_at = now()
                            WHERE id = %s AND status = 'pending' RETURNING applying_at""", (proposal_id,), returning=True)
    if not claimed:
        return api_error("This suggestion is already being applied or was decided", 409)
    meta_client.watch_writes()
    try:
        return _approve(user, p, level, row, request.get_json(silent=True) or {})
    finally:
        release_claim(proposal_id, claimed["applying_at"], user["id"], sent=meta_client.writes_sent())


def release_claim(proposal_id, since, user_id=None, ended=True, sent=False):
    """A claim nothing closed: waiting again only if nothing was sent to Meta since the claim; applied if a
    write went through; otherwise kept as "check Ads Manager", never sent twice (audit A3-40, A3-68)."""
    if not db.query("SELECT 1 FROM desk_proposals WHERE id = %s AND status = 'applying'", (proposal_id,), one=True):
        return
    changes = db.query("SELECT ok FROM meta_changes WHERE proposal_id = %s AND created_at >= %s", (proposal_id, since))
    status = desk_view.after_claim(changes, ended, sent)
    if status == "pending":
        db.execute("UPDATE desk_proposals SET status = 'pending', applying_at = NULL WHERE id = %s AND status = 'applying'", (proposal_id,))
        return
    if db.execute("""UPDATE desk_proposals SET status = %s, decided_by = COALESCE(decided_by, %s), decided_at = now()
                     WHERE id = %s AND status = 'applying' RETURNING id""", (status, user_id, proposal_id), returning=True):
        log_activity(f"proposal.{status}", subject=str(proposal_id), details={"after": "an interrupted apply"},
                     actor=None if user_id else "system", user_id=user_id)


def sweep_applying(minutes=10):
    """Proposals left 'applying' by a request that never finished (a restart mid-apply): settled from
    what reached Meta, so they don't block their conversation forever (audit A3-79)."""
    for r in db.query(f"""SELECT id, COALESCE(applying_at, created_at) AS since FROM desk_proposals
                           WHERE status = 'applying' AND COALESCE(applying_at, created_at) < now() - interval '{int(minutes)} minutes'"""):
        release_claim(r["id"], r["since"], ended=False)


def _approve(user, p, level, row, data):
    proposal_id = p["id"]
    if p["kind"] == "experiment":
        return approve_experiment(user, p)
    if p["kind"] == "tags":
        import concepts_api
        pl = p.get("payload") or {}
        ad = db.query("SELECT campaign_id FROM ads WHERE id = %s", (pl.get("ad_id"),), one=True)
        if not ad or not can_touch(user, ad["campaign_id"]):
            return api_error("Ad not found", 404)
        concepts_api.save_tags(pl["ad_id"], pl.get("tags") or {}, "claude")
        db.execute("UPDATE desk_proposals SET status = 'applied', decided_by = %s, decided_at = now() WHERE id = %s", (user["id"], p["id"]))
        log_activity("proposal.applied", subject=str(p["id"]), details={"title": p["title"], "tags": pl.get("tags")})
        return jsonify({"status": "applied", "applied": True})

    def close(status):
        db.execute("UPDATE desk_proposals SET status = %s, decided_by = %s, decided_at = now() WHERE id = %s",
                   (status, user["id"], proposal_id))
        log_activity(f"proposal.{status}", subject=str(proposal_id), details={"title": p["title"]})

    action = proposal_action(p, row, data.get("apply_as"))
    if not action:
        close("approved")
        import desk_api
        import desk_view
        if desk_view.needs_follow_through(p):
            return jsonify({"status": "approved", "applied": False, "task_id": desk_api.continue_accepted(p, user["id"]),
                            "note": "Claude is picking this up on your Mac."})
        return jsonify({"status": "approved", "applied": False,
                        "note": "Recorded. This one isn't a simple on/off or budget change, so nothing was changed on Meta."})
    kind, value = action
    if kind == "unclear":
        return api_error(value, 400)
    if kind == "spend_limit":
        return approve_spend_limit(user, p, value, data, close)
    new_id = None
    try:
        if kind == "status" and value == "ACTIVE":
            problem = turn_on_problem(level, row, data)
            if problem:
                return api_error(problem[0], problem[1], **(problem[2] if len(problem) > 2 else {}))
        if kind == "budget":
            live = fresh_budget(row["id"])
            if not live:
                return api_error(forget_budget(level, row["id"]), 409)
            row = notice_budget(level, row, live)
            try:
                echoed = (int(data.get("from_cents")), int(data.get("to_cents")))
            except (TypeError, ValueError):
                echoed = None
            if echoed != (live, value):
                return api_error(f"Check the amounts again: the budget on Meta is {live / 100:,.2f} a day now.", 409,
                                 plan=proposal_plan(p))
            # The 3-day rule is read again now, never taken from the plan shown at /check (D2).
            now = datetime.now(timezone.utc)
            change = money_rules.budget_change(live, value, ceiling(), last_budget(row["id"], now), now)
            accept_big, accept_recent = bool(data.get("accept_big")), bool(data.get("accept_recent"))
            problem = money_rules.change_problem(change, accept_big, accept_recent)
            if problem:
                return api_error(problem, 409, **({"code": "recent_change"} if change["recent"] and not accept_recent
                                                   and not (change["big"] and not accept_big) and not change["over_cap"] else {}))
            budget_accepted = money_rules.accepted(change, accept_big, accept_recent)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the live budget from Meta, so nothing was changed: {exc}", 400)
    if kind == "create":
        new_id, err = create_ad_from(user, {**value, "name": value.get("name") or p["title"]}, proposal_id)
        error = err and ({"not_sent": NOT_SENT, "unknown": UNKNOWN}.get(err[2], "") + err[0])
    elif kind == "update":
        import versions_api
        error = versions_api.update_ad(user, value, proposal_id)
    elif kind == "vertical":
        error = add_vertical(user, value["template_ad_id"], value["vertical"]["video_id"], proposal_id, value["vertical"].get("image_hash"))
    elif kind == "status":
        error = apply_status(user, level, row, value, proposal_id)
    else:
        error = apply_budget(user, level, row, value, proposal_id, accepted=budget_accepted)
    if error and error.startswith(NOT_SENT):
        return api_error(error_words(error), 409)  # nothing reached Meta: it stays waiting
    if error and error.startswith(UNKNOWN):
        close("unknown")
        return api_error(f"{error_words(error)} This suggestion is marked “check Ads Manager” and can't be applied again.", 400)
    close("failed" if error else "applied")
    if error and error.startswith(CHECKED):
        return api_error(f"Not applied: {error_words(error)}", 400)
    if error:
        return api_error(f"Accepted, but Meta refused the change: {error}", 400)
    return jsonify({"status": "applied", "applied": True, "ad_id": new_id,
                    "updated_ad": value["template_ad_id"] if kind == "update" else None})


LIMIT_ADMINS = "Only an admin of this account can change its spending limit"
_MISSING = object()


def _echoed_cents(data, key):
    """An amount the confirmation echoes back: cents, None for "no limit", or _MISSING when absent or not a number."""
    if key not in data:
        return _MISSING
    v = data[key]
    if v is None:
        return None
    if isinstance(v, bool):
        return _MISSING
    try:
        return int(v) if str(v).strip().lstrip("-").isdigit() else _MISSING
    except (TypeError, ValueError):
        return _MISSING


def approve_spend_limit(user, p, value, data, close):
    """FU-B: accepting a spend_limit suggestion. Owner or this account's admin (RLS pins the suggestion to this
    account); the sheet echoes the old and new amounts it showed; a removal needs confirm_remove (its own dialog)."""
    import spend_limit
    if user["role"] != "admin":
        return api_error(LIMIT_ADMINS, 403)
    wrong = money_rules.limit_account_problem(p.get("entity_id"), spend_limit.act())
    if wrong:
        return api_error(wrong, 409)
    remove = value is None
    to_cents, from_cents = _echoed_cents(data, "to_cents"), _echoed_cents(data, "from_cents")
    if bool(data.get("remove")) != remove or from_cents is _MISSING or (not remove and to_cents != value):
        try:
            fresh = proposal_plan(p)
        except meta_client.MetaError:
            fresh = None
        return api_error("Check the amounts again: this isn't the change the suggestion makes.", 409, plan=fresh)
    error, info = spend_limit.apply(user, value, remove=remove, confirm_remove=data.get("confirm_remove") is True,
                                    from_cents=from_cents, proposal_id=p["id"], accept_big=data.get("accept_big") is True)
    if error and error.startswith(NOT_SENT):
        return api_error(error_words(error), 400 if info.get("code") else 409, **({"plan": info["plan"]} if info.get("plan") else {}))
    if error and error.startswith(UNKNOWN):
        close("unknown")
        return api_error(f"{error_words(error)} This suggestion is marked “check Ads Manager” and can't be applied again.", 400)
    close("failed" if error else "applied")
    if error and error.startswith(CHECKED):
        return api_error(f"Not applied: {error_words(error)}", 400)
    if error:
        return api_error(f"Accepted, but Meta refused the change: {error}", 400)
    return jsonify({"status": "applied", "applied": True, "limit_cents": info.get("limit_cents")})


def approve_experiment(user, p):
    """Approving a test Claude suggested starts tracking it on the Tests page. Nothing changes on Meta."""
    import experiments_api
    if user["role"] != "admin":
        return api_error("Only admins can start tracking a test", 403)
    fields, err = experiments_api.clean(p.get("payload") or {})
    if err:
        return api_error(f"This test can't be tracked as proposed: {err[0]}", 400)
    exp_id = experiments_api.create(fields, user["id"], p["id"])
    db.execute("UPDATE desk_proposals SET status = 'applied', decided_by = %s, decided_at = now() WHERE id = %s", (user["id"], p["id"]))
    log_activity("proposal.applied", subject=str(p["id"]), details={"title": p["title"], "experiment_id": exp_id})
    return jsonify({"status": "applied", "applied": True, "experiment_id": exp_id})


def vertical_preview_spec(user, data):
    """The ad as Reels and Stories would show it after the update: its words and button with the 9:16
    video (a single-video spec, which generatepreviews renders reliably)."""
    ad = db.query("SELECT id, campaign_id, creative_id FROM ads WHERE id = %s", (data.get("template_ad_id"),), one=True)
    if not ad or not can_touch(user, ad["campaign_id"]) or not ad["creative_id"]:
        return None, ("The ad this was made for isn't there any more", 404)
    vid = str((data.get("vertical") or {}).get("video_id") or "")
    if not account_video(vid):
        return None, ("Claude's 9:16 video isn't in this account's media library", 400)
    story = (meta_client.get(ad["creative_id"], fields="object_story_spec").get("object_story_spec") or {})
    if not story.get("video_data"):
        return None, ("Only a single-video ad has this preview", 400)
    thumb = _video_state(vid)["thumbnail_url"]
    video = {**story["video_data"], "video_id": vid}
    video.pop("image_hash", None)
    cover = (data.get("vertical") or {}).get("image_hash")
    if cover:  # Meta takes only one of image_url and image_hash in video_data
        video.pop("image_url", None)
        video["image_hash"] = cover
    elif thumb:
        video["image_url"] = thumb
    return {**story, "video_data": video}, None


@bp.get("/ads/creative/<creative_id>/inspect")
@admin_required
def inspect_creative(creative_id):
    """Read-only: what Meta stored for one of this account's creatives, to see why an update failed."""
    if not creative_id.isdigit():
        return api_error("Not a creative id", 400)
    try:
        body = meta_client.get(creative_id, fields="name,account_id,object_type,object_story_spec,asset_feed_spec,degrees_of_freedom_spec")
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    if str(body.get("account_id")) != str(_account()):
        return api_error("Not a creative of this account", 404)
    return jsonify(body)


@bp.get("/proposals/<int:proposal_id>/preview")
@login_required
def proposal_preview(proposal_id):
    """Meta's own rendering of a proposed new ad before it exists (generatepreviews)."""
    p = db.query("SELECT * FROM desk_proposals WHERE id = %s", (proposal_id,), one=True)
    if not p or p["kind"] != "creative" or not p.get("payload") or current_user()["role"] == "client":
        return api_error("Only new-ad suggestions have a preview", 404)
    fmt = request.args.get("format", "MOBILE_FEED_STANDARD")
    if fmt not in dict(PREVIEW_FORMATS):
        return api_error("Unknown preview format", 400)
    data = {**p["payload"], "name": p["payload"].get("name") or p["title"]}
    try:
        if (data.get("vertical") or {}).get("video_id"):
            spec, err = vertical_preview_spec(current_user(), data)
        else:
            ctx, err = prepare_creative(current_user(), data)
            spec = ctx and ctx["spec"]
        if err:
            return api_error(err[0], err[1])
        body = meta_client.get(f"act_{_account()}/generatepreviews", ad_format=fmt,
                               creative=json.dumps({"object_story_spec": spec}))
    except meta_client.MetaError as exc:
        return api_error(f"Meta couldn't render this preview: {exc}", 400)
    first = (body.get("data") or [{}])[0]
    src = preview_src(first.get("body"))
    if not src:
        return api_error("Meta has no preview for this placement", 404)
    width, height = preview_size(first.get("body"))
    return jsonify({"src": src, "format": fmt, "width": width, "height": height})


@bp.get("/proposals/<int:proposal_id>")
@login_required
def get_proposal(proposal_id):
    p = db.query("SELECT * FROM desk_proposals WHERE id = %s", (proposal_id,), one=True)
    if not p or current_user()["role"] == "client":
        return api_error("Suggestion not found", 404)
    tid = (p.get("payload") or {}).get("template_ad_id") or p.get("entity_id")
    level, row = find_entity(tid) if tid else (None, None)
    if row and not can_touch(current_user(), row["campaign_id"]):
        return api_error("Suggestion not found", 404)
    return jsonify(p)


@bp.post("/ads/sync")
@login_required
def sync_now():
    try:
        out = insights.sync_all(days=30)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    return jsonify(out)


# ---------------------------------------------------------------- 9:16 for Reels (Meta's advice, Claude's fix)

def add_vertical(user, ad_id, video_id, proposal_id=None, image_hash=None):
    """Put a 9:16 video on an ad for Reels and Stories; feeds keep its 4:5 video, the words and the
    lead form stay. A new creative is made and read back first, so a copy Meta stored wrongly never
    reaches the running ad. Returns None, or what went wrong."""
    import placements
    ad = db.query("SELECT id, name, campaign_id, creative_id, effective_status, title, body FROM ads WHERE id = %s", (ad_id,), one=True)
    if not ad or not ad["creative_id"]:
        return NOT_SENT + "That ad has no creative Meta can show yet."
    if not can_touch(user, ad["campaign_id"]):
        return NOT_SENT + "This campaign isn't assigned to you"
    if ad["effective_status"] in ("ARCHIVED", "DELETED"):
        return NOT_SENT + "That ad is archived, so it can't be updated."
    row = {"id": ad["id"], "name": ad["name"], "campaign_id": ad["campaign_id"]}
    video_id = str(video_id)
    try:
        cr = meta_client.get(ad["creative_id"], fields="object_story_spec,asset_feed_spec,degrees_of_freedom_spec,instagram_user_id")
        if placements.has_placements(cr):
            return NOT_SENT + "This ad already shows different media per placement. Change it in Ads Manager."
        if not account_video(video_id):
            return NOT_SENT + "Claude's 9:16 video isn't in this account's media library."
        state = _video_state(video_id)
        if not state["ready"]:
            return NOT_SENT + "Meta is still processing the 9:16 video. Try again in a minute."
        story, feed = placements.build(cr.get("object_story_spec") or {}, {"video_id": video_id, "thumbnail_url": state["thumbnail_url"], "image_hash": image_hash},
                                       instagram_user_id=cr.get("instagram_user_id"))
    except ValueError as exc:
        return NOT_SENT + str(exc)
    except meta_client.MetaError as exc:
        return NOT_SENT + f"Couldn't read the ad from Meta, so nothing was changed: {exc}"
    data = {"name": f"{ad['name']} · 4:5 feeds + 9:16 Reels"[:200], "object_story_spec": json.dumps(story),
            "asset_feed_spec": json.dumps(feed)}
    if cr.get("degrees_of_freedom_spec"):
        data["degrees_of_freedom_spec"] = json.dumps(cr["degrees_of_freedom_spec"])
    new = None
    try:
        new = meta_client.post(f"act_{_account()}/adcreatives", data=data)
        made = meta_client.get(new["id"], fields="object_story_spec,asset_feed_spec,instagram_user_id")
        problem = placements.readback_problem(cr.get("object_story_spec"), made, video_id, instagram="instagram_user_id" in story)
        if problem:
            log.warning("9:16 read-back refused for ad %s: %s", ad["id"], placements.describe(made))
            record(user, "ad", row, "placement_media", ad["creative_id"], f"creative {new['id']} not used", False, problem, proposal_id)
            return f"{CHECKED}{problem} The running ad wasn't changed."
        new = {**new, "switching": True}
        put_creative(ad["id"], new["id"])
    except meta_client.MetaError as exc:
        record(user, "ad", row, "placement_media", ad["creative_id"], f"9:16 video {video_id}", False, str(exc), proposal_id)
        if exc.unknown and new and new.get("switching"):
            return UNKNOWN + SWITCH_UNKNOWN
        return f"{exc}. The running ad wasn't changed."
    record(user, "ad", row, "placement_media", ad["creative_id"],
           f"9:16 video {video_id} in Reels and Stories (creative {new['id']})", True, proposal_id=proposal_id)
    import versions_api
    after_write("stored creative", db.execute, "UPDATE ads SET creative_id = %s WHERE id = %s", (new["id"], ad["id"]))
    after_write("version history", versions_api.save_switch, ad, new["id"], "9:16 video for Reels and Stories", user["id"],
                proposal_id, ad["title"], ad["body"])
    resync_later()
    return None


SWITCH_UNKNOWN = ("Meta didn't answer, so it isn't known whether the ad got the new version. Look at the ad in "
                  "Ads Manager (or press Refresh) before trying again.")


def put_creative(ad_id, creative_id):
    """Point an ad at a creative. When Meta doesn't answer, the ad is read back: showing the new creative
    means it went through; anything else re-raises (the outcome stays unknown) (audit A3-120)."""
    try:
        meta_client.post(ad_id, data={"creative": json.dumps({"creative_id": creative_id})})
    except meta_client.MetaError as exc:
        if not exc.unknown:
            raise
        try:
            now = (meta_client.get(ad_id, fields="creative").get("creative") or {}).get("id")
        except meta_client.MetaError:
            raise exc from None
        if now != creative_id:
            raise


# ---------------------------------------------------------------- Meta's automatic changes (roadmap 4.4)

CREATIVE_FIELDS = "name,object_story_spec,degrees_of_freedom_spec"


def _creative_of(user, ad_id, cached=False):
    """The ad and its creative from Meta. `cached`: for showing it, from meta_cache by creative id. Meta never
    changes a creative's story or automatic changes (switching one makes a new creative), so the answer for
    an id stays true (audit A3-123); a change reads it live."""
    ad = db.query("SELECT id, name, campaign_id, creative_id, effective_status, title, body FROM ads WHERE id = %s", (ad_id,), one=True)
    if not ad or not can_touch(user, ad["campaign_id"]):
        return None, None
    if not ad["creative_id"]:
        return ad, None
    if not cached:
        return ad, meta_client.get(ad["creative_id"], fields=CREATIVE_FIELDS)
    import insights_api
    return ad, insights_api.cached(f"creative:{ad['creative_id']}", 86400, lambda: meta_client.get(
        ad["creative_id"], timeout=meta_client.READ_TIMEOUT, fields=CREATIVE_FIELDS))


@bp.get("/ads/ad/<ad_id>/enhancements")
@login_required
def enhancements(ad_id):
    import creative_features as cf
    try:
        ad, cr = _creative_of(current_user(), ad_id, cached=True)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the creative: {exc}", 400)
    if not ad:
        return api_error("Ad not found", 404)
    if cr is None:
        return jsonify({"features": [], "against_advice": [], "can_change": False,
                        "note": "This ad has no creative Meta can show yet."})
    feats = cf.read(cr.get("degrees_of_freedom_spec"))
    return jsonify({"features": feats, "against_advice": cf.against_advice(feats),
                    "can_change": bool(cr.get("object_story_spec")) and current_user()["role"] == "admin"})


@bp.post("/ads/ad/<ad_id>/enhancements")
@admin_required
def change_enhancement(ad_id):
    """Switch one feature: a new creative with the same story and the new setting, put on the ad."""
    import creative_features as cf
    data = request.get_json(silent=True) or {}
    key, on = str(data.get("key") or ""), bool(data.get("on"))
    user = current_user()
    try:
        ad, cr = _creative_of(user, ad_id)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read the creative: {exc}", 400)
    if not ad:
        return api_error("Ad not found", 404)
    if cr is None:
        return api_error("This ad has no creative Meta can show yet", 409)
    known = {f["key"] for f in cf.read(cr.get("degrees_of_freedom_spec"))} | set(cf.FEATURES)
    if key not in known:
        return api_error("Unknown feature", 400)
    if not cr.get("object_story_spec"):
        return api_error("This ad's creative can't be copied here; change it in Ads Manager", 409)
    dof = cf.with_change(cr.get("degrees_of_freedom_spec"), key, on)
    label = cf.FEATURES.get(key, (cf.human(key),))[0]
    row = {"id": ad["id"], "name": ad["name"], "campaign_id": ad["campaign_id"]}
    try:
        new = meta_client.post(f"act_{_account()}/adcreatives", data={
            "name": f"{ad['name']} · {label} {'on' if on else 'off'}"[:200],
            "object_story_spec": json.dumps(cr["object_story_spec"]), "degrees_of_freedom_spec": json.dumps(dof)})
        meta_client.post(ad["id"], data={"creative": json.dumps({"creative_id": new["id"]})})
    except meta_client.MetaError as exc:
        record(user, "ad", row, "enhancement", None, f"{label} {'on' if on else 'off'}", False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    db.execute("UPDATE ads SET creative_id = %s WHERE id = %s", (new["id"], ad["id"]))
    import versions_api
    versions_api.save_switch(ad, new["id"], f"Meta's automatic change: {label} {'on' if on else 'off'}", user["id"], None, ad["title"], ad["body"])
    record(user, "ad", row, "enhancement", ad["creative_id"], f"{label} {'on' if on else 'off'} (creative {new['id']})", True)
    resync_later()
    return enhancements(ad_id)
