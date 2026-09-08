from flask import (
    Blueprint, Response, abort, flash, redirect, render_template, request, url_for,
)

import db
import mailer

bp = Blueprint("public", __name__)


@bp.get("/healthz")
def healthz():
    db.query("SELECT 1")
    return {"ok": True}


@bp.get("/favicon.ico")
def favicon():
    return redirect("/static/favicon.svg", code=301)


@bp.get("/")
def home():
    services = db.query(
        "SELECT * FROM services WHERE is_published ORDER BY sort_order, id LIMIT 4"
    )
    work = db.query(
        "SELECT * FROM case_studies WHERE is_published ORDER BY sort_order, id LIMIT 3"
    )
    posts = db.query(
        """SELECT * FROM posts WHERE is_published
           ORDER BY published_at DESC NULLS LAST LIMIT 3"""
    )
    featured = db.query(
        """SELECT * FROM case_studies WHERE is_published AND is_featured
           ORDER BY sort_order, id LIMIT 3"""
    )
    testimonials = db.query(
        "SELECT * FROM testimonials WHERE is_approved ORDER BY sort_order, id"
    )
    faqs = db.query("SELECT * FROM faqs WHERE is_published ORDER BY sort_order, id")
    return render_template(
        "public/home.html",
        services=services,
        work=work,
        posts=posts,
        featured=featured,
        testimonials=testimonials,
        faqs=faqs,
    )


@bp.get("/services")
def services():
    rows = db.query("SELECT * FROM services WHERE is_published ORDER BY sort_order, id")
    return render_template("public/services.html", services=rows)


@bp.get("/work")
def work_index():
    rows = db.query(
        "SELECT * FROM case_studies WHERE is_published ORDER BY sort_order, id"
    )
    industries = db.query(
        """SELECT DISTINCT industry FROM case_studies
           WHERE is_published AND industry <> '' ORDER BY industry"""
    )
    return render_template(
        "public/work_index.html",
        work=rows,
        industries=[r["industry"] for r in industries],
    )


@bp.get("/work/<slug>")
def work_detail(slug):
    row = db.query(
        "SELECT * FROM case_studies WHERE slug = %s AND is_published", (slug,), one=True
    )
    if not row:
        abort(404)
    testimonial = db.query(
        """SELECT * FROM testimonials
           WHERE case_study_slug = %s AND is_approved
           ORDER BY sort_order, id LIMIT 1""",
        (slug,),
        one=True,
    )
    # Same industry first, then simply the next case studies in running order --
    # so a lone case study in its industry still gets two neighbours.
    related = db.query(
        """SELECT * FROM case_studies
           WHERE is_published AND id <> %s
           ORDER BY (industry <> '' AND industry = %s) DESC, sort_order, id
           LIMIT 2""",
        (row["id"], row["industry"]),
    )
    return render_template(
        "public/work_detail.html", cs=row, testimonial=testimonial, related=related
    )


@bp.get("/process")
def process():
    return render_template("public/process.html")


@bp.get("/industries")
def industries():
    return render_template("public/industries.html")


@bp.get("/about")
def about():
    return render_template("public/about.html")


@bp.get("/blog")
def blog_index():
    rows = db.query(
        """SELECT * FROM posts WHERE is_published
           ORDER BY published_at DESC NULLS LAST"""
    )
    return render_template("public/blog_index.html", posts=rows)


@bp.get("/blog/<slug>")
def blog_post(slug):
    row = db.query(
        "SELECT * FROM posts WHERE slug = %s AND is_published", (slug,), one=True
    )
    if not row:
        abort(404)
    return render_template("public/blog_post.html", post=row)


@bp.get("/contact")
def contact():
    return render_template("public/contact.html")


@bp.post("/contact")
def contact_post():
    if request.form.get("website"):
        return redirect(url_for("public.contact"))
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    message = (request.form.get("message") or "").strip()
    if not name or not email or not message:
        flash("Please fill in your name, email and message.", "error")
        return redirect(url_for("public.contact"))
    lead = db.execute(
        """INSERT INTO leads (name, email, company, phone, message, source_page)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
        (
            name,
            email,
            (request.form.get("company") or "").strip(),
            (request.form.get("phone") or "").strip(),
            message,
            request.form.get("source") or "/contact",
        ),
        returning=True,
    )
    mailer.notify_lead(dict(lead))
    flash("Thanks — your message is in. We'll get back to you within one business day.", "success")
    return redirect(url_for("public.contact"))


@bp.get("/sitemap.xml")
def sitemap():
    # NOTE: customer document pages (/pay/<token>, /estimate/<token>) must NEVER
    # be listed here -- the token is the credential.
    base = request.url_root.rstrip("/")
    entries = [(f"{base}/", None)]
    for path in (
        "/services", "/work", "/process", "/industries", "/about", "/blog", "/contact"
    ):
        entries.append((base + path, None))
    for row in db.query(
        "SELECT slug, updated_at FROM case_studies WHERE is_published"
    ):
        entries.append((f"{base}/work/{row['slug']}", row["updated_at"]))
    for row in db.query("SELECT slug, updated_at FROM posts WHERE is_published"):
        entries.append((f"{base}/blog/{row['slug']}", row["updated_at"]))
    for row in db.query("SELECT slug, updated_at FROM pages WHERE is_published"):
        entries.append((f"{base}/{row['slug']}", row["updated_at"]))
    items = []
    for url, updated in entries:
        lastmod = (
            f"<lastmod>{updated.date().isoformat()}</lastmod>" if updated else ""
        )
        items.append(f"<url><loc>{url}</loc>{lastmod}</url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(items)
        + "</urlset>"
    )
    return Response(xml, mimetype="application/xml")


@bp.get("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    body = (
        "User-agent: *\nDisallow: /admin\nDisallow: /pay/\nDisallow: /estimate/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@bp.get("/<slug>")
def custom_page(slug):
    row = db.query(
        "SELECT * FROM pages WHERE slug = %s AND is_published", (slug,), one=True
    )
    if not row:
        abort(404)
    return render_template("public/page.html", page=row)
