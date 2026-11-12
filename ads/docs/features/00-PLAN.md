# 00 · Lead architect's plan for the seven design units

Units: **D1** match Ads Manager · **D2** outside edits + 3-day rule + chart marks · **D3** "Did it work?" · **L1** follow-ups + booked calls · **L2** lead quality (lost reasons, highest stage, repeats, junk) · **W1** snooze + diagnose + lead-quality alerts · **W2** report funnel + review before send.

Checked against the repo on 2026-11-11 (HEAD `c10378d`, last migration `030_ad_versions.sql`, audit-fix workflow editing `qa/flows.cjs`, `qa/run.sh`, `dev/qa_leaks.py`). Facts this plan relies on:
- Campaign and ad set pages keep their tab in the **query** (`UrlState`: `/campaign.html?id=X&tab=history`). The ad page keeps it in the **hash** (`/ad.html?id=X#tab=history`). D2 and D3 both got this wrong.
- `alerts.run` auto-closes only `kind = 'condition'` rows. An alert raised `kind: 'event', resolved: False` stays open until its own module closes it. There's no need for W2's `SELF_CLOSING` list.
- `raise_found` sends to `notify.admin_ids()`, which returns every account's admins: a cross-account leak (also flagged by the audit).
- `report_logic.funnel(leads, contacted, qualified, won)` and `report_logic.money(cents)` (always `$`) are the current signatures.
- `status_events.field` uses an inline CHECK (`status_events_field_check`). `desk_tasks_kind_check` was last redefined in 027.

Every unit spec has been edited in place. Each now opens with an **Architect resolutions** block, and its conflicting lines are corrected.

---

## 1. Conflicts and their single resolution

