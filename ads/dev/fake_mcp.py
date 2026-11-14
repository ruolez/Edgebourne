"""Local development only (AM-A): a stand-in for Meta's Ads MCP server (https://mcp.facebook.com/ads), mounted at
/mcp-fake in fake_meta.py's process, so the Mac's link client (ads/bridge/amlink.py) can be run end to end.

- MCP authorization as the 2025-11-25 spec has it: a 401 with `WWW-Authenticate: Bearer resource_metadata=…`, protected
  resource metadata, authorization server metadata (S256 only), dynamic client registration, an authorization endpoint
  that approves at once (there is no browser in QA), a token endpoint with PKCE checks and refresh-token rotation.
- Streamable HTTP JSON-RPC: initialize (+ Mcp-Session-Id), tools/list (every tool the real server lists, annotations
  told truthfully, an inputSchema per link tool; answered as SSE), tools/call for the link's read tools with data shaped
  like the fake Graph account. Write tools answer isError and are counted: QA asserts that count stays 0.
- Controls: /fake/_mcp?refuse_dcr=1|refuse_client=1|deny=1|expire=1|expires_in=<s>|readonly_lie=<tool>|shape=<kind>|
  no_access=<act id>|reset=1 and /fake/_mcp_hits.
- AM-B drafts (ads_get_ad_entities, object_state "draft", only for the console's own ad account): drafts=none,
  draft_drop=<id,…>, draft_add=<json draft or list> (draft_add= empties), draft_pages=<n> (split over n cursors, a campaign
  with its subtree counts as one), draft_fail_page=1 (every page after the first fails)."""
import ast
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

from flask import Blueprint, Response, jsonify, redirect, request

bp = Blueprint("fake_mcp", __name__)
PREFIX = "/mcp-fake"
SCOPES = ["ads_mcp_management", "ads_read"]
USER = {"id": "10000000000001", "name": "Eugene (fake)"}

STATE = {}
HITS = []
TOKEN_REQS = []
DATA = {}  # fake_meta's globals (the account, campaign, ad set and ads), set by attach()


def reset():
    STATE.clear()
    STATE.update(clients={}, codes={}, access={}, refresh={}, sessions=set(), flags={}, write_calls=0)
    HITS.clear()
    TOKEN_REQS.clear()


reset()


def _tool_lists():
    """The read and write tool names the Mac helper knows (bridge.READ_TOOLS / META_WRITE_TOOLS), read without importing it."""
    try:
        tree = ast.parse(open("/bridge/bridge.py").read())
        found = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name) and t.id in ("READ_TOOLS", "META_WRITE_TOOLS")}
        return found["READ_TOOLS"], found["META_WRITE_TOOLS"]
    except (OSError, KeyError, SyntaxError, ValueError):
        return (["ads_get_ad_accounts", "ads_get_ad_entities", "ads_get_errors", "ads_get_dataset_quality", "ads_get_ad_preview_screenshot",
                 "ads_insights_advertiser_context", "ads_insights_anomaly_signal", "ads_insights_auction_ranking_benchmarks",
                 "ads_insights_industry_benchmark", "ads_insights_performance_trend", "ads_insights_performance_vs_peers"],
                ["ads_activate_entity", "ads_update_entity", "ads_create_campaign", "ads_create_ad"])


def base():
    return request.host_url.rstrip("/") + PREFIX


def flag(name):
    return STATE["flags"].get(name)


# ---------------------------------------------------------------- OAuth

@bp.get(PREFIX + "/.well-known/oauth-protected-resource")
@bp.get("/.well-known/oauth-protected-resource" + PREFIX + "/mcp")
def protected_resource():
    return jsonify({"resource": base() + "/mcp", "authorization_servers": [base()], "scopes_supported": SCOPES,
                    "bearer_methods_supported": ["header"]})


