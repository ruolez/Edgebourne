# EdgeBourne — Website + Admin CMS

Marketing site and admin panel for **EdgeBourne** (custom solutions · web & mobile apps · integration · automation), built from the brand identity in `project/EdgeBourne Identity.dc.html`.

- **Stack:** Flask (server-rendered Jinja2) · PostgreSQL 16 · nginx · vanilla CSS/JS · Docker Compose
- **Local URL:** http://localhost:8090 — admin at http://localhost:8090/admin

## Run locally

```bash
cp .env.example .env        # then edit: SECRET_KEY, POSTGRES_PASSWORD, ADMIN_INITIAL_PASSWORD
docker compose up -d --build
```

Log in at `/admin/login` with username `admin` and the password from `ADMIN_INITIAL_PASSWORD`
(seeded on first boot only — changing the env var later has no effect).

Development with live reload (also exposes Postgres on host port 5480):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Architecture

| Service  | Image           | Role                                                                  |
|----------|-----------------|-----------------------------------------------------------------------|
| nginx    | nginx:alpine    | Only exposed port (`APP_PORT`, default 8090). Serves `/static/` and `/uploads/` with immutable caching, proxies everything else to Flask. |
| backend  | python:3.12     | Flask + gunicorn. Renders the public site and the admin panel. Plain-SQL migrations in `backend/migrations/` run at startup. |
| postgres | postgres:16     | Data. Not exposed to the host in production.                          |
| scheduler | python:3.12    | Recurring invoices, email retries, Stripe reconciliation. Same image as backend, different command. |

Volumes: `pgdata` (database), `uploads` (admin-uploaded images, re-encoded to WebP).

## Admin panel

- **Dashboard** — lead counts, content stats, recent leads
- **Site content** — homepage hero, About page, SEO defaults, contact email/phone/socials
- **Services / Work / Blog / Pages** — full CRUD with a markdown editor (toolbar + live preview),
  image uploads, drafts vs published, ordering (↑/↓), per-item SEO fields
