"""AM-E routes without a database: who reaches Meta's picture, what a picture push keeps (only an ad of the pass's account,
only a real PNG/JPEG/WebP, always as the default view) and how ?after= is read."""
import base64
import struct
import unittest
import zlib
from datetime import datetime, timezone
from unittest import mock

from flask import Flask

import am_link_api
import auth
import meta_extras_api

ADMIN_WRAPPER = auth.admin_required(lambda: None).__code__
LOGIN_WRAPPER = auth.login_required(lambda: None).__code__
NOW = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)
AD = "120252672227950999"
RUN = {"id": 41, "scope": AD, "created_at": datetime(2026, 11, 14, 17, 59, tzinfo=timezone.utc)}
GIF = bytes.fromhex("474946383961010001008000000000ffffff21f90401000000002c00000000010001000002024401003b")


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def push(result):
    return {"kind": "screenshots", "via": "direct", "fetched_at": NOW.isoformat(), "result": result}


def images(data, **extra):
    return {"images": [{"mime": "image/png", "data_b64": base64.b64encode(data).decode()}], **extra}


def app_with_routes():
    app = Flask("routes")
    app.register_blueprint(meta_extras_api.bp)
    return app


class RouteRoleTests(unittest.TestCase):
    def test_asking_for_a_picture_is_admin_only_and_seeing_one_needs_a_sign_in(self):
        app = app_with_routes()
        found = {(r.rule, m): app.view_functions[r.endpoint].__code__ for r in app.url_map.iter_rules() if r.endpoint != "static"
                 for m in r.methods - {"HEAD", "OPTIONS"}}
        self.assertEqual(found, {("/api/ads/ad/<ad_id>/screenshot", "GET"): LOGIN_WRAPPER,
                                 ("/api/ads/ad/<ad_id>/screenshot/refresh", "POST"): ADMIN_WRAPPER})

    def test_a_teammate_and_a_client_get_403_before_anything_is_asked(self):
        app = app_with_routes()
        got = []
        for role in ("member", "client"):
            user = {"id": 8, "role": role, "account_id": 1}
            with mock.patch.object(auth, "current_user", return_value=user), \
                    mock.patch.object(am_link_api, "ask_screen", side_effect=AssertionError("asked the Mac")):
                got.append(app.test_client().post(f"/api/ads/ad/{AD}/screenshot/refresh").status_code)
        self.assertEqual(got, [403, 403])


class AfterTests(unittest.TestCase):
    def fetch(self, after):
        user = {"id": 1, "role": "admin", "account_id": 1}
        row = {"mime": "image/png", "sha256": "ab" * 32, "body": png(1, 1), "fetched_at": datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)}
        with mock.patch.object(auth, "current_user", return_value=user), \
                mock.patch.object(meta_extras_api, "_visible_ad", return_value={"id": AD, "campaign_id": "C"}), \
                mock.patch.object(meta_extras_api.db, "query", return_value=row):
            return app_with_routes().test_client().get(f"/api/ads/ad/{AD}/screenshot", query_string={"after": after}).status_code

    def test_a_time_without_a_zone_is_read_as_utc(self):
        self.assertEqual([self.fetch("2026-11-14T11:59:00"), self.fetch("2026-11-14T12:00:00"), self.fetch("2026-11-14T07:00:00-05:00")],
                         [200, 204, 204])

    def test_something_that_is_not_a_time_is_refused(self):
        self.assertEqual(self.fetch("yesterday"), 400)


class KeepPictureTests(unittest.TestCase):
    def keep(self, result, ad_known=True):
        writes = []
        app = Flask("keep")
        with app.app_context(), \
                mock.patch.object(am_link_api.db, "query", return_value={"?column?": 1} if ad_known else None), \
                mock.patch.object(am_link_api.db, "execute", side_effect=lambda sql, args=None, **kw: writes.append((" ".join(sql.split()), args))), \
                mock.patch.object(am_link_api, "set_link"):
            resp = am_link_api.keep_picture(RUN, push(result), NOW)
        stored = [args for sql, args in writes if sql.startswith("INSERT INTO am_screens")]
        return resp[1] if isinstance(resp, tuple) else resp.status_code, stored

    def test_a_picture_meta_tags_with_a_placement_is_kept_as_the_ads_picture(self):
        data = png(4, 5)
        status, stored = self.keep(images(data, placement="INSTAGRAM_STORY"))
        self.assertEqual((status, [(a[0], a[1], a[2], a[3], a[4], a[7]) for a in stored]), (200, [(AD, "", "image/png", 4, 5, data)]))

    def test_an_ad_outside_the_pass_account_keeps_nothing(self):
        status, stored = self.keep(images(png(1, 1)), ad_known=False)
        self.assertEqual((status, stored), (409, []))

    def test_a_gif_is_refused_and_nothing_is_kept(self):
        status, stored = self.keep(images(GIF))
        self.assertEqual((status, stored), (422, []))


if __name__ == "__main__":
    unittest.main()
