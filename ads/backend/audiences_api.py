"""AM-D: the account's audiences. Ads → Audiences lists custom, lookalike and saved audiences (owner, account admins and teammates;
teammates read only, their where-used limited to their campaigns; clients never), and owners / account admins make website,
engagement and lookalike audiences through the console's own Graph key (act_<id>/customaudiences). No customer list is ever
uploaded or changed here, and nothing spends: picking an audience in a live ad set is an AM-C targeting change.

Meta's audiences are read at most every 5 minutes when the page opens, after every create and once a day by the worker; only a
complete listing marks one gone (the `if seen:` guard). The pickers in New ad set, New campaign and Edit read `picker_options`;
`pick_check` refuses an audience that isn't this account's (checked under RLS before anything reaches Meta)."""
import json
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import ads_api
import adset_build as ab
import audience_rules as ar
import db
import edit_rules as er
import meta_client
import settings_store
from auth import admin_required, current_user, login_required, visible_campaign_ids
from insights_api import cached
from util import api_error, log_activity

bp = Blueprint("audiences", __name__, url_prefix="/api/audiences")

AUDIENCE_FIELDS = ("id,name,subtype,description,approximate_count_lower_bound,approximate_count_upper_bound,delivery_status,"
                   "operation_status,retention_days,lookalike_spec,rule,time_created")
SAVED_FIELDS = "id,name,description,targeting,time_created"
FRESH_SECONDS = 300          # opening the page reads Meta again at most this often
DAILY_SECONDS = 86400        # the worker's read
REFRESH_GAP = 60             # Refresh: once a minute
ADOPT_SECONDS = 600          # an unanswered create is looked for among audiences made in the last 10 minutes
TERMS_CODES = (2654,)        # Meta: the Custom Audience terms aren't accepted for this ad account (verify)
TERMS_WORDS = ("Accept Meta's Custom Audience terms for this ad account first (Business settings → Ad accounts → this account → "
               "Custom Audience terms, or Ads Manager → Audiences, which asks for them), then try again.")


def _acct():
    return settings_store.get("meta_ad_account_id")


def _now():
    return datetime.now(timezone.utc)