@bp.get(PREFIX + "/.well-known/oauth-authorization-server")
@bp.get("/.well-known/oauth-authorization-server" + PREFIX)
def as_metadata():
    b = base()
    return jsonify({"issuer": b, "authorization_endpoint": b + "/authorize", "token_endpoint": b + "/token",
                    "registration_endpoint": b + "/register", "revocation_endpoint": b + "/revoke", "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": SCOPES})


@bp.post(PREFIX + "/register")
def register():
    body = request.get_json(silent=True) or {}
    HITS.append({"method": "oauth/register", "client_name": body.get("client_name")})
    if flag("refuse_dcr"):
        return jsonify({"error": "invalid_redirect_uri", "error_description": "redirect_uris are not registered"}), 400
    uris = body.get("redirect_uris") or []
    if not uris or body.get("token_endpoint_auth_method") != "none":
        return jsonify({"error": "invalid_client_metadata"}), 400
    cid = "fake-client-" + secrets.token_hex(6)
    STATE["clients"][cid] = {"redirect_uris": uris, "name": body.get("client_name")}
    return jsonify({"client_id": cid, "client_id_issued_at": int(time.time()), "redirect_uris": uris,
                    "grant_types": ["authorization_code", "refresh_token"], "token_endpoint_auth_method": "none"}), 201


def known_client(cid):
    return cid in STATE["clients"] or (cid and cid.isdigit())  # a Meta app id is a pre-registered client


@bp.get(PREFIX + "/authorize")
def authorize():
    a = request.args
    HITS.append({"method": "oauth/authorize", "client_id": a.get("client_id"), "resource": a.get("resource"), "scope": a.get("scope")})
    redirect_uri, state = a.get("redirect_uri"), a.get("state")
    client = STATE["clients"].get(a.get("client_id"))
    if not known_client(a.get("client_id")) or (client and redirect_uri not in client["redirect_uris"]):
        return "Unknown client or redirect", 400
    def back(**params):
        return redirect(f"{redirect_uri}?{urlencode({**params, 'state': state})}", 302)
    if flag("refuse_client"):
        return back(error="unauthorized_client", error_description="This app isn't allowed to use the Ads MCP server")
    if a.get("response_type") != "code" or a.get("code_challenge_method") != "S256" or len(a.get("code_challenge") or "") != 43:
        return back(error="invalid_request", error_description="PKCE S256 is required")
    if a.get("resource") != base() + "/mcp":
        return back(error="invalid_target", error_description="resource must name the MCP server")
    if flag("deny") or a.get("auto") == "deny":
        return back(error="access_denied", error_description="The user said no")
    code = secrets.token_urlsafe(24)
    STATE["codes"][code] = {"client_id": a.get("client_id"), "challenge": a.get("code_challenge"), "redirect_uri": redirect_uri,
                            "resource": a.get("resource"), "scope": a.get("scope")}
    return back(code=code)


def issue(client_id, scope):
    access, refresh = "fake-at-" + secrets.token_urlsafe(18), "fake-rt-" + secrets.token_urlsafe(18)
    expires = int(flag("expires_in") or 3600)
    STATE["access"][access] = {"client_id": client_id, "exp": time.time() + expires}
    STATE["refresh"][refresh] = {"client_id": client_id, "valid": True, "scope": scope}
    return {"access_token": access, "token_type": "Bearer", "expires_in": expires, "refresh_token": refresh, "scope": scope or " ".join(SCOPES)}


