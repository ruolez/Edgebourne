import datetime
import io
import os
import uuid

from PIL import Image

import config

MAX_SIDE = 1920
THUMB_SIDE = 640
QUALITY = 82


def save_image(file_storage):
    """Validate an uploaded image, re-encode as webp (full + thumb).
    Returns (full_path, thumb_path) as /uploads/... URL paths."""
    raw = file_storage.read()
    if not raw:
        raise ValueError("Empty file")
    if len(raw) > config.MAX_CONTENT_LENGTH:
        raise ValueError("File too large (max 10 MB)")
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise ValueError("Not a valid JPEG, PNG or WebP image")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    subdir = datetime.date.today().strftime("%Y/%m")
    name = uuid.uuid4().hex
    dirpath = os.path.join(config.UPLOADS_DIR, subdir)
    os.makedirs(dirpath, exist_ok=True)

    def encode(max_side, suffix):
        copy = img.copy()
        copy.thumbnail((max_side, max_side))
        copy.save(os.path.join(dirpath, f"{name}{suffix}.webp"), "WEBP", quality=QUALITY)
        return f"/uploads/{subdir}/{name}{suffix}.webp"

    return encode(MAX_SIDE, ""), encode(THUMB_SIDE, "_t")


def delete_upload(url_path):
    """Best-effort removal of a stored upload given its /uploads/... path."""
    if not url_path or not url_path.startswith("/uploads/"):
        return
    rel = os.path.normpath(url_path[len("/uploads/"):])
    if rel.startswith(".."):
        return
    try:
        os.remove(os.path.join(config.UPLOADS_DIR, rel))
    except OSError:
        pass
