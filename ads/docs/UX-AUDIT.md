# Ads Console: UI/UX audit and improvement plan (Phase 9)

## Context

The console (`~/Desktop/Dev/edgebourne/ads`, live at ads.edgebourne.com) has every roadmap feature, but it was built in many separate rounds. Eugene asked for a full audit of every tab, ideas from how leading ad platforms and marketing teams work, the gaps closed, and easy navigation from anywhere.

**Eugene's decisions (2026-11-10):**
- Scope: design and workflows. Fix every tab and add the missing creative flows. No automation rules this round.
- New **Creative** section in the sidebar. Research moves out of Claude.
- Keep the **Signal** look and refine it.
- **Clickable mockup first**, then build phase by phase.

**Fixed constraints:**
- Vanilla JS, multi-page, no build step, strict CSP.
- Every existing feature stays.
- Money rules do not loosen: every budget, status and publish step keeps its current confirmation.
- New class, id and file names must pass the existing ad-blocker guard (`qa/flows.cjs:1514`). Don't reuse `.sheet` (the phone More dialog), `.step`, `.report`, or `.confirm` outside confirm dialogs.
- `qa/flows.cjs` stops at its first missing selector, so every UI change updates it in the same commit. Roughly 32–55 of its 356 checks are affected across this work.
- Pinch zoom stays off. Eugene asked for that in 8.11, even though accessibility guidance prefers it on.
- Commits follow ROADMAP §4. Push only when Eugene says so.

## What the audit found

**How it was checked:** live text and layout of every page on the dev stack, tonight's QA screenshots, a phone-width spot check of Ads and Today, and two full code sweeps. Screens with no recent screenshot were judged from their live text and code, so Phase 0 starts with a full screenshot pass.

**The biggest problems:**

| Area | Finding |
|---|---|
| Getting around | Campaign, ad set, form, test and tag names are plain text in about 16 places where the page already has the id. There is no way back to where you came from: New ad, New ad set and New campaign have no Cancel and always exit to Ads. |
| Losing your place | Default date ranges disagree (Ads 7, Campaign 14, Compare 14). Breadcrumbs drop filters. Phone Back leaves Leads instead of closing the lead. |
| Losing work | Refresh reloads forms and wipes them. A stage click wipes a half-written note. One Settings save refills other panels. Today rebuilds itself every 60 seconds. |
| Wrong or broken | Compare opened from the Ads bulk bar loses "vs before". Results can show the wrong period with no warning. ⌘K to a lead does nothing while on Leads. "Claude is on it" links nowhere. Danger buttons turn white-on-pale on hover (1.16:1). |
| Too much at once | Settings is one page 18,931 px tall. Ad Overview is about 3,040 px of stacked cards. Today repeats Inbox and Leads and runs 4.2 phone screens. Inbox counts routine notices the same as rejections. |
| One thing, many names | Views / Impressions / Shown. Hook rate / Stopped scrolling. Delivering / On / Running / Active. Suggestion / proposal / idea. Run / job / task / conversation. |
| Inconsistent parts | 6 tab styles, 5 table styles, 9 dialog builds, 28 font sizes, 23 corner radii, 26 shadows, leftover teal from the old look. |
| Accessibility | Green text fails contrast in light theme. White on green fails in both themes. Peek drawer can't be used by keyboard. No skip link. Phone Ads has 66 controls under 44 px. |
| Workflow gaps | No visual view of what's working. Research has no route to making an ad. Test winners have no next step. Nothing joins research, idea, ad, test and lesson. |

**What's already strong and must be kept:** New campaign's typed-budget publish and partial-build recovery, the bulk preview, the Accept sheet, the Tests empty state and phone cards, and Claude's phone layout.