@bp.post(PREFIX + "/token")
def token():
    f = request.form
    TOKEN_REQS.append({k: (v if k not in ("code", "refresh_token", "code_verifier") else bool(v)) for k, v in f.items()})
    if f.get("grant_type") == "authorization_code":
        c = STATE["codes"].pop(f.get("code"), None)
        verifier = f.get("code_verifier") or ""
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if not c or c["client_id"] != f.get("client_id") or c["redirect_uri"] != f.get("redirect_uri") or challenge != c["challenge"]:
            return jsonify({"error": "invalid_grant"}), 400
        if f.get("resource") != c["resource"]:
            return jsonify({"error": "invalid_target"}), 400
        return jsonify(issue(c["client_id"], c["scope"]))
    if f.get("grant_type") == "refresh_token":
        r = STATE["refresh"].get(f.get("refresh_token"))
        if flag("expire") or not r or not r["valid"] or r["client_id"] != f.get("client_id"):
            return jsonify({"error": "invalid_grant", "error_description": "The refresh token is no longer valid"}), 400
        r["valid"] = False  # rotated: the old one is refused from now on
        return jsonify(issue(r["client_id"], r["scope"]))
    return jsonify({"error": "unsupported_grant_type"}), 400


@bp.post(PREFIX + "/revoke")
def revoke():
    """RFC 7009: the refresh token (and anything else named) stops working; always 200."""
    f = request.form
    r = STATE["refresh"].get(f.get("token"))
    HITS.append({"method": "oauth/revoke", "hint": f.get("token_type_hint"), "known": bool(r)})
    if r:
        r["valid"] = False
    STATE["access"].pop(f.get("token"), None)
    return "", 200


# ---------------------------------------------------------------- MCP

def unauthorized():
    res = jsonify({"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}})
    res.status_code = 401
    res.headers["WWW-Authenticate"] = (f'Bearer resource_metadata="{base()}/.well-known/oauth-protected-resource", '
                                       f'scope="{" ".join(SCOPES)}"')
    return res


def authorized():
    h = request.headers.get("Authorization", "")
    t = STATE["access"].get(h[7:] if h.startswith("Bearer ") else "")
    return bool(t) and t["exp"] > time.time() and not flag("expire")


def act(n):
    return f"act_{n}"


def accounts():
    hidden = flag("no_access")
    rows = [{"id": act(DATA["ACCOUNT"]), "name": "Edge Bourne", "account_status": 1}]
    rows += [{"id": act(k), "name": v["name"], "account_status": v["account_status"]} for k, v in DATA["OTHER_ACCOUNTS"].items()]
    return [r for r in rows if r["id"] != hidden and r["id"][4:] != hidden]


def _d(oid, kind, values, parent=None, action="add", at=0, errors=None, publish_error=None, source="ads_manager", validation="VALIDATED"):
    return {"ad_object_id": oid, "ad_object_type": kind, "parent_ad_object_id": parent, "action": action, "status": "EDITING",
            "validation_status": validation, "source": source, "time_updated": 1794594897 + at,
            "values": {k: (v if isinstance(v, dict) and ({"new", "old"} & set(v)) else {"new": v}) for k, v in values.items()},
            "active_errors": errors or [], "publish_error": publish_error}


RIVERSIDE = {"geo_locations": {"cities": [{"key": "2421696", "name": "Riverside, CA", "radius": 25, "distance_unit": "mile"}],
                               "location_types": ["home", "recent"]},
             "age_min": 25, "age_max": 65, "targeting_automation": {"advantage_audience": 1}}
ORANGE = {"geo_locations": {"cities": [{"key": "2420605", "name": "Irvine, CA", "radius": 20, "distance_unit": "mile"}]},
          "age_min": 30, "age_max": 60, "targeting_automation": {"advantage_audience": 0}}
DRAFT_IMAGE = "5f0c1a2b3c4d5e6f708192a3b4c5d6e7"  # an image hash the drafts use (not uploaded through the fake's library)


def _image_ad(oid, parent, name, title, body, at, page=True):
    link = {"message": body, "name": title, "image_hash": DATA.get("IMAGE_HASH") or DRAFT_IMAGE,
            "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": DATA["FORM"]}}}
    return _d(oid, "ad", {"name": name, "creative": {"object_story_spec": {**({"page_id": DATA["PAGE"]} if page else {}), "link_data": link}}},
              parent=parent, at=at)


