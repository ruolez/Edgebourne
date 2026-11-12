# D1 · Match Ads Manager: restate older days, check totals, label every number's source

Unit key: `D1-match-ads-manager` · Proposal: "Restate older days, check totals against Ads Manager and label where each number comes from" (audit.json → proposals) · Meta: **read-only** (insights GETs only) · Money: none.

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build step 8 of 9; migration **N+6**. Depends on W2 (review bar, `send_due` claim hook), D2 (`fig-foot` row, `words.py`), L2 (`lead_quality.counted()`) and W1a (`snooze.WORSE`, owner-closed events). Can be pulled forward if Eugene wants it sooner: its only hard dependency is W2.
> - C3: the console's own count is **Received** (key `received`); the pair reads "Meta 12 · Received 11". It counts `lead_quality.counted()` (no test entries, a repeat counts once).
> - C21: pills are **Matches / Differs / Not checked / Couldn't check**. "Off" is the 9.2 delivery word and isn't used here.
> - C20: on chart pages, the source note sits on the left of the shared `<div class="fig-foot">` row that D2 creates, with D2's "N changes in this period" on the right.
> - C22: the report stamp is frozen into W2's sent copy. The admin warning and **Pull these days again** live inside W2's `#rv-bar`. W2's claim step calls `ensure_period`.
> - C26: `numbers_off` is in `snooze.WORSE` (measure = days that differ, worse at ≥ baseline + 3, hint "You'll hear again if 3 more days differ."). It isn't in `diagnose.PLAYBOOKS`.
> - Security: `restate`/`check` run only inside `account_ctx.use(acct)` with that account's token and `act_<id>`. A unit test checks that the lock key differs across accounts. Messages go to `notify.account_admin_ids()`.
> - Bridge: SKILL.md line ships with bridge VERSION 1.14 (C27).

## Goal

1. **Stored numbers stop drifting from Ads Manager.** Today `ad_daily` is rewritten only for the last 7 days (hourly, `jobs.py:75` → `insights.sync_all(days=7)`) and 3 days (quick pull, `refresh_api.DAYS`). Meta keeps changing older days: leads credited back to the view/click day, spend corrections, invalid-activity credits. "Last month", the monthly client report and Compare over older windows silently keep the first numbers they saw.
2. **Prove it.** Once a night, compare our day sums with Meta's own account-level totals for every day of this month and last month (at least 28 days) and keep the result. Settings → Tracking health says "Matches Ads Manager" or "Differs by $3.20 and 1 lead on 2 days", with a read-only "Pull these days again".
3. **Say where each number comes from.** Every figure panel carries a small source note: "From Meta · synced 4:10 AM · complete days to Nov 10" or "Your leads · live". Where Meta's lead count and the console's own count sit together: "Meta 12 · Received 11", with one plain explanation of why they can differ. Reports are stamped with the last check. A warning shows when the data on screen is older than it should be.

Non-goals: no new Meta writes, no automation that touches money, no change to the Refresh button's own "Updated X ago" (it stays the frame's "when did anyone last pull"), no new attribution reporting (7-day vs 1-day comparisons).

## User flow

### Desktop

1. **Any figure page** (Results, Ads manager, Campaign, Ad set, Ad Overview, Compare, Today, Reports). Under the page's figure row (or the table header) sits one line, muted, 12 px:
   `From Meta · synced 4:10 AM · complete days to Nov 10 · matches Ads Manager ⓘ`
   Clicking the line (a `<details>`) opens three short sentences: what "complete days" means, the attribution footnote from `report_logic.footnotes`, and when the check last ran. Admins also get a link "Numbers check in Settings".
