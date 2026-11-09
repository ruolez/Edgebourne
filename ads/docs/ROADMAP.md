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
- [ ] I4 A render proposal carries one video, so N1 · v2's 9:16 upload (2015174525716803) isn't used. Needs placement asset customization (4:5 for feeds, 9:16 for Stories/Reels) in the creative builder.
- [x] I5 (fixed: the line re-checks itself at 3, 6, 9, 12 s while anything is pending) Lead page "Meta has …" line (1.1) shows "on its way" right after a stage click and only updates when the lead is reopened; re-fetch a few seconds after the change.
- [x] I6 (decided: keep queueing, Meta takes 7 days back; Settings now says "N saved, sent once you turn this on" instead of "waiting") Stage events queue while the 1.1 switch is off and show as "waiting"; decide: queue only when on, or keep (Meta takes 7 days back, older ones are skipped).
- [ ] I7 Creative files: local `creatives/2026-11-07-new5/out/N1-9x16*` still carry the banned "Free workflow review" wording (polish #2 report). Not in any live ad; rebuild or delete before reuse.
- [ ] I8 **[Eugene]** Money: the $150 manual account cap ($35.31 used on 2026-11-09) stops all ads around Nov 15. Raise it or let it stop, his call.
- [x] I10 Archive and delete ads from the console (Eugene asked for both, 2026-11-09): ad page buttons, admin only, only when the ad is off; delete needs the ad's name typed; archived ads hide on the Ads page behind "Show archived"; every one lands in meta_changes. Meta: archived → only deleted, never back on; both keep their numbers. Sync no longer turns an archived ad into "deleted" when Meta's list leaves it out.
- [~] I11 Claude page was hard to read (Eugene, 2026-11-09: mixed, repeating, unclear what's for which ad or in what state; wanted previews). Rebuilt: tabs Waiting for you (pending decisions grouped by ad, each with Meta's preview via `act/generatepreviews`, old → new changes, one-line why, Create (off) / Edit / Decline) · By ad (ad families: an ad plus every ad made from it, runs as a timeline with each idea's outcome and a link to the ad it made) · All runs (reports and scorecards folded). Ask Claude is a button. `desk_view.py` (pure, tested) + `board.js`; render runs now store `from_proposal`. Built and tested locally; live check of the preview after push.
- [x] I12 Data didn't update by itself (Eugene, 2026-11-09: "I don't want to always click Refresh"). Settings → Automatic refresh (every 5 / 10 / 15 / 30 min / hour, default 15): the worker runs the Refresh pass on that interval (counted from the last pull by anyone; a failed try waits 5 min). Open pages check every minute and when they come back into view, and reload their data when the server has newer data, unless someone is typing or a dialog is open. The Refresh button's tooltip shows the interval.
- [ ] I9 Paused ads keep piling up (4 test ads from 0.3 + N1 · v2, never deleted). Consider a "Tests" filter or a naming rule so the Ads page stays readable.

### Phase 1: Close the loop with Meta
- [~] 1.1 Lead stages sent to Meta (Conversions API for CRM) (built and tested locally; Eugene: META-APP-SETUP part H, then a live test event)
- [ ] 1.2 Instant alert to Eugene's phone for every new lead (channel = open decision)
- [ ] 1.3 Automatic first reply to the lead (email)
- [ ] 1.4 Untouched-lead reminders (5 min, 1 h, next morning) and a lead-response report

### Phase 2: Works without being asked
- [ ] 2.1 Desk schedules (daily health, 3-day review, Monday summary, monthly audit)
- [ ] 2.2 Alerts engine (rules checked after every sync, sent to the 1.2 channel)
- [ ] 2.3 Spend pacing and month-end forecast

### Phase 3: Experiments
- [ ] 3.1 Experiments tracker (hypothesis, arms, metric, dates, verdict)
- [ ] 3.2 Meta A/B tests created from approved proposals and read back

### Phase 4: Build everything from the console
- [ ] 4.1 Lead form builder
- [ ] 4.2 New ad set (audience, placements, schedule, budget), created paused
- [ ] 4.3 New campaign wizard (campaign + ad set + ads + form, all paused, one approval)
- [ ] 4.4 Advantage+ creative enhancements: see them per ad, turn each on/off

### Phase 5: Creative intelligence
- [ ] 5.1 Concept tags (hook, angle, format, persona) and results by concept
- [ ] 5.2 Swipe file + competitor watch
- [ ] 5.3 Meta's own advice: Opportunity Score, recommendations, benchmarks

### Phase 6: Smaller gaps
- [ ] 6.1 Reply to / hide comments from the console
- [ ] 6.2 Tracking health (dataset quality) panel
- [ ] 6.3 Installable app (PWA) with push notifications

### Phase 7: Agency mode (only if Eugene decides to run client accounts)
- [ ] 7.0 **[Eugene]** Decide: will the console run other businesses' ads (e.g. BURDANOVAHAIR)?
- [ ] 7.1 Several ad accounts in one console
- [ ] 7.2 Client logins limited to their account
- [ ] 7.3 Client reports (link and PDF, scheduled)

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

**Server and nginx**
- nginx can cache a stale backend IP after a container is recreated. The installer recreates nginx last on Update; the ads location resolves per request (`resolver 127.0.0.11`).
- An `add_header` inside an nginx location drops the server-level CSP. Use `expires`, or repeat the headers.
- `GUNICORN_WORKERS=1` with threads. The background loop takes a Postgres advisory lock, so only one runs.

**Meta data and sync**
- Ads missing from Meta's list are marked DELETED only when the list came back non-empty (`if seen:`). Keep that guard.
- Meta video uploads go to `graph-video.facebook.com` (`meta_client._base(video=True)`), chunked start/transfer/finish.
- Budgets: `cents()` helper; the UI always shows dollars.

**Dev and QA**
- The dev seed (`dev_seed.py`) uses fake IDs `ad-0..ad-4`. Never run it on the server. A Desk report quoting those IDs came from a local run.
- Local test flows must cancel any polish task they queue, or the Mac bridge picks it up.

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