| # | Conflict | Specs | Resolution |
|---|---|---|---|
| C1 | **History link format.** D2 uses `campaign.html?id=X#tab=history`. D3 uses `?check=N#history`. Neither matches the code. | D2, D3 | One helper owned by D2: Python `links.history_href(level, id, check=None)` and JS `historyHref(level, id, {check})` in `ui.js`. It gives `/campaign.html?id=X&tab=history[&check=N]`, `/adset.html?id=X&tab=history[&check=N]` and `/ad.html?id=X[&check=N]#tab=history`. Every alert href and History link calls it, so a change in 9.3 is a one-line change. |
| C2 | **Report funnel signature.** W2 has `funnel(steps: list)`. L1 has `funnel(leads, contacted, qualified, won, booked=None)`. W2 also requires rates never to pass 100, but a call booked through a booking tool can come before Contacted. | W2, L1 | W2 owns `funnel(steps)`. Each step is `(label, n)` or `(label, n, base_label)`, and the rate is n ÷ the base step (default: the step before). Each output item is `{step, n, rate, of}`. L1 inserts `("Booked a call", b, "Leads received")`, and Qualified becomes `("Qualified", q, "Contacted")`. Every base is a superset, so no rate passes 100. L1's `booked=` kwarg is dropped. |
| C3 | **Name of the console's own lead count.** D1 uses "Arrived" and the key `arrived`. W2 uses "Leads in the inbox". Phase 9.2 makes **Inbox** mean the notification feed only. | D1, W2, L1, L2 | The word is **Received** and the key is `received`. The funnel's first step is "Leads received", the compact pair is "Meta 12 · Received 11", and help text refers to "your leads list". The phrase "from the leads inbox" is dropped everywhere. The Results sub under "Qualified or won" becomes "got that far · from your leads", and "Cost per booked call" gets "from your leads". |
| C4 | **What counts as one lead.** D1 counts `NOT is_test`, W2 uses `LEAD_SCOPE = "NOT is_test"`, L2 uses `counted()` (no tests, no repeats), and W1 has its own query. | D1, W2, L2, W1, L1, D3 | L2 owns the SQL fragments `lead_quality.counted()`, `qualified()`, `won()` and `contacted()`, and its ratchet test enforces them. Before L2 lands, W2's `LEAD_SCOPE` is `"NOT is_test"`. When L2 lands, it changes `LEAD_SCOPE` to `counted()`. Received, the funnel, the booked cohort, D3's cost per qualified lead and W1b's rules all use these fragments. |
| C5 | **What "Contacted" means.** In L2, `contacted()` includes `first_contacted_at`. Under L1, a no-answer call sets `first_contacted_at`, so a no-answer would count as Contacted in reports. L1 says Contacted stays stage-based. | L1, L2, W2 | Contacted is stage-based: `contacted(a) = a.max_stage <> 'new'`. `first_contacted_at` means "first try" and is used only for urgency and response time. L2's max_stage backfill may still read the old `first_contacted_at` (it meant contact before L1). |
| C6 | **Phone and email keys.** In L1, `bookings.contact_keys` takes the last 10 digits and gives no key under 7 digits, with no placeholder check. In L2, `phone_key` gives the last 10 digits, keeps 8–9 digits whole, gives no key under 8, and gives no key for placeholders such as 555 and test domains. L1's tests use `555-000-1111` and `example.com`, which L2 treats as fake. | L1, L2 | L2 owns one pure module, `backend/contact.py`, with `email_key` and `phone_key`; L2's rules apply. `leads.email_key` and `leads.phone_key` (L2 columns) are the only stored keys. L1 Phase C matches bookings with `contact.*` against roots (`repeat_of IS NULL`). L1's tests switch to realistic data (`Maria@LopezBakery.COM`, `+1 (619) 555-7788`). |
| C7 | **Lost-reason keys.** W1 uses `elsewhere`; L2 uses `went_elsewhere`. | W1, L2 | `went_elsewhere`, from L2's `LOST_REASONS`. |
| C8 | **What "junk" means.** W1 counts lost as `spam`, `duplicate` or `not_fit`. L2's `is_junk` is lost as spam, or flagged + never contacted + not dismissed. Repeats are already folded by `repeat_of`. | W1, L2 | `lead_quality.is_junk` is the only definition. W1's `junk_high` uses it with **counted leads in the window** as the denominator (flagged junk is never "worked"). The title is "33% of leads from “…” look like junk". `not_fit` is a real person, not junk. |
| C9 | **Overdue follow-ups.** W1 adds an alert rule `followups_overdue` on `next_step_due_at`. L1 owns follow-ups (Today, reminders, digest), says not to add that rule, and names the column `next_step_at`. | W1, L1 | **`followups_overdue` is dropped from W1.** L1 covers due and overdue items through Today, notifications and the digest, and covers "no next step" through the Today footer and `?due=none`. The column is `next_step_at`. |
| C10 | **Lead undo.** L2 uses `PATCH {status, undo:true}`, based on `activity`, 5 minutes. L1 uses `POST /calls/<event_id>/undo`, based on `lead_events`, 10 minutes. Phase 9.4 asks for "Undo on stage change". | L1, L2 | One route, `POST /api/leads/<id>/events/<event_id>/undo`, run by `lead_history.undo`. Same person, within `UNDO_MINUTES = 10`. Allowed kinds: `call`, `stage`, `lost_reason`. A stage event's `details` carry `{from, to, max_before, max_after, reason, reason_before}` so `undo_max` can restore. `CLIENT_LEADS` becomes `^/api/leads/\d+(/notes\|/calls\|/events/\d+/undo\|/not-junk)?$`. The `undo` key leaves the PATCH guard. |
| C11 | **`lead_events.kind` CHECK** is defined by L1, but L2 writes kinds L1 doesn't list. | L1, L2 | L1's migration includes L2's kinds from the start: `lost_reason`, `max_stage`, `repeat`, `returning`, `linked`, `unlinked`, `not_junk`. No constraint churn. |
| C12 | **PATCH `/api/leads/<id>` client guard.** L1 widens it one way, L2 another. | L1, L2 | Clients with `client_lead_updates` may send `{"status","lost_reason","lost_note","next_step","next_step_done","meeting"}`. Same-person, correct-stage and booking routes stay out of reach for clients. |
| C13 | **Wrong-number and couldn't-reach Lost buttons.** L2 preselects "Spam or fake" for Wrong number. L1 has its own Lost buttons. | L1, L2 | "Move to Lost" after Wrong number opens L2's Lost dialog with nothing preselected, unless the lead has junk flags (then "Spam or fake"). L1's one-tap buttons "Lost: couldn't reach" and "Lost: went quiet" send `{status:"lost", lost_reason:"no_response", lost_note:"Couldn't reach after 3 tries" \| "Went quiet after 3 tries"}`. |
| C14 | **"What we did" in the report.** D2 reshapes `changes` with `where` and a `title`. W2 builds `what_we_did(console, outside)` with `by: console\|outside` and its own wording. In D2, `by` means a person. | D2, W2 | W2 owns `report_logic.what_we_did`. Each item is `{day, where: "console"\|"outside", level, name, text}`; the key `by` is reserved for a person's name. Budget, bid, date and audience text comes from D2's `status_history.headline` with a lowercased first letter, so History and the report use the same words: "Ad set “Broad”: daily budget $24.00 → $30.00 a day (in Ads Manager)". `OUTSIDE_FIELDS = status_history.OUTSIDE_FIELDS` (`configured_status` + D2's `SETUP` fields), present from W2's first commit because D2 lands first. D2's own report section is reduced to "provide `headline` and `OUTSIDE_FIELDS`". |
| C15 | **Money and date formatting.** D2 has `account_info.money_words`, W2 has `report_logic.money(cents, currency)`, W1 uses `alerts.money`, and D3 passes `money` in. Date styles differ too: "Fri Nov 14", "Mon, Nov 17 at 8:00 AM", "Thu, Nov 13, 2:00 PM". | all | One pure server module, `backend/words.py`: `money(cents, currency)`, `day(d)` "Nov 9", `weekday(d)` "Fri, Nov 14", `day_time(dt, tz)` "Thu, Nov 13, 2:00 PM", `ago(dt, now)` "today" / "5 hours ago" / "1 day ago". The client twins live in `format.js`. If the audit fix or 9.1 has already added `account_info.money`, `words.money` wraps it. The old helpers become thin aliases for one release. |
| C16 | **Inbox items that need a person but aren't conditions.** These are `report_review` (W2, which proposed `condition` plus a `SELF_CLOSING` list), `change_result` (D3, an event that should be Needs action until put back), `booking_unmatched` (L1, an event open until matched) and `outside_edit` warn (D2, an event raised already resolved, so it could never be Needs action). | D2, D3, L1, W2, W1 | Single contract (W1 implements it in `inbox.triage()` if 9.4 hasn't): **an event raised with `resolved: False` stays open until its owner closes it.** Needs action = open conditions + open events at `warn`/`bad`, not snoozed, plus waiting suggestions. Everything else is FYI. Owners close them: `report_review` on send or skip, `booking_unmatched` on match or dismiss, `change_result` on put back or **Done**, `outside_edit` (warn) on **Done** or by itself after 72 h (housekeeping in `alerts.run`, because the 3-day window has passed). `DONE_OK = {"outside_edit", "change_result"}` get a **Done** action. No `SELF_CLOSING` list. |
| C17 | **Today reads alerts differently.** `open_alerts` has a 3-day window (W2 needs `report_review` to bypass it), and D1, D2, D3, L1, W1 and W2 each rank their own items. | all | The Today queue shows the Needs-action set (C16) plus L1's lead buckets, ranked by group (§2, S9). There's no separate age window. Each unit only declares its item's group. |
| C18 | **Who gets messages.** W1 says "the tenant fix's list", W2 adds `reviewers()`, L1 says admins and owners, and `raise_found` uses the leaky `admin_ids()`. | all | `notify.account_admin_ids()` returns active admins with `account_id = current account OR account_id IS NULL`. The audit fix owns it; if it isn't in when D2 is built, D2 adds it and switches `raise_found` to it. W2's `reviewers()` is that function. |
| C19 | **Dialog parts.** D2 adds `confirmLabel`, L2 adds `choices` and `multiline`, W1 adds a choice dialog (`al-choice`) and a textarea dialog, L1 has a two-step `fu-dialog`, D3 has a tabbed `oc-sheet`. Phase 9.2 asks for one Dialog. | D2, L2, W1, L1, D3 | One `confirmDialog`, extended once. D2 adds `confirmLabel(value)` (button text re-run on input). W1a adds `choices: {options:[{value,label,hint}], required, submitOnPick}` and `field.multiline` (16 px on coarse pointers). L2 reuses them with `required: "Pick a reason"`. L1's two-step dialog and D3's tabbed dialog are built on the same `<dialog>` base and the 9.2 Dialog CSS; only the content classes stay unit-specific (`fu-`, `oc-`). |
| C20 | **Line under charts.** D1 adds the source note and D2 adds "N changes in this period"; both want the spot under the chart row. | D1, D2 | One `<div class="fig-foot">` under the chart row on Campaign, Ad set, Ad Overview, Results and Compare: D1's `sourceNote` on the left, D2's `marksPanel` summary on the right. Phones stack them, source first. D2 creates the row (it lands first); D1 fills the left side. Pages without charts (Ads manager, Today, Reports) carry the source note alone. |
| C21 | **The D1 pill word "Off".** It clashes with the 9.2 delivery word **Off** (Delivering / Off / In review / Rejected). | D1 | The pills are **Matches** / **Differs** / **Not checked** / **Couldn't check**. The headline is "Differs by $3.20 and 1 lead on 2 days". |
| C22 | **D1's report stamp vs W2's frozen copies.** D1 says share links compute the stamp per request; W2 freezes what was sent. D1 puts an admin warning above the headline; W2 has the admin review bar. D1 calls `ensure_period` from `send_due`; W2 rewrites `send_due`. | D1, W2 | The frozen copy keeps the stamp as of sending, next to "Figures as sent on …". D1's admin warning and its **Pull these days again** button go inside W2's `#rv-bar` (never in client views or snapshots). W2's claim step calls `numbers_check.ensure_period(start, end)` before taking the snapshot, when D1 is present. A failure never blocks the email. |
| C23 | **Windows in "Did it work?".** D3 ends windows early only on outside `configured_status`; D2 asks that outside budget edits count too. | D2, D3 | D3 ends windows on `ok` console changes in `CHECKED` **and** on `status_events` (source poll/webhook) with `field = ANY(status_history.OUTSIDE_FIELDS)` on the scope, its parent or its children. |
| C24 | **Budget dialog changed by two units.** D2 adds the last-change read, `confirmLabel` and `accept_recent`; D3 adds `suggest`, `note` and `undoOf`. | D2, D3 | One signature: `editBudget({level, id, name, current, suggest?, note?, undoOf?})`. D2 builds the read and the recency hint; D3 adds the three options. Put it back always sets the exact previous amount, so D2's rollback rule (never "recent") applies, while +20% and the ceiling still apply. |
| C25 | **`timeline.merge` changed by two units.** D2 adds `versions=()` and `cat`; D3 adds `checks=None`. | D2, D3 | `merge(status_events, changes, proposals, money, versions=(), checks=None)`. Both kwargs are optional, so the old tests stay green. |
| C26 | **Which alerts can be snoozed or diagnosed.** Several units add rules that W1 doesn't know about. | W1, D1, D2, D3, L1, W2 | Snoozable = rules in `snooze.WORSE` only. D1 adds `numbers_off` (measure = days that differ, worse at ≥ baseline + 3; hint "You'll hear again if 3 more days differ."). Diagnosable = rules in `diagnose.PLAYBOOKS`. D2's `outside_edit` → `("meta-ads", "what changed outside the console", "activity log: who changed what, and whether it breaks the money rules")`. D3's `change_result` → `("cpa-diagnostics", "why a change didn't help", "before/after windows, what else changed, whether to put it back")`. Never snoozable or diagnosable: `report_review`, `report_sent`, `booking_unmatched`, `booking_canceled`, `numbers_off` (diagnose only). |
| C27 | **Bridge version bumps.** W1 goes to 1.10 and D3 also changes the bridge (`desk outcomes`). Several units only add lines to SKILL.md. | W1, D3, D1, D2, L2 | Each shipped unit that edits `ads/bridge/*` (SKILL.md included) bumps bridge VERSION by one, in build order: D2 → 1.10, W1a → 1.11, L2 → 1.12, D3 → 1.13, D1 → 1.14. No `MIN_BRIDGE` change in any unit. Eugene runs `install.sh` only **after** the server Update and checks for a running Desk task before kickstarting. |
| C28 | **Event alerts that are pure FYI** (D2 info, D3 good/flat, W2 `report_sent`, L1 `booking_canceled`). | — | Raised with `resolved: True`, level `info`. Never messaged. Always FYI. |

