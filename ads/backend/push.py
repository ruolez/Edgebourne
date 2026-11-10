"""Push notifications to the console's devices (roadmap 6.3). The server only ever posts to the
browsers' own push services, never to an address someone typed."""
import json
import re
from urllib.parse import urlsplit

import config
import db
import settings_store
import webpush

PUSH_HOSTS = re.compile(r"^(fcm\.googleapis\.com|android\.googleapis\.com|updates\.push\.services\.mozilla\.com|"
                        r"web\.push\.apple\.com|[\w.-]+\.notify\.windows\.com)$")


class PushError(Exception):
    permanent = False


def allowed_endpoint(url, test_hosts=frozenset()):
    """A browser push service over https, or a dev stand-in named in PUSH_TEST_HOSTS."""
    try:
        p = urlsplit(str(url or ""))
    except ValueError:
        return False
    if p.scheme == "https" and p.hostname and PUSH_HOSTS.match(p.hostname) and not p.username:
        return True
    return p.scheme in ("http", "https") and p.netloc in test_hosts


def valid_keys(p256dh, auth):
    """A browser's subscription keys: a P-256 point (65 bytes) and a 16-byte auth secret."""
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        point, secret = webpush.unb64u(str(p256dh)), webpush.unb64u(str(auth))
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except (ValueError, TypeError):
        return False
    return len(point) == 65 and len(secret) == 16


def keys():
    """(private, public) VAPID keys, made once and kept (the private one encrypted)."""
    priv, pub = settings_store.get("vapid_private_key"), settings_store.get("vapid_public_key")
    if not priv or not pub:
        priv, pub = webpush.new_vapid_key()
        settings_store.set("vapid_private_key", priv)
        settings_store.set("vapid_public_key", pub)
    return priv, pub


def devices(user_id):
    return db.query("SELECT id, label, created_at, last_ok_at, failures FROM push_subscriptions WHERE user_id = %s ORDER BY id", (user_id,))


def has_devices(user_ids):
    return {r["user_id"] for r in db.query("SELECT DISTINCT user_id FROM push_subscriptions WHERE user_id = ANY(%s) AND failures < 5",
                                           (list(user_ids),))} if user_ids else set()


def send_to_user(user_id, title, lines, url=None, tag=None):
    """Send to every device the person turned on. Gone devices (404/410) are removed.
    Raises PushError when none took it."""
    priv, _ = keys()
    subs = db.query("SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = %s AND failures < 5", (user_id,))
    if not subs:
        err = PushError("No device has notifications turned on")
        err.permanent = True
        raise err
    payload = json.dumps({"title": title, "body": "\n".join(lines or []), "url": url or "/home.html", "tag": tag})
    ok = 0
    for s in subs:
        if not allowed_endpoint(s["endpoint"], config.PUSH_TEST_HOSTS):
            db.execute("DELETE FROM push_subscriptions WHERE id = %s", (s["id"],))
            continue
        try:
            status = webpush.send(s, payload, priv, f"mailto:{config.ADMIN_EMAIL}")
        except Exception:  # network trouble: counts as a failure for this device
            status = 0
        if status in (200, 201, 202):
            ok += 1
            db.execute("UPDATE push_subscriptions SET last_ok_at = now(), failures = 0 WHERE id = %s", (s["id"],))
        elif status in (404, 410):
            db.execute("DELETE FROM push_subscriptions WHERE id = %s", (s["id"],))
        else:
            db.execute("UPDATE push_subscriptions SET failures = failures + 1 WHERE id = %s", (s["id"],))
    if not ok:
        raise PushError("No device took the notification")
    return ok