def drafts():
    """AM-B: the drafts Eugene (or Claude on his Mac) staged in Ads Manager, shaped like the real 2026-11-13 answer
    (ad_drafts, values.{field}.new/old, active_errors, publish_error). Only the console's own ad account has them."""
    c, s = DATA["CAMPAIGN"], DATA["ADSET"]
    video = next(iter(DATA["VIDEOS"]))
    page = {"page_id": DATA["PAGE"]}
    base = [
        # 1. The real draft, verbatim, with an ad set Claude staged under it and no ads yet.
        {"ad_object_id": "120252756936450312", "ad_object_type": "campaign", "parent_ad_object_id": None, "action": "add", "status": "EDITING",
         "validation_status": "VALIDATED", "source": "mcp_campaign_creation", "time_updated": 1794594897,
         "values": {"bid_strategy": {"new": "LOWEST_COST_WITHOUT_CAP"}, "buying_type": {"new": "AUCTION"}, "daily_budget": {"new": 2000},
                    "is_odax_campaign_group": {"new": True}, "name": {"new": "Edge Bourne - Dashboards with AI - Leads"},
                    "objective": {"new": "OUTCOME_LEADS"}, "special_ad_categories": {"new": []}, "status": {"new": "ACTIVE"}},
         "active_errors": [], "publish_error": None},
        _d("120252756936450313", "adset", {"name": "Dashboards - Riverside owners", "optimization_goal": "LEAD_GENERATION",
                                           "billing_event": "IMPRESSIONS", "destination_type": "ON_AD", "promoted_object": page,
                                           "targeting": RIVERSIDE}, parent="120252756936450312", at=60, source="mcp_campaign_creation"),
        # 2. Complete: a campaign, its ad set and two ads (a picture and a video) with the lead form.
        _d("120252756936460001", "campaign", {"name": "Edge Bourne - Order portal - Leads", "objective": "OUTCOME_LEADS", "buying_type": "AUCTION",
                                              "daily_budget": 2000, "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "special_ad_categories": [],
                                              "status": "ACTIVE"}, at=300),
        _d("120252756936460002", "adset", {"name": "Order portal - Riverside", "optimization_goal": "LEAD_GENERATION", "billing_event": "IMPRESSIONS",
                                           "destination_type": "ON_AD", "promoted_object": page, "targeting": RIVERSIDE},
           parent="120252756936460001", at=310),
        _image_ad("120252756936460003", "120252756936460002", "Portal 1 - Orders at 2 AM", "Orders that come in on their own",
                  "Customers order any time, even at 2 AM.\nFree intro call for Southern California businesses.", 320),
        _d("120252756936460004", "ad", {"name": "Portal 2 - Email orders", "creative": {"object_story_spec": {"page_id": DATA["PAGE"], "video_data": {
            "message": "Email orders get read in automatically.\nFree intro call for Southern California businesses.",
            "title": "No more retyping orders", "video_id": video,
            "call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": DATA["FORM"]}}}}}}, parent="120252756936460002", at=330),
        # 3. A staged edit of the live campaign: budget $20 → $25 and a new name.
        _d(c["id"], "campaign", {"daily_budget": {"old": 2000, "new": 2500}, "name": {"old": c["name"], "new": c["name"] + " (Nov)"}},
           action="update", at=400),
        # 4. Meta has problems with it: no Facebook Page anywhere (and a name with markup in it).
        _d("120252756936460010", "campaign", {"name": 'Weekly report <img src=x onerror="window.__drXss=1"> - Leads', "objective": "OUTCOME_LEADS",
                                              "buying_type": "AUCTION", "daily_budget": 1500, "bid_strategy": "LOWEST_COST_WITHOUT_CAP"}, at=500,
           errors=[{"message": "Choose a Facebook Page for this ad."}], publish_error={"message": "Couldn't publish: the ad set has no Page."},
           validation="ERROR"),
        _d("120252756936460011", "adset", {"name": "Weekly report - SoCal", "destination_type": "ON_AD", "targeting": RIVERSIDE},
           parent="120252756936460010", at=510),
        _image_ad("120252756936460012", "120252756936460011", "Weekly 1", "Your Monday report, already done", "No more Sunday nights.", 520, page=False),
        # 5. A Sales campaign: the console builds lead campaigns only.
        _d("120252756936460020", "campaign", {"name": "Edge Bourne - Store - Sales", "objective": "OUTCOME_SALES", "buying_type": "AUCTION",
                                              "daily_budget": 3000, "bid_strategy": "LOWEST_COST_WITHOUT_CAP"}, at=600),
        # 6. A new ad set staged under the live campaign.
        _d("120252756936460030", "adset", {"name": "SoCal owners - Orange County", "optimization_goal": "LEAD_GENERATION",
                                           "billing_event": "IMPRESSIONS", "destination_type": "ON_AD", "promoted_object": page, "targeting": ORANGE},
           parent=c["id"], at=700),
        # 7. A staged edit of the live ad set's name (the console doesn't apply names yet: Change it in Ads Manager).
        _d(s["id"], "adset", {"name": {"old": s["name"], "new": s["name"] + " (wider)"}}, parent=c["id"], action="update", at=800),
    ]
    if flag("drafts") == "none":
        return []
    dropped = set((flag("draft_drop") or "").split(","))
    return [d for d in base if d["ad_object_id"] not in dropped] + list(STATE.get("draft_add") or [])


