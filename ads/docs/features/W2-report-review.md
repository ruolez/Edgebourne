# W2 · Fix the client report funnel and let admins review a report before it goes out

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build step **2** of 9; migration **N+1**, after D2. W2 owns S10: `report_logic.funnel(steps)`, `lead_gap`, `what_we_did`, `email_text`.
> - C3: the console's own count is **Received**. The funnel's first step is **"Leads received"** and the text says "your leads list". In Phase 9.2, "Inbox" means the notification feed, so "inbox" is never used for leads.
> - C2: each funnel step is `(label, n)` or `(label, n, base_label)`, and the rate is n ÷ base (default: the step before). Each output item is `{step, n, rate, of}`. L1 later inserts `("Booked a call", b, "Leads received")` and makes Qualified `("Qualified", q, "Contacted")`.
> - C4 and C5:
>   - `LEAD_SCOPE = "NOT is_test"` until L2 lands; L2 switches it to `lead_quality.counted()` and `stage_counts` to its fragments.
>   - Contacted is stage-based.
> - C14:
>   - `what_we_did` items are `{day, where: "console"|"outside", level, name, text}`; `by` is reserved for a person's name.
>   - Budget, bid, date and audience wording comes from D2's `status_history.headline` (lowercased first letter), e.g. "daily budget $24.00 → $30.00 a day".
>   - `OUTSIDE_FIELDS = status_history.OUTSIDE_FIELDS` (D2 has already landed).
> - C15 and S1: `money` → `words.money`; `when_label` → `words.day_time`, written "Mon, Nov 17, 8:00 AM" (no "at").
> - C16: `report_review` is an **owner-closed event** (`kind: event`, `resolved: False`), closed on send or skip. There's **no `SELF_CLOSING` change** in `alerts.run`, since that loop closes only conditions. Today shows it through the Needs-action set (C17), so the 3-day window doesn't apply.
> - C18: `reviewers()` = `notify.account_admin_ids()`.
> - C22: when D1 is present, the claim step calls `numbers_check.ensure_period` before the snapshot. The snapshot carries D1's stamp. D1's admin warning and **Pull these days again** sit inside `#rv-bar`.
> - Security:
>   - The snapshot is built with the client view only (no D1 amounts, no names in marks, no proposals, no PII). The note renders as text.
>   - The settings backfill parses only `'^(week|month):\d{4}-\d{2}-\d{2}$'` values.

Design spec, 2026-11-11. Read-only design against the code as of today (`backend/reports_api.py`,
`backend/report_logic.py`, `frontend/js/report.js`, migrations up to `030_ad_versions.sql`). Another
workflow is fixing audit findings in the same files. Where this spec includes one of those findings, the
build step says "skip if already fixed".

No Meta writes. No Meta reads either: the report uses only stored data. No money moves. No bridge change.

---

## Goal

1. **One honest funnel.** Today the first step of the report funnel is Meta's lead count (`ad_daily.leads`,
   `reports_api.py:86`), while Contacted, Qualified and Won are counted from the console's leads (`reports_api.py:33-38`).
   The two sets aren't the same, so "Contacted of Leads" can go over 100% or hide leads that never arrived.
   After this change every step counts the same people: the leads received in the console's leads list (test entries left out). Meta's
   count is shown next to the first step, with the difference explained in plain words.
2. **"By idea" counts qualified leads.** The report's ideas section sets `qualified: 0` on every ad
   (`reports_api.py:75`) and judges against the qualified-lead target, not the lead target that Results → By
   idea uses. After this change it uses the same per-ad qualified query and the same target as
   `concepts_api.by_concept`, through one shared helper.
