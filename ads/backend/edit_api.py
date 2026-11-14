"""AM-C: change a campaign or ad set after it is made (every setting Meta lets change), archive and delete them.

One write path per edit: POST /api/edit/<level>/<id> with the fields changed and the values the form showed (`seen`). The
server reads Meta fresh, refuses (409) when a shown value changed since, runs the console's rules (edit_rules.problems) and
money rules (edit_rules.money: ceiling, +20 %, 3-day rule, 3x target, danger, turn-on spend), sends one Graph POST to the
object itself with only the changed fields, reads it back, records one meta_changes row per field (D2 knows them as the
console's) and stores what Meta now holds. Owner and this account's admins only (admin_required); never Claude, never the link."""
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import account_info
import ads_api
import audience_rules
import audiences_api
import db
import edit_rules as er
import meta_client
import money_rules
import status_history as sh
import sync
import targets
from auth import admin_required, current_user
from util import api_error, log_activity

bp = Blueprint("edit", __name__, url_prefix="/api")

LEVELS = ("campaign", "adset")
EDIT_FIELDS = {
    "campaign": "id,name,status,effective_status,objective,daily_budget,lifetime_budget,bid_strategy,spend_cap,start_time,stop_time,special_ad_categories",
    "adset": ("id,name,status,effective_status,campaign_id,daily_budget,lifetime_budget,bid_strategy,bid_amount,start_time,end_time,"
              "targeting,optimization_goal,destination_type,billing_event,attribution_spec,frequency_control_specs,promoted_object"),
}
CAMPAIGN_CTX_FIELDS = "id,name,daily_budget,lifetime_budget,bid_strategy,special_ad_categories"
CHILD_FIELDS = "id,name,status,bid_amount,targeting"
GONE = ("ARCHIVED", "DELETED")
OPTIONS = {"bid_strategies": [{"value": v, "label": sh.bid_words(v)} for v in er.BID_STRATEGIES],
           "goals": [{"value": v, "label": sh.goal_words(v)} for v in er.GOALS],
           "destinations": [{"value": v, "label": er.DESTINATION_WORDS[v]} for v in er.DESTINATIONS],
           "billing": [{"value": v, "label": er.BILLING_WORDS[v]} for v in er.BILLING],
           "attributions": [{"value": v, "label": sh.attribution_words(v)} for v in er.ATTRIBUTIONS],
           "categories": [{"value": v, "label": sh.CATEGORY_WORDS[v]} for v in er.CATEGORIES],
           "platforms": [{"value": v, "label": er.PLATFORM_WORDS[v]} for v in er.PLATFORMS],
           "positions": {p: [{"value": v, "label": er.POSITION_WORDS[v]} for v in er.POSITIONS[p]] for p in er.POSITIONS}}


def utcnow():
    return datetime.now(timezone.utc)


def _row(level, entity_id):
    if level not in LEVELS:
        return None
    return db.query(f"SELECT * FROM {sh.TABLE[level]} WHERE id = %s", (entity_id,), one=True)


def _target(level, entity_id):
    """The stored row (this account's, RLS) for an owner or account admin; a 404 for anything else."""
    row = _row(level, entity_id)
    if not row:
        return None, api_error("Not found. Refresh the page.", 404)
    if level == "campaign":
        row = {**row, "campaign_id": row["id"]}
    camp = row.get("campaign_id")
    if not ads_api.can_touch(current_user(), camp):
        return None, api_error("Not found", 404)
    return row, None


def delivered(level, row):
    """An ad set that ever showed (stored once seen, ad_daily or the flag): Meta refuses its goal fields from then on."""
    if level != "adset":
        return False
    if row.get("ever_delivered"):
        return True
    seen = db.query("SELECT 1 FROM ad_daily WHERE adset_id = %s AND impressions > 0 LIMIT 1", (row["id"],), one=True)
    if seen:
        db.execute("UPDATE adsets SET ever_delivered = TRUE WHERE id = %s", (row["id"],))
    return bool(seen)