2. **Leads figure** on Results, Today and Reports: under the big number, `Meta 12 · Received 11`. Hover/click explains: "Meta counts a lead on the day of the ad view or click; 'Received' counts leads by the day they reached your leads list, without test entries, and a person who filled the form twice counts once. A few can land on different days."
3. **Stale data.** If the newest pull is older than twice the automatic refresh interval (min 30 min), the note turns amber: `From Meta · last synced 2 h ago · numbers may be behind`. If the nightly check hasn't run for 36 h: `… · not checked against Ads Manager since Nov 8`.
4. **Settings → Tracking health → "Numbers vs Ads Manager"** (new panel below Tracking health, anchor `#numbers`, which 9.4's one-section Settings resolves to the Tracking section):
   - Matches: pill **Matches** + "Checked tonight at 4:10 AM for Oct 1 – Nov 10. Both say $1,234.56 spent and 41 leads." + "Last night Meta changed 3 older days; we updated them: +2 leads, −$1.10." (when a restate changed something).
   - Differs: pill **Differs** + "Differs by $3.20 and 1 lead on 2 days." + a table (Day · Ads Manager · Here · Difference, spend and leads), each day linking to Results for that day. Buttons **Pull these days again** (primary) and **Check again** (quiet).
   - Not checked: "Not checked yet. The first check runs tonight after 4 AM, or check now." + **Check now**.
   - Couldn't check: "Couldn't check: Meta asked us to slow down. We'll try again after 9:45 AM."
5. **Inbox**: when days stay off after a night's pull, one FYI item "Some older days differ from Ads Manager" (info). If they are still off after the next night (two runs in a row), it becomes Needs action (warn): "Numbers differ from Ads Manager on Oct 14 and Oct 20" → link `/settings.html#numbers`. It resolves itself when the check matches.
6. **Reports**: under the footnotes, "Checked against Meta's own totals on Nov 11 at 4:10 AM: they match." Admins see an amber note above the headline when the period has off days ("Meta's totals differ for Oct 14 ($0.50, 1 lead). Pull these days again in Settings before sharing."), with a direct **Pull these days again** button for that period.

### Phone (390 px)

- The source note is one line truncated with ellipsis; its `<summary>` is a full-width 44 px tap target; the opened text wraps.
- `Meta 12 · Received 11` stays one line under the number (font 12 px, `--muted`).
- Settings panel: the day table becomes stacked cards (Day heading, then "Ads Manager $12.34 · 3 leads", "Here $12.04 · 2 leads", "Difference +$0.30 · +1 lead"). Buttons full width, 44 px. No form fields (nothing to type), so the 16 px rule only applies to the hidden date inputs of the report-period pull (none needed: it uses the period).

## Data model

Migration `backend/migrations/NNN_numbers_check.sql` (written in one go: dev applies on save).

```sql
-- Meta's own account-level total per day (what Ads Manager shows), read nightly or on "Check now".
-- Compared with SUM(ad_daily) at read time, so a later hourly sync is never judged against an old sum.
CREATE TABLE meta_day_totals (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    day DATE NOT NULL,                        -- the ad account's time zone, like ad_daily.day
    spend_cents BIGINT NOT NULL DEFAULT 0,
    leads INTEGER NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, day)
);
ALTER TABLE meta_day_totals ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON meta_day_totals
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- One row per check or pull: what was read, how far it got, what Meta changed.
CREATE TABLE numbers_runs (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('nightly', 'check', 'pull', 'report')),
    start_day DATE NOT NULL,
    end_day DATE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,   -- NULL for the worker
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    ok BOOLEAN,
    error TEXT,                                -- plain words (meta_client.plain), never the raw token-bearing text
    parts_done INTEGER NOT NULL DEFAULT 0,
    parts_total INTEGER NOT NULL DEFAULT 0,
    changed JSONB,                             -- [{day, spend_cents, leads}] deltas the restate wrote
    summary JSONB                              -- numbers_check.summary() after the run
);
CREATE INDEX numbers_runs_recent_idx ON numbers_runs (account_id, id DESC);
ALTER TABLE numbers_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON numbers_runs
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
```

No change to `ad_daily` (its `synced_at` already says when each row was last read; PK `(day, ad_id)` serves the per-day queries). Grants come from the default privileges set in 020. Add `("numbers_runs", "started_at < now() - interval '180 days'")` to `jobs.PRUNE`. `meta_day_totals` stays small (one row per day) and is kept.

Settings keys (per account, `settings_store`):

| Key | Default | Meaning |
|---|---|---|
| `numbers_check` | on (`None` = on, `"0"` = off) | nightly check + restate |
| `insights_unified_attribution` | `"1"` | pass `use_unified_attribution_setting=true` on every daily insights read (see Open decision) |
| `last_full_sync` | — | ISO time of the last hourly 7-day `sync_all` (today `last_performance_sync` is also set by the 3-day quick pull) |
| `numbers_last_night` | — | local date of the last finished nightly run |
| `numbers_off_runs` | `0` | consecutive runs that ended off (drives info → warn) |

## Backend

### `backend/insights.py` (small refactor, behaviour kept)

- `INSIGHT_EXTRA()` → `{"use_unified_attribution_setting": "true"}` when the setting is on, else `{}`; passed by `sync_daily`, the restate read and the account-total read so all three use the same rules.
- Extract the row → column tuple from `sync_daily` into pure `daily_values(r) -> dict` (spend_cents, impressions, reach, link_clicks, leads, clicks_all, video_3s, thruplays, video_p25..p100) and `upsert_daily(r)`; `sync_daily(days=30, since=None, until=None)` keeps its signature for existing callers and accepts an explicit window.
- `sync_all` additionally sets `last_full_sync` only when `days >= 7` (the hourly pass and `/performance/sync`).

### New `backend/numbers_check.py`

Pure functions (top of file, no DB, unit-tested):

```python
TOLERANCE_CENTS_PER_ROW = 1        # ad-level spend is rounded per ad; the account total once
PART_DAYS = 7
NIGHT_HOUR = 4                      # account time; Meta has settled the day before by then
MAX_PULL_DAYS = 93
OLDEST_MONTHS = 37                  # Meta keeps insights 37 months

def check_window(today: date) -> tuple[date, date]
    # (min(yesterday - 27, first day of last month via ranges.window("lastmonth")), yesterday)

def parts(start: date, end: date, size: int = PART_DAYS) -> list[tuple[date, date]]

def day_totals(rows: list[dict]) -> dict[date, dict]
    # Meta account rows (level=account, time_increment=1) -> {day: {spend_cents, leads, impressions}}
    # uses insights.to_cents / insights.lead_count so both sides count leads the same way

def compare(meta: dict[date, dict], stored: dict[date, dict], rows_per_day: dict[date, int],
            newer: set[date], start: date, end: date) -> list[dict]
    # one entry per day in [start, end]: {day, meta, here, diff_spend_cents, diff_leads, state}
    # state: "match" | "off" | "newer" (our rows were read after Meta's total and differ: judged next check)
    #        | "unchecked" (no Meta total stored for the day)
    # a day missing on one side counts as zeros; spend matches within rows_per_day * TOLERANCE_CENTS_PER_ROW
    # (min 1), leads must be equal

def summary(days: list[dict]) -> dict
    # {state: "match"|"off"|"unchecked", off_days: [iso...], spend_off_cents: sum |diff|, leads_off: sum |diff|,
    #  meta_spend_cents, meta_leads, start, end}

def headline(s: dict, money) -> str
    # "Matches Ads Manager" | "Differs by $3.20 and 1 lead on 2 days" | "Not checked yet"

def restate_plan(stored_keys: set[tuple[date, str]], fetched: list[dict], part: tuple[date, date],
                 meta_days: dict[date, dict]) -> dict
    # {"upsert": fetched rows, "zero": [(day, ad_id)]}: rows we have but Meta no longer returns.
    # Zero only when this part returned at least one row AND, for that day, the fetched rows add up to
    # Meta's account total (within tolerance). Otherwise leave them (an empty or short answer is not proof;
    # same rule as the "if seen:" guard in sync_ads).

def changes(before: dict[date, dict], after: dict[date, dict]) -> list[dict]
    # [{day, spend_cents: after-before, leads: after-before}] for days that moved, oldest first

def window_synced(day_synced: dict[date, datetime]) -> datetime | None
    # the oldest of the per-day newest read times: every day on screen is at least this fresh

def freshness(now: float, last_pull: float | None, auto_minutes: int, last_check: float | None) -> dict
    # {"behind": now - last_pull > max(2*auto_minutes, 30) min, "check_old": no check or > 36 h}

def night_due(local: datetime, last_night: str | None) -> bool
    # local.hour >= NIGHT_HOUR and last_night != local.date().isoformat()

def pull_range(start: date, end: date, today: date) -> tuple[date, date] | str
    # validated window or the plain error: "Pick days up to yesterday", "Pick at most 93 days at a time",
    # "Meta only keeps the last 37 months"

def pair(meta_leads: int, received: int) -> dict
    # {"meta": 12, "received": 11, "differ": True}

def source_info(*, synced: datetime | None, end: date, today: date, check: dict | None,
                fresh: dict, scope_note: bool) -> dict
    # the payload every figure endpoint returns as "source" (below)
```

DB parts:

- `read_meta_totals(start, end) -> dict[date, dict]`: one `meta_client.paged(f"act_{account}/insights", level="account", time_increment=1, fields="spend,impressions,actions", time_range=…, **INSIGHT_EXTRA())`; upserts `meta_day_totals`.
- `stored_totals(start, end) -> (stored, rows_per_day, day_synced)`: `SELECT day, SUM(spend_cents), SUM(leads), COUNT(*), MAX(synced_at) FROM ad_daily WHERE day BETWEEN … GROUP BY day` (account-wide; RLS scopes the account).
- `current(start=None, end=None) -> list[dict]`: `compare()` over stored Meta totals vs `stored_totals`, `newer` = days whose `MAX(synced_at) > meta_day_totals.fetched_at`.
- `restate(start, end, kind, user_id=None) -> run`: inside the **same per-account pull lock as `refresh_api.pull_latest`** (`LOCK_KEY * 1000 + account`), so the quick pull, hourly sync and restate never interleave. Steps: insert `numbers_runs` row → `read_meta_totals` (1 call) → for each 7-day part: ad-level read (`level=ad, time_increment=1, fields=INSIGHT_FIELDS`), `restate_plan`, upserts + zeroing in one transaction per part, `parts_done += 1` → `changes()` → `summary()` → finish row. On `MetaError` with a rate code or `code="cooldown"`: stop, keep finished parts, `ok=false`, error in plain words. On Meta's "reduce the amount of data" refusal (code 1 / message match): retry that part one day at a time once.
- `check(kind="check", user_id=None)`: account totals only (1 call) + `summary()`; no ad-level reads.
- `run_nightly()` (worker): if `numbers_check` on, token and account set, `night_due(...)`, and `meta_client.cooling_until()` is None → `restate(*check_window(today), "nightly")`; on success set `numbers_last_night`, update `numbers_off_runs`. A failed night is retried on later passes, at most every 30 min, until 3 tries; then it waits for the next night.
- `ensure_period(start, end)`: called by W2's `send_due` in the claim step, before the snapshot is taken. If no successful run covering `[start, end]` finished after `end`, run `restate(start, end, "report")`. Failure never blocks the email; the stamp says what is known. The stamp is stored inside W2's frozen `snapshot`, so a sent copy keeps the check as of sending.

### Worker (`backend/jobs.py`)

In `slow(conn, acct)`, after the hourly sync and before alerts: `numbers_check.run_nightly()` wrapped like the other jobs (`log.info("account %s: numbers check skipped: %s")`). Alerts run right after, so the Inbox item appears in the same pass.

### Alerts (`backend/alerts.py`, `backend/inbox.py`)

- `DEFAULTS["numbers_off"] = {"on": True}`; `snapshot()` adds `"numbers": {"summary": …, "off_runs": int}` from the last finished nightly/pull run (no Meta call).
- `evaluate`: when `summary.state == "off"` and the run was nightly or a pull: level `info` with `off_runs == 1`, `warn` when `off_runs >= 2`. Title "Numbers differ from Ads Manager on Oct 14 and Oct 20" (≤3 days named, then "and N more"); lines: "Ads Manager says $12.34 and 3 leads for Oct 14; we have $12.04 and 2. We pull these days again every night." href `/settings.html#numbers`. Entity `account`, dedupe per day as today. Closes itself (condition alert) when the check matches.
- Each `numbers_off` alert passes `measure` = the number of days that differ (W1a column). It is a `condition`, so `alerts.run` closes it when the check matches. Snoozable through `snooze.WORSE["numbers_off"]` (worse at ≥ baseline + 3).
- `inbox.CATEGORY["numbers_off"] = "system"`. With 9.4 triage: `info` → FYI, `warn` → Needs action.
- Settings → Alerts lists the rule as "Our numbers differ from Ads Manager" (toggle only).

### Routes: new `backend/numbers_api.py`, blueprint `/api/numbers`

| Route | Who | What |
|---|---|---|
| `GET /api/numbers?start=&end=` | `admin_required` (owner admin and account admin) | days table (`current()`), `summary`, `headline`, last 5 runs (kind, when, by, ok, parts, changed, error), next nightly time, `cooling_until` |
| `POST /api/numbers/check` | admin | `check()`; throttled 60 s per account (`refresh_api.refresh_due` style, key `numbers_last_check_at`); `log_activity("numbers.check")` |
| `POST /api/numbers/pull` `{start, end}` (or `{period: "week"|"month", start}` from Reports) | admin | `pull_range()` validation → `restate(…, "pull", user)`; 409 "Already pulling from Meta, one moment" when the lock is held; 429-style JSON "Meta asked us to slow down. Try again after 9:45 AM." when cooling; `log_activity("numbers.pull", {start, end, changed})` |

Teammates (`member`) and read-only clients get 403 on all three. Nothing here is a Meta write, so `meta_changes` is untouched; activity logs carry who pulled what.

### `source` on existing figure endpoints (all roles, read-only data)

Added to: `performance_api.overview_data` (Results, and through it Today and the Desk snapshot), `ads_api` `GET /ads` (manager) and `GET /ads/ad/<id>`, `entities_api` campaign / ad set / compare, `home_api.home`, `reports_api.build`. Shape:

```json
"source": {
  "meta": {"synced_at": "2026-11-11T12:10:00Z", "complete_to": "2026-11-10", "partial_today": false,
           "behind": false, "check": {"state": "match", "checked_at": "…", "off_days": 0, "old": false,
                                       "spend_off_cents": null, "leads_off": null}},
  "leads": {"meta": 12, "received": 11, "differ": true}
}
```

- `synced_at` = `window_synced` for the page's own window, so "last month" honestly says "synced 4:10 AM" (the night's restate), not the last quick pull.
- `check.state` is only for days inside the page's window. For `member` and `client`: `spend_off_cents` / `leads_off` are `null` (no figures they can't act on), state is still given.
- `leads.received` = `COUNT(*) FROM leads l WHERE {lead_quality.counted("l")} AND (created_time AT TIME ZONE tz)::date BETWEEN …` with the same campaign scope as the page (`visible_campaign_ids`); `performance_api` already queries qualified from leads, so it's one more `COUNT(*)` in the same statement.
- `/api/ads` and `/api/performance` drop the unused `last_sync` field after the frontend reads `source` (keep one release for the Desk snapshot, then remove).