3. **Review before it goes out.** Each period's client report becomes a record that admins can open first.
   It has an **Our note** box (per account and period, shown first in the report and the email), a preview
   of the email, and **Send now**, **Send at 8 AM**, **Hold it** and **Don't send this one**. A switch per
   account sets the default: **Wait for me** or **Send it without my review** (today's 8 AM behaviour).
4. **What we did is complete.** It now also lists switches made in Ads Manager (status events from Meta,
   already recorded). Budget and schedule edits made in Ads Manager are added once the "Record budget and
   schedule edits" unit records them. Each change is dated by the account's day, not the UTC day.
5. **What the client got is what the client sees.** Once a period's report has been sent, the email link,
   any share link for that period and a signed-in client all see the frozen copy that went out. Admins see
   today's figures, with a "See what was sent" link.

Non-goals: Claude drafting the note (possible later through `/desk.html?ask=`, no bridge change), PDF
rendering on the server, HTML email design, a per-client recipient list.

---

## User flow

### Eugene (owner) or an account admin, desktop

1. Monday 8:00 AM (account time zone). The account's report setting is **Wait for me**. The worker sees the
   week is due, finds clients and a working mailbox, and creates the week's record as **waiting**. Admins of
   that account and the owner get one notification (push, else email; respects "alerts" on Your account):
   "Weekly report for Burdanova is waiting for you". The Inbox shows it under **Needs action**, and so does
   the Today queue.
2. He opens it (the link goes to `/report.html?kind=week&start=2026-11-09#review&acct=2`). Above the
   report there is a review bar:
   - status pill **Waiting for you**, and the line "Nothing goes to masha@burdanova.com until you press Send."
   - **Our note** (optional) textarea
   - **Preview the email** (folded)
   - buttons: **Send now** (primary), **Send at 8 AM** (or **Send tomorrow at 8 AM** after 8), **Don't send this one**
3. He types "N3 was turned off on Wednesday: it brought calls but no bookings. Two new videos go live
   this week." The note appears as the first section of the report preview right away, and he opens
   **Preview the email** to see the exact subject and text.
4. **Send now** opens a confirm dialog: "Send the report now? It goes to masha@burdanova.com with a link
   that works for 90 days. The figures are frozen as they are now." → **Send now**. The note is saved
   with the send. The bar shows **Sending…**, then **Sent Nov 16, 8:14 AM**. The Inbox item resolves.
5. If he does nothing, nothing is sent. The item stays in Needs action and on Today until he acts.

### Same, with "Send it without my review"

- Before 8 AM on Monday, Reports shows **Goes out at 8:00 AM**: "It goes to masha@… at 8:00 AM without
  your review. Hold it to read it first." He can add a note (it goes with the email) or press **Hold it**,
  which turns the period into a waiting one.
- At 8 AM the worker sends it exactly as today. The Inbox gets an FYI line, "Weekly report sent to 1
  client".

### Phone (390 px)

- The review bar stacks: pill and line, then the note textarea (full width, 16px text, at least 5 rows),
  then **Preview the email** as a folded block, then the buttons full width, each at least 44 px tall.
  **Send now** comes first. **Send at 8 AM** and **Don't send this one** sit below it.
- The confirm dialog is the shared `confirmDialog` (already phone-safe).
- The report itself is unchanged on phones. The funnel table keeps its scroll wrapper (A18).

### Client (read-only), desktop and phone

- They get the email: greeting, then the note (if any), the headline, and the link.
- The link opens the frozen copy. **Our note** comes first, signed "— Eugene". The footer says "Figures
  as sent on Nov 16, 2026."
- If the account is set to **Wait for me** and a client opens Reports for a period that hasn't been sent,
  they see: "This report is still being prepared. It will reach you by email." plus a link to the last
  report that was sent, when there is one. If the account is set to send without review, they see today's
  live report, as now.

### Teammate (member)

No change: Reports stays hidden, and every new route answers 403 (9.1 matched the server).

---

## Data model

Migration `NNN_report_review.sql` (one file, written in one go, see §5 gotcha):

```sql
-- W2: a client report per account and period: its note, whether it waits for review, its sending
-- state, and the frozen copy that went out.
CREATE TABLE client_reports (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('week', 'month')),
    start_day DATE NOT NULL,
    end_day DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting', 'scheduled', 'sending', 'sent', 'skipped')),
    note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
    note_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    note_at TIMESTAMPTZ,
    send_at TIMESTAMPTZ,                  -- when status = 'scheduled'
    decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- who pressed Send / Hold / Don't send
    decided_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,               -- the worker took it ('sending'); stale claims go back to 'scheduled'
    round INTEGER NOT NULL DEFAULT 1,     -- 2+ = "Send again with today's figures"
    sent_to TEXT[] NOT NULL DEFAULT '{}', -- this round, saved after each address
    sent_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    snapshot JSONB,                       -- build(..., for_admin=False) taken when this round first went out
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, kind, start_day)
);
CREATE INDEX client_reports_due_idx ON client_reports (status, send_at);
ALTER TABLE client_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON client_reports
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
GRANT SELECT, INSERT, UPDATE ON client_reports TO ebads_app;   -- match how 030 granted (or rely on db.APP_ROLE_SQL default privileges)
GRANT USAGE ON SEQUENCE client_reports_id_seq TO ebads_app;

-- What already went out under the settings-based state stays sent (no second email after Update).
INSERT INTO client_reports (account_id, kind, start_day, end_day, status, sent_at)
SELECT acct, k, s,
       CASE k WHEN 'week' THEN s + 6 ELSE (date_trunc('month', s) + interval '1 month - 1 day')::date END,
       'sent', now()
FROM (SELECT CASE WHEN key = 'report_last_sent' THEN 1 ELSE split_part(key, '@', 2)::int END AS acct,
             split_part(value, ':', 1) AS k, split_part(value, ':', 2)::date AS s
      FROM settings WHERE (key = 'report_last_sent' OR key LIKE 'report_last_sent@%') AND value ~ '^(week|month):\d{4}-\d{2}-\d{2}$') x
ON CONFLICT (account_id, kind, start_day) DO NOTHING;

-- A send that was half done at Update carries on with the addresses it already reached.
INSERT INTO client_reports (account_id, kind, start_day, end_day, status, send_at, sent_to)
SELECT acct, split_part(v->>'key', ':', 1), split_part(v->>'key', ':', 2)::date,
       CASE split_part(v->>'key', ':', 1) WHEN 'week' THEN split_part(v->>'key', ':', 2)::date + 6
            ELSE (date_trunc('month', split_part(v->>'key', ':', 2)::date) + interval '1 month - 1 day')::date END,
       'scheduled', now(), ARRAY(SELECT jsonb_array_elements_text(COALESCE(v->'to', '[]'::jsonb)))
FROM (SELECT CASE WHEN key = 'report_sent_to' THEN 1 ELSE split_part(key, '@', 2)::int END AS acct, value::jsonb AS v
      FROM settings WHERE (key = 'report_sent_to' OR key LIKE 'report_sent_to@%') AND value LIKE '{%') x
WHERE v ? 'key'
ON CONFLICT (account_id, kind, start_day) DO NOTHING;

-- Accounts that email reports today keep doing it without review; every other account waits for review.
INSERT INTO settings (key, value)
SELECT replace(key, 'report_email', 'report_review'), 'auto' FROM settings
WHERE key = 'report_email' OR key LIKE 'report_email@%'
ON CONFLICT (key) DO NOTHING;
```

Notes:
- Migrations run as the owner (RLS bypassed), so the explicit `account_id` values are used as written.
  Check `db.APP_ROLE_SQL` for how grants are made today: if it grants on all tables at boot, drop the two
  GRANT lines.
- `settings_store.ACCOUNT_KEYS` gains `report_review` (values `auto` | `wait`; missing = `wait`).
  `report_last_sent` and `report_sent_to` stop being written. Leave them in `ACCOUNT_KEYS` for one
  release so old values are still readable. A later migration can delete them.
- Pruning: none. That is one row per account per week, about 52 rows a year.
- Leak test (`dev/qa_leaks.py`) walks every GET route automatically. The new GET routes take `kind`/`start`,
  not row ids, so there is no cross-account id to try. Add a write case: an account admin of account 2
  posting `/api/reports/send` while account 1 is chosen in a stale cookie must act on account 2 only (RLS).

---

## Backend

### `report_logic.py` (pure; extend, keep existing functions)

```python
LEAD_STEP = "Leads received"

def funnel(steps: list[tuple]) -> list[dict]
    """Each step is (label, n) or (label, n, base_label). Rate = n ÷ the base step (default: the step before).
    Output items: {step, n, rate, of} (`of` = the base label, None for the first step). Every base is a superset
    of its step, so a rate never passes 100. Takes a list so L1 can insert ("Booked a call", b, "Leads received")
    and set ("Qualified", q, "Contacted") without a new signature (00-PLAN C2)."""
    # callers: funnel([(LEAD_STEP, received), ("Contacted", c), ("Qualified", q), ("Won", w)])

def lead_gap(received: int, meta: int) -> dict | None
    """Meta's count next to the console's own count (Received), in plain words. None when they agree."""

money = words.money   # D2's shared formatter (00-PLAN S1): '$12.34', '€12.34', '£12.34', 'CA$12.34', 'A$12.34',
                      # other codes '12.34 CHF', '—' for None. Kept as an alias for existing callers.

def headline(now: dict, before: dict, target_cents: int | None = None, currency: str = "USD") -> str
    # unchanged wording; `leads` now means leads received (totals() renames Meta's to meta_leads)

def footnotes(start: date, end: date, sent_on: date | None = None) -> list[str]

def what_we_did(console: list[dict], outside: list[dict], currency: str = "USD") -> list[dict]
    """One dated list: console writes (meta_changes) and changes Meta saw made elsewhere (status_events).
    Each item: {day, where: 'console'|'outside', level, name, text}. Sorted by day, then time. `by` is reserved for
    a person's name (D2). Budget, bid, date and audience text = `{Level} “{name}”: ` + status_history.headline(...)
    with its first letter lowercased; outside rows end with ' (in Ads Manager)' (00-PLAN C14)."""

def email_text(report: dict, first_name: str | None, link: str, note: str | None, round_: int = 1) -> tuple[str, str]
    """(subject, body) of the client email."""

def next_send_at(local_now: datetime, hour: int = 8) -> datetime
    """The next `hour`:00 in local_now's zone: today if before it, else tomorrow (DST-safe via zoneinfo)."""

when_label = words.day_time   # 'Mon, Nov 17, 8:00 AM' in the account's zone (00-PLAN S1)

def who_label(emails: list[str]) -> str
    """'a@x.com' · 'a@x.com and b@y.com' · 'a@x.com and 2 others' · 'nobody yet'."""

def review_state(row: dict | None, mode: str, recipients: list[str], mail_ready: bool, complete: bool,
                 due_now: bool, local_now: datetime, tz) -> dict
    """What the review bar shows: {status, pill: [tone, label], line, actions: [...]}."""

def client_can_open(mode: str, row: dict | None) -> bool
    """Clients see a period when it was sent, or when the account sends without review."""

def note_visible(row: dict | None, is_admin: bool) -> bool
    """Admins always see the saved note; everyone else only once the report went out."""

def review_alert(account: str, kind: str, start: date, recipients: list[str]) -> dict
    """The Inbox/Today item for a waiting report: {rule, key, level, title, lines, href}."""
```

Exact strings used by these functions (tests pin them):

- `lead_gap(20, 22)` → `{"meta": 22, "received": 20, "diff": -2, "text": "Meta counted 22 leads; 2 of them didn't reach your leads list. Meta can count a lead on the day the ad was seen, and test entries are left out here."}` (L2 later appends ", and a person who filled the form twice counts once" before the full stop when repeats exist)
- `lead_gap(19, 20)` → text starts `"Meta counted 20 leads; 1 of them didn't reach your leads list."`
- `lead_gap(21, 20)` → `{"meta": 20, "received": 21, "diff": 1, "text": "Meta counted 20 leads; your leads list has 1 more (someone used the form outside an ad, or Meta counted it on another day)."}`
- `lead_gap(3, 0)` → text `"Meta counted no leads from the ads; your leads list has 3 (from the form outside an ad, or not counted by Meta yet)."`
- `lead_gap(n, n)` → `None`
- `email_text` body:
  ```
  Hi Masha,

  <note, if any>

  <headline>

  The full report: <link>
  (The link works for 90 days.)
  ```
  Subject: `"<Account>: your ads report, Week of Nov 9"`. Round 2 and later add `" (updated)"`. With no
  first name the greeting is `"Hi,"`.
- `review_alert` → title `"Weekly report for Burdanova is waiting for you"` (`Monthly` for months), lines
  `["Week of Nov 9 · goes to masha@burdanova.com", "Read it, add a note if you like, then press Send."]`,
  rule `report_review`, key `report_review:week:2026-11-09`, level `warn`,
  href `/report.html?kind=week&start=2026-11-09#review`.

`review_state` table (pill tone uses the existing pill classes `ok` / `warn` / `bad` / `info` / ""):

| Situation | pill | line | actions |
|---|---|---|---|
| period not over (`complete` false) | `["", "Not finished yet"]` | "You can send it once the week is over." | — |
| no recipients | `["", "No clients yet"]` | "No clients on this account yet: add them on the Team page." | — |
| mail not set up | `["bad", "Email isn't set up"]` | "Email isn't set up yet: Settings → Email." | — |
| row waiting, or no row and mode `wait` | `["warn", "Waiting for you"]` | "Nothing goes to {who} until you press Send." | send_now, send_later, skip |
| no row, mode `auto`, due later today | `["info", "Goes out at 8:00 AM"]` | "It goes to {who} at 8:00 AM without your review. Hold it to read it first." | send_now, hold |
| no row, report emailing off, or an older period never sent | `["", "Not sent"]` | "This one wasn't emailed." | send_now, send_later |
| scheduled | `["info", "Goes out {when_label}"]` | "To {who}." | send_now, hold, skip |
| sending | `["info", "Sending…"]` | "{n} of {m} sent." | — |
| sent | `["ok", "Sent {when_label}"]` | "To {who}. Clients see it as it was sent." | view_sent, send_again |
| skipped | `["", "Not sending"]` | "You chose not to send this one." | undo_skip |

`send_later` is labelled "Send at 8 AM" before 8:00 local time and "Send tomorrow at 8 AM" after.

### `reports_api.py`

- `LEAD_SCOPE = "NOT is_test"`: the single WHERE fragment for which leads count. L2 (built later)
  replaces it with `lead_quality.counted()` and makes `stage_counts` use `contacted()` (stage-based), `qualified()`, `won()`.
- `stage_counts(start, end) -> dict`: the existing `leads` query, moved out of `totals`. Adds nothing else.
  The "Lost reasons / max_stage" unit swaps `status IN (...)` for `max_stage` in this one place.
- `totals(start, end)`: returns `meta_leads` (from `ad_daily`) and `leads` = `received` (from `stage_counts`).
  `inbox` stays as an alias of `received` for one release.
- `build(kind, start=None, for_admin=False)`:
  - `funnel` = `rl.funnel([(rl.LEAD_STEP, now["leads"]), ("Contacted", ...), ("Qualified", ...), ("Won", ...)])`
  - `lead_gap` = `rl.lead_gap(now["leads"], now["meta_leads"])`
  - `headline` = `rl.headline(now, before, target, currency)` (currency: skip if the audit-fix workflow did it)
  - ideas: `concepts_api.qualified_by_ad(s, e)` fills `qualified`, and the target is `targets.lead_own()`
    (same as By idea; skip if already fixed). Each group adds `qualified` and `qualified_rate`.
  - `ads` rows gain `id` (used only by the signed-in view for 9.3 entity links; the frontend links nothing
    on a share link or a frozen copy). They also gain a `day`-free note: the client view shows "Top 6 of N".
  - `changes` = `rl.what_we_did(console_rows, outside_rows, currency)`, where:
    - console: `SELECT ..., (m.created_at AT TIME ZONE %s)::date AS day FROM meta_changes m WHERE m.ok AND ...`
    - outside: `SELECT level, entity_id, entity_name, field, old_value, new_value, at, (at AT TIME ZONE %s)::date AS day
      FROM status_events WHERE source IN ('poll','webhook') AND change_id IS NULL AND old_value IS NOT NULL
      AND field = ANY(%s) AND (at AT TIME ZONE %s)::date BETWEEN %s AND %s`
      with `OUTSIDE_FIELDS = status_history.OUTSIDE_FIELDS` (`configured_status` + D2's SETUP fields: budgets,
      spending limit, bid, start/end, audience; D2 lands first). The words come from `status_history.headline`, and
      `what_we_did` ignores fields it doesn't know.
  - `note` / `review` / `sent` blocks, see routes.
- `report_for_viewer(kind, start, user_or_none) -> dict`: one place that decides between live and frozen:
  - admin: live `build(..., for_admin=True)`, plus `review` and the saved note (`note.saved = True`)
  - client or share link: if the period's row has a `snapshot` → the snapshot, with `as_sent` set to the sent date
  - client in `wait` mode with no sent row → `{"waiting": True, "kind", "start", "end", "account", "latest_sent": {...} | None}`
  - otherwise live, without the note
- `qualified_by_ad(start, end)`: moved from `concepts_api.by_concept` (lines 92-95) into
  `concepts_api` as a function. `by_concept` and `reports_api.build` both call it. This extraction is
  allowed by C-9 because the function is reused.
- `reviewers()` = `notify.account_admin_ids()` (00-PLAN S3): active admins with `account_id IS NULL OR account_id = current`.
  The account's admins plus owners. Not `notify.admin_ids()`, which returns every account's admins.
- `send_due(now=None)`, the worker job per account. It replaces today's version:
  1. Settle stale claims: `UPDATE client_reports SET status='scheduled', send_at=now() WHERE status='sending' AND claimed_at < now() - interval '10 minutes'`.
  2. Send what's due: for each `scheduled` row with `send_at <= now()`, claim it with
     `UPDATE ... SET status='sending', claimed_at=now(), attempts=attempts+1 WHERE id=%s AND status='scheduled' RETURNING *`.
     Nothing to claim → skip it. On the first claim of a round, store `snapshot = build(kind, start)` with
     the note inside it. Then send to each active client not in `sent_to`. After each successful send, run
     `UPDATE ... SET sent_to = array_append(sent_to, %s)`. That fixes the audit finding about resends after a crash.
     A `MailError` or any other exception for one address: `last_error`, `status='scheduled'`,
     `send_at = now() + 1 hour`, and the loop moves on. When every active client is in `sent_to`:
     `status='sent'`, `sent_at=now()`, resolve the `report_review` alert, add an FYI alert `report_sent`
     (level info, kind event, resolved), and log `report.emailed`.
  3. Create the period that just came due: if `report_email` is on, `rl.email_due(mode, local, None)` says a
     period is due, and no row exists for it, then:
     - with no recipients or no mailbox, do nothing (as today)
     - mode `auto`: insert the row as `scheduled`, `send_at = now()`, and send it in the same pass (step 2)
     - mode `wait`: insert it as `waiting`, raise the `report_review` alert, and notify `reviewers()`
       through `notify.reach(..., "notify_alerts")` + `notify.queue(..., notify.link(href))` with button
       "Review it" and dedupe key `report_review:{kind}:{start}:{uid}`
  4. `jobs.py` keeps calling `send_due()` in the quick pass (every 30 s), so `jobs.wake()` after Send now
     means the email goes within seconds.
- Alerts: `report_review` rows are raised `kind: "event"`, `resolved: False`: an owner-closed event (00-PLAN C16).
  `alerts.run`'s closing loop touches only conditions, so it needs **no change**. `reports_api` sets `resolved_at` on
  send or skip. `inbox.CATEGORY` gains `"report_review": "system"` and `"report_sent": "system"`. Needs action
  includes open warn events, so `report_review` is there. Today reads the Needs-action set (00-PLAN C17), so
  `open_alerts`' 3-day window doesn't apply. Not snoozable, not diagnosable, no Done action.
- In step 2's claim, before `snapshot = build(...)`: `numbers_check.ensure_period(start, end)` when D1 is present
  (any failure is logged and the send goes on). The snapshot includes D1's stamp as of sending.

### Routes (all under `/api/reports`, account from `account_ctx`, JSON writes need the existing cross-site header)

| Route | Who | What |
|---|---|---|
| `GET ""?kind&start` | admin (owner or account admin), client | `report_for_viewer`. Member → 403 (unchanged). |
| `GET /periods?kind=week\|month` | admin, client | The last 12 periods: `{kind, start, end, label}`. Admins also get `status` and `sent_at_label`. Clients in `wait` mode get only sent ones. Feeds the 9.4 earlier-period picker. |
| `GET /sent?kind&start` | admin | The frozen snapshot of that period, for "See what was sent"; 404 when none. |
| `PUT /note` `{kind, start, note, note_at?}` | admin | Upsert the row (status `waiting` if new and mode `wait`; if new and mode `auto`, the row is created `waiting` only when the period is still before its 8 AM send, otherwise as `waiting` too: a saved note never sends by itself). Trims; empty → NULL; > 2,000 characters → 400 `field: note` "Keep the note under 2,000 characters". If `note_at` is given and differs from the stored one → 409 "Someone else changed this note a moment ago. Reload to see it." After a send, also updates `snapshot.note` (clients see the new wording; no email goes). Logs `report.note_saved`. |
| `POST /email-preview` `{kind, start, note}` | admin | `{to: [...], from, subject, text}` from `rl.email_text` with the typed (unsaved) note. Read-only. |
| `POST /send` `{kind, start, when: "now"\|"8am", note, expect_to: [emails]}` | admin | Refused when the period isn't complete (400 "You can send it once the week is over."), with no recipients, or when the mailbox isn't set up. `expect_to` must match the current recipients (else 409 "The client list changed. Check who it goes to and try again." so a new or removed client is never a surprise). Saves the note, sets `status='scheduled'`, `send_at = now()` or `rl.next_send_at(local)`, `decided_by/at`. For `now`, also `jobs.wake()`. Refused from `sending`/`sent` (use `/resend`). Logs `report.send_now` / `report.scheduled`. |
| `POST /hold` `{kind, start}` | admin | Creates the row as `waiting`, or moves `scheduled` back to `waiting`. Refused while `sending`. Logs `report.held`. |
| `POST /skip` `{kind, start}` | admin | `waiting`/`scheduled` → `skipped`, and resolves the review alert. Logs `report.skipped`. |
| `POST /unskip` `{kind, start}` | admin | `skipped` → `waiting` (no time limit: nothing was sent). |
| `POST /resend` `{kind, start, expect_to}` | admin | `sent` → `scheduled` now, `round+1`, `sent_to='{}'`, `snapshot=NULL` (taken again at claim). Logs `report.resent`. |
| `PUT /settings` | admin | Also takes `review: "auto"\|"wait"`; anything else → 400 `field: review`. `GET /settings` returns it. |

Account admins act only on their own account (account context + RLS). The owner acts on the account
chosen in the switcher, as everywhere else. Clients get 403 on every write. `/api/reports/shared?t=`
(no sign-in) uses `report_for_viewer(..., None)` and keeps the same token and checks (expiry, epoch,
closed account).

---

## Frontend

Files: `report.html`, `js/report.js`, `css/app.css` (or `shell.css`, wherever 9.2 puts page parts),
`settings.html`, `js/settings.js` (panel + activity labels), `js/home.js` / the 9.4 Today queue and
`js/inbox.js` only if they map rules to words themselves (the server sends title, lines and href).

Names (pass the ad-blocker guard; avoid `.report`, `.sheet`, `.step`, `.confirm`): prefix `rv-`.
- `#rv-bar` (section, `no-print`, hidden for clients and share links)
- `#rv-state` (pill + line), `#rv-note` (textarea), `#rv-note-save`, `#rv-preview` (details), `.rv-mail` (pre-wrapped email text)
- `#rv-send`, `#rv-later`, `#rv-hold`, `#rv-skip`, `#rv-unskip`, `#rv-sent`, `#rv-resend`
- in the report: `.r-sec.r-note` with `.rv-text` (`white-space: pre-line`), `.r-gap` (Meta line under the funnel)
- settings: radios `#rep-review-wait`, `#rep-review-auto` (name `review`)

Reused: `confirmDialog`, `toast`, `fieldError`, `guardLeaving` / `markSaved` (note typed but not saved),
`editing()` (auto refresh skips while the note has focus), `errorState` / `showLoadError`, `setCrumbs`,
`format.js` `money` / `count` / `dayLabel` / `plural`, pill classes. In 9.3, `entityLink()` for ad names in
the signed-in "Why" table only.

### Review bar (admins)

```
[Waiting for you]  Nothing goes to masha@burdanova.com until you press Send.

Our note (optional)
┌──────────────────────────────────────────────────────────┐
│ Anything the numbers don't say: why an ad was turned off, │
│ what we're trying next, a question for them.              │
└──────────────────────────────────────────────────────────┘
Shown first in the report and the email. Clients see it once the report goes out.   [Save note]

▸ Preview the email

[Send now]  [Send at 8 AM]  [Don't send this one]
```

- Label: **Our note (optional)**. Placeholder: "Anything the numbers don't say: why an ad was turned off,
  what we're trying next, a question for them." Hint: "Shown first in the report and the email. Clients
  see it once the report goes out." Counter shown only past 1,800 characters: "1,950 of 2,000".
- **Save note** → toast "Note saved". Saved on a sent report → toast "Note saved. The report link shows
  the new wording; no new email was sent."
- The note shows live in the report preview below as it is typed.
- **Preview the email** opens: "To: …", "Subject: …", then the body in `.rv-mail`. It refreshes when opened
  and 600 ms after typing stops while open.
- **Send now** → confirm: title "Send the report now?", body "It goes to {who} with a link that works for
  90 days. The figures are frozen as they are now.", button "Send now". Then the pill shows "Sending…".
  The page re-reads every 3 s for up to a minute. On "Sent …" → toast "Report sent".
- **Send at 8 AM** → confirm: title "Send it at 8 AM?", body "It goes to {who} on {when_label}. You can
  hold it until then.", button "Send at 8 AM".
- **Hold it** → no dialog; toast "Held. It waits for you now."
- **Don't send this one** → no dialog; toast with **Undo** (calls `/unskip`): "This report won't be sent."
- **See what was sent** opens the frozen copy in the same page (`?kind&start&sent=1`), headed "As sent on
  Nov 16, 2026" with a "Back to today's figures" link.
- **Send again with today's figures** → confirm: title "Send it again?", body "{who} get a new email marked
  'updated', with today's figures. The copy sent before is replaced.", button "Send again".
- Errors: the server's message in a toast. A `field` error goes under the textarea. A 409 on the client
  list re-reads the bar and shows the new recipients.

### Report changes (all viewers)

- Section 0 **Our note** (only when visible): the text, then "— {first name of note_by}".
- Figures row: **Leads** = leads received, with small text under it, "Meta counted 22" (only when different; D1 later shows the pair "Meta 22 · Received 20").
  **Cost per lead** = spend ÷ leads received.
- Funnel: first row "Leads received"; every rate is labelled with its base (`of`), e.g. "75% of Leads received". Under the table, `.r-gap` shows `lead_gap.text` when present.
  Admins also get, when Meta counted more: "If this stays, check that new leads reach the console:
  Settings → Meta." (link)
- "Why" table: the Leads column heading becomes "Leads (Meta)". Caption "Top 6 of 9 ads by spend" when
  more than 6 ads spent money.
- Ideas sentence adds the qualified share when the best group has leads: "Of the ideas behind the ads,
  **Pain statement** brought the cheapest leads (96% sure); 3 of its 12 leads qualified."
- What we did: each line is dated by its local `day`. Lines from outside the console end with
  " (in Ads Manager)". Example: "Nov 12 Ad “N3”: turned off (in Ads Manager)".
- Footer on a frozen copy: "Figures as sent on Nov 16, 2026."
- First footnote becomes: "Leads are the people who reached your leads list from the lead forms (test entries
  left out), by the day they arrived; Meta's own count, under each ad set's attribution setting, is shown
  beside them. Qualified and won come from your leads list. In the table of ads, leads are Meta's count per ad."