def draft_units(items):
    """Meta's limit counts a campaign with everything under it as one: the answer is paged by those units."""
    ids = {d["ad_object_id"]: d for d in items}

    def top(d):
        seen = 0
        while d.get("parent_ad_object_id") in ids and d.get("action") == "add" and seen < 5:
            d, seen = ids[d["parent_ad_object_id"]], seen + 1
        return d["ad_object_id"]
    units = {}
    for d in items:
        units.setdefault(top(d), []).append(d)
    return list(units.values())


def benchmarks():
    return {"benchmarks": [{"metric": "cost_per_lead", "value": 4.79, "peer_low": 18, "peer_median": 27, "peer_high": 42,
                            "industry": "Professional services", "region": "US", "period": "last_30d"},
                           {"metric": "ctr", "value": 1.08, "peer_low": 0.9, "peer_median": 1.2, "peer_high": 1.6, "period": "last_30d"}]}


TOOL_SCHEMAS = {
    "ads_get_ad_accounts": {"type": "object", "properties": {}},
    "ads_get_ad_entities": {"type": "object", "properties": {"ad_account_id": {"type": "string"}, "object_state": {"type": "string"},
                                                              "limit": {"type": "integer"}, "after": {"type": "string"}},
                            "required": ["ad_account_id"]},
    "ads_get_errors": {"type": "object", "properties": {"ad_account_id": {"type": "string"}}, "required": ["ad_account_id"]},
    "ads_get_dataset_quality": {"type": "object", "properties": {"ad_account_id": {"type": "string"}}, "required": ["ad_account_id"]},
    "ads_get_ad_preview_screenshot": {"type": "object", "properties": {"ad_id": {"type": "string"}}, "required": ["ad_id"]},
}
INSIGHT = {"type": "object", "properties": {"ad_account_id": {"type": "string"}, "advertiser_job": {"type": "string"}},
           "required": ["ad_account_id"]}


def tools_list():
    reads, writes = _tool_lists()
    out = []
    for name in reads + writes:
        read = name in reads
        hints = {"readOnlyHint": read, "destructiveHint": not read}
        if flag("readonly_lie") == name:
            hints = {"readOnlyHint": False, "destructiveHint": False}
        schema = TOOL_SCHEMAS.get(name) or (INSIGHT if name.startswith("ads_insights_") else {"type": "object", "properties": {}})
        out.append({"name": name, "description": f"Fake {name}", "inputSchema": schema, "annotations": hints})
    return out


