"""Web Push without extra dependencies (roadmap 6.3): message encryption per RFC 8291
(aes128gcm, RFC 8188) and VAPID per RFC 8292, on the `cryptography` package already used.
Push services only see ciphertext; the browser decrypts with keys it never shares."""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RECORD_SIZE = 4096


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hmac(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()


def public_bytes(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def private_from_b64u(text):
    return ec.derive_private_key(int.from_bytes(unb64u(text), "big"), ec.SECP256R1())


def encrypt(payload, ua_public_b64u, auth_b64u, sender_private=None, salt=None):
    """The aes128gcm body for one push message (one record, no padding)."""
    ua_public = unb64u(ua_public_b64u)
    auth = unb64u(auth_b64u)
    sender = sender_private or ec.generate_private_key(ec.SECP256R1())
    as_public = public_bytes(sender)
    salt = salt or os.urandom(16)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh = sender.exchange(ec.ECDH(), ua_key)
    ikm = _hmac(_hmac(auth, ecdh), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    data = payload if isinstance(payload, bytes) else payload.encode()
    cipher = AESGCM(cek).encrypt(nonce, data + b"\x02", None)
    return salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public + cipher


def decrypt(body, ua_private, auth_b64u):
    """The receiving side (tests and the dev fake push service)."""
    salt, idlen = body[:16], body[20]
    as_public, cipher = body[21:21 + idlen], body[21 + idlen:]
    ua_public = public_bytes(ua_private)
    ecdh = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = _hmac(_hmac(unb64u(auth_b64u), ecdh), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    plain = AESGCM(cek).decrypt(nonce, cipher, None)
    return plain.rstrip(b"\x00")[:-1]


def new_vapid_key():
    """(private key as base64url of the 32-byte scalar, public key as base64url of the 65-byte point)."""
    key = ec.generate_private_key(ec.SECP256R1())
    return b64u(key.private_numbers().private_value.to_bytes(32, "big")), b64u(public_bytes(key))


def vapid_header(endpoint, private_b64u, subject, now=None):
    """Authorization header for the push service named in the endpoint (VAPID, ES256 JWT)."""
    key = private_from_b64u(private_b64u)
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": subject}
    signing_input = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()) + "." + \
        b64u(json.dumps(claims, separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    jwt = signing_input + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={jwt}, k={b64u(public_bytes(key))}"


def send(subscription, payload, private_b64u, subject, ttl=86400, post=None):
    """POST one message. Returns the HTTP status (201/200 ok; 404/410 = the subscription is gone)."""
    import requests
    body = encrypt(json.dumps(payload) if not isinstance(payload, (str, bytes)) else payload,
                   subscription["p256dh"], subscription["auth"])
    headers = {"TTL": str(ttl), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "Urgency": "high",
               "Authorization": vapid_header(subscription["endpoint"], private_b64u, subject)}
    resp = (post or requests.post)(subscription["endpoint"], data=body, headers=headers, timeout=15)
    return resp.status_code