- **Pages** — custom pages served at `/<slug>`, optionally shown in the site nav
- **Leads** — contact-form submissions; opening marks read
- **Email** — SMTP settings + "Send test email". Leads are always stored; email notification is
  best-effort on top. For local testing use host `host.docker.internal`, port `1025`,
  encryption `none` (delivers to the mail catcher at http://localhost:1080).

## Portfolio content

The public site is content-driven: ten case studies, four blog posts, eight FAQs and the
Process / Industries pages ship as seeded content in `backend/migrations/007_portfolio_seed.sql`,
so a fresh install or a production update arrives with the site already populated. Nothing has
to be re-entered in the admin after a deploy.

**Case studies** (`case_studies`) carry, beyond the basics:

| Column | Purpose |
|---|---|
| `industry` | Drives the filter chips on `/work`. Keep the set small — a chip per case study is not a filter. |
| `engagement` | e.g. "6 weeks to first sync · ongoing support" |
| `problem_lede` | 1-2 sentences, rendered as the pull-quote at the top of the page |
| `metrics` | JSONB `[{value, label}]`, max 4, shown as the stat row and inline in the homepage showcase |
| `gallery` | JSONB `[{src, thumb, caption}]`, the screenshot gallery + lightbox |
| `stack` | Full stack list for the sidebar (distinct from `tech_tags`, which are the card chips) |
| `is_featured` | The three alternating showcase rows on the homepage |

**Screenshots** are committed static files under `backend/static/media/work/<slug>/`
(`cover.webp` 1600x1000, `cover-thumb.webp` 800x500, `NN-name.webp` + `NN-name-thumb.webp`).
They are served by nginx from the host bind-mount, so they deploy with a `git pull` and need no
image rebuild and no re-upload. The admin can still upload gallery images the normal way; those
land in the `uploads` volume instead.

**Testimonials are approval-gated.** Rows seed with `is_approved = false` and the public site
renders only approved ones — `/` and `/work/<slug>` show nothing until someone ticks the box in
**Admin → Testimonials**. The seeded quotes are drafts written to match real client feedback;
confirm the wording with the client before approving. This is deliberate: nothing attributed to a
named human goes live without a person deciding it should.

**FAQs** (`faqs`) render as the homepage accordion, markdown rendered to HTML on save.

Homepage stats, the process strip, industry tiles and the tech list are inline `{% set %}` lists
at the top of `backend/templates/public/home.html` — they have no DB contract, so edit the
template to change them.

## Billing

A full back office: **Customers → Projects → Estimates → Invoices → Payments**, with a
per-customer account ledger and Stripe card payments.

- **Customers** — contact and billing address, currency (fixed once set), payment terms,
  default tax rate, archiving. The detail page is a hub: invoices, estimates, projects,
  payments and the account ledger.
- **Projects** — group documents under a customer and track budget vs. invoiced.
- **Estimates / work orders** — an accepted estimate *is* the work order; there is no separate
  Orders table. Send one and the customer accepts it online (their typed name, IP and timestamp
  are recorded as the audit trail), then convert it to a draft invoice.
- **Invoices** — line items with per-line tax rates, document-level discount, a printable view.
  Line items lock the moment an invoice is issued: corrections go through void-and-reissue or a
  credit note. That is what keeps the ledger truthful with no reconciliation logic.
- **Payments** — Stripe Hosted Checkout, plus manually recorded transfers, cheques and cash.
  Partial payments; an overpayment splits into the applied part and on-account credit.
  Refunds (Stripe or manual) optionally issue a credit note so the invoice stays settled.
- **Recurring** — retainers on a weekly/monthly/quarterly/annual cadence, generated by the
  `scheduler` container.
- **Consistency check** (`/admin/billing/audit`) rebuilds every customer's balance from the
  invoice, payment and refund tables and flags any disagreement with the ledger.

### How customers see it

There is no customer login. Each invoice and estimate gets an unguessable link
(`/pay/<token>`, `/estimate/<token>`) that is emailed to them. **Only a SHA-256 hash of the
token is stored**, so database backups contain no working payment links — the trade-off is that
a link cannot be re-displayed after sending; use "New customer link" to rotate and resend (the
old link keeps working for 24 hours).

Documents are print-styled HTML rather than generated PDFs — the customer presses Ctrl-P.

### Money handling

All amounts are **integer minor units** (`*_cents BIGINT`); quantities are thousandths and tax
rates thousandths of a percent. No float or `Decimal` ever reaches the database. Totals are
recomputed in SQL on every save, tax is computed per rate-group with any discount allocated
pro-rata, and invoice status is always derived with `SUM()` over payments and refunds — never
incremented, and never taken from a webhook field. That last property is what makes Stripe's
at-least-once, out-of-order webhook delivery harmless.

### Stripe setup

Keys are configured in **Billing settings** in the admin panel. They are **encrypted at rest**
with a key derived from `SECRET_KEY`, which lives in `.env` and is never written to the
database — so a stolen `pg_dump` yields ciphertext, and restoring it elsewhere gets you nothing.
The same applies to the SMTP password.

Because a settable webhook secret is precisely what someone with a stolen admin session would
want (point it at a secret they control, then post forged "payment succeeded" events), changing
any payment key requires the admin password again and is written to the audit log and emailed to
the alert address. Replacing the webhook secret keeps the previous one valid for one rotation, so
events already in flight are not rejected.

Setting `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` or `PUBLIC_BASE_URL` in the environment
still takes precedence; those fields then show as locked in the UI. Use that if you would rather
keep keys off the box entirely.

Test vs. live mode is derived from the key prefix (`sk_test_` / `sk_live_`) — there is no
separate toggle to fall out of sync. While in test mode, customer email is suppressed unless you
set a test-email override.

`sudo ./install.sh` → "Stripe / webhook setup info" prints the webhook URL to register and the
events to subscribe to.

Locally:

```bash
stripe listen --forward-to localhost:8090/billing/webhook/stripe
```

`stripe listen` prints its own `whsec_`, which differs from the Dashboard endpoint's — put the
CLI one in `.env` for local work.

> **PCI scope.** Hosted Checkout means card data never touches this server (SAQ A, the lowest
> burden). Adding Stripe Elements or any card input field to this app would destroy that. Don't.

### The scheduler

A separate container running the same image. It generates recurring invoices, drains the email
queue, retries failed webhooks, expires stale estimates, sends overdue reminders and — most
importantly — **reconciles against Stripe daily**, alerting if a succeeded payment has no local
record. That is the control that catches a webhook outage or a rotated-but-not-updated signing
secret.

Its heartbeat is shown on the dashboard; if it goes red, retainers are not being billed.

```bash
docker compose logs -f scheduler
docker compose run --rm scheduler python scheduler.py --once   # one pass, by hand
```

Invoices generated while *catching up* after downtime are held as **drafts**, never emailed —
if the scheduler has been down long enough to miss a period, a human should look first.

## SEO / performance

Server-rendered HTML with per-page meta + OG tags, `sitemap.xml`, `robots.txt`,
self-hosted fonts (~50 KB), one stylesheet, ~10 lines of public JS, gzip + long-cache static assets.

## Deploying to a VPS (Ubuntu 24)

One-line install on a clean server:

```bash
curl -fsSL https://raw.githubusercontent.com/ruolez/Edgebourne/main/install.sh | sudo bash
```

The installer menu offers:

1. **Install** — installs Docker + certbot, clones this repo to `/opt/edgebourne`, prompts for
   the domain (and verifies its DNS A record points at the server), issues a Let's Encrypt
   certificate (auto-renewing via `certbot.timer` with an nginx reload hook), and brings the
   site up on HTTPS.
2. **Update from GitHub** — backs up PostgreSQL to `/var/backups/edgebourne` (last 14 kept),
   pulls the latest code, rebuilds, applies any new DB migrations automatically at startup,
   and prunes unused Docker images.
3. **Install SSL only** — sets up (or redoes) the Let's Encrypt certificate on an existing
   installation, e.g. after fixing DNS or changing the domain.
4. **Renew SSL now** — manual renewal check, in addition to the automatic timer.
5. **Remove** — deletes containers, volumes, and the app directory (with an optional final DB
   backup to `/root` and optional certificate deletion).

Production TLS uses `docker-compose.prod.yml` + `nginx/nginx-ssl.conf` (rendered from
`nginx/nginx-ssl.conf.template`), activated through `COMPOSE_FILE` in `/opt/edgebourne/.env`.

## Design source

The original Claude Design handoff bundle lives untouched in `project/`
(`EdgeBourne Identity.dc.html` is the canonical design; tokens and the four logo SVGs
were lifted from it into `backend/templates/_svg_defs.html` and `backend/static/css/site.css`).
