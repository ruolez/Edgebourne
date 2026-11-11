---
name: ads-desk
description: Work the Ads console Desk (ads.edgebourne.com): pick up directions Eugene typed in the dashboard, answer them with the Meta ads tools and the meta-ads skill library, and post a report and proposals back to the Desk. Use for "/ads-desk", "/ads-desk run <id>" (headless runs started by the Mac bridge), "check the desk", "anything on the desk?", "what did I ask on the dashboard", or "/ads-desk status".
---

# ads-desk

The Desk is the "Ask Claude" page of the Ads console. Eugene types a direction there; this
skill answers it. Results go back through the `desk` helper, never by editing the dashboard
some other way.

```
~/.claude/skills/ads-desk/desk <command>     (run exactly like this; it reads its own key)
  task <id> · claim · queue · snapshot [7|14|30] · history
  progress <id> <text> · report <id> --title T [--file F | stdin] · propose <id> [--file F | stdin]
  scorecard <id> [--file F | stdin] · upload <path>
  done <id> --summary S · fail <id> --error E
```

## Modes

- **`run <id>`**: headless, started by the Mac bridge with read-only tools. Work task `<id>`
  start to finish without asking questions (nobody is there to answer). If something is
  missing, say so in the report.
- **No arguments** (Eugene in Claude Code): `desk queue`, show what's waiting, then
  `desk claim` and work each task the same way, in this conversation. Here Eugene can answer
  questions, and he can approve a change in chat; then follow the workspace hard rules
  (CLAUDE.md) and log the write in `reports/log.md`.
- **`status`**: `desk queue`, plus the bridge log tail (`~/Library/Logs/ads-desk/bridge.log`).

## Hard limits (every mode)

- **No money moves from a Desk task.** Never publish, activate, pause, change a budget, bid,
  schedule or targeting, never delete. In a headless run those tools aren't even allowed. If
  something should change, write a **proposal** instead (below); Eugene approves it later.
- Never put the Mac key, Meta tokens or lead contact details in a report.
- Judge only on complete days (through yesterday, account time zone) and only with enough
  data: spend ≥ 2× target and ≥ 3 results on the unit judged. "Not enough data yet" with the
  date it will be enough is a good answer.
- Every number you state names its period and source (Meta insights vs the dashboard inbox).

## Passing JSON and long text to `desk` (headless runs)

Never pipe or heredoc JSON into `desk`: the permission checker refuses those commands.
Write the content with the Write tool to `reports/desk/tmp/task<id>-<what>.json` (or `.md`)
and pass the file: `desk scorecard <id> --file reports/desk/tmp/task<id>-scorecard.json`,
`desk propose <id> --file …`, `desk report <id> --title "…" --file …-report.md`. Video
frames and contact sheets for a look at motion go to `reports/desk/tmp/task<id>-frames/`
(`ffmpeg` and `ffprobe` are allowed in polish and render runs). Use the Read tool to read
files; `cat`, `tail` and pipes are not allowed.

## A follow-up in a conversation

The Claude page is a conversation. When `options.reply` is true, Eugene is replying to your
earlier answer: `prompt` is his new message, `thread` holds the earlier turns (what he asked, what
you said, every report and suggestion and what he decided), and this run usually continues your
own session, so you may remember them already.

- Do what the reply says and nothing wider. `kind` only decides your tools here; don't redo the
  whole recipe for that kind (no new full audit, no new scorecard) unless he asks for it.
- `options.about` is a suggestion he sent back: `{id, title}`. Its details are in `thread`. Propose
  a revised version in this run, written from his note. The old one is already marked as sent back.
- Numbers from earlier turns may be old. Read them again before relying on them.
- A short reply earns a short answer: often the `--summary` is enough, with no report. Post a
  report only when there are real findings to lay out. Still finish with `desk done`.

## Steps for one task

1. `desk task <id>`. Read `kind`, `prompt`, `campaign_id`, and `options.reply`. Then
   `desk progress <id> Reading your ads`.
