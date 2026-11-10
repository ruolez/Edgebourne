"""Lead forms (admins): the Page's Instant Forms, a check before creating, copy, create."""
import json

from flask import Blueprint, jsonify, request

import forms
import meta_client
import settings_store
from auth import admin_required, current_user
from util import api_error

bp = Blueprint("forms", __name__, url_prefix="/api/forms")

READ_FIELDS = "name,questions,privacy_policy_url,thank_you_page,context_card,follow_up_action_url,is_optimized_for_quality,locale,status"


def _page():
    page = settings_store.get("meta_page_id")
    if not page:
        raise meta_client.MetaError("Pick the Facebook Page in Settings → Meta first")
    return page, meta_client.page_token(page)


def page_forms():
    page, token = _page()
    return list(meta_client.paged(f"{page}/leadgen_forms", token=token,
                                  fields="id,name,status,leads_count,created_time", limit=100))


def clean_spec(raw):
    def text(k, n=400):
        return str(raw.get(k) or "")[:n]
    custom = [{"label": str(q.get("label") or "")[:200], "options": [str(o)[:120] for o in (q.get("options") or [])][:10]}
              for q in (raw.get("custom") or [])[:6] if isinstance(q, dict)]
    return {"name": text("name"), "intro_title": text("intro_title"),
            "intro_bullets": [str(b)[:200] for b in (raw.get("intro_bullets") or []) if str(b).strip()][:5],
            "standard": [s for s in (raw.get("standard") or []) if s in forms.STANDARD], "custom": custom,
            "higher_intent": bool(raw.get("higher_intent")), "privacy_url": text("privacy_url").strip() or forms.DEFAULT_PRIVACY,
            "thanks_title": text("thanks_title"), "thanks_body": text("thanks_body", 600),
            "thanks_button": "website" if raw.get("thanks_button") == "website" else "none",
            "thanks_button_text": text("thanks_button_text", 60), "thanks_url": text("thanks_url").strip()}


def check(spec):
    return {"problems": [{"field": f, "message": m} for f, m in forms.problems(spec)],
            "policy": [{"where": w, "why": m} for w, m in forms.policy_problems(spec)]}


@bp.get("")
@admin_required
def listing():
    try:
        items = page_forms()
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    return jsonify({"items": items, "privacy_default": forms.DEFAULT_PRIVACY, "standard": forms.STANDARD,
                    "limits": forms.LIMITS, "max_custom": forms.MAX_CUSTOM, "max_options": forms.MAX_OPTIONS})


@bp.get("/<form_id>/copy")
@admin_required
def copy(form_id):
    try:
        _, token = _page()
        form = meta_client.get(form_id, token=token, fields=READ_FIELDS)
    except meta_client.MetaError as exc:
        return api_error(str(exc), 400)
    return jsonify(forms.spec_from_meta(form))


@bp.post("/check")
@admin_required
def check_only():
    return jsonify(check(clean_spec(request.get_json(silent=True) or {})))


@bp.post("")
@admin_required
def create():
    spec = clean_spec(request.get_json(silent=True) or {})
    result = check(spec)
    if result["problems"] or result["policy"]:
        first = (result["problems"] or [{"field": None, "message": f"{result['policy'][0]['where']}: {result['policy'][0]['why']}"}])[0]
        body = {"error": first["message"], "field": first["field"], **result}
        return jsonify(body), 400
    import ads_api
    user = current_user()
    payload = forms.payload(spec)
    row = {"id": settings_store.get("meta_page_id") or "page", "name": spec["name"], "campaign_id": None}
    try:
        page, token = _page()
        made = meta_client.post(f"{page}/leadgen_forms", token=token,
                                data={k: json.dumps(v) if isinstance(v, (list, dict, bool)) else v for k, v in payload.items()})
    except meta_client.MetaError as exc:
        ads_api.record(user, "form", row, "create", None, spec["name"], False, str(exc))
        return api_error(f"Meta refused: {exc}", 400)
    ads_api.record(user, "form", {**row, "id": made["id"]}, "create", None, spec["name"], True)
    return jsonify({"id": made["id"], "name": spec["name"]}), 201