def name_pins(locations):
    """Unnamed map pins with a primary city get the city's name (display only; never sent to Meta)."""
    pins = sorted({str(x["city_id"]) for x in locations if x.get("city_id") and not x.get("name")})
    if not pins:
        return
    try:
        names = meta_client.get("search", type="adgeolocationmeta", cities=json.dumps(pins)).get("data", {}).get("cities", {})
    except (meta_client.MetaError, AttributeError):
        return
    for x in locations:
        n = (names.get(str(x.get("city_id"))) or {}).get("name")
        if n and not x.get("name"):
            x["name"] = f"{n} area"


def read(level, entity_id):
    """Meta now: (form values, raw object, context for the rules). Raises meta_client.MetaError."""
    raw = meta_client.get(entity_id, fields=EDIT_FIELDS[level])
    if level == "campaign":
        children = [a for a in meta_client.paged(f"{entity_id}/adsets", fields=CHILD_FIELDS, limit=100) if a.get("status") not in GONE]
        live = er.current("campaign", raw, children)
        ctx = {"adsets": [{"id": str(a["id"]), "name": a.get("name"), "bid_amount": er._int(a.get("bid_amount")),
                           "targeting": er.audience_form(a.get("targeting"))} for a in children]}
    else:
        camp = meta_client.get(raw["campaign_id"], fields=CAMPAIGN_CTX_FIELDS) if raw.get("campaign_id") else {}
        live = er.current("adset", raw)
        name_pins(live["targeting"]["locations"])
        ctx = {"campaign": {"id": camp.get("id"), "name": camp.get("name"), "daily_budget": er._int(camp.get("daily_budget")),
                            "lifetime_budget": er._int(camp.get("lifetime_budget")), "bid_strategy": camp.get("bid_strategy")},
               "special": sorted(c for c in camp.get("special_ad_categories") or [] if c and c != "NONE"),
               "audiences": audiences_api.known()}
        audiences_api.name_picked(live["targeting"], ctx["audiences"])
    return live, raw, ctx


def last_bids(ids, now):
    """{id: the last real bid change} (console edits and Meta's records, 90 days) for the 3-day rule on bids."""
    if not ids:
        return {}
    rows = db.query(
        """SELECT entity_id, created_at AS at, old_value, new_value FROM meta_changes
           WHERE action = 'bid' AND ok AND entity_id = ANY(%s) AND created_at > %s
           UNION ALL
           SELECT entity_id, LEAST(COALESCE(meta_time, at), at), old_value, new_value FROM status_events
           WHERE field = 'bid_amount' AND source <> 'backfill' AND entity_id = ANY(%s) AND at > %s""",
        (list(ids), now - timedelta(days=90), list(ids), now - timedelta(days=90)))

    def cents(text):
        head = str(text or "").split(" ")[0]
        return int(head) if head.isdigit() else None
    out = {}
    for r in rows:
        item = {"at": r["at"], "old": cents(r["old_value"]), "new": cents(r["new_value"])}
        # A first goal (none -> amount) limits spending and starts no 3-day clock; a removal or a new amount does.
        if item["old"] is not None and item["old"] != item["new"] and (r["entity_id"] not in out or out[r["entity_id"]]["at"] < item["at"]):
            out[r["entity_id"]] = item
    return out


def lifetime_spent(entity_id):
    """What it has spent since it started, read from Meta (for the campaign cap and a lifetime budget's pace)."""
    rows = meta_client.get(f"{entity_id}/insights", date_preset="maximum", fields="spend").get("data") or []
    try:
        return int(round(float(rows[0].get("spend") or 0) * 100)) if rows else 0
    except (TypeError, ValueError):
        return 0


