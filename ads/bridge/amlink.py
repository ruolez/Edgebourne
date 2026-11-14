#!/usr/bin/env python3
"""amlink: the Mac's own read-only link to Meta's Ads MCP server (AM-A, desk 3.1).

The console can't see Ads Manager drafts, Meta's error details, benchmarks and a few other things through the Graph
API. Meta's Ads MCP server (https://mcp.facebook.com/ads) shows them to the person who signed in. This helper is an
MCP client of its own: one Facebook login in the Mac's browser (MCP authorization: OAuth 2.1, PKCE S256, the resource
indicator, dynamic client registration or the console's Meta app as the client), its token in its OWN Keychain item
("ads-manager-link", never Claude Code's credentials), and fixed tool calls with no Claude in the loop.

Reads only. LINK_TOOLS is the whole list this client may ever call, checked before any network request; a tool Meta
marks as one that changes things is refused even when listed, and the `next_actions` Meta's answers suggest are never
run. What it reads goes to the console under the pass the console handed out for one account (`X-Link-Pass`).

If Meta won't take this client, the bridge falls back to a headless Claude run with the same read tools only.

  amlink.py --once                 one plan from the console (connect, disconnect or passes), then exit
  amlink.py --probe KIND --ad-account ID    read one kind and print what came back (nothing is sent)
"""
import argparse
import base64
import hashlib
import http.server
import importlib.machinery
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
desk = sys.modules.get("desk") or importlib.machinery.SourceFileLoader("desk", os.path.join(HERE, "desk")).load_module()

MCP_URL = "https://mcp.facebook.com/ads"          # ADS_LINK_MCP overrides it only with ADS_DESK_CONFIG set (tests)
PROTOCOL = "2025-11-25"
KEYCHAIN_SERVICE = "ads-manager-link"             # its own item; never "Claude Code-credentials" or ads-desk-claude
REDIRECT_PORT = 47615
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"  # the loopback IP the catcher listens on (RFC 8252 §7.3)
CLIENT_NAME = "Edge Bourne Ads console (Mac)"
ACCEPT = "application/json, text/event-stream"
LINK_TOOLS = {                                    # the only tools this client may ever call
    "drafts": "ads_get_ad_entities", "ad_errors": "ads_get_errors",
    "benchmarks": "ads_insights_industry_benchmark", "peers": "ads_insights_performance_vs_peers",
    "auction_ranking": "ads_insights_auction_ranking_benchmarks", "anomalies": "ads_insights_anomaly_signal",
    "trend": "ads_insights_performance_trend", "dataset_quality": "ads_get_dataset_quality",
    "advertiser_context": "ads_insights_advertiser_context", "screenshots": "ads_get_ad_preview_screenshot",
    "_accounts": "ads_get_ad_accounts",           # connected-as and no_access checks
}
ALLOWED = frozenset(LINK_TOOLS.values())
TEST_HOSTS = ("localhost", "127.0.0.1", "fake-meta")
DRAFT_PAGE = 25
DRAFT_PAGES = 10
LOGIN_SECONDS = 300
REFRESH_EARLY = 120
STR_MAX = 300
ADVERTISER_JOB = "report_measure_or_look_up"     # Meta's server asks tools that take it to name the user's goal


class NotAllowed(Exception):
    """A tool the link may never call (not on LINK_TOOLS, or marked by Meta as changing things)."""


class LinkError(Exception):
    """A read that didn't work. `state` is what it means for the whole link ("expired", "fallback", "not_connected",
    "refused"), or None when only this pass failed. `retry`: a network hiccup, try again in a minute."""

    def __init__(self, message, state=None, retry=False):
        super().__init__(message)
        self.state = state
        self.retry = retry


def testing():
    return bool(os.environ.get("ADS_DESK_CONFIG"))


def mcp_url():
    return os.environ["ADS_LINK_MCP"] if testing() and os.environ.get("ADS_LINK_MCP") else MCP_URL


def cut(text, n=STR_MAX):
    return " ".join(str(text or "").split())[:n]


# ---------------------------------------------------------------- pure helpers

def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def challenge(verifier):
    return b64url(hashlib.sha256(verifier.encode()).digest())


def pkce_pair():
    """(verifier, S256 challenge): 64 characters from the unreserved set (RFC 7636 asks for 43-128)."""
    verifier = b64url(secrets.token_bytes(48))
    return verifier, challenge(verifier)