**What the market research adds:**
- Motion/Runneth puts creative next to its numbers, merges identical creatives across ad sets, and reports by tag. → Gallery.
- Foreplay keeps swipe file, competitor tracking and briefs in one place. → Creative section, swipes to brief.
- The usual creative testing loop is explore, validate, scale, with fatigue flags and a record of what was learned. → Launch view, next steps on test results.
- Linear makes the command menu and triage the core of the app. → Fuller ⌘K, Inbox triage.
- Review UX research: show evidence beside the action, make edit and reject as easy as approve, re-check stale data. → Claude and Inbox.
- NN/g: breadcrumbs show the hierarchy, and on phones show only the last level or two. → Keep hierarchy crumbs, carry filters separately.

## Target structure

| Group | Item | Tabs |
|---|---|---|
| Work | Today | one prioritised queue |
| Work | Inbox | Needs action / FYI |
| Work | Leads | unchanged |
| Run | Ads | Ads, Lead forms |
| Run | **Creative** (new) | Gallery, Ideas (everyone); Research (admins) |
| Run | Insights | Results, Compare, Tests, Reports |
| Run | Claude | Conversations, By ad, Schedules |
| | Settings | one section at a time, Team |

Phone tabs stay Today, Leads, Ads, Inbox, More. More carries a badge when Claude has decisions waiting and lists Claude and Creative first.

## Phases

Each phase ships on its own and follows ROADMAP §4: tests first for pure logic, fake Meta, QA, tick ROADMAP. Add a **Phase 9** block to ROADMAP §2 and save this plan as `ads/docs/UX-AUDIT.md` when work starts.

### 9.0 Baseline and clickable mockup (Eugene reviews before 9.2)
- Extend `qa/shots.cjs` to every tab and Settings section, light and dark, desktop and 390 px.
- Build a clickable mockup in `ads/.superdesign/audit/` on the real tokens: new sidebar, Today queue, Inbox triage, Gallery, Ad page, Settings, phone nav.
- Settle the design-system conflict: desktop stays dense, smallest label 12 px, phone controls 44 px. Update `.superdesign/design-system.md`.

### 9.1 Fix what's broken (can run during mockup review)
- `manager.js:288` sends `vs=1`.
- Results: validate the saved range and support `mtd` / `lastmonth`, sharing `ranges.py`.
- Leads: listen for `hashchange`, and close the detail on an empty hash. Claude: fix `#list` on desktop and the `#runs` link (`home.js:200`, use `#r/<id>`).
- `.btn-danger:hover`. Rename the colliding `.report`, `.cr-card`, `.changes`.
- Refresh on form pages refetches instead of reloading. Add a leave warning to New ad, New ad set, New campaign, Lead forms and Settings.
- Stage and owner changes keep typed notes and email. Settings saves only touch their own panel. Today skips its refresh while someone is typing (export `editing()` from `ui.js`).
- One shared error state with Retry, built here and reused later. Handlers attach first (`settings.js:326`, `team.js:63`, `api.js:7`). "Not found" only for real 404s.
- List unfinished campaign builds on Ads, with a new list route in `builds_api.py`.
- Hide Reports from team members or allow it, matching the server.
- Test-tag regex no longer catches "- copy". Bulk Archive is admin only, matching the ad page (`bulk_api.py`).
- Confirm on Team deactivate, password reset, and raising the budget ceiling. Undo on single Claude Decline.
- Security: `login.js:15` refuses `//host` redirects.
- Remove Edge Bourne wording from other accounts. Use the account's currency instead of hard-coded `$`.

### 9.2 One design system (after mockup approval)
- `tokens.css`: spacing, radius, type and shadow scales. Fix contrast pairs for both themes. Retire `--seal`, `--rust`, `--pine`, `--fog` and the old teal, ink and tints.
- Consolidate to one Tabs, Filter, Status, Date range, Table, Dialog, Empty state, Skeleton and Suggestion card (`tasks.js` and `board.js` today). Reuse `confirmDialog`, `manager.js` columns, `format.js`. Remove dead CSS and 40/32 px gutter differences.
- `format.js` becomes the single vocabulary: Views, People reached, Hook rate, Cost per lead, Delivering / Off / In review / Rejected, Suggestion, Accept, Conversation. Plain explanations for Advantage+, learning limited, swipe file.
- Accessibility: skip link, real tablists, `aria-invalid`, focus handling in dialogs and the peek drawer, keyboard table rows, reduced motion, chart summaries, safe default focus on money dialogs, toasts above dialogs, 44 px phone targets.