def full_ctx(level, row, live, ctx, chs, now):
    """Everything the rules need beyond Meta's object: delivery, money settings, what it spent, the last bid changes."""
    ctx = {**ctx, "now": now, "delivered": delivered(level, row), "cap": targets.ceiling(), "target_cpl": targets.lead()}
    fields = {c["field"] for c in chs}
    if fields & {"spend_cap", "end_time", "stop_time", "start_time"} and (level == "campaign" or live.get("lifetime_budget")):
        ctx["spent"] = lifetime_spent(row["id"])
    ids = [row["id"]] + ([a["id"] for a in ctx.get("adsets") or []] if level == "campaign" else [])
    bids = last_bids(ids, now)
    ctx["last_bid"] = {"self": bids.get(row["id"]), **{k: v for k, v in bids.items() if k != row["id"]}}
    if fields & {"end_time", "stop_time", "start_time"} and live.get("lifetime_budget"):
        ctx["last_budget"] = ads_api.last_budget(row["id"], now)
    return ctx


def wanted_from(data):
    raw = data.get("changes")
    return raw if isinstance(raw, dict) else {}


def view(level, row, live, ctx):
    """The form: what it is now, what can change (and why not), the choices."""
    can = er.editable(level, live, ctx)
    out = {"level": level, "id": row["id"], "name": live["name"], "status": live.get("status"), "values": live, "editable": can,
           "delivered": ctx.get("delivered", False), "currency": account_info.currency(), "tz": account_info.tz_name(),
           "options": OPTIONS, "city_radius": er.ab.CITY_RADIUS, "pin_radius": er.ab.PIN_RADIUS,
           "advantage_max_age_min": er.ab.ADVANTAGE_MAX_AGE_MIN, "locale_names": {str(k): v for k, v in er.LOCALE_NAMES.items()},
           "words": {"targeting": er.audience_words(live["targeting"]) if level == "adset" else None,
                     "placements": er.placements_words(live["placements"]) if level == "adset" else None}}
    if level == "adset":
        out["campaign"] = ctx.get("campaign")
        out["special"] = ctx.get("special")
        out.update(audiences_api.picker_options())
    else:
        out["adsets"] = [{k: a[k] for k in ("id", "name", "bid_amount")} for a in ctx.get("adsets") or []]
    return out


@bp.get("/edit/<level>/<entity_id>")
@admin_required
def edit_form(level, entity_id):
    row, err = _target(level, entity_id)
    if err:
        return err
    if {row.get("status"), row.get("effective_status")} & set(GONE):
        return api_error("It's archived or deleted, so it can't be changed.", 409)
    try:
        live, _, ctx = read(level, entity_id)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta, so nothing can be changed right now: {exc}", 400)
    ctx = full_ctx(level, row, live, ctx, [], utcnow())
    return jsonify(view(level, row, live, ctx))


def evaluate(level, row, data):
    """Fresh read + every check, no write: (live, raw, ctx, changes, problems, review, money questions)."""
    live, raw, ctx = read(level, row["id"])
    wanted = wanted_from(data)
    if level == "adset" and isinstance(wanted.get("targeting"), dict):
        wanted = {**wanted, "targeting": audiences_api.name_picked(dict(wanted["targeting"]), ctx.get("audiences") or {}, live["targeting"])}
    chs = er.changes(level, live, wanted)
    now = utcnow()
    ctx = full_ctx(level, row, live, ctx, chs, now)
    names = {a["id"]: a.get("name") for a in ctx.get("adsets") or []}
    probs = er.problems(level, live, chs, ctx)
    rows = er.review(level, live, chs, account_info.tz_name(), account_info.currency(), names)
    questions = [] if probs else er.money(level, live, chs, ctx, account_info.currency())
    return live, raw, ctx, chs, probs, rows, questions


def _public_q(q):
    return {k: v for k, v in q.items() if k in ("field", "code", "message", "entity", "from", "to", "pct", "lead")}


