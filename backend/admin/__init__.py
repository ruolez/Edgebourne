from flask import Blueprint, redirect, request, session, url_for

from auth import check_csrf

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def _guard():
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.path))
    if request.method == "POST":
        check_csrf()


# This import block is what registers the routes on the blueprint. A module
# missing from here has no routes at all, with no error anywhere -- just 404s.
from . import (  # noqa: E402,F401
    billing_settings, blog, customers, dashboard, email_settings, estimates,
    invoices, leads, media, pages, payments, projects, recurring, services, site,
    work,
)