def call(name, args):
    reads, writes = _tool_lists()
    if name not in reads:
        STATE["write_calls"] += 1
        return {"isError": True, "content": [{"type": "text", "text": "The fake MCP server refuses every write"}]}
    ad = str(args.get("ad_account_id") or "")
    if ad and ad not in [r["id"] for r in accounts()]:
        return {"isError": True, "content": [{"type": "text", "text": f"No access to {ad}"}]}
    kind = {"ads_get_errors": "ad_errors", "ads_insights_industry_benchmark": "benchmarks", "ads_get_ad_entities": "drafts"}.get(name)
    if kind and flag("shape") == kind:
        return {"content": [{"type": "text", "text": json.dumps({"surprise": "a shape nobody expected"})}],
                "structuredContent": {"surprise": "a shape nobody expected"}}
    if name == "ads_get_ad_accounts":
        data = {"data": accounts(), "user": USER}
    elif name == "ads_get_ad_entities":
        mine = ad in (act(DATA["ACCOUNT"]), DATA["ACCOUNT"])
        units = draft_units(drafts()) if args.get("object_state") == "draft" and mine else []
        limit = max(1, int(args.get("limit") or 25))
        if flag("draft_pages"):
            limit = max(1, -(-len(units) // int(flag("draft_pages"))))
        start = int(args.get("after") or 0)
        if start and flag("draft_fail_page"):
            return {"isError": True, "content": [{"type": "text", "text": "Please retry your request later."}]}
        page = [d for u in units[start:start + limit] for d in u]
        more = start + limit < len(units)
        data = {"ad_drafts": page,
                "paging": {"cursors": {"after": str(start + limit)}, "next": "https://mcp.fake/next"} if more else {},
                # The real server asks clients to run these; the link must never do it.
                "next_actions": {"actions": [{"step": 1, "tool": "ads_activate_entity", "strength": "required", "read_only": False,
                                              "requires_user_confirmation": False, "suggested_args": {"entity_id": "120252756936450312"}}]}}
    elif name == "ads_get_errors":
        data = {"errors": [{"entity_id": e, "level": "ad", "code": 1487, "summary": "Payment method failed",
                            "message": "Update the payment method in <b>Billing</b>.", "blocking": True, "since": "2026-11-12"}
                           for e in (STATE["flags"].get("ad_error") or "").split(",") if e]}
    elif name == "ads_insights_industry_benchmark":
        data = benchmarks()
    elif name == "ads_insights_performance_vs_peers":
        data = {"peers": [{"metric": "cost_per_lead", "value": 4.79, "peer_value": 27, "percentile": 90, "direction": "better", "period": "last_30d"}]}
    elif name == "ads_insights_auction_ranking_benchmarks":
        data = {"rankings": [{"entity_id": aid, "quality_ranking": "ABOVE_AVERAGE", "engagement_rate_ranking": "AVERAGE",
                              "conversion_rate_ranking": "ABOVE_AVERAGE", "period": "last_7d"} for aid in DATA["REAL_AD_IDS"][:2]]}
    elif name == "ads_insights_anomaly_signal":
        data = {"anomalies": [{"entity_id": DATA["REAL_AD_IDS"][1], "level": "ad", "metric": "cost_per_lead", "direction": "up",
                               "change_pct": 48, "detected_on": time.strftime("%Y-%m-%d"), "summary": "Cost per lead rose 48% against its 7-day pattern."}]}
    elif name == "ads_insights_performance_trend":
        data = {"trends": [{"metric": "cost_per_lead", "direction": "down", "change_pct": -12, "period": "last_14d"}]}
    elif name == "ads_get_dataset_quality":
        data = {"events": [{"event": "Lead", "match_quality": 7.8, "advice": "Send email and phone with each event."},
                           {"event": "PageView", "match_quality": 5.1}]}
    elif name == "ads_insights_advertiser_context":
        data = {"context": {"vertical": "Professional services", "business_type": "B2B services", "region": "US"}}
    elif name == "ads_get_ad_preview_screenshot":
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(24)).decode()
        return {"content": [{"type": "image", "mimeType": "image/png", "data": png}]}
    else:
        data = {"data": []}
    return {"content": [{"type": "text", "text": json.dumps(data)}], "structuredContent": data}


def rpc_result(rid, result, sse=False):
    body = {"jsonrpc": "2.0", "id": rid, "result": result}
    if sse:
        return Response(f"event: message\ndata: {json.dumps(body)}\n\n", mimetype="text/event-stream")
    return jsonify(body)


@bp.route(PREFIX + "/mcp", methods=["POST", "DELETE", "GET"])
def mcp():
    if request.method == "GET":
        return "", 405
    if not authorized():
        HITS.append({"method": "unauthorized"})
        return unauthorized()
    if request.method == "DELETE":
        STATE["sessions"].discard(request.headers.get("Mcp-Session-Id"))
        return "", 200
    msg = request.get_json(silent=True) or {}
    method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if method == "initialize":
        sid = secrets.token_hex(8)
        STATE["sessions"].add(sid)
        HITS.append({"method": method, "protocol": params.get("protocolVersion"), "client": (params.get("clientInfo") or {}).get("name")})
        res = rpc_result(rid, {"protocolVersion": params.get("protocolVersion") or "2025-11-25", "capabilities": {"tools": {}},
                               "serverInfo": {"name": "fake-meta-ads-mcp", "version": "0.1"}})
        res.headers["Mcp-Session-Id"] = sid
        return res
    if request.headers.get("Mcp-Session-Id") not in STATE["sessions"]:
        return jsonify({"jsonrpc": "2.0", "id": rid, "error": {"code": -32600, "message": "Unknown session"}}), 404
    if method == "notifications/initialized":
        return "", 202
    if method == "tools/list":
        HITS.append({"method": method})
        return rpc_result(rid, {"tools": tools_list()}, sse=True)
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        HITS.append({"method": method, "tool": name, "args": args})
        return rpc_result(rid, call(name, args))
    return jsonify({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})


# ---------------------------------------------------------------- QA controls

@bp.get("/fake/_mcp")
def controls():
    if request.args.get("reset"):
        reset()
    if request.args.get("draft_add"):  # AM-B: one more draft (or a list), as Meta would list it
        add = json.loads(request.args["draft_add"])
        STATE.setdefault("draft_add", []).extend(add if isinstance(add, list) else [add])
    if request.args.get("draft_add") == "":
        STATE["draft_add"] = []
    for k in ("refuse_dcr", "refuse_client", "deny", "expire", "expires_in", "readonly_lie", "shape", "no_access", "ad_error",
              "drafts", "draft_drop", "draft_pages", "draft_fail_page"):
        if k in request.args:
            v = request.args[k]
            if v in ("", "0"):
                STATE["flags"].pop(k, None)
            else:
                STATE["flags"][k] = v
    return jsonify({"flags": STATE["flags"], "clients": len(STATE["clients"])})


@bp.get("/fake/_mcp_drafts")
def drafts_now():
    """The drafts as the link would read them (QA screenshots seed the console with these; no OAuth here, dev only)."""
    return jsonify({"ad_drafts": drafts(), "complete": True})


@bp.get("/fake/_mcp_hits")
def hits():
    out = {"hits": list(HITS), "write_calls": STATE["write_calls"], "token_requests": list(TOKEN_REQS)}
    if request.args.get("clear"):
        HITS.clear()
        TOKEN_REQS.clear()
    return jsonify(out)


def attach(app, data):
    DATA.update(data)
    app.register_blueprint(bp)
