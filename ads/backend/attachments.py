"""FU-D: what a conversation on the Claude page holds (desk_attachments): the pictures, videos and pages Claude made
and the files a person sent with a message. Pure: the type from the bytes, the size rules, the picture's size and
length read from the bytes, and which old bodies go when an account would pass its budget."""
import struct

MIMES = {"image/jpeg": "image", "image/png": "image", "image/webp": "image", "video/mp4": "video",
         "video/quicktime": "video", "text/html": "page"}
# What Claude may attach as a preview: Meta's media library takes these (Upload as draft), a phone's .mov it does not.
CLAUDE_MIMES = ("image/jpeg", "image/png", "image/webp", "video/mp4")
MAX_BYTES = {"image": 10 * 1024 * 1024, "video": 60 * 1024 * 1024, "page": 3 * 1024 * 1024}
SIZE_WORDS = {"image": "images up to 10 MB", "video": "videos up to 60 MB", "page": "pages up to 3 MB"}
MAX_PER_TASK = 12
MAX_FILES = 6        # files a person sends with one message
UNSENT_HOURS = 24    # a file added to a message that was never sent is removed after this
# A page Claude built is shown in a frame with no origin of its own: no scripts, no requests, no forms, whatever its
# HTML says. Pictures and fonts travel inside it as data: URLs (`desk attach` inlines them on the Mac).
PAGE_CSP = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; "
            "frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
ACCOUNT_BUDGET = 1024 * 1024 * 1024  # bodies kept per account; the oldest go first
KEEP_DAYS = 30
HEAD = 4096  # bytes the sniffer looks at
REFUSED = "Only JPG, PNG, WebP images or MP4 videos"
# Boxes that may follow an MP4's ftyp box. Anything else (HTML, text) after a real-looking ftyp is refused.
MP4_BOXES = {b"moov", b"mdat", b"free", b"wide", b"skip", b"uuid", b"meta", b"moof", b"pdin", b"sidx", b"styp", b"prft"}
MP4_BRANDS = {b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash", b"MSNV", b"mp71"}


def sniff(head):
    """The MIME type of a preview from its first bytes, or None (GIF, HTML, SVG, MOV and anything else)."""
    head = bytes(head or b"")
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) > 16:
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and head[12:15] == b"VP8":
        return "image/webp"
    if head[4:8] == b"ftyp" and len(head) >= 16:
        size = struct.unpack(">I", head[:4])[0]
        if 16 <= size <= 256 and head[size + 4:size + 8] in MP4_BOXES:
            if head[8:12] in MP4_BRANDS:
                return "video/mp4"
            if head[8:12] == b"qt  ":
                return "video/quicktime"
    return None


def too_big(kind, size):
    """A plain refusal when a preview is over its kind's size, else None."""
    limit = MAX_BYTES.get(kind)
    if limit is None or size <= limit:
        return None
    return f"That preview is too big ({SIZE_WORDS[kind]})"


def page_problem(data):
    """Why these bytes can't be shown as a page, or None: one HTML document in UTF-8, within the size for pages.
    What it may do once shown is not decided here (PAGE_CSP switches scripts and requests off)."""
    data = bytes(data or b"")
    if len(data) > MAX_BYTES["page"]:
        return too_big("page", len(data))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "A page must be an HTML file in UTF-8"
    head = text.lstrip("\ufeff \t\r\n")[:1024].lower()
    if not (head.startswith("<!doctype html") or head.startswith("<html")):
        return "A page must be an HTML file (it starts with <!doctype html>)"
    return None


def clean_file_ids(raw, limit=MAX_FILES):
    """The ids of the files sent with a message, from a request body: positive whole numbers, each once, in order.
    None when the body holds anything else or more than a message takes."""
    if raw in (None, "", []):
        return []
    if not isinstance(raw, list) or len(raw) > limit:
        return None
    out = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            return None
        if v not in out:
            out.append(v)
    return out


def _png(data):
    if len(data) >= 24 and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg(data):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    return None


def _webp(data):
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = struct.unpack("<I", data[21:25])[0]
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def _boxes(data, start, end):
    i = start
    while i + 8 <= end:
        size = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        head = 8
        if size == 1 and i + 16 <= end:
            size, head = struct.unpack(">Q", data[i + 8:i + 16])[0], 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            return
        yield kind, i + head, i + size
        i += size


def _mp4(data):
    for kind, start, end in _boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        width = height = duration = None
        for inner, s, e in _boxes(data, start, end):
            if inner == b"mvhd" and e - s >= 20:
                if data[s] == 1 and e - s >= 32:
                    scale, length = struct.unpack(">IQ", data[s + 20:s + 32])
                else:
                    scale, length = struct.unpack(">II", data[s + 12:s + 20])
                duration = round(length * 1000 / scale) if scale else None
            elif inner == b"trak" and width is None:
                for t, ts, te in _boxes(data, s, e):
                    if t == b"tkhd" and te - ts >= 84:
                        off = ts + (88 if data[ts] == 1 else 76)
                        if off + 8 <= te:
                            w, h = struct.unpack(">II", data[off:off + 8])
                            if w and h:
                                width, height = w >> 16, h >> 16
        return (width, height), duration
    return None, None


def measure(mime, data):
    """{"width", "height", "duration_ms"} read from the bytes; None for anything it can't read (never a guess)."""
    data = bytes(data or b"")
    out = {"width": None, "height": None, "duration_ms": None}
    try:
        if mime in ("video/mp4", "video/quicktime"):
            size, duration = _mp4(data)
            out["duration_ms"] = duration
        else:
            size = {"image/png": _png, "image/jpeg": _jpeg, "image/webp": _webp}.get(mime, lambda d: None)(data)
    except (struct.error, IndexError, ValueError):
        return out
    if size and size[0] and size[1]:
        out["width"], out["height"] = int(size[0]), int(size[1])
    return out


def to_prune(rows, new_size, budget=ACCOUNT_BUDGET):
    """Ids of kept bodies to drop, oldest first, so the account's bodies plus a new one fit the budget.
    rows: [{id, size_bytes, created_at}] of the bodies still kept."""
    total = sum(r["size_bytes"] for r in rows) + new_size
    out = []
    for r in sorted(rows, key=lambda r: (r["created_at"], r["id"])):
        if total <= budget:
            break
        out.append(r["id"])
        total -= r["size_bytes"]
    return out
