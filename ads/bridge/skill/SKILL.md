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
5. **Report** (`desk report <id> --title "…"` with the Markdown on stdin via a quoted heredoc):
   - First line: the answer in one or two plain sentences.
   - Then `## What the numbers say` (a small table is fine), `## What I'd do` (numbered,
     concrete), `## Data used` (periods, sources, anything missing).
   - Plain words, no jargon without a gloss, dollars not cents. Keep it under ~600 words
     unless the question needs more.
6. **Proposals**, only when something should actually change (`desk propose <id>` with JSON on
   stdin): a list of objects with
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
