# D3: "Did it work?" check on applied changes and Claude's suggestions

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build step **7** of 9; migration **N+5**. Depends on:
>   - D2: `status_history.OUTSIDE_FIELDS`, `timeline.merge`, `editBudget`, `words.py`, `history_href`
>   - L2: `lead_quality.counted()` / `qualified()` for cost per qualified lead
>   - W1a: owner-closed events, `DONE_OK`, `diagnose.PLAYBOOKS`
> - C1: links are built by `links.history_href(level, id, check=change_id)`:
>   - `/campaign.html?id=X&tab=history&check=N`
>   - `/adset.html?id=X&tab=history&check=N`
>   - `/ad.html?id=X&check=N#tab=history`
> - C16: the bad class (`change_result` warn) is an owner-closed event (`resolved: False`). It stays in Needs action until put back or **Done** (`DONE_OK`). Good and flat results are info, raised resolved (FYI).
> - C23: windows end early on console changes **and** on outside `status_events` whose field is in `status_history.OUTSIDE_FIELDS` (switches, budgets, bids, dates, audience).
> - C24: Put it back fills D2's `editBudget({..., suggest, note, undoOf})`. The exact previous amount is a rollback, so it's never "recent", but +20% and the ceiling still apply.
> - C25: `merge(status_events, changes, proposals, money, versions=(), checks=None)`.
> - C26: `diagnose.PLAYBOOKS["change_result"] = ("cpa-diagnostics", "why a change didn't help", "before/after windows, what else changed, whether to put it back")`.
> - S1: sentences use `words.money` / `words.day`, not `entities_api._money`.
> - Security: `undo_of` must name an `ok` change of the same account, entity and action. `/api/agent/outcomes` is scoped to the task's account and has no PII.
> - Bridge: `desk outcomes` + SKILL.md rule ship as bridge VERSION 1.13 (C27).

Unit key: `D3-did-it-work` · value high · effort M · Meta writes: none new · touches money: only via the existing Undo dialogs.

## Goal

Every change the console makes on Meta is already logged in `meta_changes`: on/off, budget, new version, put a version back, Meta's advice, enhancements. Each row has who made it, old → new, and `proposal_id` when it came from Claude. Nothing checks what happened next. Today Eugene has to work out by hand whether cost per (qualified) lead improved after a budget raise, a pause or a new version. Claude gets only the last 10 report titles (`desk_api.history`), so it can suggest the same failed idea again.

This feature answers "Did it work?" for each applied change. It compares equal windows of complete days before and after the change, at 3, 7 and 14 days, and applies the minimum-data rule from `compare.shape` and `experiments.needs`. A side is judged only once it has spent 2× the target and has 3 results; until then the answer is "Too early to tell". The answer appears in four places:

- the entity's History
- Claude's decided suggestions ("Expected: cost per lead under $40. Got: $36 over 7 days.")
- Inbox (and the Phase 9 Today queue) when a change made things worse
- Claude's own context: `/api/agent/outcomes`, the snapshot, and `history`

A result that looks worse offers **Put it back**. That button only opens the existing confirmation dialog, filled in with the exact previous budget, status or version. Nothing moves money on its own. The check is read-only and uses only data already in Postgres: no Meta calls, no new Meta writes.

## User flow

### Desktop

1. Eugene raises the budget on "Free intro call" from $20 to $24 a day (Campaign page → Budget, the existing dialog). The History tab shows "Budget $20.00 → $24.00 a day" and under it, in muted text, **"First check on Nov 13"**.
2. On Nov 13 (3 complete days later) the line reads, for example, **"Too early to tell: needs $30 more spend and 1 more lead."** On Nov 17 (7 days) it reads **"Worked: cost per lead $47 → $28 over 7 days (40% cheaper)"** or **"Didn't help: …"**.
3. **Details** opens the "Did it work?" dialog:
   - tabs 3 days / 7 days / 14 days
   - a Before / After table
   - what was compared and the minimum-data rule in one sentence
   - any notes (relearning, changed again, qualified leads still being worked)
   - for a Claude suggestion, what Claude expected and whether it was met
