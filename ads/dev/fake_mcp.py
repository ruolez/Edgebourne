"""Local development only (AM-A): a stand-in for Meta's Ads MCP server (https://mcp.facebook.com/ads), mounted at
/mcp-fake in fake_meta.py's process, so the Mac's link client (ads/bridge/amlink.py) can be run end to end.

- MCP authorization as the 2025-11-25 spec has it: a 401 with `WWW-Authenticate: Bearer resource_metadata=…`, protected
  resource metadata, authorization server metadata (S256 only), dynamic client registration, an authorization endpoint
  that approves at once (there is no browser in QA), a token endpoint with PKCE checks and refresh-token rotation.
- Streamable HTTP JSON-RPC: initialize (+ Mcp-Session-Id), tools/list (every tool the real server lists, annotations
  told truthfully, an inputSchema per link tool; answered as SSE), tools/call for the link's read tools with data shaped
  like the fake Graph account. Write tools answer isError and are counted: QA asserts that count stays 0.
- Controls: /fake/_mcp?refuse_dcr=1|refuse_client=1|deny=1|expire=1|expires_in=<s>|readonly_lie=<tool>|shape=<kind>|
  no_access=<act id>|reset=1 and /fake/_mcp_hits."""
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


def drafts():
    """Shaped like the real 2026-11-13 answer (ad_drafts, values.{field}.new, active_errors, publish_error)."""
    c, s = DATA["CAMPAIGN"], DATA["ADSET"]
    t = 1794594897
    return [
        {"ad_object_id": "120252756936450312", "ad_object_type": "campaign", "parent_ad_object_id": None, "action": "add", "status": "EDITING",
         "validation_status": "VALIDATED", "source": "mcp_campaign_creation", "time_updated": t,
         "values": {"bid_strategy": {"new": "LOWEST_COST_WITHOUT_CAP"}, "buying_type": {"new": "AUCTION"}, "daily_budget": {"new": 2000},
                    "is_odax_campaign_group": {"new": True}, "name": {"new": "Edge Bourne - Dashboards with AI - Leads"},
                    "objective": {"new": "OUTCOME_LEADS"}, "special_ad_categories": {"new": []}, "status": {"new": "ACTIVE"}},
         "active_errors": [], "publish_error": None},
        {"ad_object_id": "120252756936450313", "ad_object_type": "adset", "parent_ad_object_id": "120252756936450312", "action": "add",
         "status": "EDITING", "validation_status": "ERROR", "source": "ads_manager", "time_updated": t + 60,
         "values": {"name": {"new": "Dashboards - SoCal owners"}, "optimization_goal": {"new": "LEAD_GENERATION"}},
         "active_errors": [{"error_summary": "Choose a Page", "error_message": "<b>Pick</b> the Facebook Page this ad set promotes."}],
         "publish_error": None},
        {"ad_object_id": c["id"], "ad_object_type": "campaign", "parent_ad_object_id": None, "action": "update", "status": "EDITING",
         "validation_status": "VALIDATED", "source": "ads_manager", "time_updated": t + 120,
         "values": {"daily_budget": {"old": 2000, "new": 2400}}, "active_errors": [], "publish_error": None},
        {"ad_object_id": s["id"], "ad_object_type": "adset", "parent_ad_object_id": c["id"], "action": "update", "status": "EDITING",
         "validation_status": "VALIDATED", "source": "ads_manager", "time_updated": t + 180,
         "values": {"name": {"old": s["name"], "new": s["name"] + " (wider)"}}, "active_errors": [], "publish_error": None},
    ]


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
        items = drafts() if args.get("object_state") == "draft" else []
        limit = max(1, int(args.get("limit") or 25))
        start = int(args.get("after") or 0)
        page = items[start:start + limit]
        data = {"ad_drafts": page,
                "paging": {"cursors": {"after": str(start + limit)}} if start + limit < len(items) else {},
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
    for k in ("refuse_dcr", "refuse_client", "deny", "expire", "expires_in", "readonly_lie", "shape", "no_access", "ad_error"):
        if k in request.args:
            v = request.args[k]
            if v in ("", "0"):
                STATE["flags"].pop(k, None)
            else:
                STATE["flags"][k] = v
    return jsonify({"flags": STATE["flags"], "clients": len(STATE["clients"])})


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
