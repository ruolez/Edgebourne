"""Meta's automatic creative changes (Advantage+ creative enhancements) for one ad: what each
does in plain words, whether it's on, and the meta-ads skill's advice (references/05 §4.2):
anything that rewrites the words, adds text, or generates new pixels stays off for brand copy;
fit and brightness adjustments are fine. Creatives can't change on Meta, so switching one
means a new creative with the new setting, put on the ad (which Meta then reviews again)."""
import copy

# key: (label, what it does, advice) — advice "off" = keep off for brand copy, "fine" = harmless
FEATURES = {
    "text_optimizations": ("Text improvements", "Swaps and rewrites your primary text, headline and description per person.", "off"),
    "inline_comment": ("Relevant comments", "Shows a comment someone left under the ad.", "off"),
    "enhance_cta": ("Enhance the button", "Changes the button wording and may add phrases from your site.", "off"),
    "generate_cta": ("Generate the button", "Writes a button label for you.", "off"),
    "add_text_overlay": ("Text on the image", "Puts your words on top of the picture.", "off"),
    "description_automation": ("Automatic description", "Writes the line under the headline.", "off"),
    "image_templates": ("Image templates", "Puts the image in a frame with text from the ad.", "off"),
    "image_touchups": ("Image touch-ups", "Crops and resizes the image for each placement.", "fine"),
    "adapt_to_placement": ("Fit to placement", "Adjusts the layout to each place the ad shows.", "fine"),
    "image_brightness_and_contrast": ("Brightness and contrast", "Lightens or sharpens the image.", "fine"),
    "image_background_gen": ("New backgrounds", "Generates a different background behind the image.", "off"),
    "image_uncrop": ("Expand image", "Generates more picture around the edges.", "off"),
    "video_uncrop": ("Expand video", "Generates more picture around the edges of the video.", "off"),
    "image_animation": ("Animate the image", "Adds movement to a still image.", "off"),
    "video_filtering": ("Video filters", "Applies visual filters to the video.", "off"),
    "creative_stickers": ("Stickers", "Adds stickers to the ad.", "off"),
    "music_generation": ("Music", "Adds music Meta picks or generates.", "off"),
    "text_translation": ("Translate the text", "Shows the words translated for people in other languages.", "off"),
    "translate_voiceover": ("Translate the voice-over", "Dubs the voice into other languages.", "off"),
    "image_text_translation": ("Translate words on the image", "Rewrites the words inside the picture in other languages.", "off"),
    "site_extensions": ("Site links", "Adds links pulled from your website.", "off"),
    "product_extensions": ("Product items", "Adds items from a product catalog.", "off"),
    "video_highlights": ("Video highlights", "Cuts the video into a shorter highlight.", "off"),
    "media_type_automation": ("Change the format", "May show the ad in another format, like a carousel.", "off"),
}
RETIRED = {"standard_enhancements"}  # the old bundle switch; Meta ignores it now


def human(key):
    return key.replace("_", " ").capitalize()


def read(dof):
    """[{key, label, about, on, advice}] for every feature the creative states, known ones first."""
    spec = ((dof or {}).get("creative_features_spec") or {})
    out = []
    for key, val in spec.items():
        if key in RETIRED:
            continue
        label, about, advice = FEATURES.get(key, (human(key), "A Meta enhancement this dashboard doesn't describe yet.", None))
        out.append({"key": key, "label": label, "about": about, "on": (val or {}).get("enroll_status") == "OPT_IN", "advice": advice})
    order = list(FEATURES)
    out.sort(key=lambda f: (not f["on"], order.index(f["key"]) if f["key"] in order else len(order), f["key"]))
    return out


def with_change(dof, key, on):
    """The same spec with one feature switched; the rest untouched."""
    new = copy.deepcopy(dof or {})
    spec = new.setdefault("creative_features_spec", {})
    entry = dict(spec.get(key) or {})
    entry["enroll_status"] = "OPT_IN" if on else "OPT_OUT"
    spec[key] = entry
    return new


def against_advice(features):
    """The features that are on although the advice is to keep them off."""
    return [f["label"] for f in features if f["on"] and f["advice"] == "off"]
