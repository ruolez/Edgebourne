"""Homepage hero photo: one upload, every crop the page needs.

The admin uploads a single master image (generated or photographed). A
re-encoded copy of it is kept so the crop focus can change later without a
re-upload, and from it we cut a 4:5 portrait set for the desktop panel, a 4:3
set for phones and tablets, and a 1200x630 share card for og:image.

Every cut gets a fresh id: /uploads/ is served with a one-year immutable cache
header, so a recrop written over the old file names would never be seen.
"""
import io
import json
import os
import uuid

from PIL import Image, ImageOps

import config

SUBDIR = "hero"
# The default photo ships in the repo under static/media/hero/, so a recrop
# must be able to read a master from there as well as from uploads.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MASTER_MAX_SIDE = 3200
MIN_SHORT_SIDE = 700
SOFT_SHORT_SIDE = 1200
PORTRAIT = (4, 5)
LANDSCAPE = (4, 3)
OG_SIZE = (1200, 630)
PORTRAIT_WIDTHS = (640, 1040, 1560)
LANDSCAPE_WIDTHS = (800, 1200)
AVATAR_WIDTHS = (96, 192, 400)
AVATAR_MIN_SIDE = 300
WEBP_QUALITY = 80
FOCUS = {"left": 0.25, "center": 0.5, "right": 0.75}


def crop_box(width, height, ratio_w, ratio_h, focus_x=0.5):
    """The largest ratio_w:ratio_h box inside width x height, centred
    horizontally on focus_x (a fraction of the width) and vertically centred."""
    target = ratio_w / ratio_h
    if width / height > target:
        cw, ch = round(height * target), height
    else:
        cw, ch = width, round(width / target)
    left = min(max(round(focus_x * width - cw / 2), 0), width - cw)
    top = (height - ch) // 2
    return (left, top, left + cw, top + ch)


def rendition_widths(crop_width, widths):
    """The srcset widths worth writing for a crop: never upscaled, and the
    crop's own width stands in for the sizes it cannot reach."""
    out = [w for w in widths if w < crop_width]
    top = min(crop_width, widths[-1])
    if top not in out:
        out.append(top)
    return out


def load(value):
    """The stored setting as a dict, or None when no hero photo is set."""
    if not value:
        return None
    try:
        info = json.loads(value)
    except (TypeError, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("portrait") else None


def _dir():
    path = os.path.join(config.UPLOADS_DIR, SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _url(name):
    return f"/uploads/{SUBDIR}/{name}"


def _disk(url):
    return os.path.join(_dir(), os.path.basename(url))


def _master_path(url):
    if url.startswith("/static/"):
        rel = os.path.normpath(url[len("/static/"):])
        if not rel.startswith(".."):
            return os.path.join(STATIC_DIR, rel)
    return _disk(url)


def load_avatar(value):
    """The stored founder photo as a dict, or None when none is set."""
    if not value:
        return None
    try:
        info = json.loads(value)
    except (TypeError, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("sizes") else None


def save_master(file_storage, min_short=MIN_SHORT_SIDE):
    """Validate an upload and keep a re-encoded master. Returns (url, warning)."""
    raw = file_storage.read()
    if not raw:
        raise ValueError("Choose an image file to upload.")
    if len(raw) > config.MAX_CONTENT_LENGTH:
        raise ValueError("That file is over 10 MB. Export it as a JPEG or WebP and try again.")
    try:
        Image.open(io.BytesIO(raw)).verify()
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise ValueError("That isn't a JPEG, PNG or WebP image.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    short = min(img.size)
    if short < min_short:
        raise ValueError(
            f"That image is {img.width} x {img.height} px. The short side needs to be "
            f"at least {min_short} px."
        )
    img.thumbnail((MASTER_MAX_SIDE, MASTER_MAX_SIDE))
    name = f"{uuid.uuid4().hex}-master.webp"
    img.save(os.path.join(_dir(), name), "WEBP", quality=90, method=6)
    warning = None
    if min_short == MIN_SHORT_SIDE and short < SOFT_SHORT_SIDE:
        warning = (
            f"Saved, but the image is only {short} px on its short side, so it may look "
            f"soft on high-resolution screens. {SOFT_SHORT_SIDE} px or more is better."
        )
    return _url(name), warning


def cut(master_url, focus="center"):
    """Cut every rendition from the master. Returns the dict stored in the
    hero_image setting."""
    focus = focus if focus in FOCUS else "center"
    fx = FOCUS[focus]
    img = Image.open(_master_path(master_url))
    img.load()
    cut_id = uuid.uuid4().hex[:12]

    def renditions(ratio, widths, kind):
        box = crop_box(img.width, img.height, *ratio, fx)
        crop = img.crop(box)
        out = []
        for w in rendition_widths(crop.width, widths):
            h = round(w * ratio[1] / ratio[0])
            name = f"{cut_id}-{kind}-{w}.webp"
            crop.resize((w, h), Image.LANCZOS).save(
                os.path.join(_dir(), name), "WEBP", quality=WEBP_QUALITY, method=6
            )
            out.append({"src": _url(name), "w": w, "h": h})
        return out

    portrait = renditions(PORTRAIT, PORTRAIT_WIDTHS, "p")
    landscape = renditions(LANDSCAPE, LANDSCAPE_WIDTHS, "l")
    og_box = crop_box(img.width, img.height, *OG_SIZE, fx)
    og_name = f"{cut_id}-og.jpg"
    img.crop(og_box).resize(OG_SIZE, Image.LANCZOS).save(
        os.path.join(_dir(), og_name), "JPEG", quality=85, optimize=True, progressive=True
    )
    return {
        "master": master_url,
        "focus": focus,
        "portrait": portrait,
        "landscape": landscape,
        "og": _url(og_name),
    }


def cut_avatar(master_url):
    """A centred square set from the master: the founder photo, shown as a
    small round avatar in the hero and the CTA and larger on About."""
    img = Image.open(_master_path(master_url))
    img.load()
    crop = img.crop(crop_box(img.width, img.height, 1, 1))
    cut_id = uuid.uuid4().hex[:12]
    sizes = []
    for w in rendition_widths(crop.width, AVATAR_WIDTHS):
        name = f"{cut_id}-s-{w}.webp"
        crop.resize((w, w), Image.LANCZOS).save(
            os.path.join(_dir(), name), "WEBP", quality=WEBP_QUALITY, method=6
        )
        sizes.append({"src": _url(name), "w": w, "h": w})
    return {"master": master_url, "sizes": sizes}


def delete_cut(info, keep_master=True):
    """Best-effort removal of a cut's files (and, optionally, its master)."""
    if not info:
        return
    urls = [r["src"] for r in info.get("portrait", []) + info.get("landscape", []) + info.get("sizes", [])]
    urls.append(info.get("og", ""))
    if not keep_master:
        urls.append(info.get("master", ""))
    for url in urls:
        if not url or not url.startswith(f"/uploads/{SUBDIR}/"):
            continue
        try:
            os.remove(_disk(url))
        except OSError:
            pass
