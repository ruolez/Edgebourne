# Edge Bourne Ads Console: plan (draft for approval)

A private web dashboard at `ads.edgebourne.com` to watch, manage and improve the Meta ads,
with Claude Code on Eugene's Mac as the AI that researches, reviews and proposes changes.

## Architecture

```
Meta (webhooks, Graph API)            Eugene's browser
        │  leadgen ping   ▲ insights/ads           │ HTTPS, login
        ▼                 │                        ▼
┌─────────────── VPS: ads.edgebourne.com (shared proxy → edgebourne nginx)───────────────┐
│ nginx ─ Flask API (gunicorn) ─ Postgres                                                │
│   /webhooks/meta    verify + X-Hub-Signature-256 → fetch lead → save → email (SMTP)   │
│   sync worker       hourly: ads, statuses, daily insights per ad                      │
│   /api/*            dashboard (session login)                                         │
│   /api/agent/*      AI desk: tasks, reports, proposals (agent bearer token)           │
└────────────────────────────────────────────────────────────────────────────────────────┘
                              ▲ HTTPS pull/push (agent token)
                              │
          Eugene's Mac: Claude Code in ~/Desktop/Dev/meta-ads
          skill /ads-desk: pick up tasks → run with meta-ads MCP + skills → post results
          (manual, /loop, or a launchd job running `claude -p "/ads-desk run"`)
```

Why the AI runs on the Mac: the Meta Ads MCP login, the meta-ads knowledge skills and
Claude itself live there. The server never holds Claude; it only queues work and shows
results. The Mac pulls, so nothing on the Mac is exposed to the internet.

## Safety model (same rules as meta-ads/CLAUDE.md)

- Money moves (publish, activate, budget, bid, status) only happen after Eugene approves
  the exact change in the dashboard; every action shows current → proposed in dollars.
- Server-side guardrails, enforced regardless of who asks: budget step ≤ +20% (override
  needs a typed confirmation), max daily budget setting, no deletes (pause only), the
  account spending cap shown everywhere.
- Every write (by Eugene, the server or Claude) goes to an immutable change log, mirrored
  into `meta-ads/reports/log.md` by the bridge.
- Secrets only in the server `.env`; agent token scoped to `/api/agent/*`; webhook payloads
  signature-checked with the App Secret.

## Phases

| Phase | What ships | Depends on |
|---|---|---|
| 1. Foundation + leads (built 2026-11-08) | Docker/nginx/Postgres/migrations, login, installer (shared-proxy mode), Meta webhook, lead fetch, email alert, Leads inbox (status: new / contacted / qualified / won / lost, notes, call/email links), manual "sync leads" backfill | Meta app (guide A–F), DNS, SMTP |
| 2. Performance (built 2026-11-08) | Hourly sync; overview (spend vs $150 cap, leads, cost per lead, today vs yesterday), per-ad and per-day tables/charts, delivery + review status, alerts (rejected ad, zero delivery, cap near) | Phase 1 |
| 3. AI desk (built 2026-11-08) | "Ask Claude" box with directions; task queue; `/ads-desk` skill on the Mac; reports (weekly review, research) rendered in the dashboard; proposals as structured cards | Phase 1 |
| 4. Controls (built 2026-11-08, with Home, Ads, ad previews, new ads, uploads) | Approve/decline proposals; pause/resume ad, budget change with guardrails; execution via Graph API (system user token); change log | Phases 2–3 |
| 5. Research + live improvement | Competitor research runs (Ads Library via MCP), creative improvement runs with Eugene's directions (Claude renders new variants locally, uploads drafts, proposal to publish), experiments tracker | Phase 4 |

## Stack (same conventions as EasyShip / iSpend)

Python 3.12 Flask + gunicorn, PostgreSQL 16, nginx container, vanilla JS/HTML/CSS (no build
step), Docker Compose, plain SQL migrations applied at startup, session-cookie auth,
Part of the EdgeBourne repo (`ads/`), deployed by its `install.sh` Update; `.env` holds infra secrets only.
Served by the EdgeBourne nginx container at `ads.<domain>`. Tests: unittest in the backend container + Playwright E2E.

## Open questions

1. SMTP provider for eugene@edgebourne.com (Google Workspace? other?).
2. One user (Eugene) for now, or also a teammate login?
3. How often should the Mac bridge check for tasks: only when Eugene runs it, every
   15 minutes via launchd while the Mac is on, or both?
