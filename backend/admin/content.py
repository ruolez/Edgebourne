"""Editable site copy.

Everything the public templates used to hard-code -- section headings, page
heads, list items -- lives in one table, `content_blocks`, keyed by group.
GROUPS below is what turns that generic table into a purpose-built form: it
says which columns a group actually uses and what to call them in that
group's own language ("Number" and "Label", not "Title" and "Subtitle").
"""

import json

import psycopg2
from flask import abort, flash, redirect, render_template, request, url_for

import db

from . import bp
from .services import move_row

COLUMNS = ("title", "subtitle", "body", "items", "link_url", "link_label")


def f(name, label, type="text", help="", options=None):
    """A column field. `name` must be one of COLUMNS."""
    return {"name": name, "label": label, "type": type, "help": help,
            "store": "col", "options": options or []}


def x(name, label, type="text", help="", options=None):
    """A group-specific field kept in the `extra` JSON column."""
    return {"name": name, "label": label, "type": type, "help": help,
            "store": "extra", "options": options or []}


_LIST_HELP = "One per line. Blank lines are ignored."

# Fields shared by the three fixed lookup groups.
_SECTION_FIELDS = [
    f("subtitle", "Eyebrow", help="The small mono label above the heading. Leave blank to hide it."),
    f("title", "Heading"),
    f("body", "Lead paragraph", "textarea"),
    f("link_label", "Button label", help="Leave blank to hide the button."),
    f("link_url", "Button link"),
]

