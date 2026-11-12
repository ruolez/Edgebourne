# D2: Outside edits, the 3-day budget rule, and change marks on every chart

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build step **1** of 9; migration **N** (the first of these seven; next free at build time, 031 today).
> - D2 owns these shared pieces:
>   - S1 `backend/words.py` (`money`, `day`, `weekday`, `day_time`, `ago`) and the `format.js` twins
>   - S2 `links.history_href` / `historyHref`
>   - S3 `notify.account_admin_ids()`, if the audit fix hasn't added it; switch `raise_found` to it
>   - S4 `status_history.SETUP` / `OUTSIDE_FIELDS` / `headline`
>   - S5 the changes feed (`changes_in`, `timeline.merge(..., versions=(), checks=None)`)
>   - S6 the `fig-foot` row
>   - S7 `confirmDialog(confirmLabel)`
> - C1: History links are `campaign.html?id=X&tab=history`, `adset.html?id=X&tab=history`, `ad.html?id=X#tab=history`, always through the helper.
> - C14: report "What we did" belongs to W2. D2 provides only `OUTSIDE_FIELDS` and `headline`. In report items the key is `where` (console/outside); `by` is a person.
> - C16: `outside_edit` **warn** is an owner-closed event (`resolved: False`), closed by **Done** or after 72 h. **Info** is resolved at once.
> - C24: `editBudget({level, id, name, current, suggest?, note?, undoOf?})`. D2 builds the last-change read; D3 adds `suggest`, `note` and `undoOf` later.
> - Security: `recent` is **recomputed at write time** on set_budget, proposal approve, bulk apply (per line) and advice apply. A signed preview or check plan is never trusted for it. `accept_recent` on the Accept sheet comes only from a ticked item.
> - Bridge: snapshot keys + SKILL.md paragraph ship as bridge VERSION 1.10 (C27).

Unit D2 joins two audit proposals that read the same events:

1. "Record budget and schedule edits made in Ads Manager, and warn on budget changes under 3 days apart" (value high, effort M, touches money, no Meta writes).
2. "Change markers on every chart" (value medium, effort S, no Meta writes).

This spec was checked against the code on 2026-11-11: `status_history.py`, `sync.py`, `money_rules.py`, `timeline.py`, `ads_api.py` (set_budget, apply_budget, proposal_plan/approve), `bulk.py` / `bulk_api.py`, `advice_api.py`, `desk_view.review_item`, `reports_api.build`, `alerts.py`, `inbox.py`, `entities_api.py`, `charts.js`, `controls.js`, `manager.js`, `decide.js`, `report.js`, `dev/fake_meta.py`, and `qa/flows.cjs`. Line numbers may move while the audit-fix workflow is running. Where this spec says "today", it means the code as of that date.

---

## Goal

**Two things are missing today:**

- **Outside edits go unrecorded.** `status_history.FIELDS` compares only status, review, issues and learning. When someone changes a budget, bid, start/end date or audience in Ads Manager (or Claude does it through MCP on the Mac), the next sync overwrites the stored row and records no event. That change never reaches History, the Inbox, the client report's "What we did", or Claude's snapshot.
- **Rule 6 is never checked.** The rule is "one budget change at least 3 days apart". `money_rules.change_problem` only checks the +20% step and the ceiling, so a second raise two days after the first goes through with no warning. The console also doesn't notice a budget raised outside it: `ads_api.set_budget` quietly writes the live amount into the stored row (`ads_api.py:612-614`), which also hides that outside edit from the next sync.

**What D2 adds:**

1. **Every change is recorded.** Every change to daily or lifetime budget, campaign spending limit, bid strategy, bid amount, start time, end time or audience on a campaign or ad set becomes a `status_events` row. It is marked as made outside the console unless a console write explains it.
2. **Outside edits are shown everywhere.** They appear in History, the Inbox, the client report ("in Ads Manager") and the Desk snapshot.
3. **Every budget confirmation shows the last change.** That covers the budget dialog, bulk preview, Accept sheet and Meta's advice. Raising a budget less than 3 days (72 h) after its last change needs the same deliberate yes as a step over +20%. The server enforces this with `accept_recent`, and Claude's suggestions are never pre-ticked when it applies.
4. **Charts show what changed, and when.** Every daily chart (Campaign, Ad set, Ad, Results, Compare, the peek drawer) gets small marks under the days something changed, with the changes listed on hover or tap and in a "changes in this period" list under the charts.

**What D2 never does:**

- It never changes anything on Meta, and it adds no Meta writes.
- It never acts on its own.
- It never loosens a rule: the 3-day window is a constant with no switch.
- It never blocks a decrease or a rollback to the exact previous budget.

---

## User flow

### Desktop