---

## 2. Shared pieces: build once, owner named

| # | Piece | Owner (first to land) | Users |
|---|---|---|---|
| S1 | `backend/words.py` (pure: `money`, `day`, `weekday`, `day_time`, `ago`) + the same in `format.js` | **D2** (wraps `account_info.money` if the audit fix already has it) | all |
| S2 | `links.history_href` / `ui.js historyHref` (C1) | **D2** | D3, alerts, Inbox, marks panel |
| S3 | `notify.account_admin_ids()` (C18) | audit fix, else **D2** | W2 reviewers, W1 wake-ups, L1 digest, all `raise_found` |
| S4 | `status_history.SETUP`, `OUTSIDE_FIELDS`, `headline()` for setup fields | **D2** | W2 What we did, D3 windows, marks |
| S5 | Changes feed: `status_history.changes_in` + `timeline.merge(..., versions, checks)` with `cat` | **D2** (marks, History) | D3 (`checks`), every History tab, the Desk snapshot `recent_changes` |
| S6 | `fig-foot` row under charts (C20) | **D2** | D1 |
| S7 | `confirmDialog` extensions: `confirmLabel` (D2); `choices`, `submitOnPick`, `field.multiline` (**W1a**) | D2, then W1a | L2 Lost dialog, W1 Got it and Diagnose, L1/D3 build on the base |
| S8 | Alert contract: `alerts.measure` + `quiet` columns, `alert_snoozes` table (snooze state), owner-closed events (C16), `inbox.triage()` Needs action / FYI, `DONE_OK` + Done action, `desk_api.latest_runs` | **W1a** (snooze tables in its migration) | D1 `numbers_off`, D2 `outside_edit`, D3 `change_result`, L1 booking rules, W2 `report_review` |
| S9 | Today queue groups (order): 1 leads to call now (L1 buckets 0–2) · 2 ads with problems + tracking `bad` · 3 lead follow-ups overdue / did the call happen (L1 buckets 3–4) · 4 decisions: waiting suggestions, `report_review` · 5 money: `outside_edit` warn, `change_result` warn, spend alerts · 6 system: `numbers_off` warn, other tracking · 7 follow-ups later today (L1 bucket 5) · footer lines "N open leads have no next step", "N snoozed alerts" | **9.4** (pure `today.rank(items)`); if 9.4 isn't in, W1a adds the function | all |
| S10 | `report_logic.funnel(steps)` with bases, `lead_gap`, `what_we_did`, `email_text` | **W2** | L1 (Booked step), L2 (`lost_line`, repeat clause in `lead_gap`), D1 (stamp) |
| S11 | `lead_events` + `lead_history.record / for_lead / describe / undo`, unified undo route | **L1** | L2 (stage, lost reason, max stage, link/unlink, not junk) |
| S12 | `backend/contact.py` (`email_key`, `phone_key`, placeholder rules) | **L2** | L1 Phase C booking match |
| S13 | `lead_quality` SQL fragments `counted/qualified/won/contacted`, plus the ratchet test | **L2** | W2 `LEAD_SCOPE`/`stage_counts`, D1 Received, L1 booked cohort, D3 cost per qualified lead, W1b rules, `ads_api._quality` |
| S14 | Settings anchors added to the 9.4 one-section map: `#numbers` → Tracking (D1); `#booking` and `#lead-quality` → Leads (L1, L2); `#snoozed` → Alerts (W1); `#reports` → Clients and reports (W2) | each unit; 9.4 owns the map | QA `openSettings(section)` |
| S15 | `alerts.DEFAULTS`, `inbox.CATEGORY` and Settings → Alerts rows (consolidated table, §4) | each unit adds its own rows | — |
| S16 | Desk snapshot keys, one per unit: `source` (D1), `budget_changes` + `recent_changes` (D2), `change_results` (D3), `calls`/`talked`/`booked`/`follow_ups_overdue` (L1), `lead_quality_by_ad`/`_totals`/`_notes` (L2). No names, emails, phones or notes in any of them. | each unit | bridge SKILL.md |