### 9.3 Navigation from everywhere
- Shared `entityLink()` in `ui.js`. Apply to every plain-text case found: ad page, lead detail, Today, test arms, Compare, Report (signed-in view only), proposals, alerts, Team, build results. Add ids to `concepts_api` and `insights_api` responses where missing.
- Reverse links: campaign → its leads and results; ad → its tests and Compare.
- Keep context: one shared range across Ads, Campaign, Ad set, Ad, Compare, Results (Gallery and Ideas join in 9.5). Breadcrumbs return to the filtered list. `?from=` on New pages gives Cancel and a correct return. Successful builds link to what was made.
- History: `pushState` for lead, Inbox and peek so Back closes them.
- ⌘K: all pages, tabs, Settings sections, saved views, actions, forms, tests and swipes; find "Results", "Home" and similar aliases; don't let leads get cut off; `?` shortcut sheet.
- Phone: sort and campaign filter on Ads, bulk bar that fits, working Inbox detail, More badge.
- Friendly 404 page (`error_page` in `nginx/ads.conf`). Offline page that does what it says.

### 9.4 Every tab, redesigned on the new parts

| Screen | Changes |
|---|---|
| Today | One ranked queue (leads to call, ads with problems, decisions, money). Compact numbers. Advice and benchmarks sit below, kept open. Remove duplicates of Inbox. Clients see only status alerts and leads. Decisions open the existing Accept sheet or Claude. |
| Inbox | Needs action vs FYI, with a separate needs-action count that drives the badge (`inbox_unread` stays). Resolved items leave the count. `e` only marks read. Any approval goes through the Accept sheet, never a bare button. Built (9.4a): the badge and the Needs action tab show the same number, Needs action that is still unread (`inbox_need`), so reading an item or fixing the problem takes it off; the summary line above the list still says how many need you in all. Eugene can ask for 'open items' instead (one line in `refresh_api` + `inbox.js`). |
| Leads | One urgency rule shared with Today. Readable history. Clear-filter action. Undo on stage change. |
| Ads / Ad sets / Campaigns | Sticky header and name column, delivery-track legend, one primary New button, clear-filter empty state. |
| Lead forms | Field-level errors, leave warning, leads per form linked to Leads. |
| Campaign, Ad set | Same range, targeting shown without learning data, New button in empty state, leads link. |
| Ad: Overview | Two columns with sticky preview. Lead with status, results and Claude. Fold Words, Tags, Meta's changes. Expired preview refreshes itself. |
| Ad: Polish, Audience, Video, Comments, History | Loading and error states, plain copy, one proposal card style, timeline links. |
| Results | Period and campaign carried. Ads table points to Ads, deleted ads hidden by default. |
| Compare | Picker with thumbnails and numbers, sticky metric column, line labels beyond color. |
| Tests | Plain words. A next step on results: budget and off controls through existing confirmations, "Make more like this". |
| Reports | Earlier-period picker, "Print or save as PDF", confirm before creating a share link, print-safe colors. |
| Claude: Conversations, By ad, Schedules | Status always says the same thing (Mac offline vs idle). Polling keeps focus. Timezone on schedules. One suggestion card everywhere. |
| New ad, New ad set, New campaign | Stepper with a summary beside it, field errors, validate before the confirm. One shared uploader with cancel and retry, also usable inside New campaign, which ends the empty-account loop. |
| Settings | One section at a time. Any existing anchor (`#meta-form`, `#mt-form`, `#tracking`, `#meta`, and links stored in alerts) resolves to its section. Grouped This account / Whole console, specific Save labels, technical fields under Advanced. |
| Team, Account, Login, Offline | Phone cards, copy password, one theme control, field-specific login errors. Built (9.4f): the theme lives on Your account only (the sidebar and More buttons are gone; ⌘K Switch theme stays); Settings' list keeps its two group names on phones (the mockup hid them; 9.2a had added them back), and Team stays a tab under Settings rather than an item in the list. |

