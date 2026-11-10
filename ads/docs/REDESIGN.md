# Redesign (Phase 8): new UI/UX + missing features

Approved by Eugene 2026-11-10. Resume from ROADMAP §2 Phase 8; this file is the full plan. The feature inventory (every current action → its new home) is appended below before P5.


## Context

The console at ads.edgebourne.com (code in `~/Desktop/Dev/edgebourne/ads`) now has every feature from the roadmap, and Audit 2 is fixed. But Eugene finds it hard to get around. The research found these causes:

- **Too many top-level items.** Admins see 10 (Today, Leads, Ads, Results, Reports, Tests, Claude, Research, Team, Settings), and 6 of them are behind "More" on phones.
- **No pages for campaigns or ad sets.** They exist only as section headers on Ads. The ad page's back link shows the campaign name but goes to the whole Ads list. Sub-pages boot as `page:"ads"`, so the title and the highlighted nav item are wrong.
- **Ads and Results overlap.** Both have their own ads table, with different columns, filters and status words ("On/Off" vs "Running/Paused").
- **Things are scattered.** The change log lives in 4 places and Claude proposals in 4.
- **Settings is one 14-section page.** Lead forms, tracking health and activity are buried in it.
- **Missing navigation basics:** global search, multi-select, keyboard shortcuts, and filters kept in the URL.

There are also feature gaps:

- **Ad review status isn't tracked.** Sync already fetches `effective_status`, `ad_review_feedback` and `issues_info`, but overwrites them on every upsert (`backend/insights.py:78-89`). No history is kept, so "approved" or "went live" can't be shown or alerted on.
- **No side-by-side compare** of selected ads.

**Eugene's decisions (2026-11-10):**
- New visual direction: compare mockups first, then pick one.
- Stay vanilla JS, multi-page, no build step.
- Status updates come from polling **and** Meta ad-account webhooks.
- Add bulk actions, saved views, a notification inbox, and period-over-period compare.
- Keep every existing feature.

## Target structure

**Sidebar: 7 items in 3 groups** (from 10). The account switcher, spending-limit card and user menu stay in the rail footer.

| Group | Item | Holds |
|---|---|---|
| Work | **Today** | today's numbers, "Needs attention" queue, Claude decisions waiting |
| Work | **Inbox** (new) | one feed: approvals, rejections, issues, learning limited, new leads, Claude proposals, alerts; read/unread |
| Work | **Leads** | unchanged; adds a filter by ad and by campaign |
| Run | **Ads** | one manager table with a Campaigns · Ad sets · Ads level switch, plus Lead forms tab, New ▾ menu |
| Run | **Insights** | tabs: Results · Compare · Tests · Reports |
| Run | **Claude** | tabs: Waiting · By ad · All runs · Research · Schedules |
| Admin | **Settings** | left sub-nav. This account: Meta, Targets, Alerts, Tracking, Lead stages, A/B, Replies, Activity. Console: Meta app, Team, Email/Telegram, Refresh, Accounts |

**Clients:** see Today, Leads, Ads (read-only) and Insights (Results + Reports).

**Phones:** bottom tabs are Today · Leads · Ads · Inbox (with badge) · More. The peek drawer opens as a bottom sheet, and the compare tray collapses to a pill.

**New pages**
- `campaign.html?id=`: tabs Overview, Ad sets, History.
- `adset.html?id=`: tabs Overview (with learning progress "23/50, restarted by edit on …"), Ads, History.
- `compare.html?ids=a,b,c&range=14&vs=prev`.
- `inbox.html`.

**Pages that merge:**
- Results keeps its charts and pacing. Its ads table goes; it links into the manager instead.
- Old URLs get 301s from nginx.
- One shared timeline component replaces the 4 change logs (Settings → Activity stays as the account-wide log).

**Navigation everywhere**
- **Breadcrumbs:** Ads › Campaign › Ad set › Ad.
- **⌘K / `/` palette:** pages, search across campaigns, ad sets, ads, leads and forms, actions, and `g a` / `g l` / `g i` jumps.
- **Peek drawer:** opens from any table row (summary, status, last 5 events, quick actions), mirrored to `?peek=`.
- **Shareable URLs:** filters, sort, columns, range, `vs`, and saved view all live in the query string.

## Phases