- Client in `wait` mode, unsent period: "This report is still being prepared. It will reach you by email."
  plus "Open the last one we sent (Week of Nov 2)" when one exists. Otherwise: "Nothing has been sent yet."

### Settings → Clients and reports

Below "Email the report to this account's clients":

> **Before it goes out**
> ( ) Wait for me: I read it, add a note if I want, and press Send
> ( ) Send it without my review, at 8 AM
> *Either way you can open it first on Reports and add a note.*

The save button stays "Save". `rep-state` pill becomes "Weekly · waits for you" or "Weekly · sent by
itself". Activity labels: `report.note_saved` "Wrote the report note", `report.send_now` "Sent a report",
`report.scheduled` "Set a report to go out at 8 AM", `report.held` "Held a report", `report.skipped` "Chose
not to send a report", `report.resent` "Sent a report again".

### Inbox and Today

- Needs action: "Weekly report for Burdanova is waiting for you" (lines as in `review_alert`). Clicking it
  opens Reports at `#review`, which scrolls to and focuses `#rv-note`.
- FYI: "Weekly report sent to 1 client" (info, resolved). It never pushes.
- Today (9.4 queue): the open `report_review` ranks with the other decisions and links the same way.

---

## Interaction with other features

| Feature | How this unit fits |
|---|---|
| 9.4 Reports (period picker, print, confirm before sharing, print-safe colours) | The picker reads `GET /periods` and shows each period's status pill for admins. `#rv-bar` is `no-print`. The confirm before **Share a link** adds: "Your note shows on the link once the report has been sent." |
| 9.2 one vocabulary (`format.js`) | Uses "Leads", "Cost per lead", "Cost per qualified lead" from there. Pills reuse the shared Status component. |
| 9.3 entity links | Only the signed-in admin/client view links ad names. A share link or a frozen copy never does: those visitors have no session. |
| 9.4 Inbox Needs action / FYI, Today queue | `report_review` = needs action and closes itself on send or skip. `report_sent` = FYI. Clients never see either (the client Inbox filter keeps only `status` items). |
| 9.1 Reports hidden from members | Unchanged. New routes 403 for members. |
| Record budget and schedule edits in Ads Manager (D2, lands first) | This unit reads `status_history.OUTSIDE_FIELDS` and words every row with `status_history.headline`: "Ad set “Broad”: daily budget $20.00 → $30.00 a day (in Ads Manager)". |
| Lost reasons / highest stage reached (other unit) | Swap the stage predicate inside `stage_counts` for `max_stage`. Lost-reason counts can add one line under the funnel. Nothing else changes here. |
| Organic, repeat and junk leads (L2) | Replaces `LEAD_SCOPE` with `lead_quality.counted()` and appends the repeats clause to `lead_gap`. `lead_gap`'s "your leads list has more" text already covers organic leads. If organic leads are kept in the funnel, the footnote names them. |
| Deal value on Won (other unit) | Adds revenue to `totals`. Email and report gain "Clients won: N, worth $X" after the headline. `email_text` takes it from `report`, so its signature doesn't change. |
| Booked-call tracking (L1) | Inserts `("Booked a call", n, "Leads received")` after Contacted and sets `("Qualified", q, "Contacted")`. A booking-tool booking can come before Contacted, so its base is Leads received. That's why `funnel` takes a list with bases. |
| Restate older days (other unit) | Meta's numbers for a frozen report can change later. The frozen copy keeps them, and "Send again with today's figures" is the way to update the client. |
| Notifications (`notify`) | Uses `notify.reach` + `queue` + `link` (with `?acct=`). Recipients are `reviewers()` = `notify.account_admin_ids()` (S3, built by the audit fix or D2), not `admin_ids()`. |
| Audit-fix workflow, report findings | Folded in here; skip any that are already fixed: funnel base, ideas target (`targets.lead_own`), ideas qualified, `$` in headline/email, resend after a crash mid-loop (`sent_to` saved per address), UTC day in "What we did", duplicate ad names / "Top 6 of N". |
| Claude (Desk) | No change. The Desk snapshot doesn't include notes. A later "Ask Claude to draft the note" can use `/desk.html?ask=` with the period's numbers. |
| Leak test, client read-only gate | GET routes are covered automatically. Every write is `admin_required`. |

