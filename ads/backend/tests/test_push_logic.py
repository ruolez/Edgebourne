import unittest

import push


class EndpointTests(unittest.TestCase):
    def test_only_browser_push_services_over_https(self):
        ok = ["https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/x",
              "https://web.push.apple.com/QGuQ", "https://wns2-par02p.notify.windows.com/w/?token=1"]
        bad = ["http://fcm.googleapis.com/fcm/send/abc", "https://evil.example/fcm.googleapis.com", "https://fcm.googleapis.com.evil.example/x",
               "https://user@fcm.googleapis.com/x", "http://127.0.0.1:5000/api/admin", "http://fake-meta:5001/push/x", "", None]
        self.assertEqual([push.allowed_endpoint(u) for u in ok], [True] * 4)
        self.assertEqual([push.allowed_endpoint(u) for u in bad], [False] * 8)

    def test_a_named_dev_stand_in_is_allowed_only_when_configured(self):
        self.assertEqual((push.allowed_endpoint("http://fake-meta:5001/push/x", {"fake-meta:5001"}),
                          push.allowed_endpoint("http://fake-meta:5002/push/x", {"fake-meta:5001"})), (True, False))


class KeyTests(unittest.TestCase):
    def test_subscription_keys_must_be_a_curve_point_and_a_16_byte_secret(self):
        import webpush
        from cryptography.hazmat.primitives.asymmetric import ec
        good = webpush.b64u(webpush.public_bytes(ec.generate_private_key(ec.SECP256R1())))
        auth = webpush.b64u(b"0123456789abcdef")
        self.assertEqual([push.valid_keys(good, auth), push.valid_keys("BFAKE", auth), push.valid_keys(good, "short"),
                          push.valid_keys("B" + "A" * 86, auth)], [True, False, False, False])


if __name__ == "__main__":
    unittest.main()