4. When the result is "Didn't help" or "Looks worse, not sure yet" and the change is still in place, the dialog and the History line show **Put it back**. It opens the existing budget dialog (`controls.editBudget`), filled in with $20.00, with the line "Before the change on Nov 9 it was $20.00 a day." Eugene still clicks **Change budget**. The server runs the same checks as always: fresh budget from Meta, `from_cents`, the ceiling, and the +20% warning that needs a knowing yes.
5. Inbox gets one item per change when a result comes in. "didn't help" goes to **Needs action**, the rest to **FYI**. "Didn't help" is also emailed through the normal alert path, unless switched off in Settings → Alerts.
6. Claude page: each decided suggestion row (`board.proposalRow`, and the conversation's decided list) gets the same line. When Claude gave an expectation, the row reads "Expected: cost per lead under $40. Got: $36 over 7 days · Met".

### Phone (390 px, also 320 px)

- The History line wraps under the timeline item. **Details** and **Put it back** are 44 px tall.
- The dialog uses the Phase 9.2 shared Dialog as a full-height sheet:
  - tabs are a 3-segment control, each segment 44 px tall
  - the table keeps three columns (label 40%, Before 30%, After 30%) with numbers in Geist Mono; no horizontal scroll at 320 px
  - **Put it back** is a full-width button at the bottom
- An Inbox item opens `history_href(level, id, check=<change_id>)` (e.g. `/campaign.html?id=X&tab=history&check=N`), which opens History with the dialog already open. Phone Back closes the dialog (Phase 9.3 `pushState` pattern).

## Data model

Migration `NNN_change_checks.sql` (one file, written in one go: see ROADMAP §5, dev reload):

```sql
-- "Did it work?": before/after results for each change made from the console, at 3, 7 and 14
-- complete days. Recomputed by the worker until final; never written to Meta.
CREATE TABLE change_checks (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    change_id INTEGER NOT NULL REFERENCES meta_changes(id) ON DELETE CASCADE,
    horizon SMALLINT NOT NULL CHECK (horizon IN (3, 7, 14)),
    mode TEXT NOT NULL CHECK (mode IN ('self', 'parent', 'version', 'new', 'stopped')),
    scope_level TEXT NOT NULL CHECK (scope_level IN ('campaign', 'adset', 'ad')),
    scope_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('waiting', 'too_early', 'better', 'lean_better', 'same', 'lean_worse',
                                         'worse', 'on_target', 'over_target', 'mixed', 'no_compare',
                                         'stopped', 'not_running')),
    metric TEXT CHECK (metric IN ('cpl_cents', 'cpq_cents')),
    before_start DATE, before_end DATE, after_start DATE, after_end DATE,
    before_totals JSONB,          -- {days, spend_cents, leads, qualified, impressions}
    after_totals JSONB,
    delta_pct INTEGER,            -- after vs before on `metric`, rounded like compare._delta
    confidence SMALLINT,          -- experiments.confidence on `metric`, 0-99
    needs TEXT,                   -- "$30 more spend and 1 more lead"
    sentence TEXT NOT NULL,       -- the plain line shown everywhere and sent to Claude
    notes JSONB NOT NULL DEFAULT '[]',
    expect_met BOOLEAN,           -- NULL = no expectation or not judgeable yet
    ready_on DATE,                -- first day this horizon can be read (after_end + 1)
    final BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, change_id, horizon)
);
CREATE INDEX change_checks_open_idx ON change_checks (account_id) WHERE NOT final;
ALTER TABLE change_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON change_checks
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- What Claude said would happen, in a form the check can test: {"metric": "cpl"|"cpq", "op": "<"|"<=", "cents": 4000, "days": 7}
ALTER TABLE desk_proposals ADD COLUMN expect JSONB;

-- "Put it back" says which change it reverses, so the check can say "Put back on Nov 17 by Eugene".
ALTER TABLE meta_changes ADD COLUMN undo_of INTEGER REFERENCES meta_changes(id) ON DELETE SET NULL;
```

Grants: `ALTER DEFAULT PRIVILEGES` from 020 already covers new tables for `ebads_app`, and `db.APP_ROLE_SQL` re-grants at start. `jobs.PRUNE` gets no entry: rows go when their `meta_changes` row goes, and `meta_changes` is never pruned. `qa_leaks.py` sees the new GET routes automatically.

## Backend

### New pure module `backend/change_checks.py` (no database, no Flask)

Constants:
- `HORIZONS = (3, 7, 14)`
- `CHECKED = {"status", "budget", "update_creative", "restore_creative", "placement_media", "enhancement", "recommendation", "create"}`
- `DELTA_PCT = 10`, the smallest change worth a word
- `LEAN = experiments.LEAN` (80) and `SPEND_TIMES = experiments.SPEND_TIMES`, `MIN_RESULTS = experiments.MIN_RESULTS`: imported, never copied
- `SETTLE_DAYS = 7`: a horizon becomes final this many days after its window ends, because qualified stages and Meta's late conversions keep arriving
- `FAR_OVER = 3`: zero leads after 3× the target counts as "looks worse" (same bar as `alerts.cpl_high`)

| Function | Signature | Does |
|---|---|---|
| `mode_for` | `mode_for(change, entity) -> (mode, scope_level, scope_id) \| None` | What is measured where. budget / enhancement / placement_media / recommendation → `self` on the entity. update_creative / restore_creative → `version` on the ad. status → PAUSED on an ad gives `parent` (its ad set), on an ad set gives `parent` (its campaign), on a campaign gives `stopped`. status → ACTIVE on an ad or ad set gives `parent`; on a campaign it gives `new`. create of an ad, ad set or campaign gives `new`. Failed changes (`ok` false), levels `study` / `form` / `account`, and the actions duplicate / archive / delete / comment_reply / rename / subscribe all give `None`. |
| `windows` | `windows(first_changed, last_changed, today, horizon, prev_change=None, next_change=None) -> dict` | Equal windows of complete days, from `ranges`' rule "through yesterday" (`today - 1`). The days from `first_changed` to `last_changed` count for neither side (change day; for a version, the days from the switch until Meta approved it, as in `creative_versions.split_results`). After = `last_changed+1 … +horizon`, cut the day before `next_change`. Before = `first_changed-horizon … first_changed-1`, cut the day after `prev_change`. Both sides then take the shorter length `n`. Returns `{before, after, days: n, complete, ready_on, cut_by}`. |
| `totals` | `totals(daily, start, end) -> dict` | Sums `{day, spend_cents, leads, qualified, impressions}` rows inside [start, end] and adds `days`. One daily query per scope serves all horizons. |
| `rates` | (reuse `compare.rates`) | `cpl_cents`, `cpq_cents` |
| `judge` | `judge(mode, before, after, q_target, l_target) -> dict` | Picks the metric: `cpq_cents` when a qualified target is set and both sides have ≥ 2× it in spend and ≥ 3 qualified; otherwise `cpl_cents` against `targets.lead()`. Readiness per side comes from `experiments.needs(metric_key, arm, target)`. Not ready → `too_early` with the after side's needs (or the before side's, plus a note when only the before side is short). Ready → `delta_pct`, then `confidence = experiments.confidence(...)`; \|delta\| < 10 → `same`; else `better` or `worse` when confidence ≥ 80, `lean_better` or `lean_worse` below. Special case: after has 0 leads and spend ≥ 3× the target → `lean_worse`. Mode `new`: after side only, `on_target` / `over_target` against the target once ready. Mode `stopped`: state `stopped`, before numbers only. |
| `expect_from_text` | `expect_from_text(text) -> dict \| None` | Best-effort reading of Claude's free-text `expected`. Recognises "cost per (qualified) lead / CPL / CPQL", "under / below / less than / <" (→ `<`) or "to / at most / no more than" (→ `<=`), and an amount (`$1,200.50`). Anything else → `None`. |
| `clean_expect` | `clean_expect(raw) -> dict \| None` | Validates the structured `expect` Claude sends: metric in {cpl, cpq}, op in {<, <=}, cents 1…10,000,000, days in {3, 7, 14} (default 7). |
| `expectation_met` | `expectation_met(expect, check) -> bool \| None` | `None` unless that metric is ready at that horizon. |
| `sentence` | `sentence(check, money, day) -> str` | The plain line. `money` and `day` are passed in, so the account currency and date format are not hard-coded. |
| `headline` | `headline(rows) -> dict` | The row to show in one line: the longest horizon that isn't `waiting`; if all are waiting, the 3-day row (shows "First check on …"). |
| `undo_plan` | `undo_plan(change, entity_now, versions, money) -> {"plan": dict \| None, "reason": str \| None}` | What **Put it back** would do, only while the change is still in place. budget → `{kind: "budget", level, id, name, from_cents: now, to_cents: old}`. status → `{kind: "status", to: old}`. update/restore_creative → `{kind: "version", ad_id, number}` of the version before, found by the creative id in `new_value` ("(creative 123)"). Everything else → reason "Change it back on the ad's page.". Entity archived / deleted, or changed again since → no plan, with a reason. |
| `state_class` | `state_class(state) -> "good" \| "bad" \| "flat" \| None` | Groups states for Inbox dedupe and Today triage. |

