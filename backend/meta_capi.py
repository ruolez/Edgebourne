"""Meta Conversions API: server-side copy of the browser Lead event, deduplicated by event_id.

Best effort only. A failure here must never break the contact form, so every error is logged and swallowed.
"""
import hashlib
import logging
import threading
import time

import json
import urllib.parse
import urllib.error
import urllib.request

import config

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v22.0"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def send_lead(event_id: str, email: str, request) -> None:
    if not (config.META_PIXEL_ID and config.META_CAPI_TOKEN):
        return
    payload = {
        "data": [
            {
                "event_name": "Lead",
                "event_time": int(time.time()),
                "event_id": event_id,
                "event_source_url": request.url,
                "action_source": "website",
                "user_data": {
                    "em": [_sha256(email)] if email else [],
                    "client_ip_address": request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
                    "client_user_agent": request.headers.get("User-Agent", ""),
                    "fbp": request.cookies.get("_fbp"),
                    "fbc": request.cookies.get("_fbc"),
                },
                "custom_data": {"content_name": "contact_form"},
            }
        ],
    }
    url = f"{GRAPH}/{config.META_PIXEL_ID}/events"

    def _post():
        try:
            req = urllib.request.Request(
                url + "?" + urllib.parse.urlencode({"access_token": config.META_CAPI_TOKEN}),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            log.warning("meta capi %s: %s", exc.code, exc.read()[:300])
        except Exception as exc:  # noqa: BLE001
            log.warning("meta capi failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()
