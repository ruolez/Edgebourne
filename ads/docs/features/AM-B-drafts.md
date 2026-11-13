# AM-B · Drafts in Ads Manager: see them, finish them in the console, apply staged edits

Unit key: `AM-B-drafts` · Asked by Eugene 2026-11-13 · Needs AM-A (the link) · Meta: **no new write path**. Drafts are read through the link; finishing one creates new objects through the console's own Graph key, **paused**, with the builders' usual checks and confirmations; applying a staged edit goes through the existing confirmation for that setting · Money: none new. Nothing goes live without the existing Publish / turn-on confirmations.

> **Architect resolutions (2026-11-13), applied below:**
> - Eugene's answer 1, "Finish in console": the console reads the draft through the Mac link, **fills its own builder** (New campaign `builds_api` / `campaign_build`, New ad set `adsets_api` / `adset_build`, New ad `ads_api.create_ad_from`) with the draft's values, and creates it **paused** with its own key. The draft is **never** published, edited or discarded through MCP; it stays in Ads Manager, marked here **"Finished in the console"** with a link to what was made, for Eugene to discard there.
> - A draft that **edits a live object** (`action` other than `add`) is shown as old → new per setting. **Apply in the console** opens the existing confirmation for that setting: budget → the budget dialog (`POST /api/ads/<level>/<id>/budget`, +20 %, 3-day rule, ceiling), on/off → the switch flow (turn-on confirmation), every other setting → AM-C's edit form filled with the draft's new value (wired by AM-C; until AM-C is built that button reads **Change it in Ads Manager**).
> - Drafts are scoped by Meta to the person who staged them (Eugene's Facebook login on the Mac). The screens say "Drafts you started in Ads Manager".
> - The draft's values are untrusted: the server keeps whitelisted fields per object type, and every value that reaches a builder goes through the same `clean()` and `problems()` a person's typing does.
> - Inbox: **New draft in Ads Manager** and **Draft has problems** are FYI items (alerts with level `info`), never notified.
> - Migration **046** (next free number when built). No bridge change beyond AM-A (the `drafts` kind is already in its plan).

## Goal

Eugene, 2026-11-13: *"our platform is intended to be able to create and much replace the ads manager. We do have access to those drafts via the console … We currently are lacking implementations that have to do with campaign management."* Concretely, the draft "Edge Bourne - Dashboards with AI - Leads" ($20/day, Leads, staged by Claude on the Mac) never showed in the console because the Graph API doesn't return Ads Manager drafts.

1. Ads → Campaigns shows **Drafts in Ads Manager (2)**: what each one holds, what's missing (ad set, ads, creative, lead form), Meta's own problems with it, when it was last edited.
2. **Finish in the console** opens New campaign (or New ad set / New ad) already filled in; he adds what's missing and creates it paused, as always; then Publish with the typed budget.
3. A staged edit of a live campaign ("budget $20 → $25") shows old → new with **Apply in the console**, which asks the same questions as changing it here would.
4. **Open in Ads Manager** for anything the console doesn't build.

## What exists today

| What | Where |
|---|---|
| The listing that never returns drafts | `backend/sync.py:177-185` |
| New campaign: clean, field problems, review, create paused (resumable), publish with typed budget | `backend/builds_api.py:36-72`, `:112-190`, `:270-302`; `backend/campaign_build.py:22-117` |
| New ad set: clean, problems, payload, create paused | `backend/adsets_api.py:37-63`, `:134-183`; `backend/adset_build.py:22-123` |
| New ad from a template or media, created paused | `backend/ads_api.py:1247-1380` |
| Budget change with fresh read, ceiling, +20 %, 3-day rule | `backend/ads_api.py:992-1034`, `backend/money_rules.py:115-160` |
| On/off with the turn-on confirmation | `backend/ads_api.py:895-924` |
| Builders' pages | `frontend/new-campaign.html` + `js/new-campaign.js`, `new-adset.html` + `js/new-aset.js`, `new-ad.html` + `js/new-creative.js`, stepper `js/builder.js` |
| The manager table and its built-in views | `frontend/js/manager.js`, `frontend/js/listing.js` |
| Inbox categories and FYI rules | `backend/inbox.py:13-38` |
| The link, its passes and source line | AM-A |

## Data / migration: `backend/migrations/046_am_drafts.sql` (one file, written in one go)

```sql
-- AM-B: Ads Manager drafts read through the Mac link (AM-A). Kept per console account, bound to the link pass.
CREATE TABLE am_drafts (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    draft_id TEXT NOT NULL,                    -- Meta's ad_object_id (digits)
    object_type TEXT NOT NULL CHECK (object_type IN ('campaign', 'adset', 'ad')),
    parent_id TEXT,                            -- parent_ad_object_id (a draft or a live object)
    action TEXT NOT NULL,                      -- 'add' or Meta's word for an edit (<= 20 chars, lower case)
    meta_status TEXT,                          -- EDITING …
    validation_status TEXT,                    -- VALIDATED …
    source TEXT,                               -- mcp_campaign_creation, ads_manager …
    time_updated TIMESTAMPTZ,
    fields JSONB NOT NULL,                     -- {field: {"old": …, "new": …}} whitelisted (am_drafts.FIELDS)
    other_fields TEXT[] NOT NULL DEFAULT '{}', -- names of fields the console doesn't read (shown as "Also set: …")
    problems JSONB NOT NULL DEFAULT '[]',      -- active_errors + publish_error, [{message, field}] cut to 300 chars
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL,         -- the last link read that returned it
    gone_at TIMESTAMPTZ,                       -- a complete read no longer returned it (published or discarded in Ads Manager)
    finished_build_id INTEGER REFERENCES campaign_builds(id) ON DELETE SET NULL,
    finished_entity TEXT,                      -- 'campaign:<id>' | 'adset:<id>' | 'ad:<id>' made from it
    finished_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    finished_at TIMESTAMPTZ,
    applied JSONB NOT NULL DEFAULT '{}',       -- edit drafts: {field: meta_changes id} applied from here
    PRIMARY KEY (account_id, draft_id)
);
CREATE INDEX am_drafts_open ON am_drafts (account_id, gone_at, time_updated DESC);
ALTER TABLE am_drafts ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON am_drafts
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

ALTER TABLE campaign_builds ADD COLUMN draft_id TEXT;   -- the Ads Manager draft this build finished
```

- `am_link.KINDS` (AM-A) accepts `drafts` now; its push writes here instead of `am_snapshots`.
- A read is **complete** only when every cursor page came back (the push carries `complete: true` from the Mac); only a complete read sets `gone_at` on drafts it no longer lists (the same guard as `mark_missing`'s `if seen:`). A draft that reappears clears `gone_at`.
- Gone drafts and finished ones are kept 30 days (`jobs.PRUNE`), so "Finished in the console" stays visible after Eugene discards it.

## Backend

### Pure logic (TDD first), new `backend/am_drafts.py`

```python
FIELDS = {   # whitelisted values per object type; anything else -> other_fields (names only)
    "campaign": ("name", "objective", "buying_type", "daily_budget", "lifetime_budget", "bid_strategy", "spend_cap",
                 "special_ad_categories", "start_time", "stop_time", "status"),
    "adset": ("name", "campaign_id", "daily_budget", "lifetime_budget", "bid_strategy", "bid_amount", "optimization_goal",
              "billing_event", "destination_type", "promoted_object", "targeting", "start_time", "end_time",
              "attribution_spec", "status"),
    "ad": ("name", "adset_id", "creative", "status"),
}
TARGETING_KEYS = status_history.AUDIENCE_KEYS + ("targeting_automation", "age_range", "publisher_platforms",
                  "facebook_positions", "instagram_positions", "custom_audiences", "excluded_custom_audiences")
CREATIVE_KEYS = {"object_story_spec": {"page_id", "link_data", "video_data"}, "link_data": {"message", "name", "description",
                 "link", "image_hash", "call_to_action"}, "video_data": {"message", "title", "video_id", "image_hash", "call_to_action"},
                 "call_to_action": {"type", "value"}, "value": {"lead_gen_form_id", "link"}}

def normalize(raw) -> list[dict]
    # Meta's {"ad_drafts": [...]} (paged; the Mac concatenates pages) -> rows for am_drafts. ad_object_type
    # 'ad_set' -> 'adset'; values {field: {"new": x[, "old": y]}} kept for FIELDS only, nested keys by the
    # tables above; ids digits only; strings cut at 300 (names 200, texts 5000 like builds_api.clean);
    # active_errors [{message|error_message|summary, field}] + publish_error -> problems; unknown object types dropped.

def tree(rows) -> list[dict]
    # campaign drafts with their ad set drafts and ad drafts under them (by parent_id); an ad set or ad draft whose
    # parent is a live object stands alone with that parent named. Newest time_updated first.

def missing(node, live_parents) -> list[str]
    # plain words for what an 'add' draft lacks before the console can create it:
    # "No ad set yet", "No places or ages for the ad set", "No ads yet", "Ad 2 has no picture or video",
    # "Ad 1 has no lead form", "No Facebook Page", "No daily budget" (and none of them when complete)

def finishable(node) -> str | None
    # None, or why the console can't finish it (shown with Open in Ads Manager):
    # objective other than OUTCOME_LEADS -> "This draft's goal is <words>; the console builds lead campaigns only."
    # buying_type other than AUCTION; destination other than the Instant Form ('ON_AD');
    # a lifetime budget at campaign level (the wizard sets daily budgets).

def to_campaign_spec(node, known_forms, known_templates, page_id) -> tuple[dict, list[str]]
    # (a dict builds_api.clean() accepts, notes): name; daily_budget -> daily_budget_cents; the first ad set draft's
    # targeting -> adset_build.locations_from / spec_from (pure, existing); start/end; each ad draft -> {name, title,
    # body, cta_type, media {image hash | video id}, template_ad_id: ""}; the lead form id from the ads'
    # call_to_action.value.lead_gen_form_id when known_forms has it. notes = what was left out and why
    # ("Bid cap $12: the wizard uses lowest cost; set it after creating (Edit)", "2 hint interests kept as hints").

def to_adset_spec(node, campaign_row) / to_ad_spec(node, adset_row) -> same shape for New ad set / New ad

def edit_rows(node, live) -> list[dict]
    # an edit draft as [{field, words, old, new, now, stale, apply}] where now = our stored value, stale = the
    # draft's old differs from now (Ads Manager changed since), apply in ('budget', 'status', 'edit', 'manager'):
    # daily_budget -> 'budget'; status -> 'status'; fields AM-C edits -> 'edit'; anything else -> 'manager'.

def inbox_events(before, after, now) -> list[dict]
    # draft_new (first seen, not one the console finished), draft_problems (problems non-empty, condition),
    # draft_problems resolved when problems clear or the draft is gone
```

### Routes (new `backend/drafts_api.py`)

| Route | Owner | Account admin | Teammate | Client |
|---|---|---|---|---|
| `GET /api/drafts` (open drafts as a tree, with `missing`, `finishable`, `edit_rows`, finished ones, `source` from `am_link.source`) | yes | yes | 403 | 403 |
| `GET /api/drafts/<draft_id>/spec` (the builder's prefill: `{page: "new-campaign" \| "new-adset" \| "new-ad", spec, notes}`) | yes | yes | 403 | 403 |
| `POST /api/drafts/<draft_id>/check` (fresh link read requested + the builder's `check()` on the prefill) | yes | yes | 403 | 403 |
| `POST /api/builds` with `draft_id` | yes | yes | 403 (as today) | 403 |
| `POST /api/adsets` / `POST /api/ads/new` with `draft_id` | yes | yes | 403 | 403 |
| `POST /api/drafts/<draft_id>/applied {field, change_id}` (records an Apply done through an existing route) | yes | yes | 403 | 403 |

- `drafts_api` reads `am_drafts` only (no Meta call, no MCP call); a draft id not in this account → 404 (RLS).
- The builders' create routes take an optional `draft_id`: the build stores it (`campaign_builds.draft_id`); after the create succeeds `am_drafts.finished_build_id / finished_entity / finished_by / finished_at` are set and `log_activity("draft.finished")`. The spec that is created is **the person's submitted spec**, cleaned and checked as any other; the draft only prefilled the page. A draft already finished → 409 "Already finished in the console: open it" with the link (a second build from the same draft needs **Make another from this draft**, which sends `again: true`).
- `applied` is called by the page after an Apply succeeded through the existing route (budget / status / AM-C edit); it checks that `change_id` is an ok `meta_changes` row on that draft's object and field made in the last 10 minutes by this person, then stores it. It never writes to Meta itself.
- Before **Finish** and **Apply**, the page asks `POST /api/am-link/check` (AM-A) for a fresh read when the last one is over 5 minutes old and shows "Checking Ads Manager…" for up to 20 s; it never blocks on it (the source line says how old the draft is).

### Alerts and Inbox

- `alerts.DEFAULTS["draft_new"] = {"on": True}`: event, level `info`, category `status`, title "New draft in Ads Manager: “<name>”", line "Started <time> · <what it holds>", href `/ads.html?level=campaign&view=drafts#draft=<id>`. Not for drafts the console finished. Never notified (info).
- `alerts.DEFAULTS["draft_problems"] = {"on": True}`: condition, level `info`, "Meta has problems with your draft “<name>”", the first problem's message (plain text, 300 chars) and "+N more"; resolved when the problems clear or the draft is gone. Not snoozable (FYI already).
- Both raised in the link push handler (`am_link_api.push` → `am_drafts.inbox_events` → `alerts.raise_found`), under the pass's account.

## UI

Classes `dr-`; new file `js/drafts.js`. Plain words; phones as cards; 44 px targets; nothing past 320 px.

### Ads → Campaigns (`ads.html?level=campaign`, `js/manager.js`)

- Above the table, a panel **Drafts in Ads Manager** (owner and account admins; only when there is at least one open or recently finished draft): "2 drafts you started in Ads Manager" + `ui.linkNote` ("From Ads Manager via your Mac, 12 min ago") + **Check Ads Manager now**.
- Each draft is a row (desktop) / card (phone):
  - Name, what it is ("New campaign · Leads · $20.00 a day · lowest cost" / "Edit of “Edge Bourne - Free intro call - Leads”"), last edited ("Edited in Ads Manager 9:31 AM"), a **Draft** pill (neutral grey; never green).
  - **What it holds**: "1 ad set · Riverside + 25 mi, ages 25–65 · 0 ads" (from the tree).
  - **What's missing**: the `missing` lines as a short list with a warning dot; none → "Ready to create".
  - **Meta's problems**: each problem's message (text only), or nothing.
  - Actions: **Finish in the console** (primary; disabled with the `finishable` reason when it can't), **Open in Ads Manager** (built by the console: `https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=<ad account>&selected_campaign_ids=<id>`; opens a new tab), a fold **What else it sets** for `other_fields`.
  - Edit drafts: a small table Setting · Now · In the draft, each row with **Apply in the console** (budget, on/off) or **Change it in Ads Manager** (until AM-C), with "Ads Manager changed this since the draft" when `stale`.
  - Finished: "Finished in the console 10:02 AM · Open it" (to the campaign or build) and "Discard the draft in Ads Manager when you're done" (no button that discards).
- A built-in view **Drafts** in the view list opens the same panel alone (`?view=drafts`); `#draft=<id>` scrolls to and outlines one.
- Teammates and clients: nothing (the panel isn't rendered; routes 403).

### Builders with a draft (`?draft=<id>`)

- New campaign / New ad set / New ad read `GET /api/drafts/<id>/spec` and fill the form (the steps beside it show what's done and what's missing as usual). A top note (`.dr-note`, violet is not used: this is Meta's, not Claude's): "Filled in from your Ads Manager draft “…” (read 9:42 AM). Nothing is created until you press Create, and it's created off." plus `notes` as a list ("Bid cap $12 isn't set by this page: change it after creating").
- Create → the usual confirmation → created paused → the success panel adds "The draft is still in Ads Manager: discard it there." with **Open in Ads Manager**.
- Publish stays exactly as today (typed daily budget).

### Today and Inbox

- Inbox: the two FYI kinds in the Status filter; each item opens the draft on Ads.
- Today: under "Upkeep" (FYI only, after the queue) one line "2 drafts in Ads Manager: Finish them here" when any open draft is finishable, for owner and account admins.

## Money and security rules

- **No new write path.** Drafts are read by the link (AM-A, read tools only). Finishing a draft is the builder's existing create (`status: PAUSED` in `campaign_build.campaign_payload`, `adset_build.payload`, the ad create), with the person pressing Create after seeing the review; Publish keeps its typed budget and fresh budget read. Applying a staged edit is the existing budget / switch route with every check it has today (fresh read, `from_cents` echo, ceiling, +20 %, 3-day rule, turn-on spend confirmation), started by the person.
- **The draft can't smuggle anything.** Its values only prefill the page; the create route receives what the page submits and runs `clean()` + `problems()` + the ceiling as for typing. A draft's budget over the ceiling shows the usual "above this account's ceiling" error on the budget step. Special ad categories, lifetime budgets or other objectives make it unfinishable here (no silent drop of a constraint): "Finish it in Ads Manager".
- **Never deleted or discarded by us.** No route touches the draft on Meta.
- **Untrusted text** (names, problems, field values): `esc` / `textContent` only; Ads Manager links are built from digits.
- **Roles:** owner and account admins (the builders' audience). Teammates and clients see nothing of drafts.

## Fake Meta / fake MCP additions

- `dev/fake_mcp.py` drafts (returned by `ads_get_ad_entities` with `object_state: "draft"`), consistent with `fake_meta.py`:
  1. The real 2026-11-13 campaign draft verbatim (`120252756936450312`, "Edge Bourne - Dashboards with AI - Leads", `daily_budget.new: 2000`, `validation_status: VALIDATED`, `source: mcp_campaign_creation`) with an ad set draft under it (Riverside + 25 mi, ages 25–65, Advantage+ audience, `promoted_object.page_id`) and no ads → missing "No ads yet".
  2. A complete draft: campaign + ad set + 2 ad drafts (one image hash from the fake's library, one video id; lead form `1132280359202136`) → "Ready to create".
  3. An edit draft (`action: "update"`) of the live campaign `120252638288040312`: `daily_budget {old: 2000, new: 2500}` and `name {old, new}`.
  4. A draft with `active_errors: [{"message": "Choose a Facebook Page for this ad."}]` and a `publish_error`.
  5. A Sales-objective draft (`OUTCOME_SALES`) → unfinishable.
- Paging: `limit` counts campaigns with their subtree; `/fake/_mcp?draft_pages=2` splits the answer over two cursors; `?drafts=none` empties it; `?draft_add=<json>` / `?draft_drop=<id>` for QA.
- `fake_meta.py`: `POST act_/campaigns` etc. already create paused objects; no change. QA asserts the fake's `HITS` never contains an MCP write and the draft list still holds the finished draft (we never discard it).

## Tests

### Unit: `backend/tests/test_am_drafts_logic.py` (write first)

| Case | Expected |
|---|---|
| `normalize` the verbatim 2026-11-13 response | one campaign row, `fields.daily_budget.new == 2000`, `objective.new == "OUTCOME_LEADS"`, `other_fields == ["is_odax_campaign_group"]`, problems `[]` |
| … `ad_object_type: "ad_set"`, a `<img onerror>` name, a 9,000-char message, an unknown type | `adset`; name kept as plain text (cut at 200); message 300; row dropped |
| `tree` campaign + ad set + 2 ads; an ad draft whose parent is a live ad set | nested; standalone with parent named |
| `missing` for drafts 1, 2, 4 | "No ads yet"; `[]`; "No Facebook Page" |
| `finishable` Sales objective / lifetime budget / leads daily | sentence / sentence / None |
| `to_campaign_spec` draft 2 | `builds_api.clean(spec)` round-trips; `campaign_build.field_problems(spec, …) == []`; budget 2000; locations from targeting via `adset_build.locations_from`; form id kept only when known |
| … with an unknown form id / a bid cap / interests | form empty + note; note about the bid cap; `keep_hints` true |
| … with `daily_budget.new` above the ceiling | spec keeps the amount; `builds_api.check` reports the ceiling problem (the draft never bypasses it) |
| `edit_rows` draft 3 with stored budget 2000 / stored 2200 | `apply: "budget"`, not stale / stale |
| … `name` row before AM-C / after | `apply: "manager"` / `"edit"` (feature flag `am_drafts.EDIT_FIELDS`) |
| `inbox_events` first sighting / again / problems cleared / finished draft first seen | `draft_new` once; nothing; resolve; nothing |

`backend/tests/test_drafts_routes.py`: a complete read sets `gone_at`, a partial one doesn't; `POST /api/builds` with `draft_id` stores it and marks the draft finished; again → 409 unless `again`; teammate / client 403 on every drafts route; a draft id of account 2 from account 1 → 404.

### `qa/flows.cjs` (new block "Drafts", ~17 checks)

1. After a link pass (AM-A helper), Ads → Campaigns shows `#dr-panel` with 5 drafts and the source line "From Ads Manager via your Mac".
2. Draft 1 shows "No ads yet"; draft 2 "Ready to create"; draft 4 Meta's problem text; draft 5 Finish disabled with "the console builds lead campaigns only".
3. A name with markup from the fake renders as text (no element created). **Refusal.**
4. Finish draft 2 → `new-campaign.html?draft=…` filled (name, $20.00, Riverside + 25 mi, two ads with media, the form); the note names the draft.
5. Create → confirmation → created; the fake's new campaign, ad set and ads are all `PAUSED`; no MCP write (`/fake/_mcp_hits` `write_calls == 0`).
6. Back on Ads: draft 2 reads "Finished in the console · Open it", still listed by the fake (never discarded).
7. Publish still asks for the typed budget; a wrong amount → the field error. **Refusal.**
8. Finish draft 2 again → 409 "Already finished" with the link. **Refusal.**
9. A draft whose budget is over the ceiling → the budget step shows the ceiling error; Create refuses. **Refusal.**
10. Edit draft 3: the row $20.00 → $25.00; **Apply in the console** opens the budget dialog with +25 % and the "more than +20 %" knowing-yes; after the yes the fake's budget is 2500 and the draft row says "Applied".
11. The same with a budget changed "in Ads Manager" since (`/fake/_outside`) → "Ads Manager changed this since the draft" and the dialog reads the live amount.
12. Inbox → Status → "New draft in Ads Manager" (FYI, unread, not in Needs action) and "Meta has problems with your draft" (FYI); `/fake/_mcp?draft_drop=<4>` + a complete pass → the problem item resolves.
13. A partial pass (two pages, the second failing) keeps every draft. **Refusal of a false "gone".**
14. Teammate: no panel, `GET /api/drafts` 403; client 403. **Refusal.**
15. Mac away (runs back-dated) → the panel says "Your Mac has been away since …".
16. Phone 390 and 320: cards, actions ≥ 44 px, nothing past the edge; the builder note wraps.
17. Guard sweep (`dr-`, `drafts.js`), no console errors.

### `dev/qa_leaks.py`

Seed one marked `am_drafts` row per account (name holds the mark). `/api/drafts`, `/api/drafts/<other account's id>/spec` (404), Inbox and Today must not show the other mark. RLS sweep covers `am_drafts`.

### Screenshots

`qa/shots.cjs`: Ads with the drafts panel (open, finished, edit draft), New campaign filled from a draft; light/dark, desktop/390 px.

## Live checks owed (with Eugene)

1. The real draft "Edge Bourne - Dashboards with AI - Leads" appears within 15 minutes of connecting, with its ad set and what's missing matching Ads Manager.
2. Paging: how Meta counts `limit` for a campaign with its subtree, and that the cursor reads the rest.
3. An Ads Manager edit draft (change a budget in Ads Manager, don't publish): its `action` word and whether `values` carry `old`.
4. Finish a real draft in the console (his yes): created paused with the console key, the draft still in Ads Manager, then he discards it there and the next complete read marks it gone.
5. What `source` values Ads Manager's own drafts carry (vs `mcp_campaign_creation`).

## Out of scope

- Publishing, editing or discarding drafts on Meta (MCP writes), by Eugene's answer.
- Drafts of other people (Meta scopes them to their author).
- Lifetime-budget, non-lead, special-category or non-Instant-Form drafts: "Open in Ads Manager".