GROUPS = [
    # ------------------------------------------------------------ home
    {
        "key": "home_proof", "page": "Home", "label": "Hero proof chips",
        "desc": "The three short claims under the hero buttons.",
        "single": "proof",
        "fields": [f("items", "Chips", "textarea", _LIST_HELP)],
    },
    {
        "key": "home_stats", "page": "Home", "label": "Stat band",
        "desc": "The four numbers in the dark band under the hero.",
        "help": "Keep the number short — it is set in very large type. "
                "The About page has its own stat band: if you change a figure "
                "that appears in both, change it there too, or the two pages "
                "will contradict each other.",
        "fields": [f("title", "Number", help="e.g. 10, 100%, 1 day"),
                   f("subtitle", "Label", help="What the number counts.")],
    },
    {
        "key": "home_cascade", "page": "Home", "label": "AI cascade stages",
        "desc": "The numbered stages a record passes through in the AI band.",
        "help": "The bar width is illustrative: it shows how much work is left "
                "when a record reaches that stage, so it should shrink down the list.",
        "fields": [
            f("title", "Stage name"),
            f("subtitle", "Note", help="One short line under the stage name."),
            x("fill", "Bar width", help="A CSS width such as 58%."),
            x("kind", "Stage style", "select", options=[
                ("", "Normal"), ("is-ai", "AI stage (highlighted)"),
                ("is-end", "Final stage")]),
            x("done", "Show the “Confirmed” tick", "checkbox"),
        ],
    },
    {
        "key": "home_ai_principles", "page": "Home", "label": "AI principles",
        "desc": "The four cards explaining how AI is used.",
        "fields": [f("title", "Heading"), f("body", "Text", "textarea")],
    },
    {
        "key": "home_ai_apps", "page": "Home", "label": "AI applications",
        "desc": "“What it does today” — the bulleted list in the AI band.",
        "fields": [f("title", "Lead-in", help="Shown in bold at the start of the line."),
                   f("body", "Text", "textarea")],
    },
    {
        "key": "home_ai_proof", "page": "Home", "label": "AI proof links",
        "desc": "“Already running in production” — links to case studies.",
        "fields": [f("title", "Link text"), f("link_url", "Link", help="e.g. /work/ai-seo-catalog")],
    },
    {
        "key": "home_ai_buttons", "page": "Home", "label": "AI band buttons",
        "desc": "The buttons at the foot of the AI band.",
        "help": "The first button is solid, the rest are outlined.",
        "fields": [f("title", "Button label"), f("link_url", "Link")],
    },
    {
        "key": "home_process_steps", "page": "Home", "label": "Process strip",
        "desc": "The five-step summary. Keep the names identical to the Process page.",
        "help": "A visitor clicking through to /process should not meet a second, "
                "differently-named process.",
        "fields": [f("title", "Step name"), f("body", "Text", "textarea")],
    },
    {
        "key": "home_sectors", "page": "Home", "label": "Industry tiles",
        "desc": "The tile grid linking into the Industries page.",
        "key_label": "Anchor",
        "key_help": "The id of the section on /industries this tile jumps to.",
        "fields": [f("title", "Industry name"), f("subtitle", "Note")],
    },
    {
        "key": "home_tech", "page": "Home", "label": "Technology marquee",
        "desc": "The scrolling “Built with” list at the foot of the home page.",
        "single": "tech",
        "fields": [f("subtitle", "Eyebrow"),
                   f("items", "Technologies", "textarea", _LIST_HELP)],
    },
    # ------------------------------------------------------------ process
    {
        "key": "process_steps", "page": "Process", "label": "The five steps",
        "desc": "The timeline that is the whole page.",
        "fields": [
            f("title", "Step name"),
            f("subtitle", "One-line summary", help="Set in large type under the step name."),
            f("body", "Detail", "textarea"),
            f("items", "What you get", "textarea", _LIST_HELP),
        ],
    },
    {
        "key": "process_pricing", "page": "Process", "label": "Pricing cards",
        "desc": "“What it costs, and how long it runs” — the four dark cards.",
        "fields": [
            f("title", "Heading"),
            f("body", "Text", "textarea"),
            x("title_setting", "Heading from Site content",
              help="Leave blank. Set to onboarding_fee to show the Onboarding fee "
                   "from Site content here instead of the heading above."),
            x("body_setting", "Text from Site content",
              help="Leave blank. Set to onboarding_fee_note to show the Onboarding "
                   "note from Site content instead of the text above."),
        ],
    },
    # ------------------------------------------------------------ industries
    {
        "key": "industries_sectors", "page": "Industries", "label": "Industry sections",
        "desc": "One full section per industry, plus the jump bar at the top.",
        "key_label": "Anchor",
        "key_help": "Used as the #id, so /industries#legal links straight here. "
                    "Changing it breaks existing links.",
        "fields": [
            f("title", "Industry name"),
            f("body", "Lede", "textarea"),
            f("items", "Warning signs", "textarea", _LIST_HELP),
            x("caps", "What we build here", "textarea", _LIST_HELP),
            x("cases", "Relevant work", "textarea",
              "One per line as case-study-slug | Link text."),
        ],
    },
    # ------------------------------------------------------------ services
    {
        "key": "services_shapes", "page": "Services", "label": "Ways to start",
        "desc": "“Three ways to start” — the dark cards at the foot of the page.",
        "fields": [
            f("subtitle", "Badge", help="The small mono label, e.g. FROM 2 WEEKS."),
            f("title", "Heading"),
            f("body", "Text", "textarea"),
        ],
    },
    # ------------------------------------------------------------ about
    {
        "key": "about_beliefs", "page": "About", "label": "How we work",
        "desc": "“Four things that stay true” — the belief cards.",
        "fields": [f("title", "Heading"), f("body", "Text", "textarea")],
    },
    {
        "key": "about_stats", "page": "About", "label": "Stat band",
        "desc": "The four numbers in the dark band at the foot of the page. "
                "Shares two figures with the homepage stat band — keep them in step.",
        "fields": [f("title", "Number"), f("subtitle", "Label")],
    },
    # ------------------------------------------------------------ contact
    {
        "key": "contact_steps", "page": "Contact", "label": "What happens next",
        "desc": "The numbered steps beside the contact form.",
        "fields": [f("title", "Lead-in", help="Shown in bold at the start of the line."),
                   f("body", "Text", "textarea")],
    },
    # ------------------------------------------------------------ global
    {
        "key": "sections", "page": "Global", "label": "Section headings",
        "desc": "The eyebrow, heading and lead of every band on the site.",
        "help": "These are fixed: a section cannot be added or removed here, only "
                "reworded. Clearing a heading falls back to the wording built into "
                "the page rather than leaving a blank band.",
        "fixed": True,
        "fields": _SECTION_FIELDS,
        "rows": {
            "home_services": ("Home · Services band", ""),
            "home_showcase": ("Home · Selected work", ""),
            "home_ai": ("Home · AI band", ""),
            "home_ai_cascade": ("Home · AI cascade", "Heading and note above the stage diagram."),
            "home_ai_apps": ("Home · AI applications", "Heading above the bulleted list."),
            "home_ai_proof": ("Home · AI proof panel", "Heading and the closing note under the links."),
            "home_process": ("Home · Process strip", ""),
            "home_industries": ("Home · Industry tiles", ""),
            "home_testimonials": ("Home · Testimonials", ""),
            "home_faq": ("Home · FAQ", ""),
            "home_blog": ("Home · Blog teasers", ""),
            "process_gets": ("Process · “What you get”", "Repeated inside every step."),
            "process_pricing": ("Process · Pricing band", ""),
            "services_shapes": ("Services · Ways to start", ""),
            "industries_caps": ("Industries · “What we build here”", "Repeated in every industry."),
            "industries_cases": ("Industries · “Relevant work”", "Repeated in every industry."),
            "about_beliefs": ("About · How we work", ""),
            "contact_next": ("Contact · “What happens next”", ""),
            "contact_form": ("Contact · Form", "Eyebrow, submit button and the note under it."),
            "work_problem": ("Case study · Problem eyebrow", ""),
            "work_stack": ("Case study · Stack panel", ""),
            "work_side_cta": ("Case study · Sidebar CTA", ""),
            "work_gallery": ("Case study · Gallery", ""),
            "work_related": ("Case study · Related work", ""),
            "footer_note": ("Footer · Note", "The paragraph under the wordmark."),
            "footer_explore": ("Footer · Explore column", ""),
            "footer_build": ("Footer · What we build column", ""),
            "footer_contact": ("Footer · Contact column", ""),
            "footer_bottom": ("Footer · Bottom line",
                              "Heading is the right-hand line; the lead follows the copyright."),
        },
    },
    {
        "key": "page_heads", "page": "Global", "label": "Page headers",
        "desc": "The eyebrow, big heading and lead at the top of each page.",
        "help": "The home page hero is edited under Site content instead.",
        "fixed": True,
        "fields": [
            f("subtitle", "Eyebrow"),
            f("title", "Heading"),
            x("accent", "Accent line", help="The second line, shown in teal. Leave blank for a one-line heading."),
            f("body", "Lead paragraph", "textarea"),
        ],
        "rows": {
            "services": ("Services", ""), "work": ("Work", ""),
            "process": ("Process", ""), "industries": ("Industries", ""),
            "about": ("About", ""), "contact": ("Contact", ""),
            "blog": ("Blog", ""), "notfound": ("404 page", ""),
        },
    },
    {
        "key": "page_cta", "page": "Global", "label": "Closing call to action",
        "desc": "The teal band at the foot of nearly every page.",
        "help": "“Every other page” carries the eyebrow, button and reassurance for "
                "all of them; the rest only override the heading and the lead.",
        "fixed": True,
        "fields": [
            f("subtitle", "Eyebrow"),
            f("title", "Heading"),
            f("body", "Lead paragraph", "textarea"),
            f("link_label", "Button label"),
            f("items", "Reassurance lines", "textarea", _LIST_HELP),
        ],
        "rows": {
            "default": ("Every other page", "Also supplies the eyebrow, button and reassurance everywhere."),
            "services": ("Services", ""), "work": ("Work", ""),
            "process": ("Process", ""), "industries": ("Industries", ""),
            "about": ("About", ""), "blog": ("Blog", ""),
            "work_detail": ("A case study", ""), "blog_post": ("A blog post", ""),
        },
    },
    {
        "key": "footer_explore", "page": "Global", "label": "Footer — Explore column",
        "desc": "The first list of links in the footer.",
        "fields": [f("title", "Label"), f("link_url", "Link")],
    },
    {
        "key": "footer_build", "page": "Global", "label": "Footer — What we build column",
        "desc": "The second list of links in the footer.",
        "fields": [f("title", "Label"), f("link_url", "Link")],
    },
]

