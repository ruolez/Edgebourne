# AM-D · Audiences: see them, make website, engagement and lookalike audiences, pick them in ad sets

Unit key: `AM-D-audiences` · Asked by Eugene 2026-11-13 · Needs AM-C (the ad set edit form) · Meta: Graph API through the console's own key: `act_<id>/customaudiences` (read, create website / engagement / lookalike), `act_<id>/saved_audiences` (read), ad set targeting writes through AM-C · Money: none by itself. Picking an audience in a live ad set is a targeting change and goes through AM-C's confirmation (learning note, read fresh, History); nothing spends from creating an audience.

> **Architect resolutions (2026-11-13), applied below:**
> - Eugene's scope (c): list **saved, custom and lookalike audiences** with size, status and where used; **create** website audiences (from the Pixel), engagement audiences (Facebook Page, Instagram account, lead form, video) and **lookalikes** from any of them; pick them (**include / exclude**) in New ad set, New campaign's ad set step and AM-C's ad set Edit. **No customer-list upload** (no PII ever leaves or enters the console).
> - Who: list for owner, account admins and teammates (read only for teammates: names, sizes, where used); create and pick for owner and account admins; clients never.
> - Meta's audience rule JSON is built by one pure module (`audience_rules`), each shape marked *(verify)* against the Custom Audiences reference and pinned in the fake; a refusal from Meta is shown in plain words with the field.
> - Sizes: Meta's lower/upper bounds; "Still filling (Meta needs a few hours)" while it reports none; "Too small to use yet (under 1,000)" when tiny. A lookalike source needs at least 100 people in one country (Meta's rule); the form refuses smaller sources before sending.
> - Saved audiences are read-only and offered as **"Start from a saved audience"** in the targeting forms (their targeting fills the fields). Creating or deleting saved audiences and deleting custom audiences are out of scope (deleting would break ad sets using them; Ads Manager keeps that).
> - Special ad categories: lookalikes can't be picked there (Meta's rule); the picker says why.
> - Migration **048** (next free number when built). No bridge change (the MCP's audience tools stay unused; Graph covers this).

## Goal

Eugene, 2026-11-13: *"We currently are lacking implementations that have to do with campaign management … come up with a plan to create a structure here so we can do all these things"* (scope c: audiences).

1. **Ads → Audiences** lists every audience of the account: what it is ("People who visited your website in the last 30 days"), how big, whether it's ready, which ad sets use it (included or left out).
2. **New audience**: website visitors, people who engaged with the Page / Instagram / a lead form / a video, or **People like…** (a lookalike of one of them), in plain words with a size note.
3. In New ad set, New campaign and an ad set's Edit: **Include** and **Leave out** pickers next to places and ages.

## What exists today

| What | Where |
|---|---|
| Ad set targeting summary and fingerprint (custom audiences already in the audience keys) | `backend/sync.py:15-41`, `backend/status_history.py:95-124` |
| New ad set: targeting from a template, Advantage+ audience, hints | `backend/adset_build.py:40-102`, `backend/adsets_api.py:27-63` |
| AM-C: ad set Edit form and its targeting write | `AM-C-edit.md` |
| Lead forms list (the engagement source "lead form") | `backend/forms_api.py`, `frontend/forms.html` |
| Dataset / Pixel id per account (`meta_dataset_id`) and its health | `backend/tracking_api.py:23-74`, Settings → Meta |
| Ads section tabs (Ads · Lead forms) | `frontend/js/ui.js` `SUBNAV` |
| Cached Meta reads | `backend/insights_api.py` `cached`, table `meta_cache` |

## Data / migration: `backend/migrations/048_audiences.sql` (one file, written in one go)

```sql
-- AM-D: the account's audiences (custom, lookalike, saved), as last read from Meta, and where ad sets use them.
CREATE TABLE audiences (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    id TEXT NOT NULL,                         -- Meta's id (digits)
    kind TEXT NOT NULL CHECK (kind IN ('custom', 'lookalike', 'saved')),
    subtype TEXT,                             -- WEBSITE, ENGAGEMENT, LOOKALIKE, CUSTOM (customer list: listed, never made here) …
    name TEXT NOT NULL,
    description TEXT,                         -- plain words the console wrote when it made it, else Meta's (<= 300)
    size_lower BIGINT, size_upper BIGINT,     -- NULL = Meta reports none yet
    ready TEXT,                               -- 'ready' | 'filling' | 'too_small' | 'problem'
    status_words TEXT,                        -- Meta's delivery / operation status in plain words (<= 200)
    retention_days INTEGER,
    source_id TEXT,                           -- lookalike: the audience it is like
    lookalike JSONB,                          -- {country, ratio}
    targeting JSONB,                          -- saved audiences: whitelisted targeting (edit_rules.TARGETING_KEYS)
    made_here BOOLEAN NOT NULL DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    time_created TIMESTAMPTZ,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gone_at TIMESTAMPTZ,                      -- not listed by a complete read any more
    PRIMARY KEY (account_id, id)
);
ALTER TABLE audiences ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON audiences
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- Where used: filled by the sync from each ad set's targeting.
ALTER TABLE adsets ADD COLUMN audience_ids TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE adsets ADD COLUMN excluded_audience_ids TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX adsets_audiences ON adsets USING GIN (audience_ids);
CREATE INDEX adsets_excluded_audiences ON adsets USING GIN (excluded_audience_ids);
```

- `sync.upsert_adset` fills both arrays from `targeting.custom_audiences` / `excluded_custom_audiences` (full reads only, `_KEEP` rule).
- Audiences are read: on opening Ads → Audiences (at most every 5 minutes per account, through `insights_api.cached`), after any create, and once a day by the worker (`jobs.slow`), with `listing` + the `if seen:` guard before marking any `gone_at`.

## Backend

### Pure logic (TDD first), new `backend/audience_rules.py`

```python
RETENTION_MAX = {"website": 180, "page": 365, "instagram": 365, "lead_form": 90, "video": 365}   # days (verify)
LOOKALIKE_RATIOS = (0.01, 0.02, 0.03, 0.05, 0.10)          # 1 % … 10 %
MIN_SOURCE = 100                                            # people in one country (Meta's rule)
WEBSITE_WHO = ("all_visitors", "visited_url", "lead_event")
PAGE_WHO = ("page_engaged", "page_visited", "page_messaged", "page_cta_clicked")                  # (verify event names)
IG_WHO = ("ig_business_profile_all", "ig_business_profile_visit", "ig_user_messaged_business")    # (verify)
FORM_WHO = ("lead_generation_opened", "lead_generation_submitted", "lead_generation_dropoff")     # (verify)
VIDEO_WHO = ("video_watched", "video_completed", "video_view_25_percent", "video_view_50_percent",
             "video_view_75_percent")                                                             # (verify)

def problems(kind, spec, known) -> list[(field, message)]
    # name; retention 1..RETENTION_MAX; the source exists in `known` (this account's Page / IG account / forms /
    # videos / pixel, read by the route); a URL rule only with an http(s) URL fragment of 3..200 chars;
    # lookalike: a source audience of this account, ready, size_lower >= MIN_SOURCE, country one of the account's
    # targeting countries, ratio in LOOKALIKE_RATIOS; never a customer-list subtype as a lookalike source
    # unless Meta already holds it (we read, never upload)

def create_params(kind, spec) -> dict
    # the act_<id>/customaudiences body (verify field names against the Custom Audiences reference):
    # website:  {name, subtype: "WEBSITE", retention_days, prefill: true,
    #            rule: {"inclusions": {"operator": "or", "rules": [{"event_sources": [{"id": pixel, "type": "pixel"}],
    #                    "retention_seconds": days*86400, "filter": {...url contains | event = Lead...}}]}}}
    # page / instagram / lead_form / video: {name, subtype: "ENGAGEMENT", prefill: true,
    #            rule: {"inclusions": {"operator": "or", "rules": [{"event_sources": [{"id": src, "type": "page" | "ig_business"
    #                    | "lead" | "video"}], "retention_seconds": …, "filter": {"operator": "and", "filters":
    #                    [{"field": "event", "operator": "eq", "value": <who>}]}}]}}}
    # lookalike: {name, subtype: "LOOKALIKE", origin_audience_id, lookalike_spec: {"type": "similarity", "country", "ratio"}}

def describe(row) -> str         # "People who visited your website in the last 30 days" / "People like “Lead form openers” (1 %, US)"
def readiness(row) -> (ready, words)   # sizes and Meta's status codes -> ready / filling / too_small / problem
def where_used(audience_id, adsets) -> {"include": [...], "exclude": [...]}   # names + status, deleted ad sets left out
def targeting_with(targeting, include_ids, exclude_ids) -> dict   # sets custom_audiences / excluded_custom_audiences;
    # with Advantage+ audience on, included audiences are suggestions (Meta) -> the form's words say so (verify)
def picker_refusal(campaign, audience) -> str | None   # lookalike in a special-ad-category campaign; a 'problem' audience
```

### Routes (new `backend/audiences_api.py`)

| Route | Owner | Account admin | Teammate | Client |
|---|---|---|---|---|
| `GET /api/audiences` (custom + lookalike + saved, `describe`, size, `ready`, where used, `synced_at`) | yes | yes | yes, read only (where used limited to their campaigns' ad sets) | 403 |
| `GET /api/audiences/<id>` | yes | yes | yes | 403 |
| `GET /api/audiences/sources` (this account's Page, Instagram account, lead forms, recent videos, pixel; read from Meta, cached) | yes | yes | 403 | 403 |
| `POST /api/audiences/check {kind, spec}` | yes | yes | 403 | 403 |
| `POST /api/audiences {kind, spec, client_key}` (create) | yes | yes | 403 | 403 |
| `POST /api/audiences/refresh` (read Meta now, once a minute) | yes | yes | 403 | 403 |

- Create: `problems` → 400 with `field`; same `client_key` twice → the same audience; `meta_client.post(f"act_{acc}/customaudiences", data=create_params(...))`; store the row (`made_here`, `created_by`, `description = describe`); `ads_api.record(user, "account", {...}, "audience_create", None, name, ok)` so it is in History / activity. An unanswered create is looked up by exact name created in the last 10 minutes before trying again (`campaign_build.adoptable` pattern).
- Meta refusals in plain words: Custom Audience terms not accepted → "Accept Meta's Custom Audience terms for this ad account first (Business settings → Ad accounts → … ), then try again"; no pixel → "This account has no Pixel set in Settings → Meta"; source too small → the MIN_SOURCE sentence.
- **Pickers**: `GET /api/adsets/new/options` and AM-C's `GET /api/edit/adset/<id>` add `audiences: [{id, name, kind, describe, size words, ready}]` (gone ones left out); `adsets_api.clean` / AM-C `changes` accept `include_audiences`, `exclude_audiences` (ids that exist in `audiences` for this account, at most 20 each) and `adset_build.targeting` / `audience_rules.targeting_with` put them in the targeting. A picked id not in this account's table → 400 "That audience isn't in this account" (never sent to Meta).
- **Saved audiences**: `GET /api/audiences?kind=saved` and in the builders **Start from a saved audience** → its targeting fills places, ages, genders, languages and hints (through `adset_build.spec_from`), nothing is sent until Create / Save.

## UI

Classes `aud-`; new page `audiences.html` + `js/audiences.js` (no ad-blocker words: the file and ids use `aud`). Ads section tabs become **Ads · Lead forms · Audiences** (`SUBNAV`), palette entries "Audiences", "New audience". Plain words; phones as cards; 44 px; 16 px fields; nothing past 320 px.

- **Audiences page**: a table (desktop) / cards (phone): name, what it is (`describe`), size ("12,000–15,000 people", "Still filling", "Too small to use yet"), status pill (Ready / Filling / Problem), kind (Website / Engagement / Lookalike / Saved / Customer list, the last listed only), where used ("In 2 ad sets · left out of 1", each linking through `ui.entityLink`), made in the console or Meta. Filters: kind, Ready only. **Refresh** with the source line ("Read from Meta 9:42 AM"). Teammates: no New, no actions.
- **New audience** (owner, account admins): a dialog in three steps (the builder stepper):
  1. **Who**: Website visitors · People who engaged with your Facebook Page · … your Instagram account · … opened or sent a lead form · … watched a video · **People like an audience you have** (lookalike).
  2. **Details** for that choice: website (all visitors / visited a page whose address contains … / sent a lead), how many days back (slider, max per kind); Page / Instagram (which engagement); lead form (pick the form; opened / sent / opened but didn't send); video (pick from recent videos; how much they watched); lookalike (the source audience, country, how close: 1 % "most like them" … 10 % "broader", with the size estimate in words).
  3. **Name and check**: a name prefilled from `describe`; the summary; **Make the audience**. After: "Made. Meta fills it over the next few hours."
- **Pickers** in New ad set, New campaign (ad set step) and the AM-C Edit "Who it reaches" section: two rows **Include people in** and **Leave out people in**, each a searchable list of chips (name + size words), at most 20; a not-ready audience shows "Still filling"; a lookalike in a special-category campaign is disabled with the reason; with Advantage+ audience on: "With Advantage+ audience, Meta treats these as suggestions; people you leave out stay out" *(verify)*. **Start from a saved audience** above places.
- Teammates see the Audiences page read-only; clients don't see the tab.

## Money and security rules

- No money moves by making an audience. Picking audiences in a live ad set is an AM-C targeting change: read fresh, `seen` echo, review with the learning note, History, D2 explained as the console's, D3 check.
- **No PII**: no customer-list upload route exists; customer-list audiences Meta already has are listed by name and size only and can be used, never created or changed.
- Only this account's audiences can be picked (checked against `audiences` under RLS before anything reaches Meta).
- Audience names and Meta status text are plain text (`esc`), cut to 200/300 chars.
- Roles: create and pick for owner and account admins; teammates read; clients nothing.

## Fake Meta additions (`dev/fake_meta.py`)

- `GET act_<id>/customaudiences` (fields `id,name,subtype,approximate_count_lower_bound,approximate_count_upper_bound,delivery_status,operation_status,retention_days,lookalike_spec,rule,time_created`): three seeded audiences (website 30 days "ready" 12k–15k, lead form openers 90 days "ready" 1.2k–1.5k, a customer list "ready" 800–1k) and nothing for the second account until made.
- `POST act_<id>/customaudiences`: validates the body shape `audience_rules.create_params` produces (subtype, rule JSON parses, `event_sources` type and id known to the fake, retention within the maxima, lookalike source exists in the account and has ≥ 100 people) and refuses otherwise with code 100 and a plain message; new audiences start "filling" (no size) and become ready after `/fake/_audiences?fill=<id>`; `/fake/_audiences?tos=0` makes the next create fail with the terms error (fake code 2654); `?silent=1` drops the answer once (adoption).
- `GET act_<id>/saved_audiences`: one saved audience ("SoCal owners 30–60", targeting with Riverside + 25 mi).
- `GET <page>/videos` (or `act_/advideos`) for the video source list; `GET act_<id>/adspixels` for the pixel.
- Ad set targeting accepts and returns `custom_audiences` / `excluded_custom_audiences`.

## Tests

### Unit: `backend/tests/test_audience_rules_logic.py` (write first)

| Case | Expected |
|---|---|
| `create_params("website", 30 days, all visitors)` | subtype WEBSITE, pixel event source, `retention_seconds == 2592000`, `prefill` true |
| `create_params("lead_form", form, submitted, 90)` | ENGAGEMENT, event source type `lead`, filter value `lead_generation_submitted` |
| `create_params("lookalike", source, US, 0.01)` | LOOKALIKE, `origin_audience_id`, spec `{type: similarity, country: US, ratio: 0.01}` |
| `problems` website 181 days / lead form 91 days / unknown form id / URL fragment "a" | one message each |
| … lookalike from a source of 80 people / from a filling source / ratio 0.07 / from another account's audience | one message each |
| `describe` each kind | the plain sentences above |
| `readiness` bounds None / 400–600 / 12k–15k / Meta error status | filling / too_small / ready / problem |
| `where_used` with a deleted ad set | left out |
| `targeting_with` include 2, exclude 1, keeping places and ages | only the two keys changed (fingerprint differs only by them) |
| `picker_refusal` lookalike + special category | sentence |

`backend/tests/test_audiences_routes.py`: client 403 on every route; teammate 403 on create / check / sources / refresh and 200 on the list with where-used limited to their campaigns; picking an id not in the account → 400 and no Meta call (`/fake/_hits`).

### `qa/flows.cjs` (new block "Audiences", ~16 checks)

1. Ads → **Audiences** tab: three audiences with sizes, statuses and "In 1 ad set" for the website audience (the fake's live ad set includes it).
2. New audience → Website visitors, 30 days → made; the fake holds a WEBSITE audience with the pixel; the list shows "Still filling".
3. Website, 200 days → the field error. **Refusal.**
4. Lead form openers who didn't send, 30 days → made with the right event.
5. Lookalike from the filling audience → refused "still filling"; `/fake/_audiences?fill=` → 1 % US → made. Lookalike from the 800-person customer list → allowed (≥ 100); from a 60-person one → refused. **Refusal.**
6. Terms not accepted (`tos=0`) → the plain sentence with where to accept. **Refusal.**
7. New ad set: Include "Website visitors 30 days", Leave out "Lead form senders" → Create → the fake's targeting has both lists; the list page now says "In 2 ad sets · left out of 1".
8. AM-C Edit on the live ad set: add an exclusion → review "Leaves out people in “…”" + the learning note → saved; History line; no "Changed in Ads Manager" after `pull()`.
9. A crafted request with another account's audience id → 400, nothing sent. **Refusal.**
10. Special-category campaign: the lookalike chip disabled with the reason. **Refusal.**
11. **Start from a saved audience** fills Riverside + 25 mi and ages 30–60; nothing created until Create.
12. Teammate: Audiences page read-only (no New), `POST /api/audiences` 403. **Refusal.**
13. Client: no tab; `GET /api/audiences` 403. **Refusal.**
14. An unanswered create (`silent=1`) then a retry → one audience, adopted.
15. Phone 390 and 320: cards, the three-step dialog, chips wrap, 44 px, 16 px fields.
16. Guard sweep (`aud-`, `audiences.js`, `audiences.html`), no console errors.

### `dev/qa_leaks.py`

Seed a marked `audiences` row per account and mark account 2's ad set `audience_ids`. `/api/audiences`, `/api/audiences/<other id>` (404), the builders' options and AM-C's edit read never show the other account's mark. RLS sweep covers `audiences`.

### Screenshots

`qa/shots.cjs`: Audiences list, the New audience dialog (each step), the pickers in New ad set and Edit; light/dark, desktop/390 px.

## Live checks owed (with Eugene's yes for each create)

1. The Custom Audience terms are accepted for Edge Bourne's ad account (`tos_accepted`), or where to accept them.
2. A website audience from the dataset 1821497329119793 (rule JSON accepted as built); its size after a few hours.
3. An engagement audience from the lead form (event names); one from the Page; one from a video.
4. A 1 % US lookalike of the lead-form audience; the minimum source size Meta enforces today.
5. With Advantage+ audience on, how Meta treats included and excluded custom audiences in the ad set (suggestion vs hard limit).
6. `saved_audiences` returns the account's saved audiences with their targeting.

## Out of scope

- Customer-list (PII) uploads, any hashing of contact data.
- Deleting or editing audiences; creating saved audiences.
- Audience overlap analysis (the `audience-overlap-analysis` skill on the Mac covers it).
- Value-based lookalikes, app / offline / catalog audiences.
