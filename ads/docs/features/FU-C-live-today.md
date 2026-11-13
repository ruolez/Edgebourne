# FU-C · Numbers through now: a Today range, today so far in every range, judgments still on complete days

Unit key: `FU-C-live-today` · Asked by Eugene 2026-11-12 · Meta: **read-only** (today's insights at ad level, yesterday's hourly totals) · Money: none. No decision, rule or suggestion starts using today's partial numbers.

> **Architect resolutions (2026-11-12), applied below:**
> - Screens show numbers **through now**. A new **Today** range is added. Last 7 / 14 / 30 days and This month **include today so far** (Last 7 = today plus the 6 days before it). Last month and custom ranges stay as they are (custom may end today).
> - Today's part is labelled everywhere: **"today so far, Meta still counting"**. Today's figures are read live from Meta when a page opens, cached at most **90 s** per account. Refresh re-reads at once. The worker keeps today's `ad_daily` row fresh (it already writes it; the interval stays the Settings one).
> - **Judgments stay on complete days** (CLAUDE.md rule 5) and say **"through yesterday"**: verdicts, Did it work?, tests, Claude's budget suggestions and the desk snapshot, the 3-day rule, alerts, Numbers vs Ads Manager, the client reports' settled periods. One switch decides it: `ranges.window(..., live=False)` stays the default, and only display endpoints pass `live=True`. A ratchet test keeps it that way.
> - **Like with like.** Today is compared with **yesterday up to the same hour** (Meta's hourly totals, read once an hour). A range that includes today compares **its complete days** with the same number of complete days before, and says "vs before · complete days". Per-row deltas in the manager are left out for Today.
> - Also fixed: every clock time shows the **account's clock**, with a short zone tag when the browser's zone differs. The booking dialog's next-hour default uses the account clock.
> - No migration.

## Goal

Eugene, 2026-11-12: *"when we are getting metrics stats numbers about ads clicks .... we fetch live data including today please not just settled stale data"*

1. Opening Ads, Results, a campaign, an ad or Today shows spend, views, clicks and leads **including today so far**, read from Meta within the last minute or two. Refresh reads again.
2. A **Today** range shows just today, compared with yesterday up to the same hour.
3. Every figure that includes today says so in one short line, and every verdict says it judged complete days "through yesterday", so a number that moves during the day never flips a decision.
4. Times read the same for him wherever his laptop or phone thinks it is.

## What exists today

| What | Where |
|---|---|
| Windows end yesterday for every key; previous window | `backend/ranges.py:20-52` |
| Results window and previous (`periods`, `window_args`, `RANGE_KEYS`) | `backend/performance_api.py:23`, `46-51`, `211-218`, `232` |
| Ads manager / Campaign / Ad set / Compare windows | `backend/ads_api.py:509-513`, `entities_api.py:84-87`, `146-151` |
| Ad page daily series and source | `backend/ads_api.py:680-700`, `774-778` |
| Gallery and Ideas windows (own key sets) | `backend/gallery_api.py:48-52`, `concepts_api.py:95-104` |
| Today page: 7-day figures + today's spend per campaign, cached **5 min** | `backend/home_api.py:21-35`, `168-185` |
| Today's rows already stored: daily syncs run *until today* | `backend/insights.py:196-206`; worker `jobs.py:75-93`; quick pull `refresh_api.py:28` (3 days), `85-103` |
| Today's campaign snapshot (`today_snapshot`, day-stamped) | `backend/insights.py:286-308` |
| Refresh (60 s throttle) | `backend/refresh_api.py:150-166` |
| Source line "complete days to …", "today so far, changes through the day" | `frontend/js/format.js:157-171`, `backend/numbers_check.py` (`source`) |
| Range list and shared range | `frontend/js/format.js:99-122` |
| Desk snapshot uses complete days | `backend/desk_api.py:1041-1104` (through `overview_data`) |
| Judgments: alerts `_last(rows, today, n)` days `< today` | `backend/alerts.py:88-90`, `115-121` |
| Did it work? windows end yesterday | `backend/change_checks.py:64-86` |
| Tests cover complete days | `backend/experiments.py:144`, `289-296` |
| Compare / Ideas / Gallery verdicts | `backend/compare.py:58`, `concepts.py:23`, `gallery.py:97` |
| Times shown in the **browser** zone without a tag | `frontend/js/format.js:20-22`, `145-149`; `ui.js:205-209` (`when`); `home.js:12`, `147`, `293`; `conversation.js:30-45` |
| Booking default from the browser clock | `frontend/js/followup.js:107-111` |
| Account zone known to the page | `GET /api/auth/me` `account.tz` (`auth.py:179-181`), `window.ebadsMe` |

## Data / migration

**No migration.** New per-account settings keys (`settings_store.ACCOUNT_KEYS`):

- `today_ads_at`: epoch seconds of the last live read of today's per-ad rows (any reader: page, Refresh, worker).
- `meta_cache` key `hourly:<yyyy-mm-dd>:<level>`: yesterday's hourly totals (account or campaign level), TTL 1 h, account-scoped by RLS.

`ad_daily` already holds today's row per ad. It's overwritten by every read and becomes yesterday's row the next day, rewritten by the next sync. Nothing judgmental reads it, guarded below.

## Backend

### Pure logic (TDD), `backend/ranges.py`

```python
KEYS = ("today", "7", "14", "30", "mtd", "lastmonth", "custom")
LIVE_KEYS = ("today", "7", "14", "30", "mtd", "custom")      # ranges that may reach today

def window(key, today, start=None, end=None, live=False)
    # live=False: unchanged (complete days; "today" -> yesterday alone, so a judgment never sees today)
    # live=True : "today" -> (today, today); "7|14|30" -> (today-(n-1), today); "mtd" -> (1st of today's month, today);
    #             "lastmonth" unchanged; "custom" may end today (end clamped to today, not yesterday)

def settled(start, end, today) -> tuple[date, date] | None
    # the complete-day part of a window: (start, min(end, today-1)), None when it has none (Today, or a custom day = today)

def includes_today(start, end, today) -> bool

def compare_plan(key, start, end, today) -> dict
    # how "vs before" works for a window shown live:
    #   end < today            -> {"mode": "days", "now": (start, end), "before": previous(start, end, key)}
    #   key == "today"         -> {"mode": "hours", "now": (today, today), "before": (today-1, today-1)}
    #   otherwise              -> {"mode": "days", "now": settled(...), "before": previous(*settled(...), key),
    #                              "note": "complete days"}   # today shown, not compared
    #   a window that is only today but not key "today" (custom = today) -> same as "today"

def same_hours(hour_rows, upto_hour) -> dict
    # Meta's hourly rows for one day -> {spend_cents, leads, impressions, link_clicks} for hours 0..upto_hour (inclusive)
    # hour key "13:00:00 - 13:59:59" -> 13

def label(start, end, today=None)
    # "Today" | "Nov 6 – today" | unchanged for past windows
```

`backend/insights.py`:

```python
TODAY_MAX_AGE = 90  # seconds: "at most a 1-2 minute cache"

def today_fresh(at, now, max_age=TODAY_MAX_AGE) -> bool      # pure

def read_today(force=False) -> dict
    # {as_of, read: True|False, error: str|None}
    # skip when today_fresh(settings today_ads_at) and not force, or meta_client.recently_failed("today_ads")
    # under refresh_api.pull_lock(acct) TRY (never waits: a held lock means someone is reading now; use what's stored)
    # one call: read_days(today, today) (level ad, time_increment 1, READ_TIMEOUT 8 s) -> upsert ad_daily
    # today_snapshot rebuilt from the same rows (sum per campaign), so the separate campaign read in pull_today goes
    # sets today_ads_at; a MetaError -> remember_failure("today_ads"), stored rows stand, `error` in plain words

def yesterday_hours(level="account", campaign_ids=None) -> dict | None
    # act_<id>/insights?level=<level>&time_range={yesterday}&breakdowns=hourly_stats_aggregated_by_advertiser_time_zone
    #   &fields=spend,impressions,inline_link_clicks,actions[,campaign_id]  -> meta_cache "hourly:<day>:<level>" 1 h
    # None when Meta doesn't answer (the page then says "not compared yet")
```

`pull_today` stays as the name the worker and Refresh call. It becomes `read_today(force=True)`, so every path stores the same rows.

### Display endpoints pass `live=True`

| Endpoint | Change |
|---|---|
| `performance_api.overview` (Results) | `window_args(args, live=True)`; `overview_data(..., live=True)` reads `read_today()` first when the window includes today; totals and series include today; `previous` from `compare_plan`; the response adds `today: {included, as_of, partial: true, error}` and `compare: {mode, note, before_label}`; Lead quality (`/quality`) counts follow the window, but its `verdict` is computed on `settled()` |
| `ads_api.tree` (manager, quick look), `entities_api` campaign / ad set | `window_from(args, live=True)`; per-row `before` only for `mode == "days"` over the settled part; Today mode: totals compared by hours, rows show no delta |
| `ads_api.ad_detail` / `ad_series` | series include today as the last point, flagged `partial` |
| `entities_api.compare` | figures live; **verdict on `settled()`** with `verdict_through` = yesterday; no verdict for Today ("Judged on complete days: none yet in this range") |
| `gallery_api.gallery_cards`, `concepts_api` (Ideas) | figures live; the Top order, "Too early", "Cheapest" and Tired chips computed on `settled()` and labelled "through yesterday" |
| `home_api.home` | `TODAY_TTL` 300 → `insights.TODAY_MAX_AGE` via `read_today()`; the "This week" figure becomes "Last 7 days" including today (`overview_data(user, 7, live=True)`), with today's figure next to it as now |
| FU-A `accounts_api.overview` | the shared range, live |

**Unchanged (complete days, explicit `live=False` or own windows):** `desk_api.snapshot` (and `budget_snapshot`), `alerts.*`, `change_checks*`, `experiments*`, `meta_tests`, `numbers_check` (check window ends yesterday), `report_logic` / `reports_api` periods, `money_rules` (3-day rule is time-based), `snooze`, `advice_api`, `pacing.pace` (complete days plus today's spend as today, as now), `lead_quality` verdicts.

The snapshot gains a **separate** `today_so_far` block `{spend_cents, leads, as_of}` labelled "partial, never judge on it", so Claude can mention it without counting it.

### `source` (D1) on live responses

`numbers_check.source(...)` gains `today: {included, as_of, read_ok}`. `complete_to` stays yesterday. The check state keeps covering complete days only.

### Worker and Refresh

- The worker's automatic pull (`refresh_api.pull_latest`) already reads the last 3 days including today. It now calls `read_today(force=True)` in place of `pull_today` (one call fewer).
- `POST /api/refresh` keeps its 60 s throttle. A page's Refresh calls it, then reloads. Refresh also clears `today_ads_at`, so the next page read is live.
- The hourly 7-day sync still rewrites today's rows. Nothing else changes.

### Roles

The same data rules as today: teammates see their campaigns, clients their account, read-only. The live read of today is triggered by any signed-in viewer and throttled per account (90 s, try-lock), so a client opening Today can't make the console hammer Meta. Nothing new is shown to clients that they didn't see before, except today's figures in the ranges they already see.

## UI

Words are plain throughout. Classes use the `td-` prefix. Phones get 44 px targets and nothing past the edge at 320 px.

### Range picker (`js/format.js`)

`RANGES = [["today", "Today"], ["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]]`. Every page using `rangeSelect` gets Today. `sharedRange` / `rememberRange` accept it. Pages whose view makes no sense for one partial day keep their own list without it: the ad page's Audience tab (unique reach by window), Reports (periods), Tests.

### Labels

- Under the figure row, the source line (`format.sourceLine`) becomes, for a live window: `From Meta · today so far, Meta still counting (2:41 PM PT) · complete days to Nov 11 · matches Ads Manager`. When the live read failed: `… · today's numbers are from 2:12 PM (Meta didn't answer)`.
- The change chips: Today → `vs yesterday by 3 PM: +$4.10`. Ranges with today → `vs before · complete days` in the chip's title and once under the figure row ("Compared without today: today isn't over yet.").
- Daily charts: today's bar or point is drawn **lighter and hatched** (`.td-partial`, a CSS pattern, no inline style) with the label "today so far". The legend gets "Today so far (still counting)". Charts follow the dataviz rule that partial data must look different.
- Verdict chips and lines (Compare, Gallery, Ideas, Lead quality, Tests, Did it work?): a muted suffix **"through yesterday"** where the range includes today. Compare for Today: "No verdict for today alone: judged on complete days only."
- Manager rows for Today: the delta cell shows "—" with a title "Each row is compared on complete days; pick another range".

### Today page (`home.html`)

The "Today" money figure reads "Spent today so far" with "as of 2:41 PM PT" (account clock), refreshed when the page opens if older than 90 s. "This week" becomes "Last 7 days, with today".

### Clocks in the account's zone (`js/format.js`, `ui.js`)

```js
export const acctZone = () => window.ebadsMe?.account?.tz || undefined;
export const zoneDiffers = (now = new Date()) => offsetOf(acctZone(), now) !== offsetOf(undefined, now);   // compares offsets, not names
export const zoneTag = (d) => zoneDiffers(d) ? " " + shortZone(acctZone(), d) : "";                    // "PT", "PST"/"PDT" from Intl
export const clock = (iso) => fmt(iso, { hour: "numeric", minute: "2-digit", timeZone: acctZone() }) + zoneTag(new Date(iso));
```

`dayWords`, `dayTimeWords`, `syncedWords`, `sinceWords` (dates only), `ui.when`, `home.js` (greeting, today's date, "as of"), `conversation.js` (Today / Yesterday grouping) and `followup.js` all use the account zone. Nothing else is converted: dates without a time (`dayLabel`) are account days already.

### Booking dialog (`js/followup.js`)

`meetingDefault(now)` reads the hour and the day in the account zone (`Intl.DateTimeFormat(..., { timeZone: acctZone(), hour: "numeric", hourCycle: "h23" })`). "Today" and "Tomorrow" are the account's. When the zones differ, the time field's hint reads "Times are Los Angeles time". The server already reads `{preset, time}` and a picked `at` as account time (`followup.py`); a unit test proves the `at` path.

### Phone

The source line stays one line with ellipsis and opens on tap (D1). Chips wrap. The hatched today bar keeps a minimum width of 6 px at 320 px.

## Money and security rules

- **No judgment on partial data.** `live=True` appears only in display endpoints (ratchet test below). Alerts, Did it work?, tests, Claude's snapshot and suggestions, the 3-day rule, numbers checks and client reports never read today.
- Reading today is a GET, throttled per account (90 s, try-lock, `remember_failure`), and it never blocks a page longer than `READ_TIMEOUT` (8 s). Stored numbers stand in.
- No write to Meta. No money rule changes.

## Fake Meta (`dev/fake_meta.py`)

- `insights_rows("ad")` includes a row for **today** whose spend grows with the time of day (`spend = base * (minutes since midnight / 1440)`, account zone), so two reads 2 minutes apart differ. `GET /fake/_today?spend=<dollars>&leads=<n>&ad=<id>` sets today's numbers exactly for QA.
- Hourly breakdown: `breakdowns=hourly_stats_aggregated_by_advertiser_time_zone` on `act_/insights` returns 24 rows for the asked day with `hourly_stats_aggregated_by_advertiser_time_zone: "HH:00:00 - HH:59:59"`, spend split evenly, leads in hours 9, 13 and 17.
- `/fake/_hits` already counts calls (used to prove the 90 s cache).

## Tests

### Unit: `backend/tests/test_ranges_logic.py` (extended, write first)

| Case | Expected |
|---|---|
| `window("7", Nov 12)` (default) | `(Nov 5, Nov 11)` (unchanged) |
| `window("7", Nov 12, live=True)` | `(Nov 6, Nov 12)` |
| `window("today", Nov 12, live=True)` / `live=False` | `(Nov 12, Nov 12)` / `(Nov 11, Nov 11)` |
| `window("mtd", Nov 1, live=True)` / default | `(Nov 1, Nov 1)` / `(Oct 1, Oct 31)` (today's behaviour on the 1st kept for judgments) |
| `window("lastmonth", Nov 12, live=True)` | `(Oct 1, Oct 31)` |
| `window("custom", Nov 12, "2026-11-10", "2026-11-12", live=True)` / default | ends Nov 12 / ends Nov 11 |
| `settled(Nov 6, Nov 12, Nov 12)` / `settled(Nov 12, Nov 12, Nov 12)` | `(Nov 6, Nov 11)` / `None` |
| `compare_plan("today", …)` | mode `hours`, before = Nov 11 |
| `compare_plan("7", Nov 6, Nov 12, Nov 12)` | mode `days`, now `(Nov 6, Nov 11)`, before `(Oct 31, Nov 5)`, note "complete days" |
| `compare_plan("lastmonth", …)` | before = September, no note |
| `same_hours(rows, 13)` | sums hours 0–13 only (row "14:00:00 - 14:59:59" left out) |
| `today_fresh(at=now-89, now)` / `now-91` / `None` | True / False / False |
| `label(Nov 6, Nov 12, today=Nov 12)` / `label(Nov 12, Nov 12, today=Nov 12)` | `"Nov 6 – today"` / `"Today"` |

**Ratchet** `test_live_ranges_ratchet` (pure file scan): the files that may contain `live=True` are exactly {`performance_api.py`, `ads_api.py`, `entities_api.py`, `gallery_api.py`, `concepts_api.py`, `home_api.py`, `accounts_api.py`}. And `alerts.py`, `change_checks.py`, `change_checks_db.py`, `experiments.py`, `experiments_api.py`, `meta_tests.py`, `numbers_check.py`, `report_logic.py`, `reports_api.py`, `desk_api.py`, `money_rules.py`, `snooze.py` contain no `live=True` and no `read_today(`. It fails if someone wires a judgment to partial data.

`test_performance_logic.py`: `overview_data` with a stubbed `read_today` and `live=False` (the snapshot path) never calls it (a counter stays 0).

`test_followup_logic.py`: a picked `at` "2026-11-12T15:00" for an account in America/Los_Angeles is stored as 23:00 UTC whatever the server's zone (`TZ=Europe/Berlin` set in the test).

### `qa/flows.cjs` (new block "Live today", about 16 checks)

1. `/fake/_today?spend=7.50&leads=1&ad=<N4>`. Results with **Today**: Spent includes `$7.50`, and the source line contains "today so far, Meta still counting".
2. Results Last 7 days: total = stored 6 complete days + today's $7.50 (computed from `/api/performance?range=7` series), and the last series point carries `partial: true`.
3. Change chips on Last 7 read "complete days" in their note. On Today the chip reads `vs yesterday by` followed by an hour.
4. **Cache:** `/fake/_hits?clear=1`, open Results twice within 90 s → one `level=ad` today read. After `POST /api/refresh` (or a 91 s age set through settings `today_ads_at`) → one more.
5. **Judgments stay settled:** change today to `spend=500` and run the alerts. No new `cpl_high`, `no_leads` or fatigue alert opens; only the existing `day_overspend` rule (spend vs daily budget) may. Compare's verdict on two ads is unchanged from before the bump (same JSON `verdict`), and the line reads "through yesterday".
6. `GET /api/agent/snapshot` (QA Mac key) `performance.range.end` = yesterday and `today_so_far.spend_cents` = 50000.
7. Did it work? for a seeded change is unchanged by today's bump (same state).
8. Ads manager with Today: totals show today, rows' delta cells show "—", and the legend shows today's bar hatched (`.td-partial` present).
9. Campaign, Ad set and Ad pages with Last 7: the chart's last bar has `.td-partial`.
10. Gallery and Ideas with Today: cards show today's spend, chips read "through yesterday" or "Too early".
11. Today page: "Spent today so far" equals today's sum; "as of" shows an account-clock time.
12. **Time zones:** a context with `timezoneId: 'Europe/Berlin'`. The source line's time carries `PT`/`PST`/`PDT`. A lead's "booked call" time shows the account zone tag. The booking dialog's default hour = (account hour + 1) per `Intl` in America/Los_Angeles, not Berlin's, and its hint reads "Los Angeles time".
13. The same context with `timezoneId: 'America/Los_Angeles'` shows **no** zone tag.
14. Meta slow: `/fake/_slow?daily=12` → Results opens within ~9 s with the stored today and the "Meta didn't answer" wording. Then clear.
15. Client session: Today range shows today's figures (same rules as other ranges), with no amounts in the check note (D1 rule).
16. Phone 390 and 320: the source line fits, the chips wrap, and the range select ≥ 44 px with a 16 px font.

### Screenshots

`qa/shots.cjs`: Results and Ads with `?range=today`, the ad page chart with Last 7. Check them in both themes and widths.

## Live checks owed

1. Meta's per-ad numbers for today against Ads Manager's "Today" column at the same minute (spend and leads), once in the morning and once in the evening.
2. The hourly breakdown on the real account: leads (`actions`) are returned per hour, and the account-time-zone hours line up (the "vs yesterday by 3 PM" chip against Ads Manager's hourly view).
3. Meta's rate limits with pages opened by several people: the 90 s per-account cache holds (watch the console log for code 17 / 80004 over a day).

## Out of scope

- Hour-by-hour charts for today (only the comparison uses hours).
- Live numbers inside client report emails (settled periods, as agreed).
- Judging anything on today, even "obviously bad" days. The day-overspend alert keeps its existing today rule (`alerts.py:241`, spend vs daily budget, info only), which isn't a performance verdict.
- Push notifications for today's spend.