PAGE_ORDER = ["Home", "Process", "Industries", "Services", "About", "Contact", "Global"]
BY_KEY = {g["key"]: g for g in GROUPS}


def _group(group_key):
    grp = BY_KEY.get(group_key)
    if not grp:
        abort(404)
    return grp


def _row_label(grp, row):
    named = grp.get("rows", {}).get(row["block_key"])
    if named:
        return named[0]
    for name in ("title", "subtitle", "body", "items", "link_label"):
        if row[name]:
            return row[name].split("\n")[0]
    return row["block_key"] or "(empty)"


@bp.get("/content")
def content_index():
    counts = {
        r["group_key"]: r["n"]
        for r in db.query(
            "SELECT group_key, COUNT(*) AS n FROM content_blocks GROUP BY group_key"
        )
    }
    pages = [
        (page, [g for g in GROUPS if g["page"] == page])
        for page in PAGE_ORDER
    ]
    return render_template("admin/content.html", pages=pages, counts=counts)


@bp.get("/content/<group_key>")
def content_group(group_key):
    grp = _group(group_key)
    rows = db.query(
        "SELECT * FROM content_blocks WHERE group_key = %s ORDER BY sort_order, id",
        (group_key,),
    )
    # A group that is only ever one block (the tech list, the hero chips) has
    # nothing worth listing -- go straight to its form.
    if grp.get("single") and rows:
        return redirect(url_for("admin.content_form", group_key=group_key, bid=rows[0]["id"]))
    return render_template(
        "admin/content_group.html", grp=grp, rows=rows, row_label=_row_label
    )


