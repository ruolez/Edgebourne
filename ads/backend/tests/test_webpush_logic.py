import base64
import json
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

import webpush as wp

# RFC 8291 Appendix A (the worked example).
PLAIN = b"When I grow up, I want to be a watermelon"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
UA_PRIV = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUB = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AS_PRIV = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
EXPECTED = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_y"
            "l95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


class EncryptTests(unittest.TestCase):
    def test_rfc_8291_worked_example(self):
        body = wp.encrypt(PLAIN, UA_PUB, AUTH, sender_private=wp.private_from_b64u(AS_PRIV), salt=wp.unb64u(SALT))
        self.assertEqual(wp.b64u(body), EXPECTED)

    def test_round_trip_with_fresh_keys(self):
        ua = ec.generate_private_key(ec.SECP256R1())
        auth = wp.b64u(b"0123456789abcdef")
        body = wp.encrypt(json.dumps({"title": "New lead"}), wp.b64u(wp.public_bytes(ua)), auth)
        self.assertEqual(json.loads(wp.decrypt(body, ua, auth)), {"title": "New lead"})


class VapidTests(unittest.TestCase):
    def test_the_jwt_names_the_push_service_and_verifies_with_the_public_key(self):
        priv, pub = wp.new_vapid_key()
        h = wp.vapid_header("https://fcm.googleapis.com/fcm/send/abc", priv, "mailto:eugene@edgebourne.com", now=1_800_000_000)
        token = h.split("t=")[1].split(",")[0]
        head, claims, sig = token.split(".")
        self.assertEqual(json.loads(wp.unb64u(claims)), {"aud": "https://fcm.googleapis.com", "exp": 1_800_043_200, "sub": "mailto:eugene@edgebourne.com"})
        raw = wp.unb64u(sig)
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), wp.unb64u(pub))
        key.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                   f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if wrong
        self.assertEqual(h.split("k=")[1], pub)


if __name__ == "__main__":
    unittest.main()