---

## Edge cases

- **No clients / no mailbox:** no row is created and nobody is nagged. Reports shows why Send is off.
- **Client added after the email went out:** gets nothing on their own. The sent line names who got it, and
  "Send again" covers everyone. A client removed mid-send is skipped (the loop re-reads active clients for
  each address).
- **Double click on Send now, or two admins at once:** the second `/send` sees `scheduled`/`sending` and
  returns the current state. The worker claim (`WHERE status='scheduled'`) lets only one pass send. Each
  address is saved right after it goes, so a crash resends to at most the one address in flight.
- **Worker down at 8 AM:** catches up later that week (`email_due`, as today). A `scheduled` row past its
  `send_at` goes on the next pass.
- **Period not finished:** Send, Send at 8 AM and Resend are refused by the server. Hold and the note are allowed.
- **Older period never sent** (worker was off a whole week, or the mode was `wait` and nobody acted): it stays
  waiting in the Inbox. Sending it later works, and its subject keeps its own period label.
- **Mode changed while a period waits:** existing rows keep their state. Switching to "without review"
  doesn't release a waiting report: the Settings toast says "Reports already waiting still need your Send."
- **Emailing turned off while a report is scheduled by hand:** it still goes (an admin chose it). Settings
  shows "1 report is still set to go out on Mon, Nov 17, 8:00 AM" with a link.