def parse_www_authenticate(value):
    """The Bearer parameters of a WWW-Authenticate header, lower-case names ({resource_metadata, scope, error, …})."""
    m = re.match(r"\s*Bearer\b\s*(.*)$", value or "", re.I | re.S)
    if not m:
        return {}
    return {k.lower(): (q.replace('\\"', '"') if q or not t else t)
            for k, q, t in re.findall(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,]+))', m.group(1))}


def _origin_path(url):
    u = urllib.parse.urlsplit(url)
    return f"{u.scheme}://{u.netloc}", u.path.rstrip("/")


def resource_metadata_urls(mcp, params):
    """Where the protected resource metadata may be (MCP 2025-11-25): the 401's resource_metadata first, then the
    well-known URI with the server's path, then at the root."""
    origin, path = _origin_path(mcp)
    urls = ([params["resource_metadata"]] if params.get("resource_metadata") else [])
    urls += ([f"{origin}/.well-known/oauth-protected-resource{path}"] if path else []) + [f"{origin}/.well-known/oauth-protected-resource"]
    return list(dict.fromkeys(urls))


def as_metadata_urls(issuer):
    """Authorization server metadata, in the spec's order, for an issuer with or without a path."""
    origin, path = _origin_path(issuer)
    if path:
        return [f"{origin}/.well-known/oauth-authorization-server{path}", f"{origin}/.well-known/openid-configuration{path}",
                f"{origin}{path}/.well-known/openid-configuration"]
    return [f"{origin}/.well-known/oauth-authorization-server", f"{origin}/.well-known/openid-configuration"]


def check_url(url, test=None):
    """Every OAuth and MCP address must be https; plain http only for the local fake while testing."""
    test = testing() if test is None else test
    u = urllib.parse.urlsplit(str(url or ""))
    if u.scheme == "https" and u.netloc:
        return url
    if test and u.scheme == "http" and u.hostname in TEST_HOSTS:
        return url
    raise LinkError(f"Meta's login named an address that isn't https ({cut(url, 80)}); the link won't use it.", state="refused")


def check_as(meta, test=None):
    """Refuse to sign in unless the authorization server offers PKCE with S256 and https endpoints."""
    if "S256" not in (meta.get("code_challenge_methods_supported") or []):
        raise LinkError("Meta's login doesn't offer PKCE (S256), so the link won't sign in.", state="refused")
    for key in ("authorization_endpoint", "token_endpoint"):
        if not meta.get(key):
            raise LinkError(f"Meta's login metadata has no {key}.", state="refused")
        check_url(meta[key], test)
    if meta.get("registration_endpoint"):
        check_url(meta["registration_endpoint"], test)
    return meta


def fallback_reason(step, status, body):
    """(verdict, words) for a refusal at `step` (register, authorize, token, mcp). verdict: "fallback" (Meta won't take
    this client: let Claude read instead), "not_connected" (Eugene said no), "retry" (network or Meta busy), or None."""
    body = body if isinstance(body, dict) else {}
    err = str(body.get("error") or "")
    desc = cut(body.get("error_description") or body.get("message") or err, 160)
    text = json.dumps(body)
    if status is None:
        return "retry", "Couldn't reach Meta's server. Trying again in a minute."
    if step == "authorize" and err == "access_denied":
        return "not_connected", "You didn't allow it on the Facebook page."
    if step == "register" and (err in ("invalid_redirect_uri", "invalid_client_metadata") or "redirect_uris are not registered" in text):
        return "fallback", f"Meta didn't accept the Mac's helper as a client ({desc})."
    if step in ("authorize", "token") and err in ("invalid_client", "unauthorized_client"):
        return "fallback", f"Meta didn't let the Mac's helper sign in ({desc})."
    if step == "mcp" and status == 403 and re.search(r"client", text, re.I) and re.search(r"support|allow|permit", text, re.I):
        return "fallback", f"Meta's Ads server doesn't support the Mac's helper ({desc})."
    if status == 429 or status >= 500:
        return "retry", f"Meta's server is busy ({status}). Trying again in a minute."
    return None, f"Meta answered {status} at {step}" + (f": {desc}" if desc else "")


def pick_scope(available, wide=False):
    """The scope to ask for: only the read scopes Meta lists ("ads_read"), unless Meta already refused that (`wide`)
    or lists no read scope. None when Meta names no scope at all."""
    names = [s for s in (available or "").split() if s]
    if not names:
        return None
    reads = [s for s in names if re.search(r"(^|_)read($|_)", s)]
    return " ".join(names if wide or not reads else reads)


def insufficient_scope(headers):
    """True when Meta's 403 says the login's permission is too narrow (RFC 6750 insufficient_scope)."""
    return parse_www_authenticate((headers or {}).get("www-authenticate")).get("error") == "insufficient_scope"