### Desk

`overview_data` carries `source`, so `GET /api/agent/snapshot` tells Claude when numbers are off or old. Add one line to `ads/bridge/skill/SKILL.md`: "If `source.meta.check.state` is `off` for the window you judge, say so and don't recommend budget moves on those days." (Re-run `bridge/install.sh`; bridge code unchanged.)

## Frontend

### Shared

- `js/format.js` (the 9.2 vocabulary): `SOURCE` copy and helpers:
  - `sourceLine(src)` → `"From Meta · synced 4:10 AM · complete days to Nov 10 · matches Ads Manager"`. Variants: `"… · today so far, changes through the day"` (Today's live spend), `"… · differs from Ads Manager on 2 days"`, `"… · being checked again"` (members/clients when off), `"From Meta · last synced 2 h ago · numbers may be behind"`, `"… · not checked against Ads Manager since Nov 8"`.
  - `leadsPair(p)` → `"Meta 12 · Received 11"`, only when the two counts are both present.
  - `SOURCE_HELP` (shown when opened): 
    1. "Complete days only, in the ad account's time zone (Los Angeles). Today is partial and Meta reports some leads a day or two late."
    2. "Leads are what Meta counted under each ad set's attribution setting: on the day of the ad view or click, not the day the form arrived."
    3. "Every night we read the last 28 days and last month again from Meta and compare them with Ads Manager's own totals."
    4. Last check sentence from `check`.
  - `LEADS_PAIR_HELP`: "Meta counts a lead on the day of the ad view or click. Received counts leads by the day they reached your leads list, and leaves out test entries; a person who filled the form twice counts once. A few can land on different days."
- `js/ui.js`: `sourceNote(src, {scope})` returns `<details class="src-note[ is-behind| is-off]"><summary>…</summary><div class="src-help">…</div></details>` and `pairNote(p)` returns `<span class="src-pair" title="…">Meta 12 · Received 11</span>`. Admin extra in the help: `<a href="/settings.html#numbers">Numbers check in Settings</a>`. Scope note on campaign-scoped pages: "The Ads Manager check covers the whole account."
- `css/app.css`: `.src-note` (12 px, `--muted`, chevron, `summary` min-height 44 px under `(pointer: coarse)`), `.src-note.is-behind` / `.is-off` (amber token from 9.2, never the signal green), `.src-help`, `.src-pair`; `.nc-days`, `.nc-day` cards for Settings. No `style=""`, no inline script (CSP). Names pass the ad-blocker guard (`src-`, `nc-`, `numbers`).

### Pages (each renders `sourceNote(data.source)` once, right under its figure row or table toolbar)

| Page | File | Where |
|---|---|---|
| Today | `home.js` | under the money row; "today so far" variant for live spend; `pairNote` under the Leads figure |
| Results | `performance.js` | under the figure row; `pairNote` under Leads (next to "Qualified or won", sub "got that far · from your leads") |
| Ads manager | `manager.js` / `listing.js` | in the toolbar line under the view tabs |
| Campaign / Ad set | `entity.js` | under "Figures vs before" |
| Ad Overview | `creative.js` | under the results block |
| Compare | `compare.js` | under the creatives row |
| Reports | `report.js` | stamp under the footnotes (frozen in sent copies); admin warning + **Pull these days again** inside W2's `#rv-bar`, never in the report body; `pairNote` in the funnel's first step ("Leads received") |

Labels: "Qualified or won · from the leads inbox" becomes "Qualified or won" with the sub "got that far · from your leads" (9.2: Inbox now means the notifications feed).

### Settings → `#numbers` panel (`settings.html`, `settings.js`)

```html
<section class="panel" id="numbers">
  <div class="panel-head"><h2>Numbers vs Ads Manager</h2><p id="nc-state"></p><span class="spacer"></span>
    <button type="button" class="link-btn" id="nc-check">Check now</button></div>
  <div class="panel-body stack tight" id="nc-body"><p class="muted flush">Reading…</p></div>
</section>
```

Exact copy:

| State | Pill | Body |
|---|---|---|
| match | `Matches` | "Checked {Nov 11, 4:10 AM} for {Oct 1 – Nov 10}. Both say {$1,234.56} spent and {41} leads." |
| off | `Differs` | "Differs by {$3.20} and {1 lead} on {2 days}." + table + buttons **Pull these days again** / **Check again** |
| unchecked | `Not checked` | "Not checked yet. The first check runs tonight after 4 AM, or check now." |
| couldn't | `Couldn't check` | "Couldn't check: {plain Meta error}." + "We'll try again after {9:45 AM}." when cooling |
| restated | — | "Last night Meta changed {3} older days; we updated them: {+2 leads, −$1.10}." |
| pulling | — | button text "Pulling {Oct 14 – Oct 20} from Meta…" (disabled); then toast "Pulled 7 days again. {Matches Ads Manager now.}" or "Pulled 7 days again. {Still off by $0.50 on Oct 14: Meta's totals sometimes settle a day later.}" |
| switch | — | checkbox "Check every night" with hint "Reads from Meta only. Nothing in your ads changes." |
| footer | — | "Ads Manager's totals include ads you deleted. Spend can differ by a cent per ad from rounding." |

Day table columns: **Day · Ads Manager · Here · Difference** (spend and leads in each cell, account currency via `format.money`). Day links to `/performance.html?range=custom&start=…&end=…` (9.3 entity link pattern). Range for "Pull these days again" = first to last off day (capped at 93 days).

## Interaction with other features

- **Phase 9 (built in parallel):** copy goes into `format.js` (9.2 single vocabulary); `sourceNote` is one more shared part next to the 9.2 Empty state / Dialog; amber uses the 9.2 warning token. Inbox 9.4 triage: `numbers_off` info → FYI, warn → Needs action. Today queue: only the warn alert enters it, ranked under ads with problems. Settings 9.4 "one section at a time": `#numbers` maps to the Tracking section (add it to the anchor map). 9.5 Gallery reuses `source` when it lands (numbers come from `ad_daily`).
- **Refresh / frame:** unchanged. The frame's "Updated X ago" stays the Refresh button's state; the source note is about the data on the page.
- **Quick pull and hourly sync:** share the per-account pull lock with restates; restate is skipped (retried) when either holds it.
- **`stale_data` alert (3 h):** stays the "Meta hasn't answered" alarm; the page's "may be behind" warning is the gentler on-screen version (2× auto interval, min 30 min).
- **Client reports + "review before send" proposal:** `send_due` calls `ensure_period` before building; the draft (once that proposal ships) shows the same stamp and the admin warning, so Eugene sees off days before approving. The report-funnel proposal (start from inbox leads) uses `leads.received`; this unit only labels both counts.
- **Outside-edit proposal (budget changes in Ads Manager):** independent; no shared tables.
- **Compare / Experiments verdicts:** they read `ad_daily`, so restated days change verdicts over time. Experiment summaries keep showing their own numbers; Compare shows the source note so a changed verdict has a visible reason.
- **Money rules / Accept sheet:** untouched. Nothing here writes to Meta or changes budgets.
- **Agency mode:** everything is per account (RLS tables, settings keys, lock key includes the account id, worker loops accounts).

## Edge cases

- **Meta answers with nothing for a part** (transient empty data): upserts nothing, zeroes nothing (`restate_plan` guard); the check then shows "off" and the next night tries again.
- **An ad-day Meta credited back to zero** (row disappears): zeroed only when that day's fetched rows add up to Meta's account total.
- **Rounding:** ad-level spend rounds per ad; tolerance is 1 cent per stored row that day.
- **Day read after the check** (`newer`): shown as "Updated since the check" (muted), not counted as off.
- **Deleted ads:** included on both sides (insights return them; `ad_daily` keeps them).
- **Rate limit / cooldown** mid-pull: finished parts stay; run row says "Stopped after 3 of 9 parts: Meta asked us to slow down"; UI shows the retry time from `cooling_until`. Never retries in a loop.
- **Large accounts:** 7-day parts; on "reduce the amount of data", that part one day at a time; at most 9 ad-level calls + 1 account call a night.
- **Pull while another pull runs:** 409 "Already pulling from Meta, one moment".
- **Ranges:** pulls end yesterday at the latest; at most 93 days; never older than 37 months.
- **No spend in the window:** "Nothing spent from Oct 1 to Nov 10; nothing to compare." (state match, totals 0).
- **Meta not connected / account not connected (agency):** panel says "Connect Meta first in Settings → Meta"; nightly skips silently.
- **Account time zone change:** day boundaries move on Meta's side; the check will show off days once; a pull fixes them. Noted in the help text? No (rare); the run log shows it.
- **Attribution parameter switched on** (first night after Update): many older days may change once; the restate note lists them ("Meta changed 18 older days"); that is expected and said in the release note.
- **Test leads:** never counted in Received; Meta does not count Lead Ads Testing Tool leads either.
- **Clients and members:** see source notes and state words only; no amounts off, no buttons, no Settings link.
- **Share links:** the stamp is computed when the shared report is opened (`build` runs per request), so it's always current.

## Tests

### Unit: `backend/tests/test_numbers_check_logic.py` (no DB)

`describe`-style classes per function; dates as `date(2026, m, d)`.

| Function | Input | Expected |
|---|---|---|
| `check_window` | today 2026-11-11 | (2026-10-01, 2026-11-10) |
| `check_window` | today 2026-11-30 | (2026-10-01, 2026-11-29) |
| `check_window` | today 2026-12-01 | (2026-11-01, 2026-11-30) |
| `check_window` | today 2026-03-01 | (2026-02-01, 2026-02-28) |
| `check_window` | today 2026-11-20 | (2026-10-01, 2026-11-19) (last month starts before yesterday−27 = Oct 23) |
| `parts` | Oct 1 → Oct 15, size 7 | [(Oct 1, Oct 7), (Oct 8, Oct 14), (Oct 15, Oct 15)] |
| `parts` | Oct 1 → Oct 1 | [(Oct 1, Oct 1)] |
| `day_totals` | [{date_start "2026-10-14", spend "12.34", impressions "900", actions [{onsite_conversion.lead_grouped, "3"}]}] | {Oct 14: {spend_cents 1234, leads 3, impressions 900}} |
| `compare` | meta {Oct 14: 1234/3}, here {Oct 14: 1234/2}, rows 5 | state off, diff_spend 0, diff_leads +1 |
| `compare` | meta 1236/2, here 1234/2, rows 5 | match (within 5 ¢) |
| `compare` | meta 1300/2, here 1234/2, rows 5 | off, diff_spend +66 |
| `compare` | meta none, here 250/0 | off, diff_spend −250 |
| `compare` | meta 0/0 missing here | match |
| `compare` | off day in `newer` | state newer |
| `compare` | no Meta total stored for Oct 14 (window includes it) | unchecked |
| `summary` | [match, off(+66,+1), off(−20,0)] | state off, off_days 2, spend_off_cents 86, leads_off 1 |
| `headline` | that summary, USD | "Differs by $0.86 and 1 lead on 2 days" |
| `headline` | all match | "Matches Ads Manager" |
| `restate_plan` | stored {(Oct 14,a1),(Oct 14,a2)}, fetched [Oct 14 a1 $5.00], meta Oct 14 = 500 | zero [(Oct 14, a2)] |
| `restate_plan` | same, meta Oct 14 = 900 | zero [] |
| `restate_plan` | fetched [] | zero [] (guard) |
| `changes` | before {Oct 14: 1234/2, Oct 15: 500/1}, after {Oct 14: 1200/3, Oct 15: 500/1} | [{day Oct 14, spend_cents −34, leads +1}] |
| `window_synced` | {Oct 14: 09:42, Oct 15: 04:10} | 04:10 |
| `window_synced` | {} | None |
| `freshness` | pull 40 min ago, auto 15 | behind True |
| `freshness` | pull 20 min ago, auto 15 | behind False |
| `freshness` | pull 40 min ago, auto 60 | behind False (threshold 120) |
| `freshness` | last check 37 h ago | check_old True; None → True |
| `night_due` | 2026-11-11 03:59, last "2026-11-10" | False |
| `night_due` | 2026-11-11 04:00, last "2026-11-10" | True |
| `night_due` | 2026-11-11 23:00, last "2026-11-11" | False |
| `pull_range` | Nov 11 → Nov 11, today Nov 11 | "Pick days up to yesterday" |
| `pull_range` | span 94 days | "Pick at most 93 days at a time" |
| `pull_range` | Oct 14 → Oct 20 | (Oct 14, Oct 20) |
| `pull_range` | start 38 months ago | "Meta only keeps the last 37 months" |
| `pair` | (12, 11) / (3, 3) | differ True / False |
| `source_info` | member view, check off | `spend_off_cents` None, state "off" |

Extend `test_alerts_logic.py`: `numbers_off` → info at off_runs 1, warn at 2, nothing when match or rule off. Extend `test_inbox_logic.py`: `category("numbers_off") == "system"`. Extend `test_insights_logic.py`: `daily_values` on an existing fixture equals today's tuple order (refactor safety).

A restate loop test with an injected fetch (no DB, pass `fetch` and `write` callables into a pure `run_parts(parts, fetch, plan, write)`): the third part raises `MetaError(code=17)` → parts_done 2, ok False, error "Meta asked us to slow down…", no further fetch calls.

### Fake Meta (`ads/dev/fake_meta.py`)

- `act_<id>/insights` with `level=account` and `time_increment=1`: per-day sums of `insights_rows("ad")` (spend, impressions, actions with the lead action), filtered by `time_range`.
- Level `ad` reads honour `time_range` (Meta does). Check `flows.cjs` for anything that relied on the 3-day quick pull storing all 11 days; such a flow calls `POST /api/performance/sync` first.
- Accept and ignore `use_unified_attribution_setting`.
- `GET /fake/_restate?day=YYYY-MM-DD&ad=<id>&spend=<+-dollars>&leads=<+-n>`: Meta changes an older day (applied to both ad and account reads). `GET /fake/_restate?clear=1` resets.
- `GET /fake/_restate_drop?day=&ad=`: that ad-day disappears from the ad-level read and its spend leaves the account total (credit back).
- `GET /fake/_short_answer?part=1`: the next ad-level read for a window returns no rows while the account read still has totals (guard test).
- No rate-limit simulation in QA (a code 17 pauses the dev account for 5 minutes and breaks later flows); covered by the unit test.

### `qa/flows.cjs` (new block after Tracking health, ~14 checks; uses the 9.4 `openSettings(section)` helper when it exists)

1. `POST /api/performance/sync` then Settings `#numbers`: `#nc-check` → `#nc-state` reads "Matches" and `#nc-body` names the window.
2. `/fake/_restate?day=<yesterday−20>&ad=<N1>&spend=+0.50&leads=+1` → Check now → "Differs by $0.50 and 1 lead on 1 day"; `.nc-day` has that day; its link opens Results with `range=custom`.
3. **Pull these days again** → toast "Pulled 1 day again." and `#nc-state` "Matches"; body shows "Meta changed 1 older day … +1 lead, +$0.50".
4. `/fake/_restate_drop` on another day + pull → that ad-day's `ad_daily` row reads 0 (via `/api/performance?range=custom…` totals) and the check matches.
5. `/fake/_short_answer` + pull → stored rows unchanged, state stays off, run error none (guard holds), then clear.
6. Results: `.src-note summary` contains "From Meta" and "complete days to"; open it → text contains "attribution"; `.src-pair` reads `Meta \d+ · Received \d+`.
7. `.src-note` present on home, ads (manager), campaign, adset, ad, compare and report pages.
8. Last month range on Results: note says "synced" with the restate time (not "just now").
9. Inbox: after an off pull that the fake keeps off (`/fake/_restate` re-applied after the pull), the alert run creates an FYI item "Numbers differ from Ads Manager"; a matching check resolves it.
10. Teammate session: `GET /api/numbers` → 403; `.src-note` text has no "$"; no `#nc-*` on any page.
11. Client session: report shows the stamp "Checked against Meta's own totals"; no buttons inside `.src-note`.
12. Phone 390: `.src-note summary` bounding box height ≥ 44; no horizontal overflow on Results and Settings.
13. Ad-blocker guard (existing `qa/flows.cjs:1514` sweep) passes with the new names.
14. Clean up: `/fake/_restate?clear=1`, check matches again.

`dev/qa_leaks.py` walks every GET route: confirm `/api/numbers` returns only the current account's days.

## Rollout

1. Migration `NNN_numbers_check.sql`: relative slot **N+6** in 00-PLAN (after D2, W2, W1a, L1, L2, D3); the actual number is the next free one at build time.
2. Settings: `numbers_check` on by default; `insights_unified_attribution` on by default (open decision below); alert rule `numbers_off` on.
3. Ship order inside one commit series (ROADMAP §4): pure functions + tests → fake Meta → `numbers_check.py` + worker + API → Settings panel → `source` on endpoints + notes on pages → QA → SKILL.md line + `bridge/install.sh`.
4. Commit: `feat(ads): check numbers against Ads Manager and label their source`. Push only when Eugene says.
5. **After Update, Eugene does nothing.** The first check runs that night after 4 AM Los Angeles time; he can press **Check now** in Settings → Tracking health → Numbers vs Ads Manager to see it at once. Tell him: "The first night may update a number of older days; that is Meta's corrections arriving, not a problem."
6. **Unverified on real Meta (owe a live check):** account-level `time_increment=1` totals equal what Ads Manager shows for the same days (compare two days by hand once); the effect of `use_unified_attribution_setting=true` on Edge Bourne's lead counts; Meta's "reduce the amount of data" error code for long ad-level reads.

**Open decision (conventional pick made):** pass `use_unified_attribution_setting=true` on daily insights reads. Ads Manager reports each ad set by its own attribution setting; the API only does so with this flag, so without it "matches Ads Manager" compares the console with an API default rather than with what Eugene sees. Pick: on, behind the setting so it can be turned off if the live check shows otherwise. Older stored days outside the restated window keep the old basis (shown in the run log only).

## Effort

**M, about 2.5 days.** Pure logic + tests 0.5 d; `numbers_check.py`, worker, API, alert 0.5 d; fake Meta 0.25 d; Settings panel + shared `sourceNote`/`pairNote` + seven pages 0.75 d; QA flows + screenshots 0.5 d. Meta load: +1 account call and ≤ 9 ad-level calls per account per night, +1 or more per manual check/pull.
