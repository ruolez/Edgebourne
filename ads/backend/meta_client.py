"""Thin Graph API client. Tokens come from settings (encrypted) and never leave
the server."""
import hashlib
import hmac
import logging
import time

import requests

import account_ctx
import config
import settings_store

log = logging.getLogger(__name__)
TIMEOUT = 20
RATE_CODES = {4, 17, 32, 613} | set(range(80000, 80015))  # Meta's "slow down" family
TOKEN_CODES = {190, 102}  # token revoked, expired or changed
COOLDOWN_SECONDS = 300
_cooldown = {}  # account id -> unix time before which we don't ask Meta again
_token_bad = {}  # account id -> True once Meta refused the token (cleared by the next success)


class MetaError(Exception):
    """`unknown` is True when a write may or may not have happened (Meta didn't answer)."""

    def __init__(self, message, code=None, status=None, unknown=False, raw=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.unknown = unknown
        self.raw = raw or message


def plain(code, message):
    """Meta's error in words Eugene can act on; the original text stays on `raw`."""
    if code in TOKEN_CODES:
        return ("Meta no longer accepts the access token (it was revoked, expired or changed). "
                "Paste a new System User token in Settings → Meta.")
    if code in RATE_CODES:
        return "Meta asked us to slow down (too many requests). The console waits a few minutes, then tries again."
    if code == 10 or (isinstance(code, int) and 200 <= code < 300):
        return f"The System User doesn't have permission for this: {message}"
    return message


def network_error(method, timed_out):
    """A request that never got an answer. For a write, Meta may have applied it anyway."""
    what = "Meta didn't answer in time" if timed_out else "Couldn't reach Meta (network problem)"
    if method == "GET":
        return MetaError(f"{what}. Try again in a minute.", code="network")
    return MetaError(f"{what}. The change may have gone through: check Ads Manager (or press Refresh) "
                     "before trying again.", code="network", unknown=True)


def cooling_until(account_id=None, now=None):
    until = _cooldown.get(account_ctx.current() if account_id is None else account_id, 0)
    return until if until > (now or time.time()) else None


def _note_error(code):
    acct = account_ctx.current()
    if code in RATE_CODES:
        _cooldown[acct] = time.time() + COOLDOWN_SECONDS
        log.warning("Meta rate limit (code %s) on account %s: waiting %ss", code, acct, COOLDOWN_SECONDS)
    elif code in TOKEN_CODES and not _token_bad.get(acct):
        _token_bad[acct] = True
        log.warning("Meta refused the token (code %s) on account %s", code, acct)
        try:
            settings_store.set("meta_token_error", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        except Exception:  # noqa: BLE001 - never hide Meta's error behind a settings problem
            pass


def _note_success():
    acct = account_ctx.current()
    if _token_bad.get(acct, True):
        _token_bad[acct] = False
        try:
            if settings_store.own("meta_token_error"):
                settings_store.set("meta_token_error", None)
        except Exception:  # noqa: BLE001
            pass


def _raise_for(resp):
    try:
        body = resp.json()
    except ValueError:
        raise MetaError(f"Meta returned HTTP {resp.status_code}", status=resp.status_code) from None
    if resp.status_code >= 400 or "error" in body:
        err = body.get("error", {}) if isinstance(body.get("error"), dict) else {}
        code = err.get("code")
        _note_error(code)
        message = err.get("message") or f"Meta returned HTTP {resp.status_code}"
        raise MetaError(plain(code, message), code=code, status=resp.status_code, raw=message)
    return body


def _send(method, url, **kw):
    """requests without the token ever reaching an error message or a traceback."""
    until = cooling_until()
    if until:
        raise MetaError(f"Meta asked us to slow down. The console asks again after "
                        f"{time.strftime('%H:%M UTC', time.gmtime(until))}.", code="cooldown")
    try:
        return requests.request(method, url, **kw)
    except requests.Timeout:
        err = network_error(method, True)
    except requests.RequestException:
        err = network_error(method, False)
    raise err


def _base(video=False):
    if config.META_GRAPH_BASE:
        return config.META_GRAPH_BASE
    version = settings_store.get("meta_graph_version") or config.GRAPH_VERSION_DEFAULT
    # Meta documents chunked video uploads on its own host.
    return f"https://graph{'-video' if video else ''}.facebook.com/{version}"


def system_token():
    token = settings_store.get("meta_system_token")
    if not token:
        raise MetaError("Add the System User token in Settings → Meta first")
    return token


def _call(method, path, token, params=None, data=None, files=None, timeout=TIMEOUT, video=False):
    if path.startswith(("act_None", "None", "/act_None")) or "/None/" in path:
        # Agency mode: an account added but not connected yet has no ad account or Page id.
        raise MetaError("This account isn't connected to Meta yet: add its ad account in Settings → Meta")
    params = dict(params or {})
    params["access_token"] = token
    resp = _send(method, f"{_base(video)}/{path.lstrip('/')}", params=params, data=data, files=files,
                 timeout=timeout)
    body = _raise_for(resp)
    _note_success()
    return body


def get(path, token=None, **params):
    return _call("GET", path, token or system_token(), params=params)


def post(path, token=None, data=None, files=None, timeout=TIMEOUT, video=False, **params):
    return _call("POST", path, token or system_token(), params=params, data=data, files=files,
                 timeout=timeout, video=video)


def page_token(page_id=None):
    page_id = page_id or settings_store.get("meta_page_id")
    body = get(page_id, fields="access_token,name")
    token = body.get("access_token")
    if not token:
        raise MetaError("The System User can't act for the Page. Assign the Page to it with "
                        "full control in Business settings.")
    return token


def paged(path, token=None, **params):
    """Yield every item across Graph API pages."""
    body = get(path, token=token, **params)
    while True:
        yield from body.get("data", [])
        nxt = body.get("paging", {}).get("next")
        if not nxt:
            return
        body = _raise_for(_send("GET", nxt, timeout=TIMEOUT))


def signature_valid(raw_body, header, app_secret):
    """Meta signs webhook bodies: X-Hub-Signature-256: sha256=<hex hmac>."""
    if not header or not app_secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])
