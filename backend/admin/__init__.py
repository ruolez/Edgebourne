from flask import Blueprint, redirect, request, session, url_for

from auth import check_csrf

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def _guard():
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.path))
    if request.method == "POST":
        check_csrf()


from . import (  # noqa: E402,F401
    blog, dashboard, email_settings, leads, media, pages, services, site, work,
)