Each phase ships separately and follows ROADMAP §4: tests first, fake Meta, QA, commit, tick ROADMAP, update memory. P1–P4 don't depend on the look, so they can run while Eugene is choosing a mockup.

### P0. Design direction (first; gates P5+)
- Use the `impeccable` / `interface-design` / `ui-ux-pro-max` references and the earlier Superdesign hand-authored approach.
- Build **3 distinct directions** as static HTML mockups, served under the dev nginx with the real CSP and fonts. Each mockup covers four screens:
  - the Ads manager with selection, the bulk bar and the compare tray;
  - the ad page with the status timeline;
  - the Inbox;
  - the phone nav.
- Build a side-by-side comparison page, open it in Chrome, and capture light/dark shots via `qa/shots.cjs`.
- Eugene picks one. The output is `css/tokens.css` (both themes, spacing and type scale) and a component list in `ads/.superdesign/design-system.md`.
- Note from Eugene's taste so far: he picked Plus Jakarta Sans over Instrument/Plex/Figtree and dislikes Bricolage/Mulish. Font can be re-chosen per direction.

### P1. Status history (backend)
**Migration `023_status_history.sql`**
- `status_events` columns:
  - `account_id` (RLS like migration 020), `level`, `entity_id`, `campaign_id`
  - `field` (effective_status / configured_status / review / issues / learning / created), `old_value`, `new_value`
  - `source` (poll | webhook | console | backfill)
  - `at`, `meta_time`, `detail JSONB`, `change_id → meta_changes`
  - indexes `(entity_id, at DESC)` and `(account_id, at DESC)`
- New columns:
  - campaigns and adsets: `configured_status`, `issues`, `created_time`, `updated_time`
  - adsets: `learning JSONB` (the full `learning_stage_info`)
  - ads: `configured_status`, `updated_time`

**New `backend/status_history.py`**
- Pure functions:
  - `diff(level, before, after, now)` returns the list of events.
  - `transitions(...)` turns events into alert dicts.
  - `explained_by_console(event, recent_meta_changes)` sets source=console when a dashboard write from the last 10 minutes explains the change.
- DB function `record()`.

**Sync changes**
- Wire diff-then-upsert into `insights.sync_ads` (refactor to `upsert_ad(ad, source, prev)`), `sync.sync_adsets` and `sync.sync_campaigns`.
- Lock each row with `SELECT … FOR UPDATE` so a webhook, a poll and a manual Refresh can't race.
- The "mark DELETED" updates `RETURNING` the rows they changed, so those changes are recorded too.
- `ads_api.refresh_entity` passes `source='console'`.
- First sighting: an entity older than 48 h is recorded as `backfill`, with no alert.
- An ad whose status changes only because its parent was paused (`ADSET_PAUSED` / `CAMPAIGN_PAUSED`) is stored but not alerted.

**Graph fields to add**
- Ads: `configured_status`, `updated_time`.
- Ad sets and campaigns: `configured_status`, `issues_info`, `created_time`, `updated_time`, and the full `learning_stage_info{status,conversions,last_sig_edit_ts}`.
- If Meta refuses a field, fall back to the `AD_FIELDS_PLAIN` pattern.
- New `insights.sync_entities(level, ids, source)` refetches by id (`?ids=`, up to 50 per call).

**`dev/fake_meta.py` additions**
- `/fake/_review?ad=&to=IN_PROCESS|PENDING_REVIEW|ACTIVE|DISAPPROVED|WITH_ISSUES`, which fills in feedback and issues.
- `/fake/_learning?adset=&to=LEARNING|SUCCESS|FAIL`.
- Ads that are turned on start in IN_PROCESS.
- Support `?ids=` multi-get.

**UI in the current look:** the ad History tab shows the timeline right away.

**Tests:** `backend/tests/test_status_history_logic.py`.

### P2. Status alerts + Inbox
- **Shared alert path.** Pull `alerts.raise_found(found, now)` out of `alerts.run()` and call it from both `run()` and `status_history.record`.
- **New rules:**
  - `ad_approved`: ok level, auto-resolved.
  - `ad_issues`.
  - `learning_limited`.
  - `changed_outside`: changed in Ads Manager, not from the console.
  - An event-driven rejection reuses the `ad_rejected:{id}:{day}` dedupe key, so it is never doubled with the polled alert.