def _when(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        return datetime.fromtimestamp(int(v), timezone.utc)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00").replace("+0000", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- reading Meta

UPSERT = """INSERT INTO audiences (id, kind, subtype, name, description, size_lower, size_upper, ready, status_words, retention_days,
                                   source_kind, who, detail, source_id, lookalike, targeting, time_created, synced_at, gone_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), NULL)
            ON CONFLICT (account_id, id) DO UPDATE SET kind = EXCLUDED.kind, subtype = EXCLUDED.subtype, name = EXCLUDED.name,
                description = CASE WHEN audiences.made_here THEN audiences.description ELSE EXCLUDED.description END,
                size_lower = EXCLUDED.size_lower, size_upper = EXCLUDED.size_upper, ready = EXCLUDED.ready,
                status_words = EXCLUDED.status_words, retention_days = COALESCE(EXCLUDED.retention_days, audiences.retention_days),
                source_kind = COALESCE(EXCLUDED.source_kind, audiences.source_kind), who = COALESCE(EXCLUDED.who, audiences.who),
                detail = COALESCE(EXCLUDED.detail, audiences.detail), source_id = COALESCE(EXCLUDED.source_id, audiences.source_id),
                lookalike = COALESCE(EXCLUDED.lookalike, audiences.lookalike), targeting = EXCLUDED.targeting,
                time_created = COALESCE(EXCLUDED.time_created, audiences.time_created), synced_at = now(), gone_at = NULL"""


def _upsert(r):
    db.execute(UPSERT, (r["id"], r["kind"], r["subtype"], r["name"], r["description"], r["size_lower"], r["size_upper"], r["ready"],
                        r["status_words"], r["retention_days"], r["source_kind"], r["who"], r["detail"], r["source_id"],
                        json.dumps(r["lookalike"]) if r["lookalike"] else None, json.dumps(r["targeting"]) if r["targeting"] else None,
                        _when(r["time_created"])))


def sync():
    """Read the account's custom, lookalike and saved audiences from Meta and store them. Raises meta_client.MetaError."""
    acct = _acct()
    if not acct:
        return None
    started = db.now()
    custom = list(meta_client.paged(f"act_{acct}/customaudiences", fields=AUDIENCE_FIELDS, limit=100))
    try:
        saved = list(meta_client.paged(f"act_{acct}/saved_audiences", fields=SAVED_FIELDS, limit=100))
    except meta_client.MetaError as exc:
        if meta_client.transient(exc):
            raise
        saved = []  # an account without saved audiences access still lists its custom ones
    rows = [r for r in map(ar.from_meta, custom) if r] + [r for r in map(ar.saved_from_meta, saved) if r]
    for r in rows:
        _upsert(r)
    for kinds, seen in ((["custom", "lookalike"], [r["id"] for r in rows if r["kind"] != "saved"]), (["saved"], [r["id"] for r in rows if r["kind"] == "saved"])):
        if seen:  # only a listing that returned something marks the rest gone (an empty answer changes nothing)
            db.execute("""UPDATE audiences SET gone_at = now() WHERE kind = ANY(%s) AND gone_at IS NULL AND synced_at < %s
                          AND NOT (id = ANY(%s))""", (kinds, started, seen))
    settings_store.set("audiences_read_at", _now().isoformat())
    return len(rows)


def read_at():
    return _when(settings_store.get("audiences_read_at"))


def ensure_fresh(max_age=FRESH_SECONDS, force=False):
    """Read Meta when the stored list is older than max_age (one reader at a time per account). Returns Meta's error words or None."""
    acct = _acct()
    if not acct or not settings_store.get("meta_system_token"):
        return None
    at = read_at()
    if not force and at and (_now() - at).total_seconds() < max_age:
        return None
    key = f"audiences:{acct}"
    failed = meta_client.recently_failed(key)
    if failed and not force:
        return str(failed)
    with db.try_lock(key) as mine:
        if not mine:
            return None
        try:
            sync()
        except meta_client.MetaError as exc:
            meta_client.remember_failure(key, exc)
            return str(exc)
    return None


def refresh_if_stale():
    """The worker's daily read."""
    ensure_fresh(DAILY_SECONDS)


# ---------------------------------------------------------------- this account's sources (Page, Instagram, forms, videos, pixel)

def _read_sources():
    out = {"pixel": settings_store.get("meta_dataset_id") or None, "page": settings_store.get("meta_page_id") or None,
           "page_name": None, "instagram": None, "instagram_name": None, "forms": [], "videos": []}
    if out["page"]:
        try:
            p = meta_client.get(out["page"], fields="name,instagram_business_account{id,username}")
            out["page_name"] = str(p.get("name") or "")[:200] or None
            ig = p.get("instagram_business_account") or {}
            if str(ig.get("id") or "").isdigit():
                out["instagram"], out["instagram_name"] = str(ig["id"]), str(ig.get("username") or "")[:100] or None
        except meta_client.MetaError:
            pass
        try:
            import forms_api
            out["forms"] = [{"id": str(f["id"]), "name": str(f.get("name") or "")[:200]} for f in forms_api.page_forms()
                            if str(f.get("id") or "").isdigit() and f.get("status") != "ARCHIVED"]
        except meta_client.MetaError:
            pass
    if _acct():
        try:
            vids = meta_client.get(f"act_{_acct()}/advideos", fields="id,title,created_time", limit=25).get("data") or []
            out["videos"] = [{"id": str(v["id"]), "name": str(v.get("title") or "Untitled video")[:200]} for v in vids if str(v.get("id") or "").isdigit()]
        except meta_client.MetaError:
            pass
    return out


def sources(fresh=False):
    key = f"audiences:sources:{_acct()}"
    if fresh:
        db.execute("DELETE FROM meta_cache WHERE key = %s", (key,))
    try:
        return cached(key, 600, _read_sources, stale_ok=True)
    except meta_client.MetaError:
        return _read_sources()


def countries():
    """Countries this account's ad sets reach (a lookalike is made for one of them); the US when none names a country."""
    rows = db.query("""SELECT DISTINCT jsonb_array_elements_text(targeting->'geo_locations'->'countries') AS c FROM adsets
                       WHERE targeting ? 'geo_locations' AND jsonb_typeof(targeting->'geo_locations'->'countries') = 'array'
                       AND COALESCE(effective_status, '') <> 'DELETED'""")
    found = sorted({str(r["c"]).upper()[:2] for r in rows if r["c"]})
    return found or ["US"]


def known():
    """{id: row} of this account's custom and lookalike audiences that Meta still lists (RLS keeps it to this account)."""
    return {r["id"]: r for r in db.query("SELECT * FROM audiences WHERE gone_at IS NULL AND kind IN ('custom', 'lookalike')")}


def known_for_create(src):
    return {"pixel": src.get("pixel"), "page": src.get("page"), "instagram": src.get("instagram"),
            "forms": {f["id"]: f["name"] for f in src.get("forms") or []}, "videos": {v["id"]: v["name"] for v in src.get("videos") or []},
            "audiences": known(), "countries": countries()}


def _names(rows, src=None):
    names = {r["id"]: r["name"] for r in rows}
    src = src or {}
    names.update({f["id"]: f["name"] for f in src.get("forms") or []})
    names.update({v["id"]: v["name"] for v in src.get("videos") or []})
    return names


def _cached_sources():
    """The sources as last read (no Meta call): names for the plain words."""
    row = db.query("SELECT data FROM meta_cache WHERE key = %s", (f"audiences:sources:{_acct()}",), one=True)
    return (row or {}).get("data") or {}


# ---------------------------------------------------------------- the list

def _adsets(user):
    sets = db.query("""SELECT id, name, campaign_id, status, effective_status, audience_ids, excluded_audience_ids FROM adsets
                       WHERE audience_ids <> '{}' OR excluded_audience_ids <> '{}'""")
    visible = visible_campaign_ids(user)
    return sets if visible is None else [s for s in sets if s["campaign_id"] in visible]


def view(r, sets, names):
    used = ar.where_used(r["id"], sets)
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "kind_words": ar.kind_words(r), "source_kind": r["source_kind"],
            "describe": ar.describe(r, names), "size_words": ar.size_words(r), "size_lower": r["size_lower"], "size_upper": r["size_upper"],
            "ready": r["ready"], "status_words": r["status_words"], "made_here": r["made_here"],
            "made_words": "Made in the console" if r["made_here"] else "Made in Meta", "used": used, "used_words": ar.used_words(used),
            "lookalike": r["lookalike"], "retention_days": r["retention_days"],
            "time_created": r["time_created"].isoformat() if r["time_created"] else None}


