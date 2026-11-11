"""One ad in two shapes: its 4:5 video in feeds and a 9:16 video in Reels and Stories (Meta's
placement asset customization), for Meta's "add a vertical 9:16 video for Reels" advice.
Pure: builds the creative from the ad's current single-video story spec with the same words,
button and lead form, and checks Meta's stored copy before it goes on a running ad.

The raw shape (asset_feed_spec + asset_customization_rules, the form in call_to_actions) is
Meta's documented one, unverified against this account until the first live approval; the
read-back check is what keeps a wrong guess off the running ad."""

import json

FEED, VERTICAL = "eb_feed", "eb_vertical"
VERTICAL_SPEC = {"publisher_platforms": ["facebook", "instagram"],
                 "facebook_positions": ["story", "facebook_reels"],
                 "instagram_positions": ["story", "reels"]}
FEED_SPEC = {"publisher_platforms": ["facebook", "instagram", "messenger", "audience_network"]}


def has_placements(creative):
    return bool((creative or {}).get("asset_feed_spec"))


def _video(video_id, thumbnail, label):
    v = {"video_id": str(video_id)}
    if thumbnail:
        v["thumbnail_url"] = thumbnail
    v["adlabels"] = [{"name": label}]
    return v


def instagram_of(story):
    # Older creatives name the Instagram account instagram_actor_id; Meta wants instagram_user_id now.
    return (story or {}).get("instagram_user_id") or (story or {}).get("instagram_actor_id")


def build(story, vertical, instagram_user_id=None):
    """(object_story_spec, asset_feed_spec) for the ad with `vertical` added; ValueError says why not.
    `instagram_user_id` is the creative's own Instagram account, used when the story doesn't name one."""
    v = (story or {}).get("video_data") or {}
    if not v.get("video_id"):
        raise ValueError("Only a single-video ad can get a 9:16 video for Reels this way.")
    if str(vertical["video_id"]) == str(v["video_id"]):
        raise ValueError("The 9:16 video is the same video the ad already shows.")
    cta = v.get("call_to_action") or {}
    identity = {"page_id": story["page_id"]} if story.get("page_id") else {}
    ig = instagram_of(story) or instagram_user_id
    if ig:
        identity["instagram_user_id"] = str(ig)
    feed = {
        "videos": [_video(v["video_id"], v.get("image_url"), FEED),
                   _video(vertical["video_id"], vertical.get("thumbnail_url"), VERTICAL)],
        "bodies": [{"text": v.get("message") or ""}],
        "titles": [{"text": v.get("title") or ""}],
        "link_urls": [{"website_url": (cta.get("value") or {}).get("link") or "http://fb.me/"}],
        "ad_formats": ["SINGLE_VIDEO"],
        "optimization_type": "PLACEMENT",
        "asset_customization_rules": [
            {"customization_spec": VERTICAL_SPEC, "video_label": {"name": VERTICAL}, "priority": 1},
            {"customization_spec": FEED_SPEC, "video_label": {"name": FEED}, "priority": 2},
        ],
    }
    if v.get("link_description"):
        feed["descriptions"] = [{"text": v["link_description"]}]
    if cta.get("type"):
        feed["call_to_action_types"] = [cta["type"]]
        if cta.get("value"):
            feed["call_to_actions"] = [{"type": cta["type"], "value": cta["value"]}]
    return identity, feed


def form_ids(spec):
    """Every lead_gen_form_id anywhere in a spec, as strings."""
    found = set()
    if isinstance(spec, dict):
        for k, val in spec.items():
            if k == "lead_gen_form_id" and val not in (None, ""):
                found.add(str(val))
            else:
                found |= form_ids(val)
    elif isinstance(spec, list):
        for item in spec:
            found |= form_ids(item)
    return found


def describe(made):
    """What Meta stored, in a line for the change log: enough to see why a read-back failed."""
    feed = (made or {}).get("asset_feed_spec") or {}
    story = (made or {}).get("object_story_spec") or {}
    shown = [{k: v[k] for k in ("video_id", "adlabels") if k in v} for v in feed.get("videos") or []]
    videos = json.dumps(shown, sort_keys=True)[:800]
    return f"feed keys: {', '.join(sorted(feed)) or 'none'}; videos: {videos}; story keys: {', '.join(sorted(story)) or 'none'}"


def _labels(video):
    return {str(l.get("name")) for l in video.get("adlabels") or [] if isinstance(l, dict)}


def _has_vertical(feed, vertical_id):
    # Meta stores each asset_feed_spec video under a new id (an untitled copy), so the uploaded id
    # rarely comes back; the eb_vertical label it keeps is what marks the 9:16 one.
    return any(v.get("video_id") and (str(v["video_id"]) == str(vertical_id) or VERTICAL in _labels(v))
               for v in feed.get("videos") or [])


def readback_problem(old_story, made, vertical_id, instagram=False):
    """What's wrong with the creative Meta stored, or None. Checked before it replaces the
    running ad's creative: the 9:16 video must be in it, the lead form must not change, and an ad
    that runs on Instagram (`instagram`) must keep its Instagram account."""
    feed = (made or {}).get("asset_feed_spec") or {}
    if not _has_vertical(feed, vertical_id):
        return "Meta's copy of the new creative has no 9:16 video."
    if instagram and not instagram_of((made or {}).get("object_story_spec")) and not (made or {}).get("instagram_user_id"):
        return "Meta's copy of the new creative has no Instagram account, so it couldn't run on Instagram."
    want = form_ids(old_story)
    if want and form_ids(made) != want:
        return "Meta's copy of the new creative lost the lead form, so the button wouldn't open your form."
    return None