- **Wording:** the message quotes the `ad_review_feedback` reasons (per placement) and the `issues_info.error_summary`.
- **Delivery:** through `notify.reach` (email/push/Telegram, per person).
- **Fix:** `no_delivery` now counts 24 h from approval instead of from creation.
- **Inbox data:**
  - Migration: `alerts.kind` ('condition' | 'event'), plus an `alert_reads(user_id, alert_id, read_at)` table with RLS.
  - `GET /api/inbox?filter=unread|all&kind=` and `POST /api/inbox/read`.
  - `inbox_unread` is added to `GET /api/refresh`, which already polls each minute.
- **Tests:** extend `test_alerts_logic.py`.
- **QA:** step a fake ad IN_PROCESS → ACTIVE and → DISAPPROVED, then assert both the inbox items and the messages sent (`/push/_sent`).

### P3. Meta ad-account webhooks
- **Receiving (`webhooks.receive`)**
  - Branch on `object`. `page` keeps the leadgen path.
  - For `ad_account`, the pure `parse_ad_account(payload)` handles `effective_status` (field_changed, no new value, so the entity is refetched), `with_issues_ad_objects` (error code/summary), `in_process_ad_objects`, `creative_fatigue` and `ad_recommendations`.
  - Routing: a new `account_for_ad_account()`, like `account_for_page`. Unknown accounts are dropped and logged; they never fall back to account 1.
  - Events are stored in `webhook_events`, which gains `kind`, `object_id` and `field`.
  - Call `jobs.wake()`. The worker job `status_history.process_webhooks` groups events by object, makes one multi-id refetch, then runs `upsert(source='webhook')`.
- **Subscribing**
  - `POST /api/settings/meta/connect-account` makes two calls: the app-level `/{app_id}/subscriptions` (object `ad_account`) and `act_<id>/subscribed_apps`.
  - Settings switch "Instant status updates from Meta", showing when the last event arrived.
  - The subscribe call is logged in `meta_changes`.
  - Polling stays on as the safety net.
- **Fake Meta:** `/fake/_webhook?field=&object=` posts a signed payload, and the subscription endpoints are faked too.
- **Docs:** new section I in `docs/META-APP-SETUP.md`, the step Eugene does in the Meta app.
- **Tests:** `test_webhooks_logic.py`.

### P4. APIs for the new screens
- **`backend/ranges.py`** (pure): `window(key, today, from, to)` and `previous(start, end)`. It replaces `ads_api.RANGES`, `performance_api.periods` and `insights_api.time_params`. Ranges: 7 | 14 | 30 | mtd | lastmonth | custom.
- **Period compare:** `vs=prev` on `/api/ads`, `/api/performance` and campaign/ad set detail. It re-runs `ads_api._metrics` over the previous window and attaches `prev`.
- **Compare:** `GET /api/ads/compare?ids=&level=&range=&vs=` for 2–6 items, scoped with `_scope`.
  - Returns totals, a daily series per item, qualified leads, status and creative.
  - Pure `compare.shape()` names a winner only when spend ≥ 2× target CPL and there are ≥ 3 leads. Otherwise it says "not enough data" (hard rule 7).
- **Entities:**
  - Refactor `tree()` into `tree_data(..., campaign_id, adset_id)`.
  - New `entities_api.py`: `GET /api/campaigns/<id>`, `/api/adsets/<id>` (both with `crumbs`), and `/api/<level>/<id>/timeline`.
  - Pure `timeline.merge()` combines status_events, meta_changes, decided proposals and leads.
- **Search:** `GET /api/search?q=` across campaigns, ad sets, ads, leads and forms, scoped to the user, 20 results.
- **Saved views:** migration `024_views.sql` adds `saved_views(account_id RLS, user_id, page, name, query, shared, position)`. CRUD at `/api/views`.
- **Bulk:** pure `bulk.py`.
  - `POST /api/ads/bulk/preview` handles status | budget_set | budget_pct | archive.
    - It reads live values from Meta.
    - Each line shows current → new in dollars and flags: above the ceiling, more than +20%, turn-on problem, the ad is still on, out of scope.
    - It returns totals and a 5-minute HMAC `plan_token`.
  - `POST /bulk/apply`:
    - Re-reads every item and skips anything that changed since the preview.
    - Applies changes one by one through the existing `apply_status` / `apply_budget`.
    - Each write is logged in `meta_changes` with a new `bulk_id`, and the result comes back per item.
  - There is no bulk delete.