@bp.get("/content/<group_key>/new")
@bp.get("/content/<group_key>/<int:bid>")
def content_form(group_key, bid=None):
    grp = _group(group_key)
    if bid is None and (grp.get("fixed") or grp.get("single")):
        abort(404)
    row = None
    if bid:
        row = db.query(
            "SELECT * FROM content_blocks WHERE id = %s AND group_key = %s",
            (bid, group_key), one=True,
        )
        if not row:
            abort(404)
    return render_template(
        "admin/content_form.html", grp=grp, row=row, row_label=_row_label
    )


def _values(grp, form, existing):
    """Column values and the merged `extra` dict for one submitted form."""
    cols = {c: (existing[c] if existing else "") for c in COLUMNS}
    extra = dict(existing["extra"]) if existing else {}
    for field in grp["fields"]:
        name = field["name"]
        if field["type"] == "checkbox":
            value = bool(form.get(name))
        else:
            value = (form.get(name) or "").replace("\r\n", "\n").strip()
        if field["store"] == "col":
            cols[name] = value
        else:
            extra[name] = value
    return cols, extra


@bp.post("/content/<group_key>/new")
@bp.post("/content/<group_key>/<int:bid>")
def content_save(group_key, bid=None):
    grp = _group(group_key)
    existing = None
    if bid:
        existing = db.query(
            "SELECT * FROM content_blocks WHERE id = %s AND group_key = %s",
            (bid, group_key), one=True,
        )
        if not existing:
            abort(404)
    elif grp.get("fixed") or grp.get("single"):
        abort(404)

    cols, extra = _values(grp, request.form, existing)
    block_key = existing["block_key"] if existing else ""
    if grp.get("key_label"):
        block_key = (request.form.get("block_key") or "").strip()
    is_published = True if grp.get("fixed") else bool(request.form.get("is_published"))
    params = (
        cols["title"], cols["subtitle"], cols["body"], cols["items"],
        cols["link_url"], cols["link_label"], json.dumps(extra), block_key,
        is_published,
    )
    try:
        if bid:
            db.execute(
                """UPDATE content_blocks SET title=%s, subtitle=%s, body=%s, items=%s,
                   link_url=%s, link_label=%s, extra=%s, block_key=%s, is_published=%s,
                   updated_at=now() WHERE id=%s""",
                params + (bid,),
            )
        else:
            nxt = db.query(
                """SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM content_blocks
                   WHERE group_key = %s""",
                (group_key,), one=True,
            )["n"]
            db.execute(
                """INSERT INTO content_blocks
                   (title, subtitle, body, items, link_url, link_label, extra,
                    block_key, is_published, group_key, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                params + (group_key, nxt),
            )
    except psycopg2.errors.UniqueViolation:
        db.rollback()
        flash(f'{grp.get("key_label") or "Key"} "{block_key}" is already used in this list.', "error")
        return redirect(request.path)
    flash("Saved.", "success")
    return redirect(url_for("admin.content_group", group_key=group_key))


@bp.post("/content/<group_key>/<int:bid>/delete")
def content_delete(group_key, bid):
    grp = _group(group_key)
    if grp.get("fixed") or grp.get("single"):
        abort(404)
    db.execute(
        "DELETE FROM content_blocks WHERE id = %s AND group_key = %s", (bid, group_key)
    )
    flash("Deleted.", "success")
    return redirect(url_for("admin.content_group", group_key=group_key))


@bp.post("/content/<group_key>/<int:bid>/move")
def content_move(group_key, bid):
    _group(group_key)
    move_row("content_blocks", bid, request.form.get("dir"),
             "WHERE group_key = %s", (group_key,))
    return redirect(url_for("admin.content_group", group_key=group_key))