2. Context, in parallel where possible:
   - `desk snapshot 7` (and 14/30 if the question spans longer): spend, leads, cost per lead,
     per-ad results, the spending limit, plus what Meta doesn't know: lead stages from the
     inbox (qualified/won), business types, speed to first contact, and `experiments`: the
     tests on the Tests page (running, or closed in the last 30 days) with each arm's numbers
     and the dashboard's verdict. Don't call a running test differently from its verdict;
     a closed one's `verdict` is what Eugene concluded, so build on it.
   - `desk history`: what earlier Desk runs concluded and proposed; build on it, don't repeat it.
   - `briefs/edgebourne.md` (offer, audience, target: $60 per qualified lead, kill band above
     $120 after $240 spend) and the end of `reports/log.md` (recent changes and why).
   - The Meta MCP read tools (`ads_get_ad_entities` with insights, `ads_get_errors`,
     `ads_insights_*`, `ads_get_opportunity_score`, `ads_library_search`,
     `ads_account_get_activity_logs`). Account `act_1025971549903293`, Page `1404203629446490`.
   - The `meta-ads` skill library (`~/.claude/skills/meta-ads/SKILL.md` router, then the one
     reference the question needs) before any judgement.
3. Post short progress lines as you go (`desk progress <id> Comparing the five ads`); each one
   becomes a step in the list Eugene watches, with its time, so post one per real stage of the
   work (usually 3 to 8), in plain words.
4. Do the work by kind:
   - **question**: answer it directly; show the numbers that prove it.
   - **review**: the operating check: tracking health, delivery and review status, results vs
     target with the minimum-data rule, fatigue (frequency, CTR, CPM trend), lead quality from
     the inbox, then keep / watch / change per ad set and ad.
   - **research**: `ads_library_search` (and the web) for the competitors or angle asked; group
     what they run by angle, format, offer and hook; end with what's worth testing here.
   - **creative**: 3-5 genuinely different concepts (angle, hook, persona, format), each with
     primary text, headline and what the visual shows, following `meta-ads` refs 07 and 09 and
     the policy rules in ref 12. Never invent facts about Edge Bourne (prices, reviews, years,
     guarantees); leave `[brackets]` for anything the brief doesn't state.
5. **Report** (`desk report <id> --title "…" --file reports/desk/tmp/task<id>-report.md`):
   - First line: the answer in one or two plain sentences.
   - Then `## What the numbers say` (a small table is fine), `## What I'd do` (numbered,
     concrete), `## Data used` (periods, sources, anything missing). The page shows each `##` as
     its own section and folds `## Data used`, so keep to these headings where they fit.
   - Name ads by their full name or short code (N3); the page shows a preview of every ad you name.
   - Plain words, no jargon without a gloss, dollars not cents. Keep it under ~600 words
     unless the question needs more.
6. **Proposals**, only when something should actually change (`desk propose <id> --file
   reports/desk/tmp/task<id>-proposals.json`): a JSON list of objects with
   `kind` (budget | status | creative | targeting | experiment | other), `title`, `entity_type`
   (campaign | adset | ad), `entity_id`, `entity_name`, `field`, `current_value`,
   `proposed_value` (budgets in dollars per day, e.g. "$20/day"), `rationale` (with the
   numbers), `expected`, `rollback` (the exact previous value). Respect the workspace rules:
   one budget change per campaign, ≥ 3 days apart, ≤ +20%.
   Eugene approves proposals in the dashboard, and two kinds are then applied on Meta with
   one click, so write them exactly: **status** = `entity_id` (the real Meta id of the
   campaign, ad set or ad) + `proposed_value` `PAUSED` or `ACTIVE`; **budget** = `entity_id`
   of the campaign or ad set that holds the daily budget (Edge Bourne: the campaign) +
   `proposed_value` like `$24/day`. Anything else (new creative, targeting, copy) is recorded
   when approved and needs a later step, so say what that step is in `expected`.
   **experiment** = a test worth tracking (two to four ads or ad sets that already run at the
   same time to the same people): `title`, `rationale` (the question and why it matters),
   `payload` `{"name": "…", "hypothesis": "…", "metric": "cpl" | "cpql" | "ctr" | "hook",
   "arms": [{"label": "A", "ad_ids": ["<ad id>"]}, {"label": "B", "adset_ids": ["<ad set id>"]}],
   "start_day": "YYYY-MM-DD" (optional, default today), "end_day": "YYYY-MM-DD" (optional),
   "target_cents": 6000 (optional, cost metrics)}`. Approving it only starts tracking; nothing
   changes on Meta. A payload that doesn't validate (unknown ids, fewer than two arms) is
   stored as `other`. The page says "too early" until each arm has spent 2× the target with
   ≥ 3 results over ≥ 3 full days, and calls a winner only at 95% confidence. A test may also
   run on Meta as an A/B test (`meta` in the snapshot: dates, test budget, Meta's own verdict);
   only Eugene starts those, from the Tests page. Never create one with
   `ads_experiment_abtest_create_test`; propose the experiment instead.
   **tags** = label an ad's idea so Results can compare ideas across ads (each ad in the
   snapshot carries its `tags`): `payload` `{"ad_id": "<ad id>", "tags": {"hook": "Question",
   "angle": "…", "persona": "…", "format": "9 s motion video, 4:5", "offer": "Free intro call"}}`.
   Hooks are a style, reused across ads so they group: Question, Command, Pain statement,
   Outcome promise, Number or stat, Story, Social proof. Reuse an existing value before inventing
   one. Propose tags for any ad with none (Polish and review runs), one proposal per ad.