---

## 3. Money-rule and cross-account security review

General rules every unit keeps: no new Meta writes; nothing applies on its own; every budget or status write still goes through `money_rules` and the confirm dialog that shows dollars; every new table has `account_id DEFAULT app_account()` + `ENABLE ROW LEVEL SECURITY` + the `account_isolation` policy; worker steps run per account inside `account_ctx.use`; `dev/qa_leaks.py` covers new GET routes.

### D1: Match Ads Manager. Verdict: safe; 4 corrections
- **Required:** `restate` and `check` run only inside `account_ctx.use(acct)`, and the token and `act_<id>` come from that account's settings, never a module default. The pull lock key is `LOCK_KEY * 1000 + account_id`, as specified. A unit test asserts that the lock key differs across accounts.
- **Required:** `numbers_off` goes in `snooze.WORSE` and passes `measure` (C26). `href` = `/settings.html#numbers`. Clients never see it (category `system`).
- **Required:** snapshots and client views carry only `state`, never `spend_off_cents` / `leads_off` (already in the spec for members and clients; it also covers W2's frozen snapshot).
- **Required:** a restate after `insights_unified_attribution` is switched on may change many older days. Alerts must not fire on that night's shifts: `cpl_high` and `no_leads` already judge only the recent window, so this is fine, but the release note must tell Eugene that older lead counts can move. Turning that switch on is a stated pick (open decision). It is a read parameter, not a Meta write.
- The zeroing guard (`restate_plan` zeroes only when that day's fetched rows add up to Meta's total) stays mandatory, with its unit test.

### D2: Outside edits and the 3-day rule. Verdict: tightens money rules; 4 corrections
- **Required:** recency is **recomputed at write time** on every path: `set_budget`, `proposals/<id>/approve`, `bulk/apply` (per line, against `budget_rows` read in the apply transaction) and `advice/apply`. A plan signed at preview or check time is never trusted for `recent`. Bulk apply refuses a line that became recent after the preview unless `accept_recent` is set.
- **Required:** on the Accept sheet, `accept_recent` is sent only from an item the user ticked (`needs_tick`, never pre-ticked), the same as `accept_big`.
- **Required:** `outside_edit` warn is an owner-closed event (C16), Done or 72 h. Info is resolved at once.
- **Required:** `GET /api/ads/<level>/<id>/budget/last`: owner and account admins, teammates only with `can_touch` (else 404), clients 403. Marks with `for_client` drop people's names and "Claude's suggestion". Account-level marks are admin only.
- The 72 h window is a constant with no setting, rollback and decreases are never "recent", and decreases are never blocked. All correct.

### D3: "Did it work?". Verdict: safe; 3 corrections
- **Required:** `undo_of` is accepted only when it names an `ok` change of the **same account (RLS), same entity and matching action**. It never skips `from_cents`, the ceiling, +20% or `turn_on_problem`. Put it back is always the exact previous amount, so D2's "recent" exemption for rollbacks applies, and nothing else is exempt.
- **Required:** `/api/agent/outcomes` and the snapshot `change_results` are scoped to the task's account (the same mechanism as `/api/agent/snapshot`, `DESK_ACCOUNT`). They contain no lead names, emails or phones (QA check 9).
- **Required:** `change_result` warn is an owner-closed event (C16). Clients never get `undo`, `proposal` or `expect`. Teammates get `undo` only under `can_touch`.

### L1: Follow-ups and booked calls. Verdict: no money paths; 5 corrections
- **Required (owner decision before build):** moving New → Contacted after "Talked to them" or "Booked a call" sends Contacted to Meta through `crm_events` when stage sending is on. That is an existing write type on a new trigger, so it needs Eugene's explicit yes. **The default without a yes:** no automatic move; the toast offers **Move to Contacted** (one tap, a human stage move as today).
- **Required:** the booking webhook token is resolved to an account by a lookup on `sha256(token)` (column or settings key `booking_hook_token_hash`), through the same narrow owner-side lookup as `account_for_ad_account`. `account_ctx.use` is set **before** any read or write. An unknown token gets 403 and never falls back to account 1. The signature is checked with `hmac.compare_digest`.
- **Required:** `bookings.payload` stores only the normalized fields plus the raw delivery for 30 days. A `jobs.PRUNE` rule nulls `payload` on processed rows after 30 days; the rows themselves are kept.
- **Required:** reminders and the digest go to the lead's owner, or `notify.account_admin_ids()` (S3), never the global list.
- **Required:** client writes (`/calls`, the undo route) only with `client_lead_updates`, through `CLIENT_LEADS` (C10). The bookings list, match and Settings are admin only.

### L2: Lead quality. Verdict: no money paths; 4 corrections
- **Required:** the match query carries an explicit `AND o.account_id = %(acct)s` as well as RLS (backfills and owner-role code paths bypass RLS), plus the composite foreign keys, as specified.
- **Required:** replace the blocking `db.lock` on its own connection with `pg_advisory_xact_lock(hashtext('lead-match'), account_id)` inside the insert transaction. It's released on commit or rollback, and a webhook can't hang on a leaked lock.
- **Required:** undo deletes a `crm_events` row only with `DELETE … WHERE id=%s AND status='pending' RETURNING id` in the undo transaction. If nothing is returned, it was claimed or sent, and the response says "Meta already has it". It never sends a retraction (that would be a Meta write).
- **Required:** the snapshot, report and share links never include `lost_note`, answers, names, emails or phones (QA check 14).

### W1: Snooze and Diagnose. Verdict: no money moves; 4 corrections
- **Required:** a **money** alert already at level `bad` (for example the spending limit reached) offers only **Remind me tomorrow** (1 day), never "Only if it gets worse". Snoozing never hides an escalation to `bad`.
- **Required:** `diagnose` runs read-only on the Mac through an **explicit** entry in the bridge's read-only kinds, not the "unknown kind" default. `dev/qa_agent_diagnose.py` asserts the tool list the bridge would use.
- **Required:** `GET /api/diagnose/draft?ad_id=` and `?alert_id=` return 404 for another account's ids (RLS), and both are in `qa_leaks.py`. All four routes are `admin_required`.
- **Required:** wake-up messages go through `raise_found`, so they use S3 recipients.

### W2: Report review. Verdict: no Meta, no money; 3 corrections
- **Required:** the frozen `snapshot` is built with the client view (`for_admin=False`): no D1 amounts that differ, no people's names in marks, no Claude proposals, no lead PII. The note is plain text rendered with `textContent`.
- **Required:** the migration's settings backfill parses only values matching `'^(week|month):\d{4}-\d{2}-\d{2}$'`, so one malformed setting can't fail the migration.
- **Required:** `reviewers()` = `notify.account_admin_ids()`. QA check 4 already asserts that the other account's admin gets nothing.

---

## 4. Vocabulary (exact UI words)

These words go into `format.js` (and the server twins in `words.py` or the owning module). Phase 9.2 words stay as they are: **Views, People reached, Hook rate, Cost per lead, Delivering / Off / In review / Rejected, Suggestion, Accept, Conversation, Inbox = the notification feed, Needs action / FYI, Today, Leads**.

| Concept | Use | Never |
|---|---|---|
| The console's own lead count | **Received** (pair: "Meta 12 · Received 11"); funnel step **Leads received**; "your leads list" | Arrived, Leads in the inbox, leads inbox |
| Meta's lead count | **Meta** / "Meta counted 22 leads" | — |
| Highest stage | **Qualified or won** (sub: "got that far · from your leads"), **Got as far as: Qualified** | — |
| Cost per qualified lead | **Cost per qualified lead** (table header "Per qualified lead" where narrow) | CPQL |
| Booked call | **call**, **booked call**; figure **Calls booked**; figure **Cost per booked call**; column **Booked** / **Per booked call**; funnel **Booked a call**; **No-show**; "Did the call happen?" | meeting, appointment |
| Next step | **Next step**, **Follow-up**, **Due today**, **Overdue**, **No next step** | task, to-do |
| Lost reasons | No response · Not a fit · Too small · Price · Went with someone else · Spam or fake · Duplicate · Other; "Lost because: …"; "No reason given" | — |
| Junk | **Looks like junk** (chip), "Mark as lost: spam or fake", "It's real" | spam lead, fake lead |
| Repeats | **Repeat**, **Asked 2×**, **Asked again**, **Asked before**, "Not the same person", "Same person as…" | duplicate lead (that's a lost reason) |
| Outside edits | "in Ads Manager"; "Made outside this console (Ads Manager, or Claude on the Mac)"; "Changed in Ads Manager: …" | external, third-party |
| 3-day rule | "Less than 3 days since the last change." / **Raise anyway** / **Apply anyway** / "Last change: …" / "Back to $20.00, the budget before the last change." | cooldown |
| Confirmed knowingly | "Confirmed knowingly: more than +20%" / "…: under 3 days since the last change" | override |
| Chart marks | categories **Budget · On/off · Edits · Meta**; "N changes in this period"; **Show on charts** | markers, annotations |
| Numbers check | **Numbers vs Ads Manager**; pills **Matches / Differs / Not checked / Couldn't check**; **Check now**, **Check again**, **Pull these days again**; "From Meta · synced 4:10 AM · complete days to Nov 10" | restate, reconcile, Off |
| Did it work | **Did it work?**; Worked · Looks better, not sure yet · No clear change · Looks worse, not sure yet · Didn't help · Too early to tell · Not checked yet · On target · Over target · Changed again too soon · Nothing to compare · Off · Not running yet; **Put it back**; "Put back on Nov 17 by Eugene"; **Done** | revert, rollback (UI) |
| Snooze | **Got it…**; **In 3 days**; **Only if it gets worse**; **Remind me tomorrow**; "Snoozed until Fri, Nov 14 · Eugene"; "Snoozed until it gets worse · Eugene"; **Wake it now**; "Worse: …"; "Back as promised: …" | mute, dismiss, acknowledge |
| Diagnose | **Diagnose with Claude**; run kind label **Diagnosis**; chips **Waiting for your Mac · Claude is on it · N suggestions · Read Claude's answer · Diagnose again** | proposals, job, task |
| Report review | **Our note (optional)**; **Preview the email**; **Send now · Send at 8 AM · Send tomorrow at 8 AM · Hold it · Don't send this one · Send again with today's figures · See what was sent**; pills **Waiting for you · Goes out at 8:00 AM · Sending… · Sent Mon, Nov 17, 8:14 AM · Not sending · Not finished yet · No clients yet · Email isn't set up** | approve, publish |
| Dates | "Nov 9" · "Fri, Nov 14" · "Thu, Nov 13, 2:00 PM" · "1 day ago" / "5 hours ago" / "today" (S1) | "Fri Nov 14", "at 8:00 AM" |
| Undo | toast button **Undo** (8 s). Server window 10 min for leads, then "Too late to undo; …" | — |

**Settings → Alerts rows (new and renamed):**
- `numbers_off`: "Our numbers differ from Ads Manager"
- `outside_edit`: "Changed in Ads Manager: budget, bid, dates or audience"
- `changed_outside` (renamed): "Switched on or off in Ads Manager"
- `change_result`: "A change didn't help"
- `qualified_low`: "Few leads qualify"
- `junk_high`: "Many leads look like junk"

Booking and report items have no row: they're controlled by their own settings.

**`inbox.CATEGORY` additions:**
- `numbers_off`, `report_review`, `report_sent`: `system`
- `outside_edit`, `change_result`: `money`
- `qualified_low`, `junk_high`, `booking_unmatched`, `booking_canceled`: `leads`

Clients see only `status`, as today.

---

## 5. Build order and migration numbers

The next free migration today is **031**. The audit-fix workflow may take numbers first, so each unit takes **the next free number at build time, in this relative order**. Each migration is written in one go (ROADMAP §5).

| Step | Unit | Migration (relative) | Depends on | Why here |
|---|---|---|---|---|
| 1 | **D2** outside edits, 3-day rule, report and Desk words, chart marks (D2.1–D2.4; D2.5 optional, later) | **N** `NNN_outside_edits.sql` | audit fix (S3 if present) | Money safety first. It creates S1, S2, S4, S5, S6 and the `confirmLabel` part of S7. |
| 2 | **W2** report funnel + review | **N+1** `NNN_report_review.sql` | D2 (S4 `OUTSIDE_FIELDS`, `headline`) | Clients get wrong funnels today. It creates S10. |
| 3 | **W1a** snooze + diagnose (no lead rules) | **N+2** `NNN_alert_snooze_diagnose.sql` | D2 (`outside_edit` playbook), W2 (`report_review` as an owner-closed event) | It creates S8 and the rest of S7. Later alert rules are built with `measure` from day one. |
| 4 | **L1** Phases A + B (follow-ups, booked calls) | **N+3** `NNN_followups.sql` (creates `bookings` too) | W2 (funnel with bases), W1a (dialog parts, triage) | It creates S11. The stage-move decision is asked first (§3). |
| 5 | **L2** lead quality | **N+4** `NNN_lead_quality.sql` | audit-fix `is_organic` / `alerted_at`; L1 (`lead_events`); W1a (`choices` dialog) | It creates S12 and S13 and changes W2's `LEAD_SCOPE`. |
| 6 | **W1b** lead-quality alerts (`qualified_low`, `junk_high`) | none | L2 | Uses L2 fragments directly, with no column detection. |
| 7 | **D3** "Did it work?" | **N+5** `NNN_change_checks.sql` | D2 (windows, `editBudget`, `merge`), L2 (cost per qualified lead), W1a (owner-closed events, playbook) | — |
| 8 | **D1** match Ads Manager + source notes | **N+6** `NNN_numbers_check.sql` | W2 (review bar, `ensure_period` hook), D2 (`fig-foot`), L2 (`counted()`), W1a (`WORSE`) | It touches every figure page, so it's best after 9.2 and 9.4 settle. It can be pulled forward if Eugene wants the numbers check sooner: its only hard dependency is W2. |
| 9 | **L1** Phase C (booking tool) | none (the table is in N+3) | L2 (`contact.py`); Eugene names his tool | — |

Each step lands after the 9.x commit that is current at that time. It rebases onto `format.js`, the 9.2 Dialog and `entityLink`, never around them. The `qa/flows.cjs` additions go in the same commit as the UI.

**Effort:** D2 3.5–4 d · W2 2.5 d · W1 3 d (W1a 2.5, W1b 0.5) · L1 3 d (A+B) + 1.5 d (C) · L2 4 d · D3 2.5 d · D1 2.5 d · **about 22–24 days in total**.

---

## 6. Acceptance tests per unit (short checklists)

Every unit also runs the existing gates: the unit suite green (`docker exec -e WORKERS_ENABLED=0 edgebourne-ads-backend python -m unittest discover -s tests -v`), the `qa/run.sh` ad-blocker name guard, the console-error guard, no overflow at 320 and 390 px, 44 px targets, 16 px fields, `qa_leaks.py` clean, and `qa/shots.cjs` light and dark at desktop and 390 px.

### D2
- [ ] `money_rules.recency`: true at 71 h 59 m, false at 72 h. Rollback to the exact previous amount and any decrease are never recent. The ceiling is still checked first.
- [ ] Every budget path refuses a recent raise without `accept_recent`, with 409 `code: recent_change`: dialog, bulk apply (recomputed at apply), proposal approve (recomputed), advice apply.
- [ ] Accept sheet: a recent budget item is never pre-ticked, and its note starts "Budget last changed".
- [ ] An outside budget change via `/fake/_outside` + pull gives one `status_events` row with by "Ads Manager" and one Inbox item. Warn when it breaks a rule (open, Needs action, Done closes it, and it closes by itself after 72 h); info otherwise. A repeat pull adds nothing.
- [ ] The first sync after the migration records no events (`setup_seen_at` seeding). Targeting noise doesn't count as a change.
- [ ] A console budget change followed by a pull gives no `outside_edit`.
- [ ] Alert hrefs use `history_href`: `campaign.html?id=…&tab=history` opens the History tab.
- [ ] Chart marks on Campaign, Ad set, Ad, Results and Compare. The tooltip on a tap lists the changes. The Show on charts switch persists. The client view shows no names.
- [ ] `words.money` uses the account currency (EUR test).

### W2
- [ ] `funnel` with bases: `[("Leads received",10),("Contacted",8),("Booked a call",5,"Leads received"),("Qualified",3,"Contacted"),("Won",1)]` → rates `[None, 80, 50, 38, 33]`. The exhaustive nested invariant (no rate over 100) holds.
- [ ] `lead_gap` exact strings (with "your leads list"). The report's first funnel step reads "Leads received".
- [ ] Ideas count qualified leads, and the target is `targets.lead_own()`.
- [ ] What we did merges console and outside rows, dated by the account's day, with "(in Ads Manager)" and D2's budget words.
- [ ] Wait mode: no mail at 8 AM, one `report_review` event that is open and Needs action, and a notification to this account's admins only. Send now sends exactly one email per client. A second Send sends nothing. The item closes.
- [ ] Client and share-link views show the frozen copy and the note. An unsent period in wait mode shows "still being prepared".
- [ ] A crash mid-loop resends only the address in flight (`sent_to` per address).
- [ ] The migration keeps already-sent periods as sent, and accounts that email reports start in `auto`.

### W1a
- [ ] `snooze.worse` table cases; the property "an unchanged figure never wakes" holds.
- [ ] Snooze "Only if it gets worse" on `spend_cap` 82 → 85 is quiet (no notification row), and 96 → "Worse: …" goes out once.
- [ ] A money alert at `bad` offers only "Remind me tomorrow". Events and info alerts offer no Got it.
- [ ] A snoozed item moves to FYI, leaves the Needs-action count and leaves Today, and Today shows "1 snoozed alert". Undo or Wake it now restores it.
- [ ] A Meta outage (stale data) doesn't end snoozes.
- [ ] Diagnose: the draft names the ids and the playbook. A second POST returns `already: true`. The task is kind `diagnose`, read-only on the bridge (asserted by `qa_agent_diagnose.py`). Chip states. The `outside_edit` playbook is present.
- [ ] Teammates and clients get 403 on every route. Another account's `alert_id` / `ad_id` → 404.
- [ ] Owner-closed events (C16): an open `report_review` sits in Needs action, and `change_result`/`outside_edit` show **Done**.

### L1 (A + B)
- [ ] `due_at`, `parse_local`, `call_summary`, `meeting_state`, `queue` and `reminder_due` exact cases, DST included.
- [ ] A call outcome sets `first_contacted_at`; a note alone doesn't (reminders still fire). Undo through `/events/<id>/undo` within 10 min restores the counters and `first_contacted_at`; after that, 409.
- [ ] No auto stage move unless Eugene said yes; otherwise the toast offers **Move to Contacted**.
- [ ] Three no-answers → "Lost: couldn't reach" stores `lost_reason=no_response` and closes the next step.
- [ ] `?due=today|overdue|none|booked` lists are correct. The Today rows are in bucket order. A due reminder is sent once (dedupe).
- [ ] `jobs.PRUNE` never lists `lead_events` or `bookings` (guard test). The backfill created `received` events for every lead.
- [ ] Booked a call → chip, `booked_at`, Results "Calls booked" / "Cost per booked call" (sub "from your leads"), and the report step "Booked a call" with its base "Leads received", only when `tracks_bookings`.
- [ ] Clients: no buttons unless `client_lead_updates`. Teammate on another campaign → 404.

### L2
- [ ] `raise_max`, `undo_max`, `clean_lost`, `contact.email_key` / `phone_key` (placeholders give `None`), `flags`, `match_kind`, `is_junk` and `summarize` exact cases. `contacted()` is stage-based.
- [ ] The ratchet test: no `status IN ('qualified'` left in backend queries; every leads count uses `counted()`.
- [ ] Qualified → Lost leaves `totals.qualified` unchanged. Undo through the shared route deletes only a **pending** CRM row.
- [ ] A second fill from the same person → repeat: one alert "Asked again:", no auto reply, the Open count unchanged. **Not the same person** unlinks it and it never relinks.
- [ ] A junk lead gets the chip, no auto reply to a test or throwaway address, and the one-tap "Mark as lost: spam or fake".
- [ ] Results → Lead quality: By ad, form and answer; cards at 390 px; the minimum-data rule holds.
- [ ] Account 2 never links to account 1's lead with the same email (`qa_leaks`). The snapshot has no PII.

### W1b
- [ ] `qualified_low` fires at 2 of 12 worked (16.7%), not at 25%, and not under 10 worked leads.
- [ ] `junk_high` uses `lead_quality.is_junk` over counted leads. The title says "look like junk". There is no `followups_overdue` rule anywhere.
- [ ] Both are snoozable, with hints from `worse_hint`.

### D3
- [ ] `windows`, `judge`, `mode_for`, `expect_from_text`, `clean_expect`, `expectation_met`, `undo_plan` and `sentence` exact cases.
- [ ] An outside budget edit (D2 event) inside the after window ends it early and gives "Changed again…".
- [ ] Put it back opens the budget dialog filled in with the exact previous amount: no "recent" warning, +20% and the ceiling still apply. Cancel → no POST. Confirm → `undo_of` is stored, the History says "Put back on …", and the `change_result` item closes.
- [ ] "Didn't help" → open Needs-action event, emailed once per state class. Good or flat results are FYI.
- [ ] `/api/changes/<id>/check`: clients get no `undo`/`proposal`/`expect`; a teammate outside the campaign gets 404; another account's id gets 404.
- [ ] `/api/agent/outcomes` is account-scoped and has no PII. A Claude expectation shows "Met." or "Not met.".

### D1
- [ ] `check_window`, `parts`, `compare` (tolerance), `summary`, `headline` ("Differs by …"), `restate_plan` (zeroing guard), `freshness`, `night_due` and `pull_range` exact cases. The lock key differs per account.
- [ ] `/fake/_restate` → Check now → **Differs**. Pull these days again → **Matches**, and "Meta changed 1 older day…".
- [ ] A short answer from Meta zeroes nothing.
- [ ] The source note on every figure page ("From Meta · synced … · complete days to …"). The pair reads "Meta N · Received M". The `fig-foot` row is shared with the marks.
- [ ] `numbers_off`: FYI after one night, Needs action after two, closes itself when matching, and is snoozable.
- [ ] Report: the stamp in live and frozen copies. The admin warning and Pull button show only in `#rv-bar`. `ensure_period` runs at the claim.
- [ ] Teammates and clients: no amounts in the note, `/api/numbers` → 403.

### L1 Phase C
- [ ] Signed deliveries from the chosen tool verify; a bad signature → 403; a replay is a no-op.
- [ ] Matching uses `contact.*` against roots (newest open). Unmatched → open Needs-action event; Match or Not from an ad closes it.
- [ ] An unknown token never reaches account 1. Payloads are nulled after 30 days. Rotating the token stops the old URL at once.

---

## 7. Eugene's answers (2026-11-11) — these override any open decision above

1. Booking tool: **none yet, manual only.** Build L1 Phases A + B (Booked a call as a call outcome with the meeting time). Do NOT build Phase C (booking webhook); the `bookings` table may be left out of the migration.
2. **Yes:** "Talked to them" and "Booked a call" on a New lead move it to Contacted automatically (this sends Contacted to Meta through crm_events when Lead stages to Meta is on, exactly as a manual move); toast with Undo.
3. **Yes:** a note no longer counts as contact. Only a logged call, an email or a stage change stops the "nobody called" reminders.
4. Not asked, conventional picks stand: D1 `use_unified_attribution_setting=true` behind a setting; W1 snooze shared by the account's admins, "In 3 days" and "Until it gets worse", default thresholds from the spec. "Send Booked to Meta" is NOT built (needs a separate yes).