def _not_for_clients(user):
    return user["role"] == "client"


@bp.get("")
@login_required
def listing():
    user = current_user()
    if _not_for_clients(user):
        return api_error("Audiences aren't part of a client's view", 403)
    error = ensure_fresh()
    kind = request.args.get("kind")
    rows = db.query("SELECT * FROM audiences WHERE gone_at IS NULL ORDER BY (kind = 'saved'), lower(name)")
    sets = _adsets(user)
    names = _names(rows, sources() if _acct() and settings_store.get("meta_system_token") else {})
    items = [view(r, sets, names) for r in rows if not kind or r["kind"] == kind]
    at = read_at()
    return jsonify({"items": items, "read_at": at.isoformat() if at else None, "error": error, "can_edit": user["role"] == "admin",
                    "has_meta": bool(_acct())})


@bp.get("/<audience_id>")
@login_required
def one(audience_id):
    user = current_user()
    if _not_for_clients(user):
        return api_error("Audiences aren't part of a client's view", 403)
    r = db.query("SELECT * FROM audiences WHERE id = %s", (str(audience_id)[:30],), one=True)
    if not r:
        return api_error("That audience isn't in this account", 404)
    rows = db.query("SELECT id, name FROM audiences")
    return jsonify(view(r, _adsets(user), _names(rows, _cached_sources())))


