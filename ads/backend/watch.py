"""Watch (the ad player): which video links the console fetches from Meta, where a fetched video is kept and how the
keep is trimmed. Pure apart from the files in the cache folder, so it is tested without Meta or a database."""
import os
from urllib.parse import urlparse

# Meta hands out video files from its CDN; anything else in a `source` answer is refused (the console fetches it).
META_MEDIA_HOSTS = (".fbcdn.net", ".facebook.com", ".fbsbx.com", ".cdninstagram.com")
MAX_VIDEO_BYTES = 200 * 1024 * 1024
CACHE_BYTES = 2 * 1024 * 1024 * 1024
IDS_LIMIT = 200


def allowed_source(url, dev=False):
    """True for a Meta CDN https link; with dev (a fake Graph API is configured) any http(s) link."""
    try:
        u = urlparse(url or "")
    except ValueError:
        return False
    if not u.hostname:
        return False
    if dev:
        return u.scheme in ("http", "https")
    return u.scheme == "https" and any(u.hostname.endswith(h) for h in META_MEDIA_HOSTS)


def cache_file(folder, video_id):
    """The kept file of a Meta video, or None for an id that isn't one (ids are digits)."""
    vid = str(video_id or "")
    return os.path.join(folder, f"{vid}.mp4") if vid.isdigit() else None


def prune(folder, limit=CACHE_BYTES, keep=()):
    """Delete the least recently used videos until the folder holds at most `limit` bytes; `keep` (paths) stay.
    Returns the paths deleted."""
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".mp4")]
    except FileNotFoundError:
        return []
    files = []
    for n in names:
        p = os.path.join(folder, n)
        try:
            st = os.stat(p)
        except FileNotFoundError:
            continue
        files.append((max(st.st_atime, st.st_mtime), st.st_size, p))
    total = sum(size for _, size, _ in files)
    gone = []
    for _, size, p in sorted(files):
        if total <= limit:
            break
        if p in keep:
            continue
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        total -= size
        gone.append(p)
    return gone


def parse_ids(raw):
    """The ad ids of ?ids=a,b,c: digits only, in order, without repeats, at most IDS_LIMIT."""
    out = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if part.isdigit() and part not in out:
            out.append(part)
    return out[:IDS_LIMIT]
