import re

import markdown as md_lib

RESERVED_SLUGS = {
    "services", "work", "about", "contact", "blog", "admin", "static",
    "uploads", "healthz", "sitemap.xml", "robots.txt", "favicon.ico", "index",
}

SLUG_RE = re.compile(r"^[a-z0-9-]{1,120}$")


def render_md(text):
    return md_lib.markdown(text or "", extensions=["extra", "smarty"])


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:120] or "page"


def clean_slug(raw, fallback_title=""):
    slug = (raw or "").strip().lower()
    return slugify(slug) if slug else slugify(fallback_title)


def slug_error(slug):
    if not SLUG_RE.match(slug):
        return "Slug may only contain lowercase letters, numbers and hyphens."
    if slug in RESERVED_SLUGS:
        return f'"{slug}" is a reserved URL — pick a different slug.'
    return None


def excerpt(text, length=180):
    plain = re.sub(r"[#*_`>\[\]()!]", "", text or "")
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain if len(plain) <= length else plain[:length].rsplit(" ", 1)[0] + "…"
