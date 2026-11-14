"""AM-D: who reaches the audiences routes (a ratchet: making or reading Meta's sources is for the owner and account admins only,
the list never answers a client), without a database."""
import unittest
from unittest import mock

from flask import Flask

import audiences_api
import auth

ADMIN_WRAPPER = auth.admin_required(lambda: None).__code__
LOGIN_WRAPPER = auth.login_required(lambda: None).__code__


def app_with_routes():
    app = Flask("routes")
    app.register_blueprint(audiences_api.bp)
    return app


def routes():
    app = app_with_routes()
    return {(rule.rule, m): app.view_functions[rule.endpoint] for rule in app.url_map.iter_rules() if rule.endpoint != "static"
            for m in rule.methods - {"HEAD", "OPTIONS"}}


class RouteRoleTests(unittest.TestCase):
    def test_every_write_and_the_sources_are_admin_only(self):
        found = routes()
        admin = {k for k, v in found.items() if v.__code__ is ADMIN_WRAPPER}
        self.assertEqual(admin, {("/api/audiences/sources", "GET"), ("/api/audiences/check", "POST"), ("/api/audiences", "POST"),
                                 ("/api/audiences/refresh", "POST")})

    def test_the_rest_needs_a_sign_in(self):
        rest = {k for k, v in routes().items() if v.__code__ is not ADMIN_WRAPPER}
        self.assertEqual((rest, {routes()[k].__code__ is LOGIN_WRAPPER for k in rest}),
                         ({("/api/audiences", "GET"), ("/api/audiences/<audience_id>", "GET")}, {True}))

    def test_a_client_gets_403_on_the_list_and_one_audience_before_any_read(self):
        client = {"id": 9, "role": "client", "account_id": 1}
        app = app_with_routes()
        with mock.patch.object(auth, "current_user", return_value=client), mock.patch.object(audiences_api, "current_user", return_value=client), \
                mock.patch.object(audiences_api, "ensure_fresh", side_effect=AssertionError("read Meta")), \
                mock.patch.object(audiences_api.db, "query", side_effect=AssertionError("read the database")):
            c = app.test_client()
            self.assertEqual([c.get("/api/audiences").status_code, c.get("/api/audiences/238501").status_code], [403, 403])

    def test_a_teammate_gets_403_on_every_admin_route(self):
        mate = {"id": 8, "role": "member", "account_id": 1}
        app = app_with_routes()
        with mock.patch.object(auth, "current_user", return_value=mate), \
                mock.patch.object(audiences_api.meta_client, "post", side_effect=AssertionError("wrote to Meta")):
            c = app.test_client()
            got = [c.get("/api/audiences/sources").status_code, c.post("/api/audiences/check", json={}).status_code,
                   c.post("/api/audiences", json={"kind": "website"}).status_code, c.post("/api/audiences/refresh", json={}).status_code]
        self.assertEqual(got, [403, 403, 403, 403])


class PickCheckTests(unittest.TestCase):
    def test_an_audience_not_in_this_account_is_refused_before_meta(self):
        with mock.patch.object(audiences_api, "known", return_value={"238501": {"id": "238501", "name": "Web", "kind": "custom", "ready": "ready"}}):
            self.assertEqual((audiences_api.pick_check({"include_audiences": ["238501"]}),
                              audiences_api.pick_check({"include_audiences": ["999001"], "exclude_audiences": []})),
                             ([], [("audiences", "That audience isn't in this account")]))

    def test_a_browser_name_for_a_picked_audience_is_never_kept(self):
        form = {"custom_audiences": [{"id": "238501", "name": "<b>mine</b>"}], "excluded_custom_audiences": [{"id": "777", "name": "Fake name"}]}
        out = audiences_api.name_picked(form, {"238501": {"name": "Web visitors", "kind": "custom"}}, {"custom_audiences": [], "excluded_custom_audiences": []})
        self.assertEqual(out, {"custom_audiences": [{"id": "238501", "name": "Web visitors"}], "excluded_custom_audiences": [{"id": "777", "name": "777"}]})


class PerAccountTests(unittest.TestCase):
    def test_the_freshness_and_refresh_stamps_belong_to_one_account(self):
        import settings_store
        self.assertEqual([settings_store.stored_key(k, account_id=2) for k in ("audiences_read_at", "audiences_refresh_at")],
                         ["audiences_read_at@2", "audiences_refresh_at@2"])

    def test_a_teammate_sees_where_used_only_for_their_campaigns(self):
        sets = [{"id": "S1", "campaign_id": "C1", "audience_ids": ["7"], "excluded_audience_ids": []},
                {"id": "S2", "campaign_id": "C2", "audience_ids": ["7"], "excluded_audience_ids": []}]
        with mock.patch.object(audiences_api.db, "query", return_value=sets), \
                mock.patch.object(audiences_api, "visible_campaign_ids", return_value={"C1"}):
            self.assertEqual([s["id"] for s in audiences_api._adsets({"id": 8, "role": "member"})], ["S1"])


class RefusalTests(unittest.TestCase):
    def test_only_the_custom_audience_terms_refusal_asks_to_accept_terms(self):
        from meta_client import MetaError
        self.assertEqual([audiences_api._refusal(MetaError("Invalid parameter: search terms too long", code=100)),
                          audiences_api._refusal(MetaError("You must accept the Custom Audience Terms", code=200)),
                          audiences_api._refusal(MetaError("Not allowed", code=2654))],
                         ["Meta refused: Invalid parameter: search terms too long", audiences_api.TERMS_WORDS, audiences_api.TERMS_WORDS])


class EstimateTests(unittest.TestCase):
    def test_an_audience_not_in_this_account_never_reaches_metas_estimate(self):
        import adsets_api
        app = Flask("est")
        app.register_blueprint(adsets_api.bp)
        admin = {"id": 1, "role": "admin", "account_id": 1}
        spec = {"locations": [{"kind": "city", "key": "1", "name": "Riverside", "radius": 25}], "include_audiences": ["999001"]}
        with mock.patch.object(auth, "current_user", return_value=admin), \
                mock.patch.object(audiences_api, "known", return_value={}), \
                mock.patch.object(audiences_api.db, "query", return_value=None), \
                mock.patch.object(adsets_api, "template", return_value={}), \
                mock.patch.object(adsets_api.meta_client, "get", side_effect=AssertionError("asked Meta")), \
                mock.patch.object(adsets_api, "cached", side_effect=AssertionError("asked Meta")):
            r = app.test_client().post("/api/adsets/estimate", json={"spec": spec})
        self.assertEqual((r.status_code, r.get_json()), (200, {"lower": None, "upper": None, "problem": "That audience isn't in this account"}))


class LiveReadTests(unittest.TestCase):
    def test_metas_own_list_on_the_ad_set_is_never_cut(self):
        many = [{"id": str(9000 + i), "name": f"List {i}"} for i in range(30)]
        out = audiences_api.name_picked({"custom_audiences": [], "excluded_custom_audiences": list(many)}, {})
        self.assertEqual([a["id"] for a in out["excluded_custom_audiences"]], [a["id"] for a in many])


if __name__ == "__main__":
    unittest.main()
