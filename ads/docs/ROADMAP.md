# Ads console roadmap: from good dashboard to state of the art

Written 2026-11-09. This file is the single source for finishing the Ads console. A fresh
Claude session must be able to resume from this file alone, so it carries the context, the
rules, the plan and the progress log. Keep it current: tick boxes and append to the log at
the end of every working session.

---

## 0. How to resume (read this first)

1. Read this whole file. Then read, in this order, only what the current step needs:
   - `ads/README.md` (how the console runs, pages, conventions)
   - `ads/docs/PLAN.md` (original architecture and safety model)
   - `~/Desktop/Dev/meta-ads/CLAUDE.md` (hard rules for anything that touches Meta)
   - memory: `~/.claude/projects/-Users-ruolez-Desktop-Dev-meta-ads/memory/edgebourne-ads-console.md`
2. Check the state: `cd ~/Desktop/Dev/edgebourne && git log --oneline -10 && git status`.
   Compare with the **Progress log** (section 6). If git has commits the log doesn't mention,
   add them to the log before doing anything else.
3. Check **Open issues** in Status first: Eugene asked (2026-11-09) to fix some of them before
   new phases. Then find the first unticked step in **Status** (section 2). Steps marked **[Eugene]** need him.
   If the next step is blocked on him, say exactly what he has to do, then move on to the
   next step that isn't blocked.
4. Before building a step: if it has an **Open decision**, ask Eugene (one AskUserQuestion
   with the options listed there) unless the log already records his answer.
5. Build it the way section 4 says (tests first, fake Meta, QA, commit). Then tick the box,
   add a log line, update the memory file, and tell Eugene in plain words what changed and
   what he has to do on the server (usually: run Update).

The working directory for Claude Code sessions is usually `~/Desktop/Dev/meta-ads` (the ads
workspace with the Meta MCP login). The console code lives in `~/Desktop/Dev/edgebourne/ads`.

---

## 1. Context in one page

**What it is.** `https://ads.edgebourne.com`, Eugene's private console for the Edge Bourne
Meta ads. It has:
- leads inbox: webhook → email alert → stages new / contacted / qualified / won / lost
- performance pages
- ads manager: cards, on/off switches, budgets, real Meta previews, duplicate, new ad with upload
- ad page tabs: Overview, Polish, Audience, Video, Comments, History
- Research page
- AI Desk: Eugene types directions; Claude Code on his Mac does the work and posts reports and proposals; he approves

**Built so far** (all on `main` of github.com/ruolez/edgebourne):

| Commit | What |
|---|---|
| b62baaa | console added to the EdgeBourne repo |
| e1f6027 | lead alerts sent through the website's mail settings |
| 19aeea5 | installer: nginx recreated after the backends on update |
| 4dde6e8 | AI Desk and Mac bridge |
| 3a9d49e | Ads manager, previews, controls, new ads, Home |
| 544c4eb | polish passes, new versions, Audience/Video/Comments/History tabs, breakdowns, Meta change history |
| c05e30a | "Seal & ledger" redesign, Refresh button on every screen |
| 65ae275 | tab labels centred, Leads "Only mine" filter removed |

**The live ad account** (IDs are not secrets; tokens are and never go in chat or files):

| Item | Value |
|---|---|
| Ad account | 1025971549903293 (America/Los_Angeles, USD) |
| Page | Edge Bourne Consulting, 61596354777753 |
| Business portfolio | 2289619248494805 |
| Campaign | 120252638288040312 "Edge Bourne - Free intro call - Leads": live since 2026-11-08, $20/day, account spending cap $150 |
| Ad set | 120252672227950312 |
| Ads | N1–N5, videos |
| Instant Form | 1132280359202136 |
| Dataset (pixel) | `edgebourne.com`, 1821497329119793; the website sends Lead via Pixel + Conversions API (`backend/meta_capi.py`, `META_PIXEL_ID`, `META_CAPI_TOKEN` in the site `.env`) |
| Target | $60 per qualified lead |

**Where things are.**
- Backend (Flask, one module per area):
  - `ads/backend/`: `ads_api.py`, `desk_api.py`, `insights.py`, `insights_api.py`, `polish.py`, `leads.py`, `leads_api.py`, `webhooks.py`, `jobs.py` (background loop, advisory lock), `sync.py`, `meta_client.py`, `mailer.py`, `site_mail.py`, `settings_store.py` (encrypted settings), `auth.py`
  - Migrations `migrations/00N_*.sql` run at startup; the next one is `006_…`
- Frontend: `ads/frontend/`, vanilla JS, no build step. Shared modules in `js/`:
  - `format.js`, `charts.js`, `controls.js`, `tasks.js`, `ui.js`, `markdown.js`
- Mac bridge: `ads/bridge/`
  - `bridge.py` (LaunchAgent `com.edgebourne.ads-desk`, long-polls the server and runs `claude -p "/ads-desk run <id>"`)
  - `desk` (CLI helper)
  - `skill/SKILL.md`
  - Installed copies live in `~/.claude/skills/ads-desk/`. Re-run `ads/bridge/install.sh` after changing them.
- Dev tools:
  - `ads/dev/fake_meta.py`: fake Graph API with the real N1–N5 IDs (dev overlay service `fake-meta`)
  - `ads/qa/flows.cjs`: end-to-end flows
  - `ads/qa/shots.cjs`: screenshots, light/dark, desktop/phone

**Hard rules** (from meta-ads/CLAUDE.md; they apply to every feature here):
1. No money moves without Eugene's explicit yes. In the console that means a confirm dialog
   showing current → new in dollars, or an approved proposal. AI never acts alone. This covers:
   - publish or activate
   - budgets and bids
   - status, schedule and targeting
2. Anything new is created **PAUSED**/off.
3. Never delete on Meta; pause instead.
4. Budgets are in cents in the API; show dollars.
5. Judge only complete days with enough data (spend ≥ 2× target CPA and ≥ 3 results).
6. Log every write: `meta_changes` table in the console; `reports/log.md` for Claude's own writes.
7. Secrets go only in Settings (stored encrypted) or the Keychain, never in `.env` for app keys,
   never in chat. Claude never types tokens or passwords into fields.

---

## 2. Status

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · **[Eugene]** = needs him