@bp.get("/sources")
@admin_required
def source_list():
    src = sources(fresh=request.args.get("fresh") == "1")
    auds = known()
    names = _names(list(auds.values()), src)
    cs = countries()

    def why_not(a):
        found = ar.problems("lookalike", {"name": "x", "origin_id": a["id"], "country": cs[0], "ratio": 0.01}, {"audiences": auds, "countries": cs})
        return found[0][1] if found else None
    origins = [{"id": a["id"], "name": a["name"], "describe": ar.describe(a, names), "size_words": ar.size_words(a), "size_lower": a["size_lower"],
                "ready": a["ready"], "kind_words": ar.kind_words(a), "why_not": why_not(a)}
               for a in sorted(auds.values(), key=lambda a: a["name"].lower()) if a["kind"] == "custom"]
    return jsonify({**{k: src.get(k) for k in ("pixel", "page", "page_name", "instagram", "instagram_name", "forms", "videos")},
                    "origins": origins, "countries": cs, "ratios": list(ar.LOOKALIKE_RATIOS), "retention_max": ar.RETENTION_MAX,
                    "who": {k: [{"value": w, "label": ar.CHOICES[w]} for w in v] for k, v in ar.WHO.items()},
                    "min_source": ar.MIN_SOURCE})


# ---------------------------------------------------------------- making one

def _spec(kind, raw, src):
    spec = ar.clean(kind, raw)
    if kind in ("website", "page", "instagram"):  # the account's own: never taken from the request
        spec["source_id"] = str(src.get({"website": "pixel", "page": "page", "instagram": "instagram"}[kind]) or "")
    return spec


def _describe_new(kind, spec, k):
    row = {**ar.row_from_spec(kind, spec), "made_here": False}
    names = {**k["forms"], **k["videos"], **{i: a["name"] for i, a in k["audiences"].items()}}
    return ar.describe(row, names)


@bp.post("/check")
@admin_required
def check():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind") or "")
    src = sources()
    k = known_for_create(src)
    spec = _spec(kind, data.get("spec") or {}, src)
    probs = ar.problems(kind, spec, k)
    return jsonify({"problems": [{"field": f, "message": m} for f, m in probs],
                    "describe": None if probs else _describe_new(kind, spec, k),
                    "size": ar.lookalike_size_words(spec.get("country"), spec.get("ratio")) if kind == "lookalike" and not probs else None})


def _store_made(aid, kind, spec, words, user, key, raw=None):
    r = ar.from_meta(raw) if raw else None
    base = {**ar.row_from_spec(kind, spec), "name": spec["name"], "description": words}
    if r:  # what Meta says it holds, with the console's own words and what it was made from
        base = {**base, **{k: r[k] for k in ("size_lower", "size_upper", "ready", "status_words", "time_created") if r.get(k) is not None}}
    ready, status = (base.get("ready"), base.get("status_words")) if base.get("ready") else ar.readiness(None, None, None, None)
    if key and db.query("SELECT 1 FROM audiences WHERE client_key = %s AND id <> %s", (key, aid), one=True):
        key = None  # UNIQUE(account_id, client_key): the click already names another row
    db.execute("""INSERT INTO audiences (id, kind, subtype, name, description, size_lower, size_upper, ready, status_words, retention_days, source_kind,
                                         who, detail, source_id, lookalike, made_here, created_by, client_key, time_created, synced_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, %s, %s, COALESCE(%s, now()), now())
                  ON CONFLICT (account_id, id) DO UPDATE SET made_here = TRUE, created_by = EXCLUDED.created_by,
                      client_key = COALESCE(audiences.client_key, EXCLUDED.client_key), description = EXCLUDED.description,
                      source_kind = EXCLUDED.source_kind, who = EXCLUDED.who, detail = EXCLUDED.detail, source_id = EXCLUDED.source_id,
                      lookalike = EXCLUDED.lookalike, gone_at = NULL""",
               (aid, base["kind"], base["subtype"], spec["name"], words, base.get("size_lower"), base.get("size_upper"), ready, status,
                base["retention_days"], base["source_kind"], base["who"], base["detail"], base["source_id"],
                json.dumps(base["lookalike"]) if base["lookalike"] else None, user["id"], key, _when(base.get("time_created"))))


