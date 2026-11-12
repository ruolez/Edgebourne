"""New ad (roadmap 4.x, 9.4e), pure part: what is missing before anything is sent to Meta, each
problem at the input it is about (the New ad page's field names), in the order the page shows them."""

MEDIA_KINDS = {"image": "hash", "video": "video_id"}


def problems(data, cta_types):
    """[(field, message)]. `data` is what New ad posts; `cta_types` the buttons it may pick."""
    out = []
    scratch = not (data.get("template_ad_id") or "")
    if not str(data.get("adset_id") or "").strip():
        out.append(("adset_id", "Pick the ad set it goes in"))
    form_id = str(data.get("form_id") or "").strip()
    if form_id and not form_id.isdigit():
        out.append(("form_id", "Unknown lead form"))
    elif scratch and not form_id:
        out.append(("form_id", "Pick the lead form the button opens"))
    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    kind = media.get("kind")
    if scratch and kind == "same":
        out.append(("media", "Choose an image or video (it doesn't start from another ad)"))
    elif kind != "same" and not (kind in MEDIA_KINDS and media.get(MEDIA_KINDS[kind])):
        out.append(("media", "Choose an image or video"))
    if not (data.get("body") or "").strip():
        out.append(("body", "Write the primary text"))
    if not (data.get("title") or "").strip():
        out.append(("title", "Write a headline"))
    if data.get("cta_type") and data["cta_type"] not in cta_types:
        out.append(("cta_type", "Pick a button from the list"))
    if not (data.get("name") or "").strip():
        out.append(("name", "Name the ad (only you see the name)"))
    return out
