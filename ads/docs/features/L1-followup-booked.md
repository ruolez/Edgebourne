# L1: Follow-up queue and booked calls (one design)

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build order and migrations:
>   - Phases A + B are build step **4** of 9, migration **N+3**. They depend on W2 (`funnel(steps)` with bases) and W1a (dialog parts, Needs-action triage).
>   - Phase C is step **9**, with no migration. It depends on L2's `contact.py` and on Eugene naming his tool.
> - C2: there's no `booked=` kwarg. The report inserts `("Booked a call", b, "Leads received")` and `("Qualified", q, "Contacted")` into W2's `funnel(steps)`.
> - C3: there's no "leads inbox" wording. "Cost per booked call" has the sub "from your leads", and the footnote reads "Booked calls come from your leads list, by the day the lead arrived."
> - C5: Contacted in reports is stage-based (`max_stage <> 'new'`). `first_contacted_at` means first try.
> - C6: there's no `bookings.contact_keys`. Phase C matches with L2's `contact.email_key` / `contact.phone_key` against the stored `leads.email_key` / `phone_key` of roots (`repeat_of IS NULL`). The tests use realistic data, since L2 treats 555 numbers and `example.com` as placeholders.
> - C10: undo goes through one route, `POST /api/leads/<id>/events/<event_id>/undo` (kinds `call`, `stage`, `lost_reason`; same person; 10 min). `CLIENT_LEADS` = `^/api/leads/\d+(/notes|/calls|/events/\d+/undo|/not-junk)?$`.
> - C11: the `lead_events.kind` CHECK also lists L2's kinds: `lost_reason`, `max_stage`, `repeat`, `returning`, `linked`, `unlinked`, `not_junk`.
> - C12: the client PATCH guard is `{"status","lost_reason","lost_note","next_step","next_step_done","meeting"}` when `client_lead_updates` is on.
> - C13: the one-tap Lost buttons send `lost_reason: "no_response"` with a note. **Move to Lost** after Wrong number opens L2's Lost dialog, with "Spam or fake" preselected only when the lead has junk flags.
> - C16: `booking_unmatched` is an owner-closed event (`resolved: False`), closed on match or dismiss. `booking_canceled` is info, raised resolved.
> - Security:
>   - The New → Contacted move on an outcome sends Contacted to Meta (an existing write on a new trigger), so it **needs Eugene's yes before build**. Without it, there's no automatic move, and the toast offers **Move to Contacted**.
>   - The booking token is looked up by `sha256(token)`, and `account_ctx` is set before any read or write.
>   - `bookings.payload` is nulled 30 days after processing.
>   - Recipients come from `notify.account_admin_ids()` or the lead's owner.

Two proposals from the audit, designed together because they share one history table and the **Booked a call** outcome:

- "Follow-up queue: call outcomes, next step and a lead history that is never pruned" (value high, effort M)
- "Booked-call tracking and cost per booked call" (value medium, effort M)

The design was checked against the code on 2026-11-11 (HEAD `c10378d`, migrations up to `030_ad_versions.sql`, with uncommitted QA edits from the audit-fix workflow). It has no Meta writes, no money paths and no new Meta reads.

---

## Goal

1. **No promised call-back depends on memory.** Every call attempt is recorded with an outcome. Every open lead has a visible next step with a due time, or shows up as "No next step". Due and overdue follow-ups reach the right person through `notify.py` and the 8 AM digest.
2. **One urgency rule.** Leads, Today, the reminders and the response line all agree on what "waiting for a first call" means: `first_contacted_at IS NULL`. Today, a note stops reminders but doesn't count as contact, so the two disagree. After this change, a call outcome, an email sent or a stage change sets `first_contacted_at`. A note no longer does.
3. **A lead's history is never lost.** A new `lead_events` table is excluded from `jobs.PRUNE` and backfilled from what `activity` still holds. It is the only source of the lead's History.
4. **Booked calls are counted.** `booked_at` / `meeting_at` are set by the call outcome, by hand, or by a signed booking-tool webhook. **Calls booked** and **Cost per booked call** appear between Contacted and Qualified in Results, the Ads manager, Compare and client reports. Today asks "Did the call happen?" once the time has passed.

Out of scope, each needing its own yes:
- Sending "Booked" to Meta as a CRM event. That is a new Meta write, so it is sketched only (see Rollout).
- Automatic stage moves from a booking tool. A stage move goes to Meta through `crm_events`, so only people move stages.
- Any lead being marked Lost automatically.

---

## User flow