def _adoptable(acct, kind, spec):
    """The audience an unanswered create made: same name, type and source (ar.adopt_match), made in the last 10 minutes, and no
    console row claims it."""
    taken = {r["id"] for r in db.query("SELECT id FROM audiences WHERE made_here")}
    floor = time.time() - ADOPT_SECONDS
    for x in meta_client.paged(f"act_{acct}/customaudiences", fields=AUDIENCE_FIELDS, limit=100):
        made = _when(x.get("time_created"))
        if str(x.get("id")) not in taken and made and made.timestamp() >= floor and ar.adopt_match(kind, spec, x):
            return x
    return None


def _pending_key(acct, key):
    return f"audience_pending:{acct}:{key}"


def _refusal(exc):
    text = str(exc)
    if exc.code in TERMS_CODES or "custom audience terms" in text.lower():
        return TERMS_WORDS
    return f"Meta refused: {text}"


def _same_key(key):
    return db.query("SELECT id FROM audiences WHERE client_key = %s", (key,), one=True) if key else None


@bp.post("")
@admin_required
def create():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind") or "")
    key = str(data.get("client_key") or "")[:64] or None
    same = _same_key(key)  # the same click sent twice: the same audience
    if same:
        return jsonify({"id": same["id"], "again": True}), 200
    acct = _acct()
    if not acct:
        return api_error("Connect this account's Meta ad account in Settings → Meta first", 400)
    src = sources()
    k = known_for_create(src)
    spec = _spec(kind, data.get("spec") or {}, src)
    probs = ar.problems(kind, spec, k)
    if probs:
        return api_error(probs[0][1], 400, field=probs[0][0], problems=[{"field": f, "message": m} for f, m in probs])
    words = _describe_new(kind, spec, k)
    user = current_user()
    rec = {"id": f"act_{acct}", "name": spec["name"]}

    def adopt(earlier):
        _store_made(str(earlier["id"]), kind, spec, words, user, key, earlier)
        if key:
            settings_store.set(_pending_key(acct, key), None)
        ads_api.record(user, "account", rec, "audience_create", None, f"{spec['name']} (found after Meta didn't answer)", True)
        return jsonify({"id": str(earlier["id"]), "adopted": True}), 201

    with db.try_lock(f"audience-create:{acct}") as mine:
        if not mine:
            return api_error("Another audience is still being made. Try again in a moment.", 409)
        same = _same_key(key)  # a press that finished while this one read Meta's sources
        if same:
            return jsonify({"id": same["id"], "again": True}), 200
        if key and settings_store.get(_pending_key(acct, key)):  # this very click went unanswered before: look for it first
            try:
                earlier = _adoptable(acct, kind, spec)
            except meta_client.MetaError as exc:
                return api_error(f"Couldn't read Meta's audiences, so nothing was made: {exc}", 400)
            if earlier:
                return adopt(earlier)
        body = ar.create_params(kind, spec, words)
        if key:
            settings_store.set(_pending_key(acct, key), _now().isoformat())
        try:
            made = meta_client.post(f"act_{acct}/customaudiences",
                                    data={k_: json.dumps(v) if isinstance(v, (dict, list, bool)) else v for k_, v in body.items()})
        except meta_client.MetaError as exc:
            if exc.unknown:
                try:
                    earlier = _adoptable(acct, kind, spec)
                except meta_client.MetaError:
                    earlier = None
                if earlier:
                    return adopt(earlier)
                return api_error("Meta didn't answer, so it may still make the audience. Wait a minute, then press Make the audience again: "
                                 "the console looks for it first and never makes it twice.", 409, code="unknown")
            if key:
                settings_store.set(_pending_key(acct, key), None)
            ads_api.record(user, "account", rec, "audience_create", None, spec["name"], False, str(exc))
            return api_error(_refusal(exc), 400, code="terms" if _refusal(exc) == TERMS_WORDS else None)
        aid = str(made.get("id") or "")
        if not aid.isdigit():
            return api_error("Meta answered without the new audience's id. Refresh the list in a minute.", 409, code="unknown")
        _store_made(aid, kind, spec, words, user, key)
        if key:
            settings_store.set(_pending_key(acct, key), None)
    ads_api.record(user, "account", rec, "audience_create", None, spec["name"], True)
    log_activity("audience.created", subject=aid, details={"kind": kind, "name": spec["name"]})
    return jsonify({"id": aid}), 201