### Phase 0: Prove what's built (do first)
- [x] 0.1 **[Eugene]** Run Update on the server (installer one-liner → option 2) so 544c4eb is live.
- [x] 0.2 **[Eugene]** `claude setup-token` on the Mac, then store it for the bridge (Keychain service `ads-desk-claude`, see `ads/bridge/install.sh`). Deadline: before 2026-11-11.
- [~] 0.3 Real-Meta verification pass (12/13 pass; h needs Eugene's token with `pages_read_user_content`) (checklist in section 3, Phase 0), fixing what breaks.
- [x] 0.4 First real "Make a new version" render run, watched end to end (task 3 rendered + uploaded in 9 min; proposal 5 approved → ad 120252690325970312 "N1 · v2", PAUSED).

### Open issues (Eugene, 2026-11-09: fix a few of these before going forward)
Found while proving Phase 0 and building 1.1. Pick with Eugene; tick here when fixed.
- [ ] I1 **[Eugene]** Comments tab (0.3 h): the token lacks `pages_read_user_content`. Regenerate the system user token with it and paste it in Settings → Meta; then recheck h.
- [x] I2 (fixed: placeholder stays until Meta's frame has loaded, "open in a new tab" after 12 s, note on ads still in review; same loader on the Claude page) Ad page has no loading state: Meta previews take 2–8 s and the box stays blank (a fresh ad still IN_PROCESS shows an empty white preview).
- [x] I3 (fixed: "Show test leads" checkbox, rows marked Test) Test leads are hidden from the Leads inbox with no way to see them (API has `tests=1`); add a toggle.
- [~] I4 A render proposal carries one video, so N1 · v2's 9:16 upload (2015174525716803) isn't used. Needs placement asset customization (4:5 for feeds, 9:16 for Stories/Reels) in the creative builder. Built 2026-11-10 with 5.4: `placements.py` + `ads_api.add_vertical` (update proposals `payload.update_ad` + `vertical.video_id`). Unverified against real Meta: the raw `asset_feed_spec` shape for a lead-form ad (form in `call_to_actions`); the read-back check refuses a copy without the form, so a wrong guess never reaches the running ad.
- [x] I5 (fixed: the line re-checks itself at 3, 6, 9, 12 s while anything is pending) Lead page "Meta has …" line (1.1) shows "on its way" right after a stage click and only updates when the lead is reopened; re-fetch a few seconds after the change.
- [x] I6 (decided: keep queueing, Meta takes 7 days back; Settings now says "N saved, sent once you turn this on" instead of "waiting") Stage events queue while the 1.1 switch is off and show as "waiting"; decide: queue only when on, or keep (Meta takes 7 days back, older ones are skipped).
- [ ] I7 Creative files: local `creatives/2026-11-07-new5/out/N1-9x16*` still carry the banned "Free workflow review" wording (polish #2 report). Not in any live ad; rebuild or delete before reuse.
- [ ] I8 **[Eugene]** Money: the $150 manual account cap ($35.31 used on 2026-11-09) stops all ads around Nov 15. Raise it or let it stop, his call.
- [x] I10 Archive and delete ads from the console (Eugene asked for both, 2026-11-09): ad page buttons, admin only, only when the ad is off; delete needs the ad's name typed; archived ads hide on the Ads page behind "Show archived"; every one lands in meta_changes. Meta: archived → only deleted, never back on; both keep their numbers. Sync no longer turns an archived ad into "deleted" when Meta's list leaves it out.
- [~] I11 Claude page was hard to read (Eugene, 2026-11-09: mixed, repeating, unclear what's for which ad or in what state; wanted previews). Rebuilt: tabs Waiting for you (pending decisions grouped by ad, each with Meta's preview via `act/generatepreviews`, old → new changes, one-line why, Create (off) / Edit / Decline) · By ad (ad families: an ad plus every ad made from it, runs as a timeline with each idea's outcome and a link to the ad it made) · All runs (reports and scorecards folded). Ask Claude is a button. `desk_view.py` (pure, tested) + `board.js`; render runs now store `from_proposal`. Built and tested locally; live check of the preview after push.
- [x] I12 Data didn't update by itself (Eugene, 2026-11-09: "I don't want to always click Refresh"). Settings → Automatic refresh (every 5 / 10 / 15 / 30 min / hour, default 15): the worker runs the Refresh pass on that interval (counted from the last pull by anyone; a failed try waits 5 min). Open pages check every minute and when they come back into view, and reload their data when the server has newer data, unless someone is typing or a dialog is open. The Refresh button's tooltip shows the interval.
- [ ] I9 Paused ads keep piling up (4 test ads from 0.3 + N1 · v2, never deleted). Consider a "Tests" filter or a naming rule so the Ads page stays readable.

### Audit 2 (2026-11-10): gaps found after Phase 7
Four parallel reviews (security/isolation, Meta writes and money, worker/ops/deploy, product/UX), read-only, dev only. "verified" = reproduced or queried; the rest traced in code. Fix in this order; tick here when fixed.

**Money and data first**
- [x] A1 (fixed: `money_rules.parse_budget_text` reads the amount after “to”/“→” and refuses unclear text; `payload.proposed_cents` wins; `GET /api/proposals/<id>/check` reads Meta's live budget; the dialog shows live → new in dollars; approve must echo both and +20% needs a knowing yes; ceiling) Budget proposals: `parse_dollars` takes the first number in Claude's text ("+20% to $24/day" → $20.00, "Raise 2x to $40" → $2.00, verified); the dialog shows Claude's text, not the amount; no +20% cap; no fresh read of the live budget (`ads_api.py:46,68`, `tasks.js:152`, `board.js:98`). Fix: structured `proposed_cents`, server-computed current → new from a fresh read, cap.
- [x] A2 (fixed: proposals claimed `applying` (migration 022) before Meta; wizard `client_key` + per-build advisory lock + adopts a same-name paused campaign/ad set after a timeout; A/B study claimed first; a copy keeps its id when naming fails; comment replies locked + 2-minute repeat guard; Approve disabled while it runs) Double submits and timeouts: Approve isn't claimed atomically (double click = two ads, `ads_api.py:679`); `POST /api/builds` always inserts; study create check-then-create; a network timeout after Meta applied a write leaves no `meta_changes` row and loses the build's made ids, so the retry makes a second campaign (`meta_client.py:37`, `builds_api.py:93`). Fix: claim rows (`status='applying'`), idempotency, wrap `requests` errors as "outcome unknown" and look up before retrying.
- [x] A3 (fixed: `money_rules.recommendation_amount` trusts only whole cents ≥ 100; unclear → no Apply button; apply needs `confirm_to`, the ceiling, and reads the budget back (a different result is logged as `recommendation_check`)) Recommendation apply fails open when `additional_budget` isn't int cents: no amount shown, `accept_big` skipped (`advice.py:67`, verified by the reviewer). Fix: refuse unless the amount parses; confirm the new amount; read back.
- [x] A4 (fixed: `account_info.today()/yesterday()` in the account's time zone everywhere; lead days bucketed `AT TIME ZONE`) "Yesterday" is the UTC date: from 4 PM LA, Results / Ads / By idea / Claude's snapshot include today's partial day (`date.today()` in performance_api, ads_api, insights_api, concepts_api, insights; container TZ is UTC, verified). Fix: one account-day helper.
- [x] A5 (fixed: `meta_client._send` turns network errors into `MetaError` (writes marked `unknown`, no URL/token in the message or traceback); plain words for 190/4/17/32/613/80004; 5-minute per-account cooldown on rate limits; `meta_token_error` banner; CRM events carry `event_id`; the worker's lead pass is inside its own try) Network errors from Meta aren't `MetaError`: pages show "Request failed (500)" after 20 s, a timeout skips the worker's lead pass, the URL with `access_token` can land in logs, CRM events resend without `event_id` (Meta may double count). Codes 190/4/17/613/80004 have no backoff or plain words. Fix: wrap in `_call`/`paged`, token in a header, cooldown, "reconnect Meta" alert on 190.
- [x] A6 (fixed: `leads.alert_phones` sends Telegram, else push (people with lead alerts on); the email still goes) New leads never go by push: `leads.alert_phones` queues Telegram only (verified), so installing the app gives no lead pushes. Fix: lead alerts through `notify.reach` (push) plus the email.
- [x] A7 (fixed: `db.APP_ROLE_SQL` recreates `ebads_app` + grants on every boot; restore steps in README; nightly backup keeps a dump only when it succeeded (`.part` + `gzip -t`), exits non-zero on failure, optional `BACKUP_COPY_TO` off-server copy) Restore: `pg_dump` has no roles, so a restored DB on a new server never recreates `ebads_app` and every request fails; no documented restore; nightly backup has no pipefail (a failed dump rotates out good ones); backups only on the same disk. Fix: create role + grants on every boot, document restore, check dump size.
- [x] A8 (fixed: gunicorn `max_requests = 0`; notifications and lead replies claimed `sending` before they go (left over → failed, never resent); manual replies inserted as `sending`; client report emails per person, retried hourly, caught up on later days) Double sends: gunicorn `max_requests=1000` with one worker recycles every few hours (bridge long-poll alone ~144 req/h) mid-pass; notify/replies send then mark sent, so a kill between can email a lead twice; client report email marks sent before sending and never retries.

**Before the first client account**
- [x] A9 (fixed: Settings split into This account / Whole console; Meta app keys, email, Telegram, refresh only by the owner from Edge Bourne's Settings (server refuses elsewhere)) Console-wide settings (Meta app secret, verify token, app id, SMTP, auto refresh) are edited from every account's Settings; pasting a client's app secret breaks webhooks for all. Fix: a "Console-wide" section on account 1 only, server refuses elsewhere.
- [x] A10 (fixed: client forms need their own privacy page; automatic replies never fall back to Eugene outside account 1; the copied template takes the business name; Research quick searches only on Edge Bourne; neutral Leads empty text) Edge Bourne leaks into client accounts: lead forms default to edgebourne.com/privacy, the copied reply template says "from Edge Bourne", the auto-reply sender falls back to Eugene, Research quick searches and Leads empty text are Edge Bourne's.
- [x] A11 (fixed: time zone from Meta per account (`account_info`); money formatted in the account's currency; currencies without cents refused on connect and on sync) Time zone and currency are global (`config.ACCOUNT_TZ`, `format.js` USD, spend ×100 vs Meta minor units): a client in another zone gets wrong ad set start times, digests, report periods; a no-cents currency is 100× off. Fix: store Meta's `timezone_name`, currency and offset per account.
- [x] A12 (fixed: “Admin of this account” (admin with `users.account_id`) vs the owner; `owner_required` for accounts, console settings, Mac key; account admins can't touch owners) Every admin is admin of every account (client leads, Mac key, SMTP, Eugene's password). Fix: an account-limited admin role if a client ever needs write access.
- [x] A13 (fixed: `notify.link` adds `?acct=`; the page switches to that account first; phone top bar names the account) Notification links have no account: with another account chosen, a lead alert opens "Can't open this lead"; the phone top bar doesn't name the account. Fix: `?acct=` on every link, switch on arrival.
- [x] A14 (fixed: Today checks the account's own ad account; Settings says when the token is Edge Bourne's) An unconnected account says "Nothing needs you right now" and Settings shows the token "Saved" (inherited System User token). Fix: check the account's own ad account id.
- [x] A15 (fixed: clients don't see Polish / Improve / New ad / Owner / Refresh; “Client” label; Settings → Clients and reports switch lets clients move stages and add notes; closed accounts lose access; “Stop all shared links” (`report_link_epoch`); shared and client reports don't list Claude's pending ideas) Client view: sees Polish / "Make a new version" / "Improve the words", the full New ad form, an Owner select, Refresh; sidebar says "Team member"; can't move stages, so client funnels stay at zero; archived accounts keep client access and share links can't be revoked; shared reports list pending proposal titles.
- [x] A16 (fixed: `resync_later` copies the context; each request starts at account 1 before choosing; `campaign_members` under RLS (migration 022); lead owner limited to the campaign's people; `/api/media/video/<id>` digits only and in this account's library; one account per ad account/Page; rolled-back queries re-point the connection) Account context bugs: `resync_later` threads run in account 1 (verified); pooled gunicorn threads keep the previous request's account for session-less paths; `campaign_members` has no account (cross-account assignments, lead emails); lead owner can be any user; `/api/media/video/<id>` takes any Graph id (`%3F` adds params). Fix: copy contextvars, reset per request, digits-only + ownership checks.
- [x] A17 (fixed: wizard, New ad set and New ad can start from nothing (Meta's lead-form defaults, the account's Page, the chosen form, own media)) New campaign / ad set / ad all copy an existing synced one, so a fresh client account can't launch from the console (4.3 planned a from-scratch wizard).

**Polish and visibility**
- [x] A18 (fixed: grid/flex children `min-width: 0`, wide strips and tables scroll in place, scroll boxes contain positioned children; QA checks 10 pages at 390px) Phone width: the ad page is 1087 px wide at 390 (placement buttons, tab strip), also Reports "Why" table (clients' share link), Team, Today. QA screenshots crop it. Fix: scrolling strips/tables + a QA check on `scrollWidth`.
- [x] A19 (fixed: Settings → Targets (cost per qualified lead, cost per lead, highest daily budget, monthly shown); the alert falls back to the qualified-lead target; By idea / Tests keep their own average without a lead target) Targets live in four places; the Alerts cost-per-lead target is empty, so "Leads cost too much" never fires and By idea / Tests read the empty one. Fix: one target per account.
- [x] A20 (fixed: turning on shows the fresh daily spend and the server requires it (`confirm_daily_cents`); one ceiling (`max_daily_budget_cents`, default $100) for budget edits, proposals, advice, new ad sets, the wizard and A/B tests; +20% needs `accept_big`; wizard Publish checks Meta's live budget) Turning an ad/ad set/campaign on never shows dollars a day; approving an "on" proposal goes straight to ACTIVE; no server budget ceiling (`set_budget` any amount ≥ $1 from an assigned member, ad set create no max, wizard 3× rule off when nothing runs, A/B 2× off without a campaign budget).
- [x] A21 (fixed: Today → Changes words per action) Today → Changes calls most actions "Created" (replies, hides, archive, delete, advice, enhancements, tests, forms).
- [x] A22 (fixed: worker heartbeat `worker_last_pass`, `/api/health` 503 when stale (10-minute grace after a start), admin banners (worker, Meta token, Mac helper, Claude sign-in); desk < 1.6 refused (426) when there are several accounts; daily pruning) Nobody would know if the worker died (`/api/health` doesn't check it, timers in memory); bridge version not enforced (desk < 1.6 answers every account with account 1); expired Claude token still shows the bridge online; nothing is ever pruned.
- [x] A23 (fixed: Claude wording; Settings section links; 44 px touch targets; labelled ages; Accounts panel (rename, close, reopen; unique names); no-creative ads; Claude tabs scroll; lead's ad links; Ads Manager links carry `act=`; wizard start/end dates) Small things: "Desk" vs "Claude" wording on Today/Activity; Settings is one ~5,900 px page mixing shared and per-account panels; small tap targets (sort headers, Research links 20 px); unlabeled age fields in New campaign; no rename/archive account in the UI and duplicate names allowed; ad with no creative → 500 in "Meta's automatic changes"; Claude page's Schedules tab cut off on phones; lead page Ad isn't a link; Ads Manager links lack `act=`; New ad set has no schedule field.
- [x] A24 (fixed: 16 new unit tests (meta_client network/token/cooldown, links, report emails, clock, Mac helper, advice, money rules, worker health, scratch builds); leak test adds members, account admins, writes with the other account's ids, threads, assignments, cross-site; 22 new QA checks (230 total)) Tests: nothing imports `db`, `jobs`, `meta_client`, `webhooks`, `mailer`, `auth`; the leak test is GET-only (no members, writes, worker, notifications, threads).
- [x] A25 (listed below under “Live checks still owed”: none can run without Eugene's yes per write) Never run against real Meta (add to 0.3-style live checks, each with Eugene's yes): budget change, campaign create, ad set create, wizard Publish, archive/delete, lead form create, comment reply/hide, CRM events, `creative_test_config.daily_budget`, plus the ones already noted (studies, recommendation apply, creative swap).

**Live checks still owed (A25)**, each one with Eugene's yes, on a copy or a paused object like 0.3: budget change; campaign create; ad set create; wizard Publish; archive and delete; lead form create; comment reply and hide (needs I1); CRM events to the dataset (1.1); `creative_test_config.daily_budget` in cents; ad studies; recommendation apply (`additional_budget` units); creative swap on a live ad; a new ad from nothing (Page + form, no template); the 190 / rate-limit wording on a real error; a real organic form lead (`is_organic`, no `ad_id`) and a Lead Ads Testing Tool lead (its `is_organic` value; still filed as a test lead).

Sound: RLS on all 23 tables (app role not superuser), client read-only gate, webhook signature, share-link HMAC, encrypted secrets, escaping/CSP, every create PAUSED, the only delete path guarded, sync never marks DELETED on a failed list, migrations in one transaction with backup before Update.

### Phase 1: Close the loop with Meta
- [~] 1.1 Lead stages sent to Meta (Conversions API for CRM) (built and tested locally; Eugene: META-APP-SETUP part H, then a live test event)
- [~] 1.2 Instant alert to Eugene's phone for every new lead: **Telegram** (Eugene chose it 2026-11-09). Built: `telegram.py` (bot token in Settings → Telegram, people link from Your account with a one-time `t.me/<bot>?start=` code, getUpdates polling, /stop unlinks), `notify.py` queue (migration 007, retries 1/5/15 min, dedupe), lead alert to everyone who gets the lead email. Dev: fake Telegram in `dev/fake_meta.py` (token `123456:FAKE-token`). Eugene: create the bot with @BotFather, paste the token, connect from Your account, send a test
- [~] 1.3 Replies to leads by email. Eugene (2026-11-09): manual first, automatic as an option. Built: Settings → Lead replies (templates with placeholders, live preview, booking link, "send by itself" switch, default off, confirm to turn on, signed by the admin who turned it on), lead page "Email them" composer (template, edit, Move to Contacted, Reply-To = sender), Emails list + history, `replies.py` + migration 008, auto reply queued on a new real lead with an email. Draft template wording waits for Eugene's OK; add his booking link if he has one
- [~] 1.4 Untouched-lead reminders and response report. Built: `reminders.py` (5 min → owner or the lead's people, 1 h → admins, 8 AM America/Los_Angeles list of every lead still waiting; untouched = still New, no stage change, no email from the lead page, no note; test leads and leads over 24 h never; Telegram when linked, else email; each once), Your account switch (migration 009), Leads header "Last 30 days: half heard back within … · N of M within 5 min · K not contacted". Live check after Eugene links Telegram

### Phase 2: Works without being asked
- [~] 2.1 Desk schedules. Built: `schedules.py` + migration 010 (4 presets, all off: Daily health 8:30, Optimizer review every 3 days 9:00, Monday summary 8:00, Monthly audit the 1st 9:00, America/Los_Angeles, DST-safe), the worker files an ordinary Desk task (same read-only bridge tools; skipped, not piled, while the previous run still waits), Claude page → Schedules tab (switch, change time, Run it now), every finished Desk run messages its people (admins for scheduled ones) with the summary; skill playbook "Scheduled runs" (installed). Eugene: switch on the ones he wants
- [~] 2.2 Alerts engine. Built: `alerts.py` (pure `evaluate(snapshot, rules, today)`, 10 rules: rejected ad, no delivery after 24 h, fatigue (7-day frequency > 3 with clicks -20% and cost per 1,000 +20% vs the ad's first week; frequency from summed daily reach, a low estimate), day spend > 1.75× budget (Today only), week > 7×, spending limit ≥ 80%, cost per lead > 1.3× target (off until Eugene sets a per-lead target), no leads 3 days while spending, Meta leads not reaching the inbox, Meta silent > 3 h), migration 011 (`alerts`, `users.notify_alerts`), once per thing per day, clears by itself, admins by Telegram/email, Today → Needs attention reads the table, Settings → Alerts thresholds + recent list, Your account switch. Token expiry: system user tokens don't expire, so 'Meta silent' covers a revoked token
- [~] 2.3 Spend pacing and month-end forecast. Built: `pacing.py` (pure: month-to-date incl. today so far, projection = complete days + 7-day average × days left, spending limit run-out date, daily spend that lands on the monthly target), Results → "<Month> so far" panel (replaces the old limit bar; admins set the monthly target there, setting `monthly_target_cents`), two alert rules through 2.2: limit runs out within 3 days, month heading > 15% over target. Eugene: set a monthly target if he wants one

### Phase 3: Experiments
- [~] 3.1 Experiments tracker. Built: Tests page (`experiments.html`, admins; nav "Tests"), migration 012 (`experiments`; arms = ads and/or ad sets), `experiments.py` (pure `judge`: cost metrics compare results per dollar with an exact binomial test, rates a two-proportion test; "too early" until each arm spent 2× the target (test target → Settings → Alerts cost-per-lead target → the test's own average) with ≥ 3 results over ≥ 3 full days; leaning at 80%, winner at 95%), `experiments_api.py` (list, choices, create, edit, finish/stop/reopen), Desk proposal kind `experiment` (approve = start tracking, nothing on Meta), running and recent tests in the Desk snapshot, skill playbook updated (installed). Eugene: set up the first test when two ads run side by side
- [~] 3.2 Meta A/B tests. Built, switched OFF (Settings → Meta A/B tests, setting `meta_ab_tests`): migration 013 (`experiments.meta_study`, `meta_changes.level` 'study'), `meta_tests.py` (pure `plan`: every arm one ad → creative test `SPLIT_TEST_V2` with a test daily budget (cents; cooldown/observation = start/end; ≤ 2× the campaign budget), every arm one ad set → `SPLIT_TEST` (no extra spend); starts tomorrow at the earliest, 3–30 days, even shares summing to 100; `meta_verdict` maps Meta's winner / high performers / confidence to the arms), POST `<business>/ad_studies` (business id read from the ad account and stored), the cost must be confirmed as shown, end early = move `end_time` (never delete; cancelling before the start is done in Ads Manager), results read back by the worker every 30 min and by "Check Meta now". Fake Meta implements the study endpoints. Unverified against real Meta: the `results` shape, and whether the system user may create studies in the business. Eugene: turn it on only when he wants the first one

### Phase 4: Build everything from the console
- [~] 4.1 Lead form builder. Built: Lead forms page (`forms.html`, admins, linked from Ads), `forms.py` (pure: `payload` → `POST /{page}/leadgen_forms` with Page token: FULL_NAME/EMAIL/PHONE always, optional company/job/city/ZIP, up to 3 custom questions with 2–6 answers or typed, `context_card` intro, `thank_you_page` with a website button or none, `privacy_policy`, `is_optimized_for_quality` for "fewer, more serious leads", `block_display_for_non_targeted_viewer`; `policy_problems` blocks Meta's prohibited question types and prefill repeats; `spec_from_meta` for "Copy into a new form"), live check + phone preview, migration 014 (`meta_changes.level` 'form'), New ad gets a Lead form picker (`form_id` replaces the template's `lead_gen_form_id`). Conditional logic isn't offered (Ads Manager only per the skill). Unverified against real Meta: the form read fields used for copying
- [~] 4.2 New ad set. Built: New ad set page (`new-adset.html`, admins; "+ New ad set" on each campaign), `adset_build.py` (pure: `spec_from` an existing ad set incl. map pins named by their `primary_city_id` via `search?type=adgeolocationmeta`, `targeting` (pins / cities with 10–50 mi / states / ZIPs, `location_types` home+recent, age limits, Advantage+ audience with `age_range` suggestion and age_min ≤ 25, audience hints kept as `flexible_spec`), `payload` copies goal / billing / destination / promoted_object / attribution from the template, `daily_budget` + bid strategy only when the campaign has no budget, always PAUSED, no placement fields = Advantage+ placements), Meta place search (`search?type=adgeolocation`), live `delivery_estimate`, then New ad opens on the new ad set. Unverified against real Meta: the age_min ≤ 25 rule with Advantage+ audience, and `adgeolocationmeta` names
- [~] 4.3 New campaign wizard. Built: `new-campaign.html` (admins; "New campaign" on Ads): goal + name, daily budget (refused above 3× what runs now), ad set (shared place picker `js/places.js`, template ad set, ages, Advantage+ audience, hints, live estimate), lead form (pick, or build one in a new tab and reload), 1–6 ads (start from an existing ad's words and button, same media or one from the library); live check by step + review in dollars with copy warnings (personal attributes, 125-character first line, 40-character headline). `campaign_build.py` (pure: problems, campaign payload OUTCOME_LEADS / lowest cost / PAUSED, review, `next_steps` for resuming, `publish_order` ads → ad set → campaign), `builds_api.py` + migration 015 `campaign_builds` (spec, made ids, draft/partial/created/published): create runs campaign → ad set → creatives + ads (via `create_ad_from` with the chosen form), stops at Meta's first refusal and "Finish creating" makes only what's missing; Publish needs the daily budget typed. Sync now marks ad sets and campaigns that vanished from Meta as DELETED, like ads. Pre-launch checklist items that need people (tracking test, previews) are pointed to, not ticked
- [~] 4.4 Advantage+ creative enhancements. Built: ad page Overview → "Meta's automatic changes" (`creative_features.py`: plain-words labels for ~24 `creative_features_spec` keys, the skill's advice — rewriting / generating ones off, fit / brightness fine — a warning when one of the "off" ones is on; `standard_enhancements` hidden as retired), switching one (admins) makes a new creative with the same `object_story_spec` and the changed spec and swaps it onto the ad (`creative` update), logged as `enhancement`; Meta reviews the ad again. Live check 2026-11-09: N1–N5 have none on; two test creatives have `video_filtering` on. Unverified against real Meta: swapping the creative on a live ad

### Phase 5: Creative intelligence
- [~] 5.1 Concept tags. Built: migration 016 `ad_tags` (one value per ad per dimension: hook / angle / persona / format / offer; source manual / claude / seed / copied), seeded for N1–N5 and N1 · v2 from the round notes (hook styles: Pain statement N1, Outcome promise N2 + N5, Command N3, Question N4), `concepts.py` (pure `group`: sums, cost per lead, hook / hold / qualified rates, minimum-data badge (3 leads and 2× target), cheapest judged group with the exact binomial confidence from `experiments.py`), ad page "The idea" (tags with known values to reuse), Results "By idea" (switch dimension, verdict says how sure), new ads copy their template's tags, Desk proposal kind `tags` (approve applies, source claude), tags in the Desk snapshot, skill playbook (installed)
- [~] 5.2 Swipe file + competitor watch. Built: migration 017 (`swipes`: Ad Library id unique, page, text, headline, button, media, start/stop dates, platforms, notes, tags, source manual / claude; `watched_pages`; schedule preset "Competitor check", weekly Wednesday 9:30, kind research, off), `swipes.py` (pure: Library id from a link, days running, "likely working" at 30+ days), `swipes_api.py` (swipe file + watched Pages for admins; agent `GET /api/agent/watched`, `POST /api/agent/swipes` which refreshes known ids and marks Pages checked), Research page: swipe file (filters: all / running 30+ days / found by Claude, notes) and Watched Pages. Mac: `desk watched`, `desk swipe --file` (desk 1.4, installed), skill section "Competitor watch". The public Ad Library API covers only political and EU ads, so US searches run on the Mac (`ads_library_search`). QA now runs with `qa/run.sh` (fresh fake Meta + sync each run)
- [~] 5.3 Meta's own advice. Built: `advice.py` (pure: both recommendation response shapes, plain labels for known types, which ones apply here (Advantage+ audience, automatic placements, spend more on a good campaign), the budget step against today's budget with the +20% flag, `extra_data`), `advice_api.py` (`act_<id>?fields=opportunity_score` + `act_<id>/recommendations`, cached in setting `meta_advice` with the previous score, refreshed by the worker every 6 h and by "Check again"; apply = `POST act_<id>/recommendations {recommendation_signature, extra_data}` after a fresh read, refused when Meta changed it, big budget steps need `accept_big`; logged as `recommendation`; agent `POST /api/agent/benchmarks`), migration 018 (Monday summary now posts benchmarks; `meta_changes.level` 'account'), Today → "Meta's advice" card (score with change, suggestions by points, Apply behind a confirmation with the +20% warning, Ads Manager links, "How you compare" from the Monday summary). Mac: `desk benchmarks --file` (desk 1.5, installed). Live 2026-11-09: score 96, one suggestion (9:16 video for Reels, +4 points: open issue I4). Unverified against real Meta: applying a recommendation, the `additional_budget` location in the response
- [~] 5.5 Update ads in place (2026-11-10, Eugene: every polish made a new ad and split the statistics). Polish and "Make a new version" proposals are stamped `update_ad` by the server (`desk_api.stamp_update`; `new_ad` opts out); approving puts a new creative on the same ad (`versions_api.update_ad`: fresh read, refuses ads with per-placement media, read-back via `creative_versions.readback_problem`, then the swap). Every switch (also 9:16, Meta's automatic changes, edits seen by sync) lands in `ad_versions` (migration 030). Ad page Overview → Versions: complete days per version, days from a switch until Meta's approval count for neither, Switch back (`/versions/<n>/restore`). Either kind can be applied the other way (`apply_as`). Bridge skill text changed: run `bridge/install.sh` after the server Update, not before (the old server drops `update_ad` payloads with words). Unverified against real Meta: the swap on a live ad (A25), whether the old version keeps delivering during review, the read-back's word comparison.
- [~] 5.4 Fix Meta's advice with Claude (2026-11-10, Eugene: "we get Meta's advice but no way to fix it using claude"). Today → Meta's advice: every suggestion the console can't Apply gets **Fix with Claude** → Desk run kind `advice` (migration 027; options carry the advice, `advice_key` = type + object ids, and the running ads under it; one open run per advice). Mac: bridge/desk 1.7 gives advice runs the render tools (90 min, 300 turns); the server holds advice runs for helpers < 1.7. Skill section "Kind `advice`": for the Reels advice Claude renders a 9:16 cut per running ad, uploads it, and proposes `creative` with `update_ad`; approving **updates the running ad** (Eugene's choice over a new ad): new creative = 4:5 feeds + 9:16 Reels/Stories, same words and form, read back, then swapped on (logged `placement_media`). The card shows Waiting for your Mac / Claude is on it / N to approve / Fix again. Unverified against real Meta: the PAC creative with a lead form (I4), a real advice run end to end.

### Phase 6: Smaller gaps
- [~] 6.1 Comments. Built: Comments tab shows each comment with the Page's replies under it, Answered / Not answered / Hidden, Reply (posted publicly as the Page after a confirmation showing the text) and Hide / Show again (`POST /{comment}/comments`, `POST /{comment} is_hidden`, Page token), only for comments on the ad's own post (`comments.py`), logged as comment_reply / comment_hide / comment_show; no delete. Found while testing: a creative swap (4.4) makes a new post, so likes and comments stay behind; the 4.4 confirmation now says so. Still needs `pages_read_user_content` (and likely `pages_manage_engagement`) on the system user token (I1)
- [~] 6.2 Tracking health. Built: `tracking.py` (pure: last-fired times where the Unix epoch means never, event counts and server/browser split from `/{dataset}/stats`, Event Match Quality from `dataset_quality`, a verdict: not set up / quiet after 48 h / something to fix (EMQ < 6, failed stages) / healthy, with what to do), `tracking_api.py` (read every 6 h by the worker or "Check now", setting `tracking_snapshot`), Settings → Tracking health (above Lead stages to Meta), alert rule `events_quiet` (13 rules now). Live 2026-11-09: dataset edgebourne.com (1821497329119793, business 2289619248494805) has never received an event: lead stages to Meta are off and no site pixel fires. Unverified against real Meta: the `dataset_quality` request shape and the `event_source` aggregation values
- [~] 6.3 Installable app + push. Built: `manifest.webmanifest` (standalone, opens on Today, shortcuts Leads / Results), icons from the logo (`img/app/`, maskable + apple-touch), `sw.js` (no caching of live pages or data; offline page for navigations; push → notification with the link; click opens or focuses the console; renews subscriptions), every page links the manifest and registers the worker. Push without new dependencies: `webpush.py` (RFC 8291 aes128gcm encryption, checked against the RFC's worked example, and VAPID ES256), `push.py` (VAPID keys made once, private one encrypted in settings; only Google / Mozilla / Apple / Microsoft push hosts accepted (no requests to typed addresses), keys validated, gone devices removed), migration 019 `push_subscriptions`, `push_api.py` (`/api/me/push`: list, on, off, test), notify channel order Telegram → push → email. Your account → This device: install button (or the iPhone "Add to Home Screen" steps; iPhone push works only from the installed app), Turn on notifications, devices, Send a test. Dev: fake push service decrypts what it receives (`PUSH_TEST_HOSTS`). Unverified on real devices: Chrome / Android / iPhone delivery

### Phase 7: Agency mode (only if Eugene decides to run client accounts)
- [x] 7.0 Eugene (2026-11-09): yes, one console with many accounts; clients get a read-only login plus reports
- [~] 7.1 Several accounts. Built: migration 020 (`accounts`, account 1 = Edge Bourne with everything that existed; `account_id` on 23 account-owned tables, default and row-level security from `app_account()` = the connection setting `app.account_id`; the app runs as role `ebads_app` (no superuser, so RLS applies), migrations and the few all-accounts jobs (`account_ctx.all_accounts()`: the Mac claiming tasks, expiring stale ones, the queue) use the owner; unique keys per account: meta_cache, alerts, swipes), `account_ctx.py` (context var), `db.py` (`connect_app` + `SET ROLE`, the account set before each query), `settings_store` (23 per-account keys stored as `key@<id>`; account 1 keeps plain keys; the System User token falls back to account 1's), `accounts_api.py` (list / add / rename / switch; a request's account: admins' choice in the session, others their own; Mac task calls use the task's account, other Mac calls `X-Account`), worker pass per account, lead webhooks routed by Page, notification dedupe keys per account, Meta calls refused for unconnected accounts, sidebar switcher with "+ Add an account" (new accounts get Claude's schedules (off) and the first-reply template), Settings note on what's per account, Claude's snapshot names the account and the skill uses that business's brief, bridge 1.6 sets DESK_ACCOUNT (installed). Leak test `dev/qa_leaks.py`: every GET route (48) as admin on each account and as a client, with the other account's ids: no leaks
- [~] 7.2 Client logins. Built: role `client` (users.account_id), sees Today / Leads / Ads / Results of its own account read-only; the server refuses every change except sign-out, password and its own notifications; changing controls hidden (`.read-only`); Team page adds clients to the current account. "Unless granted" (letting a client approve or change budgets) is not built
- [~] 7.3 Client reports. Built: `report_logic.py` (pure: last complete Mon–Sun week or month and the period before, funnel with step rates, a business headline against the target per qualified lead (directional under 10), footnotes on attribution, modelled conversions and the Nov 12, 2026 measurement change when spanned, HMAC-signed share tokens with expiry), `reports_api.py` (the report in the skill's five parts (references/14 §1.9): what happened, why (top ads, best idea), what we did (the change log), what's next (tests), what we need from you (pending decisions); signed share link for 90 days with no sign-in; per-account settings `kpi_target_cents` (Edge Bourne $60 from the brief, migration 021) and `report_email` weekly / monthly, sent by the worker to the account's clients once per period), Reports page (admins and clients; week / month; Share a link; Download PDF = the browser's print to PDF with a print layout, so the server needs no renderer), Settings → Client reports. The admin's chosen account now lives in its own cookie (`ebads_account`): with the session cookie re-sent by every response, a request started before a switch could undo it

### Phase 8: Redesign (Eugene, 2026-11-10: "navigation is difficult, UI/UX sub par"; plan in `ads/docs/REDESIGN.md`)
Decisions: new visual direction (3 mockups, he picks), stay vanilla multi-page, ad status by polling + ad-account webhooks, add bulk actions, saved views, Inbox, period compare. Keep every feature.
- [x] 8.0 Design direction: 3 mockups (`.superdesign/redesign/`: build.py → a/b/c.html, shoot.cjs, compare.html) → Eugene picked **A · Signal** (2026-11-10): graphite, one green = on air, Geist + Geist Mono numbers, 14-day delivery track per ad, borders-only depth, dense rows; tokens in `.superdesign/redesign/a.css` (light + dark)
- [x] 8.1 Status history: migration 023 `status_events` (RLS) + configured_status/issues/learning/created/updated columns; `status_history.py` (pure snapshot/diff/explained_by_console/headline, 16 tests; `upsert_tracked` = SELECT … FOR UPDATE + upsert in one transaction via `db.run_in_transaction`; `mark_missing` records deletions); sync for campaigns/ad sets/ads diffs before each upsert, falls back to the old field set if Meta refuses a new field; `refresh_entity` records console on/off linked to meta_changes (review outcomes never credited to the console); fake Meta `/fake/_review`, `/fake/_review_on_activate`, `/fake/_learning`; ad History tab "Status from Meta" timeline; QA 233 PASS (`qa/run.sh` clears status_events). Unverified on real Meta: the new fields on v24
- [x] 8.2 Status alerts + Inbox API: `status_history.transitions` (pure) → `alerts.raise_found` (shared with `run()`): ad_approved (ok, event), rejection/issues with Meta's reason (same `ad_rejected:{id}:{day}` key as the polled rule), learning_limited, changed_outside (info, console only); migration 024 (`alerts.kind`, condition vs event — the hourly check closes only conditions; `inbox_reads`); `inbox.py` (pure build/pick/counts/category) + `GET /api/inbox`, `POST /api/inbox/read`; `inbox_unread` on `GET /api/refresh`; no_delivery counts from going live; Settings → Alerts lists the 3 new rules; QA 235 PASS
- [~] 8.3 Ad-account webhooks built: `webhooks.parse_ad_account` / `refetch_plan` (pure, tolerant of the documented payload variants: id|object_id, level|object_type, creative level → its ads), `account_for_ad_account` (asks each account's settings; unknown = dropped + logged, never account 1), rows in `webhook_events` (migration 025: `kind`, `field`, `object_id`); worker job `status_history.process_webhooks` → `insights.sync_entities` (multi-id `?ids=` read, plain-field and one-by-one fallbacks) with source `webhook`; retries for an hour; Settings → Meta switch `POST /api/settings/meta/status-updates` (app-level `/{app}/subscriptions` with the app token + `act_/subscribed_apps`; off = DELETE; logged in meta_changes); `dev/status_webhook.py` posts a signed one; QA 239 PASS. **[Eugene]** switch it on after Update; if Meta refuses the app-level call, META-APP-SETUP part I by hand. Unverified on real Meta: payload shapes (raw payload kept in webhook_events), whether the System User can call subscribed_apps
- [x] 8.4 APIs: `ranges.py` (7/14/30/mtd/lastmonth/custom, complete days, `previous`) — wired into `/api/ads` (`vs=prev` adds `prev` at every level; `ads_api.tree_data` reusable with campaign/ad set filters); performance/concepts/insights keep their own ranges until 8.7; `entities_api.py`: `GET /api/campaigns/<id>`, `/api/adsets/<id>` (crumbs, children, timeline, daily series), `/api/timeline/<level>/<id>` (`timeline.merge`, pure), `/api/compare?ids=` (2–6 ads, `compare.shape` pure: best per row, verdict only with 2× target spend and 3 results), `/api/search?q=` (campaigns, ad sets, ads, leads), `/api/views` CRUD (migration 026 `saved_views`); `bulk_api.py` + `bulk.py` (pure): preview reads live values → lines + totals + signed 5-minute plan; apply re-reads each item, turning on needs the daily total echoed (each budget once), +20% needs accept_big, ceiling holds, archive only when off, no delete, each write in meta_changes with `bulk_id`, one resync at the end; QA 250 PASS
- [x] 8.5 Signal shell: `css/tokens.css` (Signal light + dark, legacy token names kept as aliases, Geist + Geist Mono self-hosted with OFL), `css/shell.css` (grouped rail Work / Run + Settings, ⌘K jump field, breadcrumb line with Refresh, section tabs `.subnav` for Ads / Insights / Claude / Settings, phone top bar with back + search + 5 tabs Today · Leads · Ads · Inbox · More, palette, Inbox, Signal density for shared components), app.css lost its tokens + old frame (weights calmed for Geist); `ui.js boot()` rebuilt from one map (PAGE_SECTION / SECTIONS / SUBNAV), `setCrumbs()`, shortcuts (⌘K, /, g+t/i/l/a/n/c/s); `palette.js`; Inbox page (`inbox.html` + `inbox.js`: filters with counts, list + detail, read state, j/k); one status vocabulary in `format.js` (ACTIVE = Delivering, PREAPPROVED, review/problem sets, learning words); every page has its own id; ad page breadcrumbs; sw cache v2; QA 254 PASS. Compare tab joins Insights in 8.7
- [x] 8.6 Ads manager: `js/manager.js` (shared: column registry with Results / Delivery / Video sets, sortable, `tableHtml`, phone `listHtml`, cards, the 14-day delivery track + status dots, `figuresHtml` with vs-before deltas, built-in views All / Delivering / In review / Needs attention / Learning / Off / Tests (closes I9), checkbox + shift-range selection, bulk bar → preview dialog listing every line → apply, Compare 2–6, peek drawer with the merged timeline, `wire()`), `js/urlstate.js`; Ads page = `listing.js` (levels Ads / Ad sets / Campaigns, saved views from the toolbar, range incl. this/last month, vs before, columns, name filter, campaign picker, archived, cards for ads, everything in the URL; old ads.js removed — EasyList blocks `/ads.js`); `campaign.html` / `adset.html` + `entity.js` (figures, spend and leads charts, learning progress + who sees it + reach estimate, children table, History timeline, breadcrumbs); ad page breadcrumbs link to them; QA 262 PASS (budget flows now on the Campaigns level, New ▾ menu)
- [x] 8.7 Compare page (`compare.html` + `compare.js`: creatives as column heads, metric rows with Lowest/Highest and vs-before, the verdict that waits for 2× target spend and 3 results, tags compared, `charts.lineChart` with a line per ad (series tokens --s1..--s6), add/remove ads, picker when opened empty; Insights tab + ⌘K); Today's Changes card → Inbox card (latest unread that are still live, ads in review at Meta, console changes folded below); Leads filter by campaign or ad (`?campaign=` / `?ad=`, `sources` from `/api/leads`, ad page links to it); Settings section list on the left on wide screens; Results ads table kept as the analysis view with a “Manage in Ads” link (no URL retired, so no 301s); ad-named scripts renamed (`creative.js`, `new-creative.js`, `new-aset.js`) and QA now also refuses ad-like file paths; resolved problems marked in the Inbox and kept off Today; QA 267 PASS
- [~] 8.9 Claude page as one board (2026-11-10, Eugene: jobs stack up, hard to see what's finished, can't clear the queue, can't tell which question a suggestion came from, can't accept across categories in one go). Requests tab = trays (Needs you, On your Mac, Up next, Finished, Cleared; `desk_view.board`) + a thread per request (You asked → Claude → Suggestions, `js/requests.js`). Review all shows every waiting suggestion under its question; one Accept sheet (`js/decide.js`, `POST /api/proposals/review` = fresh Meta read, `desk_view.review`) sorts them by what they touch; each is then approved one by one through `/approve`, so every money rule holds and a refusal doesn't stop the rest. Never ticked for you: turning on, a step over +20%, a budget that moved since Claude read it, two changes to the same thing. Stop (desk/bridge 1.8: keep-alive every 15 s ends the run), Run next (`queue_rank`), Clear queue, Clear finished, Put back (`archived_at`; kept for `desk history` and By ad), New until opened (`seen_at`). Migration 028. Dev: `dev/seed_board.py`. **After push + Update: reinstall the bridge on the Mac (check for a running task first); Stop is hidden until it reports 1.8.**
- [~] 8.10 Claude page as conversations (2026-11-10, Eugene: no way to cancel, no way to follow up, page still clunky). List + one conversation with a pinned reply box (`js/conversation.js`, `js/desk.js`, `js/reading.js`, `js/viewer.js`). A reply is a new run with `thread_id` = the first run (NULL on the first run), `options.reply`, and `options.about` when a suggestion was sent back (`status = 'revised'`); it runs next. `desk_view.board` is per conversation. Runs keep `steps` (progress history) and `swipe_ids`. Each answer shows previews: every ad it names (`desk_view.mentioned_ads`), Meta's preview per placement on new-ad suggestions, compare with what runs now, competitor ads it saved (`desk swipe --task`). Clearing: × per conversation, Clear per day, remove one reply, Undo (`/api/desk/restore`). Bridge/desk 1.9: session id = uuid5 of the task, a follow-up runs `--resume <previous> --fork-session`, falling back to a fresh run; keep-alive 5 s. Migration 029. **After push + Update: nothing else; the Mac already has 1.9.**
- [~] 8.11 Mobile hardening (2026-11-10, Eugene: screens zoom and lose their size). Every field is 16px on phones (iOS zooms into anything smaller), viewport fixed at scale 1 on every page, pinch off, nothing past the screen edge at 320 px, `theme.js` follows the visual viewport (`--app-h`) and clears iOS's leftover pan after the keyboard or a rotation. QA guards it. Checked in Chromium mobile emulation and WebKit; unverified on a real iPhone keyboard.
- [~] 8.12 Follow-through and the line (2026-11-10, Eugene: approved a fix and nothing visibly happened; always show what Claude is on; let me queue a bunch). Accepting a suggestion nothing else acts on now starts a run in its conversation (`continue_accepted`, `options.accepted`, state "Claude is on it"); older approvals get "Have Claude do this". Failed suggestions show Meta's or the check's exact reason (`failure`, also in `desk task`). `/api/desk/now` feeds a status line on every page (`ui.js startClaudeNow`) and the always-present On your Mac panel lists each waiting job. Add to line stacks new jobs; several follow-ups can wait in one conversation, in order. **9:16 still open:** all five approvals failed on "Meta's copy of the new creative has no 9:16 video" (`readback_problem`). After Update, read what Meta stored with `GET /api/ads/creative/1783540646270812/inspect`, then fix `readback_problem` or the build, and retry one ad.
- [~] 8.8 Finish: full screenshot pass (every page, light + dark, desktop + 390 px) clean; feature inventory in REDESIGN.md all ticked; README Pages + Design rewritten; old per-page back links hidden (breadcrumbs replace them); 317 unit tests, QA 267 PASS, no console errors, no ad-like class/id/file path. **Live checks owed (each with Eugene's yes, after push + Update):** (1) the new Graph fields on v24 (`configured_status`, `issues_info` + `created_time` on campaigns/ad sets, full `learning_stage_info`) — the sync falls back to the old field set if Meta refuses one, check the backend log; (2) Settings → Meta → Instant status updates: the app-level `/{app}/subscriptions` call and `act_/subscribed_apps` with the System User token (else META-APP-SETUP part I by hand); (3) first real ad-account webhook payload (stored raw in `webhook_events.payload.raw`) matches `parse_ad_account`; (4) a paused test ad turned on → In review → Approved shows in the Inbox, on the ad's History tab and as a push/email; (5) a bulk off + on on two test ads; (6) Eugene's ad blocker: open Ads, an ad, Compare

### Phase 9: UI/UX audit (Eugene, 2026-11-10: "research the web… improve our app design in all sections, close gaps, easy seamless navigation from everywhere"; plan in `ads/docs/UX-AUDIT.md`)
Decisions: design + workflows (no automation rules), new Creative section (Research moves out of Claude), keep Signal and refine, clickable mockup first, then phase by phase. Money rules do not loosen.
- [~] 9.0 Baseline shots of every tab + clickable mockup (`.superdesign/audit/`). **[Eugene]** reviews before 9.2
- [x] 9.1 Fix what's broken: Compare keeps vs before; Results takes This month / Last month through `ranges.py` and ignores a bad saved range; Leads follows `#lead=`; Claude `#list` on desktop; fix run links; danger buttons readable on hover; class collisions renamed (`.rp-doc`, `.cw-card`, `.chg-list`); Refresh no longer reloads a form; leave warning (`guardLeaving`/`markSaved`); typed notes and email survive a stage move; each Settings save touches its own panel; shared `errorState`/`showLoadError` with Try again, network errors in plain words; unfinished builds on Ads (`GET /api/builds/open`); Reports hidden from team members; bulk Archive admin only; confirm on Team reset/deactivate and raising the ceiling; Undo on Decline (`/undecline`, 10 minutes, same person); sign-in refuses `//host`; account currency and name instead of `$` and Edge Bourne
- [x] 9.2 One design system (tokens, components, one vocabulary, accessibility). Part 1 done (9.2a): Signal tokens with type / radius / shadow / space scales and `--on-*` text-on-fill roles, contrast fixed in both themes (QA reads 30 token pairs), Seal & ledger names retired, skip link, real tablists, `aria-invalid`, money dialogs and the Accept sheet open on Cancel, toasts announced inside an open dialog, tables one Tab stop with ↑ ↓, quick-look focus trap, chart summaries + true-size phone charts, 44px phone targets (`qa/guards.cjs`). Part 2 done (9.2b): one definition each in `app.css` for Tabs (`.tabs`, section `.subnav` shares it), Segmented, Filter chips (`.filters` + `.view-chip`, also the vs before / archived toggles), Status (`.pill`, `format.statusPill`), Date range (`format.rangeSelect` + `RANGES` on Ads, Results, Campaign, Ad set, Compare, Audience), Table, Empty state (`ui.emptyState`), Skeleton (`ui.skeleton`), Dialog (`confirmDialog`, `cancel: false` for notices; Team's password uses it), Suggestion card (`js/suggest.js`, used by the Claude page, the ad page and Research); shell.css overrides folded in, 26 dead classes removed, 40 px gutter gone; `format.js` `WORDS` + `EXPLAIN` (Views, People reached, Hook rate, Cost per lead, Suggestion, Accept, Conversation; plain Advantage+, learning, swipe file), server messages in the same words; QA `guards.componentDrift` / `vocabularyLeaks` on 25 screens. Review fixes: one Status (`.st` retired, Ads manager, Today, Compare use `.pill`), Inbox filters on the Tabs component, inline Suggestion cards name the ad (never its id) and show what stays the same, Polish tab and Fix-with-Claude words (accept, suggests), QA clicks the inline Accept / Decline and Team's password notice
- [x] 9.3 Navigation from everywhere. [x] 9.3a links and keeping your place, done and pushed 2026-11-11. [x] 9.3b command menu, phone, 404 and offline, done and pushed 2026-11-11 (review fixes: clients get no Refresh in ⌘K, "Results: By idea" scrolls to its panel, phone sort names the computer sort, screen-reader text for Claude's count, lead-form leak canary; Creative first in More waits for 9.5). Part 1 (9.3a): `ui.entityLink(level, id, name)` is the one way a page names a campaign, ad set, ad, lead, form (`/forms.html#form=`), test (`/experiments.html#<id>`) or tag (`/performance.html?idea=&tag=` marks that row in By idea); forms and tests stay plain for non-admins. Applied on the ad page (Where it runs + the tests it is in), lead detail (ad, ad set, campaign, form), Today (the ad a lead came from, console changes), test arms (`experiments.arm_members`), Compare (names, tag chips), Results (By idea ads via `concepts.members`, Meta's history via `activity_object` + `object_id`), the signed-in report only (`build(links=True)`; share links and emails carry no ids), suggestions (On, the ad updated, test arms), Inbox detail (`inbox.with_subjects`), Settings' recent alerts, Team, build results. Reverse links: campaign → Its leads + Results (and in its quick look), ad → Compare (picker with it ticked) + its tests (`experiments.containing`, admins). One date range (`format.sharedRange` / `rememberRange`, localStorage `ebads-range`) on Ads, Campaign, Ad set, Ad (Overview daily charts via `/api/ads/ad/<id>/series` + `ranges.daily_series`, and Audience), Compare, Results; a link's own `?range=` wins. Breadcrumbs back to a list open it as last filtered in the tab (`rememberList` / `listHref`, sessionStorage). New pages: `?from=` (only a path on this site, `safePath`) gives Cancel, the middle breadcrumb and the way back (`returnCrumbs`, `withFrom`); New ad's template is `?template=` (an old `?from=<ad id>` still works); a new ad set lands on New ad with a link to it; a published campaign links to its page. History: `urlstate.openLayer` / `closeLayer` / `leaveLayer`: the quick look (Ads, Campaign, Ad set: `?peek=`), a lead on a phone and an Inbox item (`#item=`; phones now open the item over the list instead of jumping to its link) push one step that Back closes; the Inbox honours `#item=` on arrival only (filters and refreshes stay put, a read item stays open), and a phone returns to the list where it was with focus on that item. Part 2 (9.3b): the command menu (`js/palette.js`) holds every page, the in-page tabs worth a jump (Claude's, Results' By idea, Inbox filters, the Ads views), this page's own tabs (an ad's Polish…, by clicking them), every Settings section (whole-console ones for owners), saved views (`/api/views`), actions (New…, Ask Claude, Refresh, Switch theme, Keyboard shortcuts, Sign out; nothing that moves money) and the words people use for a page (`keys`: Home, Results, Performance…), ranked name > alias > where it lives; `/api/search` adds lead forms (from stored leads, no Meta call), tests and saved competitor ads for admins, escapes `%`/`_` (`search.like_pattern`) and shares its 24 places out by kind (`search.fair_share`), so leads are never pushed out; `research.html#swipe=` and `forms.html#form=` follow the link. "?" opens the shortcuts card (`ui.openShortcuts`, the shared dialog). Phones: Ads has a Sort picker and the campaign picker, the bulk bar wraps to count + × over equal actions (`.bk-acts`), More carries Claude's waiting count and lists Claude first (opening on it, not on the account switcher). `404.html` via `error_page 404` in `nginx/ads.conf` (the API's 404s still come from Flask); `offline.html` + `js/offline.js` check the connection on `online`, every 10 s and on Try again now, and open the page asked for (sw cache v5 keeps theme.js and offline.js). Leak test also searches each account's marks. Inbox detail on phones was already done in 9.3a
- [ ] 9.4 Every tab redesigned on the new parts
- [ ] 9.5 Creative section and the loop
- [ ] 9.6 Finish

### Audit 3 (2026-11-11): 134 verified findings fixed, then 11 new features
Eugene: "full detailed audit… data consistency, feature abundance… new useful features… UI/UX… reliable and secure". 9.0 mockup treated as approved.
- [x] Fixes, 9 clusters (all pushed): QA harness can fail + RLS/leak coverage (cf2398a), account isolation (b065419), lead pipeline + migration 031 (b3dcb9d), money writes read Meta fresh + migration 032 (1eee589), sync integrity (892fe47), one number everywhere (8543d68), desk/bridge binding + sandbox, bridge 2.0, migration 033 (b533dc6), sign-in sessions + migration 034 (660d810), parallel reads + migration 035 (73c4622). Left open on purpose: per-account keys on leads/campaigns/adsets/ads (A3-17), a sandbox-exec around node in render runs (A3-4), thread summaries on the Claude board (A3-127)
- [ ] **[Eugene]** after the Update: everyone signs in once more (034); reinstall the bridge (2.0); live checks listed in the 2026-11-11 log line
- Features (specs in `docs/features/`, plan and Eugene's answers in `00-PLAN.md` §7; build order D2 → W2 → W1a → L1 A+B → L2 → W1b → D3 → D1):
- [ ] D2 Edits made in Ads Manager + change markers on charts
- [ ] W2 Client report review
- [ ] W1a Snooze alerts + quality alerts
- [ ] L1 Follow-up queue + booked-call tracking (manual only, no booking webhook)
- [ ] L2 Lost reasons, lead quality, repeat and junk leads
- [ ] W1b Diagnose with Claude
- [ ] D3 "Did it work?" check
- [ ] D1 Match Ads Manager

---

## 3. The plan, step by step

Each step lists: goal · how · files · tests · done when · open decisions. Meta API details marked
*(verify)* must be checked against Meta's current docs (`mcp__meta-ads__ads_get_help_article`,
`ads_get_field_context`, or developers.facebook.com) before coding, and added to
`ads/dev/fake_meta.py` so local tests cover them.

### Phase 0: Prove what's built

**0.3 Real-Meta verification.**
- **Ask first.** Run this with Eugene watching, or with his yes for each write. These touch the live account.
- **Off-switch only.** Use a test ad that is **off**: duplicate N3 (copies are created PAUSED) and work on the copy. Never touch N1–N5's status or the budget for testing.
- **Results go in this file.** Record each one in the Phase 0 table below. Fix bugs as `fix(ads): …` commits.

| # | Path | How to check | Result |
|---|---|---|---|
| a | Sync: ads, ad sets, daily insights, thumbnails | Ads page shows N1–N5 with images; Performance has rows | ✅ 2026-11-09: N1–N5 with thumbnails, campaign/ad set ACTIVE, 7-day spend $20.47 / 1 lead |
| b | Preview iframes | Ad page Overview shows Feed / Reels / Stories previews | ✅ Meta preview renders (2–8 s; page is blank meanwhile, no spinner) |
| c | Duplicate | Duplicate N3 → new ad appears, off | ✅ 120252689342970312 "N3 - Same work twice - copy", PAUSED |
| d | On/off on the copy | Turn the copy on and off; check Ads Manager shows the same | ✅ Meta (MCP) ACTIVE after on, PAUSED after off, $0 |
| e | Image upload + new ad | New ad from the copy with an uploaded image; created off; preview renders | ✅ "TEST e - N3 image upload" 120252689366370312, PAUSED, preview shows the still |
| f | Video upload (chunked) + new ad | Same with a short MP4; watch Settings/Activity for errors | ✅ 1.4 MB MP4 → "TEST f - N3 video upload" 120252689383970312, PAUSED, video preview |
| g | Breakdowns, rankings, video funnel | Audience and Video tabs fill once there is delivery | ✅ age/gender/region/placement/hour, rankings ("not enough data yet"), funnel p25–p100 |
| h | Comments | Comments tab lists post comments (needs Page token) | ❌ Meta (#10): needs `pages_read_user_content`. **[Eugene]** regenerate the system user token with it (META-APP-SETUP part C/E) and paste it in Settings → Meta |
| i | Meta change history | Performance → "What changed on Meta" lists the 2026-11-08 publish | ✅ 33 events incl. Pending Review → Active, delivery starts, "Account billed" |
| j | Audience estimate | Ads page shows the ad set estimate | ✅ after a fix: Meta retired `estimate_dau` (#12), field dropped; live 2026-11-09: 10.4M–12.3M people |
| k | Polish run | Polish → Quick check on N1; scorecard + proposals arrive | ✅ task 2, 4 min, score 3.5/5, 3 copy proposals + 1 new-version request |
| l | Approve a copy version | Creates an ad, off; leave it off | ✅ proposal 1 → 120252689507540312 "N1 - One simple system · headline Run it all", PAUSED |
| m | Lead webhook | Meta Lead Ads Testing Tool → lead in inbox + email | ✅ delivered (Success), lead #4 stored as test lead 11:06:25, email 5 s later. Test leads are hidden from the inbox (no toggle). Meta's webhook "Test" sample (lead 444444444444) retried forever → fixed: give up on code 100 or after 24 h |

Clean-up: the test copies stay **paused**; never delete them.

Follow-ups found in 0.3 (small): show test leads behind a toggle on Leads; a loading state on the ad page while Meta's data arrives. Meta's webhook payload uses page id 1404203625446490 (the Page's other id); the handler doesn't check it, keep it that way.

**0.4 Render run.**
1. Pick a creative proposal with "Make it now" (or queue "Make a new version" on N3 with the direction "rebuild the 9:16 files without the banned FREE WORKFLOW REVIEW wording").
2. Watch `~/Library/Logs/ads-desk/task-<id>.log`. Expect 10–40 minutes.
3. Check that the result arrives as a proposal with the uploaded media, and that approving it creates an ad that is off.
4. Fix what breaks: permissions in `bridge.py` `allowed_tools()` for kind `render`; SKILL.md render playbook.

Result 2026-11-09 ✅: "Make it now" on N1 (proposal 4 from polish #2) → task 3 ran headless in 9 min →
`creatives/2026-11-09-desk-task3/` (offer bar from frame 0 bottom right, solution line at 3.2 s, bold
"Tap below ↓", "Updates drafted") → uploaded video 4:5 1030340833422294, video 9:16 2015174525716803,
stills f55f0c04…, 25b7a5b3… → proposal 5 → approved → ad 120252690325970312 "N1 - One simple
system · v2", PAUSED, $0. Broke and fixed: the run couldn't append to `reports/log.md` (now allowed,
bridge 1.3); `cp` in a chain was refused (playbook now says one command at a time; it used node).

### Phase 1: Close the loop with Meta

**1.1 Lead stages → Meta (Conversions API for CRM).**
- **Goal.** When a lead moves to contacted / qualified / won / lost in the inbox, Meta receives that event for the lead. Meta then learns who becomes a client, and later the ad set can optimise for qualified leads (needs about 200 leads a month).
- **How.**
  - On a stage change, enqueue a row in a new `crm_events` table (migration 006): lead_id, meta lead id, stage, event_time, status, attempts, last_error, sent_at.
  - The background loop in `jobs.py` sends pending rows to `POST /{dataset_id}/events` with:
    - `event_name` = the stage name
    - `action_source: "system_generated"`
    - `user_data.lead_id` = the Meta lead id (the 15–17 digit leadgen id stored with each lead)
    - `custom_data.event_source: "crm"`
    - `custom_data.lead_event_source: "Edge Bourne Ads Console"`
    - `event_time` = when the stage changed

    Verified 2026-11-09 against Meta's payload spec: `event_name` is free-form (we send Lead / Contacted / Qualified / Won / Lost), `lead_id` is a JSON number, `event_time` at most 7 days old and later than the lead, and every earlier stage plus the initial lead must be sent too (a jump from New to Won also sends Contacted and Qualified).
  - Retry with backoff, give up after 24 h, and show failures on Home → Needs attention.
  - Settings → Meta gets:
    - a "Dataset ID" field (default 1821497329119793)
    - a "Send lead stages to Meta" switch, default off until Eugene turns it on
    - a "Send test event" button that uses Meta's `test_event_code`
  - Lead page: a small line per stage, "Sent to Meta 2 min ago" or the error.
- **Setup Eugene does in Events Manager** *(verify)*:
  - connect the dataset to the lead form / CRM
  - map the stages to the funnel (Events Manager → the dataset → "CRM" setup)

  Write him a click-by-click guide in `docs/META-APP-SETUP.md` (new part H).
- **Token.** Use the system user token already in Settings. Check that it has access to the dataset, or that the dataset is assigned to the system user.
- **Files.** `migrations/006_crm_events.sql`, new `crm_events.py` (pure payload builder + sender), `leads_api.py` (enqueue on stage change), `jobs.py`, `settings_api.py`, `frontend/settings.html|js`, `frontend/leads.js`, `dev/fake_meta.py` (accept and record `/events`).
- **Tests.**
  - payload builder: each stage, missing lead id → skipped with reason, time handling
  - retry and backoff schedule
  - is_test leads are never sent
  - E2E: change a stage in the dev inbox → fake Meta received exactly one event
- **Done when** the test event shows in Events Manager → Test events, and a real stage change shows up in the dataset overview.

**1.2 Instant lead alert to the phone.**
- **Open decision (ask Eugene):**
  - (a) Telegram bot. Free, instant, no app to build.
  - (b) Web push from an installable console app. Free; iPhone needs the app added to the Home Screen.
  - (c) SMS through Twilio. Paid account; most reliable.
  - (d) Email only, as now.

  Recommend (a), or (b) if he dislikes Telegram.
- **How.** Add a `notify.py` with one `send(user, kind, text, url)` function and one backend per channel. Each user picks their channels in Account settings. Lead alerts, reminders (1.4), alerts (2.2) and Desk results all go through it.
- **Files.** `notify.py`, migration (user channels, delivery log), `account.html|js`, settings for the bot or Twilio keys (encrypted, entered in Settings).
- **Done when** a test lead reaches Eugene's phone in under 30 s.

**1.3 Automatic first reply to the lead.**
- **Goal.** Within a minute of the form, the lead gets a short email from Eugene's address: "Got it, here's what happens next, book a time here".
- **How.**
  - Template stored in Settings → Lead reply, editable with a preview; switch default off.
  - Sent through `mailer.py`, using the site mail settings.
  - The lead page shows "Reply sent".
  - Never send to test leads.
  - Use plain text plus simple HTML, no tracking pixel.
- **Open decision:**
  - booking link: does Eugene have one (Calendly, SavvyCal, Google appointment page)?
  - wording: Eugene approves it.
- **Done when** a Testing Tool lead receives the reply and Eugene approves the wording.

**1.4 Untouched-lead reminders and response report.**
- **How.**
  - Reminders through `notify.py`, using the same background loop:
    - 5 min after arrival, if still `new` and no note → remind the owner
    - after 1 h → remind the admins
    - next morning at 8:00 local → daily list of untouched leads
  - Leads page header: median time to first contact over the last 30 days, and the share contacted within 5 min.
- **Done when** a fake lead triggers the 5-minute reminder in dev. Use a short interval through an env override for tests.

### Phase 2: Works without being asked

**2.1 Desk schedules.**
- **How.** Migration: a `desk_schedules` table with kind, direction text, cron-like spec (daily HH:MM, every N days, weekly weekday), next_run, enabled.
  - The background loop creates a normal `desk_tasks` row when a schedule is due. The Mac bridge already picks tasks up, and nothing new runs on the Mac.
  - Desk page: "Schedules" section with on/off and edit.
  - Presets matching meta-ads/CLAUDE.md:

    | Preset | When | What |
    |---|---|---|
    | Daily health | 8:30 | Disapproved ads, delivery errors, zero impressions, spend vs week, pixel volume. No budget talk. |
    | Optimizer review | every 3 days | The `/meta-ads-launch optimize` logic. Proposals only. |
    | Monday summary | weekly | `/weekly-account-summary` + `/ads` operating check. |
    | Monthly audit | 1st of month | `/meta-ads-audit` plus fatigue and frequency checks. |
  - Results notify Eugene through `notify.py`, with a one-line summary and a link.
  - Add a playbook per new kind in the Desk SKILL.md, keeping the read-only tool list. Proposals are the only output that changes anything.
- **Tests:** schedule maths (next_run across DST in America/Los_Angeles), and no duplicate tasks when the loop runs twice.
- **Done when** a daily health task appears by itself and its report reaches Eugene's phone.

**2.2 Alerts engine.**
- **How.**
  - A pure function `evaluate(snapshot, history) → [alerts]` in `alerts.py`, run after every sync.
  - Stored in an `alerts` table with a dedupe key per entity and day, so the same alert never repeats.
  - Sent through `notify.py`.
  - Home → Needs attention reads from the same table.
  - Each rule has a threshold Eugene can edit in Settings → Alerts. Rules:
    - ad rejected or has issues
    - zero impressions 6 h after approval
    - spend today > 1.75× daily budget (only flags; Meta allows this)
    - week spend > 7× daily budget
    - spending cap ≥ 80%
    - frequency (7-day) > 3 with CTR down ≥ 20% and CPM up ≥ 20% vs the ad's own first week, i.e. fatigue
    - CPL 7-day > 1.3× target with ≥ 3× target spent
    - no leads for 3 days while spending
    - lead webhook silent while Meta reports leads (tracking break)
    - Meta token expiring
- **Tests:** a table of snapshots → expected alerts for every rule, including "not enough data" cases.

**2.3 Pacing and forecast.**
- Performance page: month-to-date spend, projection at current pace, days until the spending cap, and the daily budget needed to land on a monthly target that Eugene sets in Settings.
- Pure functions, unit tested. Pacing alerts go through 2.2.

### Phase 3: Experiments

**3.1 Tracker.**
- Migration: an `experiments` table with:
  - name, hypothesis, metric (CPL / cost per qualified lead / hook rate…), arms (ad or ad set IDs)
  - start, planned end, minimum data rule, status, verdict, notes
- Experiments page:
  - a list, plus a detail view showing arms side by side for the experiment's dates
  - the verdict is "not enough data" until each arm has spent ≥ 2× target and has ≥ 3 results
  - after that it shows the difference with a simple confidence note
- Rule: never call a winner from Meta's 65% confidence alone.
- The Desk can propose an experiment (proposal kind `experiment`); approving one creates the record.

**3.2 Meta A/B tests.**
- For structural questions (two ad sets / two creatives with a clean split), create a Meta A/B test from an approved experiment, with the arms paused until approved.
- Graph API: ad studies of type SPLIT_TEST *(verify)*. The Mac also has `ads_experiment_abtest_create_test`, so creating can happen through the Desk.
- Read results back into the experiment page.
- Open decision: create on the server through the Graph API, or through the Desk via MCP? Recommend the Graph API so it works when the Mac is off.

### Phase 4: Build everything from the console

**4.1 Lead form builder.**
- New form page:
  - intro (headline, bullets)
  - questions: name, email, phone, and up to 3 custom multiple-choice qualifying questions with conditional logic *(verify)*
  - "Higher intent" review step
  - privacy policy URL, default https://edgebourne.com/privacy
  - thank-you screen with a button (website or booking link)
- Created through `POST /{page_id}/leadgen_forms` with the Page token *(verify fields)*. Show a phone-shaped preview before creating.
- Forms can't be edited after creation on Meta *(verify)*, so the UI offers "Copy into a new form".
- Policy check before creating: no prohibited questions (meta-ads skill `references/12-policies-and-compliance.md` §lead-form questions).
- **Done when** a new form appears in the Page's forms list and can be chosen in New ad.

**4.2 New ad set.**
- In an existing campaign. Fields:
  - name
  - optimisation: leads on the Instant Form
  - locations: list of pins with a radius (SoCal default from the live ad set)
  - age
  - Advantage+ audience on (suggestions only)
  - placements: Advantage+ (manual placements are not offered for Leads campaigns since 2026)
  - schedule
  - daily budget, only if the campaign uses ad-set budgets
- Always created PAUSED. The audience-size estimate (`delivery_estimate`) updates live while editing.
- Targeting summary through the existing `summarize_targeting()`.

**4.3 New campaign wizard.**
- Steps: goal (leads) → budget (dollars, shows cents) → ad set (4.2) → form (4.1 or existing) → ads (pick media from the library, words) → review.
- Review shows every entity, budgets in dollars, the policy check result and the pre-launch checklist (meta-ads skill `templates/campaign-build-sheet.md` §F).
- Create everything paused. Then a separate **Publish** button with a typed confirmation turns on the campaign, the ad set and the ads.
- **Tests:** a fake Meta full build; the build order matches meta-ads skill `references/15-marketing-api.md` §build sequence.

**4.4 Advantage+ creative enhancements.**
- Ad page Overview gets "Meta's automatic changes", read from the creative's `degrees_of_freedom_spec.creative_features_spec`.
- Show each feature (text improvements, image touch-ups, music, etc.) as on or off.
- Changing one creates a new creative and swaps it in, with confirmation, because creatives can't be edited in place *(verify)*.
- Default recommendation from the meta-ads skill: turn off text rewriting for brand-sensitive copy.

### Phase 5: Creative intelligence

**5.1 Concepts.**
- Migration: `ad_tags` with ad_id, dimension (hook / angle / format / persona / offer), value.
- **Tagging.** Tag ads by hand on the ad page. The Desk can propose tags: Polish runs tag automatically as a proposal.
- **Concepts page:** results grouped by any dimension:
  - spend, leads, cost per lead, hook rate, hold rate, qualified rate
  - a minimum-data badge per group
  - question it answers: "which hook wins across ads"
- Seed the tags for N1–N5 from `~/Desktop/Dev/meta-ads/creatives/` round notes.

**5.2 Swipe file + competitor watch.**
- Research page:
  - "Save" on any Ads Library result → a `swipes` table (snapshot of text, media URL, page, first seen, days running, notes, tags)
  - a "Watched pages" list
- **Weekly competitor check.** A Desk schedule (2.1) re-runs Ads Library searches for watched pages through the Mac's MCP `ads_library_search`. It reports new ads and long-running ones (running a long time is a sign the ad works).
- **API limit.** The Graph Ads Library API returns only political/issue ads and ads delivered in the EU, so commercial US searches go through the Desk *(verify current limits)*.

**5.3 Meta's own advice.**
- Show Opportunity Score and its recommendations (Graph `act_<id>/recommendations` *(verify)*; MCP `ads_get_opportunity_score`) on Home.
- Each recommendation has an "Apply" button that goes through the usual confirm dialog. Budget changes keep the +20% warning.
- Benchmarks and peer comparison (MCP `ads_insights_industry_benchmark`, `ads_insights_performance_vs_peers`, `ads_insights_auction_ranking_benchmarks`) are MCP-only. The Monday summary schedule includes them and the dashboard shows the latest numbers.

### Phase 6: Smaller gaps

- **6.1 Comments.**
  - Reply, hide and unhide on the Comments tab, through the Page token: `POST /{comment_id}/comments`, `POST /{comment_id}` with `is_hidden`.
  - May need the `pages_manage_engagement` permission on the system user *(verify)*.
  - Optional: the Desk drafts replies for Eugene to send.
  - Never delete comments.
- **6.2 Tracking health.**
  - Panel showing dataset event counts (Lead, PageView), Conversions API share, Event Match Quality, last event time, and lead-stage events from 1.1.
  - Source: dataset stats/quality *(verify Graph fields; MCP `ads_get_dataset_quality`)*.
  - Alert when Lead events stop (2.2).
- **6.3 Installable app.**
  - Manifest, icons and a service worker for push (if 1.2 chose web push).
  - Copy the approach from iSpend (`~/Desktop/Dev/ispend`, see "Fast screens"); mind the CSP.
  - On iPhone, push works only after "Add to Home Screen".

### Phase 7: Agency mode (only after 7.0 says yes)

- **7.1 Several accounts.**
  - New `accounts` table.
  - Every Meta table gets `account_id`.
  - Settings become per account: token, page, ad account, dataset, form defaults.
  - An account switcher in the nav, sent as a header (as iSpend does with profiles).
  - Leak tests that walk every GET route.
  - Per-account Desk tasks; the bridge passes the account to the skill.
- **7.2 Client role.** It sees only its own account: results, leads, reports. It cannot change budgets or approve proposals unless granted.
- **7.3 Client reports.**
  - Monthly and weekly report pages, as a shareable signed link and a PDF (headless Chrome is already in the stack for creatives; on the server use a small renderer *(decide)*).
  - Content follows meta-ads skill `references/14-reporting.md`: business results first, attribution setting named.

---

## 4. How to build each step (working agreement)

1. **Ask first** when the step has an open decision. Otherwise pick the conventional option
   and say so.
2. **Tests first** for pure logic (payload builders, rule evaluation, schedule maths, pacing):
   `ads/backend/tests/test_<area>_logic.py`, unittest, no database. Run:
   ```bash
   cd ~/Desktop/Dev/edgebourne
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
   docker exec -e WORKERS_ENABLED=0 edgebourne-ads-backend python -m unittest discover -s tests -v
   ```
3. **Fake Meta first.**
   - Add every new Graph endpoint to `ads/dev/fake_meta.py` before calling it.
   - Production code reads `META_GRAPH_BASE`, so dev hits the fake. Never hit real Meta from tests.
4. **UI rules:**
   - **CSP:** no inline scripts or `style=""`. Widths are set from JS (`data-w` + CSSOM). Classes go in `css/app.css`.
   - **Shared modules:** reuse `format.js`, `charts.js`, `controls.js` (`confirmDialog`, `switchHtml`) and `tasks.js`.
   - **Look:** light and dark themes, phone width, plain words (Eugene is not a developer).
   - **Charts:** follow the dataviz skill.
5. **QA.** Extend `ads/qa/flows.cjs` with the new flow and run it plus `ads/qa/shots.cjs`.
   Look at the screenshots. Both use the Playwright install under
   `~/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules`. The local login is in
   `flows.cjs`. Too many logins hit the rate limit; wait or restart the backend.
6. **Desk/bridge changes.**
   - Edit `ads/bridge/*` and `ads/bridge/skill/SKILL.md`, then run `ads/bridge/install.sh` to refresh `~/.claude/skills/ads-desk/`.
   - Restart the LaunchAgent: `launchctl kickstart -k gui/$(id -u)/com.edgebourne.ads-desk`.
   - Check `~/Library/Logs/ads-desk/bridge.log` shows the new version watching `https://ads.edgebourne.com`.
7. **Commit.**
   - Conventional Commits, e.g. `feat(ads): send lead stages to Meta`.
   - Never mention Claude or Anthropic in commit messages (user CLAUDE.md); no Co-Authored-By line.
   - Push to `main` only when Eugene has said to commit/push, or has already asked for this phase to ship.
8. **Hand-off.** Tick the box, add a Progress log line, update the memory file, and tell Eugene:
   - what's new
   - "run Update on the server"
   - any Meta-side setup he must click, with a guide in `docs/META-APP-SETUP.md`
   - what is still unverified on real Meta

---

## 5. Gotchas already learned (don't relearn them)

- **Ad blockers hide "ad" class names.** EasyList hides `.ad-cell`, `.ad-card`, `.ad-grid`, `.ad-head`, `.adset`, `#ads-panel` and many more; in an ads console that blanked ad names on Results and could hide whole ad sets on Ads (Eugene's screenshot, 2026-11-09). Ad things use the `cr-` (creative) and `aset` prefixes instead; QA fails on any class or id starting with ad- / ads- / adset / advert / sponsor / banner / promo. Data values (`level: "ad"`, `#ads` tab links) are fine: blockers only match markup.

**Headless Desk runs on the Mac**
- They use `--permission-mode dontAsk`. Heredoc JSON piped into `desk` is refused.
  - Write JSON to `reports/desk/tmp/task<id>-*.json`.
  - Pass it with `--file`.
- Permission rule paths:
  - a bare path is relative to the working directory
  - `//abs/path` is absolute
  - a single leading `/` is relative to the settings file
  - use `Edit(...)`, not `Write(...)`: Edit rules cover all file-editing tools
- The Claude sign-in on the Mac expires (2026-11-11..14). Unattended runs need `claude setup-token`.
- Runs read files only in the workspace and `~/.claude/skills` (`Read(//abs/**)` rules, which also cover
  Glob and Grep; never a bare `Read`/`Glob`/`Grep`, those allow every path), with `.env` and `~/.config`
  denied. desk 2.0+ gets a pass per claimed request (`X-Desk-Claim`, env `DESK_CLAIM`): a run's calls
  reach only that request and its account. A new agent route needs nothing extra (`agent_required`
  binds it); one that takes a task id from the body must check `desk_api.claimed_task()`.
- Never give a run a shell tool that takes a path (`ffmpeg`, `ffprobe`, `ls`, `cp`, `node`): the
  permission checker doesn't look at the paths those commands open, so they read past every `Read`
  deny rule, and `ffmpeg` / `node` send over http. Add a `desk` subcommand that checks the path
  (`desk.media_input`: realpath inside the workspace) instead. Render and advice runs still have them
  (open risk, needs `sandbox-exec`).
- The meta-ads workspace is shared by every business: a run for another account or from a teammate
  gets deny rules for the other briefs, `state/`, `reports/*.md|html` and `reports/desk/*.md`
  (`bridge.private_paths`). Other clients' `creatives/` folders stay readable, and the Meta MCP
  read tools, `CLAUDE.md` and Claude's memory reach every account: per-client isolation there is the
  skill's instructions only. A cleaner fix is per-client folders (`clients/<account_id>/`).

**Server and nginx**
- nginx can cache a stale backend IP after a container is recreated. The installer recreates nginx last on Update; the ads location resolves per request (`resolver 127.0.0.11`).
- An `add_header` inside an nginx location drops the server-level CSP. Use `expires`, or repeat the headers.
- `GUNICORN_WORKERS=1` with threads. The background loop takes a Postgres advisory lock, so only one runs.

**Meta data and sync**
- Ads missing from Meta's list are marked DELETED only when the list came back non-empty (`if seen:`). Keep that guard.
- Meta's lists leave archived and deleted objects out. `status_history.mark_missing` reads the missing ids by id and
  stores ARCHIVED or DELETED as Meta says, and skips rows another sync stored after this listing was read (`listed_at`).
  A sync upsert skips a row the console wrote to Meta after the listing started (`UNLESS_CONSOLE_WROTE`, via `meta_changes`).
- Field-set fallbacks (`sync.with_fallback`) are only for Meta refusing a field; timeouts, cooldowns, rate limits and 5xx
  are raised. Rows read with the older set are `_partial` and keep the stored issues, configured status and times.
  Pass `shape` ("list", "ids" for a `?ids=` read, "one" for one object by id) so the right rows get the flag.
- `today_snapshot` carries the account day it belongs to and every pull refills it; readers use `insights.today_for` and
  ignore another day's. The fatigue rule divides by Meta's unique 7-day reach, never by daily reach added up; while
  Meta doesn't answer that reach (`reach_7d` None) open fatigue alerts stay open (`alerts.to_resolve`).
- Background work started by a request (`ads_api.resync_later`) runs in a plain thread with `account_ctx.use` +
  `db.reusing()`, never a copied context: Flask's app context (and the request's connection) would come with it.
  It is debounced per process (3 s after the last write) and takes the advisory lock `resync:<account>`, so two
  gunicorn workers never re-read one account at once; a held lock postpones the re-read, it never blocks a request.
- Meta video uploads go to `graph-video.facebook.com` (`meta_client._base(video=True)`), chunked start/transfer/finish.
- A page never waits on Meta reads one after another (audit A3-46). Several reads go through `meta_client.read_many`
  (parallel, one thread per read up to `PARALLEL_READS` 16, `READ_TIMEOUT` 8 s, one deadline for all; a read that never
  started is `not_asked` and not remembered); reach windows through `insights.reach_many` (one meta_cache query, the cold
  ones read together, the last stored answer when Meta is quiet, only if under `insights_api.STALE_MAX`, a day). A read Meta left unanswered is remembered for
  `FAIL_SECONDS` per account and key (`meta_client.remember_failure` / `recently_failed`, also inside `insights_api.cached`),
  so a slow Meta costs one wait every two minutes, not one per load. Refusals aren't remembered. The worker keeps Meta's
  full timeout (`unique_reach`). Several items of one kind: one `?ids=` read (`bulk_api.live_nodes`), budgets through one
  `spend_context` memo per request. QA can hang the fake's reach reads (`/fake/_slow?reach=<s>`) and count Graph calls (`/fake/_hits`).
- Budgets: `cents()` helper; the UI always shows dollars.

**Dev and QA**
- The dev seed (`dev_seed.py`) uses fake IDs `ad-0..ad-4`. Never run it on the server. A Desk report quoting those IDs came from a local run.
- Local test flows must cancel any polish task they queue, or the Mac bridge picks it up.
- Dev runs gunicorn with reload: saving a new migration file applies it at once, so a migration
  written in two steps lands half-applied in dev (it's already recorded). Write each migration in one go,
  or fix dev by hand. Production applies the whole file.
- Every write to `/api/` needs `X-Requested-With: ebads` or a JSON body (cross-site guard); `api.js`
  sends it, QA's direct `fetch()` calls get it from an init script.
- The `users` table has no row-level security. Anyone told about an account's leads, alerts or Claude runs
  comes from `notify.admin_ids()` or `leads.staff_for()` / `recipients_for()`, which keep the console's owners
  plus that account's own people (`notify.serves`). Lead emails go out one per recipient.
- Which account owns a Page, ad account or dataset: `settings_store.meta_holders(key)`. It includes account 1's
  built-in `config.META_DEFAULTS`, which are usually not stored as rows. Lead routing skips closed accounts
  (a lead for a Page only a closed account names is dropped and logged, never filed under account 1, whose
  Page token can't read it), and the duplicate check keeps a closed account's assets taken, because ids are
  unique across accounts. The duplicate check refuses only a change: a value the account already holds is
  re-sent by every Settings save and stays allowed.
- A lead is stored only by `leads.store_lead` (webhook, catch-up, Refresh, Settings sync) and told about only
  by `leads.announce`: email, phone alerts and automatic reply are queued under dedupe keys, then
  `leads.alerted_at` is claimed and one `lead.received` line written; `announce_pending` in the worker
  finishes any lead a pass left unannounced (last 24 h). The new-lead email goes through the `notifications`
  queue (retried, HTML in `notifications.html`). `alerted_at` defaults to now(), so leads inserted any other
  way (dev seed, QA) never alert. Test lead = Testing Tool dummy answers (`<test lead: …>`), or no ad and not
  `is_organic`; organic form leads are real. Failed lead pings back off (`webhook_events.attempts` /
  `next_attempt_at`); Settings' Try again forces them. Meta's webhook Test sample (lead 444444444444) is closed
  without a Meta call. A lead email the queue gives up on writes `lead.email_failed` under the lead's account.
  Live checks owed: a real organic Instant Form lead arrives with `is_organic` true and no `ad_id`; the
  `is_organic` value and answers of a Lead Ads Testing Tool lead; the code/subcode of the webhook Test sample.
- Money rules live in `money_rules.py` (ceiling, +20%, reading Claude's amounts) and the ceiling in
  Settings → Targets. Anything new that sets a budget goes through them.
- The fake Meta's "refuse the next ad" must not use a rate-limit code (17, 4, 613, 80004): those now
  pause the account for five minutes.

---

## 6. Progress log

Append one line per session: date · steps touched · commits · what's next / blocked on.

- 2026-11-09 · roadmap written (this file) · — · next: Phase 0 (Eugene: Update + setup-token), then 0.3 verification with Eugene
- 2026-11-09 · console redesign "Seal & ledger" (design A, Plus Jakarta Sans, Impeccable polish; design files + system in ads/.superdesign/) and a Refresh button on every screen (`POST /api/refresh`: ads, last 3 days, today's spend, catches up missed form leads; 60 s throttle) · next: Eugene runs Update; leadgen webhook field still unsubscribed in the Meta app (Page → leadgen), needs his OK to switch on
- 2026-11-09 · 65ae275 (tab labels, Only mine filter dropped) is live on the server; 0.1 done (server serves the c05e30a/65ae275 frontend), 0.2 done (Keychain `ads-desk-claude` holds the setup-token) · next: 0.3 verification with Eugene; leadgen webhook switch still needs his OK
- 2026-11-09 · 0.3 verification run with Eugene approving each write: 11/13 pass (table in section 3); fixes: delivery estimate without the retired `estimate_dau`, webhook events give up on missing leads / after 24 h, bridge 1.2 keepalive stops quietly once the skill closed the task, empty charts label only $0, "starts delivering" wording · test ads left PAUSED: 120252689342970312, …366370312, …383970312, …507540312 · next: Eugene pushes + Update, adds `pages_read_user_content` to the token; then 0.4 render run (proposal 4 on N1 is a ready "Make a new version")
- 2026-11-09 · a61b65b pushed to main · waiting on Eugene: Update + his own test pass; then 0.4 render run
- 2026-11-09 · 0.3 j passes live (estimate 10.4M–12.3M) · 0.4: render task 3 on N1 (from polish #2) ran headless in 9 min, uploaded 2 videos + 2 stills, proposal 5 "N1 · v2"; fixes: render runs may append to `reports/log.md`, playbook says how to copy files (`cp` in a chain was refused), bridge 1.3 installed · 1.1 built: `crm_events.py` + migration 006, queue on new lead and stage change, worker sends with backoff (24 h give-up, invalid lead → failed at once), Settings panel (dataset, switch, test event), lead page line, Home warning, part H guide; 64 unit tests, QA 24 PASS
- 2026-11-09 · 347e58c pushed · proposal 5 approved → N1 · v2 120252690325970312 PAUSED, $0 (now 5 test/new ads paused; never delete) · follow-up: a render proposal carries one video, so the 9:16 upload (2015174525716803) isn't attached (needs placement asset customization) · next: Eugene runs Update + part H test event (1.1), then 1.2 needs his alert-channel choice
- 2026-11-09 · progress marked: 0.3 12/13 (h waits on the token), 0.4 done, 1.1 built and pushed (live test waits on Update + part H) · new **Open issues** list I1–I9 in section 2 · next: Eugene picks which issues to fix first, before 1.1 live test / 1.2
- 2026-11-09 · I10 archive + delete built (unit tests + QA flow: refuse when on, archive hides, Show archived, wrong name refused, delete) · Eugene swapped N1 → N1 · v2 himself (v2 ACTIVE, N1 PAUSED, logged) · next: push + Update, then Eugene picks the next issues
- 2026-11-09 · I11 Claude page rebuilt (Impeccable shape → build; decisions/by ad/all runs; Meta previews of proposed ads; dev copy of the real Desk in `dev/seed_desk.py`); unit tests OK, QA 41 PASS · next: Eugene pushes + Update, check a live preview
- 2026-11-09 · I12 automatic refresh (Settings interval, worker pull, pages catch up by themselves); 85 unit tests, QA 45 PASS · next: Eugene runs Update and tests
- 2026-11-09 · I2, I3, I5, I6 fixed (preview loader shared by ad page and Claude page, test-leads toggle, lead's Meta line follows itself, CRM wording while off); 85 unit tests, QA 48 PASS · next: Eugene pushes + Update; open: I1/I8 (Eugene), I4, I7, I9, I11 live check, then 1.2 (alert channel)
- 2026-11-09 · 1.2 Telegram alerts built (Settings bot, account linking, notify queue, lead alert in 1 s in QA); unit tests OK, QA 54 PASS · next: 1.3 manual replies + auto switch, 1.4 reminders
- 2026-11-09 · 1.3 lead replies built (manual composer, templates, optional automatic reply); fixed: opening leads.html#lead=X could show the newest lead instead (load race); dev mail catcher on fake-meta:1025; QA 61 PASS · next: 1.4 reminders
- 2026-11-09 · 1.4 reminders + response line built; Phase 1 code complete (1.1–1.4 wait on Eugene's live steps: part H test event, Telegram bot + link, reply wording/booking link); 100 unit tests, QA 65 PASS · next: Phase 2 (2.1 Desk schedules, 2.2 alerts engine, 2.3 pacing)
- 2026-11-09 · 2.1 Desk schedules built; Desk results now reach Telegram/email; QA 72 PASS · next: 2.2 alerts engine
- 2026-11-09 · 2.2 alerts engine built; QA 78 PASS · next: 2.3 pacing and forecast
- 2026-11-09 · 2.3 pacing built; Phase 2 code complete (2.1 schedules, 2.2 alerts, 2.3 pacing); 120 unit tests, QA 81 PASS; committed, not pushed · next: Eugene pushes + Update, switches on schedules, links Telegram; then Phase 3 (experiments)
- 2026-11-09 · Results: ads table sorts by any column (kept per browser), filters Spent money / Running / All, Find an ad, total row, cost from fewer than 3 leads in grey, names open the ad; figures show the change vs the same number of days before; campaign picker (when there's more than one, ?campaign= in the URL); Telegram kept, unused (email covers everything); 122 unit tests, QA 93 PASS · next: Phase 3 (3.1 experiments tracker)
- 2026-11-09 · 3.1 experiments tracker built (Tests page, verdict rules, Claude can suggest a test); 134 unit tests, QA 104 PASS; pushed · next: 3.2 Meta A/B tests (needs Eugene's call: they split the audience and budget on Meta)
- 2026-11-09 · 3.2 Meta A/B tests built and switched off (Settings switch, Run on Meta with cost confirmation, Meta's result next to ours, end early); 145 unit tests, QA 115 PASS; pushed · next: Eugene runs Update; then Phase 4 (build everything from the console)
- 2026-11-09 · 4.1 lead form builder built (Lead forms page, policy check, phone preview, copy, New ad form picker); unit tests OK, QA 126 PASS; committed, not pushed · next: 4.2 new ad set
- 2026-11-09 · 4.2 new ad set built (starts from the live one, place search, live estimate, created paused, then New ad); unit tests OK, QA 134 PASS; committed, not pushed · next: 4.3 new campaign wizard
- 2026-11-09 · 4.3 new campaign wizard built (one page, everything off, resumable after a refusal, publish with the budget typed, ads → ad set → campaign); unit tests OK, QA 144 PASS; committed, not pushed · next: 4.4 Advantage+ creative switches
- 2026-11-09 · 4.4 automatic changes built; Phase 4 code complete (4.1 forms, 4.2 ad sets, 4.3 campaign wizard, 4.4 enhancements); 179 unit tests, QA 149 PASS; pushed · next: Eugene runs Update; Phase 5 (creative intelligence)
- 2026-11-09 · 5.1 concept tags built (seeded N1–N5, By idea on Results, tag suggestions from Claude); unit tests OK, QA 156 PASS; committed, not pushed · next: 5.2 swipe file + competitor watch
- 2026-11-09 · 5.2 swipe file + competitor watch built (Research page, weekly Competitor check schedule off, desk 1.4); unit tests OK, QA 164 PASS; committed, not pushed · next: 5.3 Meta's own advice
- 2026-11-09 · 5.3 Meta's advice on Today (score, suggestions, apply with the +20% warning, benchmarks from the Monday summary); Phase 5 code complete (5.1 ideas, 5.2 swipe file, 5.3 advice); unit tests OK, QA 172 PASS; pushed · next: Eugene runs Update, turns on the Competitor check and adds watched Pages; Phase 6 (smaller gaps)
- 2026-11-09 · 6.1 comments reply / hide built; qa/run.sh also clears the Meta cache; unit tests OK, QA 179 PASS; pushed · next: fix Results ads table names (Eugene's screenshot), then 6.2 tracking health
- 2026-11-09 · fix: ad names blank on Results for people with an ad blocker (EasyList hid .ad-cell, .adset, #ads-panel …): ad-like class and id names renamed to cr- / aset, a QA guard added; the Ad column now stays in view when the table scrolls at any width; QA 180 PASS; pushed
- 2026-11-09 · 6.2 tracking health built (Settings panel, quiet-dataset alert); unit tests OK, QA 184 PASS; pushed · next: 6.3 installable app
- 2026-11-09 · 6.3 installable app + push built; Phase 6 code complete (6.1 comments, 6.2 tracking health, 6.3 app + push); unit tests OK, QA 191 PASS; pushed · next: Eugene runs Update, installs the app on his phone and turns on notifications; then Phase 7 only if he decides on agency mode
- 2026-11-09 · 7.1 several accounts (row-level security) + 7.2 read-only client logins built; unit tests OK, QA 200 PASS (leak test included); committed, not pushed · next: 7.3 client reports
- 2026-11-09 · 7.3 client reports built (five parts, share link, print to PDF, scheduled email); Phase 7 code complete (7.1 accounts with row-level security, 7.2 read-only clients, 7.3 reports); 224 unit tests, QA 208 PASS; committed, not pushed · next: Eugene pushes + Update; adds BURDANOVAHAIR as an account when Meta access is shared
- 2026-11-10 · Phase 7 pushed (b15d367, c9665f6). Audit 2 run (4 parallel reviews): 25 gaps A1–A25 listed under Status, ranked; waiting for Eugene to pick what to fix.
- 2026-11-10 · Audit 2 fixed (A1–A24; A25 is the live-check list). Migration 022 (proposal `applying`, `campaign_members` under RLS, `campaign_builds.client_key`, `users.session_version`). 251 unit tests OK, QA 230 PASS, leak test clean for 5 roles. Playwright for QA: the render pipeline's copy lost its package files, flows/shots now pick an intact 1.64 copy. Pushed · next: Eugene runs Update, sets Targets, checks the live list A25
- 2026-11-10 · Phase 8 redesign planned and approved (research: IA map, backend gaps, 2026 ad-tool UX benchmark); plan in docs/REDESIGN.md · next: 8.0 mockups, 8.1 status history in parallel
- 2026-11-10 · 8.0 three directions mocked (Signal / Ledger / Studio, 5 screens each); Eugene picked A · Signal · next: 8.1 status history
- 2026-11-10 · 8.1 status history built (migration 023, status_history.py, sync diffing, History timeline); 269 unit tests, QA 233 PASS; committed, not pushed · next: 8.2 status alerts + Inbox
- 2026-11-10 · 8.2 status alerts + Inbox API built; 281 unit tests, QA 235 PASS; committed, not pushed · next: 8.3 ad-account webhooks
- 2026-11-10 · 8.3 ad-account webhooks built (parse/route/refetch, switch, setup part I); 288 unit tests, QA 239 PASS; committed, not pushed · next: 8.4 APIs
- 2026-11-10 · 8.4 APIs built (ranges, compare, campaign/ad set pages, timeline, search, saved views, bulk); 316 unit tests, QA 250 PASS; committed, not pushed · next: 8.5 new shell + CSS (Signal)
- 2026-11-10 · 8.5 Signal shell built (tokens, fonts, grouped nav, ⌘K palette, breadcrumbs, section tabs, phone tabs, Inbox page); QA 254 PASS; committed, not pushed · next: 8.6 Ads manager rebuild
- 2026-11-10 · 8.6 Ads manager rebuilt (table + views + bulk + peek + phone list, campaign and ad set pages); QA 262 PASS; committed, not pushed · next: 8.7 compare page, Today queue, Insights/Claude/Settings, Leads filters, 301s
- 2026-11-10 · 8.7 Compare page, Today Inbox card, Leads source filter, Settings side list, ad-safe file names; QA 267 PASS; committed, not pushed · next: 8.8 finish (shots, docs, live checks list)
- 2026-11-10 · 8.8 finish pass (screens, docs, inventory); 317 unit tests, QA 267 PASS; Phase 8 code complete, pushed 2026-11-10 (d24efac…37547ca) · next: Eugene → Update on the VPS → live checks 8.8 (1)–(6)
- 2026-11-10 · 5.4 Fix Meta's advice with Claude (advice runs, 9:16 update proposals, placement creative with read-back), bridge 1.7 installed on the Mac; 344 unit tests, QA 279 PASS; not committed · next: Eugene says commit/push → Update → first live Fix with Claude on the Reels advice
- 2026-11-10 · 5.5 update ads in place (same ad keeps its ID and results, per-version results, switch back, either way round); 418 unit tests; not committed · next: Eugene says push, runs Update, then `bridge/install.sh`; first live test on one ad with his yes
- 2026-11-10 · Phase 9 started (UI/UX audit, plan in `docs/UX-AUDIT.md`): 9.0 baseline shots + clickable mockup in `.superdesign/audit/` waiting for Eugene; 9.1 broken items fixed, QA 364 PASS, 418 unit tests, leak test clean; next: Eugene's mockup review, then 9.2
- 2026-11-11 · Audit 3: 134 verified findings fixed in 9 clusters and pushed (cf2398a…73c4622), 572 unit tests, QA green with exit code now honest; migrations 031–035 run on the next Update (034 signs everyone out once); bridge 2.0 needs `ads/bridge/install.sh` after the Update. Live checks owed: Telegram fallback on a blocked bot, organic form leads (is_organic), webhook Test sample code, lifetime_budget/end_time fields, ad_studies listing, ?ids= reads, archived ad read-back, backfill chunks, /activities budget extra_data, a headless run's Grep/Glob under Read(//…) rules, an account-2 render upload. Feature specs committed in `docs/features/`
- 2026-11-11 · 9.2a design system part 1 (tokens + accessibility) built, review fixes applied (phone summary markers, toasts inside open dialogs for screen readers, one Tab stop per table, Accept sheet + Compare summary QA, manifest colours, Settings group names on phones, charts at true size on phones); 572 unit tests, QA 456 PASS; pushed · next: 9.2 part 2 (components, one vocabulary, dead CSS)
- 2026-11-11 · 9.2b design system part 2 (one set of components in `app.css`, `suggest.js` Suggestion card, one vocabulary in `format.js` WORDS/EXPLAIN and server messages, 26 dead classes gone) plus review fixes (one Status, Inbox tabs, inline card names, Polish words, QA for inline Accept/Decline and Team's password); 574 unit tests, QA 469 PASS; pushed · next: 9.3 navigation from everywhere
- 2026-11-11 · 9.3a navigation part 1 (entity links everywhere, reverse links, one shared date range incl. the ad's daily charts, filtered breadcrumbs, ?from= + Cancel, Back closes overlays) plus review fixes (Inbox filters no longer overruled by #item, phone list keeps scroll + focus, short phone pages start under the top bar, one link colour in facts, made note said once, client sees no form/test links); 584 unit tests, QA 513 PASS; pushed · next: 9.3b (⌘K everywhere, phone Ads/bulk bar/More badge, 404 and offline pages)
- 2026-11-11 · 9.3b navigation part 2 (command menu reaches pages, tabs, Settings sections, saved views, actions, forms, tests and swipes with aliases; fair search so leads stay; "?" shortcuts; phone Ads sort + campaign, bulk bar that fits at 320, More badge + Claude first; 404 page; offline page that reconnects by itself); 594 unit tests, QA 532 PASS, leak test clean · next: 9.4 every tab redesigned. **After Update:** nothing extra (nginx is recreated, so `error_page` loads)
- 2026-11-11 · 9.3b review fixes: Refresh from Meta is staff-only in the command menu (client menu checked in QA), "Results: By idea" scrolls to its panel once drawn (clears the phone bars), Claude: Schedules and Inbox: Money opened from the menu in QA, phone Sort says "Sorted by click rate" for a computer sort, Claude's count has screen-reader text instead of aria-label on a span, leak test seeds account 2's lead form; 594 unit tests, QA 537 PASS; pushed · next: 9.4 every tab redesigned (Creative first in More with 9.5)