### 9.5 Creative section and the loop
- Add the Creative section to `SECTIONS` / `SUBNAV` in `ui.js`, the phone More sheet and ⌘K. Remove Research from Claude's tabs. No URL changes.
- **Gallery** (`gallery.html`, `gallery.js`, pure `backend/gallery.py`, `GET /api/gallery`), built from stored data with no new Meta calls:
  - Cards show spend, leads, cost per lead and hook rate. Image ads show no hook rate rather than 0.
  - Group key: `video_id` + normalized title + body + button. Images group only on the same `creative_id`, because `image_hash` isn't stored and adding it is a separate change. Never merge on missing fields. Test: the same video on a new creative merges.
  - Numbers come from `ad_daily` the way `concepts_api.by_concept` does, not `tree_data`. Credit only the current version's days with `creative_versions.split_results`.
  - Filter by tag, status and range. Views: Top, Just launched (too-early rule applies), Tired (reuses the fatigue alert, with a note when that rule is off).
  - Compare from a group uses its top-spending ad, up to the 6-ad limit of `/api/compare`.
- **Ideas**: existing `/api/concepts` as visual groups by hook, angle, persona ("Who it's for"), format, offer, with thumbnails added. Verdicts keep the 3-lead and 2× target minimum. Results' By idea moves here with a summary link. Tag chips link to the filtered Gallery.
- **Research** (admins): the current page moves here, in clear parts: search, swipe file, watched Pages, past research.
- **The loop, reusing Claude runs, no new money paths, no bridge change:** on a swipe, "Make something like this"; select several, "Write a brief". Both open an editable dialog with trimmed swipe text under the 4,000-character prompt limit, POST `{kind: "creative", prompt}`, then open `#r/<id>`. Suggestions are approved as today. A winner gets the Tests next step. The lesson is kept through tags and Ideas.
- Client pass in QA: no action controls visible on any new or redesigned screen, since `.read-only` is a hand-kept list in `app.css:1221-1226`.

### 9.6 Finish
- Full QA and screenshot pass, feature inventory ticked, README and memory updated, list of what's still unverified on real Meta and real phones.
- Done 2026-11-12: `qa/shots.cjs` takes every tab and every Settings section, light and dark, desktop and 390 px (240 shots, no console errors). Fixed from them: Claude's phone tabs drawn 52 px low over New conversation, the report funnel's Share column cut at phone width, account marks wrapping in Settings → Accounts, a Settings explanation in a column of its own, "inbox" used for the leads list. The inventory below is ticked; the unverified lists are in ROADMAP §2 under Audit 3 → What Eugene does after the Update.

## Feature inventory (ticked at 9.6)

Every action from the Phase 8 inventory (`REDESIGN.md`) and where it lives after Phase 9. Nothing was dropped; moved items name their new place. Checked against the code, `qa/flows.cjs` (all green) and the 9.6 screenshots.