@bp.post("/edit/<level>/<entity_id>/check")
@admin_required
def check(level, entity_id):
    row, err = _target(level, entity_id)
    if err:
        return err
    if {row.get("status"), row.get("effective_status")} & set(GONE):
        return api_error("It's archived or deleted, so it can't be changed.", 409)
    try:
        live, _, _, chs, probs, rows, questions = evaluate(level, row, request.get_json(silent=True) or {})
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta: {exc}", 400)
    return jsonify({"changes": [c["field"] for c in chs], "problems": [{"field": f, "message": m} for f, m in probs],
                    "review": rows, "money": [_public_q(q) for q in questions],
                    "seen": {c["field"]: live.get(c["field"]) for c in chs}})


ACCEPT_KEYS = {"big": "accept_big", "recent": "accept_recent", "high": "accept_high", "danger": "confirm_remove"}


def _accepts(data):
    return {code: bool(data.get(key)) for code, key in ACCEPT_KEYS.items()}


def _store_after(level, entity_id, fresh, extra_children=()):
    """What Meta holds now, stored at once (so the next sync sees no difference and History has only the console's line)."""
    if level == "campaign":
        db.execute("""UPDATE campaigns SET name = %s, bid_strategy = %s, spend_cap_cents = %s, stop_time = %s, start_time = %s,
                      special_ad_categories = %s WHERE id = %s""",
                   (fresh.get("name"), fresh.get("bid_strategy"), sync.spend_cap(fresh.get("spend_cap")), sync._time(fresh.get("stop_time")),
                    sync._time(fresh.get("start_time")), sorted(c for c in fresh.get("special_ad_categories") or [] if c and c != "NONE"), entity_id))
        for a in extra_children:
            db.execute("UPDATE adsets SET bid_amount_cents = %s, bid_strategy = %s WHERE id = %s",
                       (sync.cents(a.get("bid_amount")), a.get("bid_strategy") or None, a["id"]))
        return
    t = fresh.get("targeting")
    db.execute("""UPDATE adsets SET name = %s, bid_strategy = %s, bid_amount_cents = %s, start_time = %s, end_time = %s, targeting_fp = %s,
                  targeting = %s, targeting_summary = %s, placements_fp = %s, optimization_goal = %s, destination_type = %s,
                  billing_event = %s, attribution = %s, frequency = %s, audience_ids = %s, excluded_audience_ids = %s WHERE id = %s""",
               (fresh.get("name"), fresh.get("bid_strategy") or None, sync.cents(fresh.get("bid_amount")), sync._time(fresh.get("start_time")),
                sync._time(fresh.get("end_time")), sh.targeting_fingerprint(t), sync._json(er.kept_targeting(t)), sync.summarize_targeting(t, sync.audience_names(t)),
                sh.placements_fingerprint(t), fresh.get("optimization_goal"), fresh.get("destination_type"), fresh.get("billing_event"),
                sync._json(fresh.get("attribution_spec")), sync._json(fresh.get("frequency_control_specs")),
                audience_rules.ids_in(t, "custom_audiences"), audience_rules.ids_in(t, "excluded_custom_audiences"), entity_id))


def _texts(level, c, rows, live_raw_t, merged_t, ctx, live=None):
    """(old, new) meta_changes values for one change: the machine part status_history reads, then the History words."""
    field = c["field"]
    if field == "name":
        return c["old"], c["new"]
    line = er.history_words(rows, field)
    if field == "targeting":
        before = (live or {}).get("targeting") or er.audience_form(live_raw_t)
        return f"{er.change_text(field, None, live_raw_t)} {er.audience_words(before)}", f"{er.change_text(field, None, merged_t)} {line}"
    if field == "placements":
        return f"{er.change_text(field, None, live_raw_t)} {er.placements_words(c['old'])}", f"{er.change_text(field, None, merged_t)} {line}"
    if field == "bid_amount":  # two machine tokens: the amount, then the bidding it goes with (History names it)
        strategy = ctx.get("strategy_after") or "NONE"
        return f"{er.change_text(field, c['old'])} {strategy}", f"{er.change_text(field, c['new'])} {strategy} {line}"
    return er.change_text(field, c["old"]), f"{er.change_text(field, c['new'])} {line}"