7. `desk done <id> --summary "<one or two sentences>"`. If you can't finish (Meta down, no
   data, a tool refused), `desk fail <id> --error "<what happened and what would fix it>"`
   rather than stopping silently.


## Which business (agency mode)

The console can run several ad accounts. Every task belongs to one; the bridge runs it with
`DESK_ACCOUNT` set, so `desk snapshot`, `desk watched` and the rest answer for that account, and
`snapshot.account.name` says which business it is. Use that business's brief
(`briefs/<business>.md`, e.g. `briefs/burdanovahair.md`), its own ad account and Page from the
snapshot's campaigns, and never Edge Bourne's brief, target or wording for another business.
If there is no brief for it, say so in the report and keep to what the numbers show.

## Competitor watch (swipe file)

- `desk watched` lists the Pages Eugene watches (name, Page id if known, search terms, when last
  checked) and the Ad Library ids already in the swipe file.
- Search with `ads_library_search` (US, active). Meta's public Ad Library API covers only
  political and EU ads, so this search is the only way to see US competitors' commercial ads.
- Save ads with `desk swipe --task <id> --file reports/desk/tmp/task<id>-swipes.json` (`--task`
  shows them as pictures in your answer; save the ones your report talks about): a JSON list of
  `{"library_id", "page_name", "page_id", "body", "title", "cta", "media_url" (https only),
  "started_on": "YYYY-MM-DD", "stopped_on", "platforms": [...], "notes", "tags": {"hook", "angle",
  "format", "offer"}}`. Saving an id already in the file refreshes its dates and text; nothing
  is duplicated. Tag hooks in this dashboard's styles (Question, Command, Pain statement,
  Outcome promise, Number or stat, Story, Social proof).
- An ad running 30 days or more is the best public sign it works; say why it likely does.
- Never copy a competitor's ad. Turn what works into ideas for Edge Bourne's own voice.

## Benchmarks (Monday summary)

The benchmark and peer tools are only in the Ads MCP, so the dashboard shows what you post.
After the Monday summary, read `ads_insights_industry_benchmark`, `ads_insights_performance_vs_peers`
and `ads_insights_auction_ranking_benchmarks`, then `desk benchmarks --file
reports/desk/tmp/task<id>-benchmarks.json` with `{"as_of": "YYYY-MM-DD", "summary": "<one sentence>",
"items": [{"label": "Cost per lead", "ours": "$4.79", "peers": "$18–$42", "note": "Professional
services, US"}]}` (at most 12 rows, the numbers as shown to people, with units). Today shows them.

## Scheduled runs

A prompt that starts with "Scheduled" was filed by a Desk schedule (daily health check,
optimizer review, Monday summary, monthly audit), not typed by Eugene. Nobody asked a question,
so do exactly the scope the prompt names and nothing more:

- **Daily health check**: health only, never budget advice. If everything is fine, the report is
  five lines or fewer. Propose only for something broken (a rejected ad, a delivery error).
- **Optimizer review**: the `/meta-ads-launch optimize` logic. Proposals are the output; respect
  the budget rules (one change per campaign, ≥ 3 days apart, ≤ +20%) and check `desk history`
  for the last budget proposal and its date first.
- **Monday summary** and **Monthly audit**: the report is the output; propose only what the
  numbers clearly support.

The `--summary` you pass to `desk done` is sent to Eugene's phone as the message, so write it
for that: the verdict first, one or two sentences, numbers with their period
("All 5 ads delivering; 4 leads yesterday at $5.10 each, on target.").

## Kind `polish`: the preset audit passes

