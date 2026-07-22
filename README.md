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
3. **Renew SSL now** — manual renewal check, in addition to the automatic timer.
4. **Remove** — deletes containers, volumes, and the app directory (with an optional final DB
   backup to `/root` and optional certificate deletion).

Production TLS uses `docker-compose.prod.yml` + `nginx/nginx-ssl.conf` (rendered from
`nginx/nginx-ssl.conf.template`), activated through `COMPOSE_FILE` in `/opt/edgebourne/.env`.

## Design source

The original Claude Design handoff bundle lives untouched in `project/`
(`EdgeBourne Identity.dc.html` is the canonical design; tokens and the four logo SVGs
were lifted from it into `backend/templates/_svg_defs.html` and `backend/static/css/site.css`).