`mode_for` reads `entity` (`{level, id, adset_id, campaign_id, status}`) only for parent ids. It is passed in and never looked up.

### New database module `backend/change_checks_db.py` (named to keep the pure one importable without `db`)

- `compute(change_id) -> list[row]` does the following:
  1. Loads the change, the entity (from `campaigns` / `adsets` / `ads`, or the change row's ids when the entity is gone) and the targets (`targets.qualified()`, `targets.lead()`).
  2. Finds the version days (`versions_api.for_ad` → `creative_versions.with_live_days`).
  3. Finds `prev_change` / `next_change`. These are other `ok` meta_changes in `CHECKED` actions, or `status_events` with source `poll` / `webhook` and `field = ANY(status_history.OUTSIDE_FIELDS)` (switches, budgets, bids, dates and audience changed in Ads Manager; D2), on the scope entity, its parent or its children. Any of them within 14 days ends the window early.
  4. Runs one `ad_daily` query (daily sums by `day` for the scope column, from `first_changed − 14` to `last_changed + 14`) and one `leads` query (`lead_quality.counted()` and `lead_quality.qualified()` from L2, by `(created_time AT TIME ZONE tz)::date`, the same as `ads_api._quality` after L2).
  5. Builds the three horizons with the pure functions and upserts `change_checks`.
  6. A row becomes `final` once `today − 1 ≥ after_end + SETTLE_DAYS`, or when its state is `mixed`, `no_compare` or `stopped` and its window is complete.
  7. If `ad_daily` has no data up to `after_end` yet (`settings.last_performance_sync` is older than that day), the state stays `waiting` with the note "Waiting for Meta's numbers".
- `run()` runs in the worker. It covers `ok` changes in `CHECKED` from the last 35 days that have no row yet, plus every non-final row, at most 300 changes per pass, oldest first. After computing, it raises Inbox items (below) and resolves the items of changes that were put back (a later change with `undo_of = id`).
- `summary_for(change_ids) -> {change_id: {headline, rows}}` is used by timeline and desk enrichment; it is read-only.

### Inbox / alerts (`alerts.py`, `inbox.py`)

- `alerts.DEFAULTS["change_result"] = {"on": True}`.
- `inbox.CATEGORY["change_result"] = "money"`. Clients are already filtered to `status` alerts, so they never see these.
- `change_checks_db.raise_results(rows)` calls `alerts.raise_found([...])` with:
  - `kind: 'event'`; the bad class is raised with `resolved: False` (an owner-closed event, 00-PLAN C16); good and flat are raised `resolved: True`
  - `dedupe_key: change_result:<change_id>:<state_class>`, so a change can say "good" then "bad" but never repeats itself
  - `level: 'warn'` for the bad class (emailed through `notify`, like other alerts), `'info'` for good and flat (console only)
  - `entity_id` and `campaign_id`, so teammates see only their campaigns
  - `href` = `links.history_href(level, entity_id, check=change_id)`
  - `diagnose.PLAYBOOKS` gains `change_result` (W1a module), so the item offers **Diagnose with Claude**; `DONE_OK` includes `change_result`, so it offers **Done** ("keep the change")
- Title: "Budget raise on “Free intro call”: didn't help". Lines: the sentence, and "Before Nov 2 – Nov 8 · After Nov 10 – Nov 16".
- Phase 9.4 triage: `change_result` with level `warn` and `resolved_at IS NULL` is **Needs action**; everything else is FYI. Putting the change back sets `resolved_at`.

### Routes

| Route | Auth | Rules |
|---|---|---|
| `GET /api/changes/<int:change_id>/check` | `login_required` | Loads the change. Its `campaign_id` must pass `ads_api.can_touch` (admins and clients see the whole account, teammates only their campaigns, RLS limits to the account); otherwise 404. Recomputes when not final (fast: two queries) and returns `{change, title, rows: [3, 7, 14], headline, scope: {level, id, name}, expect, expected_text, proposal: {id, title}, undo: {plan, reason}, undone_by: {at, by}}`. For **read-only clients**: `undo`, `proposal` and `expect` / `expected_text` are left out. For a **teammate**, `undo` is included only when `can_touch` holds (the same rule as the write routes). |
| `GET /api/timeline/<level>/<id>` and campaign / ad set / ad detail | unchanged | `entities_api.timeline_for` passes `checks=change_checks_db.summary_for(ids)` to `timeline.merge`. Change items gain `change_id` and `check: {state, sentence, ready_on, worse: bool}`. `merge(..., checks=None)` keeps the old signature for the other workflow's tests. |
| `GET /api/desk` (`tasks_with_results`) | admin (unchanged) | Each applied proposal gets `check` (the headline row, plus `expect_met`) through its `meta_changes.proposal_id`. |
| `GET /api/agent/outcomes?days=60` (new, `agent_required`) | Mac key | Up to 60 days, at most 100 items, newest first: every checked change `{change: {id, at, level, entity_id, entity_name, action, old, new, by: "console" \| "claude" \| "bulk"}, proposal: {id, title, kind, expected, expect} \| null, result: {horizon, state, metric, before, after, delta_pct, confidence, sentence, expect_met}, put_back: bool}`, plus declined or sent-back proposals `{proposal, status, decided_at}` with no result. No lead names or contact details. |
| `GET /api/agent/snapshot` | Mac key | Adds `change_results`: the same shape, last 30 days, 20 items. |
| `GET /api/agent/history` | Mac key | Unchanged shape. Proposals inside carry `result` (headline row) through the `tasks_with_results` enrichment. |
| `POST /api/ads/<level>/<id>/budget`, `…/status`, `/api/ads/ad/<id>/versions/<n>/restore` | unchanged | They accept an optional `undo_of` (int). It is stored only when it names an `ok` change on the same entity with a matching action (`budget` / `status` / `update_creative` or `restore_creative`); otherwise it is ignored. It never skips a check: fresh budget, `from_cents` 409, `money_rules.change_problem`, `turn_on_problem`, ceiling. Client writes stay blocked by `accounts_api`'s read-only guard. |

Desk side (`desk_api.clean_proposal`): `expect` is added to the cleaned keys as `change_checks.clean_expect(p.get("expect")) or change_checks.expect_from_text(out["expected"])`. The insert loop JSON-encodes `expect` like `payload`.

Worker (`jobs.slow`): after `alerts.run()` add `("did it work", "change_checks_db")` → `run()`, inside its own try, as the other steps do.

## Frontend

### Shared

- **`format.js`** (the Phase 9 vocabulary): `OUTCOME` = `{better: "Worked", lean_better: "Looks better, not sure yet", same: "No clear change", lean_worse: "Looks worse, not sure yet", worse: "Didn't help", too_early: "Too early to tell", waiting: "Not checked yet", on_target: "On target", over_target: "Over target", mixed: "Changed again too soon", no_compare: "Nothing to compare", stopped: "Off", not_running: "Not running yet"}` and `outcomeWords(state)`. Words carry the meaning; colour only backs them up. Signal keeps green for "delivering", so good results use the neutral `ok` tone with text, bad ones the `bad` tone.
- **New `js/outcome.js`**:
  - `outcomeLine(check, {changeId, canUndo, expect})` returns the HTML line
  - `openOutcome(changeId)` fetches `/api/changes/<id>/check` and shows the dialog
  - `putBack(plan, changeId, after)` sends `budget` to `controls.editBudget({…, suggest: plan.to_cents, note, undoOf})`, `status` to `controls.setStatus({…, turnOn: plan.to === "ACTIVE", undoOf})`, and `version` to `controls.restoreVersion({adId, number, undoOf})`
- **`controls.js`**:
  - `editBudget` takes optional `suggest` (prefills the field), `note` (one extra paragraph) and `undoOf` (sent in the body). Validation, the +20% hint and the server's `accept_big` stay exactly as they are.
  - `toggleEntity`'s body moves into an exported `setStatus({level, id, name, turnOn, undoOf}, after)` that both callers share. Same /spend read, same copy.
  - The "Switch back to version N?" confirmation moves from `creative.js:541-546` into `restoreVersion`. Same copy; `creative.js` calls it.
- CSS (`app.css`, names checked against the ad-blocker guard): `.oc-line`, `.oc-state`, `.oc-sheet`, `.oc-tabs`, `.oc-grid`, `.oc-note`, `.oc-expect`. None of them reuse `.report`, `.confirm`, `.sheet` or `.step`.

### Pages touched

- **Campaign / Ad set History** (`entity.js:54`) and **Ad → History** (`creative.js` around line 505): change items with `check` render `outcomeLine` under the title. Loading with `check=<id>` in the query opens the dialog (Inbox and Today links, built by `historyHref`).
- **Claude page**: `board.proposalRow` and the conversation's decided list (`conversation.js` `suggestionsHtml`) add `outcomeLine(p.check, {expect: p.expect})` after the state pill. A suggestion that is still waiting shows nothing new.
- **Settings → Alerts**: new row "A change didn't help".
- **Today queue (9.4)**: item type `result` for `change_result` alerts at level `warn` from the last 7 days that are still open. Buttons: **See what happened** (dialog) and **Put it back**. Ranked after leads to call and ads with problems, before money FYIs. Not shown to clients.
- **Inbox**: no new UI. The alert item already has a title, lines and href; the 9.4 triage rule puts it in Needs action.

### Exact copy

The History / suggestion line shows the state word, then the sentence, then **Details**:

| State | Sentence |
|---|---|
| waiting | "First check on Nov 13" |
| too_early | "Too early to tell: needs $30 more spend and 1 more lead." |
| better | "Worked: cost per lead $47 → $28 over 7 days (40% cheaper)." |
| lean_better | "Looks better, not sure yet: cost per lead $47 → $28 over 7 days." |
| same | "No clear change: cost per lead $35 → $36 over 7 days." |
| lean_worse | "Looks worse, not sure yet: cost per lead $28 → $41 over 7 days." |
| lean_worse (no leads) | "Looks worse, not sure yet: no leads in 7 days after spending $180 (3× your target)." |
| worse | "Didn't help: cost per lead $25 → $100 over 7 days (300% more)." |
| on_target / over_target | "Got $36 per lead over its first 7 days (target $40)." |
| mixed | "Changed again on Nov 13, too soon to tell the two changes apart." |
| no_compare | "It hadn't run long enough before the change to compare." |
| stopped | "Off since Nov 9. In the 7 days before, it spent $140 for 3 leads ($47 each)." |
| not_running | "Hasn't spent anything yet." |

The Put it back state appears after the sentence: "Put back on Nov 17 by Eugene".

When the qualified metric decides, the sentence says "cost per qualified lead" instead of "cost per lead".

**Dialog**
- Title: "Did it work?"
- Subtitle: the change title from `timeline.change_title`, e.g. "Budget $20.00 → $24.00 a day · Nov 9 · Eugene" (or "· from Claude's suggestion", linked to `/desk.html#p/<id>`; admins only).
- Tabs: "3 days", "7 days", "14 days". A tab that isn't ready yet shows its date, "14 days · Nov 24", and is disabled.
- Table header: "", "Before", "After". Under each, the window from `ranges.label`, e.g. "Nov 2 – Nov 8".
- Table rows: "Spent", "Spent a day", "Leads", "Cost per lead", "Qualified leads", "Cost per qualified lead". "—" when there's nothing to divide by.
- "What's compared" line:
  - self: "Compared on the campaign itself."
  - parent: "Compared on the ad set “Broad US”, which this ad is in."
  - version: "The days Meta was reviewing the new version (Nov 9 – Nov 10) count for neither side."
  - stopped: "It's off, so there's no after to compare."
- Rule line: "Judged only once each side has spent at least $120 (2× your $60 target) and has 3 leads." With no target set: "Set a cost-per-lead target in Settings → Targets to judge results." and a link.
- Notes, each one when it applies:
  - "The change was bigger than +20%: Meta relearned for 3 days, so the first days are rough."
  - "Qualified leads can still go up while the team works the leads (until Nov 23)."
  - "Changed in Ads Manager on Nov 13."
  - "A test is running on this ad. See Tests for its verdict."
  - "Waiting for Meta's numbers."
- Expectation block (admins and teammates): "Claude expected: cost per lead under $40." / "Got: $36 over 7 days. **Met.**" / "**Not met.**" / "Too early to say." For text that can't be read: "Claude expected: <text>" with no Met / Not met.
- Buttons:
  - **Put it back** (outline style; primary when the state is worse or lean_worse)
  - **Close**
  - When there's no plan, the reason as muted text instead of the button:
    - "The budget was changed again since: it's $30.00 a day now."
    - "It's already off again."
    - "It's archived, so it can't be switched back."
    - "The ad has a newer version since."
    - "Change it back on the ad's page."
- Budget dialog note: "Before the change on Nov 9 it was **$20.00 a day**."

**Settings → Alerts row**
- Label: "A change didn't help"
- Hint: "After a budget, on/off or new-version change, tell me when cost per lead got worse. Checked after 3, 7 and 14 full days."

**Empty and error states**
- No checkable changes: History unchanged ("Nothing recorded yet.").
- The dialog fails to load: the shared 9.1 error state with Retry.

## Interaction with other features

- **Phase 9.1 / 9.2**: one error state, one Dialog, one suggestion card. The outcome line goes into the shared suggestion card, so `tasks.js` and `board.js` both get it. Vocabulary sits in `format.js`.
- **9.3 entity links**: the scope name in the dialog is an `entityLink()`; `?check=` uses the 9.3 history pattern so Back closes the dialog.
- **9.4 Today / Inbox**: new queue type and triage rule as above. Inbox's `inbox_unread` stays; needs-action counts drop when a change is put back (alert resolved).
- **Leads**: stage changes later raise the qualified counts. Checks keep recomputing until `final` (7 days after the window).
- **Ad versions (5.5)**: the version mode uses `with_live_days` and the same changeover exclusion as `split_results`. Put it back uses the existing restore route.
- **Bulk (8.x)**: each bulk line is its own `meta_changes` row and gets its own check. Changes in the same bulk on parent and child cut each other's windows (shown as "Changed again …").
- **Meta's advice (5.3)**: `recommendation` rows are checked as `self`. There's no Put it back ("Change it back on the ad's page.").
- **Tests (3.x)**: not replaced. The dialog only notes when a test is running on the entity.
- **Status history (8.1)**: changes made in Ads Manager (`status_events`) end windows early, so outside changes don't get credited to the console.
- **money_rules / Targets**: Put it back goes through `budget_change` / `change_problem`. If the ceiling was lowered since, the server refuses with its usual message. Targets come from `targets.py`, never copied.
- **Accounts (7.1)**: the worker runs per account in `account_ctx.use`; the table has RLS.
- **Audit-fix workflow**: the merge points are small. `timeline.merge` gains an optional kwarg, `tasks_with_results` gets an enrichment, the `clean_proposal` key list grows, and the three write routes accept an optional `undo_of`. Rebase on whatever lands there.

## Edge cases

- **Change on the same day as another on the same scope**: the later one cuts the earlier one's after window to 0 days, so the earlier one shows `mixed` at every horizon. The later one is measured normally from the next day.
- **A budget change while the entity was off for part of the before window**: zero-spend days count (they're real). The minimum-data rule then usually says too early, which is the honest answer.
- **The paused ad was the only ad in its ad set**: parent spend after = 0, so the state falls back to `stopped` with the before numbers.
- **Entity deleted or archived later**: the check still shows from stored rows; Put it back gives the reason; rows become final.
- **Change failed** (`ok` false): not checked. A proposal that `failed` shows its failure, never a result.
- **Created ad that never ran**: `not_running`. When it starts (turned on), the `status` change is the anchor for "new".
- **No targets set**: no judging; the dialog shows the Settings → Targets prompt. `targets.lead()` falls back to the qualified target, as Alerts do.
- **Currency other than USD**: sentences use `words.money` (account currency); the frontend uses `format.money`.
- **Data stale** (sync behind): `waiting` with "Waiting for Meta's numbers". Rule 5 (complete days only) holds because windows end by yesterday and the job never reads today.
- **Time zone**: days come from `account_info.today()`; the change day comes from `(created_at AT TIME ZONE tz)::date`.
- **Meta's late conversions**: the 3-day result can still move for up to 7 days, so it isn't final until then. A Needs-action item is raised only once per state class; if later numbers make it look fine, a good item follows and the bad one stays read or unread as it was.
- **Two people press Put it back**: the second gets the server's existing 409 "The budget changed on Meta since you looked".
- **Rollback of a rollback**: Put it back is itself a change, gets its own check, and `undo_of` links them. The original shows "Put back on …".
- **Volume**: 300 changes per pass, two queries each, about 600 cheap indexed queries per 15 minutes at most; in practice Edge Bourne has a handful a week.

## Tests

### Unit (`backend/tests/test_change_checks_logic.py`, unittest, no DB, grouped by function)

`windows`:
- anchor Nov 9 (`first = last = 2026-11-09`), horizon 7, today 2026-11-20 → before (11-02, 11-08), after (11-10, 11-16), days 7, complete True, ready_on 11-17.
- same, today 2026-11-16 → complete False, ready_on 2026-11-17.
- horizon 3, today 2026-11-13 → after (11-10, 11-12), complete True.
- next_change 2026-11-13, horizon 7 → after (11-10, 11-12), before (11-06, 11-08), days 3, cut_by 11-13.
- next_change 2026-11-11, horizon 3 → days 1.
- version: first 11-09, last 11-10 (Meta approved on the 10th), horizon 3 → before (11-06, 11-08), after (11-11, 11-13).
- prev_change 2026-11-05, horizon 7 → before (11-06, 11-08), days 3.

`judge` (lead target 6000 cents, no qualified target):
- before {spend 14000, leads 3}, after {spend 14000, leads 5} → metric cpl_cents, delta -40, confidence 27, state lean_better.
- before {30000, 3}, after {30000, 12} → delta -75, confidence 96, state better.
- before {30000, 12}, after {30000, 3} → delta 300, confidence 96, state worse.
- before {14000, 4}, after {14000, 4} → delta 0, state same.
- after {9000, 2} → state too_early, needs "$30 more spend and 1 more lead".
- before {18000, 4}, after {18000, 0} → state lean_worse (no-leads rule; never `worse` without 3 results).
- With qualified target 6000: before {spend 14000, leads 6, qualified 3}, after {spend 14000, leads 8, qualified 3} → metric cpq_cents. With after qualified 1 → falls back to cpl_cents and adds a note.
- mode new, after {14000, 4}, target 4000 → cpl 3500 → on_target. Mode stopped → state stopped, after None.

`mode_for`:
- budget on campaign c1 → ("self", "campaign", "c1").
- status PAUSED on ad a1 in adset s1 → ("parent", "adset", "s1").
- status PAUSED on campaign → ("stopped", "campaign", id); ACTIVE on campaign → ("new", …).
- update_creative → ("version", "ad", a1); create ad → ("new", "ad", id).
- duplicate / archive / comment_reply / level form → None; ok False → None.

`expect_from_text`:
- "CPL under $40 within 7 days" → {"metric": "cpl", "op": "<", "cents": 4000, "days": 7}.
- "Cost per qualified lead below $60" → {"metric": "cpq", "op": "<", "cents": 6000, "days": 7}.
- "cost per lead drops to $35.50" → {"metric": "cpl", "op": "<=", "cents": 3550, "days": 7}.
- "Per lead under $1,200" → cents 120000.
- "More leads, same budget" → None. "CPM under $10" → None.

`clean_expect`: {"metric": "cpl", "op": "<", "cents": "4000"} → None (must be int). {"metric": "roas", …} → None. days 30 → None. No days → days 7.

`expectation_met`: expect cpl < 4000 with a ready after cpl 3600 → True; 4200 → False; not ready → None; expect cpq while cpq isn't ready → None.

`undo_plan` (money = lambda c: f"${c/100:,.2f}"):
- budget old "2000" new "2400", entity_now budget 2400 → plan {kind budget, from_cents 2400, to_cents 2000}.
- entity_now 3000 → plan None, reason "The budget was changed again since: it's $30.00 a day now."
- status ACTIVE → PAUSED with entity PAUSED → plan {kind status, to ACTIVE}. Entity ACTIVE → reason "It's already on again." Entity ARCHIVED → "It's archived, so it can't be switched back."
- update_creative new_value "New headline (creative 222)", versions [{1, "111"}, {2, "222"}], ad creative 222 → plan {kind version, number 1}. Ad creative 333 → reason "The ad has a newer version since."
- enhancement → plan None, reason "Change it back on the ad's page."

`sentence`: one case per row of the copy table, exact strings (e.g. better 7-day cpl 4667 → 2800 → "Worked: cost per lead $47 → $28 over 7 days (40% cheaper).").

`headline`: rows [3: same, 7: better, 14: waiting] → the 7-day row; all waiting → the 3-day row.

Extra cases in existing test files:
- `test_timeline_logic`: `merge(..., checks={5: {...}})` puts `check` and `change_id` on change 5 only; without `checks` the output is unchanged.
- `test_inbox_logic`: category of `change_result` is money.
- `test_desk_logic`: `clean_proposal` with `expect` and with only text `expected`.

### QA (`qa/flows.cjs`, about 12 new checks; also update the ad-blocker naming guard list if needed)

Seed with `ads/dev/seed_checks.py` (local only, like `seed_board.py`, run from `qa/run.sh` after the sync): three backdated `meta_changes` rows on fake campaign or ad set ids (budget 2000 → 2400 dated 12 days ago; a pause on ad 2 dated 9 days ago; a budget change with a worse result), then `change_checks_db.run()`.

1. Campaign History shows "Worked:" under "Budget $20.00 → $24.00 a day".
2. Details opens the dialog; the 7-day tab's Before / After cells equal the seeded sums; the 14-day tab is disabled and shows a date.
3. The worse change shows **Put it back**. Clicking it opens the budget dialog with the field value "20.00" and the "Before the change on" note. Cancel → no POST to `/budget` (request listener). Confirm → POST body has `daily_budget_cents: 2000`, `from_cents: 2400`, `undo_of: <id>`. Reload → "Put back on … by" text.
4. Claude page: an applied seeded proposal with `expect` cpl < 4000 shows "Expected: cost per lead under $40." and "Met." or "Not met." to match the seed.
5. Inbox: the worse change's item sits under Needs action; after step 3 it leaves the count.
6. `historyHref(level, id, {check})` (campaign: `?id=…&tab=history&check=…`; ad: `?id=…&check=…#tab=history`) opens the dialog; phone Back closes it.
7. Client login: the History line is visible, no **Put it back** anywhere, and `GET /api/changes/<id>/check` has no `undo`, `proposal` or `expect` keys.
8. Teammate on an unassigned campaign: `GET /api/changes/<id>/check` returns 404.
9. Agent API with the dev Mac key: `/api/agent/outcomes` has the three items, `sentence` strings, and no `full_name`, `email` or `phone` anywhere.
10. Phone 390 and 320: no horizontal overflow; dialog tabs and buttons ≥ 44 px; the line wraps.
11. Light and dark screenshots of the dialog and the History line through `qa/shots.cjs`.
12. Naming guard: no class or id starting with ad- / ads- / adset / banner / sponsor / promo.

### Fake Meta additions (`dev/fake_meta.py`)

- `insights_rows` covers `FAKE_INSIGHT_DAYS` (default 35, was 11), same seeded rng, so 14-day windows exist after a fresh sync.
- `GET /fake/_insights_shape?ad=<id>&from=<iso>&spend_times=<x>&leads_times=<y>` multiplies that ad's daily spend and leads from a date, so QA can make a change "work" or "not". `/fake/_insights_shape?reset=1` clears it.
- The sync must pull the longer range in dev: `insights.sync_all(days=35)` once from `run.sh` (Meta is never called from tests).

## Rollout

1. Migration `NNN_change_checks.sql`: relative slot **N+5** in 00-PLAN (after D2, W2, W1a, L1, L2); the actual number is the next free one at build time.
2. Settings switch: Settings → Alerts → "A change didn't help", on by default. Off stops the Inbox items and emails; the History lines and dialog stay.
3. The first worker pass after Update backfills checks for changes from the last 35 days. Live N1–N5 budget and status history since Nov 8 will show mostly "Too early to tell" at first: with $20/day against a $60 target, a side needs $120 and 3 qualified leads.
4. Bridge: `ads/bridge/desk` gets `desk outcomes [--days 60]`. `ads/bridge/skill/SKILL.md` gets this rule: "Before proposing, read `desk outcomes`. Don't suggest again what didn't help without saying what's different this time. Give `expect` as {metric, op, cents, days} with every budget, on/off or new-version suggestion."
5. What Eugene does after Update:
   - Run **Update** on the server.
   - Then, on the Mac, run `ads/bridge/install.sh` and `launchctl kickstart -k gui/$(id -u)/com.edgebourne.ads-desk`. Install the bridge only after the server Update, because older servers don't have `/api/agent/outcomes`. Check for a running Desk task first (memory: bridge-restart-check).
   - Optionally set a cost-per-lead target in Settings → Targets; without it, leads are judged against the $60 qualified-lead target.
6. Nothing new on the Meta side: no app permissions, no new Graph endpoints, no Meta reads.
7. Unverified on real data until about Nov 24 (first complete 14-day window on the live campaign): readings against real late conversions, and the email for "didn't help".

## Effort

M, about 2.5 days:
- pure module + unit tests: 0.75 d
- DB module, worker, routes, desk / agent enrichment: 0.5 d
- frontend (`outcome.js`, controls refactor, History, Claude rows, Settings, Today hook): 0.75 d
- fake Meta, seed script, `flows.cjs` checks, screenshots: 0.4 d
- bridge `desk outcomes` + SKILL.md: 0.1 d