Words used in the UI: **call** (never "meeting" or "appointment"), **next step**, **follow-up**, **booked call**, **No-show**. These go into `format.js` (UX-AUDIT 9.2's single vocabulary).

### Desktop: Leads

1. Eugene opens a lead. Under the reach buttons there is a new **Follow-up** box (`#fu-box`):
   - Call line: "No calls yet" or "Last try: no answer, Tue 3:10 PM · 2 tries, not reached yet"
   - Next step: "Next: Call back · today 4:00 PM" with **Done** and **Change**, or "No next step" with **Add next step**
   - Booked call, when there is one: "Call booked for Thu, Nov 13, 2:00 PM (booked by phone)" with **Moved** and **Canceled**
2. He clicks **Call (555) 123-4567**. On a desktop with no dialer, the `tel:` link does nothing. The outcome dialog (`dialog.fu-dialog`) opens after 400 ms either way. **Log a call** (`#log-call`) opens the same dialog without dialling, for calls made from his own phone.
3. Outcome dialog: "How did the call with Maria go?"
   - Five large buttons: **Talked to them** · **No answer** · **Left a voicemail** · **Booked a call** · **Wrong number**
   - "Note (optional)" field
   - **Not now**: closes the dialog and saves nothing
4. After he picks an outcome, the same dialog moves to step 2, "What's next?". The kinds are **Call back** · **Send proposal** · **Follow up** · **Something else…**. The times are **Later today (2 PM)** · **Tomorrow 9 AM** · **Thu, Nov 13 9 AM** (the "in 3 days" button shows its date) · **Pick a date…**. Two exits:
   - **Save** stores both steps.
   - **No next step** stores only the outcome.

   Each outcome fills in a sensible default:

   | Outcome | Preselected next step |
   |---|---|
   | No answer, Left a voicemail | Call back, Later today |
   | Talked to them | Follow up, In 3 days |
   | Booked a call | Step 2 becomes "When is the call?": Today / Tomorrow / Pick a date, a time field, and **Not sure yet** |
   | Wrong number | The dialog closes. The box shows "Wrong number. **Email them**" (if they left an email) or "**Move to Lost**" |

5. **Talked to them** and **Booked a call** on a **New** lead: **only after Eugene's explicit yes (open decision 3)** the lead also moves to **Contacted**, and the toast says "Logged: talked to them. Moved to Contacted. **Undo**". This move sends Contacted to Meta through `crm_events` when stage sending is on. That's an existing write type on a new trigger, so it isn't built without the yes. **Default without a yes:** no automatic move, and the toast says "Logged: talked to them." with a **Move to Contacted** button (one tap, a normal human stage move).
6. Moving a lead to **Contacted** or **Qualified** with the stage buttons opens only step 2 ("What's next for Maria?"). **No next step** is always allowed.
7. After **3 calls in a row with no answer**, the box shows one suggestion:
   - "3 tries, no answer. **Lost: couldn't reach**" if they were never reached
   - "**Lost: went quiet**" if they were reached before

   One tap moves the lead to Lost, with Undo. Nothing happens on its own.
8. The **History** section reads `lead_events`. Entries are grouped by day, use plain sentences from the server (`text`), and link the ad and campaign (`entityLink` from 9.3).

### Desktop: Leads list and filters

- A new select `#follow` sits next to the source select: **Any follow-up** · **Due today** · **Overdue** · **No next step** · **Calls booked**. It maps to `?due=today|overdue|none|booked`, so Today, the digest and notifications can link straight to it.
- Each row gets one chip (`.fu-chip`), the most urgent that applies:
  - "Overdue: Call back (Tue)" (warn)
  - "Call back · 4 PM"
  - "Call on Thu 2 PM"
  - "Did the call happen?" (warn)
  - "Tried 2×", which replaces the "waiting" clock on a New lead that was tried but not reached
- Header line `#response`: "Last 30 days: first try within 6 min for half of them · 4 of 9 within 5 min · 2 not tried yet · 31 calls, 11 talked to (35%)".

### Today

The 9.4 Today is one ranked queue. If 9.4 hasn't shipped yet, this becomes a **Follow up** card (`section.panel.fu-card`) next to "Call these first". Either way the server returns `follow.queue` already ranked by `followup.queue()`. One row per lead, each with one action:

| Row | Action |
|---|---|
| New lead under 1 h ("Call these first") | **Call** (opens the outcome dialog after dialling) |
| Booked call within the next hour: "Call with Ana Ruiz at 2:00 PM" | **Open** |
| New lead waiting over 1 h | **Call** |
| Overdue follow-up: "Overdue: Call back Tom Reed (since Tue 4 PM)" | **Call** / **Done** |
| "Did the call with Ana happen?" | **It happened** · **No-show** · **Moved** |
| Follow-up due later today | **Call** / **Done** |

- Footer line: "4 open leads have no next step", linking to `/leads.html?due=none`.
- "Call these first" changes its rule: New **and never tried** **and** no booked call coming up. A lead that was tried moves to the follow-up rows.
- Empty state: "No follow-ups due. Set a next step after each call and it shows up here on the day."

### Phone (390 px)

- The lead detail is already full screen.
  - The Call button stays first, full width. **Log a call** sits beside it as a 44 px secondary button.
  - The outcome dialog is a bottom-anchored `<dialog>`, full width, with 48 px buttons in one column.
  - The note field and `datetime-local` / `time` inputs are 16 px (8.11 rule).
- Dialling: tapping the `tel:` link on iOS and Android backgrounds the browser without unloading the page. The dialog is already open underneath, so when Eugene comes back from the call it is waiting for him. A `visibilitychange` listener puts focus back on the first outcome button.
- `sessionStorage` key `fu-pending` = `{lead_id, at}`. If the page *was* reloaded (a PWA cold start), it reopens the dialog for that lead when it's less than 2 h old. The value is wrapped in try/catch and cleared after any choice.
- Today rows stack: name and chip on the first line, buttons on the second. All targets are 44 px. Nothing overflows at 320 px (QA guard).
- Leads `#follow` select: full width under the search on phones.

### Booking tool (Phase C, once Eugene picks a tool)

1. Settings › Leads › **Booking tool** (account admins). Eugene picks his tool, copies the link "Paste this in your booking tool's webhooks", pastes the signing secret, and saves.
2. When someone books, their email or phone is matched to a lead from the last 90 days:
   - The lead gets the chip "Call on Thu 2 PM", and History says "Booked through Cal.com for Thu, Nov 13, 2:00 PM".
   - Their stage is **not** changed.
3. When nothing matches, an Inbox **Needs action** item appears: "A call was booked by someone who isn't in your leads". It has **Match to a lead** and **Not from an ad**.
4. A cancellation becomes an Inbox FYI item, "Ana Ruiz canceled their call", and Today suggests a Call back.

---

## Data model

One migration `NNN_followups.sql`, written in one go (§5 gotcha: dev applies a half-written file).

```sql
-- Follow-up queue and booked calls (L1). Lead history that is never pruned, call outcomes,
-- next step, booked calls, and bookings from a booking tool.

-- 1. Lead history. jobs.PRUNE never lists it.
CREATE TABLE lead_events (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor TEXT NOT NULL DEFAULT 'user' CHECK (actor IN ('user', 'system', 'meta', 'claude', 'booking')),
    kind TEXT NOT NULL CHECK (kind IN (
        'received', 'call', 'stage', 'owner', 'note', 'email', 'email_auto', 'alert_failed',
        'next_set', 'next_done', 'next_cleared',
        'booked', 'call_moved', 'call_canceled', 'call_held', 'no_show', 'booking_removed',
        -- L2's kinds, listed now so L2 needs no constraint change (00-PLAN C11)
        'lost_reason', 'max_stage', 'repeat', 'returning', 'linked', 'unlinked', 'not_junk')),
    outcome TEXT CHECK (outcome IN ('reached', 'no_answer', 'voicemail', 'wrong_number', 'booked')),
    ref_id BIGINT,                        -- lead_notes.id, lead_replies.id or bookings.id
    details JSONB NOT NULL DEFAULT '{}',
    undone_at TIMESTAMPTZ,                -- Undo marks, never deletes
    undone_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CHECK ((kind = 'call') = (outcome IS NOT NULL))
);
CREATE INDEX lead_events_lead ON lead_events (lead_id, at);
CREATE INDEX lead_events_calls ON lead_events (account_id, at) WHERE kind = 'call' AND undone_at IS NULL;
CREATE INDEX lead_events_account_idx ON lead_events (account_id);
ALTER TABLE lead_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON lead_events
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- 2. The lead's follow-up state (kept in step with lead_events by followup.py, one place).
ALTER TABLE leads
    ADD COLUMN call_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN unanswered_streak INTEGER NOT NULL DEFAULT 0,  -- calls since the last time they were reached
    ADD COLUMN ever_reached BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN last_call_at TIMESTAMPTZ,
    ADD COLUMN last_outcome TEXT,
    ADD COLUMN next_step_kind TEXT CHECK (next_step_kind IN ('call_back', 'proposal', 'follow_up', 'other')),
    ADD COLUMN next_step_text TEXT,                           -- only for 'other', at most 120 characters
    ADD COLUMN next_step_at TIMESTAMPTZ,
    ADD COLUMN next_step_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN booked_at TIMESTAMPTZ,                         -- first time a call was booked; kept after cancel / no-show
    ADD COLUMN meeting_at TIMESTAMPTZ,                        -- when the booked call is (NULL = "not sure yet")
    ADD COLUMN meeting_status TEXT CHECK (meeting_status IN ('scheduled', 'held', 'no_show', 'canceled')),
    ADD COLUMN booking_source TEXT CHECK (booking_source IN ('call', 'manual', 'calcom', 'calendly', 'savvycal', 'other')),
    ADD CONSTRAINT leads_next_step_whole CHECK ((next_step_kind IS NULL) = (next_step_at IS NULL));
CREATE INDEX leads_next_step_idx ON leads (next_step_at) WHERE next_step_at IS NOT NULL;
CREATE INDEX leads_meeting_idx ON leads (meeting_at) WHERE meeting_status = 'scheduled';
CREATE INDEX leads_booked_idx ON leads (booked_at) WHERE booked_at IS NOT NULL;

-- 3. Deliveries from a booking tool (Phase C). Kept, like webhook_events, but never pruned while unmatched.
CREATE TABLE bookings (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    provider TEXT NOT NULL CHECK (provider IN ('calcom', 'calendly', 'savvycal', 'other')),
    delivery_key TEXT NOT NULL,           -- sha256(external_id|event|start_at): a retried delivery is a no-op
    external_id TEXT,
    event TEXT NOT NULL CHECK (event IN ('created', 'rescheduled', 'canceled', 'no_show')),
    name TEXT, email TEXT, phone TEXT,
    start_at TIMESTAMPTZ, end_at TIMESTAMPTZ,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    matched_by TEXT CHECK (matched_by IN ('email', 'phone', 'hand', 'later_lead')),
    dismissed_at TIMESTAMPTZ, dismissed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    error TEXT,
    UNIQUE (account_id, provider, delivery_key)
);
CREATE INDEX bookings_pending ON bookings (id) WHERE processed_at IS NULL;
CREATE INDEX bookings_unmatched ON bookings (received_at) WHERE lead_id IS NULL AND dismissed_at IS NULL;
CREATE INDEX bookings_account_idx ON bookings (account_id);
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON bookings
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- 4. Backfill. Migrations run as the owner (no RLS), so account_id is copied explicitly.
INSERT INTO lead_events (account_id, lead_id, at, user_id, actor, kind, details)
SELECT a.account_id, l.id, a.at, a.user_id,
       CASE WHEN a.actor IN ('user', 'system', 'meta', 'claude') THEN a.actor ELSE 'system' END,
       CASE a.action WHEN 'lead.received' THEN 'received' WHEN 'lead.status' THEN 'stage'
                     WHEN 'lead.owner' THEN 'owner' WHEN 'lead.reply' THEN 'email'
                     WHEN 'lead.reply_auto' THEN 'email_auto' WHEN 'lead.email_failed' THEN 'alert_failed' END,
       a.details || '{"backfilled": true}'::jsonb
FROM activity a JOIN leads l ON l.id::text = a.subject AND l.account_id = a.account_id
WHERE a.action IN ('lead.received', 'lead.status', 'lead.owner', 'lead.reply', 'lead.reply_auto', 'lead.email_failed');

INSERT INTO lead_events (account_id, lead_id, at, actor, kind, details)
SELECT l.account_id, l.id, l.created_time, 'meta', 'received', '{"backfilled": true}'::jsonb
FROM leads l WHERE NOT EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id = l.id AND e.kind = 'received');

INSERT INTO lead_events (account_id, lead_id, at, user_id, actor, kind, ref_id, details)
SELECT n.account_id, n.lead_id, n.created_at, n.user_id, 'user', 'note', n.id, '{"backfilled": true}'::jsonb
FROM lead_notes n;
```

Notes on the model:
- `ON DELETE CASCADE` on `lead_id` matches `lead_notes`. Leads are never deleted in the product, only by QA scripts. "Never pruned" is enforced by a unit test on `jobs.PRUNE`, not by the schema.
- `notifications` stays as it is. Dedupe keys carry the due time (see Backend).
- The `leads` counters are a cache of `lead_events`. `followup.recount(lead_id)` rebuilds them from the events after every call write and every Undo. The pure `call_summary()` does the counting.
- No new `settings` keys for Phase A or B. Phase C adds the account keys `booking_tool`, `booking_hook_token` and `booking_hook_token_hash` (sha256 of the token, the only thing the webhook looks up; added to `ACCOUNT_KEYS`), plus `booking_secret` (in both `ACCOUNT_KEYS` and `SECRET_KEYS`, encrypted, masked in responses).

---

## Backend

### New modules

**`backend/lead_history.py`**: the one writer and reader of `lead_events`.

```python
KINDS = (...)  # mirrors the CHECK
def record(lead_id, kind, *, outcome=None, details=None, ref_id=None, actor=None, user_id=None, at=None) -> int
    """Insert a lead_event and mirror it to `activity` as action 'lead.<kind>' (Settings → Activity keeps working)."""
def for_lead(lead_id, tz) -> list[dict]          # rows + "text" from describe(), oldest first, undone ones flagged
def describe(ev, tz, names=None) -> str          # PURE: one plain sentence per event (table below)
def undo(event_id, user, now) -> dict | None     # same person, within 10 minutes, kind 'call' or 'stage'; sets undone_at
```

What `describe()` returns:

| kind / outcome | text |
|---|---|
| received | "Received from Meta (N1 · v2)" / "Received from Meta" |
| call reached | "Eugene called: talked to them" (+ " · ‘note’" first 80 characters) |
| call no_answer / voicemail / wrong_number | "Eugene called: no answer" / "…left a voicemail" / "…wrong number" |
| call booked | "Eugene called: booked a call for Thu, Nov 13, 2:00 PM" |
| stage | "Eugene moved it from New to Contacted" |
| owner | "Eugene gave it to Anna" / "Eugene took Anna off it" |
| note | "Eugene added a note" |
| email / email_auto | "Eugene emailed them: ‹subject›" / "Automatic reply sent: ‹subject›" |
| alert_failed | "The new-lead email to the team couldn't be sent" |
| next_set | "Next step: Call back, Wed, Nov 12, 9:00 AM" |
| next_done / next_cleared | "Done: Call back" / "Removed the next step" (system on Won/Lost: "Next step closed: lead is Won") |
| booked (actor booking) | "Booked through Cal.com for Thu, Nov 13, 2:00 PM" |
| booked (manual) | "Eugene marked a call booked for Thu, Nov 13, 2:00 PM" |
| call_moved | "Call moved to Fri, Nov 14, 10:00 AM" |
| call_canceled / call_held / no_show | "Call canceled" / "The call happened" / "No-show" |
| booking_removed | "Eugene removed the booked call" |
| any undone | the same text plus " (undone)" |

**`backend/followup.py`**: rules (pure) plus the write paths.

```python
OUTCOMES = ("reached", "no_answer", "voicemail", "wrong_number", "booked")
NEXT_KINDS = ("call_back", "proposal", "follow_up", "other")
PRESETS = ("later_today", "tomorrow_9", "in_3_days")
LATER_TODAY_HOURS, DAY_END_HOUR, MORNING_HOUR = 3, 18, 9
MEETING_GRACE = timedelta(minutes=60)
LOST_AFTER = 3

# --- pure
def due_at(preset, now, tz) -> datetime                       # UTC
def parse_local(value, tz, now) -> datetime                  # "2026-11-13T14:00" in account tz → UTC; ValueError with plain message
def clean_next(data, tz, now) -> dict                         # {kind, text, at} or ValueError("Pick when", field="when")
def call_summary(events) -> dict                              # {attempts, unanswered_streak, ever_reached, last_call_at, last_outcome}
def first_contact_at(events, stage_changes, emails) -> datetime | None
def lost_suggestion(summary) -> str | None                    # None | "couldnt_reach" | "went_quiet"
def meeting_state(lead, now) -> str | None                    # None | "upcoming" | "soon" | "check" | "held" | "no_show" | "canceled" | "unscheduled"
def chip(lead, now, tz) -> dict | None                        # {"tone", "text"} the one row chip
def queue(leads, now) -> list[dict]                           # ranked Today rows (bucket, sort time)
def call_stats(rows) -> dict                                  # {calls, talked, rate, booked}
def reminder_due(lead, now) -> bool                           # next step reached its time, within 24 h
def is_open(lead) -> bool                                     # status in new/contacted/qualified and not is_test

# --- database
def record_call(lead, user, outcome, note=None, meeting=None, next_step=None) -> dict   # one transaction
def set_next(lead, user, next_step) / done_next(lead, user) / clear_next(lead, user, reason)
def set_meeting(lead, user, at, source) / meeting_outcome(lead, user, status) / remove_meeting(lead, user)
def recount(lead_id)                                          # counters + first_contacted_at from lead_events
def leads_due(scope_where, scope_params, due, now, tz) -> (sql, params)   # the ?due= filter
```

Rules in plain terms:
- `due_at`:
  - **later_today**: now plus 3 h, rounded up to the hour. If that lands after 18:00 local, it becomes tomorrow at 9:00.
  - **tomorrow_9**: the next local day at 09:00.
  - **in_3_days**: local date plus 3 days, at 09:00. No weekend skipping: the button shows its date.
  - All maths is in the account time zone (`account_info.tz()`), which also handles DST.
- `parse_local` errors: in the past → "Pick a time from now on". More than 365 days away → "Pick a date within a year".
- `call_summary`:
  - Ignores undone events.
  - `unanswered_streak` counts no_answer / voicemail / wrong_number calls since the last reached or booked one.
  - `ever_reached` is true when any reached or booked call exists.
- `first_contact_at`: the earliest of the first call (any outcome), the first email sent and the first stage change away from New.
- `lost_suggestion`:
  - streak ≥ 3 and never reached → `couldnt_reach`
  - streak ≥ 3 and reached before → `went_quiet`
  - otherwise None
  - Not offered when the lead is Won or Lost.
- `meeting_state`:
  - status scheduled, `meeting_at` NULL → `unscheduled`
  - now < meeting_at − 60 min → `upcoming`
  - within the hour before → `soon`
  - meeting_at ≤ now < meeting_at + 60 min → `soon`
  - after that, still scheduled, stage not moved to qualified/won since `booked_at` → `check`
  - stage moved to qualified/won after `meeting_at` → `held` (shown as held, not written)
  - held / no_show / canceled as stored
- `queue` buckets, ordered by (bucket, time):
  - 0: never-tried New lead under 60 min (oldest first)
  - 1: meeting `soon`
  - 2: never-tried New lead ≥ 60 min
  - 3: overdue follow-up (oldest due first)
  - 4: meeting `check`
  - 5: follow-up due later today
  - Each lead appears once, in its lowest bucket. Test leads are left out.
- `reminder_due`: `next_step_at ≤ now < next_step_at + 24 h` and the lead is open.

**`backend/bookings.py` and `backend/booking_hooks.py`** (Phase C):

```python
# booking_hooks.py: PURE, one function per tool, fixtures in tests
def detect(headers) -> str | None                             # by which signature header is present
def verify(provider, raw, headers, secret, now) -> bool
def parse(provider, payload) -> dict | None                   # {external_id, event, name, email, phone, start_at, end_at}; None = ignore (other trigger)
def delivery_key(b) -> str

# bookings.py
# contact keys come from L2's pure module contact.py (email_key, phone_key; placeholders → None), 00-PLAN C6
def match(booking, candidates) -> (lead_id | None, matched_by | None)   # PURE
def process_pending()                                         # worker quick() job: match, apply to the lead, raise Inbox items
def link_later_lead(lead)                                     # called from leads.store_lead for a new real lead
def link(booking_id, lead_id, user) / dismiss(booking_id, user)
```

- Signatures (*verify every header name and payload path against each tool's current docs before building; tests use their documented examples*):
  - **Cal.com**: `X-Cal-Signature-256` = hex HMAC-SHA256(secret, raw body). Triggers `BOOKING_CREATED` / `BOOKING_RESCHEDULED` / `BOOKING_CANCELLED` / `BOOKING_NO_SHOW_UPDATED`. Attendee is `payload.attendees[0].email` / `.name`; phone is from `payload.responses` when asked; times are `payload.startTime` / `payload.endTime`; id is `payload.uid`.
  - **Calendly**: `Calendly-Webhook-Signature: t=<unix>,v1=<hex>`, HMAC-SHA256(secret, `"<t>.<raw>"`). Refused when |now − t| > 180 s. Events `invitee.created` / `invitee.canceled` / `invitee_no_show.created`. Subscriptions need a paid Calendly plan and one API call to create; the guide says so.
  - **SavvyCal**: `x-savvycal-signature` = hex HMAC-SHA256(secret, raw). Events `event.created` / `event.rescheduled` / `event.canceled`.
  - **Other (Zapier, Google appointment pages)**: header `X-Booking-Secret` equal to the secret (`hmac.compare_digest`). JSON body `{event, email, phone, name, start, end, id}`. Google appointment schedules have no webhook of their own, so this is the Zapier route.
- `match`:
  - Candidates are this account's non-test leads created in the last 90 days.
  - An email match beats a phone match.
  - Among several matches, prefer an open lead, then the newest.
  - No candidate → `(None, None)`.
  - Candidates are roots only (`repeat_of IS NULL`, L2), matched on `leads.email_key` / `leads.phone_key` against `contact.email_key(booking.email)` / `contact.phone_key(booking.phone)`.
- Applying a booking to a lead (one transaction, `actor='booking'`):

  | Event | Change to the lead |
  |---|---|
  | created | `booked_at = COALESCE(booked_at, received_at)`, `meeting_at = start_at`, `meeting_status = 'scheduled'`, `booking_source = provider`. Event `booked`. |
  | rescheduled | `meeting_at` changes. Event `call_moved`. |
  | canceled | `meeting_status = 'canceled'`. Event `call_canceled`. FYI alert `booking_canceled`. |
  | no_show | `meeting_status = 'no_show'`. Event `no_show`. |

  - The stage and `first_contacted_at` are never touched. A booking stops the 5 min / 1 h reminders through the urgency rule (a never-tried lead with a booked call is left out of "Call these first" and of reminders).
- Unmatched: `alerts.raise_found([...])` with:
  - rule `booking_unmatched`, kind `event`, `resolved: False` (an owner-closed event, 00-PLAN C16), level `warn`
  - dedupe `booking:<id>`, entity_id `booking:<id>`, href `/leads.html#booking=<id>`
  - title "A call was booked by someone who isn't in your leads"
  - lines `[name, email or phone, "Thu, Nov 13, 2:00 PM"]`

  It is resolved (`resolved_at = now()`) on link or dismiss. `inbox.CATEGORY` gets `booking_unmatched: "leads"` and `booking_canceled: "leads"`. 9.4 triage puts `booking_unmatched` under **Needs action** and `booking_canceled` (level `info`, so no push) under **FYI**.

### Changes to existing modules

| File | Change |
|---|---|
| `leads_api.py` | `_set_status` → `lead_history.record('stage')`, and on Won/Lost → `followup.clear_next(reason='closed')`. Owner change → `record('owner', details={from_id, to_id})`. `add_note` → `record('note', ref_id=note.id)`. Note no longer counts as contact (see reminders). `get_lead` returns `history = lead_history.for_lead()`, `follow = {summary, next, meeting, state, suggestion, chip}`. `list_leads`: `due=` filter, `follow` counts (`due_today`, `overdue`, `no_next`, `booked`), `chip` per row, `response` gains `calls` and `talked`. PATCH accepts `next_step` (object or null), `next_step_done` (true), `meeting` (`{at|preset|unscheduled}`, `{status: held|no_show|canceled}`, or null). The client check widens from `{"status"}` to `{"status", "lost_reason", "lost_note", "next_step", "next_step_done", "meeting"}` when `clients_update_leads` is on (same rule as notes; merged with L2, 00-PLAN C12). |
| `replies.py` | `send_now` / auto reply → `record('email'|'email_auto', ref_id=reply.id)` instead of only `log_activity` |
| `leads.py` | `fetch_and_store` → `record('received', actor='meta')`. After a new real lead: `bookings.link_later_lead(lead)` (Phase C) |
| `reminders.py` | `untouched(lead)` = `status == 'new' and not is_test and not first_contacted_at and meeting_status is distinct from 'scheduled'` (the `notes` condition is removed). `LEADS_SQL` stops counting notes. New pass `followups(now)` queues one reminder per due follow-up. New `digest_text(waiting, due, calls_today, now, tz)`, sent per person: admins get everything, teammates get the leads they own. `stats()` adds `calls`, `talked` from `lead_events`. |
| `home_api.py` | `call` query uses the same urgency rule (`first_contacted_at IS NULL AND (meeting_status IS DISTINCT FROM 'scheduled')`), and so does the "waiting more than an hour" attention item. New `follow = {queue: followup.queue(...)[:8], no_next: n}` from one query of open leads with a next step, booked call or no first contact, scoped by `visible_campaign_ids`. |
| `jobs.py` | `quick()` adds `("booking deliveries", bookings.process_pending)` (Phase C). `PRUNE` never deletes `lead_events` or `bookings` rows (guarded by a test); one PRUNE-style rule nulls `bookings.payload` on processed rows older than 30 days (PII kept only as long as needed; the normalized columns stay). |
| `crm_events.py` | No change. `booked` is not a stage. |
| `performance_api.overview_data` | `quality` adds `COUNT(*) FILTER (WHERE l.booked_at IS NOT NULL) AS booked`. `totals.booked`, `previous.booked`, per-ad `booked`. `tracks_bookings` = any non-test lead in the account with `booked_at`. |
| `ads_api._quality` | Returns `{ad_id: {"qualified": n, "booked": n}}` (callers updated: `tree_data`, `entities_api.compare_ads`), or a sibling `_booked()` to keep the change small. Prefer the sibling: fewer call sites move while 9.x edits these files. |
| `reports_api.totals` / `report_logic.funnel` | `booked` count (cohort: day the lead arrived, `lead_quality.counted()` once L2 lands). W2's `funnel(steps)` gets `("Booked a call", booked, "Leads received")` after Contacted and `("Qualified", q, "Contacted")`, only when `tracks_bookings` (00-PLAN C2: a booking-tool booking can precede Contacted, so its base is Leads received). A footnote adds "Booked calls come from your leads list, by the day the lead arrived." |
| `desk_api.snapshot` | Per-ad `booked` and account-wide `calls`, `talked`, `follow_ups_overdue`. No names or contact details. |
| `inbox.py` | `CATEGORY` gains the two booking rules |
| `settings_api.py` (Phase C) | GET `booking = {tool, url, secret_set, last_received_at, last_matched}`. POST `booking_tool`, `booking_secret`. `POST /api/settings/booking/rotate`. |
| `webhooks.py` (Phase C) | `POST /webhooks/booking/<token>`, described below |
| `accounts_api.CLIENT_LEADS` | Becomes `^/api/leads/\d+(/notes\|/calls\|/events/\d+/undo\|/not-junk)?$` (shared with L2, 00-PLAN C10) |
| `dev/qa_leaks.py` | `seed_marked` adds `once("lead_events", …)` and `once("bookings", …)` |
| `dev_seed.py` | A few seeded follow-ups, one booked call, one overdue (local only) |

### Routes

The roles are the existing ones:
- **owner admin**: `role='admin'`, no `account_id`
- **account admin**: `role='admin'` with `account_id`
- **teammate**: `member`; leads of assigned campaigns via `_get_visible`
- **client**: read-only; may update leads only when `client_lead_updates` is on

| Route | Who | Body / answer |
|---|---|---|
| `POST /api/leads/<id>/calls` | owner admin, account admin, teammate (own campaigns), client only with `client_lead_updates` | `{outcome, note?, meeting?: {preset: today\|tomorrow, time: "14:00"} \| {at: "2026-11-13T14:00"} \| {unscheduled: true}, next_step?: {kind, text?, preset? \| at?}}` → full lead (as GET). Errors: `outcome` not in list → 400 "Pick how the call went". Bad time → 400 with `field: "when"`. Test leads are allowed (QA), but excluded from stats. |
| `POST /api/leads/<id>/events/<event_id>/undo` (shared with L2; kinds `call`, `stage`, `lost_reason`) | the person who logged it, within 10 min (`lead_history.UNDO_MINUTES`) | → lead. 409 "Too late to undo; log another call instead" (call) / "Too late to undo; move it by hand" (stage) after 10 min |
| `PATCH /api/leads/<id>` (extended) | same as calls | `next_step`, `next_step_done`, `meeting` as above |
| `GET /api/leads?due=today\|overdue\|none\|booked` | anyone who sees Leads | existing shape plus `follow` counts and `chip` per lead |
| `GET /api/leads/<id>` | as today | plus `history` (from `lead_events`) and `follow` |
| `GET /api/home` | as today | plus `follow` |
| `POST /webhooks/booking/<token>` | no session. Token picks the account: a lookup on `sha256(token)` against `booking_hook_token_hash` across accounts, through the same narrow owner-side helper as `account_for_ad_account`, compared with `hmac.compare_digest`. `account_ctx.use(acct)` is set **before** any other read or write. Signature checked with that account's secret. | 403 on unknown token or bad signature (logged, no body). 413 over 64 KB. 200 `{ok: true}` for an ignored trigger. Stores the row then `jobs.wake()`. Not under `/api/`, so the CSRF guard doesn't apply. nginx: same location rules as `/webhooks/meta`. |
| `GET /api/bookings?unmatched=1` | account admin, owner admin | unmatched list (name, email, phone, time) |
| `POST /api/bookings/<id>/link` `{lead_id}` | account admin, owner admin | applies the booking as above, `matched_by='hand'`, resolves the alert |
| `POST /api/bookings/<id>/dismiss` | account admin, owner admin | resolves the alert; History not touched |
| `POST /api/settings/booking/rotate` | account admin, owner admin | new token; the old URL stops at once |

Read-only clients see `follow`, chips, history and booked counts on Leads and in reports. They never see the bookings list or the Settings section.

---

## Frontend

### New shared module `js/followup.js`

Used by `leads.js` and `home.js`, and by the 9.4 Today queue later. No ad-like names: prefix `fu-`, dialog class `fu-dialog`. The audit says not to reuse `.sheet`, `.step`, `.confirm` or `.report`.

```js
export const OUTCOMES = [["reached", "Talked to them"], ["no_answer", "No answer"], ["voicemail", "Left a voicemail"],
                         ["booked", "Booked a call"], ["wrong_number", "Wrong number"]];
export const NEXT_KINDS = [["call_back", "Call back"], ["proposal", "Send proposal"], ["follow_up", "Follow up"], ["other", "Something else…"]];
export function chipHtml(chip)                          // .fu-chip.warn / .fu-chip
export function boxHtml(lead, me)                       // the Follow-up box on the lead page
export async function logCall(lead, { dialled })        // opens the outcome dialog, posts, returns the updated lead
export async function askNext(lead, { title, preset })  // step 2 alone (stage moves, "Add next step", "Change")
export async function askMeeting(lead)                  // "When is the call?"
export function armDial(link, lead)                     // click → sessionStorage fu-pending + open logCall after 400 ms
export function resumePending(open)                     // on boot / visibilitychange
```

The dialog follows `confirmDialog`'s pattern: `<dialog>` + `<form method="dialog">`, focus on the first button, Escape = Not now. When 9.2 lands the shared Dialog, it moves to that. Money-dialog rules don't apply here (nothing costs money).

### Exact copy

| Where | Copy |
|---|---|
| Outcome dialog title | "How did the call with {first name or 'them'} go?" |
| Outcome buttons | Talked to them · No answer · Left a voicemail · Booked a call · Wrong number |
| Note field | label "Note (optional)", placeholder "What did they say?" |
| Dismiss | "Not now" |
| Step 2 title | "What's next?" (from a stage move: "What's next for {first name}?") |
| Time buttons | "Later today ({2 PM})" · "Tomorrow 9 AM" · "{Thu, Nov 13} 9 AM" · "Pick a date…" |
| Custom kind | label "What's the next step?", placeholder "e.g. Send the case study", max 120 |
| Step 2 buttons | "Save" (primary) · "No next step" |
| Booked step | title "When is the call?", buttons Today · Tomorrow · Pick a date…, field "Time", link "Not sure yet" |
| Toasts | "Logged: no answer. Next: Call back at 2 PM." · "Logged: talked to them. Moved to Contacted." · "Call booked for Thu 2 PM." each with **Undo** (calls only) |
| Box, no calls | "No calls yet." + buttons "Call {phone}" and "Log a call" |
| Box, calls | "Last try: {no answer}, {Tue 3:10 PM} · {2} tries, {not reached yet\|talked to them before}" |
| Box, next | "Next: {Call back} · {today 4:00 PM}" [Done] [Change] / overdue: "Overdue: {Call back} · was due {Tue 4 PM}" |
| Box, no next on an open lead | "No next step." [Add next step] |
| Box, booked | "Call booked for {Thu, Nov 13, 2:00 PM} ({booked by phone\|booked through Cal.com\|marked by hand})" [Moved] [Canceled] |
| Box, unscheduled | "Call booked, time not set." [Set the time] |
| Box, check | "Did the call on {Thu 2 PM} happen?" [It happened] [No-show] [Moved] |
| Box, after No-show | "No-show on {Thu 2 PM}." Step 2 preset Call back · Later today |
| Box, wrong number | "Wrong number." [Email them] or [Move to Lost] |
| Suggestion | "{3} tries, no answer." [Lost: couldn't reach] / "[Lost: went quiet]" |
| `#follow` options | Any follow-up · Due today · Overdue · No next step · Calls booked |
| Empty: Due today | "Nothing due today. Next steps you set show up here on their day." |
| Empty: Overdue | "Nothing overdue." |
| Empty: No next step | "Every open lead has a next step." |
| Empty: Calls booked | "No calls booked yet. Tap Booked a call after a call, or connect your booking tool in Settings." (the second half only for admins) |
| Response line | "Last 30 days: first try within {6 min} for half of them · {4} of {9} within 5 min · {2} not tried yet · {31} calls, {11} talked to ({35%})" |
| Today card title | "Follow up" with hint "{n} due today, {m} overdue" |
| Today empty | "No follow-ups due. Set a next step after each call and it shows up here on the day." |
| Today footer | "{4} open leads have no next step" → `/leads.html?due=none` |
| Today check row buttons | "It happened" · "No-show" · "Moved" |
| Results figures | "Calls booked" (sub: "{9} held, {2} no-shows") · "Cost per booked call" (sub: "from your leads") |
| Results / manager columns | "Booked" · "Per booked call" (title: "Leads that booked a call, by the day the lead arrived") |
| Report funnel step | "Booked a call" (rate shown as a share of Leads received) |
| Notification (due) | title "{Call back} {Maria Lopez}: due {3:00 PM}", lines [business, "Phone: …", "Last try: no answer, Tue 3:10 PM"], button "Open the lead" |
| Digest | title "Today: {2} leads waiting for a first call, {3} follow-ups due, {1} booked call" (parts with 0 left out). Lines "{Maria Lopez}, {Bakery}: waiting 14 h" · "{Call back} {Tom Reed}: overdue since Tue" · "Call at {2:00 PM}: {Ana Ruiz}". Link `/leads.html?due=today` |
| Inbox unmatched | "A call was booked by someone who isn't in your leads" + [Match to a lead] [Not from an ad] |
| Inbox canceled | "{Ana Ruiz} canceled their call ({Thu 2 PM})" |
| Settings › Booking tool | heading "Booking tool". Help: "When someone books a call through your booking page, the console finds the lead and shows the call." Select "Which tool": Cal.com · Calendly · SavvyCal · Something else (Zapier). URL row "Paste this in your booking tool's webhooks" + [Copy]. Field "Signing secret" (password field, masked once saved, "Saved" chip). Status "Last booking: {Tue 3:10 PM}, matched to {Maria Lopez}" / "No bookings received yet." Button "Make a new link" → confirm "The old link stops working at once. Paste the new one in {Cal.com}." |
| Match dialog | title "Which lead booked this call?", search field "Search leads", list rows name · business · arrived; button "Match"; secondary "Not from an ad" |

### Pages touched

- **`leads.html` / `leads.js`**
  - `#follow` select, the box, chips, history from the server's `text`
  - `#booking=<id>` hash opens the match dialog (admins)
  - The note form loses the "stops reminders" side effect. On a never-tried New lead, a hint under it says "Called them? Use Log a call so the reminders stop."
- **`home.js`**: follow-up card or queue rows. "Call these first" gets the new rule and `armDial` on its Call buttons.
- **`performance.js`**: two figures and two table columns, only when `tracks_bookings`.
- **`manager.js`**:
  - Column registry gains `booked` and `cpb`.
  - `results` sets add them after `cpl` when `tracks_bookings`; otherwise they are available under column picking.
  - The quick-look drawer gets "Booked" and "Per booked call".
- **`compare.js`**: two metric rows. No change to the verdict rule.
- **`report.js`**: the funnel step comes from the server.
- **`settings.js`**: the Booking tool section (9.4 "one section at a time": put it under **Leads**, next to Lead replies). Old anchors keep resolving.
- **`css/app.css`**:
  - `.fu-box`, `.fu-chip(.warn|.ok)`, `.fu-dialog`, `.fu-outcomes`, `.fu-times`, `.fu-card`, `.fu-row`
  - The `.read-only` list adds `.read-only:not(.client-leads) .fu-actions`, `#log-call` and `[data-fu]`
  - Phone rules: one column, 48 px outcome buttons, 16 px fields

---

## Interaction with other features

| Feature | How they fit |
|---|---|
| UX-AUDIT 9.2 `format.js` vocabulary | Add OUTCOMES, NEXT_KINDS, "Calls booked", "Per booked call", "No-show", "Follow-up" to `format.js`. "call" is the only word for a booked call (never meeting or appointment). |
| 9.2 one Dialog / Empty state | `fu-dialog` and the empty states above move onto the shared parts when they land. Until then, `confirmDialog`'s markup pattern. |
| 9.3 entity links / pushState | History rows link ad and campaign. `#booking=` and `#lead=` go through the same hash handling (Back closes the lead, 9.3). |
| 9.4 Today queue | `followup.queue()` *is* the leads part of the ranked queue. One urgency rule (`first_contacted_at IS NULL`, no booked call) shared by Leads, Today, reminders and the attention item, as 9.4 asks. Undo on stage change (9.4) uses `lead_history.undo` on `stage` events too. |
| Inbox Needs action / FYI | Only booking problems enter the Inbox (`booking_unmatched` Needs action, `booking_canceled` FYI). Follow-ups due are **not** Inbox items, because 9.4 removes duplicates between Today and Inbox. They live in Today, Leads and notifications. |
| Leads section | Filters via `?due=`, chips, response line. The "Undo on stage change" and "Clear-filter action" from 9.4 cover `#follow` too. |
| Creative section / Gallery / Ideas | Not in this unit. `gallery.py` cards can add booked counts later from the same `booked_at` cohort query. |
| Proposal "Lost reasons, highest stage reached" | `lead_events` stage rows are the clean source for backfilling `max_stage`. "Lost: couldn't reach" / "went quiet" map to reason `no_response`. The one-tap sends `{status: "lost", lost_reason: "no_response", lost_note: "Couldn't reach after 3 tries" | "Went quiet after 3 tries"}` (L2 lands before Phase C, after A+B; until then `lost_reason` is ignored by the server). **Move to Lost** after Wrong number opens L2's Lost dialog, with "Spam or fake" preselected only when the lead has junk flags. Booked is not a stage, so `max_stage` stays the 5 stages. |
| Proposal "Organic, repeat and junk leads" (L2) | One normalizer: L2's pure `contact.py` (`email_key`, `phone_key`, placeholders → None). Phase C matches stored keys of roots (`repeat_of IS NULL`), newest open first. |
| Proposal "Fix the client report funnel" | The funnel gains Booked between Contacted and Qualified, only for accounts that track bookings. "Contacted" stays stage-based (`status <> 'new'`), not "tried": a no-answer attempt is not contact in the report. |
| Proposal "Deal value on Won" | Same lead-page dialog pattern (`fu-dialog` look) for the value prompt. Independent data. |
| Proposal "Acknowledge or snooze alerts, plus lead-quality alerts" | Its "overdue follow-ups" rule should not be added. Overdue follow-ups are handled here by direct reminders plus the digest. If a rule is wanted, it reads `followup.reminder_due`. |
| Proposal "Diagnose with Claude from any alert or Inbox item" | `booking_unmatched` items needn't offer Claude (nothing to diagnose). Snapshot booked counts let Claude judge ads by booked calls. |
| `crm_events` (1.1) | Unchanged. Human stage moves from Talked to them / Booked a call (New → Contacted) send Contacted as today. Booking-tool deliveries never move stages. |
| `notify.py` | New kind `followup` through `reach(..., "notify_reminders")`. Dedupe `followup:{lead}:{epoch of next_step_at}:{uid}`, so a rescheduled step reminds again and a retry never does. |
| Agency mode / RLS | Two new account tables with `account_isolation`. The booking token resolves the account *before* any write. `qa_leaks` seeds both. |
| Desk / bridge | No bridge change. The snapshot gains counts only. |

---

## Edge cases

- **Tel link on desktop does nothing**: the dialog opens anyway. **Log a call** exists for calls made elsewhere.
- **Phone page reloaded during the call** (PWA cold start): `fu-pending` in sessionStorage reopens the dialog if it is under 2 h old. If storage throws (private mode), nothing reopens, and **Log a call** remains.
- **Two people log the same lead at once**: both events are kept, and `recount` is idempotent (it rebuilds from events inside the transaction, `SELECT … FOR UPDATE` on the lead row).
- **Undo**:
  - Only the person who logged it, within 10 min. The event is marked undone, never deleted.
  - Undoing the first attempt re-derives `first_contacted_at` from the remaining events (it may become NULL, and reminders resume only if the lead is still under 24 h).
  - A New → Contacted move done by the outcome is *not* undone automatically. The toast's Undo covers the call, and 9.4's stage Undo covers the stage. The toast says both happened.
- **Next step in the past** (picked yesterday, saved today): refused with "Pick a time from now on". Presets can't produce the past.
- **Late-evening "Later today"**: rolls to tomorrow 9 AM, and the button label shows that ("Later today (tomorrow 9 AM)").
- **DST**: presets and `parse_local` work in the account zone (unit tested on 2026-11-01).
- **Account in another time zone than the browser**: times are shown and entered in the account zone. Labels add the zone abbreviation when it differs from the browser's (`Intl` check).
- **Lead moved to Won/Lost with a next step**: the step is closed by the system ("Next step closed: lead is Won"). A booked call on a Lost lead stays visible but leaves the Today queue.
- **Lead reassigned**: due reminders go to the new owner. `next_step_by` is used only when there is no owner. With no owner and no setter, they go to admins.
- **Worker down for hours**: due reminders catch up within 24 h of the due time. Older ones are dropped silently (the digest still lists them as overdue).
- **Note-only leads after Update**: leads that had only a note are reminded again only if under 24 h old. On Update day that's at most a few leads; the Rollout note tells Eugene.
- **Old history**: `activity` older than 180 days is already gone. Those leads start their history with "Received from Meta" (backfilled from `created_time`) plus their notes. The History footer says "History before {date of the oldest activity row} was not kept." when the backfill flag is set and the lead is older than that date.
- **Test leads**: may be logged (QA), never counted in stats, Today, digest or cost per booked call.
- **Booked without a time** ("Not sure yet"): counts as booked. Chip "Call booked, time not set". No check row until a time is set. Today shows it under "No next step"-style nudges only if over 3 days old.
- **Booked twice / rescheduled many times**: `booked_at` keeps the first booking (the cost-per-booked-call cohort is stable). `meeting_at` follows the latest.
- **Canceled, then booked again**: `meeting_status` back to scheduled, `booked_at` unchanged.
- **Booking arrives before the lead** (someone books from the website, then fills the form): it stays unmatched with an Inbox item. When the lead arrives within 14 days, `link_later_lead` links it (`matched_by='later_lead'`) and resolves the item.
- **Booking matches a test lead or a lead over 90 days old**: no match → Inbox item (Eugene can match by hand).
- **Same email on two leads**: newest open lead wins. History on the other lead is untouched. The match dialog shows both when matched by hand.
- **Phone formats**: "+1 (555) 000-1111", "555-000-1111" and "15550001111" all key to `5550001111`. Numbers under 7 digits don't match. Non-US numbers use the last 10 digits, which is the same rule as the repeat proposal (documented limitation).
- **Webhook replay or retry**: `delivery_key` unique, so a repeat is a no-op 200. Calendly's timestamp tolerance blocks old replays.
- **Wrong or missing secret**: 403, logged as `booking.rejected` once per hour per account, so there's no log flood. Settings shows "Last refused: {time} (signature didn't match)".
- **Token rotated**: the old URL returns 403 immediately.
- **Agency mode**: each account has its own token, secret and tool. An unknown token never falls back to account 1 (unlike lead webhooks).
- **Client roles**:
  - Read-only clients see chips and history, no buttons.
  - With `client_lead_updates`, they can log calls and set next steps like a teammate, but not use booking settings or the match dialog.
- **Cost per booked call with tiny numbers**: shown as a plain figure, never a verdict. The Compare verdict rule (3 results, 2× target) is unchanged, and booked doesn't feed it. Accounts that never booked anything don't see the columns or the report step (`tracks_bookings`).
- **Ad blocker**: all new names use `fu-`, `booking`, `lead_history`. None start with ad-/ads-/adset/sponsor/banner/promo. QA's guard covers them.

---

## Tests

### Unit (`backend/tests/test_followup_logic.py`, `test_lead_history_logic.py`, `test_bookings_logic.py`; no database)

Constants: `LA = ZoneInfo("America/Los_Angeles")`, `NOW = datetime(2026, 11, 11, 18, 20, tzinfo=timezone.utc)` (Wed 10:20 AM LA).

**`due_at`** (`describe("due_at")`)

| preset | now (LA) | expected (UTC) |
|---|---|---|
| later_today | Wed 10:20 | 2026-11-11 22:00 (2 PM LA) |
| later_today | Wed 16:30 | 2026-11-12 17:00 (Thu 9 AM LA; 19:30 → 20:00 is past 18:00) |
| later_today | Wed 14:00 | 2026-11-12 01:00 (Wed 5 PM LA; exactly on the hour stays) |
| tomorrow_9 | Wed 10:20 | 2026-11-12 17:00 |
| tomorrow_9 | Sat 2026-10-31 20:00 | 2026-11-01 17:00 (PST after the DST change) |
| in_3_days | Wed 10:20 | 2026-11-14 17:00 (Sat 9 AM; no weekend skipping) |

**`parse_local`**
- `"2026-11-13T14:00"` → 2026-11-13 22:00 UTC
- `"2026-11-10T09:00"` → ValueError "Pick a time from now on"
- `"2027-11-12T09:00"` → ValueError "Pick a date within a year"
- `"tomorrow"` → ValueError "Pick a date and time"

**`clean_next`**
- `{kind: "other", text: "x"*121, preset: "tomorrow_9"}` → ValueError (field `text`)
- `{kind: "lunch", preset: "tomorrow_9"}` → ValueError "Pick a next step"
- `{kind: "call_back"}` → ValueError (field `when`)
- `{kind: "proposal", preset: "tomorrow_9"}` → `{"kind": "proposal", "text": None, "at": 2026-11-12 17:00 UTC}`

**`call_summary`**, with events built from outcome lists at 1-minute steps:

| outcomes | expected |
|---|---|
| `[]` | `{"attempts": 0, "unanswered_streak": 0, "ever_reached": False, "last_outcome": None, "last_call_at": None}` |
| `["no_answer", "voicemail", "reached", "no_answer"]` | attempts 4, streak 1, ever_reached True, last_outcome `"no_answer"` |
| `["no_answer", "no_answer", "no_answer"]` with the 2nd undone | attempts 2, streak 2 |
| `["wrong_number"]` | attempts 1, streak 1, ever_reached False |

**`lost_suggestion`**
- streak 3, never reached → `"couldnt_reach"`
- streak 3, reached before → `"went_quiet"`
- streak 2 → None
- streak 5 with status won → None

**`first_contact_at`**
- calls at 10:05, email at 10:02, stage change at 10:30 → 10:02
- nothing → None
- the only call undone → None

**`meeting_state`** (`meeting_at` = NOW + offset, status scheduled, stage contacted, `booked_at` NOW − 1 day)

| offset | expected |
|---|---|
| +3 h | upcoming |
| +30 min | soon |
| −30 min | soon |
| −61 min | check |

Plus:
- −61 min with status moved to qualified at −10 min → held
- `meeting_at` NULL → unscheduled
- stored no_show → no_show

**`queue`**, six leads (ids 1–6):
1. New, never tried, 10 min old
2. New, never tried, 3 h old
3. Contacted, next_step_at NOW − 2 h
4. Contacted, meeting_at NOW + 30 min
5. Contacted, meeting_at NOW − 2 h, scheduled
6. Qualified, next_step_at NOW + 4 h

Plus a 7th, a test lead overdue. Expected order of ids `[1, 4, 2, 3, 5, 6]`, with buckets `[0, 1, 2, 3, 4, 5]`, test lead absent. A lead that is both New-never-tried and has an overdue next step appears once, in bucket 0/2.

**`reminder_due`**, due at NOW:
- now − 1 min → False
- now → True
- now + 23 h 59 m → True
- now + 24 h → False
- status lost → False
- `is_test` → False

**`untouched`** (changed rule, in `test_reminders_logic.py`):
- `lead(90, notes=1)` → now **is** untouched (`due` = ["5m", "1h"])
- `lead(90, meeting_status="scheduled")` → `[]`
- the existing first_contacted_at case stays `[]`

Update the old test `test_nothing_once_someone_acted…`: the `notes=1` case moves into a new test named `test_a_note_alone_no_longer_stops_reminders`.

**`call_stats`**: rows of outcomes `reached, no_answer, no_answer, booked, voicemail` plus one undone `reached` → `{"calls": 5, "talked": 2, "rate": 40, "booked": 1}`. `[]` → `{"calls": 0, "talked": 0, "rate": None, "booked": 0}`.

**`digest_text`**:
- `(waiting=[Maria 14 h], due=[Tom call_back due Tue 16:00 LA], calls_today=[Ana 14:00 LA], now=Wed 08:00 LA)` → title "Today: 1 lead waiting for a first call, 1 follow-up due, 1 booked call", lines `["Maria Lopez, Bakery: waiting 14 h", "Call back Tom Reed: overdue since Tue", "Call at 2:00 PM: Ana Ruiz"]`
- Only follow-ups → "Today: 2 follow-ups due"
- All empty → None (nothing sent)

**`describe`** (`lead_history`), one assert over a list of 8 events → the exact sentences in the table above, incl. "(undone)" and a backfilled stage row "Eugene moved it from New to Contacted".

**PRUNE guard**: `self.assertFalse({"lead_events", "bookings"} & {t for t, _ in jobs.PRUNE})` in a test named `test_lead_history_and_bookings_are_never_pruned`.

**`report_logic.funnel`**:
- `funnel([("Leads received",10),("Contacted",8),("Booked a call",5,"Leads received"),("Qualified",3,"Contacted"),("Won",1)])` → rates `[None, 80, 50, 38, 33]`, `of` `[None, "Leads received", "Leads received", "Contacted", "Qualified"]` (W2's signature, 00-PLAN C2)
- without the Booked step → W2's 4-step case unchanged

**Contact keys**: tested in L2's `test_contact_logic` (`contact.email_key` / `contact.phone_key`); L1 adds only the booking side:
- booking `(" Maria@LopezBakery.COM ", "+1 (619) 555-7788")` → keys `("maria@lopezbakery.com", "6195557788")`
- `(None, "12345")` → `(None, None)`; `("test@example.com", "+1 (555) 000-1111")` → `(None, None)` (placeholders never match)

**`bookings.match`**, candidates:
- A: email maria@lopezbakery.com, lost, 10 days old
- B: email maria@lopezbakery.com, contacted, 5 days old
- C: phone 6195557788, new, 1 day old
- F: a repeat of B (`repeat_of` = B), same email, 1 day old: never a candidate (roots only)
- D: test lead with the same email
- E: email old@…, 100 days old

| booking | expected |
|---|---|
| email MARIA@LopezBakery.com | `(B, "email")`: open beats lost, test and repeat excluded |
| email none, phone "619.555.7788" | `(C, "phone")` |
| email old@… | `(None, None)`: over 90 days |
| both email of B and phone of C | `(B, "email")` |

**`booking_hooks.verify`**, secret `whsec_qa`, raw body `{"triggerEvent":"BOOKING_CREATED"}`:
- calcom header `e18266989b291deef90edad819e17c88dabbad0178b20ca9cd7e641984ab4de1` → True
- the same with the body's last byte changed → False
- calendly header `t=1794340000,v1=38719b08606412c4ebda5373267355834ccfe265f53349cd1e57b94b98b35e91` at now = 1794340100 → True; at now = 1794340400 → False (over 180 s)
- other: header `X-Booking-Secret: whsec_qa` → True; `whsec_qb` → False
- missing header → False for every provider

**`booking_hooks.parse`**: one documented example payload per tool saved under `tests/fixtures/booking_<tool>_*.json` (created, rescheduled, canceled) → the normalized dict. Unknown trigger (`MEETING_ENDED`) → None. Times parse to UTC.

### `qa/flows.cjs` (the file stops at the first missing selector, so add these in the same commit)

1. Seed a lead "QA Follow Lead" with a phone.
   - Open `#lead=`. `#fu-box` says "No calls yet."
   - Click `#log-call` → `.fu-dialog`. Click `[data-outcome="no_answer"]`.
   - Step 2 has `[data-kind="call_back"][aria-pressed="true"]` and `[data-when="later_today"][aria-pressed="true"]`. **Save**.
   - Check:
     - `.fu-chip` in the row matches `/Call back/`
     - API `first_contacted_at` is set
     - `.history` contains "called: no answer"
     - toast contains "Next: Call back"
2. Undo: click the toast's Undo → history shows "(undone)", `call_attempts` 0, `first_contacted_at` null.
3. Log three no-answers via API. `#fu-lost` reads "Lost: couldn't reach". Click → stage Lost pressed. Next step cleared ("Next step closed").
4. Stage move: a Contacted lead → click Qualified → `.fu-dialog` "What's next for". Pick `proposal` + `tomorrow_9` → box "Next: Send proposal · tomorrow 9:00 AM".
5. Overdue:
   - Via SQL, set `next_step_at = now() - interval '2 hours'`.
   - `/leads.html?due=overdue` lists the lead, and its chip matches `/Overdue/`.
   - `/home.html`: `#fu-today` (or the 9.4 queue) has a row for it with **Done**. Click Done → the row leaves, and history has "Done: Send proposal".
6. Booked:
   - `#log-call` → `booked` → Tomorrow + time 14:00 → chip "Call on {day} 2 PM". `booked_at` set. A New lead moved to Contacted.
   - `/performance.html` shows "Calls booked" and "Cost per booked call".
   - Ads manager `results` columns include "Booked".
7. Check row:
   - SQL `meeting_at = now() - interval '2 hours'`. Today shows "Did the call … happen?".
   - Click `[data-meeting="no_show"]` → history "No-show". Step 2 opens with Call back preset.
8. Reminders:
   - SQL `next_step_at = now() - interval '1 minute'`, then run `reminders.run()` in the container.
   - The fake Telegram gets "Call back QA Follow Lead: due" once.
   - A second run sends nothing more (dedupe).
9. Never pruned:
   - Insert a `lead_events` row and an `activity` row dated 400 days ago, then run `jobs.prune()`.
   - The event is still there and the activity row is gone.
10. Booking webhook (Phase C):
    - Set tool Cal.com plus secret in Settings › Booking tool. `#booking-url` is shown.
    - POST a signed Cal.com payload with the QA lead's email → within 5 s the lead has `meeting_status = scheduled` and the chip "Call on".
    - Bad signature → 403.
    - Unknown email → Inbox Needs action item "isn't in your leads". `[data-match]` → search → Match → item resolved and the lead shows the call.
    - Canceled payload → Inbox FYI item "canceled their call".
11. Roles:
    - As the QA client (read-only): no `#log-call`, no `.fu-actions` visible. POST `/calls` → 403.
    - With `client_lead_updates` on: logging works.
    - As a teammate on another campaign: `/calls` → 404.
12. Phone 390 px:
    - Open the lead and the dialog. Every `.fu-dialog button` is ≥ 44 px, every input font-size is 16 px.
    - At 320 px, no horizontal overflow on Leads and Today.
13. The ad-blocker guard and console-error guard run unchanged and cover the new markup.

`dev/qa_leaks.py`:
- `once("lead_events", {"lead_id": lead, "kind": "note", "details": json.dumps({"mark": mark}), "account_id": acct}, "details")` (or a marked `ref_id`)
- `once("bookings", {"provider": "other", "delivery_key": f"{mark}booking", "event": "created", "name": f"{mark} booking", "payload": "{}", "account_id": acct}, "delivery_key")`
- Confirm `/api/bookings` and `/api/leads/<other lead>` never show the other mark, and that both new tables pass `isolated()`.

### Fake Meta additions

None. No Meta call is added. If Eugene later says yes to sending Booked to Meta, `fake_meta.py` already records `POST /{dataset}/events`; add one QA check that a `Booked` event arrives once.

---

## Rollout

Ship in three commits, each on its own (ROADMAP §4: tests first, QA, tick the box):

1. **`feat(ads): call outcomes, next steps and lead history that is kept`** (Phase A)
   - Migration `NNN_followups.sql`: relative slot **N+3** in 00-PLAN (whole file, including the `bookings` table, so no second migration is needed).
   - `lead_history.py`, `followup.py`, and the leads/home/reminders/replies changes. `followup.js`, CSS, flows 1–5, 8, 9, 11–13.
2. **`feat(ads): booked calls and cost per booked call`** (Phase B)
   - The booked step in the dialog (already in 1 if built together), Results / manager / Compare / report funnel, `tracks_bookings`, flows 6–7.
3. **`feat(ads): bookings from Cal.com, Calendly or SavvyCal`** (Phase C): **only after Eugene names his tool**.
   - `booking_hooks.py`, `bookings.py`, webhook route, Settings section, Inbox rules, flow 10, `docs/BOOKING-SETUP.md` (click-by-click for the chosen tool; Calendly includes the one API call to create the subscription).

Settings switches:
- None for A and B: the features are inert until someone logs a call, and Booked columns appear only when a booking exists.
- Phase C is off until a secret is saved. A delivery to an account with no secret gets a 403.

Open decisions for Eugene (one AskUserQuestion before building):
1. Which booking tool, if any: Cal.com · Calendly (paid plan needed for webhooks) · SavvyCal · Google appointment page (via Zapier) · none for now. Recommend building A and B now and C once he answers.
2. A note alone no longer stops the "nobody called" reminders; Log a call does. Recommend yes, so one rule.
3. "Talked to them" and "Booked a call" on a New lead also move it to Contacted, which sends Contacted to Meta when stage sending is on. Recommend yes.
4. (Later, Meta write) Send "Booked" to the dataset as a CRM event? Recommend not now. It needs his explicit yes, a separate switch off by default, a new `Booked` event mapped in Events Manager, and a payload test. Sketch: `crm_events` gets a side event `booked`, sent after Lead and Contacted, never required before Qualified.

What Eugene does after Update:
- Phase A/B: nothing to configure.
  - Tell him: "After a call, tap the outcome. Set a next step and it comes back on the day. Notes don't stop the reminders any more; Log a call does."
  - The digest now also lists follow-ups.
- Phase C: Settings › Leads › Booking tool. Pick the tool, copy the link into the tool's webhook settings, paste its signing secret, then book a test call with a lead's email and check the chip.
- Unverified until live:
  - `tel:` → back-to-browser behaviour on his real iPhone (dialog waiting on return)
  - each booking tool's real payload and signature
  - timing of notifications on his phone

Backfill: runs inside the migration. On the live database it is a few hundred rows (it took milliseconds in dev). History older than 180 days was already pruned from `activity` and can't be recovered; the History footer says so.

---

## Effort

| Part | Size | Notes |
|---|---|---|
| A: lead_events + backfill, outcomes dialog, next step, chips, filter, Today rows, reminders + digest, response line, undo | M (≈ 2 days) | Most of the work is UI states and the flows.cjs additions |
| B: booked + cost per booked call across Results, manager, Compare, report funnel, snapshot | S–M (≈ 1 day) | Touches files 9.x is also editing (`manager.js`, `performance.js`): land after the current 9.x commit or rebase carefully |
| C: booking webhook, matching, Inbox items, Settings section, setup guide | M (≈ 1.5 days) | Blocked on Eugene's tool choice; payload fixtures per tool |
| Total | M+ (≈ 4–5 days) | No Meta writes, no money paths, no bridge change |
