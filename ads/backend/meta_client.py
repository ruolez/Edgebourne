"""Thin Graph API client. Tokens come from settings (encrypted) and never leave
the server."""
import hashlib
import hmac

import requests

import config
import settings_store

TIMEOUT = 20


class MetaError(Exception):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


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
    params = dict(params or {})
    params["access_token"] = token
    resp = requests.request(method, f"{_base(video)}/{path.lstrip('/')}", params=params, data=data,
                            files=files, timeout=timeout)
    try:
        body = resp.json()
    except ValueError:
        raise MetaError(f"Meta returned HTTP {resp.status_code}", status=resp.status_code)
    if resp.status_code >= 400 or "error" in body:
        err = body.get("error", {})
        raise MetaError(err.get("message") or f"Meta returned HTTP {resp.status_code}",
                        code=err.get("code"), status=resp.status_code)
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
        resp = requests.get(nxt, timeout=TIMEOUT)
        body = resp.json()
        if "error" in body:
            raise MetaError(body["error"].get("message", "Paging failed"))


def signature_valid(raw_body, header, app_secret):
    """Meta signs webhook bodies: X-Hub-Signature-256: sha256=<hex hmac>."""
    if not header or not app_secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])
