"""AM-C: every Edit, copy, archive and delete route is for the owner and this account's admins only (a ratchet: a new route
without admin_required fails here, before any end-to-end run)."""
import unittest

from flask import Flask

import auth
import copy_api
import edit_api

ADMIN_WRAPPER = auth.admin_required(lambda: None).__code__


def routes(*blueprints):
    app = Flask("routes")
    for bp in blueprints:
        app.register_blueprint(bp)
    return [(rule.rule, app.view_functions[rule.endpoint]) for rule in app.url_map.iter_rules() if rule.endpoint != "static"]


class AdminOnlyTests(unittest.TestCase):
    def test_every_edit_and_copy_route_is_admin_only(self):
        found = routes(edit_api.bp, copy_api.bp)
        self.assertEqual([rule for rule, view in found if view.__code__ is not ADMIN_WRAPPER], [])

    def test_the_routes_checked_include_archive_delete_copy_and_save(self):
        rules = {rule for rule, _ in routes(edit_api.bp, copy_api.bp)}
        self.assertEqual({"/api/ads/<level>/<entity_id>/archive", "/api/ads/<level>/<entity_id>/delete", "/api/edit/<level>/<entity_id>",
                          "/api/edit/<level>/<entity_id>/check", "/api/copy/<level>/<source_id>", "/api/copy/<int:job_id>/resume"} - rules, set())


if __name__ == "__main__":
    unittest.main()
