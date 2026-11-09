"""Polish passes: the checks used to bring the Edge Bourne ads from first draft to
approved (Nov 2026), packaged so any ad can get the same treatment from the
dashboard. A polish run is a Desk task (kind 'polish') that carries the pass
definitions, so Claude on the Mac checks exactly what the dashboard promised.
A render run (kind 'render') has Claude rebuild the creative on the Mac from the
fixes and send the new version back as a proposal."""
from flask import Blueprint, jsonify, request

import db
from ads_api import can_touch, entity
from auth import current_user, login_required
from util import api_error, log_activity

bp = Blueprint("polish", __name__, url_prefix="/api")

PASSES = [
    {"id": "hook", "label": "Hook", "icon": "spark",
     "summary": "Does the first second stop the scroll?",
     "checks": ["Problem first, in the reader's words; no question hooks",
                "Something moves or reads within the first second",
                "Works muted: the key words are on screen",
                "The hook is about the reader's business, not about us"]},
    {"id": "headline", "label": "Headline", "icon": "type",
     "summary": "Short, specific, readable at feed size",
     "checks": ["26–47 characters, two lines at most", "A concrete outcome, not a category name",
                "Highlight words on the image match the headline field", "No clickbait, no ALL CAPS shouting"]},
    {"id": "primary_text", "label": "Primary text", "icon": "text",
     "summary": "The first 125 characters carry it",
     "checks": ["Problem and promise land before \"See more\"", "Plain words a busy owner reads in five seconds",
                "Offer stated exactly: free intro call (never \"free workflow review\")",
                "No website copy, no process detail or timelines", "AI framed as optional (\"if you want it\")"]},
    {"id": "cta", "label": "Call to action", "icon": "cursor",
     "summary": "One obvious next step",
     "checks": ["Button fits an Instant Form (Book now / Sign up / Get quote)",
                "\"Tap below\" note big and bold on the creative", "CTA sits at the bottom-right exit of the eye path",
                "What happens after the tap is clear and honest"]},
    {"id": "message", "label": "Message & intent", "icon": "target",
     "summary": "One idea, for the right person, different from the others",
     "checks": ["One idea per ad; problem → solution → CTA", "About the reader's own business, not selling software",
                "Fits Southern California small-business owners", "Different enough from the other running ads to be shown separately"]},
    {"id": "visual", "label": "Visual design", "icon": "image",
     "summary": "Hierarchy, readability, harmony",
     "checks": ["Three text levels only: headline, lead, small text", "Small text ≥ 28 px on a 1080 canvas; contrast ≥ 4.5:1",
                "One accent colour plus ink; no gradients, glass or stray colours", "No clutter: no labels that repeat a word already there",
                "Harmony and flow: one shape or line carries the eye", "Nothing important sits under a plate or chip"]},
    {"id": "ai_signal", "label": "AI signal", "icon": "toggle",
     "summary": "AI present, optional, never too small",
     "checks": ["The AI chip sits inside the solution object, in a row with the job it does",
                "One chip size across the set, OPTIONAL text ≥ 32 px", "OPTIONAL plus a switch that visibly flicks",
                "The entrance pop stays ≤ 1.12× and doesn't spill over neighbours"]},
    {"id": "placements", "label": "Placements", "icon": "phone",
     "summary": "Feed, Stories and Reels all read",
     "checks": ["4:5 for feeds, 9:16 for Stories and Reels", "Reels safe zone: 14% top, 35% bottom, clear of the right action strip",
                "Check Meta's previews per placement for cut or covered text", "Text the same size in 9:16 as in 4:5"]},
    {"id": "motion", "label": "Motion & sound", "icon": "play",
     "summary": "Movement that belongs, sound that lifts",
     "checks": ["Motion belongs to structural elements; no lone moving dots",
                "Mid-video text pops (highlighter band, words one by one)", "Nothing comes to rest before the end; no frozen hold",
                "Elements never fly across other content", "Energetic licensed music, levels even"]},
    {"id": "policy", "label": "Policy & claims", "icon": "shield",
     "summary": "Nothing Meta or a customer could object to",
     "checks": ["No invented facts (prices, reviews, years, guarantees)", "No personal-attribute wording (\"Are you struggling…\")",
                "Claims are true and specific to Edge Bourne", "Landing / form matches what the ad promises"]},
    {"id": "performance", "label": "Performance read", "icon": "chart",
     "summary": "What the numbers say about this ad",
     "checks": ["Hook rate (3-second views ÷ impressions) and hold rate (ThruPlays ÷ 3-second views)",
                "Click rate and cost per lead against the other ads", "Frequency and signs of fatigue",
                "Meta's quality, engagement and conversion rankings", "Enough data yet? (2× target spend and 3 results)"]},
]
PASS_IDS = [p["id"] for p in PASSES]
PRESETS = {
    "full": PASS_IDS,
    "copy": ["hook", "headline", "primary_text", "cta", "message", "policy"],
    "design": ["visual", "ai_signal", "placements", "motion"],
    "quick": ["hook", "headline", "cta", "message"],
}


