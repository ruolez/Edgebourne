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

## Steps for one task

1. `desk task <id>`. Read `kind`, `prompt`, `campaign_id`. Then
   `desk progress <id> Reading your ads`.
2. Context, in parallel where possible:
   - `desk snapshot 7` (and 14/30 if the question spans longer): spend, leads, cost per lead,
     per-ad results, the spending limit, plus what Meta doesn't know: lead stages from the
     inbox (qualified/won), business types, speed to first contact.
   - `desk history`: what earlier Desk runs concluded and proposed; build on it, don't repeat it.
   - `briefs/edgebourne.md` (offer, audience, target: $60 per qualified lead, kill band above
     $120 after $240 spend) and the end of `reports/log.md` (recent changes and why).
   - The Meta MCP read tools (`ads_get_ad_entities` with insights, `ads_get_errors`,
     `ads_insights_*`, `ads_get_opportunity_score`, `ads_library_search`,
     `ads_account_get_activity_logs`). Account `act_1025971549903293`, Page `1404203629446490`.
   - The `meta-ads` skill library (`~/.claude/skills/meta-ads/SKILL.md` router, then the one
     reference the question needs) before any judgement.
3. Post short progress lines as you go (`desk progress <id> Comparing the five ads`); they
   show live on the Desk page.
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
     concrete), `## Data used` (periods, sources, anything missing).
   - Plain words, no jargon without a gloss, dollars not cents. Keep it under ~600 words
     unless the question needs more.
6. **Proposals**, only when something should actually change (`desk propose <id> --file
   reports/desk/tmp/task<id>-proposals.json`): a JSON list of objects with
   `kind` (budget | status | creative | targeting | other), `title`, `entity_type`
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
7. `desk done <id> --summary "<one or two sentences>"`. If you can't finish (Meta down, no
   data, a tool refused), `desk fail <id> --error "<what happened and what would fix it>"`
   rather than stopping silently.


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