| Before Phase 9 | Action | Where it is now |
|---|---|---|
| Today | Needs attention, call / email a lead, Money, Ads strip, Claude card, console changes, Meta's advice + Apply + Fix with Claude, benchmarks, Ask Claude, New ad | Today: one ranked queue (leads to call, problems, follow-ups, decisions through the Accept sheet, money, upkeep, later today), Money / leads this week / Ads / Claude / Changes made from the console beside it, advice and benchmarks below [x] |
| Inbox | Feed, read / unread, kinds, detail, j / k / e | Needs action / For your information / All with one badge rule, Got it… (snooze), Diagnose with Claude, Done, `#item=` that Back closes [x] |
| Leads | Stages, owner, notes, call, email + templates, history, test leads, filter by ad / campaign | Same, plus ad set / form filters, Clear filters, Undo on stage moves, sentence history, one urgency rule with Today; call outcomes, next steps, booked calls, lost reasons, highest stage, repeats, junk [x] |
| Ads | Levels, views, saved views, ranges + vs before, columns, bulk on / off / budget / archive, Compare, quick look, cards, New ▾, unfinished builds | Same; sticky header and name column, delivery legend, one primary New, Clear filters, phone sort + campaign picker, bulk bar that fits at 320 [x] |
| Lead forms | Builder, list, copy, use in a new ad | Ads › Lead forms; field errors, leave warning, leads per form linked to Leads [x] |
| Campaign / Ad set | Figures, charts, learning, who sees it, children, History, quick look | Same; shared dates, Its leads, Results link, empty-state New, chart marks [x] |
| Ad | Status, preview, Claude, results, words, where it runs, tags, versions, Meta's automatic changes, leads, on / off, duplicate, new from this, polish, archive / delete, Audience, Video, Comments reply / hide, History | Overview: status card first, kept-in-view preview that renews itself, remembered folds; Polish / Audience / Video / Comments with loading and Try again; History one timeline with filters and "Did it work?" lines [x] |
| Results | Range, campaign, pacing + monthly target, figures, charts + day table, ads table, By idea, who and where, what changed | Insights › Results; deleted ads hidden unless asked, Open in Ads with days and campaign, Lead quality panel, By idea → one line + Open Ideas (Creative › Ideas) [x] |
| Compare | 2–6 ads, best per row, verdict, tags, lines, picker | Insights › Compare; picker cards with pictures and numbers, sticky metric column, numbered and dashed lines [x] |
| Tests | Running / finished, sides, verdict, A/B on Meta, new / edit / finish / reopen | Insights › Tests; plain words, a Next step on a winner through the usual confirmations, Make more like this [x] |
| Reports | Week / month, share link, PDF | Insights › Reports; earlier periods, Print or save as PDF, confirm before a share link, review before sending [x] |
| Claude | Conversations, By ad, Schedules, Accept / Decline + Undo, Stop, queue, Mac status, Mac key | Same three tabs; one Mac sentence everywhere, polls keep focus, schedules name the time zone, one Suggestion card [x] |
| Research | Ad Library search, Ask Claude to research, swipe file, watched Pages, past research | Creative › Research (same address) in four parts; Make something like this, Write a brief [x] |
| New ad / ad set / campaign | Builders, upload, everything created off, typed-budget publish, partial-build recovery | Same pages; stepper beside the form, field errors before any confirmation, one uploader with Cancel / Try again, `?from=` Cancel [x] |
| Settings | 14+ sections on one page | One section at a time, This account / Whole console, specific Saves, Advanced folds, old anchors still open their section [x] |
| Team, Your account, sign-in, offline, 404 | Members, roles, passwords; password, theme, alerts, Telegram, device + push; sign-in; offline page | Team phone cards + Copy password; Your account holds the one theme control (⌘K Switch theme too); field-level sign-in errors; offline reopens the page; friendly 404 [x] |
| Frame | Sidebar, account switcher, badges, refresh, spending limit, banners, ⌘K, breadcrumbs, phone tabs + More | Work / Run groups with Creative; ⌘K reaches every page, tab, Settings section, saved view, action, form, test and swipe; `?` shortcuts; More with Claude's count, Claude then Creative first [x] |
| New in Phase 9 | Creative › Gallery (copies merged, Top / Just launched / Tired, Compare from cards) | `gallery.html` [x] |
| New in Phase 9 | Creative › Ideas (idea groups with pictures, See in Gallery) | `ideas.html` [x] |
| New in Phase 9 | Gallery: "Make more like these" from picked cards (mockup) | Not built yet; the brief loop runs from Research and from a test's winner [ ] |