def _ad_for(user, ad_id):
    row = entity("ad", ad_id)
    if not row or not can_touch(user, row["campaign_id"]):
        return None
    return db.query("SELECT id, name, campaign_id, adset_id, title, body, cta_type, object_type, video_id, image_url, "
                    "creative_id FROM ads WHERE id = %s", (ad_id,), one=True)


@bp.get("/polish/passes")
@login_required
def passes():
    return jsonify({"passes": PASSES, "presets": PRESETS})


def _task(user, kind, prompt, ad, options):
    t = db.execute(
        "INSERT INTO desk_tasks (kind, prompt, campaign_id, created_by, options) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (kind, prompt, ad["campaign_id"], user["id"], __import__("json").dumps(options)), returning=True)
    log_activity(f"desk.{kind}_requested", subject=str(t["id"]), details={"ad": ad["name"]})
    return t["id"]


@bp.post("/ads/ad/<ad_id>/polish")
@login_required
def polish(ad_id):
    user = current_user()
    ad = _ad_for(user, ad_id)
    if not ad:
        return api_error("Ad not found", 404)
    data = request.get_json(silent=True) or {}
    chosen = [p for p in PASSES if p["id"] in (data.get("passes") or [])]
    if not chosen:
        return api_error("Pick at least one pass", 400, field="passes")
    direction = (data.get("direction") or "").strip()[:2000]
    labels = ", ".join(p["label"] for p in chosen)
    prompt = f"Polish “{ad['name']}”: {labels}." + (f"\nDirection: {direction}" if direction else "")
    options = {"ad_id": ad["id"], "ad_name": ad["name"], "passes": chosen, "direction": direction,
               "variants": bool(data.get("variants", True))}
    return jsonify({"task_id": _task(user, "polish", prompt, ad, options)}), 201


@bp.post("/ads/ad/<ad_id>/render")
@login_required
def render(ad_id):
    user = current_user()
    ad = _ad_for(user, ad_id)
    if not ad:
        return api_error("Ad not found", 404)
    data = request.get_json(silent=True) or {}
    direction = (data.get("direction") or "").strip()[:2000]
    from_task = data.get("from_task")
    fixes = None
    if from_task:
        t = db.query("SELECT scorecard FROM desk_tasks WHERE id = %s AND kind = 'polish'", (from_task,), one=True)
        fixes = t and t["scorecard"]
    if not direction and not fixes:
        return api_error("Say what the new version should change, or start from a polish run", 400, field="direction")
    prompt = f"Make a new version of “{ad['name']}”." + (f"\nDirection: {direction}" if direction else "") + \
             (f"\nApply the fixes from polish run #{from_task}." if fixes else "")
    options = {"ad_id": ad["id"], "ad_name": ad["name"], "direction": direction, "from_task": from_task,
               "scorecard": fixes}
    return jsonify({"task_id": _task(user, "render", prompt, ad, options)}), 201


@bp.get("/ads/ad/<ad_id>/polish-runs")
@login_required
def runs(ad_id):
    user = current_user()
    if not _ad_for(user, ad_id):
        return api_error("Ad not found", 404)
    from desk_api import tasks_with_results
    tasks = tasks_with_results("t.kind IN ('polish','render') AND t.options->>'ad_id' = %s", [ad_id], 20)
    return jsonify({"tasks": tasks})