@bp.post("/edit/<level>/<entity_id>")
@admin_required
def save(level, entity_id):
    row, err = _target(level, entity_id)
    if err:
        return err
    if {row.get("status"), row.get("effective_status")} & set(GONE):
        return api_error("It's archived or deleted, so it can't be changed.", 409)
    data = request.get_json(silent=True) or {}
    with db.try_lock(f"edit:{entity_id}") as mine:
        if not mine:
            return api_error("Another change to this is still being sent. Try again in a moment.", 409)
        return _save(level, row, data)


def _save(level, row, data):
    user = current_user()
    try:
        live, raw, ctx, chs, probs, rows, questions = evaluate(level, row, data)
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta, so nothing was changed: {exc}", 400)
    if not chs:
        return api_error("Nothing changed: that's what it is now.", 400)
    seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
    for c in chs:
        if c["field"] == "adset_bids":
            shown = er.normal("adset_bids", seen.get("adset_bids"))
            if any(shown.get(k) != v for k, v in c["old"].items()):
                return api_error("Ads Manager has a different value now: check it again.", 409, field=c["field"], live=live.get("adset_bids"))
            continue
        if c["field"] not in seen or er.normal(c["field"], seen[c["field"]]) != c["old"]:
            return api_error("Ads Manager has a different value now: check it again.", 409, field=c["field"], live=live.get(c["field"]))
    if probs:
        return api_error(probs[0][1], 400, field=probs[0][0], problems=[{"field": f, "message": m} for f, m in probs])
    accepts = _accepts(data)
    spend_ctx = None
    if any(q["code"] == "spend" for q in questions):
        try:
            spend_ctx = ads_api.spend_context(level, row)
        except meta_client.MetaError as exc:
            return api_error(f"Couldn't read the budget from Meta, so nothing was changed: {exc}", 400)
        accepts["spend"] = not money_rules.turn_on_problem(spend_ctx, data.get("confirm_daily_cents"), data.get("confirm_lifetime_cents"))
    question = er.money_problem(questions, accepts)
    if question:
        status = 400 if question["code"] == "refused" else 409
        return api_error(question["message"], status, field=question["field"], code=question["code"],
                         money=[_public_q(q) for q in questions], **({"spend": spend_ctx} if spend_ctx else {}))
    accepted = sorted({q["code"] for q in questions if q["code"] in ("big", "recent", "high", "danger")})
    params = er.meta_params(level, chs, raw.get("targeting"))
    by = {c["field"]: c for c in chs}
    merged_t = json.loads(params["targeting"]) if "targeting" in params else raw.get("targeting")
    camp = ctx.get("campaign") or {}
    strategy_after = (by.get("bid_strategy") or {}).get("new") or live.get("bid_strategy") or "NONE"
    if level == "adset" and (camp.get("daily_budget") or camp.get("lifetime_budget")):
        strategy_after = camp.get("bid_strategy") or strategy_after
    ctx["strategy_after"] = strategy_after
    undo_of = None
    if data.get("undo_of") and len(chs) == 1:
        c = chs[0]
        undo_of = ads_api.undo_target(data["undo_of"], row["id"], (er.ACTIONS[c["field"]],),
                                      er.change_text(c["field"], c["new"], merged_t if c["field"] in ("targeting", "placements") else None))
    own = {str(a["id"]) for a in ctx.get("adsets") or []}
    if "adset_bids" in by and set(by["adset_bids"]["new"]) - own:  # problems refuses it first; never written outside this campaign
        return api_error("These aren't ad sets of this campaign: refresh the page.", 400, field="adset_bids")
    unknown = None
    if params:
        try:
            meta_client.post(row["id"], **params)
        except meta_client.MetaError as exc:
            if not exc.unknown:
                for c in chs:
                    if c["field"] != "adset_bids":
                        ads_api.record(user, level, row, er.ACTIONS[c["field"]], *_texts(level, c, rows, raw.get("targeting"), merged_t, ctx, live), False, str(exc))
                return api_error(f"Meta refused: {exc}", 400, field=chs[0]["field"])
            unknown = str(exc)
    # Read back before anything else: a write Meta didn't answer is done only when the read says so, never sent again blind.
    try:
        fresh = meta_client.get(row["id"], fields=EDIT_FIELDS[level])
    except meta_client.MetaError as exc:
        if unknown:
            return api_error("Meta didn't answer, and reading it back failed too: the change may still arrive. Refresh in a minute "
                             "before trying again.", 409, code="unknown")
        fresh = None
    fresh_form = er.current(level, fresh) if fresh else None
    if level == "adset" and fresh_form:
        name_pins(fresh_form["targeting"]["locations"])
    written = [c for c in chs if c["field"] != "adset_bids"]
    differs = er.readback_ok(written, fresh_form) if fresh_form else []
    if unknown and fresh_form and set(differs) == {c["field"] for c in written}:
        return api_error("Meta didn't answer, and it still shows the old values: the change may still arrive. Refresh in a minute "
                         "before trying again.", 409, code="unknown")
    if unknown and not fresh_form:
        return api_error("Meta didn't answer: the change may still arrive. Refresh in a minute before trying again.", 409, code="unknown")
    for c in written:
        old, new = _texts(level, c, rows, raw.get("targeting"), merged_t, ctx, live)
        if c["field"] in differs:
            kept = er.value_words(level, c["field"], er.normal(c["field"], fresh_form.get(c["field"])), account_info.tz_name(), account_info.currency())
            ads_api.record(user, level, row, er.ACTIONS[c["field"]], old, new, False, f"Meta kept {kept}")
        else:
            ads_api.record(user, level, row, er.ACTIONS[c["field"]], old, new, True,
                           accepted=[a for a in accepted if any(q["field"] == c["field"] and q["code"] == a for q in questions)] or None,
                           undo_of=undo_of)
    children = []
    if "adset_bids" in by:
        names = {a["id"]: a.get("name") for a in ctx.get("adsets") or []}
        for sid, cents in by["adset_bids"]["new"].items():
            child = {"id": sid, "name": names.get(sid), "campaign_id": row["id"]}
            old_c = by["adset_bids"]["old"].get(sid)
            words = f"Cost per result goal {er._money(old_c, account_info.currency())} → {er._money(cents, account_info.currency())}"
            try:
                meta_client.post(sid, bid_amount=str(int(cents)))
                ads_api.record(user, "adset", child, "bid", er.change_text("bid_amount", old_c), f"{cents} {strategy_after} {words}", True,
                               accepted=[a for a in accepted if any(q.get("entity") == sid and q["code"] == a for q in questions)] or None)
            except meta_client.MetaError as exc:
                ads_api.record(user, "adset", child, "bid", er.change_text("bid_amount", old_c), f"{cents} {strategy_after} {words}", False, str(exc))
                differs.append("adset_bids")
        try:
            children = list(meta_client.paged(f"{row['id']}/adsets", fields="id,bid_amount,bid_strategy", limit=100))  # as Meta reads them
        except meta_client.MetaError:
            children = []
    if fresh:
        ads_api.after_write("stored setup", _store_after, level, row["id"], fresh, children)
    ads_api.resync_later()
    log_activity("meta.edit", subject=row["id"], details={"level": level, "fields": [c["field"] for c in chs], "differs": differs})
    return jsonify({"saved": [c["field"] for c in chs if c["field"] not in differs], "differs": differs,
                    "review": rows, "kept": {f: er.value_words(level, f, er.normal(f, fresh_form.get(f)), account_info.tz_name(), account_info.currency())
                                             for f in differs if f != "adset_bids" and fresh_form}})