- **Tests:** `test_ranges_logic`, `test_compare_logic`, `test_bulk_logic`, `test_timeline_logic`, `test_search_logic`.

### P5. New shell + CSS (needs P0)
- **CSS:** split `css/app.css` (1,475 lines) into `tokens.css` (from P0), `base.css`, `shell.css`, `components.css` and `pages/*.css`. Use `<link>` tags rather than `@import`, with `?v=` cache-busting. Bump the `sw.js` cache name and offline list.
- **New modules in `frontend/js/`:**
  - `shell.js`: one nav config (groups, role filter, badges), breadcrumbs, bell, phone tabs. `ui.js` re-exports `boot` from it.
  - `urlstate.js`: read/write/onChange, plus a one-time migration of the `ebads-adsview` / `ebads-results` localStorage keys.
  - `palette.js`: the ⌘K palette.
  - `status.js`: one status map, `pill(entity)` and `timeline(items)`. It replaces `format.STATUS` and the copies in `performance.js` and `new-campaign.js`, and covers PREAPPROVED, IN_PROCESS, PENDING_REVIEW, learning and learning limited.
- **Page ids:** every page gets its own `page` id plus a `section` for highlighting, which fixes the wrong titles and highlights on ad, forms and the new-* pages.
- **Naming:** no "ad" token in file or class names (EasyList also blocks file paths like `/ads.js`). Prefixes are `cr-`, `aset-`, `camp-`, `tbl-`, `pk-`.

### P6. Ads manager rebuild
- `table.js`: the shared table.
  - Column registry with sets perf / delivery / video / review.
  - Sort, sticky header and first column.
  - Checkbox selection with shift-ranges; `j/k/x` keys.
  - Expandable campaign › ad set › ad rows.
  - `data-w` widths (CSP).
- `views.js`: built-in views (On, Needs attention, In review, Learning, Spent no leads, Tests, which closes I9) plus the user's own.
- `bulkbar.js`: preview → `confirmDialog` with every line and the totals; the confirm button repeats the total.
- `peek.js`: the peek drawer.
- `tray.js`: the compare tray.
- Campaign and ad set pages. Cards view kept as an option.

### P7. Remaining screens
- Compare page:
  - Creative thumbnails as column headers.
  - Metric rows with a best-in-row mark (only when the sample is met).
  - Overlaid daily line chart in `charts.js` (follow the dataviz skill).
  - Δ vs the previous period.
- Inbox page.
- Today becomes a queue: attention, approvals, Claude decisions, new leads.
- Insights tabs, Claude tabs, Settings sub-nav (Team moves in).
- Leads filter by ad and campaign.
- nginx 301s for the retired URLs.
- Wire period compare into every chart and figure (Δ arrows).

### P8. Finish
- Full QA pass, an ad-blocker check (a browser with uBlock), and phone 390 px light/dark shots.
- Log in ROADMAP §2 (new "Phase 8: Redesign" block) and §6, and update memory.
- Real-Meta checks list: webhook field names and payloads, `configured_status` / `issues_info` / `learning_stage_info` on v24, the System User calling `subscribed_apps`, PENDING_REVIEW vs IN_PROCESS.

## Keep every feature

- Before P5, write a feature inventory in `ads/docs/REDESIGN.md`: every action on every current page → its new home.
- QA `flows.cjs` (230 checks) is updated, not dropped. Each old check maps to the new location, and the inventory is ticked at P8.

## Verification

- **Unit tests:**
  ```
  cd ~/Desktop/Dev/edgebourne && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
  docker exec -e WORKERS_ENABLED=0 edgebourne-ads-backend python -m unittest discover -s tests -v
  ```
- **E2E:** `ads/qa/run.sh` (fresh fake Meta → `flows.cjs`). New flows cover:
  - review stepping, with alert + inbox + timeline;
  - a signed webhook leading to a refetch and a timeline event;
  - compare of 3 ads with `vs=prev`;
  - bulk off and budget +30%: blocked until accepted, Cancel changes nothing, every write in meta_changes;
  - a saved view round-tripping through the URL;
  - ⌘K search;
  - nav highlight and breadcrumbs on every page;
  - the leak test `dev/qa_leaks.py` extended to status_events, saved_views and alert_reads.