def same_url(a, b):
    return str(a or "").rstrip("/") == str(b or "").rstrip("/")


def tool_args(kind, ad_account_id, scope=None, after=None):
    """The arguments of one kind's read (the console's am_link.tool_args holds the same; a test compares them)."""
    if kind == "screenshots":
        return {"ad_id": str(scope)}
    if kind == "_accounts":
        return {}
    args = {"ad_account_id": f"act_{ad_account_id}"}
    if kind == "drafts":
        args.update(object_state="draft", limit=DRAFT_PAGE)
        if after:
            args["after"] = after
    return args


def with_known(args, schema):
    """Arguments Meta's server documents for every read: the user's goal, when the tool takes it."""
    props = (schema or {}).get("properties")
    if isinstance(props, dict) and "advertiser_job" in props and "advertiser_job" not in args:
        return {**args, "advertiser_job": ADVERTISER_JOB}
    return args


def check_args(name, args, schema):
    """The tool's inputSchema must still take these arguments: every required key present and no key it lacks.
    A mismatch is never guessed around."""
    schema = schema or {}
    props = schema.get("properties")
    missing = [k for k in schema.get("required") or [] if k not in args]
    extra = [k for k in args if isinstance(props, dict) and k not in props]
    if missing or extra:
        raise LinkError(f"Meta changed the tool `{name}`; update the Mac helper.")


def tool_refusal(tool):
    """Why Meta's own description of a tool rules it out, or None."""
    hints = (tool or {}).get("annotations") or {}
    if hints.get("readOnlyHint") is False or hints.get("destructiveHint") is True:
        return "Meta marks this tool as one that changes things; the link won't call it."
    return None


def result_payload(result):
    """What a tools/call answer holds: its structuredContent, else the JSON in its text, else its images."""
    result = result or {}
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    content = result.get("content") or []
    images = [{"mime": c.get("mimeType"), "data_b64": c.get("data")} for c in content if c.get("type") == "image"]
    if images:
        return {"images": images}
    texts = [c.get("text") or "" for c in content if c.get("type") == "text"]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except ValueError:
            return texts[0]
    return texts


def account_ids(payload):
    """act_ ids in an ads_get_ad_accounts answer, or None when its shape isn't known (then nothing is concluded)."""
    rows = payload if isinstance(payload, list) else next(
        (payload[k] for k in ("data", "ad_accounts", "accounts") if isinstance(payload, dict) and isinstance(payload.get(k), list)), None)
    if rows is None:
        return None
    out = set()
    for r in rows:
        ident = str((r or {}).get("id") or (r or {}).get("account_id") or "") if isinstance(r, dict) else str(r)
        if ident:
            out.add(ident if ident.startswith("act_") else f"act_{ident}")
    return out


def connected_name(payload):
    user = payload.get("user") if isinstance(payload, dict) else None
    return cut((user or {}).get("name"), 120) if isinstance(user, dict) else ""


def keychain_write(account, secret):
    """(argv, stdin) for `security -i`: the token is in the commands read from stdin, never on a command line."""
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", secret or "") or re.search(r'["\n\\]', account or ""):
        raise ValueError("unexpected characters for the Keychain")
    return ["security", "-i"], f'add-generic-password -U -s {KEYCHAIN_SERVICE} -a "{account}" -l "Ads console: Ads Manager link" -w "{secret}"\n'


def sse_messages(text):
    """JSON-RPC messages in a text/event-stream body (each event's data: lines joined)."""
    out, data = [], []
    for line in (text or "").splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line.strip() and data:
            try:
                out.append(json.loads("\n".join(data)))
            except ValueError:
                pass
            data = []
    return out


# ---------------------------------------------------------------- HTTP, token store

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Http:
    """One request at a time, no redirects followed (the login's redirect is read, not followed)."""

    def __init__(self):
        self.calls = 0
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method, url, headers=None, data=None, timeout=30):
        self.calls += 1
        req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": f"ads-desk-link/{desk.VERSION}", **(headers or {})})
        try:
            with self._opener.open(req, timeout=timeout) as res:
                return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read()


def _json(raw):
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