@bp.get("/edit/search")
@admin_required
def search():
    """Languages and detailed targeting (interests, behaviours) from Meta's targeting search."""
    kind, q = request.args.get("kind"), (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    try:
        if kind == "language":
            rows = meta_client.get("search", type="adlocale", q=q, limit=10).get("data") or []
            return jsonify({"items": [{"key": int(r["key"]), "name": r.get("name")} for r in rows if str(r.get("key", "")).isdigit()]})
        rows = meta_client.get("search", type="adinterest", q=q, limit=10).get("data") or []
        cats = meta_client.get("search", type="adTargetingCategory", **{"class": "behaviors"}).get("data") or []
    except meta_client.MetaError as exc:
        return api_error(f"Meta's search failed: {exc}", 400)
    items = [{"id": str(r["id"]), "name": r.get("name"), "type": "interests"} for r in rows if str(r.get("id", "")).isdigit()]
    items += [{"id": str(r["id"]), "name": r.get("name"), "type": "behaviors"} for r in cats
              if str(r.get("id", "")).isdigit() and q.lower() in (r.get("name") or "").lower()]
    return jsonify({"items": items[:15]})


# ---------------------------------------------------------------- archive and delete (campaigns and ad sets)

WORD = {"campaign": "campaign", "adset": "ad set"}


@bp.get("/edit/<level>/<entity_id>/inside")
@admin_required
def inside(level, entity_id):
    """For the archive / delete dialog: what goes with it, read fresh, and whether it is on now."""
    row, err = _target(level, entity_id)
    if err:
        return err
    try:
        status = meta_client.get(entity_id, fields="status").get("status")
        ads = [a for a in meta_client.paged(f"{entity_id}/ads", fields="id,status", limit=200) if a.get("status") not in GONE]
        sets = [a for a in meta_client.paged(f"{entity_id}/adsets", fields="id,status", limit=100)
                if a.get("status") not in GONE] if level == "campaign" else []
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta: {exc}", 400)
    return jsonify({"status": status, "adsets": len(sets), "ads": len(ads)})


@bp.post("/ads/<level>/<entity_id>/archive")
@admin_required
def archive(level, entity_id):
    return _remove(level, entity_id, "archive")


@bp.post("/ads/<level>/<entity_id>/delete")
@admin_required
def delete(level, entity_id):
    return _remove(level, entity_id, "delete")


def _remove(level, entity_id, action):
    if level not in LEVELS:
        return api_error("Not found", 404)
    row, err = _target(level, entity_id)
    if err:
        return err
    user = current_user()
    try:
        live = meta_client.get(entity_id, fields="status").get("status") or row["status"]
    except meta_client.MetaError as exc:
        return api_error(f"Couldn't read it from Meta, so nothing was changed: {exc}", 400)
    problem = ads_api.removal_problem(user, {**row, "status": live}, action, (request.get_json(silent=True) or {}).get("name"), level)
    if problem:
        return api_error(problem, 400 if "name" in problem else 409, field="name" if "name" in problem else None)
    status = ads_api.REMOVALS[action]
    rec = row
    try:
        meta_client.post(entity_id, status=status)
    except meta_client.MetaError as exc:
        ads_api.record(user, level, rec, action, live, status, False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    table = sh.TABLE[level]
    db.execute(f"UPDATE {table} SET status = %s, effective_status = %s WHERE id = %s", (status, status, entity_id))
    col = "campaign_id" if level == "campaign" else "adset_id"
    for child in (("adsets", "ads") if level == "campaign" else ("ads",)):
        ads_api.after_write("children status", db.execute,
                            f"UPDATE {child} SET status = %s, effective_status = %s WHERE {col} = %s AND COALESCE(status, '') <> 'DELETED'",
                            (status, status, entity_id))
    ads_api.record(user, level, rec, action, live, status, True)
    ads_api.resync_later()
    return jsonify({"id": entity_id, "status": status})