- **Visual:** `qa/shots.cjs` of every page, light/dark, desktop/390 px, opened in Chrome for Eugene.
- **Live, with Eugene approving each write:**
  - Turn on webhooks.
  - Submit a test ad (PAUSED → he approves turning it on) and watch In review → Approved arrive in the Inbox.
  - Run Update on the VPS after each pushed phase.

## Critical files

- **Backend:** `ads/backend/{insights.py, sync.py, alerts.py, webhooks.py, ads_api.py, performance_api.py, jobs.py, notify.py, money_rules.py}`; new `status_history.py`, `ranges.py`, `compare.py`, `bulk.py`, `timeline.py`, `entities_api.py`, migrations 023–025.
- **Frontend:** `ads/frontend/js/{ui.js, format.js, ads.js, performance.js, home.js, ad.js, charts.js, controls.js}`, `css/app.css` → split; new `shell.js, urlstate.js, table.js, views.js, palette.js, peek.js, tray.js, bulkbar.js, status.js`, new pages `campaign/adset/compare/inbox.html`.
- **Dev:** `ads/dev/fake_meta.py`, `ads/qa/flows.cjs`, `ads/qa/shots.cjs`, `ads/nginx/ads.conf`, `ads/docs/{ROADMAP.md, META-APP-SETUP.md}`.

---

## Feature inventory (written before 8.5; tick at 8.8)

Every action on every current page and where it lives after the redesign. Nothing is dropped.

| Now | Action | New home |
|---|---|---|
| Today | Needs attention list, call/email lead, Money card, Ads strip, Claude card, Changes, Meta's advice + benchmarks, Apply advice, Ask Claude, New ad | Today (queue: attention, approvals, Claude decisions, leads; Money + advice kept; Changes → Inbox) [ ] |
| Leads | Stage filter, search, show test leads, list/detail, call, email reply + templates, stage, owner, notes, history | Leads (same) + filter by ad / campaign [ ] |
| Ads | Range, filter on/off/attention, archived, sort, cards/table, on/off + budget at 3 levels, New ad set, Lead forms, New campaign, New ad | Ads manager table (levels, views, bulk, peek) + cards option; New ▾ menu; Lead forms tab [ ] |
| Ad | Back link, tabs Overview/Polish/Audience/Video/Comments/History, preview, Claude suggests, results, words, where it runs, tags, Meta's automatic changes, leads, toggle, duplicate, new from this, polish, archive, delete, comments reply/hide, approve proposals | Ad page (breadcrumbs, same tabs, History = merged timeline, Compare button) [ ] |
| Results | Range, campaign picker, alerts, pacing + monthly target, figures, charts + day table, ads table, by idea, who and where, what changed on Meta | Insights → Results (ads table → link to manager with range/vs) [ ] |
| Reports | Week/month, shared view, PDF, share link | Insights → Reports [ ] |
| Tests | Running/Finished/All, arms, verdict, A/B on Meta, new/edit/finish/reopen/run/end | Insights → Tests [ ] |
| Claude | Mac status, Ask composer, Waiting / By ad / All runs / Schedules, approve/decline, cancel/re-run, Mac key | Claude (tabs + Research) [ ] |
| Research | Ad Library search, Ask Claude to research, swipe file, watched Pages, research runs | Claude → Research [ ] |
| Lead forms | Builder, list, copy, use in a new ad | Ads → Lead forms tab [ ] |
| New ad / New ad set / New campaign | Wizards | Same pages, reached from New ▾ and from campaign/ad set pages [ ] |
| Team | Members, roles, campaigns, passwords | Settings → Team [ ] |
| Settings | 14 sections | Settings with a left sub-nav (This account / Console), + Instant status updates [ ] |
| Account | Password, appearance, lead alerts, Telegram, device install, push | Account menu at the bottom of the rail [ ] |
| Frame | Badges, account switcher, refresh + auto catch-up, spending-limit card, system banners, theme, sign out | Signal shell (+ Inbox badge, ⌘K, breadcrumbs) [ ] |
| New | Compare, Inbox, campaign page, ad set page, saved views, bulk bar, peek, period compare | 8.6 / 8.7 [ ] |
