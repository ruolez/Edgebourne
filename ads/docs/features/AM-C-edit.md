# AM-C · Change campaigns and ad sets after they're made: settings, copies, archive and delete

Unit key: `AM-C-edit` · Asked by Eugene 2026-11-13 · Meta: Graph API writes through the console's own key, the same door as budget and on/off (`ads_api`), each **read fresh before**, recorded in History, never from Claude or the link · Money: every field that moves money (bid / cost cap, campaign spend cap, lifetime budget with dates, an earlier start) goes through `money_rules` (ceiling, +20 %, 3-day rule) and a confirmation that shows dollars; copies are created **paused**; delete keeps its typed-name danger confirmation and "turn it off instead" stays the default suggestion.

> **Architect resolutions (2026-11-13), applied below:**
> - Eugene's scope (b): every setting the Graph API lets change after creation, for campaigns and ad sets, plus **duplicate** (always paused), **archive** and **delete** for both levels. Who: **owner and this account's admins** (`admin_required`), never teammates or clients. Teammates keep on/off and budget on their assigned campaigns, as today.
> - What Meta allows after publish is pinned in one table, `edit_rules.MUTABLE`, from the Marketing API reference and Ads Manager behaviour; entries marked *(verify)* get a live check. A setting Meta refuses after the ad set has run (optimization goal, conversion location, attribution, billing) is offered **only while it has never delivered**; after that the form says why and offers **Make a paused copy with this change** (duplicate, then edit the copy).
> - **One write path per edit:** `POST /api/edit/<level>/<id>` with the fields changed and the values the form showed (`seen`); the server reads Meta fresh, refuses with 409 when a shown value changed since, runs the money rules, sends one Graph `POST /{id}` with only the changed fields, reads back, records each field in `meta_changes` (new `action` names) and lets the next status sync see it as the console's (D2 `explained_by_console` extended), so it never shows as "Changed in Ads Manager".
> - **Copies** go level by level (campaign shallow copy → each ad set copied into it → each ad copied into its ad set), all `status_option=PAUSED`, resumable like campaign builds (Meta's synchronous deep copy is limited to 3 child ads; Edge Bourne's campaign has 5). New table `copy_jobs`.
> - **Did it work?** (D3) checks are made for bid / cost cap, targeting, placements and optimization changes; History and chart marks show every change.
> - AM-B's "Apply in the console" for setup fields opens this form prefilled from the draft (feature flag `am_drafts.EDIT_FIELDS` becomes the AM-C list).
> - AM-D adds the audience pickers to this form; this spec leaves room for them (the Audience section's "Custom audiences" row).
> - Migration **047** (next free number when built). No bridge change.

## Goal

Eugene, 2026-11-13: *"our platform is intended to be able to create and much replace the ads manager … We currently are lacking implementations that have to do with campaign management."*

1. On a campaign or ad set page, **Edit** opens its settings in plain words (name, dates, bidding, who it reaches, where it shows, what it optimizes for), each showing what it is now.
2. Changing one shows old → new before anything is sent, with the same money questions as a budget change, then **Save**.
3. **Make a paused copy**, **Archive** and **Delete** (with "Turn it off instead" offered first) for campaigns and ad sets.
4. Everything lands in History and on the charts, and the console never mistakes its own change for one made in Ads Manager.

## What exists today

| What | Where |
|---|---|
| Budget write: fresh read, `from_cents` echo, ceiling, +20 %, 3-day rule, `accepted` stored | `backend/ads_api.py:992-1034`, `backend/money_rules.py:115-160` |
| On/off with spend confirmation | `backend/ads_api.py:451-475`, `:895-924` |
| Archive / delete for ads only (admin, must be off, typed name) | `backend/ads_api.py:154-172`, `:940-968` |
| Duplicate for ads only (`/{ad}/copies`, `status_option=PAUSED`, rename) | `backend/ads_api.py:1037-1064` |
| Every write in `meta_changes` + activity | `backend/ads_api.py:214-228` |
| Setup fields compared on sync (D2), outside-edit detection | `backend/status_history.py:24-37`, `:199-233`; `backend/sync.py:44-71`, `:142-160` |
| "Did it work?" checks | `backend/change_checks.py`, `backend/change_checks_db.py` |
| New ad set builder: locations, ages, Advantage+ audience, hints, schedule | `backend/adset_build.py`, `backend/adsets_api.py`, `frontend/js/new-aset.js`, `js/places.js` |
| Campaign / ad set page header actions | `frontend/js/entity.js:42-60` |
| Fake Meta writes on objects | `dev/fake_meta.py` graph POST (`/v24.0/<id>`), `/fake/_outside` |

## Data / migration: `backend/migrations/047_edits_copies.sql` (one file, written in one go)

```sql
-- AM-C: editing campaigns and ad sets after creation, copies, archive/delete at every level.

-- What the sync stores so the edit form and History can show the current setup (read with the full field set).
ALTER TABLE adsets ADD COLUMN targeting JSONB;                 -- whitelisted targeting (edit_rules.TARGETING_KEYS)
ALTER TABLE adsets ADD COLUMN placements_fp TEXT;              -- fingerprint of the placement keys (Advantage+ = 'auto')
ALTER TABLE adsets ADD COLUMN attribution JSONB;
ALTER TABLE adsets ADD COLUMN destination_type TEXT;
ALTER TABLE adsets ADD COLUMN billing_event TEXT;
ALTER TABLE adsets ADD COLUMN frequency JSONB;                 -- frequency_control_specs
ALTER TABLE adsets ADD COLUMN ever_delivered BOOLEAN NOT NULL DEFAULT FALSE;  -- any impression ever (ad_daily or Meta)
ALTER TABLE campaigns ADD COLUMN special_ad_categories TEXT[];

-- Copies: resumable like campaign_builds (one per Make a copy).
CREATE TABLE copy_jobs (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    level TEXT NOT NULL CHECK (level IN ('campaign', 'adset')),
    source_id TEXT NOT NULL,
    target_campaign_id TEXT,                       -- an ad set copied into another campaign
    plan JSONB NOT NULL,                           -- {name, adsets: [{id, name, ads: [ids]}]} picked by the person
    made JSONB NOT NULL DEFAULT '{}',              -- {campaign_id, adsets: {src: new}, ads: {src: new}, unknown}
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'partial', 'done')),
    error TEXT,
    client_key TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, client_key)
);
ALTER TABLE copy_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON copy_jobs
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
```

- `sync.ADSET_FIELDS` += `attribution_spec,destination_type,billing_event,frequency_control_specs,promoted_object`; `CAMPAIGN_FIELDS` += `special_ad_categories`. Stored under the same `_KEEP` rule (only from a full read). `targeting` stored whitelisted (no Meta-added defaults beyond `TARGETING_KEYS`).
- `status_history.SETUP["adset"]` += `"placements", "optimization_goal", "attribution", "frequency"`; `["campaign"]` += `"special_ad_categories"`; `OUTSIDE_FIELDS` follows (an Ads Manager change of these now shows too).

## Backend

### Pure logic (TDD first), new `backend/edit_rules.py`

```python
# (level, field) -> when it may change after creation. Sources: Marketing API Campaign / Ad Set reference
# ("Updating"), Ads Manager behaviour; (verify) = live check owed.
MUTABLE = {
    ("campaign", "name"): "always",
    ("campaign", "objective"): "never", ("campaign", "buying_type"): "never",
    ("campaign", "bid_strategy"): "always",          # not away from LOWEST_COST_WITH_MIN_ROAS (Meta), budget on the campaign only
    ("campaign", "spend_cap"): "always",             # remove = Meta's sentinel (verify); never below what it has spent
    ("campaign", "stop_time"): "lifetime_budget",    # only when the campaign holds a lifetime budget
    ("campaign", "special_ad_categories"): "add_only",   # (verify) removing: Ads Manager only
    ("adset", "name"): "always",
    ("adset", "start_time"): "not_started",
    ("adset", "end_time"): "always",                 # not in the past; required with a lifetime budget
    ("adset", "targeting"): "always",                # locations+radius, ages, genders, languages, detailed targeting,
                                                     # Advantage+ audience, custom/lookalike audiences (AM-D), exclusions
    ("adset", "placements"): "always",               # Advantage+ or manual (Meta may refuse manual for lead goals; shown)
    ("adset", "bid_strategy"): "ad_set_budget",
    ("adset", "bid_amount"): "capped_strategy",      # COST_CAP / LOWEST_COST_WITH_BID_CAP only
    ("adset", "optimization_goal"): "never_delivered",   # (verify)
    ("adset", "destination_type"): "never_delivered",    # conversion location (verify)
    ("adset", "attribution_spec"): "never_delivered",    # (verify)
    ("adset", "billing_event"): "never_delivered",       # (verify)
    ("adset", "frequency_control_specs"): "reach_goal",  # REACH / THRUPLAY goals only
    ("adset", "promoted_object"): "never",               # Page, form, pixel event
}

def editable(level, row, live) -> dict[str, str | None]       # {field: None if editable now, else the plain reason}
def changes(level, live, wanted) -> list[dict]                # only real differences, normalized (cents, ISO times, sorted lists)
def problems(level, live, changes, ctx) -> list[(field, msg)] # everything create-time builders check, plus:
    # end before start / in the past; lifetime budget without an end; start earlier than now on a running ad set -> confirm;
    # special categories: ages 18-65, all genders, radius >= 15 mi, no detailed exclusions, no lookalikes (Meta's rules);
    # Advantage+ audience age_min <= 25 (adset_build); manual placements need at least one;
    # bid_amount without a capped strategy; frequency outside reach goals.
def money(level, live, changes, ctx, last, now) -> dict       # the money side: see "Money rules" below
def review(level, live, changes, tz, currency) -> list[dict]  # [{field, words, old_words, new_words, note}] for the dialog
def meta_params(level, changes) -> dict                       # the Graph POST body (JSON strings for objects), only changed fields
def readback_ok(changes, fresh) -> list[str]                  # fields whose read-back differs (named in History and to the person)
```

New `money_rules` functions (pure, unit tested next to the existing ones):

```python
def bid_change(old_cents, new_cents, target_cpl_cents, cap_cents, last, now)
    # like budget_change for a bid / cost cap: big = raise > +20 %; recent = raise < 3 days after the last bid change;
    # over_cap = new above the daily-budget ceiling (a cap above a day's budget means nothing); 'high' = above 3x the
    # account's target cost per lead (knowing yes). Removing a cap (-> LOWEST_COST_WITHOUT_CAP) counts as a raise (big).
def spend_cap_change(old_cents, new_cents, spent_cents)
    # below spent -> refused; removal -> danger yes; a raise past 2x the current cap -> danger yes (as spend_limit_change)
def lifetime_pace(lifetime_cents, spent_cents, now, end) -> cents per day still to spend
def schedule_money(live, changes, now, cap)
    # a lifetime budget with a new end date: old pace vs new pace -> budget_change rules on the pace (ceiling, +20 %);
    # an earlier start on an ad set that is on -> the turn-on spend confirmation (what it can spend from then)
```

### Routes (new `backend/edit_api.py`; every one `admin_required`, and `can_touch` as `_target` does)

| Route | Owner | Account admin | Teammate | Client |
|---|---|---|---|---|
| `GET /api/edit/<level>/<id>` (fresh Meta read; current values in form shape; `editable` reasons; `last` bid change) | yes | yes | 403 | 403 |
| `POST /api/edit/<level>/<id>/check {changes}` (problems + review + money questions, no write) | yes | yes | 403 | 403 |
| `POST /api/edit/<level>/<id> {changes, seen, accept_big, accept_recent, accept_high, confirm_remove, confirm_daily_cents, undo_of}` | yes | yes | 403 | 403 |
| `POST /api/copy/<level>/<id>/plan` (what a copy would hold) / `POST /api/copy/<level>/<id> {plan, client_key}` / `GET /api/copy/<job>` / `POST /api/copy/<job>/resume` | yes | yes | 403 | 403 |
| `POST /api/ads/<level>/<id>/archive` / `.../delete {name}` for `campaign` and `adset` (the ad routes generalized) | yes | yes | 403 (as for ads today) | 403 |

- **Edit write** (`edit_api.save`): one try-lock per entity (`edit:<id>`); `GET` Meta now (`EDIT_FIELDS[level]`); for every changed field `seen[field]` must equal the live value (normalized) → else 409 `{field, live}` "Ads Manager has a different value now: check it again"; `edit_rules.problems` → 400 with `field`; `money_rules` → 409 with `code: big | recent | high | danger` and the knowing-yes flags it needs; then `meta_client.post(id, **meta_params)`; `UNKNOWN` answers are read back before anything else (stored → done; old → "may still arrive", never resent blind); read back the changed fields; record **one `meta_changes` row per field** (`action` in `edit_rules.ACTIONS`: `rename`, `schedule`, `bid_strategy`, `bid`, `spend_cap`, `targeting`, `placements`, `optimization`, `conversion_location`, `attribution`, `billing`, `frequency`, `special_categories`), `old_value` / `new_value` as plain text (targeting: `fp:<hash> <summary>`); store the new values on the row (`after_write`); `resync_later()`.
- **D2 consistency:** `status_history.explained_by_console` gets `FIELD_ACTIONS = {"bid_amount": ("bid",), "bid_strategy": ("bid_strategy",), "start_time": ("schedule",), "end_time": ("schedule",), "spend_cap": ("spend_cap",), "targeting": ("targeting",), "placements": ("placements",), "optimization_goal": ("optimization",), "attribution": ("attribution",), "frequency": ("frequency",), "special_ad_categories": ("special_categories",)}`: an event on one of those fields within `CONSOLE_WINDOW` after an ok row of that action with the same new value (targeting: the fingerprint) is the console's: no "Changed in Ads Manager", no `outside_edit` alert.
- **D3:** `change_checks_db` registers `bid`, `targeting`, `placements`, `optimization` (and a copy turned on later is a "new" ad as today); Put it back opens this form with the old values (`undo_of`, `ads_api.undo_target` with the new actions).
- **Copies** (`copy_api.py`, mirrors `builds_api.run`): advisory lock per job; steps `campaign` → `adset:<src>` → `ad:<src>`; campaign `POST /{id}/copies {deep_copy: false, status_option: PAUSED, rename_options: {rename_strategy: ONLY_TOP_LEVEL_RENAME, rename_suffix: " - copy"}}`; ad set `POST /{adset}/copies {campaign_id: <new or picked>, deep_copy: false, status_option: PAUSED}`; ad `POST /{ad}/copies {adset_id: <new>, status_option: PAUSED}`; an unanswered step is adopted only through `campaign_build.adoptable` (same name, paused, same parent, created since the job, not taken). A copied object that comes back not `PAUSED` is switched off at once and named in History (should never happen; the guard is tested with the fake). A copy into a campaign without its own budget carries the ad set's daily budget: above the ceiling → refused before anything is made.
- **Archive / delete** (`ads_api.removal_problem` generalized to levels): owner or account admin; must be off (`status` PAUSED) first ("Switch it off first" with the switch button); delete needs the exact name typed; the dialog shows what's inside ("1 ad set and 5 ads are deleted with it; their leads stay in the console") read fresh (`/{id}/adsets`, `/{id}/ads`); archive: `status=ARCHIVED`; delete: `status=DELETED` (as the ad route). Recorded as `archive` / `delete`.

### Settings in the form (what each section edits)

| Section (plain words) | Campaign | Ad set |
|---|---|---|
| Name | `name` | `name` |
| When it runs | `stop_time` (lifetime budget only) | `start_time` (before it starts), `end_time` or "No end date" (daily budget) |
| Bidding | `bid_strategy`: Highest volume / Cost per result goal / Bid cap (budget on the campaign); for a cap the amount goes on each ad set (listed) | `bid_strategy` (budget on the ad set), `bid_amount` |
| Spending cap | `spend_cap` amount / Remove | — |
| Special ad category | add Housing / Employment / Credit / Social issues (with what it changes) | — |
| Who it reaches | — | places with radius (the builder's `places.js`), ages, suggested ages (Advantage+), gender, languages (`locales` via `search?type=adlocale`), detailed targeting include / exclude (`search?type=adinterest` etc.), **Advantage+ audience** on/off, custom audiences (AM-D) |
| Where it shows | — | Advantage+ placements, or manual: Facebook / Instagram / Messenger / Audience Network with their positions |
| What it optimizes for | — | `optimization_goal`, conversion location, attribution window, billing: editable only while never delivered |
| How often people see it | — | `frequency_control_specs` (reach goals only) |

## UI

Classes `ed-` and `cp-`; new `js/edit.js` (form + review, reusing `js/places.js`, `controls.confirmDialog`, `builder.js` field marks). Plain words; phones 44 px, 16 px fields, nothing past 320 px.

- **Campaign / Ad set page** (`entity.js` header, owner and account admins): **Edit** (primary outline), and a **More** menu: **Make a paused copy**, **Archive…**, **Delete…**. Teammates and clients see neither.
- **Edit** opens a full page panel (desktop: a side panel 560 px; phone: a full screen layer with Back closing it via `urlstate.openLayer`), one section per row above, each folded under a summary line of what it is now ("Riverside + 25 mi, ages 25–65, Advantage+ audience"). Fields read-only with the reason when `editable` says so ("Meta doesn't allow changing this after the ad set has delivered. **Make a paused copy with this change**").
- **Save** → `check` → a confirmation (`confirmDialog`) listing old → new per change; money lines as in the budget dialog ("Cost per result goal $12.00 → $15.00 a lead (+25 %): more than +20 % in one step; Meta may restart learning."); the knowing-yes checkboxes the server named; delete/remove ones use the danger style. Learning reset note for targeting / placements / optimization changes ("Meta restarts learning for this ad set; results wobble for a few days").
- After saving: a toast "Saved. Meta shows it within a minute.", the page reloads its data, History shows the lines ("Ages 25–65 → 30–65", "Cost per result goal $12.00 → $15.00").
- **Make a paused copy**: a dialog listing what the copy will hold (ad sets and ads with checkboxes, all ticked except deleted / archived), the new name (" - copy"), for an ad set the campaign it goes in; **Make the copy** → progress per step → "Made, switched off" with Open it; a partial copy shows **Finish the copy** (resume) like a build.
- **Archive… / Delete…**: if on → "Switch it off first" with the switch; Delete first offers **Turn it off instead** (primary) and **Delete anyway** (danger, typed name). Archived and deleted levels show their pill and drop out of the default views as ads do.
- AM-B: the drafts panel's **Apply in the console** for these fields opens Edit with the draft's new value filled and its row outlined.

## Money and security rules

- **Read fresh, echo, then write**: every save compares what the form showed with Meta now (409 on any difference); nothing is computed from stored values alone.
- **Money rules** (all server side, `money_rules`):
  - Bid / cost cap: ceiling (daily-budget ceiling), +20 % knowing yes, 3-day rule on raises (rollback exempt, as budgets), above 3× the target cost per lead needs its own knowing yes; removing a cap = a big raise.
  - Campaign spend cap: never at or below what it has spent; removal or more than 2× the current cap → danger second yes (same wording as the account limit).
  - Lifetime budget with a new end date: the daily pace before and after through `budget_change` (ceiling, +20 %).
  - An earlier start on an ad set that is on: the turn-on spend confirmation (`turn_on_problem`, what it can spend a day, echoed).
  - Copies are paused (`status_option=PAUSED`, checked on read-back); a copy's budget over the ceiling is refused.
  - Delete: typed name + danger; never on a sheet of several; "turn it off instead" offered first.
- **No automation**: only a person's Save / Make the copy / Archive / Delete writes. Claude's suggestions about these fields stay `targeting` / `other` kinds that are recorded, not applied (as today).
- **History**: every field in `meta_changes` with old → new; read-back differences named ("Meta kept 30–65, not 25–65"); D2 explains them as the console's; D3 checks where they apply.
- Roles: owner and account admins; teammates and clients 403 on every route.

## Fake Meta additions (`dev/fake_meta.py`)

- Objects store and return the new fields (`attribution_spec`, `destination_type`, `billing_event`, `frequency_control_specs`, `promoted_object`, `special_ad_categories`, `targeting` with every key).
- Mutability enforced like Meta: an ad set with spend (fake `ever_delivered`) refuses `optimization_goal`, `destination_type`, `attribution_spec`, `billing_event`, `promoted_object` with code 100, subcode 1885 (fake value, plain message "This field can't be changed after the ad set has delivered"); `objective` always refused; `bid_amount` without a capped strategy refused; `end_time` in the past refused. `/fake/_mutability?field=&allow=1` relaxes one for a test. Never a rate-limit code.
- `POST /{campaign}/copies` and `/{adset}/copies` (with `campaign_id`, `deep_copy`, `status_option`, `rename_options`) return Meta's shape (`copied_campaign_id` / `copied_adset_id`, `ad_object_ids`); `/fake/_copy?active=1` makes the next copy come back ACTIVE (the guard's test); `/fake/_copy?silent=1` drops the answer (adoption).
- Campaign / ad set `status=ARCHIVED|DELETED` with children cascading as Meta does.
- `search?type=adlocale|adinterest|adTargetingCategory` (a few fixed rows).

## Tests

### Unit: `backend/tests/test_edit_rules_logic.py` and additions to `test_money_rules_logic.py` (write first)

| Case | Expected |
|---|---|
| `editable("adset", never delivered)` / delivered | goal fields editable / each with the reason |
| `editable("campaign")` objective; spend_cap; stop_time without lifetime | reason; None; reason |
| `changes` same targeting in another order; cents as strings; an end time in another zone | no change (each) |
| `problems` end before start; lifetime with no end; Advantage+ age_min 30; manual placements none ticked; special category with radius 10 mi / ages 25–65 / a lookalike | one message each |
| `meta_params` targeting + name | only those two keys, targeting JSON string |
| `readback_ok` Meta kept another age | `["targeting"]` |
| `bid_change` 1200 → 1500 / → 1400 / 2 days after a raise / rollback within 3 days / above 3× target / above the ceiling / cap removed | big / ok / recent / ok / high / over_cap / big |
| `spend_cap_change` below spent / removal / 2.5× | refused / danger / danger |
| `schedule_money` lifetime $300, $100 spent, end moved 10 days → 5 days earlier | pace doubles → big |
| … earlier start on a running ad set | needs the turn-on confirmation |
| `status_history.explained_by_console` a `targeting` event 2 min after an ok `targeting` change with the same fingerprint / 12 min after / another fingerprint | explained / not / not |

`backend/tests/test_edit_routes.py`: a teammate and a client get 403 on every edit, copy, archive and delete route (one test per route, so a route added without the decorator fails); `seen` different from the fake → 409 and no POST reached the fake (`/fake/_hits`); a delete without the name → 400.

### `qa/flows.cjs` (new block "Edit campaigns and ad sets", ~22 checks)

1. Ad set page → **Edit**: sections with today's values (places, ages, Advantage+, placements "Advantage+", goal "Leads"); goal fields read-only with the reason (the live ad set has delivered).
2. Change ages 25 → 30 with Advantage+ on → "minimum age can be at most 25" on the field. **Refusal.**
3. Ages 25–65 → 30–65 with Advantage+ off → review shows "Ages 25–65 → 30–65" + the learning note → Save → the fake holds 30; History "Ages 25–65 → 30–65"; after `pull()` no "Changed in Ads Manager" line and no `outside_edit` alert.
4. Ads Manager changes the ages meanwhile (`/fake/_outside`) before Save → 409 "Ads Manager has a different value now". **Refusal.**
5. Add a place through the place search; radius 60 mi → the range error. **Refusal.**
6. Manual placements: Instagram only → saved; the fake's `publisher_platforms == ["instagram"]`.
7. Campaign → Bidding → Cost per result goal $12 on its ad set; then $12 → $15 → "+25 %" knowing yes; without it 409. **Refusal.** With it saved; the ad set's `bid_amount` 1500.
8. Raise again at once → the 3-day question; accepted → `accepted` holds `recent`.
9. A cost cap above the ceiling → refused. **Refusal.**
10. Campaign spend cap: below spent → refused (**Refusal**); remove → danger dialog; saved.
11. Name change → History "Renamed …"; the manager shows the new name.
12. A never-delivered ad set (made with New ad set) → Edit goal → saved; the delivered one offers **Make a paused copy with this change**.
13. Make a paused copy of the campaign (1 ad set, 5 ads) → progress → the fake has a campaign, an ad set and 5 ads, all `PAUSED`; the manager shows them off.
14. `/fake/_copy?active=1` → the copy is switched off at once and History says so. **Refusal of a live copy.**
15. `/fake/_copy?silent=1` on the ad set step → "Finish the copy" → resumes and adopts, no duplicate ad set.
16. Archive a campaign that is on → "Switch it off first". **Refusal.**
17. Delete an ad set: **Turn it off instead** is the primary button; Delete with a wrong name → field error (**Refusal**); the right name → deleted, its ads with it; leads still on Leads.
18. Teammate session: no Edit / More on campaign and ad set pages; `POST /api/edit/...` 403. **Refusal.**
19. Client: 403 on every route. **Refusal.**
20. AM-B edit draft "name" row → **Apply in the console** opens Edit with the draft's name filled and outlined.
21. Phone 390 and 320: the Edit layer full screen, sections fold, fields 16 px, Save ≥ 44 px, Back closes it.
22. Guard sweep (`ed-`, `cp-`, `edit.js`), no console errors.

### `dev/qa_leaks.py`

Seed a marked `copy_jobs` row per account; `GET /api/copy/<other account's job>` → 404; `GET /api/edit/<level>/<other account's id>` → 404; edit/copy/archive/delete aimed at account 1's ids from account 2 → 404 and nothing reaches the fake. RLS sweep covers `copy_jobs`.

### Screenshots

`qa/shots.cjs`: the Edit panel (ad set, all sections open), the review dialog with a money line, the copy dialog, the delete dialog; light/dark, desktop/390 px.

## Live checks owed (with Eugene's yes for each write, on a paused copy)

1. Which ad set fields Meta refuses after delivery on v24 for an Instant Form leads ad set (optimization goal, destination, attribution, billing): adjust `MUTABLE`.
2. Removing a campaign spend cap: the sentinel value Meta takes; the minimum cap.
3. Manual placements on a leads ad set in 2026 (the 4.2 note says Meta may refuse them).
4. Special ad category added to a live campaign: re-review and targeting checks.
5. A campaign copy level by level on the real account (paused), and the names Meta gives.
6. Archive and delete of a paused test campaign; that its leads stay readable.
7. That a console edit is not shown as "Changed in Ads Manager" after the hourly sync on real data.

## Out of scope

- Editing ads' creatives (5.5 already swaps creatives), lead forms (can't be edited on Meta), budgets (exist).
- Bulk edits of setup fields (the bulk bar keeps on/off, budget, archive).
- Campaign objective changes, A/B test structure, Advantage+ campaign type conversions.
- Changing settings from Claude's suggestions automatically.
