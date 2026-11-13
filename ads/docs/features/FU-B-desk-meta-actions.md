# FU-B · Ask Claude for Meta changes in plain words: budgets, on/off and the account spending limit

Unit key: `FU-B-desk-meta-actions` · Asked by Eugene 2026-11-12 · Meta: **one new write**, the ad account's `spend_cap`, only after an Accept or the Settings confirmation · Money: **yes**. This is the account-wide ceiling on total spend.

> **Architect resolutions (2026-11-12), applied below:**
> - Agreed design: the Desk agent reads Meta freely and turns plain requests into **proposals**. Nothing changes on Meta until Eugene taps Accept. The **backend** (never the Mac) writes, through `money_rules`, and logs it in `meta_changes` (History), `activity`, and `reports/log.md` through the skill's existing log step.
> - New proposal kind **`spend_limit`** (the ad account's `act_<id>` `spend_cap`). The same control lives in Settings → This account → Targets, with the same confirmation.
> - **Units.** Meta's reference (checked 2026-11-12, Ad Account reference): the *read* field `spend_cap` is "Value specified in basic unit of the currency, for example 'cents' for USD". The *update* parameter `spend_cap` is a float, "Value specified in standard denomination of the currency, e.g. 23.50 for USD $23.50". So we **read cents and write dollars**. Both conversions live in `money_rules` and nowhere else. After every write we read back, and on any mismatch we put the previous value back, raise a bad alert and block further limit writes until an owner clears the block.
> - Refusals: a new limit **at or below the amount already spent** (Meta would stop every ad at once). **0 or no limit** needs a separate explicit confirmation. Only the **owner or this account's admin**; teammates and clients never. Never `spend_cap_action` (its `reset` zeroes `amount_spent`, its `delete` removes the limit without our confirmation).
> - Wording: `/ads-desk` (`bridge/skill/SKILL.md`) gets one mapping table so "raise campaign X to $30/day", "turn off N3" and "set my limit to $200" land as budget, status and spend-limit proposals in whichever account the conversation belongs to. Skill text only: desk **2.7**.
> - ~~No migration.~~ **Built (2026-11-13): migration `043_spend_limit_kind.sql`**, because `desk_proposals.kind` has a CHECK constraint (016) that refused the new kind; it only widens that check (no new table, no RLS change). A unit test now ties `desk_api.PROPOSAL_KINDS` to the newest constraint. The block flag is a per-account setting, and the alert uses the existing `alerts` table.

## Goal

Eugene, 2026-11-12: *"adjusting our Desk Agent to have ability and access to use Meta API on our account so I can ask it for things like 'increase my total spending limit to 200$'"*

1. He types "increase my total spending limit to $200" on the Claude page. Claude reads Meta, then answers with **one suggestion**: "Raise the account spending limit to $200". The suggestion shows what's spent so far and how long $200 lasts at the current pace.
2. **Accept** opens the usual sheet showing **$150 → $200**, "Spent so far: $112.40", and "At about $20 a day, the ads run about 4 more days (was 1)". One more tap and the console changes it on Meta, reads it back to check, and records it.
3. The same works for "raise campaign X to $30/day" (budget, through every existing budget rule) and "turn off N3" (on/off), for either account.
4. The same spending-limit change is in **Settings → Targets → Account spending limit**, with the same confirmation, for when he isn't talking to Claude.

## What exists today

| What | Where |
|---|---|
| Proposal kinds: budget, status, creative, targeting, experiment, tags, other | `backend/desk_api.py:40`, cleaning `909-946` |
| What Accept does per kind; budget words vs cents (`proposal_cents`) | `backend/ads_api.py:59-78`, `money_rules.py:29-69` |
| Fresh read for the sheet (`proposal_plan`), the multi-accept review | `backend/ads_api.py:1296-1377`, `desk_view.py:318-367` |
| Accept: claim `applying`, money checks, write, close, settle interrupted applies | `backend/ads_api.py:1393-1537` |
| Who may decide: clients blocked as writers (`CLIENT_MAY`); account-wide suggestions admins only | `accounts_api.py:78-81`, `ads_api.py:1404-1408` |
| Every Meta write in `meta_changes` + activity | `ads_api.py:212-226` |
| Spending limit **read**: `spend_cap` and `amount_spent` stored as cents in `account_snapshot` | `backend/insights.py:209-225` (comment: "Meta reports both in the account currency's minor units"), `performance_api.py:34-43` |
| Spending-limit alerts tell him to change it in Meta's billing settings | `backend/alerts.py:268-283`, wording in `performance_api.py:140-145` |
| Pace and "days until the limit" (`cap_days`) | `backend/pacing.py:17-35`, `performance_api.py:186-208` |
| Skill: "Raising the account spending limit is `other`: Eugene changes it himself" | `bridge/skill/SKILL.md:384-386` |
| Skill proposal format, budget and status rules | `bridge/skill/SKILL.md:136-162` |
| Accept sheet lines and groups | `frontend/js/decide.js:9-70` |
| Settings → Targets (highest daily budget, raise confirmation) | `frontend/settings.html:53-66`, `frontend/js/settings.js:436-536` |
| Fake Meta: `act_` read returns `spend_cap` "15000" (cents); account writes not modelled | `dev/fake_meta.py:630-633`, `925-947` |

## Data / migration

**Migration 043** widens `desk_proposals_kind_check` with `spend_limit` (see the note above); nothing else.

- New per-account settings keys (add to `settings_store.ACCOUNT_KEYS`):
  - `spend_limit_block`: JSON `{at, by_change_id, wanted_cents, got_cents, restored: true|false, restored_cents}` while writes are blocked. Absent = allowed.
  - `spend_limit_last_check`: ISO time of the last read-back (for the Settings line "Checked on Meta at 2:41 PM").
- `meta_changes` rows: `level = 'account'`, `entity_id = 'act_<id>'`, `entity_name` = the ad account's name, `action = 'spend_limit'` (and `'spend_limit_restore'` for the put-back), `old_value` / `new_value` = **cents** as text (`''` → no limit), `proposal_id` when it came from a suggestion. History's money marks already treat `spend_cap` as money (`marks.py:13`). The account-level timeline shows the line "Account spending limit $150 → $200 (by Eugene, from Claude's suggestion)".
- Alert rule `spend_limit_mismatch` (event, level `bad`, entity `account`, dedupe `spend_limit_mismatch:<change id>`), category `money` (`inbox.CATEGORY`), not snoozable (`snooze.WORSE` doesn't list it). It's resolved when an owner clears the block.

## Backend

### Pure logic (TDD), `backend/money_rules.py` (extended)

```python
LIMIT_MIN_HEADROOM = 1   # cents: a new limit must be above what's spent, by at least this

def spend_cap_cents(raw) -> int | None
    # Meta's READ value (minor units) -> cents. "15000" -> 15000; "0", "", None -> None (no limit).
    # A non-integer string ("150.00") -> raises ValueError (never guessed). Used by insights.sync_account too.

def spend_cap_param(cents, currency) -> str
    # Meta's WRITE value (standard denomination): 20000 -> "200.00"; 15050 -> "150.50"; None -> "0" (no limit).
    # Raises ValueError for a zero-decimal currency (account_info.ZERO_DECIMAL) or cents < 0 / not int.
    # THE ONLY place that turns cents into Meta's spend_cap write unit.

def spend_limit_change(old_cents, new_cents, spent_cents, rate_cents) -> dict
    # {from, to, spent, remove: new is None, left_now, left_after, days_now, days_after, rate}
    #   left_* = limit - spent (None without a limit); days_* = left // rate (None when rate <= 0 or no limit)

def spend_limit_problem(change, confirm_remove) -> str | None
    # the refusal in plain words, or None, in this order:
    #   to is not None and to < 100            -> "The new limit must be at least 1.00."
    #   to is not None and to <= spent        -> "That's at or below what's already spent (<spent>): Meta would stop every ad at once. Pick more than <spent>."
    #   remove and not confirm_remove          -> "Removing the limit needs its own confirmation."
    #   to == from                             -> "That's already the limit."

def readback_ok(intended_cents, raw_read) -> bool
    # spend_cap_cents(raw_read) == intended_cents (None == None for "no limit"); a read that can't be parsed -> False

def limit_words(text) -> int | None | str
    # The amount a spend_limit suggestion names: "$200" / "to $200" / "200 dollars" -> 20000;
    # "no limit" / "remove the limit" -> None; anything per day ("$200/day", "a day", "daily") -> "daily"
    # (refused as a spend limit: it reads as a budget); otherwise parse_budget_text's rules ("or", "?", two amounts -> nothing)
```

`insights.sync_account` (`insights.py:218`) switches to `money_rules.spend_cap_cents`, so the read conversion lives in one place too. That's a refactor with the same results; the existing test fixtures prove it.

### DB / Meta part: new `backend/spend_limit.py`

```python
FIELDS = "spend_cap,amount_spent,currency,name"
LOCK = "spend_limit:{account}"

def live() -> dict
    # one fresh read of act_<id>: {limit_cents, spent_cents, currency, name, rate_cents (pacing 7 complete days), blocked}
    # also refreshes account_snapshot's cap (the frame and alerts read it)

def plan(new_cents, remove=False) -> dict
    # live() + spend_limit_change + spend_limit_problem(confirm_remove=True) for the sheet (problem shown, remove flagged)

def apply(user, new_cents, *, remove, confirm_remove, from_cents, proposal_id=None) -> (ok: bool, error: str|None, result: dict)
    # 1. blocked?          -> NOT_SENT "Spending-limit changes are paused: on Nov 12 Meta stored a different amount than we sent.
    #                          The console's owner checks Ads Manager and clears it in Settings → Targets."
    # 2. advisory lock LOCK (try, no wait) -> NOT_SENT "Someone is changing the limit right now."
    # 3. live() read now;   from_cents != live limit -> 409 "The limit on Meta is <x> now. Check the amounts again." (+ new plan)
    # 4. spend_limit_problem(change, confirm_remove) -> NOT_SENT with it
    # 5. meta_client.post(f"act_{id}", spend_cap=money_rules.spend_cap_param(new, currency))   # never spend_cap_action
    #      MetaError -> record(ok=False); UNKNOWN prefix when exc.unknown (never retried blind)
    # 6. record(user, "account", row, "spend_limit", old, new, True, proposal_id=...)
    # 7. read back spend_cap (meta_client.get, fresh); readback_ok(new, raw)?
    #      yes -> store snapshot, settings spend_limit_last_check, return ok
    #      no  -> restore(old): post spend_cap_param(old), read back again, record "spend_limit_restore" (ok per its readback);
    #             set spend_limit_block {...}; raise alert spend_limit_mismatch (bad) with both amounts and whether the put-back held;
    #             return CHECKED "Meta stored <got> instead of <wanted>, so the console put back <old> and paused limit changes."
    #      a read-back that Meta doesn't answer -> treated as a mismatch we can't see: no restore write (we don't know what's there),
    #             block + alert "Couldn't read the limit back from Meta; check it in Ads Manager", return UNKNOWN

def unblock(user)   # owner only: clears spend_limit_block, resolves the alert, log_activity("spend_limit.unblocked")
```

`row` for `record` = `{"id": f"act_{id}", "name": <ad account name>, "campaign_id": None}`.

### Proposals

- `desk_api.PROPOSAL_KINDS` += `"spend_limit"`. `clean_proposal` for it: `entity_type = "account"`. `entity_id` must equal `act_<this account's meta_ad_account_id>`, otherwise the kind becomes `other` (a run can't aim at another account's limit). `payload` = `clean_spend_limit(raw)` → `{"proposed_cents": int}` or `{"remove": true}`. A missing or invalid payload → `other`.
- `ads_api.proposal_action`: `spend_limit` → `("spend_limit", cents|None)` when `money_rules.limit_words(proposed_value)` agrees with the payload (same rule as budgets: words and cents must agree). `"daily"` → `("unclear", "This reads as a daily budget, not the account spending limit. Decline it and ask again.")`. Disagreement → `("unclear", "Claude's amount isn't what its words say …")`.
- `ads_api.proposal_plan`: `spend_limit` → `{"kind": "spend_limit", **spend_limit.plan(...)}` (fresh read).
- `desk_view.review_item`: `spend_limit` → group `money`, **never pre-ticked** (`needs_tick=True`), `body = {from_cents, to_cents}`. A removal is `blocked` on the multi-accept sheet: "Removing the limit is accepted on its own: open the suggestion."
- `ads_api._approve`: `spend_limit` → role check (`user["role"] == "admin"`; RLS already pins the proposal to this account; account admins of *this* account pass, teammates and clients get 403 "Only an admin of this account can change its spending limit"), then `spend_limit.apply(...)` with `data.from_cents`, `data.to_cents` (must equal the plan), `data.remove`, `data.confirm_remove`. Errors map through the existing prefixes (`NOT_SENT` stays waiting; `UNKNOWN` → "check Ads Manager"; `CHECKED` → failed with the sentence).
- D3 "Did it work?" doesn't judge spend-limit changes (not a performance change). `change_checks` ignores `action = 'spend_limit*'`.

### Routes (Settings)

| Route | Owner | Account admin | Teammate | Client | What |
|---|---|---|---|---|---|
| `GET /api/settings/spend-limit` | yes | yes (own account) | 403 | 403 | `spend_limit.live()` + `blocked` |
| `POST /api/settings/spend-limit/check {to_cents \| remove}` | yes | yes | 403 | 403 | `plan()` for the dialog (fresh read) |
| `POST /api/settings/spend-limit {from_cents, to_cents \| remove, confirm_remove}` | yes | yes | 403 | 403 | `apply()`; answers like Accept (409 with a new plan when the limit moved) |
| `POST /api/settings/spend-limit/unblock` | yes | 403 | 403 | 403 | `unblock()` |
| `GET /api/agent/snapshot` | (Mac) | | | | `spend_limit: {limit_cents, spent_cents, rate_cents, days_left}` from the stored snapshot + pace, no write |

`admin_required` covers the first three. Unblock is `owner_required`, because clearing a safety stop is console-wide trust.

### Alerts and wording

- `spend_cap` and `cap_soon` (`alerts.py:268-283`) and the Results warning (`performance_api.py:143-145`) stop saying "raise it in Meta's billing settings". Instead: "Change the limit in Settings → Targets, or ask Claude." The `href` becomes `/settings.html#spend-limit` (alias → Targets). Same rules and thresholds.
- `spend_limit_mismatch` lines: "We sent $200.00; Meta stored $2.00. We put back $150.00 (checked: it held). Limit changes are paused until you clear them in Settings → Targets."

## UI

Words are plain throughout. Classes use the `sl-` prefix. Phones get 44 px targets, 16 px fields and nothing past the edge at 320 px.

### Accept sheet / suggestion card (`js/decide.js`, `js/suggest.js`)

- Line for `spend_limit`: `Account spending limit: <del>$150.00</del> → <ins>$200.00</ins>` then a second line `Spent so far $112.40 · at about $20 a day the ads run about 4 more days (now 1).` Without a pace: `… · not enough recent spend to tell how long it lasts.`
- Group "Spending". Never pre-ticked.
- Removal: line `Removes the account spending limit. Meta then has no ceiling on total spend.` Accept opens a **second** dialog: title "Remove the spending limit?", body "Your ads could then spend without an account ceiling. Each campaign's daily budget still applies.", confirm button **Remove the limit** (danger style). Only that sends `confirm_remove: true`.
- Refused plans show their sentence in place of Accept (e.g. "That's at or below what's already spent ($112.40)…").
- The suggestion card's change text: "Spending limit $150 → $200".

### Settings → Targets → "Account spending limit" (`#spend-limit`, owner and account admins)

Below "Highest daily budget", a block (`.sl-box`) read live when the section opens (skeleton while reading):

- "Spending limit: **$150.00** · spent **$112.40** · about **1 day** left at the current pace." Or "No spending limit." Muted: "Checked on Meta at 2:41 PM."
- Field "New limit" (money input, 16 px, `inputmode="decimal"`) + **Change limit** → the same dialog as the Accept sheet (old → new, spent, days left), confirm **Change to $200.00**. A quiet link **Remove the limit…** → the separate removal confirmation.
- Field errors on the field itself (`fieldError`): "That's at or below what's already spent…".
- When blocked: a red note "Limit changes are paused: on Nov 12 Meta stored $2.00 when we sent $200.00. We put back $150.00. Check the limit in Ads Manager." The owner gets **Clear and allow changes** (confirm: "Ads Manager shows the limit you expect?"); an account admin reads "The console's owner clears it."
- Hint under the block: "Meta pauses every ad once this much has been spent in total. Raising it lets them run again."
- At phone width the fields and buttons stack full width.

### The Claude page

No new controls. The conversation shows the spend-limit suggestion card like any other (kind label "Spending limit", money group).

## Skill (`ads/bridge/skill/SKILL.md`, desk 2.7, text only)

1. Replace `SKILL.md:384-386` ("Raising the account spending limit is `other`…") with the `spend_limit` kind.
2. In **Proposals** (step 6) add `spend_limit` = `entity_type: "account"`, `entity_id: "act_<the snapshot's ad account>"`, `proposed_value` "$200" (the new total limit, never per day) + `payload {"proposed_cents": 20000}`, or `proposed_value` "no limit" + `payload {"remove": true}`; `current_value` from the snapshot's `spend_limit`; `rationale` with spent so far and the pace. The console refuses a limit at or below the amount spent.
3. New section **"Plain requests → suggestions"**, one table (Claude never writes to Meta; it reads, then proposes):

| He writes | Kind | What to fill |
|---|---|---|
| "raise / lower / set campaign X to $30/day", "$30 a day on N-campaign", "budget 30" | `budget` | the campaign or ad set that holds the daily budget; `$30/day` + `proposed_cents 3000`; every budget rule (≤ +20% unless said, 3-day rule from `budget_changes`) still applies and is named in the rationale |
| "turn off / pause / stop N3", "switch off the reels ad" | `status` | the ad's id, `PAUSED` |
| "turn on / resume N3" | `status` | `ACTIVE` (the sheet confirms its budget) |
| "set / raise / increase my (total / account) spending limit to $200", "limit 200", "cap the account at $200" | `spend_limit` | `$200`, `proposed_cents 20000` |
| "remove the spending limit", "no limit" | `spend_limit` | `no limit`, `remove: true` |
| "$200" with no per-day / limit word, or a name matching two things | none | ask in the answer which one he means; no suggestion |

   Rules: match names against the snapshot's campaigns and ads (short codes like N3). Several matches → ask. The conversation's account is the only one a run can change. When he names the other business ("raise Masha's campaign"), answer "Switch to Masha Fontana Studio and ask there", because a run can't suggest changes for another account.
4. Keep "No money moves from a Desk task" and add: "Changing it happens in the console when Eugene taps Accept: the console reads Meta again, checks the money rules and records it."
5. Logging: when `desk history` shows an applied `spend_limit`, `budget` or `status` suggestion not yet in `reports/log.md`, the next run appends one line (what, old → new, when, by Accept) through `desk log-applied <id>` (built after review: the CLI appends fixed-format lines from the dashboard's record, owner's own requests only, so a run that reads outside text never gets an Edit grant on the log; `Edit(reports/log.md)` stays with render and advice runs for their uploads).

Bridge: `desk VERSION` 2.7, with the new `desk log-applied` command. Install after the server Update (check for a running Desk task first).

## Money and security rules

- Nothing reaches Meta without a person's yes: the Accept sheet (never pre-ticked) or the Settings dialog. Removal needs a second, separate confirmation, and multi-accept never removes.
- The server reads Meta **right before** the write, checks the echoed old amount, and refuses at or below `amount_spent`.
- **One write unit function** (`spend_cap_param`) and **one read unit function** (`spend_cap_cents`). Every write is followed by a read-back. On a mismatch: put the old value back, raise a bad alert, and block until an owner clears it. A read-back Meta doesn't answer blocks too, with no blind restore.
- Never `spend_cap_action` (`reset` would zero `amount_spent`, `delete` removes the limit).
- Roles: owner or this account's admin. Teammates and clients never (403, also proven for a forged POST). The suggestion must name this account's own `act_` id.
- The Mac never writes: proposals only. The meta-ads guard hook and `~/.claude/settings.json` are untouched.
- Every write goes to `meta_changes`, `activity`, History (account level) and, through the skill, `reports/log.md`.
- `max_daily_budget_cents` (per account) is unchanged and still caps every daily budget suggestion.

## Fake Meta (`dev/fake_meta.py`)

- Account object state `ACCOUNT_STATE[act] = {"spend_cap": 15000 (cents), "amount_spent": 4120}`, read as cents strings (as now).
- `POST act_<id>` with `spend_cap`: parse as a **decimal in standard units** ("200.00" → 20000 cents), the documented write unit. `"0"` → no limit. A value with more than two decimals or not a number → error 100. `spend_cap_action` → error 100 "not used by the console (fake)" (proves we never send it).
- `GET /fake/_spend_cap?mode=cents` (the "Meta reads our value as cents" bug: "200.00" stored as 200), `mode=ignore` (the write answers success and changes nothing), `mode=normal`, `amount_spent=<cents>`, `limit=<cents>` to set the state.
- `GET /fake/_spend_cap?silent_readback=1`: the next `GET act_` after a write times out (the unanswered read-back path).

## Tests

### Unit: `backend/tests/test_spend_limit_logic.py` (write first; each can fail for a real defect)

| Case | Expected |
|---|---|
| `spend_cap_param(20000, "USD")` | `"200.00"` |
| `spend_cap_param(15050, "EUR")` | `"150.50"` |
| `spend_cap_param(1, "USD")` | `"0.01"` |
| `spend_cap_param(None, "USD")` | `"0"` |
| `spend_cap_param(20000, "JPY")` | raises ValueError |
| `spend_cap_param(-5, "USD")`, `spend_cap_param(20000.0, "USD")` | raises ValueError |
| round trip, property: for cents in 0..10_000_000 step 9973 | `round(float(spend_cap_param(c)) * 100) == c` |
| `spend_cap_cents("15000")` / `("0")` / `("")` / `(None)` | `15000` / `None` / `None` / `None` |
| `spend_cap_cents("150.00")` | raises ValueError |
| `readback_ok(20000, "20000")` / `(20000, "200")` / `(None, "0")` / `(20000, "abc")` | True / False / True / False |
| problem: to 4120, spent 4120 | "at or below what's already spent" |
| problem: to 4119, spent 4120 | same sentence |
| problem: to 4121, spent 4120 | None |
| problem: remove, confirm False / True | "needs its own confirmation" / None |
| problem: to 99 | "at least 1.00" |
| problem: to == from | "already the limit" |
| `spend_limit_change(15000, 20000, 11240, 2000)` | `days_now 1`, `days_after 4`, `left_after 8760` |
| `spend_limit_change(…, rate 0)` | days `None` |
| `limit_words("$200")`, `("to $200")`, `("200 dollars")` | `20000` |
| `limit_words("no limit")`, `("remove the limit")` | `None` |
| `limit_words("$200/day")`, `("$200 a day")`, `("200 daily")` | `"daily"` |
| `limit_words("$150 or $200")` | not an amount (refused) |
| `insights` read refactor | `sync_account` on the fake's account row stores `spend_cap_cents == 15000` (existing fixture in `test_insights_logic.py`) |

Extend `test_desk_logic.py`: `clean_proposal({"kind": "spend_limit", "entity_id": "act_999", …})` for an account whose ad account is `1025…` → kind `other`. Payload `{"proposed_cents": "20000"}` → int 20000. `{"remove": "yes"}` → refused (must be literal true).

Extend `test_ads_logic.py`: `proposal_action` for `spend_limit` with words "$200" and cents 20000 → `("spend_limit", 20000)`; words "$200/day" → `unclear` naming a daily budget; cents 25000 with words $200 → `unclear`.

Extend `test_desk_view_logic.py`: `review_item` for `spend_limit` → group `money`, `tick False`, `needs_tick True`; removal → `blocked` with the "accepted on its own" sentence.

A ratchet test (`test_money_rules_logic.py`): scan `backend/*.py` for `spend_cap=`. The only file allowed to pass it to `meta_client.post` is `spend_limit.py`, and that file must call `money_rules.spend_cap_param`. Any `spend_cap_action` anywhere fails.

### `qa/flows.cjs` (new block "Spending limit", about 18 checks; `ageBudget` style helpers for fake state)

1. Settings → Targets as owner: `#sl-box` reads "$150.00" and "spent $41.20" (fake 4120).
2. Change to 200 → the dialog shows `$150.00 → $200.00` and days-left wording. Confirm → toast "Spending limit changed to $200.00". **The fake holds 20000 cents** (`metaObj('act_…').spend_cap === '20000'`), proving the dollars write. A `meta_changes` line appears in History (account) and the Activity list.
3. **Refusal, at spent:** `/fake/_spend_cap?amount_spent=20000`, then type 200 → field error "at or below what's already spent". POST directly with `to_cents 20000` → 409 and the fake unchanged.
4. **Refusal, remove without confirm:** POST `{remove: true}` without `confirm_remove` → 400. The fake unchanged.
5. Remove through the UI: **Remove the limit…** → the second dialog → the fake `spend_cap` "0" (no limit) → the line reads "No spending limit". Then set 150 back.
6. **Refusal, stale amount:** change the fake to 17000 behind the page, then confirm a change shown from 15000 → 409 "The limit on Meta is $170.00 now", nothing written.
7. **Mismatch:** `/fake/_spend_cap?mode=cents`, change to 200 → error "Meta stored $2.00 instead of $200.00, so the console put back $150.00…". The fake ends at 15000. The `spend_limit_mismatch` alert is in Inbox → Needs action. A second change attempt → "Limit changes are paused".
8. Account admin sees the paused note without **Clear**; `POST /unblock` as account admin → 403.
9. Owner **Clear and allow changes** → note gone, alert resolved, a change works again. `mode=normal`.
10. **Unanswered read-back:** `silent_readback=1`, change → "Couldn't read the limit back from Meta; check it in Ads Manager", blocked, **no second write** (`/fake/_hits` shows one POST). Clear.
11. **Suggestion:** a seeded `spend_limit` proposal (`qa_desk_states`-style insert: words "$200", cents 20000, entity `act_1025…`) shows on the Claude page with kind "Spending limit". The Accept sheet line reads `$150.00 → $200.00` and isn't ticked. Tick + Accept → the fake 20000, the proposal `applied`, `meta_changes.proposal_id` set.
12. A seeded removal suggestion on the multi-accept sheet → `blocked` "accepted on its own". Opened alone → the second dialog appears before anything is sent.
13. A suggestion with words "$200/day" → the sheet shows the "reads as a daily budget" refusal and no Accept.
14. A suggestion naming another account's `act_` id → stored as `other` (Accept records only; the fake unchanged).
15. Teammate session: `GET /api/settings/spend-limit` 403, `POST` 403, accepting the seeded suggestion 403 (account-wide).
16. Client session: the same POST → 403 "Your access is read-only".
17. The Results / Today limit warning links to `settings.html#spend-limit` and no longer says "billing settings".
18. Phone 390 and 320: `#sl-box` field 16 px, buttons ≥ 44 px, no overflow. Ad-blocker guard passes (`sl-`).

Reset at the end: `mode=normal`, limit 15000, spent 4120, block cleared.

### `dev/qa_leaks.py`

`GET /api/settings/spend-limit` in the walk (account 2's admin reads account 2's ad account only; client 403). A `spend_limit` proposal seeded in account 1 is invisible and not acceptable from account 2 (404).

### Bridge

`bridge/test_bridge.py`: only render and advice runs may edit `reports/log.md`; `desk log-applied` lines tested (built after review). No Meta write tool is in any list (an existing check, extended to the full write-tool list).

## Live checks owed (with Eugene, in this order, his yes before each)

1. **The first real change.** With Eugene watching Ads Manager → Billing → Account spending limit: raise $150 → $160 from Settings. Expect Ads Manager to show $160.00 and the console's read-back to pass. If Meta stored $1.60 or $16,000, the console has put $150 back and paused. Then we know the write unit, and fix `spend_cap_param` in one place.
2. `amount_spent` after the change: Meta's note "setting a new spend cap only applies to spend AFTER the time at which you set it" could mean `amount_spent` restarts. Compare the console's "spent so far" with Ads Manager right after the change.
3. Removal (`spend_cap` 0) on the real account, only if Eugene wants it. Otherwise leave it unverified.
4. A real Claude conversation: "increase my total spending limit to $200" produces one `spend_limit` suggestion with the right numbers (bridge desk 2.7 installed).

## Out of scope

- Billing (payment methods, thresholds) and campaign-level spending limits (`spend_cap` on campaigns stays read-only, as D2 shows it).
- Bid changes and schedule or targeting edits from a sentence (they stay `other` / `targeting`, recorded only).
- Automatic raises ("keep it topped up"). Never: every change needs a yes.
- Changing the other account from this account's conversation.