`options` carries `ad_id`, `ad_name`, `direction` (Eugene's words, may be empty), `variants`
(true = write copy variants) and `passes`: each with `id`, `label` and the `checks` the
dashboard promised. Check exactly those, nothing vaguer.

1. Gather, in parallel: the ad (`ads_get_ad_entities` level=ad, `object_ids=[ad_id]`, with
   results, video and ranking fields over `last_30d`), its words (`ads_get_creatives`), the
   previews per placement (`ads_get_ad_preview` for `MOBILE_FEED_STANDARD`,
   `INSTAGRAM_STORY`, `INSTAGRAM_REELS`), `desk snapshot 7`, the other running ads (for
   "different enough" and "against the other ads").
2. Look at the creative itself. Edge Bourne N1–N5 sources live in
   `creatives/2026-11-07-new5/` (`out/N#-4x5.png`, `out/N#-9x16.png`, videos
   `out/N#-video-4x5.mp4`; the template is `src/n5.html`, history in its `README.md`). Read
   the PNGs (the Read tool shows images). For other ads, use the preview screenshots.
3. Judge with the rules that produced the approved set: `~/.claude/skills/ad-creative-render/
   references/design-rules.md` (incl. Eugene's taste file), `.../gotchas.md` (AI chip
   placement, declutter checks), and `~/.claude/skills/meta-ads/references/` 07 (creative),
   08 (visual, safe zones, 28 px / 4.5:1), 09 (copy), 12 (policy). Performance pass: hook
   rate = 3-second views ÷ impressions, hold rate = ThruPlays ÷ 3-second views; apply the
   minimum-data rule and say "not enough data yet" when it applies.
4. Score every pass 1–5: 5 ready, 4 small polish, 3 works but a fix would help, 2 hurting
   results, 1 blocking. `verdict` is one plain sentence; `findings` cite what you saw
   (quote the text, name the element, give the number); `fixes` are concrete enough to do
   without asking ("Shorten the headline to 'Type it once' (12 chars)", "Move the AI chip
   into the report card's status column, 32 px"). Post them:
   `desk scorecard <id> --file reports/desk/tmp/task<id>-scorecard.json` containing `{"headline": "<one-line overall verdict>", "passes": [{"id",
   "label", "score", "verdict", "findings": [], "fixes": []}]}`.
5. When `variants` is true and any copy pass scored ≤ 4: 2–4 **creative proposals**, each a
   genuinely different fix (not synonyms), in the proposals file (`desk propose <id> --file …`) with `kind: "creative"`,
   `title` ("New headline: Type it once"), `rationale` (which checks it fixes), and
   `payload: {"template_ad_id": "<ad_id>", "media": {"kind": "same"}, "name": "<ad name> ·
   <what changed>", "title": "<headline>", "body": "<full primary text>", "cta_type":
   "<same unless the CTA pass says otherwise>"}`. Approving one creates that ad, switched
   off, with the same image or video. Never invent facts in the copy.
6. Fixes that need new pixels (visual, AI signal, placements, motion): one proposal, kind
   `other`, titled "Make a new version: <the fixes in a few words>", `expected`: "Use 'Make
   a new version' on the ad page; Claude rebuilds the creative and sends it back for approval."
7. Report: first line = the overall verdict and the top three fixes; then a table
   pass | score | verdict; then the details. `desk done` with the one-line verdict.

## Kind `render`: make a new version

`options`: `ad_id`, `ad_name`, `direction`, and `scorecard` (fixes from a polish run, may be
null). This run may edit files under `creatives/` and run node / ffmpeg (nothing else).

1. Read `~/.claude/skills/ad-creative-render/SKILL.md` and its references first.
2. Find the source. N1–N5: `creatives/2026-11-07-new5/src/` (`n5.html`, `render16.js`,
   `batch.sh` / `batchv.sh`, `textaudit.js`; README "Final set v15"). Copy what you need into
   `creatives/<today>-desk-task<id>/` and work there; never edit an approved file in place.
3. Apply the scorecard fixes and the direction, nothing else (one variable at a time is
   what Eugene expects). Respect the taste file: rejections are permanent.
4. Render the 4:5 still and, if the original is a video, the 4:5 video with its sound bed;
   9:16 too when the source supports it. Run `textaudit.js` and the probe, check a 0.3 s
   contact sheet for motion, and look at the frames before uploading.
5. `desk upload <file>` for each output (prints `hash` or `video_id`), then append one line per
   upload to `reports/log.md` (date, task, file, id; "library only, no ad created"). Copy files
   with `cp` one command at a time (no `&&` chains, no `-R` into a new folder: create it with
   `mkdir -p` first), or a small node script if `cp` is refused.
6. `desk propose <id> --file …` with one `creative` proposal: `payload.template_ad_id` = the ad,
   `media` = `{"kind": "video", "video_id": "..."}` (or image + hash), `name` "<ad name> ·
   v<n>", and the same words unless the fixes changed them. Approving it creates the ad off.
7. Report: what changed and why (before → after), file paths, audit results. Never touch
   other ads, never activate anything.

## Kind `advice`: fix Meta's advice

Started by **Fix with Claude** on Today → Meta's advice. `options.advice` is Meta's suggestion as
the console read it (`type`, `label`, `body`, `lift`, `points`, `object_ids`: the campaign, ad set or
ads it names, `url`, and `fix`: what the console promised Eugene you would do), `options.ads` the
running ads under it (`id`, `name`, `adset_id`). This run has the render tools (node, ffmpeg, files
under `creatives/`, `desk upload`). Do what `fix` says, nothing wider.

First check the advice is still live (`ads_get_opportunity_score`) and that it fits: the meta-ads
library and the brief beat Meta's generic advice (e.g. Meta-picked music for a brand ad). If it
doesn't fit, say why in the report and propose nothing.

**`REELS_PC_RECOMMENDATION` (add a vertical 9:16 video for Reels):**

1. For each ad in `options.ads`: read its creative (`ads_get_ad_entities` level=ad with
   `creative_id`, then `ads_get_creatives`). Skip an ad that already shows different media per
   placement, or isn't a single video. Note its video, words and sound.
2. Find the source the running 4:5 video was rendered from. N1–N5: `creatives/2026-11-07-new5/`;
   later versions live in `creatives/<date>-desk-task<id>/` (README says which ad), and
   `reports/log.md` maps uploaded video ids to files. The old `out/N#-video-9x16.mp4` files predate
   the final words (some still say "FREE WORKFLOW REVIEW"): never upload them as they are.
3. Render the 9:16 version of exactly what the ad shows now: same words, scenes, timing and sound
   bed; only the layout changes to the Reels frame (`ad-creative-render` SKILL + design rules;
   `meta-ads` ref 08 safe zones: keep text out of the top 14%, the bottom 35% and 6% of each side, 28 px
   minimum). Work in `creatives/<today>-desk-task<id>/`; run `textaudit.js`, the probe and a 0.3 s
   contact sheet, and look at the frames before uploading. 1080×1920, H.264 + AAC, ≤ 30 s.
4. `desk upload <file>` → `video_id`; append one line per upload to `reports/log.md`.
5. One proposal per ad, `kind: "creative"`, title "9:16 for Reels: <ad name>", rationale quoting
   Meta's lift, `expected` "Feeds keep the 4:5 video; Reels and Stories show the 9:16 one. Meta
   reviews the ad again.", and `payload`:
   `{"template_ad_id": "<ad id>", "update_ad": true, "vertical": {"video_id": "<9:16 id>"},
   "name": "<ad name> · 9:16 Reels"}`. Approving it updates that running ad in place (Eugene's
   choice, 2026-11-10): the console builds the 4:5 + 9:16 creative with the same words and lead
   form, checks Meta's copy, then swaps it onto the ad.
6. Never call `ads_create_creative` or `ads_update_entity` for this: the MCP can't carry the
   Instant Form, so the console makes the creative.
7. Report: per ad, before → after (file paths, video ids, audit results), anything skipped and why.
   If time runs short, finish the ads you started and say which are left; "Fix with Claude" again
   picks up the rest (skip ads that already have a waiting 9:16 proposal: `desk history`).

**Creative fatigue / too few ads:** as a polish or render run on the ads named: new versions or new
ideas as `creative` proposals (new ads, created off), never edits to the running ads.

**Anything else:** a review of that one point: the numbers that bear on it (minimum-data rule), what
the playbook says, and proposals only for what should change (status, budget, `other` with the
exact step for Ads Manager when the console can't do it).

`desk done` summary: what you made and what's waiting for Eugene ("9:16 versions of 5 ads ready
to approve on the Claude page; N3 skipped: it's an image ad").
