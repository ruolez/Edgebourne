"""What an ad is doing right now, in plain words, and the one next step that helps. Pure: the ad page's
status card reads it (UX-AUDIT 9.4, Ad Overview leads with status)."""
import json

# Meta's effective_status → (tone, headline, sentence). Headlines match format.js STATUS.
HEADLINES = {
    "ACTIVE": ("ok", "Delivering", None),
    "PAUSED": ("", "Off", "Switched off, so it spends nothing."),
    "CAMPAIGN_PAUSED": ("", "Off (campaign is off)", "The ad itself is on, but its campaign is off, so it spends nothing."),
    "ADSET_PAUSED": ("", "Off (ad set is off)", "The ad itself is on, but its ad set is off, so it spends nothing."),
    "IN_PROCESS": ("warn", "In review", "Meta is checking it, usually within a day. It starts delivering once approved."),
    "PENDING_REVIEW": ("warn", "In review", "Meta is checking it, usually within a day. It starts delivering once approved."),
    "PREAPPROVED": ("ok", "Approved, starts on schedule", "Meta approved it. It starts when its schedule begins."),
    "DISAPPROVED": ("bad", "Rejected", "Meta rejected it, so it spends nothing. Change the words or picture and Meta reviews it again."),
    "WITH_ISSUES": ("bad", "Has issues", "Meta reports a problem with it, so it may not deliver."),
    "PENDING_BILLING_INFO": ("bad", "Needs billing", "Meta needs payment details for the ad account before anything delivers."),
    "ARCHIVED": ("", "Archived", "Archived: Meta can't run it again. Duplicate it to run the same ad."),
    "DELETED": ("", "Deleted", "Deleted in Meta. Its past results stay here."),
}
FIX = {"PAUSED": "switch", "CAMPAIGN_PAUSED": "campaign", "ADSET_PAUSED": "adset", "DISAPPROVED": "polish",
       "WITH_ISSUES": "polish", "PENDING_BILLING_INFO": "billing"}
LEARNING = {"LEARNING": "learning", "FAIL": "learning_limited"}


def _read(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def reasons(ad):
    """Meta's review reasons (everywhere, then per placement) and reported issues, each once."""
    out = []
    feedback = _read(ad.get("review_feedback"))
    if isinstance(feedback, dict):
        out += [v for v in (feedback.get("global") or {}).values() if isinstance(v, str)]
        for place, texts in (feedback.get("placement_specific") or {}).items():
            out += [f"{place.replace('_', ' ').title()}: {v}" for v in (texts or {}).values() if isinstance(v, str)]
    issues = _read(ad.get("issues"))
    if isinstance(issues, dict):
        issues = [issues]
    for i in issues if isinstance(issues, list) else []:
        if isinstance(i, dict):
            out.append(i.get("error_message") or i.get("error_summary") or "")
    seen, uniq = set(), []
    for line in (o.strip() for o in out):
        if line and line not in seen:
            seen.add(line)
            uniq.append(line)
    return uniq


def explain(ad, learning_stage=None, track=None):
    """{tone, headline, line, reasons, fix, learning, days_on} for the ad's current status."""
    status = ad.get("effective_status") or ad.get("status") or ""
    tone, headline, line = HEADLINES.get(status, ("", status.replace("_", " ").capitalize() or "Unknown", "Meta reports this status."))
    days = track or []
    on = sum(1 for d in days if d.get("on"))
    if status == "ACTIVE":
        line = (f"Spent on {on} of the last {len(days)} days." if on
                else "On and approved, but it hasn't spent in the last two weeks. New ads can take a day to start.")
    return {"tone": tone, "headline": headline, "line": line, "reasons": reasons(ad), "fix": FIX.get(status),
            "learning": LEARNING.get(learning_stage) if status == "ACTIVE" else None, "days_on": on}