**Audit 3 features (the 11 Eugene picked), all shipped:** follow-up queue [x] · booked-call tracking [x] · lost reasons and lead quality [x] · repeat and junk leads [x] · snooze and lead-quality alerts [x] · Diagnose with Claude [x] · client report review [x] · edits made in Ads Manager [x] · change markers on charts [x] · "Did it work?" [x] · match Ads Manager [x] (commits in ROADMAP §2, Audit 3; where each lives in the README's Features section).

## Critical files

- **Shell and shared:** `frontend/js/{ui.js, palette.js, format.js, urlstate.js, api.js, controls.js, charts.js, manager.js}`, `frontend/css/{tokens.css, app.css, shell.css, desk.css}`, `frontend/sw.js`
- **Pages:** `frontend/js/{home, inbox, leads, listing, entity, creative, compare, performance, report, experiments, desk, board, conversation, tasks, research, forms, new-creative, new-aset, new-campaign, settings, team, account, login}.js` and their HTML
- **New:** `frontend/{gallery,ideas}.html`, `frontend/js/{gallery,ideas}.js`, `backend/gallery.py`
- **Backend touch points:** `concepts_api.py`, `swipes_api.py`, `insights_api.py`, `performance_api.py`, `builds_api.py`, `bulk_api.py`, `alerts.py`, `status_history.py`, `inbox.py`
- **QA and server:** `qa/flows.cjs` (add an `openSettings(section)` helper, keep existing form ids), `qa/shots.cjs`, `dev/fake_meta.py`, `nginx/ads.conf`, `backend/tests/test_inbox_logic.py`
- **Reuse, don't rebuild:** `confirmDialog`, `UrlState`, `setCrumbs`, `ranges.py`, `compare.shape`, `concepts.group`, `timeline.merge`, `/api/search`, `?ask=` on Desk

## Verification

- Unit: `docker exec -e WORKERS_ENABLED=0 edgebourne-ads-backend python -m unittest discover -s tests -v`, with new tests for `gallery.py` and Inbox triage.
- End to end: `ads/qa/run.sh`. Every existing check keeps passing or is mapped to its new location. New flows: every bug in 9.1, entity links on each page, range carried across pages, Cancel returns to origin, Back closes lead and peek, ⌘K reaches every page and tab, swipe → brief, typed text surviving Refresh and saves.
- Automated guards: no `ad`-like names, contrast of token pairs, 44 px phone targets, no overflow at 320 and 390 px, no console errors.
- Visual: `qa/shots.cjs` for every tab, light and dark, desktop and 390 px, opened for Eugene after each phase.
- Leak test `dev/qa_leaks.py` covers `/api/gallery` automatically (it walks every GET route); confirm in its output.
- Live, with Eugene's yes for any write: run Update after each pushed phase, check with his ad blocker on, check on his real phone. This round needs no new Meta writes.

## Sources

- [Runneth (formerly Motion): vs Ads Manager](https://runneth.com/blog/motion-vs-ads-manager-creative-analysis)
- [Motion creative metrics](https://motionapp.com/blog/key-creative-performance-metrics)
- [Foreplay review](https://superscale.ai/alternatives/foreplay/review) (vendor-written)
- [Bïrch creative testing framework](https://bir.ch/blog/meta-ad-creative-testing-framework)
- [Revealbot help: automated rules](https://help.revealbot.com/en/articles/1526011-creating-automated-rules)
- [Linear design analysis](https://interfacelineage.com/linear-keyboard-first-multiplayer)
- [NN/g breadcrumbs](https://www.nngroup.com/articles/breadcrumbs/)
- [Human-in-the-loop review patterns](https://www.tcules.com/insights/human-in-the-loop-ux-patterns)
- [LeanData: lead response time](https://www.leandata.com/blog/the-modern-rules-of-lead-response-time)