- **Note edited after sending:** the frozen copy's note changes and no email goes. The activity log keeps who
  changed it and when.
- **Two admins editing the note:** `note_at` check → 409 with plain words, and the typed text is kept in the field.
- **Account closed:** the worker skips closed accounts (as now). Rows stay. Links are refused (existing check).
- **Time zone:** due times, `send_at`, "Send at 8 AM", `day` in What we did and labels all use the account's
  zone. DST nights are covered by `next_send_at` tests.
- **Share link for a period sent later:** the old live link now shows the frozen copy. That's intended:
  outsiders see what went out.
- **Skipped period, then shared:** live figures without the note (nothing went out).
- **Meta counted 0 and 0 leads received:** no gap line, and the funnel rates are blank (no division).
- **Big gap** (received < Meta by 2+ and 10%+): admins get the Settings → Meta hint. The existing tracking alert
  (Meta leads not reaching the console) stays the real warning.
- **Lead moved to Lost after Qualified:** counts drop (today's behaviour) until the max_stage unit lands.
- **Snapshot of a huge month:** bounded (6 ads, 5 tests, 15 shown changes plus a count), well under 50 KB.
- **Currency:** the snapshot keeps the account's currency as it was sent.

---

## Tests

### Unit (`backend/tests/test_report_logic.py`, no DB)

Existing tests change: `funnel` now takes a list; update `test_funnel_rates_are_shares_of_the_step_before`.

```python
class FunnelTests:
  funnel([("Leads received", 20), ("Contacted", 15), ("Qualified", 4), ("Won", 1)])
    == [{"step": "Leads received", "n": 20, "rate": None, "of": None},
        {"step": "Contacted", "n": 15, "rate": 75, "of": "Leads received"},
        {"step": "Qualified", "n": 4, "rate": 27, "of": "Contacted"}, {"step": "Won", "n": 1, "rate": 25, "of": "Qualified"}]
  funnel([("Leads received", 0), ("Contacted", 0), ("Qualified", 0), ("Won", 0)]) rates == [None, None, None, None]
  # invariant: nested counts never give a rate over 100 (exhaustive over 0..6 for each step, nested)
  for a in range(7) for b in range(a+1) for c in range(b+1) for d in range(c+1): all(r is None or r <= 100)
  # a Booked step with explicit bases (00-PLAN C2): 5 steps in, 5 out
  [r["rate"] for r in funnel([("Leads received",10),("Contacted",8),("Booked a call",5,"Leads received"),("Qualified",3,"Contacted"),("Won",1)])]
    == [None, 80, 50, 38, 33]
  # unknown base label → ValueError

class LeadGapTests:  (the four exact outputs listed under Backend)

class MoneyTests:
  [money(1234), money(1234, "EUR"), money(1234, "GBP"), money(1234, "CAD"), money(1234, "CHF"), money(None)]
    == ["$12.34", "€12.34", "£12.34", "CA$12.34", "12.34 CHF", "—"]
  headline({"spend_cents": 14000, "leads": 30, "qualified": 2}, {"spend_cents": 14000, "leads": 25, "qualified": 1}, 6000, "EUR")
    == "Cost per qualified lead was €70.00 against the €60.00 target (over by €10.00), down from €140.00 the period before. 2 qualified leads from €140.00 spent; at this volume the number is directional."

class WhatWeDidTests:
  console = [{"day": date(2026,11,10), "created_at": dt(10,9,0), "level": "adset", "entity_name": "Broad", "action": "budget", "old_value": "2000", "new_value": "2400"}]
  outside = [{"day": date(2026,11,9), "at": dt(9,18,0), "level": "ad", "entity_name": "N3", "field": "configured_status", "old_value": "ACTIVE", "new_value": "PAUSED"},
             {"day": date(2026,11,11), "at": dt(11,8,0), "level": "adset", "entity_name": "Broad", "field": "daily_budget", "old_value": "2400", "new_value": "3000"},
             {"day": date(2026,11,11), "at": dt(11,9,0), "level": "ad", "entity_name": "N4", "field": "learning", "old_value": "LEARNING", "new_value": "FAIL"}]
  [(i["day"].isoformat(), i["where"], i["text"]) for i in what_we_did(console, outside)] ==
    [("2026-11-09", "outside", "Ad “N3”: turned off (in Ads Manager)"),
     ("2026-11-10", "console", "Ad set “Broad”: daily budget $20.00 → $24.00 a day"),
     ("2026-11-11", "outside", "Ad set “Broad”: daily budget $24.00 → $30.00 a day (in Ads Manager)")]
  # unknown field (learning) is left out; budget words come from status_history.headline (D2), lowercased first letter;
  # other console words match report.js's current ACTION map

class EmailTests:
  r = {"account": "Burdanova", "kind": "week", "start": "2026-11-09", "headline": "Cost per lead was $5.00. 18 leads from $90.00 spent."}
  email_text(r, "Masha", "https://x/report.html?t=T", "N3 was turned off.") ==
    ("Burdanova: your ads report, Week of Nov 9",
     "Hi Masha,\n\nN3 was turned off.\n\nCost per lead was $5.00. 18 leads from $90.00 spent.\n\nThe full report: https://x/report.html?t=T\n(The link works for 90 days.)")
  email_text(r, None, L, None)[1].startswith("Hi,\n\nCost per lead")
  email_text(r, "Masha", L, None, round_=2)[0] == "Burdanova: your ads report, Week of Nov 9 (updated)"
  month: {"kind": "month", "start": "2026-10-01"} → subject "...: your ads report, Month of Oct 1"

class SendTimeTests (tz = ZoneInfo("America/Los_Angeles")):
  next_send_at(Mon 2026-11-16 07:59 LA) == Mon 2026-11-16 08:00 LA
  next_send_at(Mon 2026-11-16 08:00 LA) == Tue 2026-11-17 08:00 LA
  next_send_at(Sat 2026-10-31 21:00 PDT) == Sun 2026-11-01 08:00 PST, i.e. 16:00 UTC
  when_label(Mon 2026-11-17 08:00 LA, tz) == "Mon, Nov 17, 8:00 AM"   # = words.day_time
  who_label([]) == "nobody yet"; who_label(["a@x.com"]) == "a@x.com"; who_label(["a@x.com","b@y.com"]) == "a@x.com and b@y.com";
  who_label(["a@x.com","b@y.com","c@z.com"]) == "a@x.com and 2 others"

class ReviewStateTests: one case per row of the review_state table, asserting the whole dict, e.g.
  review_state(None, "wait", ["a@x.com"], True, True, True, mon_0900, tz) ==
    {"status": "waiting", "pill": ["warn", "Waiting for you"], "line": "Nothing goes to a@x.com until you press Send.",
     "actions": ["send_now", "send_later", "skip"], "later_label": "Send tomorrow at 8 AM"}
  review_state(None, "auto", ["a@x.com"], True, True, False, mon_0700, tz)["actions"] == ["send_now", "hold"]
  review_state(None, "wait", ["a@x.com"], True, False, False, ...)["actions"] == []        # not finished
  review_state(None, "wait", [], True, True, True, ...)["pill"] == ["", "No clients yet"]
  review_state({"status": "sending", "sent_to": ["a@x.com"]}, "wait", ["a@x.com","b@y.com"], ...)["line"] == "1 of 2 sent."

class VisibilityTests:
  [client_can_open("wait", None), client_can_open("wait", {"status": "waiting"}), client_can_open("wait", {"status": "sent"}),
   client_can_open("auto", None), client_can_open("auto", {"status": "skipped"})] == [False, False, True, True, True]
  [note_visible({"status": "waiting", "note": "x"}, True), note_visible({"status": "waiting", "note": "x"}, False),
   note_visible({"status": "sent", "note": "x"}, False), note_visible(None, False)] == [True, False, True, False]

class ReviewAlertTests: review_alert("Burdanova", "week", date(2026,11,9), ["masha@burdanova.com"]) == the dict under Backend
  and the monthly title "Monthly report for Burdanova is waiting for you"
```

`backend/tests/test_concepts_logic.py`: no change (the extracted `qualified_by_ad` is a query). Its use is
covered by QA.

### `qa/flows.cjs` (add after the existing Client reports block; update the existing "on Monday … once" check)

1. Seed (via `docker exec … python -c`) a week in account Burdanova QA: Meta `ad_daily.leads` = 6 and 4 leads in
   the console (one contacted, one qualified on a tagged ad). Report: the first funnel row reads "Leads
   received" and 4, and `.r-gap` contains "Meta counted 6 leads; 2 of them didn't reach your leads list". The
   "Contacted" rate is ≤ 100%. (The gap-of-1 wording is covered by the unit case `lead_gap(19, 20)`.)
2. Ideas: `/api/reports` → `ideas.groups[*].qualified` sums to 1.
3. What we did: insert a `status_events` row (poll, configured_status ACTIVE→PAUSED, change_id NULL) →
   the report lists it with "(in Ads Manager)".
4. With `report_review` unset (= wait) and `report_email` weekly: `send_due(monday 8:00)` returns 0 and sends
   no mail. `#rv-bar` shows "Waiting for you". An Inbox item "Weekly report for Burdanova QA is waiting for you"
   is open. The mail catcher holds a "Review it" notification for the admin, and none for the account admin of
   another account.
5. Client signed in (wait mode) opens that week: "This report is still being prepared"; no `#rv-bar`.
6. Admin types a note, **Preview the email** shows it before the headline, **Send now** + confirm → within 10 s
   the pill reads "Sent". The catcher has one email per client, starting with the note. The Inbox item is
   resolved, and an FYI "sent to 1 client" exists.
7. Second **Send now** (direct `fetch`) → no second email (`sent === 1`).
8. Share link and client view: "Our note" first, footer "Figures as sent on". Change the seed's numbers;
   the client still sees the sent figures, and the admin sees "See what was sent" plus today's figures.
9. Edit the note after sending → client view shows the new wording, and no new email arrives.
10. Auto mode: set `report_review=auto`, clear rows. Before 8 AM the bar shows "Goes out at 8:00 AM";
    **Hold it** → `send_due(8:00)` sends 0. Then **Send at 8 AM** → `send_due(next 8:00)` sends 1. This
    replaces the old `'1 0'` check, and the old check is kept as "auto mode, no row: sends once" (`'1 0'`).
11. **Don't send this one** → toast with Undo → Undo puts it back to waiting.
12. Roles: member gets 403 on `GET /api/reports`, `PUT /note`, `POST /send`. Client gets 403 on every write.
    An account admin of account 2 posting `/send` changes only account 2's row.
13. `expect_to` mismatch → 409 with "The client list changed".
14. Phone 390 px: `#rv-send`, `#rv-later`, `#rv-skip` ≥ 44 px tall; `#rv-note` computed font-size 16px; no
    horizontal overflow on report.html (the existing 10-page overflow check gains report.html with the bar).
15. Print: `#rv-bar` hidden in print media.
16. Ad-blocker guard and console-error guard pass (automatic).
17. Settings: choose "Send it without my review", Save, reload, still selected. The `rep-state` pill reads
    "Weekly · sent by itself".

### Fake Meta

None needed: the report uses only stored data, and email goes to the existing dev mail catcher on
`fake-meta` (`/mail/_sent`). `qa/run.sh` must also clear `client_reports` and the `report_review` alerts
between runs (same place it clears `status_events`).

---

## Rollout

- Migration `NNN_report_review.sql`: relative slot **N+1** in 00-PLAN (right after D2's); the actual number is the
  next free one at build time.
- Settings: `report_review` per account (`auto` | `wait`, default `wait`). The migration sets `auto` for
  every account that already has `report_email` on, so nothing changes silently on Update.
- `report_review` is an owner-closed event, so `alerts.run` needs no change. `inbox.CATEGORY` gains the two rules.
- README: under Pages, change Reports to "client reports with a review step: note, email preview, send now
  or at 8 AM". ROADMAP: a line under 7.3 or Phase 9, and a Progress log entry.
- What Eugene does after Update:
  1. Settings → Clients and reports: choose **Wait for me** or **Send it without my review** for each
     client account. Accounts that already emailed reports stay on "without my review".
  2. Next Monday at 8 AM he gets "Weekly report for … is waiting for you". He opens it, adds a note if he
     likes, and presses **Send now**.
  3. Nothing on the Mac and nothing on Meta.
- Unverified until live: delivery through the real mailbox (same path as today's report email), and how
  clients' mail apps show the note's line breaks.

---

## Effort

**M, about 2.5 days.**
- Backend: `report_logic` additions, `totals`/`build` changes, routes, the worker rewrite, migration (1 day)
- Frontend: review bar, report changes, Settings radios, phone layout (0.75 day)
- Unit tests plus 17 QA checks, leak test case, docs (0.75 day)

Risk is low. There are no Meta calls and no money paths. The send loop is the one place with concurrency,
and it reuses the claim pattern from `notify` / A8.