class TokenStore:
    """The link's token: one JSON blob in the Keychain item `ads-manager-link` (account = the console's address).
    Tests (ADS_DESK_CONFIG set) may use ADS_LINK_TOKEN_FILE instead; the real Keychain is never touched by them."""

    def __init__(self, account):
        self.account = account
        self.file = os.environ.get("ADS_LINK_TOKEN_FILE") if testing() else None

    def load(self):
        if self.file:
            try:
                with open(self.file) as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return None
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", self.account, "-w"],
                             capture_output=True, text=True)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        try:
            return json.loads(base64.b64decode(out.stdout.strip()))
        except ValueError:
            return None

    def save(self, tok):
        if self.file:
            fd = os.open(self.file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(tok, fh)
            return
        argv, stdin = keychain_write(self.account, base64.b64encode(json.dumps(tok).encode()).decode())
        out = subprocess.run(argv, input=stdin, capture_output=True, text=True)
        if out.returncode != 0:
            raise LinkError("Couldn't keep the login in the Mac's Keychain.")

    def delete(self):
        if self.file:
            try:
                os.remove(self.file)
            except FileNotFoundError:
                pass
            return
        subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", self.account], capture_output=True)


# ---------------------------------------------------------------- the login

class Catcher:
    """A one-shot loopback server on 127.0.0.1 that receives the login's code and checks its state."""

    def __init__(self, state, port=REDIRECT_PORT):
        self.state, self.result, self.done = state, None, threading.Event()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - the stdlib's name
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                ok = u.path == "/callback" and q.get("state") == outer.state
                page = ("You can close this tab. The Ads console is reading Ads Manager through your Mac now." if ok and q.get("code")
                        else "You can close this tab." if ok else "This page didn't come from your Mac's Ads console helper.")
                body = f"<!doctype html><meta charset=utf-8><title>Ads console</title><p>{page}</p>".encode()
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                if ok:
                    outer.result = q
                    outer.done.set()

            def log_message(self, *args):
                pass

        try:
            self.server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            raise LinkError(f"Port {port} on the Mac is busy ({exc}); close what uses it and press Connect again.", state="not_connected")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def wait(self, seconds):
        self.done.wait(seconds)
        return self.result

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Link:
    """One Mac's link: discovery, registration, login, tokens. `http` and `store` are swapped in tests."""

    def __init__(self, cfg, http=None, store=None):
        self.cfg = cfg
        self.http = http or Http()
        self.store = store or TokenStore(cfg["base_url"])
        self.url = check_url(mcp_url())
        self.tok = None

    def get_json(self, url):
        check_url(url)
        status, _, body = self.http.request("GET", url, {"Accept": "application/json"})
        return _json(body) if status == 200 else None

    def discover(self, wide=False):
        """Where and how to sign in. The metadata must be about this server (RFC 9728 §3.3: its `resource` is the MCP
        address) and from the issuer it names (RFC 8414 §3.3), or the link doesn't sign in."""
        status, headers, _ = self.http.request("POST", self.url, {"Content-Type": "application/json", "Accept": ACCEPT},
                                               json.dumps(initialize_message()).encode())
        params = parse_www_authenticate(headers.get("www-authenticate")) if status == 401 else {}
        prm = next((m for m in (self.get_json(u) for u in resource_metadata_urls(self.url, params)) if m), None)
        if not prm or not prm.get("authorization_servers"):
            raise LinkError("Meta's Ads server didn't say where to sign in.", state="refused")
        if not same_url(prm.get("resource"), self.url):
            raise LinkError("Meta's sign-in details are for another server; the link won't use them.", state="refused")
        issuer = check_url(prm["authorization_servers"][0])
        asm = next((m for m in (self.get_json(u) for u in as_metadata_urls(issuer)) if m), None)
        if not asm:
            raise LinkError("Meta's login metadata couldn't be read.", state="refused")
        if not same_url(asm.get("issuer"), issuer):
            raise LinkError("Meta's login metadata names another issuer; the link won't sign in.", state="refused")
        check_as(asm)
        if asm.get("revocation_endpoint"):
            check_url(asm["revocation_endpoint"])
        available = params.get("scope") or " ".join(prm.get("scopes_supported") or [])
        scope = pick_scope(available, wide)
        return {"asm": asm, "scope": scope, "issuer": issuer, "narrowed": bool(scope and scope != pick_scope(available, True))}

    def register(self, found, app_id=None):
        if app_id:
            return {"client_id": str(app_id), "kind": "app"}
        endpoint = found["asm"].get("registration_endpoint")
        if not endpoint:
            raise LinkError("Meta's login doesn't take new clients.", state="fallback")
        body = {"client_name": CLIENT_NAME, "redirect_uris": [REDIRECT_URI], "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none"}
        status, _, raw = self.http.request("POST", endpoint, {"Content-Type": "application/json", "Accept": "application/json"},
                                           json.dumps(body).encode())
        if status not in (200, 201) or not _json(raw).get("client_id"):
            verdict, words = fallback_reason("register", status, _json(raw))
            raise LinkError(words, state=verdict if verdict in ("fallback", "not_connected") else "refused", retry=verdict == "retry")
        return {"client_id": _json(raw)["client_id"], "kind": "dcr"}

    def open_browser(self, url):
        if testing() and os.environ.get("ADS_LINK_OPEN") == "fetch":
            # Tests: the fake approves at once; follow its redirect to the loopback catcher ourselves.
            _, headers, _ = self.http.request("GET", url)
            if headers.get("location"):
                self.http.request("GET", headers["location"])
            return
        subprocess.run(["open", url], check=False)

    def login(self, found, client):
        asm = found["asm"]
        verifier, chal = pkce_pair()
        state = secrets.token_urlsafe(24)
        query = {"response_type": "code", "client_id": client["client_id"], "redirect_uri": REDIRECT_URI, "code_challenge": chal,
                 "code_challenge_method": "S256", "state": state, "resource": self.url}
        if found.get("scope"):
            query["scope"] = found["scope"]
        url = asm["authorization_endpoint"] + ("&" if "?" in asm["authorization_endpoint"] else "?") + urllib.parse.urlencode(query)
        catcher = Catcher(state)
        try:
            self.open_browser(url)
            got = catcher.wait(LOGIN_SECONDS)
        finally:
            catcher.close()
        if not got:
            raise LinkError("The Facebook page wasn't finished within 5 minutes. Press Connect again.", state="not_connected")
        if got.get("error") or not got.get("code"):
            verdict, words = fallback_reason("authorize", 400, got)
            raise LinkError(words, state=verdict if verdict in ("fallback", "not_connected") else "refused")
        form = {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT_URI, "client_id": client["client_id"],
                "code_verifier": verifier, "resource": self.url}
        status, _, raw = self.http.request("POST", asm["token_endpoint"], {"Content-Type": "application/x-www-form-urlencoded",
                                                                          "Accept": "application/json"}, urllib.parse.urlencode(form).encode())
        tok = _json(raw)
        if status != 200 or not tok.get("access_token"):
            verdict, words = fallback_reason("token", status, tok)
            raise LinkError(words, state=verdict if verdict in ("fallback", "not_connected") else "refused")
        self.tok = {"client_id": client["client_id"], "client_kind": client["kind"], "access_token": tok["access_token"],
                    "refresh_token": tok.get("refresh_token"), "expires_at": time.time() + int(tok.get("expires_in") or 3600),
                    "issuer": found["issuer"], "token_endpoint": asm["token_endpoint"],
                    "revocation_endpoint": asm.get("revocation_endpoint"), "scope": cut(tok.get("scope") or found.get("scope") or "", 200),
                    "narrowed": bool(found.get("narrowed"))}
        self.store.save(self.tok)
        return self.tok

    def refresh(self, tok):
        if not tok or not tok.get("refresh_token"):
            raise LinkError("Reconnect needed: Meta asked for a new login.", state="expired")
        form = {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": tok["client_id"], "resource": self.url}
        status, _, raw = self.http.request("POST", check_url(tok["token_endpoint"]), {"Content-Type": "application/x-www-form-urlencoded",
                                                                                     "Accept": "application/json"}, urllib.parse.urlencode(form).encode())
        body = _json(raw)
        if status in (400, 401) and body.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client"):
            raise LinkError("Reconnect needed: Meta asked for a new login.", state="expired")
        if status != 200 or not body.get("access_token"):
            raise LinkError(f"Meta's login answered {status} to a token refresh.", retry=True)
        new = {**tok, "access_token": body["access_token"], "refresh_token": body.get("refresh_token") or tok["refresh_token"],
               "expires_at": time.time() + int(body.get("expires_in") or 3600)}
        self.store.save(new)  # a rotated refresh token replaces the old one
        self.tok = new
        return new

    def revoke(self):
        """Disconnect: ask Meta to cancel the refresh token (when its login offers revocation) before the Keychain item
        is deleted, so a copy of it stops working too. Best effort: the local login goes either way."""
        tok = self.tok or self.store.load()
        if not tok or not tok.get("revocation_endpoint"):
            return False
        token, hint = (tok["refresh_token"], "refresh_token") if tok.get("refresh_token") else (tok.get("access_token"), "access_token")
        if not token:
            return False
        try:
            status, _, _ = self.http.request("POST", check_url(tok["revocation_endpoint"]),
                                             {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                                             urllib.parse.urlencode({"token": token, "token_type_hint": hint, "client_id": tok["client_id"]}).encode(),
                                             timeout=15)
            return status == 200
        except (LinkError, urllib.error.URLError, OSError):
            return False

    def widen_next(self):
        """Meta refused the read-only permission: the next Connect asks for every scope Meta lists."""
        tok = self.tok or self.store.load() or {}
        self.store.save({**tok, "widen": True})

    def token(self):
        tok = self.tok or self.store.load()
        if not tok:
            raise LinkError("The Mac has no Facebook login for the link. Press Reconnect in Settings.", state="expired")
        if tok.get("expires_at", 0) - time.time() < REFRESH_EARLY:
            tok = self.refresh(tok)
        self.tok = tok
        return tok["access_token"]


def initialize_message():
    return {"jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "edgebourne-ads-link", "version": desk.VERSION}}}


# ---------------------------------------------------------------- MCP session

class Session:
    """One streamable-HTTP MCP session per pass: initialize, tools/list once, tools/call for allowed tools only."""

    def __init__(self, link):
        self.link = link
        self.sid = None
        self.seq = 0
        self.tools = {}

    def rpc(self, method, params=None, notify=False, retried=False):
        headers = {"Content-Type": "application/json", "Accept": ACCEPT, "Authorization": f"Bearer {self.link.token()}"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        if method != "initialize":
            headers["MCP-Protocol-Version"] = PROTOCOL
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self.seq += 1
            msg["id"] = self.seq
        status, h, raw = self.link.http.request("POST", self.link.url, headers, json.dumps(msg).encode(), timeout=60)
        if status == 401 and not retried:
            self.link.refresh(self.link.tok or self.link.store.load())
            return self.rpc(method, params, notify, retried=True)
        if status == 401:
            raise LinkError("Reconnect needed: Meta asked for a new login.", state="expired")
        if status == 403 and insufficient_scope(h) and (self.link.tok or {}).get("narrowed"):
            self.link.widen_next()
            raise LinkError("Meta needs a wider permission than reading for the link. Press Reconnect in Settings and allow it.",
                            state="expired")
        if status == 403:
            verdict, words = fallback_reason("mcp", 403, _json(raw))
            raise LinkError(words, state="fallback" if verdict == "fallback" else None)
        if status >= 400:
            verdict, words = fallback_reason("mcp", status, _json(raw))
            raise LinkError(words, retry=verdict == "retry")
        if method == "initialize" and h.get("mcp-session-id"):
            self.sid = h["mcp-session-id"]
        if notify:
            return None
        if (h.get("content-type") or "").startswith("text/event-stream"):
            msgs = [m for m in sse_messages(raw.decode("utf-8", "replace")) if m.get("id") == self.seq]
            body = msgs[-1] if msgs else {}
        else:
            body = _json(raw)
        if body.get("error"):
            raise LinkError(f"Meta's Ads server refused {method}: {cut((body['error'] or {}).get('message'), 160)}")
        return body.get("result") or {}

    def open(self):
        self.rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                "clientInfo": {"name": "edgebourne-ads-link", "version": desk.VERSION}})
        self.rpc("notifications/initialized", notify=True)
        cursor = None
        for _ in range(10):
            res = self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            for t in res.get("tools") or []:
                if isinstance(t, dict) and t.get("name"):
                    self.tools[t["name"]] = t
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return self

    def call_tool(self, name, args):
        """Read-only guard first, before any network: never a tool off LINK_TOOLS, never one Meta marks as a change.
        Whatever `next_actions` the answer suggests is left alone."""
        if name not in ALLOWED:
            raise NotAllowed(f"`{name}` isn't one of the link's read tools.")
        tool = self.tools.get(name)
        if tool is None:
            raise LinkError(f"Meta's Ads server no longer lists `{name}`; update the Mac helper.")
        why = tool_refusal(tool)
        if why:
            raise NotAllowed(why)
        args = with_known(args, tool.get("inputSchema"))
        check_args(name, args, tool.get("inputSchema"))
        result = self.rpc("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            text = " ".join(c.get("text") or "" for c in result.get("content") or [] if isinstance(c, dict))
            raise LinkError(f"Meta didn't answer `{name}`: {cut(text, 160)}")
        return result

    def close(self):
        if not self.sid:
            return
        try:
            self.link.http.request("DELETE", self.link.url, {"Mcp-Session-Id": self.sid, "MCP-Protocol-Version": PROTOCOL,
                                                             "Authorization": f"Bearer {(self.link.tok or {}).get('access_token', '')}"}, timeout=10)
        except (urllib.error.URLError, OSError):
            pass


def read_kind(session, kind, ad_account_id, scope=None):
    """One kind's raw answer. Drafts are paged (at most DRAFT_PAGES pages) and joined into one {"ad_drafts": [...]}."""
    tool = LINK_TOOLS[kind]
    if kind != "drafts":
        return result_payload(session.call_tool(tool, tool_args(kind, ad_account_id, scope)))
    rows, after = [], None
    for _ in range(DRAFT_PAGES):
        payload = result_payload(session.call_tool(tool, tool_args(kind, ad_account_id, after=after)))
        if not isinstance(payload, dict) or not isinstance(payload.get("ad_drafts"), list):
            return payload  # the console refuses a shape it doesn't know
        rows += payload["ad_drafts"]
        paging = payload.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not after or not (paging.get("next") or len(payload["ad_drafts"]) >= DRAFT_PAGE):
            break
    return {"ad_drafts": rows}


# ---------------------------------------------------------------- talking to the console

def console(cfg, key, method, path, body=None, link_pass=None, timeout=40):
    return desk.call(method, path, body, cfg=cfg, token=key, timeout=timeout,
                     extra_headers={"X-Link-Pass": link_pass} if link_pass else None)


def post_status(cfg, key, **body):
    """True when the console took it."""
    try:
        console(cfg, key, "POST", "/api/agent/link/status", body)
        return True
    except (desk.DeskError, urllib.error.URLError, OSError) as exc:
        print(f"link: status not sent ({exc})", file=sys.stderr)
        return False


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_pass(cfg, key, run, link, log=print):
    """One pass for one account: the kinds it asks for, each pushed under the pass. Returns {kind: rows kept}.
    A LinkError with a `state` (login gone, Meta refusing the client) ends the pass and is raised for the caller."""
    def finish(status, error=None):
        console(cfg, key, "POST", "/api/agent/link/finish", {"status": status, "error": error}, link_pass=run["pass"])

    def close_failed(words):
        try:
            finish("failed", words)
        except (desk.DeskError, urllib.error.URLError, OSError):
            pass  # the console is away too: the pass expires there by itself

    session, kept, first = Session(link), {}, None
    try:
        session.open()
        try:
            accounts = result_payload(session.call_tool(LINK_TOOLS["_accounts"], {}))
        except NotAllowed as exc:
            close_failed(f"Checking the ad account: {exc}")
            return kept
        ids = account_ids(accounts)
        if ids is not None and f"act_{run['ad_account_id']}" not in ids:
            finish("no_access", "Your Facebook login on the Mac can't see this ad account.")
            return {"no_access": True}
        for kind in run["kinds"]:
            try:
                result = read_kind(session, kind, run["ad_account_id"], run.get("scope"))
                _, answer = console(cfg, key, "POST", "/api/agent/link/push",
                                    {"kind": kind, "ad_account_id": f"act_{run['ad_account_id']}", "fetched_at": now_iso(), "via": "direct",
                                     "tool": LINK_TOOLS[kind], "result": result}, link_pass=run["pass"])
                kept[kind] = (answer or {}).get("kept", 0)
            except NotAllowed as exc:
                first = first or f"{kind}: {exc}"
            except LinkError as exc:
                if exc.state:
                    raise
                first = first or f"{kind}: {exc}"
            except desk.DeskError as exc:
                first = first or f"{kind}: the console didn't keep it ({exc})"
        finish("failed" if first else "done", first)
        return kept
    except LinkError as exc:
        close_failed(str(exc))
        raise
    except (urllib.error.URLError, OSError) as exc:
        # Meta (or the console) didn't answer: close the pass now so the next plan can read this account again.
        close_failed(f"Couldn't reach Meta's server ({cut(exc, 120)}). Trying again next time.")
        return kept
    finally:
        session.close()


def connect(cfg, key, conn, link, log=print):
    """Connect / Reconnect: the console's Meta app first when the owner ticked it, then dynamic registration; when Meta
    refuses this client, Claude on the Mac reads instead (fallback). Returns the state it ended in."""
    def ended(state, **body):
        return state if post_status(cfg, key, state=state, **body) else "unconfirmed"

    signed_in = False
    try:
        wide = bool((link.store.load() or {}).get("widen"))
        found = link.discover(wide=wide)
        attempts = ([("app", conn["app_id"])] if conn.get("use_app") and conn.get("app_id") else []) + [("dcr", None)]
        refused = None
        for _, app_id in attempts:
            try:
                client = link.register(found, app_id)
                link.login(found, client)
                signed_in = True
                session = Session(link)
                try:
                    name = connected_name(result_payload(session.open().call_tool(LINK_TOOLS["_accounts"], {})))
                finally:
                    session.close()
                log(f"link: connected ({client['kind']}){' as ' + name if name else ''}, allowed: {link.tok.get('scope') or '?'}")
                return ended("connected", client_kind=client["kind"], connected_as=name, scope=link.tok.get("scope") or None)
            except LinkError as exc:
                if exc.state != "fallback":
                    raise
                refused = exc
        log(f"link: Meta refused the Mac's own client ({refused}); Claude on the Mac reads instead")
        return ended("fallback", client_kind="claude", fallback_reason=str(refused))
    except NotAllowed as exc:
        # Meta marks the ad-account list as a tool that changes things: the link won't use this server as it is.
        link.store.delete()
        log(f"link: refused ({exc})")
        return ended("refused", error=f"Checking the login: {exc}")
    except LinkError as exc:
        if exc.retry and not signed_in:
            return ended("connecting", error=str(exc))
        if signed_in and exc.state is None:
            link.store.delete()  # signed in but not checked: Connect starts over, no login left behind
        state = exc.state if exc.state in ("not_connected", "refused", "expired") else "not_connected"
        log(f"link: not connected ({exc})")
        return ended(state, error=str(exc))
    except (urllib.error.URLError, OSError) as exc:
        if signed_in:
            # The Facebook page was done, then Meta stopped answering: don't open it again every minute. The login
            # isn't kept half-checked; Connect starts over.
            link.store.delete()
            return ended("not_connected", error=f"Couldn't reach Meta's server after the sign-in ({cut(exc, 120)}). Press Connect again.")
        return ended("connecting", error=f"Couldn't reach Meta's server ({cut(exc, 120)}). Trying again in a minute.")


def handle_plan(cfg, key, plan, link=None, log=print, fallback=None):
    """Does what one plan from the console asks: disconnect, connect, or the passes (direct, or through Claude)."""
    link = link or Link(cfg)
    if plan.get("disconnect"):
        revoked = link.revoke()
        link.store.delete()
        log(f"link: disconnected; the Facebook login is removed from this Mac{' and cancelled at Meta' if revoked else ''}")
        return "not_connected" if post_status(cfg, key, state="not_connected") else "unconfirmed"
    if plan.get("connect"):
        return connect(cfg, key, plan["connect"], link, log)
    for run in plan.get("runs") or []:
        label = f"link pass {run['run_id']} (account {run['account_id']}, {'+'.join(run['kinds'])}, {plan.get('mode', 'direct')})"
        if plan.get("mode") == "claude":
            if fallback:
                fallback(run)
                log(f"{label}: handed to Claude")
            else:
                console(cfg, key, "POST", "/api/agent/link/finish", {"status": "failed", "error": "No Claude on this Mac to read for the link"},
                        link_pass=run["pass"])
            continue
        try:
            kept = run_pass(cfg, key, run, link, log)
            log(f"{label}: " + ("no access to this ad account" if kept.get("no_access") else
                                ", ".join(f"{v} {k}" for k, v in kept.items()) or "nothing kept"))
        except LinkError as exc:
            log(f"{label}: {exc}")
            if exc.state:
                post_status(cfg, key, state=exc.state, error=str(exc),
                            **({"client_kind": "claude", "fallback_reason": str(exc)} if exc.state == "fallback" else {}))
                break
        except (desk.DeskError, urllib.error.URLError, OSError) as exc:
            log(f"{label}: {exc}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="amlink", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--once", action="store_true", help="ask the console for one plan, do it, exit")
    p.add_argument("--probe", choices=sorted(k for k in LINK_TOOLS if not k.startswith("_")))
    p.add_argument("--ad-account")
    a = p.parse_args(argv)
    cfg = desk.config()
    key = desk.key(cfg)
    if a.probe:
        session = Session(Link(cfg))
        try:
            payload = read_kind(session.open(), a.probe, (a.ad_account or "").replace("act_", ""))
        finally:
            session.close()
        print(json.dumps(payload))
        return
    if a.once:
        _, plan = console(cfg, key, "GET", "/api/agent/link/plan?timeout=0")
        handle_plan(cfg, key, plan or {})
        print(json.dumps({"plan": {k: v for k, v in (plan or {}).items() if k != "runs"},
                          "runs": [{k: v for k, v in r.items() if k != "pass"} for r in (plan or {}).get("runs") or []]}))
        return
    p.print_help()


if __name__ == "__main__":
    try:
        main()
    except LinkError as exc:
        sys.exit(str(exc))