**A. Eugene raises the budget in Ads Manager** (or Claude does on the Mac):
1. Within an hour (the hourly sync, a manual Refresh, or the next budget dialog's fresh read), the console records "Daily budget $20.00 → $30.00 a day", by "Ads Manager".
2. The Inbox gets one item: **Budget changed in Ads Manager: $20.00 → $30.00 a day**. The level is warn when the step breaks a console rule (more than +20%, above the ceiling, or under 3 days since the last change). A warn item sits in **Needs action** and is also emailed, like other warn alerts. Otherwise it is info, in **FYI**, and shown in the console only.
3. The campaign page's History tab shows the change with "Ads Manager" as who. The Spend and Leads charts get a money mark on that day.
4. The monthly client report lists it under "What we did" with "(in Ads Manager)".

**B. Eugene raises the same budget again in the console the next day:**
1. He clicks the budget chip. The dialog reads the last change first (a database read) and shows: *Last change: Nov 9, $20.00 → $30.00 a day, in Ads Manager, 1 day ago.*
2. He types $36. The hint shows the percent change, plus: **Less than 3 days since the last change.** Meta is still adjusting to it, and another raise now makes results hard to read. The usual rule is to wait until Nov 12, 3:40 PM.
3. The confirm button changes from "Change budget" to **Raise anyway**. Clicking it sends `accept_recent: true`. Cancel changes nothing.
4. If he types $20 (the budget before the last change), the hint says *Back to $20.00, the budget before the last change.* The button stays "Change budget", and no extra yes is needed.
5. If he types $25 (a decrease), the hint shows only the last-change line. No extra yes is needed.

**C. Bulk budget change from the Ads manager:**
- The preview line for a budget that changed under 3 days ago shows a pill **changed 1 day ago** next to the amounts.
- The summary adds: **Some of these changed less than 3 days ago.** The confirm button reads **Apply anyway**.
- The server refuses the apply without `accept_recent` (409).

**D. Claude's budget suggestion on the Accept sheet:**
- The item is never pre-ticked. It says: *Budget last changed Nov 9 ($20.00 → $30.00, in Ads Manager), 1 day ago. Tick this yourself if you still want it.*

**E. Meta's "Spend more on a campaign that's doing well" (Today → Meta's advice):**
- The step line adds *Last change 1 day ago*.
- The apply confirmation uses **Raise anyway**, and the body carries `accept_recent`.

**F. Charts:**
- Under the x-axis of each daily chart, a small tick sits under every day with a change. The colour shows the kind:
  - **Budget**: budget, bids, spending limit.
  - **On/off**: switches, start and end dates, archive.
  - **Edits**: new ad, new version, audience.
  - **Meta**: approved, rejected, issues, learning.
- Budget days also get a faint dashed guide line through the plot, so a jump in cost per lead can be lined up with the budget change.
- Hovering a day (the existing tooltip) adds the changes for that day under the value.
- Under the charts, a single line reads **3 changes in this period**, with a **Show on charts** switch. It opens a list of the changes, each linking to the History of what changed.

### Phone (390 px)

- The ticks are decorative at that size. Tapping anywhere in a day's column opens the same tooltip as hovering, with the changes. Tapping outside closes it.
- The "N changes in this period" row is a full-width 44 px `summary`. The **Show on charts** switch is 44 px. Each list row is at least 44 px tall and links to the History.
- The budget dialog field stays 16 px. The last-change line sits in the dialog body above the field, so the on-screen keyboard doesn't hide it.
- Bulk pill text wraps under the amounts on narrow lines (`.bk-lines li` already wraps).

---

## Data model

No new table. Every table touched already has an `account_id` column and the `account_isolation` RLS policy: `campaigns`, `adsets`, `meta_changes` and `alerts` since 020, and `status_events` since 023. The leak test (`dev/qa_leaks.py`) covers the new GET route and the new response fields automatically.

```sql
-- NNN_outside_edits.sql
-- Budget, bid, dates and audience changes made outside the console are recorded like status changes;
-- a budget change confirmed knowingly says which warning was accepted.

ALTER TABLE campaigns
    ADD COLUMN start_time TIMESTAMPTZ,
    ADD COLUMN stop_time TIMESTAMPTZ,            -- Meta's campaign end is `stop_time`
    ADD COLUMN spend_cap_cents BIGINT,           -- campaign spending limit (not the account cap)
    ADD COLUMN setup_seen_at TIMESTAMPTZ;        -- NULL until a full read stored these fields once
ALTER TABLE adsets
    ADD COLUMN bid_strategy TEXT,
    ADD COLUMN bid_amount_cents INTEGER,
    ADD COLUMN start_time TIMESTAMPTZ,
    ADD COLUMN end_time TIMESTAMPTZ,
    ADD COLUMN targeting_fp TEXT,                -- fingerprint of the audience (status_history.targeting_fingerprint)
    ADD COLUMN setup_seen_at TIMESTAMPTZ;

-- The inline CHECK from 023 is named <table>_<column>_check.
ALTER TABLE status_events DROP CONSTRAINT status_events_field_check;
ALTER TABLE status_events ADD CONSTRAINT status_events_field_check CHECK (field IN (
    'created', 'effective_status', 'configured_status', 'review', 'issues', 'learning',
    'daily_budget', 'lifetime_budget', 'spend_cap', 'bid_strategy', 'bid_amount',
    'start_time', 'end_time', 'targeting'));
CREATE INDEX status_events_budget_idx ON status_events (entity_id, at DESC)
    WHERE field IN ('daily_budget', 'lifetime_budget');
CREATE INDEX status_events_campaign_at_idx ON status_events (campaign_id, at);

ALTER TABLE meta_changes ADD COLUMN accepted TEXT[];   -- warnings confirmed knowingly: {'big'}, {'recent'}, {'big','recent'}
CREATE INDEX meta_changes_budget_idx ON meta_changes (entity_id, created_at DESC)
    WHERE action = 'budget' AND ok;
```

**How values are stored in `status_events.old_value` / `new_value`** (TEXT, same as today):

| Kind | Stored as |
|---|---|
| Money | cents as a decimal string (`"2000"`) |
| Times | UTC ISO to the minute (`"2026-12-01T07:59Z"`) |
| Bid strategy | Meta's enum |
| Audience | the fingerprint; `detail` holds `{"before": <targeting_summary>, "after": <targeting_summary>}` so the headline can say what changed |
| Removed value | NULL |

**Seeding.** `setup_seen_at IS NULL` means the console has never stored the setup fields for that row. The first full read after Update stores them and records nothing. This prevents 100+ false "changed" events on the first sync after Update. The first-sighting rules for new entities (`created` / `backfill`) are unchanged.

`alerts` gets a new rule key, `outside_edit`. The `rule` column is free text and the dedupe key is per account, so no schema change is needed.

---

## Backend

### Modules and pure functions

**`money_rules.py`** (pure, unit tested)

```python
RECENT = timedelta(hours=72)   # rule 6: one budget change at least 3 days apart; no setting, never loosened

def last_budget_change(rows):
    """rows: [{at: datetime, field: 'daily_budget'|'lifetime_budget', old: int|None, new: int|None,
               by: str|None, where: 'console'|'outside', proposal_id: int|None}]
    → the latest row whose old != new, or None."""

def recency(last, now, old_cents, new_cents):
    """→ {"recent": bool, "raise": bool, "rollback": bool, "hours": int, "ok_after": datetime} or None when last is None.
    recent = now - last.at < RECENT; raise = new > old; rollback = last.old is not None and new == last.old."""

def budget_change(old_cents, new_cents, cap_cents, last=None, now=None):
    """As today, plus "recent" (bool: recent and a raise and not a rollback), "rollback", "last" (the row)."""

def change_problem(change, accept_big, accept_recent=False):
    """As today, then: a recent raise without accept_recent →
    'The budget last changed {N day(s)|N hours} ago ({from:,.2f} → {to:,.2f} a day). Raising it again this soon
     makes results hard to read: confirm it knowingly.'"""
```

Existing callers that pass no `last` keep today's behaviour, so the current `test_money_rules_logic.py` cases pass unchanged. The ceiling and +20% checks run first, in the same order as today.

**`status_history.py`** (pure parts unit tested)

```python
SETUP = {
    "campaign": ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "start_time", "end_time"),
    "adset": ("daily_budget", "lifetime_budget", "bid_strategy", "bid_amount", "start_time", "end_time", "targeting"),
}
META_KEY = {"end_time": {"campaign": "stop_time", "adset": "end_time"}}   # everything else is the same name
MONEY_FIELDS = ("daily_budget", "lifetime_budget", "spend_cap", "bid_strategy", "bid_amount")

def minute_utc(value) -> str | None            # '2026-11-30T23:59:00-0800' and a datetime → '2026-12-01T07:59Z'
def targeting_fingerprint(t) -> str | None     # sha256[:16] of the normalized audience (below)
def snapshot(level, meta)                      # adds SETUP fields ONLY when meta['_fields'] (the field list that was
                                               # requested) names them; a requested field Meta omitted = None (removed)
def stored_snapshot(level, row)                # adds SETUP fields only when row['setup_seen_at'] is set
def diff(level, before, after, now, created_time)
                                               # compares STATUS fields as today and SETUP fields present on both sides
def explained_by_console(entity_id, ev, changes, now)
                                               # + budget fields: a meta_changes 'budget' row with new_value == ev.new,
                                               #   or a 'recommendation' / 'recommendation_check' row, ok, within CONSOLE_WINDOW
def headline(ev, money=None, tz=None)          # plain words for the new fields (table below)
def transitions(level, entity, events, rules, now, today, money=None, context=None)
                                               # context = {"cap_cents": int, "last_budget": row|None}; new `outside_edit` branch
```

**How `targeting_fingerprint` normalizes the audience:**
- It keeps only these keys: `geo_locations` (countries, regions, cities, zips, custom_locations with lat, long, radius and unit, location_types), `excluded_geo_locations`, `age_min`, `age_max`, `genders`, `locales`, `flexible_spec`, `exclusions`, `custom_audiences`, `excluded_custom_audiences`, `targeting_automation.advantage_audience`, `publisher_platforms`, `facebook_positions`, `instagram_positions`, `device_platforms`.
- Lists of objects are sorted by `id` (or `key`, or their JSON), and plain lists are sorted.
- It drops keys Meta fills in by itself, such as `age_range`, `targeting_relaxation_types` and `brand_safety_content_filter_levels`. That way a reorder or a default Meta adds doesn't count as an audience change.

**Headlines.** `money(c)` is the account-currency formatter already in `entities_api._money`. It moves to the new pure module `backend/words.py` (`words.money(cents, currency)`, plus `day`, `weekday`, `day_time`, `ago`; shared piece S1, owned by D2). `status_history`, `timeline`, W2's report and every later unit use it. If the audit fix already added `account_info.money`, `words.money` wraps it.

| Field | old → new | Headline |
|---|---|---|
| daily_budget | 2000 → 2400 | `Daily budget $20.00 → $24.00 a day` |
| daily_budget | None → 1000 | `Daily budget set: $10.00 a day` |
| daily_budget | 2000 → None (campaign) | `Daily budget removed: the ad sets have their own now` |
| daily_budget | 2000 → None (ad set) | `Daily budget removed: the campaign's budget is shared now` |
| lifetime_budget | 50000 → 70000 | `Lifetime budget $500.00 → $700.00` |
| spend_cap | None → 30000 | `Campaign spending limit set: $300.00` (removed: `Campaign spending limit removed`) |
| bid_strategy | LOWEST_COST_WITHOUT_CAP → COST_CAP | `Bid strategy: Highest volume → Cost per result goal` |
| bid_amount | 4000 → 3500 | `Bid amount $40.00 → $35.00` |
| start_time | → 2026-11-12T17:00Z | `Start moved to Nov 12, 9:00 AM` |
| end_time | None → … | `End date set: Nov 30` / `End date moved: Nov 30 → Dec 15` / `End date removed: runs until turned off` |
| targeting | fp → fp | `Audience changed: {before} → {after}` (from `detail`); when the summaries are equal, `Audience settings changed (see Ads Manager for the detail)` |

`BID_WORDS` maps the bid strategies: `LOWEST_COST_WITHOUT_CAP` "Highest volume", `COST_CAP` "Cost per result goal", `LOWEST_COST_WITH_BID_CAP` "Bid cap", `LOWEST_COST_WITH_MIN_ROAS` "Return on ad spend goal". Anything else shows Title Case.

**The `transitions` branch for `outside_edit`** (rule on by default):
- It looks only at events in `SETUP` whose `source` is `poll` or `webhook` (`console` and `backfill` never alert).
- All outside setup changes of one entity in one sync become one alert:
  - One change: the title is that change, in the form `Budget changed in Ads Manager: $20.00 → $30.00 a day`, `End date set in Ads Manager: Nov 30`, `Audience changed in Ads Manager`, `Bid strategy changed in Ads Manager: Highest volume → Cost per result goal`.
  - Several changes: the title is `{Campaign|Ad set} “{name}” changed in Ads Manager`, with one line per change.
- The lines, in this order:
  1. `{Campaign|Ad set} “{name}”`
  2. Only when the step is a raise of more than +20%: `That's +50%, more than the +20% step the console allows at once.`
  3. Only when it is above the ceiling: `It's above the highest daily budget set in Settings ($25.00).`
  4. Only when it came less than 72 h after the last change: `The budget had changed only 2 days before (Nov 7, $16.00 → $20.00).`
  5. Always: `Made outside this console (Ads Manager, or Claude on the Mac). Nothing to do if that was you.`
- `level` is `warn` if line 2, 3 or 4 applies, otherwise `info`. `kind` is `event`. **Info is raised `resolved: True` (FYI). Warn is raised `resolved: False` (an owner-closed event, 00-PLAN C16):** it stays in Needs action until an admin presses **Done**, or until `alerts.run` housekeeping resolves it 72 h after it was raised (the 3-day window has passed). The dedupe key is `outside_edit:{eid}:{YYYY-MM-DDTHH:MM}`, so it doesn't collide with the existing `changed_outside` switch alert, which stays as it is.
- `href`:
  - built by the new shared helper `links.history_href(level, id, check=None)` (S2, owned by D2; JS twin `historyHref` in `ui.js`), which matches the current code: campaign and ad set pages keep the tab in the query (`UrlState`), the ad page in the hash
  - campaign: `/campaign.html?id={id}&tab=history`
  - ad set: `/adset.html?id={id}&tab=history`
  - ad: `/ad.html?id={id}#tab=history`
- `_href` today sends everything except ads to `/ads.html`. It should be fixed here for both rules: 9.3 asks for entity links.

**Database functions** (in `status_history.py`, beside `timeline`):

```python
def budget_rows(entity_ids, since):
    """Budget history for the 3-day rule: console writes (meta_changes action 'budget', ok) UNION ALL the
    daily/lifetime budget events (any source except backfill: a recommendation shows up as a 'console'
    event from the next sync, with numbers). Returns money_rules.last_budget_change rows; `at` for events is
    LEAST(COALESCE(meta_time, at), at); `by` = users.name for console, detail->>'actor' or 'Ads Manager' outside."""

def note_live_budget(level, row, live_cents, source="poll"):
    """A fresh read found a budget that differs from the stored one: record it as an outside daily_budget event
    (detail {"noticed": "budget check"}) BEFORE the caller overwrites the stored value. Raises alerts like a sync."""

def changes_in(scope, start, end, viewer):
    """Rows for chart marks: status_events + meta_changes + ad_versions in [start, end] (account-tz days) for
    scope = {"entity_ids": [...], "campaign_ids": [...]} limited to visible_campaign_ids(viewer).
    Excludes backfill, failed console writes and Claude proposals that weren't applied."""
```

**`sync.py`:**
- `CAMPAIGN_FIELDS` adds `spend_cap,start_time,stop_time`. `ADSET_FIELDS` adds `bid_strategy,bid_amount,start_time,end_time`. The `_PLAIN` fallbacks stay as they are.
- `listing()` stamps each row with `_fields` (the field string that succeeded). `insights._fetch_many` does the same for webhook refetches.
- Both upserts write the new columns and `setup_seen_at = CASE WHEN %s THEN now() ELSE <table>.setup_seen_at END`. The flag is true only when the full field set was used. The plain fallback leaves the new columns untouched: `COALESCE(EXCLUDED.x, x)` for them when the flag is false.
- `PREV_COLS` for campaign and adset add the new columns plus `daily_budget_cents`, `lifetime_budget_cents`, `targeting_summary` and `setup_seen_at`.
- `track()` puts `{"before": prev.targeting_summary, "after": summarize_targeting(meta.targeting)}` in the targeting event's `detail`.
- `record()` widens its `meta_changes` query to `action IN ('status', 'budget', 'recommendation', 'recommendation_check')`.
- `alert_on()` builds `context`: the ceiling via `money_rules.ceiling(settings_store.get(...))`, and the last budget row before this event via `budget_rows`.

**`timeline.py`** (pure):
- `merge(status_events, changes, proposals, money, versions=())`: every item gains `cat` (`money` | `switch` | `edit` | `meta`), `level`, `entity_id` and `entity_name`. `versions` (ad_versions rows) become `{"kind": "version", "title": "Version {n} started" + (f": {label}" if label), "cat": "edit"}`.
- Outside setup events get `by = detail.actor or "Ads Manager"` instead of "Meta".
- A change with `accepted` gets `sub = "Confirmed knowingly: more than +20%"`, `"…: under 3 days since the last change"`, or both joined with " and ".
- A change made from a Claude suggestion (`proposal_id`) gets the suffix ` (Claude's suggestion)` on its title.

**`marks.py`** (new, pure, unit tested; the name carries no ad-blocker words)

```python
CAT_ORDER = ("money", "switch", "edit", "meta")
PER_DAY = 6

def category(item) -> str                      # from field / action / kind
def chart_worthy(items) -> list                # drops cascade noise (below)
def by_day(items, tz, start, end, for_client=False) -> list[dict]
    # → [{"day": "2026-11-09", "cats": ["money", "meta"], "items": [{"cat", "title", "by", "level", "entity_id",
    #     "entity_name", "at"}], "more": 0}], days inside [start, end] only, items money-first then by time, at most PER_DAY
def summary_words(marks, day_words) -> str     # "2 changes in this period: budget raised Nov 9, ad “N6” approved Nov 11."
```

**`chart_worthy` drops:**
- `effective_status` events whose new value is `CAMPAIGN_PAUSED` / `ADSET_PAUSED`.
- `effective_status` events whose old value is one of those and whose new value is `ACTIVE`.
- An `effective_status` event within 15 minutes of a `configured_status` event with the same new value on the same entity. The switch already says it, and says who.
- Proposal items. Applied suggestions are already there as their `meta_changes` row.

**When `for_client=True`:**
- `by` becomes `Team` for console users, stays `Meta` or `Ads Manager` otherwise, and is never a person's name.
- The " (Claude's suggestion)" suffix is removed.

### Routes

| Route | Change | Who |
|---|---|---|
| `GET /api/ads/<level>/<id>/budget/last` (new; level `campaign` or `adset`) | `{"daily_budget_cents", "last": {at, field, from, to, by, where} or null, "recent": bool, "ok_after": iso or null}` from `budget_rows` (90 days) + `money_rules.recency` against the stored budget. Database only, no Meta call. | owner admin and account admin: any campaign in the account; teammate: `can_touch`, else 404; client: 403 "Read-only access" |
| `POST /api/ads/<level>/<id>/budget` | Reads `accept_recent`. Calls `note_live_budget` before the existing stored-row update when the live amount differs (today's lines 612-614). Builds the change with `last` + `now`. A refused recent raise returns 409 `{error, field: "budget", code: "recent_change", last}`. Stores `accepted` (`big`, `recent`) on the `meta_changes` row; `ads_api.record` gains an `accepted=None` kwarg. | unchanged (anyone who may touch the campaign, never client) |
| `POST /api/ads/bulk/preview` | `bulk.budget_lines(rows, mode, value, live, cap, lasts=None, now=None)`. Each line gains `recent` (bool) and `last_words` (e.g. `"changed 1 day ago"`), and totals gain `recent`. Rollbacks and decreases never set `recent`. The signed plan carries `totals.recent`. | unchanged |
| `POST /api/ads/bulk/apply` | `totals.recent` and no `accept_recent` → 409 "Some budgets changed less than 3 days ago: confirm them knowingly." **Recency is recomputed per line from `budget_rows` at apply time**, so a line that became recent after the preview is refused without `accept_recent`, even if the signed plan said otherwise. Each line records `accepted`. | unchanged |
| `GET /api/proposals/<id>/check` | `proposal_plan` budget branch passes `last` (`budget_rows` for that entity) into `budget_change`, so the plan carries `recent`, `rollback` and `last`. | unchanged |
| `POST /api/proposals/<id>/approve` | The budget branch re-reads `budget_rows` at approve time (never the plan from `/check`), passes `accept_recent` to `change_problem` and records `accepted`. | unchanged (admin, or teammate on own campaigns, as today) |
| `GET /api/advice`, `POST /api/advice/apply` | The view adds `budget.recent` / `budget.last_words` for `SCALE_GOOD_CAMPAIGN`. Apply checks `accept_recent` the same way (409). | admin, as today |
| `GET /api/campaigns/<id>`, `GET /api/adsets/<id>` | Add `marks` and `marks_summary` for the page range. Scope: campaign = the campaign, its ad sets and ads; ad set = the ad set, its ads and its campaign (money and switch only, because a shared campaign budget drives the ad set). | as today; client gets `for_client` |
| `GET /api/ads/ad/<id>` | Adds `marks` and `marks_summary` for its 30-day series. Scope: the ad (all), its ad set and campaign (money and switch). | as today |
| `GET /api/performance` | Adds `marks` and `marks_summary`. Scope: the account, or the chosen campaign. Ad-level items only for `created`, approval or rejection, and versions. | as today; teammate limited by `visible_campaign_ids` |
| `GET /api/compare` | Adds `marks`: the compared ads (all), plus their ad sets and campaigns (money and switch). Titles carry the ad name (`N3: Version 2 started`). | as today |
| `GET /api/timeline/<level>/<id>?marks=14` | Optional `marks` for the peek drawer's 14-day spark charts. | as today |
| `GET /api/agent/snapshot` (bridge) | Adds `budget_changes`: `[{level, id, name, daily_budget_cents, last: {at, from, to, where}, days_since, ok_after}]` for every campaign and ad set with a budget, plus `recent_changes`: the account-wide `marks` for the snapshot range (names kept: Claude is admin-side). | agent key |
| `GET /api/reports…` (`reports_api.build`) | **Owned by W2 (00-PLAN C14).** D2 provides only `status_history.OUTSIDE_FIELDS = ("configured_status",) + every SETUP field` and `headline()`. W2's `report_logic.what_we_did(console, outside)` builds the lines, with items `{day, where: "console"\|"outside", level, name, text}`; the key `by` stays reserved for a person's name. The text is `{Level} “{name}”: {headline with a lowercased first letter}` + ` (in Ads Manager)` for outside rows. | as today (clients and share links included: these are facts about the ads, not Claude's ideas) |

`desk_view.review_item`, for the budget kind:
- `needs_tick |= plan.recent`
- `body["accept_recent"] = bool(plan.recent)`
- When recent, `note` is: `Budget last changed {Mon D} ({from} → {to}, {in Ads Manager|by {by}}), {N} day(s) ago.` The existing "Claude saw …" note takes priority, and both are joined when both apply.

The rule applies to the budget being changed: the campaign for a shared budget, or the ad set for its own budget. Edge Bourne runs one shared campaign budget, so this is "per campaign" in practice. See the edge cases for the ad set with its own budget.

---

## Frontend

All copy goes through `format.js` once 9.2 lands. The new shared words go there now:
- `CHANGE_CATS = { money: "Budget", switch: "On/off", edit: "Edits", meta: "Meta" }`
- `agoWords(iso)` gives "today", "1 day ago", "2 days ago" or "5 hours ago", and is reused by the bulk pill and the dialog.

The new class names (`chg-*`) pass the ad-blocker guard.

**`controls.js` `editBudget`:**
- Before opening the dialog, it calls `GET /api/ads/{level}/{id}/budget/last`. On a network error it still opens without the line: the server check is the real gate.
- Dialog body, after today's sentence: `<p class="muted small">Last change: <b>Nov 9</b>, $20.00 → $30.00 a day, in Ads Manager, 1 day ago.</p>`. For a console change: `…, by you` or `…, by {name}`. With no history: nothing.
- `hint(v)`:
  - Today's percent line comes first.
  - Then, for a raise inside the window: `<b>Less than 3 days since the last change.</b> Meta is still adjusting to it; another raise now makes results hard to read. The usual rule: wait until Nov 12, 3:40 PM.`
  - For a rollback: `Back to $20.00, the budget before the last change.`
- The confirm label is dynamic: `Raise anyway` when the typed amount is more than +20% or a recent raise, `Change budget` otherwise. `confirmDialog` gains an optional `confirmLabel(value)` callback, re-run on input; `#cd-ok` keeps its id.
- POST body: `{ daily_budget_cents, from_cents, accept_big, accept_recent }`. A 409 with `code: "recent_change"` shows its message as a toast. It can only happen when the dialog had no history (offline read), and the next open shows it.

**`manager.js` `bulkRun`:**
- Budget lines with `l.recent` get `<span class="pill warn">{l.last_words}</span>`.
- When `t.recent`, the summary gets `<p><b>Some of these changed less than 3 days ago.</b> Raising them again this soon makes results hard to read.</p>`, `confirm = "Apply anyway"`, and the body adds `accept_recent: true`.

**`decide.js`:** nothing new. It already renders `note`, `needs_tick` and `body`, which the server now fills.

**`home.js` advice:**
- When `r.budget.recent`, the step line gets ` · last change {last_words}`.
- The apply confirmation uses `Raise anyway` and sends `accept_recent`.

**`charts.js`:**
- `columnChart({..., marks = []})` and `lineChart({..., marks = []})` take `marks` as returned by the API. They match on `day` against the series days.
- With marks, the bottom margin `B` grows by 10. For each marked day:
  - `<rect class="chg-mark chg-{cat}" x=… y="{T+plotH+3}" width="4" height="6" rx="1">`, coloured by its first (highest-priority) cat.
  - Days with `money` also get `<line class="chg-guide">` through the plot (dashed, 1 px, `--mark-money` at 45% opacity).
- Tooltip: after today's value line, `<ul class="tip-chg">` lists each item as `<li><i class="chg-dot chg-{cat}"></i>{title}<small>{entity_name if not this entity} · {by}</small></li>`, followed by `and {more} more` when `more`.
- Taps: a `pointerup` handler on `.hit` for `pointerType !== "mouse"` toggles the same tooltip. A document `pointerdown` outside closes it. The tooltip's left edge is clamped into the chart box.
- Accessibility: the `aria-label` becomes `{title}. {marks_summary}` when there are marks.
- Visibility: `body.chg-off .chg-mark, body.chg-off .chg-guide { display: none }`. The tooltip still lists the changes, because that is information, not decoration.

**New shared fragment in `charts.js`, `marksPanel(el, marks, summary)`:**
- Rendered under the charts row on Campaign, Ad set, Ad (Overview), Results and Compare (`#chg-panel`).
- Markup: `<details class="chg-list"><summary>{N} change(s) in this period</summary><div class="chg-legend">■ Budget ■ On/off ■ Edits ■ Meta</div>{switchHtml(on, 'data-chg-toggle', 'Show on charts')} <span>Show on charts</span><ul>…rows…</ul></details>`.
- Row: `<li><span class="r-date">{Nov 9}</span> <i class="chg-dot chg-{cat}"></i> {title}{ · Campaign “{name}”}{ · by {by}} </li>`. The entity part is a link (9.3 `entityLink`) to its History through `historyHref(level, id)`.
- Empty state: `<p class="muted small flush">No changes in this period.</p>`, with no switch.
- The switch state lives in localStorage `eb-chg-marks` (`"0"`/`"1"`, default on). Reads and writes are wrapped in try/catch, and the default works without storage.
- Phones: `summary` and rows `min-height: 44px`; the switch keeps its 44 px target.

**Peek drawer (`manager.js`):** the existing `/api/timeline` call adds `?marks=14`, and the two spark charts pass `marks`. There is no panel there: the drawer's own timeline list already shows the changes.

**Tokens (`tokens.css`, light and dark):**
- New: `--mark-money`, `--mark-switch`, `--mark-edit`, `--mark-meta`. Run them through the dataviz palette checker against `--chart-spend` and `--chart-leads`, in both themes.
- Violet stays reserved for Claude: a Claude-suggested change is a money mark with "(Claude's suggestion)" in its text, not a violet mark.
- Starting proposal: money = amber (`--warn` family), switch = graphite (`--text-2`), edit = blue, meta = red (or green for "approved" via `.chg-meta.ok`). If the checker fails, adjust.

**History tabs:** no change. New events show up through `headline` and `by`, and console changes confirmed knowingly show their `sub`.

**Report:** no D2 change in `report.js`. W2 (built right after D2) renders the server's `text` from `what_we_did` (00-PLAN C14).

**Settings → Alerts:**
- New row, `outside_edit`: **Changed in Ads Manager: budget, bid, dates or audience**, with help text "A note when someone changes these in Ads Manager. It's marked as needing action when the change breaks a money rule."
- The existing `changed_outside` row is renamed **Switched on or off in Ads Manager**.

---

## Interaction with other features

| Feature | How D2 fits |
|---|---|
| 9.2 one vocabulary (`format.js`) | `CHANGE_CATS` and `agoWords` live there, and server headlines use the same state words (Delivering / Off / In review / Rejected). A unit test pins `headline` output for every new field so a vocabulary change is deliberate. |
| 9.2 chart summaries and accessibility | `marks_summary` is the chart summary text for marks. Tooltip-on-tap fixes charts on touch for everyone. |
| 9.3 `entityLink()` and shared range | The changes list uses `entityLink`. Marks follow whatever range the page shows (`ranges.py`), including `mtd` / `lastmonth`. |
| 9.4 Inbox "Needs action / FYI" | `outside_edit` at `warn` is Needs action, at `info` it is FYI. Add `outside_edit` to `inbox.CATEGORY` as `money`, so clients (who see only status alerts and leads on Today) don't get money notices. |
| 9.4 Today queue | Warn-level outside edits enter the money part of the queue, ranked below rejections. |
| 9.1 currency | Every amount goes through the account currency (`words.money` / `format.js money()`), never a hard-coded `$`. |
| "Restate older days … label where each number comes from" (D1) | D2 creates the shared row `<div class="fig-foot">` under the charts (S6): the marks summary on the right; D1 later puts its source note on the left. Phones stack them, source first. No data conflict. |
| "'Did it work?' check on applied changes" | It should use `status_history.budget_rows` / `money_rules.last_budget_change` so outside raises count as changes too. Marks give that check its picture. |
| "Acknowledge or snooze alerts" (W1) | Outside-edit alerts are events, so they can't be snoozed. Info items are resolved at once (FYI). Warn items are owner-closed: **Done** (W1's `DONE_OK` includes `outside_edit`) or after 72 h. |
| "Diagnose with Claude from any alert" (W1) | `diagnose.PLAYBOOKS["outside_edit"] = ("meta-ads", "what changed outside the console", "activity log: who changed what, and whether it breaks the money rules")`. |
| "Fix the client report funnel / review before send" | "What we did" now has outside lines. The review step shows them like the rest. |
| 5.5 update ads in place (`ad_versions`) | Version starts are `edit` marks, read from `ad_versions.started_on`. |
| Experiments / Meta A/B tests | Marks show budget changes during a running test on the Results and Compare charts. A test-specific warning is out of scope (a later idea: say "a test is running on this campaign" in the budget dialog). |
| Desk / bridge | `budget_changes` and `recent_changes` in the snapshot. Add one paragraph to `ads/bridge/skill/SKILL.md`: before proposing a budget change, read `budget_changes`. If the same budget changed less than 3 days ago, say so and propose holding unless 7-day CPA is far over target. Claude can still propose, and the Accept sheet still won't pre-tick it. |
| Bulk, Accept sheet, Meta's advice, budget dialog | All four check `accept_recent` server-side. Nothing that sets a budget skips `money_rules`. |
| `changed_outside` (switch alert, 8.2) | Unchanged. Its `_href` fix (entity History) applies to both rules. |

---

## Edge cases

- **The first sync after Update** seeds the setup columns with no events or alerts (`setup_seen_at`). The existing `daily_budget_cents` / `bid_strategy` columns are also gated, so a campaign whose stored budget was stale doesn't raise an alert on Update day.
- **Meta refuses the new fields** and the plain fallback is used: `_fields` lacks them, so they are not compared and `setup_seen_at` is not set. Nothing false is recorded.
- **A field Meta omits when empty** (`end_time`, `spend_cap`, `bid_amount`) counts as "removed" only when it was requested, so removing an end date in Ads Manager is still noticed.
- **The console's own budget writes** update the stored row at once (`apply_budget`), so a sync sees no difference. Meta's advice apply doesn't update the row: the next sync records the change as `console` via `explained_by_console` (recommendation within 10 min), with numbers, so the 3-day rule sees it.
- **A budget changed outside and then within minutes in the console:** `set_budget` reads it live. `note_live_budget` records the outside change first (as of now), then the dialog's `from_cents` mismatch returns today's 409 "The budget changed on Meta since you looked". The next open shows "Last change: today, in Ads Manager" and the raise needs `accept_recent`.
- **Detection delay:** Meta's ad-account webhooks cover status, not budgets, so outside budget edits arrive with the hourly poll, a Refresh, or the next budget dialog's live read. `at` is clamped to Meta's `updated_time` when that is earlier, so the 72 h counts from close to the real change.
- **Rollback:** a change to exactly the budget before the last change is never "recent" (rule 6: rollback = exact previous budget). A decrease is never "recent" either. Both show the last-change line.
- **Boundary:** exactly 72 h after the last change is not recent (`<`, not `<=`).
- **Shared budget switched to ad-set budgets in Ads Manager** (the campaign budget goes to None and the ad sets get budgets): the events are "Daily budget removed: the ad sets have their own now", then "Daily budget set: $10.00 a day" per ad set. The ad sets have no earlier change of their own, so a raise on one isn't "recent". The campaign's removal does show on that ad set's chart marks (money, from the campaign).
- **Lifetime budgets:** a lifetime change counts as the last budget change of that entity. The console still only edits daily budgets.
- **Audience noise:** Meta adds defaults or reorders lists, which the fingerprint whitelist and sorting absorb. A fingerprint change with equal summaries gives "Audience settings changed (see Ads Manager for the detail)", at info level.
- **Times** come back in the account's offset (`-0800`) and are stored as UTC timestamps, so `minute_utc` compares them reliably. Display uses the account time zone (`account_info.tz()`).
- **Several outside changes to one entity in one sync** make one Inbox item with one line each. Ten ad sets edited at once make ten items (grouping is out of scope).
- **Deleted or archived entities** keep their marks in the ranges where they happened.
- **Busy days:** `PER_DAY = 6` items, then "and N more", money first.
- **Charts with no series days** (an empty range) draw no marks, and the panel says "No changes in this period."
- **Teammates** see marks and outside-edit alerts only for their campaigns (`visible_campaign_ids`). An account-level mark (Meta's advice applied at account level) has no campaign and is shown to admins only.
- **Clients** see marks without people's names or "Claude's suggestion", and no budget routes (403). Report lines are the same as today plus "(in Ads Manager)".
- **Multi-account:** every query runs under `app.account_id`, so RLS keeps one account's marks and history out of another's.
- **Bulk:** a budget changed between preview and apply is already skipped ("Changed on Meta since the preview"). `recent` is evaluated at preview time and signed into the plan.
- **No storage** (private window, blocked site data): marks default on, and the switch just doesn't persist.

---

## Tests

### Unit (no database)

**`test_money_rules_logic.py`** (`t(d, h)` = `datetime(2026, 11, d, h, tzinfo=UTC)`):

| Case | Input | Expected |
|---|---|---|
| latest real change wins | rows `[{at:t(7,10), old:1600,new:2000,…}, {at:t(9,15), old:2000,new:2400, where:"outside"}, {at:t(10,9), old:2400,new:2400}]` | the `t(9,15)` row |
| nothing to go on | `last_budget_change([])` | `None` |
| raise inside 72 h | `recency(last(t(9,15), 2000→2400), now=t(11,15), 2400, 2600)` | `{"recent": True, "raise": True, "rollback": False, "hours": 48, "ok_after": t(12,15)}` |
| boundary | same, `now=t(12,15)` | `recent: False` |
| rollback | same last, now `t(11,15)`, new `2000` | `rollback: True`; `budget_change(...)["recent"] is False` |
| decrease | new `2200` | `raise: False`; `budget_change(...)["recent"] is False` |
| refused without the yes | `change_problem(budget_change(2400, 2600, 10000, last, t(11,15)), accept_big=False)` | `"The budget last changed 2 days ago (20.00 → 24.00 a day). Raising it again this soon makes results hard to read: confirm it knowingly."` |
| with the yes | same, `accept_recent=True` | `None` |
| big and recent | `budget_change(2400, 3200, 10000, last, t(11,15))`, `accept_big=True`, `accept_recent=False` | the recent message; with both → `None` |
| ceiling still first | `budget_change(2400, 20000, 10000, last, …)`, both accepted | the ceiling message |
| backward compatible | `budget_change(2000, 2400, 10000)` | has `recent: False`; existing assertions unchanged |
| hours wording | last 5 h ago | message says `5 hours ago` |

**`test_status_history_logic.py`:**

| Case | Expected |
|---|---|
| `snapshot("campaign", {..., "daily_budget": "2000", "stop_time": "2026-11-30T23:59:00-0800", "_fields": sync.CAMPAIGN_FIELDS})` | includes `daily_budget: 2000`, `end_time: "2026-12-01T07:59Z"` |
| the same without `_fields` (fallback) | no SETUP keys |
| `stored_snapshot("campaign", row with setup_seen_at=None)` vs the snapshot above | `diff == []` (seeding) |
| stored `daily_budget_cents=2000, setup_seen_at=set`, Meta `"3000"` | `[{"field": "daily_budget", "old": 2000, "new": 3000, "backfill": False}]` |
| Meta `"0"`, stored `None` | `[]` |
| stored `end_time=datetime(2026,12,1,7,59,tz=UTC)`, Meta `"2026-11-30T23:59:00-0800"` | `[]` |
| requested `end_time` missing from Meta's row, stored set | one event `end_time` old `"2026-12-01T07:59Z"` new `None` |
| `targeting_fingerprint({"age_min": 25, "geo_locations": {"countries": ["US"]}})` vs keys reordered + `"targeting_relaxation_types": {"lookalike": 1}` + `"age_range": [25, 65]` | equal |
| same with `age_min: 30` | different |
| `flexible_spec` interests `[{id:"2"},{id:"1"}]` vs `[{id:"1"},{id:"2"}]` | equal |
| `explained_by_console("C", {"field":"daily_budget","new":"2600"}, [{"id":7,"entity_id":"C","action":"budget","new_value":"2600","ok":True,"created_at":now-3min}], now)` | `7` |
| same with `new_value "2500"` | `None` |
| same with `action "recommendation"`, any value, 4 min | that id |
| same, 11 min old | `None` |
| `headline({"field":"daily_budget","old":"2000","new":"2400"}, money=usd)` | `"Daily budget $20.00 → $24.00 a day"` |
| `headline({"field":"bid_strategy","old":"LOWEST_COST_WITHOUT_CAP","new":"COST_CAP"})` | `"Bid strategy: Highest volume → Cost per result goal"` |
| `headline({"field":"end_time","old":"2026-12-01T07:59Z","new":None}, tz=LA)` | `"End date removed: runs until turned off"` |
| `headline({"field":"end_time","old":None,"new":"2026-12-01T07:59Z"}, tz=LA)` | `"End date set: Nov 30"` |
| `headline` targeting with detail before "Ages 25–65+ · …" after "Ages 30–65+ · …" | `"Audience changed: Ages 25–65+ · … → Ages 30–65+ · …"` |
| `transitions` outside `daily_budget` 2000→3000, source poll, rules on, context cap 10000, last = 2 days earlier 1600→2000 | one alert: rule `outside_edit`, level `warn`, title `Budget changed in Ads Manager: $20.00 → $30.00 a day`, lines contain `+50%` and `only 2 days before` |
| 2000→2200, no last | level `info`, no rule lines |
| a decrease above the ceiling (ceiling lowered later) | `warn` with the ceiling line |
| two outside events in one call (budget + end date) | one alert titled `Campaign “X” changed in Ads Manager`, 2 change lines |
| source `console` or `backfill` | `[]` |
| rule `outside_edit` off | `[]` |
| the existing switch alert still fires for `configured_status` | unchanged assertion |

**`test_timeline_logic.py`:**
- An outside `daily_budget` event gives `by == "Ads Manager"` and `cat == "money"`, or `by == "Eugene R."` when `detail.actor` is set.
- A change with `accepted=["recent"]` gives `sub == "Confirmed knowingly: under 3 days since the last change"`.
- A version row gives `kind "version"`, `cat "edit"` and `title "Version 2 started: shorter hook"`.
- A change with `proposal_id` gives a title ending in ` (Claude's suggestion)`.

**`test_marks_logic.py` (new):**
- **Time zone:** an item at `2026-11-10T06:30Z` with tz America/Los_Angeles and range Nov 1–14 lands on day `"2026-11-09"`.
- **Range:** an item on Oct 31 is dropped.
- **Order:** a day with a meta item at 09:00 and a money item at 15:00 gives `cats == ["money", "meta"]`, with the money item first.
- **Cap:** 8 items in one day give 6 items and `more == 2`.
- **`chart_worthy`:**
  - `[configured PAUSED at 10:00, effective PAUSED at 10:04]` on the same entity keeps only the configured one.
  - An effective `CAMPAIGN_PAUSED` on an ad is dropped.
  - Effective `ADSET_PAUSED → ACTIVE` is dropped.
  - Proposal items are dropped.
- **`for_client`:** a console change by "Eugene" gives `by == "Team"`, and " (Claude's suggestion)" is removed.
- **`summary_words`** with a budget raise on Nov 9 and an approval of “N6” on Nov 11 gives `"2 changes in this period: budget raised Nov 9, ad “N6” approved Nov 11."`; with none, `"No changes in this period."`.

**`test_bulk_logic.py`** (`budget_lines` with `lasts={"C": last(t(9,15), 2000→2400)}`, `now=t(10,15)`):
- `+10%` gives the line `recent: True`, `last_words: "changed 1 day ago"`, and `totals.recent: True`.
- `set 2000` (rollback) gives `recent: False`.
- `-10%` gives `recent: False`.
- With no `lasts`, everything is unchanged.

**`test_desk_view_logic.py`:**
- `review_item` for a budget plan with `recent: True` (and `big: False`) gives `needs_tick True`, `tick False`, `body.accept_recent True`, and a note that starts `"Budget last changed Nov 9 ($20.00 → $24.00, in Ads Manager)"`.
- With both that and "Claude saw $18.00", both notes are present.

### QA (`qa/flows.cjs`)

**New helpers:**
- `outside(id, params)`: runs `docker exec … requests.get('http://fake-meta:5001/fake/_outside?id=…&…')`.
- `ageBudget(days=4)`: runs `docker exec … db.execute("UPDATE meta_changes SET created_at = created_at - interval '%s days' WHERE action IN ('budget','recommendation'); UPDATE status_events SET at = at - …, meta_time = meta_time - … WHERE field IN ('daily_budget','lifetime_budget')")`.

**Existing checks this changes.** Each one must call `ageBudget()` first, or it starts failing because an earlier QA step changed the same budget less than 3 days before:
- flow 2 budget dialog (≈ line 62)
- advice budget apply (≈ 1204–1221)
- the bulk +30% check (≈ 1753)
- proposal budget approval (≈ 1593–1600)
- the Accept-sheet "Claude saw" check (≈ 598): that note now may also say "Budget last changed"; adjust the regex to keep matching `Claude saw \$20\.00 a day`.

**New checks**, in a new block after 8.3 (all against fake Meta):
1. `outside(C1, daily_budget=3000)` + `pull()` → `/api/campaigns/C1` timeline has `Daily budget $20.00 → $30.00 a day`, by `Ads Manager`. The Inbox (`kind=money`) has `Budget changed in Ads Manager: $20.00 → $30.00 a day`, level warn, a line with `+50%`. A repeat `pull()` records nothing new.
2. A console budget change via the dialog followed by `pull()` raises no `outside_edit` alert (Inbox count unchanged).
3. API: `POST /api/ads/campaign/C1/budget {daily_budget_cents: 3200, from_cents: 3000}` → 409 with `code === "recent_change"` and `last.to === 3000`. With `accept_recent: true` → 200, and `meta_changes.accepted` contains `recent`.
4. A rollback to the exact previous amount → 200 without `accept_recent`. A decrease → 200 without it.
5. Dialog: clicking the budget chip shows `Last change:` with `today` in `.confirm-body`. Typing a raise makes `#cd-ok` read `Raise anyway`. Typing the previous amount makes it read `Change budget` and the hint reads `Back to`.
6. Bulk: the preview line shows a `.pill` with `changed today`, and `#cd-ok` reads `Apply anyway`. Apply without `accept_recent` → 409.
7. Accept sheet: a seeded budget proposal on C1 is not ticked and its `.sheet-why` says `Budget last changed`.
8. Schedule: `outside(ADSET, end_time=<+20 days>)` + pull → timeline `End date set: …` and an Inbox item. Then `outside(ADSET, clear=end_time)` + pull → `End date removed: runs until turned off`.
9. Audience: `outside(ADSET, targeting_age_min=30)` + pull → `Audience changed: Ages 25` … `→ Ages 30`. `outside(ADSET, targeting_noise=1)` (adds `targeting_relaxation_types`) + pull → no new event.
10. Seeding: after `UPDATE campaigns SET setup_seen_at = NULL` + pull, no new events; the next pull after a real change records it.
11. Report: `/api/reports?kind=month` `changes` has an item with `where === "outside"`, and the rendered report text contains `(in Ads Manager)`.
12. Marks on pages: `/api/campaigns/C1?range=14` has a `marks` entry for today with cat `money`. `campaign.html?id=C1` renders `#c-spend svg .chg-mark` and `.chg-guide`, and `.chg-list summary` matches `/\d+ changes? in this period/`. Hovering the last `.hit` shows `.tip .tip-chg` with `Budget`.
13. Toggle: clicking `[data-chg-toggle]` hides `.chg-mark`, and after a reload they stay hidden. Toggling back shows them again.
14. The same `.chg-mark` presence on `ad.html?id=N1`, `performance.html` and `compare.html?ids=…`.
15. Client login: `/api/campaigns/C1` `marks[*].items[*].by` ⊂ {`Team`, `Meta`, `Ads Manager`}, and `GET /api/ads/campaign/C1/budget/last` → 403.
16. Teammate on another campaign: `GET /api/ads/campaign/C1/budget/last` → 404.
17. Phone 390 px: a tap (`page.touchscreen.tap`) on a marked day's column shows `.tip-chg`. `.chg-list summary` height ≥ 44. No horizontal overflow.
18. Ad-blocker guard and console-error guard pass. They are existing checks and cover the new `chg-*` classes automatically.

### Fake Meta (`dev/fake_meta.py`)

- `CAMPAIGN` gains `"spend_cap"` (absent), `"start_time": "<TODAY-10>T09:00:00-0800"`, and no `stop_time`. `ADSET` gains `"bid_strategy": "LOWEST_COST_WITHOUT_CAP"` and `"start_time"`.
- Check that the object GET and the account listings return these keys. The fake returns whole dicts, so the new keys just appear. A requested field that is unset is omitted, as on real Meta.
- The object POST accepts `lifetime_budget`, `spend_cap`, `bid_strategy`, `bid_amount`, `start_time`, `end_time`, `stop_time` and `targeting` (JSON), next to today's `status`/`daily_budget`/`name`. Only `/fake/_outside` and QA use them: the console never sends them.
- New route `GET /fake/_outside?id=<id>&daily_budget=&lifetime_budget=&spend_cap=&bid_strategy=&bid_amount=&end_time=&start_time=&targeting_age_min=&targeting_noise=1&clear=<field,…>`:
  - Mutates the object as Ads Manager would.
  - Bumps `updated_time`.
  - Appends an entry to a new `ACTIVITIES` list (`event_type` `update_campaign_budget` / `update_ad_set_budget` / `update_ad_set_run_status` / `update_ad_set_target_spec`, `actor_name` "Eugene", `extra_data` old/new).
- `GET act_…/activities` returns `ACTIVITIES` plus today's two static rows, so Settings → Activity and the optional "who" step can be tested.

---

## Rollout

Ship in this order. Each step is one commit, and each step ships on its own:

1. **D2.1 Record outside edits:**
   - migration `NNN_outside_edits.sql`
   - `sync.py` fields, `_fields` and upserts
   - `status_history` pure + `budget_rows` / `note_live_budget`
   - `timeline` `by`/`cat`, headlines, the `outside_edit` alert, `inbox.CATEGORY`, `_href` fix
   - Settings → Alerts row
   - fake `_outside`
   - QA 1, 2, 8–10
2. **D2.2 The 3-day rule:**
   - `money_rules`
   - `GET …/budget/last`
   - set_budget, bulk, proposals, advice
   - `controls.js` dialog, `confirmLabel`, `manager.js` bulk, `home.js` advice, `desk_view`
   - `meta_changes.accepted`
   - QA 3–7, plus `ageBudget()` in the existing budget flows
3. **D2.3 Desk (report lines move to W2, C14):**
   - `status_history.OUTSIDE_FIELDS` exported for W2
   - snapshot `budget_changes` / `recent_changes`
   - SKILL.md paragraph and `ads/bridge/install.sh`
   - QA 11
4. **D2.4 Chart marks:**
   - `marks.py`
   - `status_history.changes_in`
   - `marks` on the 6 routes
   - `charts.js` marks, tap tooltip, `marksPanel`
   - tokens validated with the dataviz checker
   - page wiring (entity, creative, performance, compare, manager peek)
   - QA 12–17, screenshots light/dark, desktop and 390 px
5. **D2.5 (optional) Who made it:**
   - The slow pass (hourly, under the existing advisory lock) reads `act_…/activities` for the last 2 days when an outside setup event from the last 2 hours has no `detail.actor`. This is read-only and uses the cache already used by `/api/insights/activity`.
   - It matches on object name + type + new value and fills `detail.actor`, so History says "by Eugene R. (outside the console)".
   - Skip this step if Meta's live activity data proves too loose to match.

**Settings switches:**
- **Settings → Alerts → `outside_edit`** (on by default). It turns off only the Inbox note, never the recording or the 3-day rule.
- **Show on charts:** a per-viewer switch in the changes panel (localStorage).
- There is no switch for the 3-day rule or its window.

**What Eugene does after Update:**
- Nothing on Meta. No new permissions or webhooks are needed, because the new fields are read with the System User token's existing `ads_read`.
- The first hourly sync (or a Refresh) after Update stores the current budgets, dates and audiences quietly. From then on, outside changes are recorded.
- After step 3, run `ads/bridge/install.sh` on the Mac and restart the LaunchAgent (§4.6), so Claude reads the last budget changes before it suggests one. Check for a running Desk task before kickstarting (memory: bridge-restart-check).
- Look once at a campaign page on his phone (tap a marked day) and with his ad blocker on.

**Still unverified on real Meta after shipping:**
- Real `stop_time` / `end_time` formats and offsets.
- Whether Meta omits or nulls a removed end date.
- Which targeting keys Meta fills in by itself on this account (watch for a false "Audience settings changed" in the first week).
- Whether advice auto-applies show up as recommendations.
- The `activities` actor names for MCP-made changes (D2.5).

---

## Effort

| Step | Size |
|---|---|
| D2.1 Record outside edits (migration, sync, pure diff and headlines, alert, fake, QA) | ~1 day |
| D2.2 3-day rule across five budget paths + dialog/bulk/sheet/advice UI + QA ripple | ~1 day |
| D2.3 Report and Desk snapshot + skill line | ~0.5 day |
| D2.4 Chart marks (pure module, 6 routes, charts.js, panel, tokens, QA, screenshots) | ~1 day |
| D2.5 Optional actor names from Meta's activity log | ~0.5 day |
| **Total** | **M (≈ 3.5–4 days)**; 1+2 are the money-safety part and can ship before the marks |

Main risks:
- QA ripple: every existing budget flow needs `ageBudget()`.
- False audience changes from Meta's own defaults: the whitelist fingerprint and seeding guard against them, and a first-week review is needed.
- `charts.js` is shared by five pages: one change covers all of them, and the screenshot pass checks them all.