@bp.post("/refresh")
@admin_required
def refresh():
    last = _when(settings_store.get("audiences_refresh_at"))
    if last and (_now() - last).total_seconds() < REFRESH_GAP:
        return api_error("Read from Meta less than a minute ago. Try again in a moment.", 429)
    settings_store.set("audiences_refresh_at", _now().isoformat())
    sources(fresh=True)
    error = ensure_fresh(force=True)
    if error:
        return api_error(f"Couldn't read Meta's audiences: {error}", 400)
    return jsonify({"ok": True, "read_at": read_at().isoformat() if read_at() else None})


# ---------------------------------------------------------------- pickers (New ad set, New campaign, Edit)

def picker_options():
    """What the include / leave-out pickers and Start from a saved audience offer."""
    rows = db.query("SELECT * FROM audiences WHERE gone_at IS NULL ORDER BY lower(name)")
    names = _names(rows, _cached_sources())
    auds = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "kind_words": ar.kind_words(r), "describe": ar.describe(r, names),
             "size_words": ar.size_words(r), "ready": r["ready"], "problem": ar.picker_refusal({}, r)}
            for r in rows if r["kind"] != "saved"]
    saved = []
    for r in rows:
        if r["kind"] != "saved":
            continue
        t = r["targeting"] or {}
        builder = ab.spec_from({"targeting": t})
        builder["include_audiences"] = [i for i in ar.ids_in(t, "custom_audiences")]
        builder["exclude_audiences"] = [i for i in ar.ids_in(t, "excluded_custom_audiences")]
        saved.append({"id": r["id"], "name": r["name"], "describe": ar.describe(r, names), "builder": builder, "form": er.audience_form(t)})
    return {"audiences": auds, "saved_audiences": saved,
            "audience_words": {"lookalike_special": ar.LOOKALIKE_SPECIAL, "advantage": ar.ADVANTAGE_NOTE, "max": ar.MAX_PICKED}}


def pick_check(spec, special=()):
    """[(field, message)] for the audiences a builder picked (and its saved audience): this account's only, before Meta."""
    out = [(f, m) for f, m in ar.pick_problems(spec.get("include_audiences") or [], spec.get("exclude_audiences") or [], known(), special)]
    sid = spec.get("saved_audience_id")
    if sid and not db.query("SELECT 1 FROM audiences WHERE id = %s AND kind = 'saved' AND gone_at IS NULL", (sid,), one=True):
        out.append(("audiences", "That saved audience isn't in this account"))
    return out


def names_for(spec):
    """{id: name} for the audiences a builder picked, read from this account's rows (never the browser's words)."""
    ids = list(spec.get("include_audiences") or []) + list(spec.get("exclude_audiences") or [])
    return {r["id"]: r["name"] for r in db.query("SELECT id, name FROM audiences WHERE id = ANY(%s)", (ids,))} if ids else {}


def with_saved(template, spec):
    """The template whose hints a new ad set keeps: a saved audience picked to start from gives its own (read here, never from the request)."""
    sid = spec.get("saved_audience_id")
    if not sid:
        return template
    r = db.query("SELECT targeting FROM audiences WHERE id = %s AND kind = 'saved' AND gone_at IS NULL", (sid,), one=True)
    return {**(template or {}), "targeting": (r or {}).get("targeting") or {}} if r else template


def name_picked(form, known_rows, live_form=None):
    """Picked audiences named from the account's list (or Meta's read of the ad set); a name sent by the browser is never kept."""
    live = {str(a.get("id")): a.get("name") for k in ("custom_audiences", "excluded_custom_audiences") for a in (live_form or {}).get(k) or []
            if isinstance(a, dict)}
    for k in ("custom_audiences", "excluded_custom_audiences"):
        items = form.get(k) if isinstance(form.get(k), list) else []
        form[k] = [{"id": i, "name": (known_rows.get(i) or {}).get("name") or live.get(i) or (next((a.get("name") for a in items
                    if isinstance(a, dict) and str(a.get("id")) == i), None) if live_form is None else None) or i,
                    **({"subtype": "LOOKALIKE"} if (known_rows.get(i) or {}).get("kind") == "lookalike" else {})}
                   for i in ar.clean_ids(items, cap=live_form is not None)]
    return form
