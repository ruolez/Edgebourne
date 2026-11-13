# FU-A · A second ad account: add it from Meta, keep it separate, see every account side by side

Unit key: `FU-A-second-account` · Asked by Eugene 2026-11-12 · Meta: **read-only** (`me/adaccounts`, business ad account lists, insights); the only new write is the console's own row and settings · Money: none moves. Each account keeps its own ceiling.

> **Architect resolutions (2026-11-12), applied below:**
> - "Separate + overview" (Eugene's answer): every Meta ad account is its own console account (the 7.1 accounts with row-level security and the switcher), plus one new page, **All accounts**, that puts the accounts side by side. Nothing is ever summed across currencies.
> - The picker lists what the **System User key the open account uses** can reach. Eugene was added to the other ad account **as a person**, so that key can't see it yet: the empty state explains the three Business Settings steps in plain words. The per-account own token (Settings → Meta connection) stays as the fallback.
> - Picking an ad account creates a new console account bound to it. **Owner only**, and the existing refusals stay: an ad account another account already holds (`settings_api.used_elsewhere`, account 1's built-in `config.META_DEFAULTS` included), a zero-decimal currency (`account_info.currency_problem`).
> - The other ad account's owner gets a **read-only client sign-in** through Team (7.2, unchanged). No new role.
> - Build order: FU-A, FU-B, FU-C, FU-D. FU-A adds **no migration** (accounts, settings and RLS already exist). Its overview reads the shared date range, so once FU-C lands it includes today with no change here.

## Goal

Eugene, 2026-11-12: *"My Meta Ads account has access to a campaign from another Meta user and I am managing their ads as well but I have no way to bring it into my dashboard... please make sure I can do it and have clear separation between ad campaigns and have a way to monitor and manage both."*

1. **Bring it in.** Settings → Accounts → **Add ad account** lists every ad account the console's Meta key reaches, with its name, id, currency, status and whether another console account already uses it. One tap makes a console account for it, already connected.
2. **When it isn't listed,** the page says why in plain words and lists the three steps that make it appear, then **Look again**.
3. **Clear separation.** Each ad account is its own console account: its own leads, ads, results, Claude conversations, alerts, settings and money ceiling, kept apart by the database (RLS). The switcher and the page header always name the account in view.
4. **Monitor both.** A new **All accounts** page shows each account in one row: spent, leads, cost per lead, ads delivering and what needs him. All rows use the same dates, and each row opens that account.
5. **Their owner can look.** Eugene invites the other business's owner from Team as a **Client** (read-only) of that account. This exists already and only needs to be mentioned in the right place.

Non-goals: no merged "all accounts" Ads manager or Leads list, no cross-account budget moves, no automatic Business Settings requests (Meta has no API for "request access" from a personal grant), no change to how a person's own account is decided (`accounts_api.account_for`).

## What exists today

| What | Where |
|---|---|
| Accounts table, `app_account()`, RLS on every account-owned table | `backend/migrations/020_accounts.sql:4-43` |
| Which account a request works on (owner: cookie `ebads_account`; others: their own; closed → 403) | `backend/accounts_api.py:34-81` |
| Create an account by name only (copies schedules and the first reply template, switches to it) | `backend/accounts_api.py:125-143` |
| Rename / close / reopen, list all (owner) | `backend/accounts_api.py:146-185` |
| Switch (owner), list (owner: all; others: their own) | `backend/accounts_api.py:116-122`, `188-194` |
| Per-account settings keys (`key@<id>`), the Meta token inherited from account 1 | `backend/settings_store.py:21-41`, `60-66` |
| Who holds a Page / ad account / dataset (account 1's built-in defaults included) | `backend/settings_store.py:89-96`, `config.py:55-59` |
| Refusals: asset used elsewhere, borrowed connection changed by a non-owner, zero-decimal currency | `backend/settings_api.py:121-151`, `154-184`; `backend/account_info.py:13`, `53-59` |
| Highest daily budget per account (`max_daily_budget_cents`, default $100) | `backend/money_rules.py:11`, `89-95`; `backend/settings_api.py:328-356` |
| Switcher in the rail / phone sheet, "+ Add an account…" asks for a name only | `frontend/js/ui.js:354-391` |
| `?acct=<id>` on any link opens that account for the owner | `frontend/js/ui.js:595-603` |
| Settings → Accounts panel (rename, close) | `frontend/settings.html:225-228`, `frontend/js/settings.js:456-462`, `538-560` |
| Read-only client sign-ins, Team invite with role `client` | `backend/team_api.py:15`, `61-86`; `accounts_api.CLIENT_MAY` `:106` |
| Fake Meta: one hard-coded ad account `act_1025971549903293` | `dev/fake_meta.py:15`, `611-633` |
| Leak test: account 2 "Burdanova QA", every GET as admin / switched admin / client | `dev/qa_leaks.py:1-110` |

What's missing: nothing lists the ad accounts the key reaches, and adding an account means typing a name, opening its Meta connection and pasting an id by hand. There's no way to see two accounts' figures together, and the fake models only one ad account.

## Data / migration

**No migration.** Everything needed is already per account.

- Settings written on create, under the new account's id (`settings_store.set(key, value, account_id=new)`): `meta_ad_account_id` (digits only, no `act_`), and `meta_business_id` when Meta returned the ad account's `business.id`. Nothing else is copied: the System User token is **inherited** from account 1 (`settings_store.INHERITED`), so the account starts on the owner's connection. Its Page and dataset stay empty until set in its Meta connection.
- New per-account settings key (add to `settings_store.ACCOUNT_KEYS`): none. The picker's result is cached in `meta_cache` under key `adaccounts:reachable` (account-scoped by RLS, TTL 60 s), so it never crosses accounts.
- `max_daily_budget_cents` stays per account and starts at the default `MAX_DAILY_DEFAULT` ($100/day) for the new account. That's by design: the new account doesn't inherit Edge Bourne's ceiling. The create dialog says so.

Leak test (`dev/qa_leaks.py`): no new table. The new GET routes are added to its route walk (below), and **All accounts** is checked as each role.

## Backend

### Pure logic: new `backend/adaccounts.py` (no DB, no Meta; unit-tested)

```python
STATUS_WORDS = {1: "Active", 2: "Disabled", 3: "Payment problem", 7: "Under review by Meta", 8: "Payment due",
                9: "Grace period", 100: "Closing", 101: "Closed", 201: "Active", 202: "Closed"}
USABLE = {1, 3, 7, 8, 9, 201}   # Meta can still report on these; 2/100/101/202 can't be run from the console

def act_digits(value) -> str | None
    # "act_123" / "123" / " act_123 " -> "123"; anything with a non-digit -> None

def merge(sources: dict[str, list[dict]]) -> list[dict]
    # {"assigned": me/adaccounts rows, "owned": business owned rows, "client": business client rows}
    # -> one entry per ad account id: {id, name, currency, status, status_words, timezone, business_name,
    #    via: ["assigned", "client", ...]} ; same id from two lists merges `via`; sorted by name (case-insensitive)

def mark_used(items: list[dict], holders: list[tuple[int, bool, str]], names: dict[int, str]) -> list[dict]
    # holders = settings_store.meta_holders("meta_ad_account_id"); adds used_by {account_id, name, closed} or None

def blocked(item: dict, currency_problem) -> str | None
    # why it can't be added, in plain words, or None:
    #   used_by (open)   -> "Already in the console as <name>."
    #   used_by (closed) -> "<name> (a closed account) still holds it: reopen that account instead."
    #   currency_problem -> account_info.currency_problem(currency)
    #   status not usable -> "Meta says this ad account is <status words>."

def default_name(item: dict) -> str
    # the console account's suggested name: Meta's ad account name, trimmed to 120, or "Ad account <last 4>"
```

### DB / Meta part: `backend/accounts_api.py` (extended)

```python
FIELDS = "account_id,name,currency,account_status,timezone_name,business{id,name}"

def reachable(force=False) -> dict
    # Read with the token the OPEN account uses (meta_client.system_token(): its own or account 1's inherited one).
    # 1. me/adaccounts (paged, limit 100)                       -> "assigned"
    # 2. if settings_store.get("meta_business_id"): <biz>/owned_ad_accounts and <biz>/client_ad_accounts -> "owned", "client"
    #    (a refusal of 2. is recorded as `partial`, never fatal: the System User may lack business_management)
    # Reads go through meta_client.read_many (parallel, one deadline); cached 60 s in meta_cache "adaccounts:reachable".
    # Returns {items: mark_used(merge(...)) with `blocked` filled, partial: [list names], token: "own"|"owner", read_at}
```

Routes (blueprint `/api/accounts`):

| Route | Owner | Account admin | Teammate | Client | What |
|---|---|---|---|---|---|
| `GET /api/accounts/reachable?fresh=1` | yes | 403 | 403 | 403 | `reachable(force=fresh)`. A MetaError → 400 with its plain words (`meta_client.plain`). `fresh=1` is throttled to once per 10 s per account. |
| `POST /api/accounts/from-meta {ad_account_id, name}` | yes | 403 | 403 | 403 | Creates the console account. See below. |
| `GET /api/accounts/overview?range=&start=&end=` | every account | own account | own account, own campaigns | own account | All accounts rows (below) |
| existing `POST /api/accounts` (name only) | unchanged | | | | Stays: an account without Meta yet (a client still sorting access) |

All the 403s use `owner_required` (`auth.py:84-94`). Clients are also stopped earlier for any write (`accounts_api.choose_for_request`, `CLIENT_MAY`).

`POST /api/accounts/from-meta`, step by step:
1. `digits = adaccounts.act_digits(body.ad_account_id)`; missing → 400 field `ad_account_id` "Pick an ad account from the list".
2. **Read the list again now, with `force=True`**, never trusting the browser: the id must be in `items`, else 404 "This ad account isn't reachable with the console's Meta key any more. Look again." (An owner can't bind an id their key can't read.)
3. `blocked(item)` → 409 with that sentence, field `ad_account_id`. This covers `used_elsewhere` (account 1's built-in id included, through `meta_holders`), a closed holder, a zero-decimal currency and a disabled or closed ad account.
4. `name` = trimmed body name or `default_name(item)`; `name_taken` → 409 field `name` (existing rule).
5. One transaction under `account_ctx.all_accounts()`: insert into `accounts`, copy schedules and the first reply template exactly as `create()` does (factor that copy into `_seed_new_account(new_id, name)`, shared by both routes), then `settings.meta_ad_account_id@<new>` and `meta_business_id@<new>`. The `used_elsewhere` check is re-run inside the transaction under advisory lock `adaccount:<digits>`, so two tabs can't bind the same id.
6. `log_activity("account.created", subject=str(new), details={"name", "ad_account_id", "via"})` in the **new** account and `account.added_from_meta` in the current one.
7. Answer 201 `{id, name, ad_account_id}` with the switch cookie set (`_with_choice`, as `create()` does). The worker's next pass syncs it: `sync_account` reads its time zone and currency, then the backfill.

`GET /api/accounts/overview` returns one row per account the person can see:

```json
{"range": {"key": "7", "start": "...", "end": "...", "label": "Nov 5 – Nov 11"},
 "rows": [{"id": 1, "name": "Edge Bourne", "currency": "USD", "connected": true,
           "spend_cents": 14012, "leads": 9, "received": 8, "cpl_cents": 1557,
           "delivering": 4, "needs_you": 2, "suggestions": 1,
           "cap": {"limit_cents": 15000, "spent_cents": 11240},       // admins only, else null
           "synced_at": "...", "behind": false}],
 "same_currency": true, "totals": {"spend_cents": ..., "leads": ..., "cpl_cents": ...}}   // totals only when same_currency
```

- The account list: owner → `active_accounts()`; everyone else → only `account_ctx.current()`. Each row is computed inside `with account_ctx.use(acct), db.reusing():`, so RLS scopes every query to that row's account. Scoping is still checked per account: a teammate's row counts only their `visible_campaign_ids`.
- Figures: the same SQL as `performance_api.overview_data` totals (refactor its totals query into `performance_api.window_totals(user, start, end, campaign_id=None)` and call it here). `received` = `lead_quality.counted()`. `cpl_cents` is `None` under 1 lead. `delivering` = ads with `effective_status = 'ACTIVE'`. `needs_you` = `inbox.counts(inbox.items_for(user))["need"]` (the same count as the badge and Today). `suggestions` (admins) = pending `desk_proposals`.
- The range is the shared range (`performance_api.window_args`); each account's own day boundary comes from that account's time zone (`account_info.today()` inside the `use` block). So the label says "each account's own days" when zones differ.
- Costs Meta nothing: stored data only.

### Settings payload

`GET /api/settings` gains `account.ad_account_id` and `account.via` (how it was added: `"picker"` or `"typed"`). Nothing else changes.

### Desk

No change. Every account already has its own Desk line (`desk_tasks.account_id`), and the bridge passes the account (`DESK_ACCOUNT`).

## UI

Words are plain throughout. Classes use the prefixes `acp-` (account picker) and `ovw-` (overview), which are free of ad-blocker words. Phones get 44 px targets, 16 px fields and nothing past the edge at 320 px.

### Settings → Accounts (owner)

The panel (`#accounts-panel`) gets a primary button **Add ad account** above the list. The list itself (rename, close, reopen) stays, and each row now also shows its ad account (`act_…` · currency) or "Not connected to Meta yet".

**Add ad account** opens a dialog (`confirmDialog` with a custom body, id `acp`):

- Title "Add an ad account". Lede: "Ad accounts the console's Meta key can reach. Each one becomes its own account here, with its own leads, ads, results, Claude and settings."
- While loading, a skeleton of 3 rows. On error, the plain Meta error with **Try again**.
- One row per ad account (`li.acp-row`), checkable as a radio:
  `Masha Fontana Studio` · `act_2223334445556667` · `USD` · status pill (`Active` ok, `Payment problem` warn, `Disabled` bad) · `via` in muted text ("shared with your Business", "your Business", "assigned to the console").
  A blocked row is greyed and not pickable, and its reason shows under the name ("Already in the console as Edge Bourne.").
- Name field (label "Name in the console", 16 px), filled with Meta's name when a row is picked. Hint: "Usually the business it advertises."
- A note under it: "It starts with a highest daily budget of $100. Change it in its Settings → Targets."
- Buttons: **Add this account** (primary, disabled until a usable row is picked) · Cancel · a quiet **Look again** link (`fresh=1`).
- After adding: toast "Masha Fontana Studio added. Its results arrive within a few minutes.", then the page reloads into the new account at `settings.html#meta`. The Meta connection section shows the ad account filled, the Page empty, and the line "Next: pick its Page, so its leads arrive."

**Empty or missing** (no rows, or every row blocked). This box (`#acp-help`) is also always reachable as the fold "Can't see the one you want?":

> **Can't see the ad account?** You were added to it as a person, so the console's Meta key can't see it yet. Three steps make it appear:
> 1. In Meta **Business Settings**, open **Accounts → Ad accounts**, press **Add**, then **Request access to an ad account**, and type its ID (the number after `act_`, from Ads Manager's account menu).
> 2. Its owner approves the request. Meta tells them in their Business Settings and by notification.
> 3. Back in **Business Settings → Ad accounts**, pick that ad account, press **Assign people**, choose **System users → {system user name}**, and turn on **Manage campaigns**. Then press **Look again** here.
>
> Another way: paste that ad account's own System User token in its Meta connection after adding it by name (**Add without Meta for now**).

`{system user name}` comes from `meta_client.get("me", fields="name")` (already read by **Test connection**, `settings_api.py:404-422`). **Add without Meta for now** opens the existing name-only add (`ui.js addAccount`).

`partial` (the business lists were refused): one muted line, "Your Business's own list couldn't be read (the key needs Business management). Showing the accounts assigned to the console only."

### All accounts (`accounts.html`, `js/overview.js`)

- **Where to find it:** the owner's account switcher (rail and phone sheet) gets **All accounts** as its first option, above the account names. ⌘K: "All accounts" (aliases "overview", "both accounts"). Settings → Accounts links it. Breadcrumb: "All accounts". It's shown only when `me.accounts.length > 1`.
- **Header:** "All accounts" + the shared date range picker (`format.rangeSelect`, `sharedRange()` / `rememberRange`). When the accounts' time zones differ: "Each account uses its own days."
- **Desktop table** (`table.ovw-table`, one Tab stop, ↑↓ rows, Enter opens): Account · Spent · Leads · Cost per lead · Delivering · Needs you · Spending limit (admins). Leads shows "Meta 9 · Received 8" through `ui.pairNote`. A dash means "nothing yet". An unconnected account's row says "Not connected to Meta yet · Connect", linking to `/settings.html?acct=<id>#meta`. The total row shows only when every row shares one currency; otherwise it says "Totals aren't added up: the accounts use different currencies."
- **Phone** (≤ 640 px): one card per account (`.ovw-card`): the name on its own line (the 9.6 rule: at least 80 px wide, at most two lines), then Spent / Leads / Cost per lead as a three-up figure row, and "4 delivering · 2 need you" under it. The whole card is the link (≥ 44 px).
- **Each row** links to `/home.html?acct=<id>` (ui.boot switches and opens Today). "Needs you" links to `/inbox.html?acct=<id>&box=need`.
- The source line (`ui.sourceNote`) is per row, folded under the row's name on desktop and at the card's foot on phones.

### Team

The invite form, when the role is **Client**, gets one sentence: "Clients see this account only (results, leads, reports) and can't change anything." This already holds (7.2); the sentence makes the other owner's sign-in obvious. No new role.

### Header

`ui.js` already shows the account name in the phone top bar (`top-acct`) when there's more than one account. On desktop, the breadcrumb starts with the account's name when there's more than one, so every page names its account. This is a small change in `setCrumbs`.

## Money and security rules

- **No Meta write.** `reachable` and `overview` are GETs on Meta and the database. `from-meta` writes only console rows and settings.
- **Owner only** for the picker and binding. An account admin can't widen their reach: their own account's key is the owner's, and `borrowed_connection_change` (`settings_api.py:145-151`) still stops them pointing it elsewhere.
- **The id is re-checked on the server** against a fresh read of the key's reach, under an advisory lock. Every existing refusal applies: used elsewhere (incl. the built-in default), closed holder, currency.
- **Ceilings stay per account.** A new account starts at the $100/day default, never Edge Bourne's. FU-B's spending-limit changes act only on the open account's own ad account.
- **Separation is the database's job.** The overview computes each row inside `account_ctx.use(acct)`. A non-owner gets only their own account (one row). The leak test proves a client of account 2 sees only account 2.
- Tokens never reach the browser (the picker returns ids, names, currency and status only).

## Fake Meta (`dev/fake_meta.py`)

- `OTHER_ACCOUNTS`: `{"2223334445556667": {"name": "Masha Fontana Studio", "currency": "USD", "timezone_name": "America/Chicago", "account_status": 1, "business": {"id": "3334445556667778", "name": "Masha Braverman"}}, "4445556667778889": {"name": "Tokyo Test KK", "currency": "JPY", "account_status": 1}, "5556667778889990": {"name": "Old Shop", "currency": "USD", "account_status": 101}}`.
- `GET me/adaccounts` → the real account plus `2223334445556667` and `4445556667778889` (fields as asked, `account_id` without `act_`, `id` with it). `GET <BUSINESS>/owned_ad_accounts` → the real account. `GET <BUSINESS>/client_ad_accounts` → `5556667778889990`.
- `GET /fake/_adaccounts?hide=<id>` hides one from every list (`?clear=1` resets), to drive the empty state. `GET /fake/_adaccounts?refuse_business=1` makes both business lists answer code 200 "permission" (the `partial` path).
- `act_2223334445556667` reads: its own object (with `spend_cap` "0" and `amount_spent` "0"), one campaign "Masha - Extensions - Leads", one ad set, two ads, and 10 days of `insights` rows per ad (spend/leads different from Edge Bourne's). Implementation: an `ACCOUNT_DATA[id]` dict that the existing `act` branches read through `acct_of(parts[0])`, replacing the hard-coded `act = f"act_{ACCOUNT}"` comparisons. The real account stays the default and keeps its current shape.

## Tests

### Unit: `backend/tests/test_adaccounts_logic.py` (TDD: write first, see it fail)

| Function | Input | Expected |
|---|---|---|
| `act_digits` | `"act_2223"`, `" 2223 "`, `"act_22x3"`, `None` | `"2223"`, `"2223"`, `None`, `None` |
| `merge` | assigned `[A, B]`, owned `[A]`, client `[C]` | three items sorted by name, A has `via == ["assigned", "owned"]` |
| `merge` | the same id twice in one list | one item |
| `mark_used` | holders `[(1, False, "1025…"), (3, True, "5556…")]` | the 1025 item `used_by == {account_id: 1, name: "Edge Bourne", closed: False}`, the 5556 item closed True, others None |
| `blocked` | used by an open account | `"Already in the console as Edge Bourne."` |
| `blocked` | used by a closed account | sentence naming it and "reopen that account instead" |
| `blocked` | currency `JPY` | the `currency_problem` sentence (passed in, so the test gives the real `account_info.currency_problem`) |
| `blocked` | status 101 | `"Meta says this ad account is Closed."` |
| `blocked` | status 3, USD, unused | `None` (a payment problem can still be run; its pill warns) |
| `default_name` | name `""`, id `"2223334445556667"` | `"Ad account 6667"` |

Extend `test_accounts_logic.py`: overview rows for one account in a different currency → `same_currency` False and no `totals` (pure helper `overview_totals(rows)`). Totals over two USD rows → spend summed, `cpl_cents` = total spend / total leads (not an average of averages).

### `dev/qa_leaks.py`

- Add `GET /api/accounts/reachable` (owner 200; switched owner 200, read with account 2's key; account 2's admin and client 403) and `GET /api/accounts/overview` to the walk.
- **The overview as account 2's client** returns exactly one row with id = account 2, and no figure or name of account 1 appears anywhere in the body (the marks check). As the owner it returns both rows, each row's `name` matching its id.
- `POST /api/accounts/from-meta` as account 2's admin → 403. As the owner with account 1's ad account id → 409 and no new row in `accounts`.

### `qa/flows.cjs` (new block "Second ad account", after the Accounts checks; about 16 checks)

1. Settings → Accounts as owner: `#acp-open` opens the dialog. `.acp-row` count is 4: Edge Bourne, Masha Fontana Studio and Tokyo Test KK from the fake's assigned list, plus Old Shop from the business's client list.
2. The Edge Bourne row is not pickable and reads "Already in the console as Edge Bourne".
3. The Tokyo Test KK row is not pickable and names JPY ("without cents").
4. The Old Shop row is not pickable and reads "Closed".
5. Picking Masha fills the name field with "Masha Fontana Studio". **Add this account** creates it, and the page lands on `settings.html#meta` in the new account with `#meta_ad_account_id` = `2223334445556667`.
6. **Refusal, the browser lies:** `fetch('/api/accounts/from-meta', {ad_account_id: '1025971549903293'})` → 409, and `GET /api/accounts/all` count unchanged.
7. **Refusal, not reachable:** `from-meta` with `9999999999` → 404 "isn't reachable".
8. **Refusal, twice:** a second `from-meta` for Masha → 409 "Already in the console as Masha Fontana Studio".
9. After `POST /api/performance/sync` in the new account, Results shows Masha's campaign and not "Free intro call" (separation on screen). Switching back shows Edge Bourne's and not Masha's.
10. All accounts (`/accounts.html`): two rows (`tr.ovw-row`), each name present, each Spent equals that account's Results total for the same range (read through `/api/performance?range=7` in each account and compared).
11. A row opens `/home.html` in that account (the switcher reads its name).
12. Changing the range on All accounts changes `sharedRange` (Ads opens on it).
13. Empty state: `/fake/_adaccounts?hide=2223334445556667` + `hide=4445556667778889` + `hide=5556667778889990`, then **Look again** → `#acp-help` is visible with "Request access to an ad account" and the System User's name. Then clear.
14. `partial`: `/fake/_adaccounts?refuse_business=1` → the line "Your Business's own list couldn't be read" and Old Shop missing. Then clear.
15. Account admin of account 1 (existing QA user): `#acp-open` absent, `GET /api/accounts/reachable` 403, the All accounts entry absent from the switcher and ⌘K.
16. Client of the new account (invite via Team as Client, sign in in a second context): All accounts shows one card only, with no spending limit column. The switcher shows the name only.
17. Phone 390 and 320: the dialog rows wrap without overflow (`scrollWidth <= clientWidth`). Each `.ovw-card` is ≥ 44 px tall, its name ≥ 80 px wide and ≤ 2 lines. The name field's computed font-size is 16 px.
18. Ad-blocker guard sweep passes (`acp-`, `ovw-`, `accounts.html`).

Cleanup at the end of the block: close the QA-made account (`PATCH archived`) and clear its `meta_ad_account_id@<id>`, so later runs can add it again. The leak test's "Burdanova QA" is untouched.

### Screenshots

`qa/shots.cjs`: add `accounts` and a step that opens the picker (`settings.html#accounts-panel` + click `#acp-open`). Check them light and dark, at desktop and 390 px.

## Live checks owed (with Eugene)

1. With the real System User token: `me/adaccounts` lists Edge Bourne's ad account. `client_ad_accounts` appears only after the request in step 1 is approved.
2. Whether the other user's ad account sits in a **Business** at all. "Request access to an ad account" works only for an ad account owned by a Business portfolio. If it's a personal ad account, its owner first moves it into a Business (or makes one), or the fallback is that Business's own System User token. *(Open question for Eugene.)*
3. After assigning it to the System User with **Manage campaigns**: the picker shows it, adding it syncs its first results, and the leads webhook for its Page works once the Page is also shared and subscribed (Settings → Meta connection → Start receiving leads).
4. The other owner signs in as a client and sees only their account.

## Out of scope

- A merged Ads manager, Leads list or Inbox across accounts (the overview links into each).
- Reading the other user's account with Eugene's **personal** login (no user tokens are stored).
- Picking the new account's Page and dataset from a list (they're typed in its Meta connection as today; a picker is a later step).
- Moving data between accounts, or merging two console accounts.
