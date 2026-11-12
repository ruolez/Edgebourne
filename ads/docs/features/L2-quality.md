# L2 — Lead quality: lost reasons, highest stage reached, repeats and junk

> **Architect resolutions (00-PLAN.md), applied below:**
> - Build step **5** of 9; migration **N+4**. Depends on:
>   - the audit-fix `is_organic` / `alerted_at`
>   - L1 (`lead_events`, `lead_history`, the shared undo route); writing there is **mandatory**, not optional
>   - W1a (`confirmDialog` `choices` / `multiline`, built there; L2 reuses them with `required: "Pick a reason"`)
>   - W2 (`LEAD_SCOPE`, `stage_counts`, `lead_gap`)
> - L2 owns these shared pieces:
>   - S12: the pure module **`backend/contact.py`** (`email_key`, `phone_key`, placeholder rules). L1 Phase C uses it too.
>   - S13: the `lead_quality` SQL fragments and the ratchet test. On landing, set W2's `reports_api.LEAD_SCOPE = lead_quality.counted()`, `stage_counts` → `contacted()/qualified()/won()`, and append to W2's `lead_gap` text when repeats exist: ", and a person who filled the form twice counts once".
> - C5: `contacted(a) = a.max_stage <> 'new'` (stage-based). `first_contacted_at` (first *try* under L1) no longer counts as contact. The max_stage backfill may still read the old `first_contacted_at`.
> - C10: undo uses the shared `POST /api/leads/<id>/events/<event_id>/undo` (L1's `lead_history.undo`; same person; **10 minutes**). Stage events carry `{from, to, max_before, max_after, reason, reason_before}` in `lead_events.details`. The PATCH `undo: true` form is removed.
> - C12: client PATCH guard `{"status","lost_reason","lost_note","next_step","next_step_done","meeting"}`.
> - C8: `lead_quality.is_junk` is the only definition of junk; W1b's `junk_high` uses it.
> - C3: the Results sub is "got that far · from your leads" (no "leads inbox").
> - Security:
>   - The match SQL adds `AND o.account_id = %(acct)s` as well as RLS.
>   - The lock is `pg_advisory_xact_lock(hashtext('lead-match'), account_id)` inside the insert transaction (no blocking lock on its own connection).
>   - Undo deletes a CRM row only with `DELETE … WHERE id=%s AND status='pending' RETURNING id`.
> - Bridge: the snapshot sentence ships as bridge VERSION 1.12 (C27).

Unit L2-quality covers two audit proposals:

- **"Lost reasons, highest stage reached and lead quality by ad"**: `max_stage`, a reason when a lead is marked Lost, a Lead quality panel on Results, lost reasons in Claude's snapshot and in the client report.
- **"Organic, repeat and junk leads classified correctly"**: repeat detection and junk flags. The organic vs test split (`is_organic`, `is_test = not ad_id and not is_organic`) and the single alert claim (`leads.alerted_at`) are being built by the audit-fix workflow. This design assumes both exist and plugs into them (see Rollout, "Depends on").

No new Meta writes. No money paths. Every Meta call this design uses is already in the code (lead read). The CRM event payload doesn't change.

---

## 1. Goal

1. **Qualified stays qualified.** Every Qualified or Won count measures the *highest stage a lead reached*, not where it sits today. A prospect who qualified and then said no still counts toward cost per qualified lead. Today they drop out (`status IN ('qualified','won')` in 8 places), so the $60 KPI gets worse every time a good prospect declines.
2. **Know why leads are lost.** Moving a lead to Lost asks for one reason from a short list. Leads can filter by reason. Results shows reasons per ad. Claude's snapshot carries counts per reason. The client report says why leads were lost.
3. **One person counts once.** A second form fill from the same email or phone within 90 days is marked as a **repeat** and linked to the first lead. The team gets one "asked again" alert. There is no second automatic reply and no reminder chain, and the repeat counts once in leads, qualified and won. A person who comes back after their first lead was closed is a **returning** lead. They're treated as new, but the earlier lead is shown next to them.
4. **Junk is visible.** A pure `lead_quality.flags()` marks placeholder phones, test or throwaway email domains, one-letter names, test words and identical answers. The lead gets a "Looks like junk" chip and a one-tap "Mark as lost: spam or fake". Flags are hints only. They never hide a lead or stop an alert.
5. **Lead quality by ad, form and answer** on Results: per row, leads, repeats, qualified %, junk %, cost per qualified lead and why leads were lost. It keeps the console's minimum-data rule (3 results and 2× target).

---

## 2. User flow

### 2.1 Marking a lead Lost (desktop and phone)
1. Eugene opens a lead and taps **Lost** in the stage strip.
2. A dialog opens: **"Why was this lead lost?"** It has 8 reasons as full-width radio rows (44 px tall on phones), each with a one-line hint. Below them is an optional note, **"Anything to add? (optional)"**, a 16 px textarea of 2 rows.
3. **Mark as lost** saves. **Cancel** leaves the stage as it was. With no reason picked, the dialog shows **"Pick a reason"** under the list and stays open.
4. The toast says **"Moved to Lost · Undo"** for 8 s. Undo restores the stage, the highest stage and the reason.
5. The lead's facts show **Lost because: Price — "went with a cheaper quote"** and a **Change** link, which reopens the dialog with the current answer.
6. Moving a Lost lead back to an open stage clears the reason. The reason stays in History. Marking it Lost again asks again.

On phones the dialog is the shared Phase 9 dialog at full width. The radio list scrolls inside it, and the buttons stay pinned at the bottom (the 9.2 Dialog pattern).

### 2.2 Highest stage reached
- Lead facts gain **"Got as far as: Qualified"**, shown only when it differs from the current stage (for example, Lost after Qualified).
- Admins see **Correct** next to it. It opens a dialog with a select (New / Contacted / Qualified / Won) and the hint "Use this only to fix a wrong click. Meta keeps any stage it was already sent." Teammates and clients don't see it.

### 2.3 Repeats (arrival)
1. Maria Lopez fills the form on N2 on Nov 3 and is Contacted. On Nov 10 she fills it again from N3.
2. The worker stores the Nov 10 lead, finds the Nov 3 lead by email or phone, and links it as a **repeat**.
3. The alert goes to the usual people plus the first lead's owner. Email subject: **"Asked again: Maria Lopez, Wholesale bakery"**. First line: **"Maria Lopez asked again (from N3 - Same work twice). Their first request is with Eugene, stage Contacted."** The Telegram and push title is **"Asked again: Maria Lopez"**. No automatic reply. No 5-minute or 1-hour reminder. Not in the morning digest.
4. In **Leads → Open** (the default), the Nov 10 row isn't listed separately. Maria's Nov 3 row shows the chip **"Asked 2×"**. In **All**, the repeat row is listed, muted, with the chip **"Repeat"** and no waiting clock.
5. Opening the repeat shows a note, **"Maria Lopez asked again on Nov 10 from N3 - Same work twice. Work it on the first lead; this one doesn't count twice."**, with the buttons **Open the first lead** and **Not the same person**. The stage strip is replaced by that note, because the stage lives on the first lead.
6. The first lead's page has an **"Also asked"** section: date, ad, and their answers, folded. Each entry links to the repeat.
7. **Not the same person** unlinks the lead. It becomes a normal lead, counted on its own, and is never linked again automatically. Toast: **"Unlinked: counted as a separate lead"**. Because no automatic reply went out, its page says **"No automatic reply went out because it looked like a repeat."** above the existing Email button.

### 2.4 Returning leads
If the first lead is **Won**, or **Lost** for any reason other than "Spam or fake" or "Duplicate", the new fill is **returning**. It's a new chance, so it gets the normal alert, reminders and automatic reply, and it counts as a lead. Two things are added:
- The alert and email carry the line **"Asked before: Sep 2, Lost (No response)."** or **"Already a client: Won on Sep 2."**
- The list chip is **"Asked before"**. The detail note is **"Asked before on Sep 2 from N1 (Lost: No response). Open that lead"**.

### 2.5 Junk
1. A lead arrives with name "a", email test@test.com and phone 1234567890.
2. The alert still goes. Its subject is **"New lead (looks like junk): a, business not given"**.
3. The list row shows **"Looks like junk"** as a warn pill.
4. The detail shows a warn note: **"This looks like junk: the phone number looks made up, the email is a test address, the name is a single letter."** Two buttons:
   - **Mark as lost: spam or fake**: one tap, no dialog, with an Undo toast. It sets Lost with the reason `spam`.
   - **It's real**: the chip goes away, the lead isn't counted as junk, and the toast says "Marked as real".
5. No automatic reply goes to a test or throwaway address (`replies.auto_reason` → `"looks fake"`). Bounces would hurt the sender's reputation. A placeholder phone or a short name doesn't block the reply.

### 2.6 Same person, by hand
For leads the check missed (a different email and phone, same person), the lead detail **⋯** menu, or a quiet button below the facts on phones, has **Same person as…**. It opens the dialog **"Which lead is the same person?"**:
- A 16 px search field, **"Name, phone or email"**, with up to 8 matches from `/api/leads?q=&status=all`. The current lead and its own repeats are left out.
- Each match is one 44 px row: name, business, date, stage.
- **Link them** saves. The older lead stays the first lead, and the newer one becomes the repeat. If the newer one had already got further (for example Qualified), the first lead's "Got as far as" moves up to match, so the person's progress isn't lost from the counts.

### 2.7 Leads filters
- When the **Lost** filter is on, a second control appears under the stage filters: a select, **"Why"**: All reasons (12) / No response (5) / … / No reason given (3). It is kept in the URL as `?why=`.
- If any Lost lead has no reason, the Lost view shows the note **"3 lost leads have no reason yet. Open one and tap Change to add it."**

### 2.8 Results → Lead quality (desktop and phone)
- A new panel sits below **Ads** and above **By idea**: **"Lead quality"**, with the subtitle **"What happened to the leads from each ad, same period"**. It follows the page's range and campaign.
- Segmented control: **By ad · By form · By answer**. "By answer" adds a **Question** select, which lists the form questions seen in the period.
- There is one verdict line, then a table. On phones under 600 px the table becomes cards (2×2 figures and a "Why lost" line). There is no horizontal scroll.
- Below the table is a junk note: **"4 of 31 leads look like junk and 2 were repeats. Meta counts all of them, so its cost per lead ($12.10) is lower than the cost per real lead ($14.50)."**
- Each row's name links to the ad (`entityLink`) and to `leads.html?ad=<id>&status=all`. A form row links to `leads.html?form=<id>`.

---

## 3. Data model

One migration, `NNN_lead_quality.sql`. No new table. `leads` already has `account_id` and the `account_isolation` policy (020), so every new column is under RLS. Same-account links are also enforced by composite foreign keys (the iSpend pattern), so a bug in Python can't link two accounts' leads.

```sql
-- NNN Lead quality: highest stage reached, lost reasons, repeats and junk flags.
-- Depends on the audit-fix migration that adds leads.is_organic and leads.alerted_at.

ALTER TABLE leads
    ADD COLUMN max_stage TEXT NOT NULL DEFAULT 'new'
        CHECK (max_stage IN ('new', 'contacted', 'qualified', 'won')),
    ADD COLUMN max_stage_at TIMESTAMPTZ,
    ADD COLUMN lost_reason TEXT
        CHECK (lost_reason IN ('no_response', 'not_fit', 'spam', 'duplicate', 'too_small',
                               'price', 'went_elsewhere', 'other')),
    ADD COLUMN lost_note TEXT,
    ADD COLUMN email_key TEXT,              -- normalised email, NULL when missing or a placeholder
    ADD COLUMN phone_key TEXT,              -- last 10 digits, NULL when missing or a placeholder
    ADD COLUMN earlier_lead_id INTEGER,     -- the first lead of the same person (repeat or returning)
    ADD COLUMN repeat_of INTEGER,           -- set only for a repeat: this row doesn't count
    ADD COLUMN repeat_source TEXT CHECK (repeat_source IN ('auto', 'hand')),
    ADD COLUMN repeat_checked BOOLEAN NOT NULL DEFAULT FALSE,  -- "Not the same person": never auto-link
    ADD COLUMN junk_flags TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN junk_dismissed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE leads ADD CONSTRAINT leads_account_id_id UNIQUE (account_id, id);
ALTER TABLE leads ADD CONSTRAINT leads_repeat_same_account
    FOREIGN KEY (account_id, repeat_of) REFERENCES leads (account_id, id) ON DELETE SET NULL (repeat_of);
ALTER TABLE leads ADD CONSTRAINT leads_earlier_same_account
    FOREIGN KEY (account_id, earlier_lead_id) REFERENCES leads (account_id, id) ON DELETE SET NULL (earlier_lead_id);
ALTER TABLE leads ADD CONSTRAINT leads_repeat_not_self CHECK (repeat_of IS NULL OR repeat_of <> id);
ALTER TABLE leads ADD CONSTRAINT leads_lost_reason_only_lost CHECK (lost_reason IS NULL OR status = 'lost');

CREATE INDEX leads_email_key_idx ON leads (email_key, created_time) WHERE email_key IS NOT NULL;
CREATE INDEX leads_phone_key_idx ON leads (phone_key, created_time) WHERE phone_key IS NOT NULL;
CREATE INDEX leads_repeat_of_idx ON leads (repeat_of) WHERE repeat_of IS NOT NULL;

-- Backfill the highest stage from what we know: current stage, every recorded stage change
-- (activity, kept 180 days), every stage queued for Meta (crm_events, kept forever), first contact.
WITH ranks(stage, r) AS (VALUES ('new', 0), ('contacted', 1), ('qualified', 2), ('won', 3)),
seen AS (
    SELECT l.id, l.status AS stage FROM leads l
    UNION ALL SELECT l.id, 'contacted' FROM leads l WHERE l.first_contacted_at IS NOT NULL
    UNION ALL SELECT a.subject::int, a.details->>'to' FROM activity a
              WHERE a.action = 'lead.status' AND a.subject ~ '^\d+$'
    UNION ALL SELECT c.lead_id, c.stage FROM crm_events c
),
best AS (
    SELECT s.id, (ARRAY['new','contacted','qualified','won'])[MAX(r.r) + 1] AS stage
    FROM seen s JOIN ranks r ON r.stage = s.stage GROUP BY s.id
)
UPDATE leads l SET max_stage = b.stage, max_stage_at = l.status_changed_at
FROM best b WHERE b.id = l.id AND b.stage <> 'new';
```

Notes:
- The migration runs as the owner role, so the backfill crosses accounts. `activity.subject` and `crm_events.lead_id` reference the global serial `leads.id`, so the join is exact.
- `email_key`, `phone_key`, `junk_flags` and the repeat links are **not** backfilled in SQL, because placeholder detection lives in Python. A one-off worker step does it (§4.6), once per account, behind a settings flag.
- PG 16 (compose `postgres:16-alpine`) supports `ON DELETE SET NULL (col)`. Leads are never deleted today, so this only matters if they ever are.
- The migration is written in one go (ROADMAP §5: dev applies a half-written migration).

---

## 4. Backend

### 4.1 New module `backend/lead_quality.py` (pure, no `db` import at module level)

```python
FUNNEL = ("new", "contacted", "qualified", "won")
RANK = {s: i for i, s in enumerate(FUNNEL)}

LOST_REASONS = (            # key, label, hint (the dialog's order)
    ("no_response",   "No response",          "Never answered calls or emails"),
    ("not_fit",       "Not a fit",            "Not the kind of business we help"),
    ("too_small",     "Too small",            "Too early or too small for this"),
    ("price",         "Price",                "Said it costs too much"),
    ("went_elsewhere","Went with someone else","Chose another company or did it in-house"),
    ("spam",          "Spam or fake",         "Fake details, a bot, or someone selling to us"),
    ("duplicate",     "Duplicate",            "Same person as another lead"),
    ("other",         "Other",                "Say why in the note"),
)
REAL_PERSON = {"not_fit", "too_small", "price", "went_elsewhere"}
REPEAT_DAYS = 90
MIN_LEADS = 3            # = concepts.MIN_LEADS
SPEND_TIMES = 2          # = concepts.SPEND_TIMES
ANSWER_GROUPS_MAX = 12

# SQL fragments: the one definition of what counts (ratchet test in §8.1 enforces their use).
def counted(a="l"):   return f"NOT {a}.is_test AND {a}.repeat_of IS NULL"
def qualified(a="l"): return f"{a}.max_stage IN ('qualified','won')"
def won(a="l"):       return f"{a}.max_stage = 'won'"
def contacted(a="l"): return f"{a}.max_stage <> 'new'"   # stage-based (00-PLAN C5): a no-answer try is not contact
```

Pure functions (signatures):

| Function | What |
|---|---|
| `raise_max(current_max: str, new_status: str) -> str` | Highest stage after a move. Lost never lowers it. |
| `max_from_history(stages: list[str], contacted: bool = False) -> str` | Python twin of the migration backfill. Used by tests and the hand-link merge. |
| `undo_max(max_now: str, change: dict) -> str` | `change = {"max_before", "max_after"}` from the stage event's `lead_events.details`. Restores `max_before` only if nothing has raised it since. |
| `clean_lost(status: str, reason, note) -> tuple[reason, note, error]` | Validates the PATCH. Not lost → `(None, None, None)`. Unknown reason → error. Note trimmed to 500 characters. |
| `contact.email_key(email) -> str \| None` (module `contact.py`, S12) | Lowercases and trims. None when invalid or a placeholder. |
| `contact.phone_key(phone) -> str \| None` (module `contact.py`, S12) | Digits only. Last 10 when there are ≥ 10, all of them when there are 8–9, None when fewer or a placeholder. |
| `flags(lead: dict) -> list[str]` | Codes in a fixed order: `fake_phone`, `test_email`, `throwaway_email`, `short_name`, `test_words`, `same_answers`. `lead` has `full_name`, `email`, `phone`, `answers` (Meta's field_data). |
| `flag_text(codes: list[str]) -> str` | One plain sentence for the note, the email and the snapshot. |
| `match_kind(original: dict) -> "repeat" \| "returning"` | From the first lead's `status` and `lost_reason`. |
| `is_junk(lead: dict) -> bool` | True for `lost_reason == 'spam'`. Also true when the lead has flags, isn't dismissed, `max_stage == 'new'` and `lost_reason not in REAL_PERSON`. |
| `group_key(lead: dict, by: str, question: str \| None) -> tuple[key, label]` | `by`: `ad` → (`ad_id`, ad name), or (`"page"`, "From the Page (no ad)") for organic leads. `form` → `form_id`. `answer` → the answer value, lowercased for the key and shown as first seen, multi-choice joined with ", ". |
| `summarize(leads: list[dict], spend: dict[key, int], by: str, question: str \| None, target_cents: int \| None) -> dict` | Rows, totals, verdict, junk note numbers (§4.1.1). |
| `lost_counts(leads) -> dict[str, int]` | Reasons in `LOST_REASONS` order, plus `"none"` for no reason given. Counted leads only. |

Placeholder rules (data, not code paths, so they're easy to test and extend):
- **Fake phone:** after taking the digits:
  - every digit the same (`1111111111`, `0000000`)
  - ascending or descending runs (`1234567890`, `0123456789`, `9876543210`)
  - NANP area code `555`, or area code starting with 0 or 1, when there are 10 digits after an optional leading 1
  - fictional exchange 555-0100 to 555-0199
  - fewer than 7 digits
- **Test email:**
  - local part in `{test, testing, tester, asdf, qwerty, abc, fake, none, noemail, no, na, null, x, xx, xxx}`
  - domain in `{example.com, example.org, example.net, test.com, test.test, email.com, domain.com, none.com}`
  - TLD in `{example, test, invalid, localhost}`
- **Throwaway email:** domain in a 40-entry list kept in the module (`mailinator.com`, `guerrillamail.com`, `10minutemail.com`, `yopmail.com`, `sharklasers.com`, `trashmail.com`, `maildrop.cc`, `tempmail.com`, `temp-mail.org`, `getnada.com`, `dispostable.com`, …). No external list fetch.
- **Short name:** every part of the name has ≤ 1 letter (`a`, `J K`), or the name has no letters at all (`123`). `Jo Li` is fine.
- **Test words:** a whole word `test`, `testing`, `asdf`, `qwerty`, `lorem`, `fake` or `dummy` in the name or any non-contact answer.
- **Same answers:** ≥ 2 non-contact answers, all equal ignoring case, with the shared value at least 3 characters long and not `yes`, `no`, `n/a` or a number.

#### 4.1.1 `summarize` output

```python
{"by": "ad", "question": None, "target_cents": 6000,
 "rows": [{"key": "1202…", "label": "N3 - Same work twice", "is_page": False,
           "fills": 7,          # every non-test form fill, repeats included (what Meta charges for)
           "leads": 6,          # people: counted() rows
           "repeats": 1, "junk": 1, "qualified": 3, "won": 1,
           "qualified_rate": 0.5, "junk_rate": 0.1667,
           "spend_cents": 12000, "cpq_cents": 4000,
           "rates_enough": True,          # leads >= MIN_LEADS
           "cpq_enough": True,            # qualified >= MIN_LEADS and spend >= SPEND_TIMES * target
           "lost": {"no_response": 1, "price": 1}}],
 "totals": {"fills": 31, "leads": 29, "repeats": 2, "junk": 4, "qualified": 9, "won": 2,
            "spend_cents": 37510, "meta_leads": 31,
            "cpl_meta_cents": 1210, "cpl_real_cents": 1500},  # spend / (leads - junk)
 "best": "1202…" | None,   # cheapest cpq among cpq_enough rows, only when >= 2 rows are cpq_enough
 "answer_question_ok": True}  # False when the question has > ANSWER_GROUPS_MAX distinct values
```

With no qualified target set, `cpq_enough` uses only `qualified >= 3` (the same fallback as `concepts.group` without a target). Rows are sorted: `cpq_enough` first by `cpq_cents`, then the rest by `leads` descending. The "From the Page" row is always last, has `spend_cents = None` and `cpq_cents = None`.

### 4.2 Changes to existing modules

| Module | Change |
|---|---|
| `leads.py` `store_lead` | Compute `email_key`, `phone_key` and `junk_flags` (test leads: keys `None`, no flags). Take `pg_advisory_xact_lock(hashtext('lead-match'), account_id)` inside the insert transaction, covering the insert, the match and the link (released on commit or rollback; 00-PLAN §3). Match SQL in §4.3. On a match: `match_kind(root)` decides. Repeat → `repeat_of = root, earlier_lead_id = root, repeat_source = 'auto'`. Returning → `earlier_lead_id = root` only. Event `lead_history.record('repeat' | 'returning', details={"of": root})` (mirrored to activity). Skipped when the account's `lead_repeat_check` is `"0"`. |
| `leads.py` alert step (the audit fix's single claim, `alert_once` or the name it ends up with) | After the claim: if `repeat_of`, call `notify_repeat(lead, root)` (email, phone, no auto reply). Otherwise call the normal `notify`. Returning adds the "Asked before" line. Junk flags add "(looks like junk)" to the subject and title. |
| `leads.render_email` / `notify.lead_alert` | Optional `context_line` and `junk` arguments. A new `render_repeat_email(lead, root, can_see_root)`. If a recipient can't see the root's campaign, the line reads "They asked before in another campaign" and has no link. |
| `leads.recipients_for` (after the audit's account-scope fix) | `repeat_recipients(lead, root)` = the repeat's usual recipients plus the root's owner (if active and wanting lead emails). |
| `replies.auto_reason` | `if lead.get("repeat_of"): return "repeat"`. `if {"test_email","throwaway_email"} & set(lead.get("junk_flags") or []): return "looks fake"`. |
| `reminders.untouched` / `LEADS_SQL` | `AND l.repeat_of IS NULL`. Reminder text gets "(looks like junk)" when flagged. |
| `leads_api._set_status` | Compute `raise_max`. In one UPDATE, set `status`, `max_stage`, `max_stage_at` (only when it rose), `lost_reason` and `lost_note` (cleared when leaving Lost). Event `lead_history.record('stage', details={"from","to","max_before","max_after","reason","reason_before"})` (mirrored to activity). A repeat's stage can't be moved: 409 "This lead is a repeat of another lead; change the stage there". |
| `leads_api.update_lead` | Accepts `lost_reason` and `lost_note`, with `status` or alone when the lead is already Lost. Accepts `max_stage` (admins only, §4.4). Undo is the shared events route (§4.4). Clients with `clients_update_leads` may send `status`, `lost_reason`, `lost_note` (plus L1's `next_step`, `next_step_done`, `meeting`). The guard becomes `set(data) - {"status","lost_reason","lost_note","next_step","next_step_done","meeting"}` (00-PLAN C12). |
| `leads_api.list_leads` | `LIST_COLUMNS` adds `max_stage`, `lost_reason`, `repeat_of`, `earlier_lead_id`, `junk_flags`, `junk_dismissed`, `is_organic`, `form_id`, and `(SELECT COUNT(*) FROM leads r WHERE r.repeat_of = l.id) AS repeats`. Any filter other than `all` adds `l.repeat_of IS NULL`. New params: `why` (a reason key or `none`, only with `status=lost`) and `form`. `counts` uses `counted()`. A new `why_counts` is sent when `status=lost`. |
| `leads_api.get_lead` | Adds `family` (`{"root": {...}, "can_see_root": bool}` for a repeat; `{"repeats": [{id, created_time, ad_id, ad_name, answers}]}` for a root), `earlier` (returning: `{id, created_time, ad_name, status, lost_reason}`, or `None` when it isn't visible to the viewer), `junk_text` and `reasons` (the `LOST_REASONS` list for the dialog). |
| `ads_api._quality`, `concepts_api.by_concept`, `performance_api.overview_data` (quality + before_q), `experiments.py` arm query, `reports_api.totals`, `desk_api.snapshot`, `home_api` stage counts | Replace `NOT is_test AND status IN ('qualified','won')` with `counted()` + `qualified()`, and `status = 'won'` with `won()`. `inbox` counts use `counted()`. `entities_api` (Compare) and Gallery (9.5) inherit this through `ads_api._quality` / the concepts query. |
| `home_api` "Call these first", `inbox.items_for` leads | `AND repeat_of IS NULL`. Flagged leads sort after the others in "Call these first". The Inbox shows a repeat as an FYI item: "Maria Lopez asked again". |
| `alerts.py` inbox-vs-Meta lead count (tracking check) | Keeps repeats, because Meta counts them. Leaves out organic (`NOT is_organic`), because Meta's `ad_daily` has no organic leads (shared with the audit fix). |
| `reports_api.build` / `report_logic` | `totals` adds `lost` = `lost_counts`. A new pure `report_logic.lost_line(counts)`. The report response gets `"lost_line"`, shown under the funnel. The funnel's Contacted, Qualified and Won use `contacted()`, `qualified()` and `won()`. |
| `desk_api.snapshot` | Adds `lead_quality_by_ad` (§4.5) and uses the performance window (also fixes the audit's mixed-windows finding). |
| `jobs.quick` | One step `("lead quality backfill", lead_quality_store.backfill_once)`, a no-op after the flag is set. |

New DB-touching module **`backend/lead_quality_store.py`**: `match(lead_row) -> root | None`, `link(lead_id, root_id, kind, source)`, `unlink(lead_id)`, `hand_link(a_id, b_id, user)`, `leads_for_window(user, start, end, campaign_id) -> list[dict]`, `backfill_once()`. These are kept apart from the pure module (T-3).

### 4.3 Match SQL (inside the lock, after the insert)

```sql
SELECT COALESCE(o.repeat_of, o.id) AS root_id
FROM leads o
WHERE o.id <> %(id)s AND NOT o.is_test
  AND o.created_time <= %(created)s AND o.created_time > %(created)s - interval '90 days'
  AND o.account_id = %(acct)s           -- explicit, as well as RLS (owner-role paths bypass RLS)
  AND ((%(email_key)s IS NOT NULL AND o.email_key = %(email_key)s)
       OR (%(phone_key)s IS NOT NULL AND o.phone_key = %(phone_key)s))
ORDER BY o.created_time DESC LIMIT 1
```

RLS and the explicit `account_id` predicate limit this to the current account. If the new row has `repeat_checked`, matching is skipped.

**Late arrivals:** a backfill can store a lead that's older than one already in the table. After its own match, the newer, unlinked, unchecked leads that match it are linked to the root too: `UPDATE … SET repeat_of/earlier_lead_id …` for rows with `created_time > new.created_time`, using the same `match_kind`. These get no alert (they were already alerted). Each gets an activity row `lead.repeat` with `{"late": true}`.

### 4.4 Routes and roles

Roles: **owner admin** (`role=admin`, no `account_id`), **account admin** (`role=admin` + `account_id`), **teammate** (`member`, assigned campaigns only), **client** (read-only unless the account's `clients_update_leads` is on).

| Route | Who | What |
|---|---|---|
| `PATCH /api/leads/<id>` `{status, lost_reason?, lost_note?}` | all who can see the lead; clients only with `clients_update_leads` | Stage plus reason. With `status=lost` and no reason, it's accepted and stored as NULL (API back-compat: Claude and old clients). The UI always asks. |
| `PATCH /api/leads/<id>` `{lost_reason, lost_note}` on a Lost lead | same | **Change** the reason. Activity `lead.lost_reason`. |
| `POST /api/leads/<id>/events/<event_id>/undo` (shared with L1, `lead_history.undo`) | the person who made the change, within 10 minutes | For a `stage` event: restores `from`, `max_stage = undo_max(...)` and `lost_reason = reason_before`, and marks the event undone. In the same transaction, `DELETE FROM crm_events WHERE id = %s AND status = 'pending' RETURNING id` removes the undone stage's row only if nothing claimed it. If it was already sent, the response carries `"meta_kept": "Qualified"` and the toast adds "Meta already has it". Otherwise 409 "Too late to undo; move it by hand". |
| `PATCH /api/leads/<id>` `{max_stage}` | owner admin, account admin | Correction. Can lower the stage. Activity `lead.max_stage` `{from,to}`. Never touches `crm_events`. |
| `POST /api/leads/<id>/same-person` `{other_id}` | admins, teammates (both leads must be visible); not clients | `hand_link`: the older lead is the root and the newer one gets `repeat_of`, `repeat_source='hand'`. The root's `max_stage = max(root, repeat)`. The repeats of the newer lead are re-pointed to the root. 400 "That's the same lead" or "They're already linked". 404 when either isn't visible. |
| `DELETE /api/leads/<id>/same-person` | admins, teammates; not clients | Clears `repeat_of` and `earlier_lead_id` and sets `repeat_checked = TRUE`. The root's `max_stage` isn't lowered (an admin can correct it). Activity `lead.unlinked`. |
| `POST /api/leads/<id>/not-junk` | admins, teammates; clients with `clients_update_leads` | `junk_dismissed = TRUE`. Activity `lead.not_junk`. |
| `GET /api/performance/quality?range=&by=ad\|form\|answer&question=&campaign=` | all signed-in, clients included (no personal data) | Teammates are scoped by `visible_campaign_ids`. The range comes from `ranges.window` (complete account days, same as Results). Response = `summarize(...)` plus `questions: [{name, label, distinct}]`. |
| `GET /api/agent/snapshot` | `agent_required` (Mac bridge) | Adds `lead_quality_by_ad` (§4.5). |

There's no new write route for clients beyond what `clients_update_leads` already allows. Every write is recorded in `lead_events` through `lead_history.record` (L1, which lands first), mirrored to `activity`.

### 4.5 Snapshot addition (no personal data)

```json
"lead_quality_by_ad": [
  {"ad_id": "1202…", "ad_name": "N3 - Same work twice", "leads": 6, "repeats": 1, "junk": 1,
   "qualified": 3, "won": 1, "lost": {"no_response": 1, "price": 1, "none": 0},
   "junk_flags": {"fake_phone": 1}}
],
"lead_quality_totals": {"leads": 29, "repeats": 2, "junk": 4, "qualified": 9, "won": 2,
                        "lost": {"no_response": 5, "spam": 2, "none": 3}},
"lead_quality_notes": "Qualified and won count the highest stage a lead reached. Repeats (the same email or phone within 90 days while the first lead is open) are counted once. Junk = marked spam, or flagged as looking fake and never contacted."
```

It's grouped by `ad_id` with `MAX(ad_name)`, over the performance range: `(created_time AT TIME ZONE tz)::date BETWEEN start AND end`. `lost_note`, names, emails, phones and answers are **never** included. The bridge skill text (`bridge/skill/SKILL.md` step 2) gets one sentence: "`lead_quality_by_ad`: per ad, repeats, junk and why leads were lost; judge an ad's cost per qualified lead on these, never on Meta's lead count alone."

### 4.6 One-off backfill (worker, per account)

`lead_quality_store.backfill_once()` runs when the setting `lead_quality_backfill_v1` isn't set:
1. For every lead, oldest first:
   - compute `email_key`, `phone_key` and `junk_flags` (test leads get none)
   - run the match, but only against leads before it in time
   - link with `repeat_source='auto'`
   - send no alerts and no CRM events
2. Write one activity row, `leads.quality_backfill` `{leads, repeats, returning, flagged}`.
3. Set the flag.

It's idempotent: it skips rows that already have keys. It's chunked in batches of 200 per pass, so a big account doesn't hold the worker.

---

## 5. Frontend

All class names use the `quality-`, `lost-`, `why-`, `junk-`, `repeat-` and `family-` prefixes. None starts with `ad-`, `ads-`, `adset`, `advert`, `sponsor`, `banner` or `promo` (the `qa/flows.cjs` guard). `.sheet`, `.step`, `.report` and `.confirm` aren't reused (UX-AUDIT constraint).

### 5.1 Shared

- **`format.js`** (the 9.2 single vocabulary) gains:
  - `LOST_REASONS` (key → label), mirrored from the API's `reasons` so the list can render before a lead loads. The server stays the source of truth.
  - `LEAD_CHIPS = { repeat: ["", "Repeat"], asked: ["", n => `Asked ${n}×`], before: ["info", "Asked before"], junk: ["warn", "Looks like junk"], page: ["", "From the Page"], test: ["", "Test"] }`
  - `STAGE_LABELS`, moved out of `leads.js`, so Today, Inbox and Report use the same words.
- **`ui.js confirmDialog`** options `choices` and `field.multiline`. W1a builds them first (00-PLAN S7); L2 reuses them and adds only `required: "Pick a reason"` if W1a didn't. The contract, in line with the one-Dialog goal of 9.2:
  - `choices: { name, options: [{value, label, hint}], value, required: "Pick a reason" }`: radio rows, `.lost-choice`, `min-height: 44px`
  - `field.multiline: true`: a textarea, 16 px on coarse pointers
  - It resolves `{choice, text}` when `choices` is given, so existing callers are unchanged.

### 5.2 `leads.js` / `leads.html`

- Stage strip: **Lost** opens `confirmDialog({title: "Why was this lead lost?", choices: …, field: {label: "Anything to add? (optional)", multiline: true}, confirm: "Mark as lost"})`, then `patch(id, {status: "lost", lost_reason, lost_note})`.
- `patch()` toast: "Moved to Lost · Undo". Undo calls `POST /api/leads/<id>/events/<event_id>/undo` with the `event_id` returned by the PATCH, using the 8 s Undo button pattern from 9.4. Lead pages already keep typed notes (`renderDetail(…, {keep: true})`).
- Facts rows:
  - **Lost because**: label + note + `<button class="btn-link" id="lost-change">Change</button>`
  - **Got as far as**: only when `max_stage` differs from `status`; admins also see `<button id="max-correct">Correct</button>`
- Notes:
  - repeat note (`.repeat-note`) with **Open the first lead** (`#lead=<root>`, so hashchange handles it) and **Not the same person**
  - returning note
  - junk note (`.junk-note`) with **Mark as lost: spam or fake** and **It's real**
- **Also asked** section (`.family-list`): `<details>` per repeat, with the answers inside.
- List rows: chips from `LEAD_CHIPS`. Repeats get `.lead-row.is-repeat` (muted) and no waiting clock (`clockClass` returns `"done"` when `repeat_of`).
- Filters: a `#why` select under `#filters`, shown only when `state.filter === "lost"`, with the URL param `why`. The `form` param is supported for links from Results and Lead forms.
- **Same person as…**: a button in the detail's quiet actions row. The dialog has the search field (`inputmode="search"`, 16 px), the results list `.family-pick` with 44 px rows, and confirms **Link them**.

Exact copy:

| Where | Text |
|---|---|
| Dialog title | Why was this lead lost? |
| Dialog note label | Anything to add? (optional) |
| Dialog buttons | Mark as lost · Cancel |
| Dialog error | Pick a reason |
| Change dialog title | Change why it was lost |
| Toasts | Moved to Lost · Undo / Back to Qualified / Too late to undo: move it by hand / Linked to Maria Lopez's first lead / Unlinked: counted as a separate lead / Marked as real |
| Undo after send | Back to Contacted. Meta already has Qualified and keeps it. |
| Correct dialog | Title "Correct how far this lead got", hint "Use this only to fix a wrong click. Meta keeps any stage it was already sent.", button "Save" |
| Why select | Why · All reasons (n) · No response (n) … · No reason given (n) |
| Lost view note | n lost leads have no reason yet. Open one and tap Change to add it. |
| Empty, why filter | **Nothing lost for this reason** / Try another reason or All reasons. |
| Repeat no-reply line | No automatic reply went out because it looked like a repeat. |

### 5.3 `performance.js` / `performance.html` (Results)

- A new section, `<section class="panel quality-panel" id="quality-panel">`, inserted after `cr-panel` and loaded lazily like `loadIdeas()` (`loadQuality()`), from `/api/performance/quality?range=<range>&campaign=<id>&by=<by>&question=<q>`. `by` and `question` are kept in the URL through `UrlState` (`lq_by`, `lq_q`).
- Segmented control `#quality-by` (By ad / By form / By answer) and `#quality-question` select (shown for By answer).
- Table `.quality-table` (sticky first column, as in the 9.4 table rules), with columns:
  - Ad / Form / Answer
  - Leads (title "People who filled in the form; repeats counted once")
  - Repeats
  - Qualified (title "Got to Qualified or Won, ÷ leads")
  - Looks like junk (title "Marked spam, or looks fake and was never contacted, ÷ leads")
  - Cost per qualified lead
  - Why lost (e.g. "2 no response · 1 price", or "—")
- Greyed (`.early`) cells, with the existing "too early" pill title, when `rates_enough` or `cpq_enough` is false. The row named in `best` is marked with the pill **"cheapest qualified"**.
- Under 600 px: `.quality-cards` list. Each card has the name, then a 2×2 of Leads / Qualified / Junk / Per qualified, then the Why-lost line.

Exact copy:

| Where | Text |
|---|---|
| Title / subtitle | Lead quality / What happened to the leads from each ad, same period |
| Verdict, ≥ 2 judged | **N3 - Same work twice** brings qualified leads cheapest: $40.00 each. |
| Verdict, < 2 judged | Too early to compare: an ad needs 3 qualified leads and twice the $60.00 target in spend before its cost per qualified lead means much. |
| Verdict, no target set | Too early to compare: an ad needs 3 qualified leads first. Set a target in Settings → Targets to judge against it. |
| Junk note | 4 of 31 leads look like junk and 2 were repeats. Meta counts all of them, so its cost per lead ($12.10) is lower than the cost per real lead ($14.50). |
| Junk note, none | No junk or repeats in this period. |
| Empty | No leads in this period yet. |
| By answer, free text | This question has typed answers, so they can't be grouped. Pick a question with set choices. |
| By answer, no spend | Spend can't be split by answer, so cost per qualified lead shows for ads and forms only. |
| Organic row | From the Page (no ad) |

- The figures strip label "Qualified or won" stays. Its sub becomes "got that far · from your leads". Its numbers now come from `max_stage`.

### 5.4 Other pages

- **Report** (`report.js`): under the funnel, `lost_line`, e.g. "Lost: 4 (2 no response, 1 not a fit, 1 spam or fake)." Shown to clients and on share links. Notes are never shown.
- **Today / Inbox**: no new UI. Repeats leave "Call these first", and the Inbox FYI item text is "Maria Lopez asked again".
- **Lead forms** (`forms.js`, 9.4 "leads per form linked to Leads"): an optional "Qualified" % column from the same endpoint, `by=form&range=30`, linking to `leads.html?form=<id>&status=all`. If the 9.4 form work isn't in yet, this waits for it.
- **Settings → Leads**, an account section (owner or account admin):
  - switch **"Spot repeats"**, hint "The same email or phone within 90 days is linked to the first lead and counted once", default on, `lead_repeat_check`
  - switch **"Flag leads that look like junk"**, default on, `lead_junk_flags`

---

## 6. Interaction with other features

| Feature | How it fits |
|---|---|
| **Audit fix: organic vs test, `alerted_at` claim** (in flight) | This unit builds on it. Organic leads are matched and flagged like any lead, and grouped as "From the Page (no ad)". The repeat and returning decision is made at insert (inside `store_lead`), so both the webhook and the catch-up path classify before the single alert claim reads the row. Without the claim, this design would still work, but backfilled repeats wouldn't alert, which is today's behaviour. |
| **L1 Follow-up queue** (`lead_events`, call outcomes, next step) | L1 lands first, so `_set_status`, `lost_reason`, undo, max-stage correction, link/unlink and not-junk all write through `lead_history.record(...)` (kinds already in L1's CHECK). The History tab reads it. **Move to Lost** after the call outcome **Wrong number** opens the Lost dialog with **Spam or fake** preselected only when the lead has junk flags; otherwise nothing is preselected (00-PLAN C13). L1's "Lost: couldn't reach" / "went quiet" send `no_response` with a note. `max_stage` stays a column: counts don't scan events. |
| **Deal value on Won** | The Won dialog (value) and the Lost dialog are siblings in the same `confirmDialog` extension. Revenue and cost per client count leads with `won()` (`max_stage = 'won'`). A Won lead later marked Lost keeps its value unless an admin corrects it. |
| **Client report funnel fix** | Its "start from inbox leads" uses `counted()`. Its "By idea uses inbox qualified" uses `qualified()`. `lost_line` sits under its funnel. |
| **Lead-quality alerts** (snooze/ack unit) | Its "junk share above Y%" rule reads `lead_quality.summarize(...)["totals"]`. Its "qualified rate below X%" rule uses the same `qualified()` / `counted()`. |
| **Phase 9: format.js vocabulary, entity links, Today queue, Inbox Needs action/FYI, Leads undo, 44 px, Creative/Gallery** | The labels live in `format.js`. Results rows use `entityLink`. Repeats are FYI, never Needs action. The Leads undo (9.4) is the same Undo this unit needs: build it once. Gallery and Ideas inherit the corrected qualified counts through the concepts query. |
| **Compare, Tests, By idea, Ads manager columns** | All read `qualified` through `ads_api._quality` / the concepts query / `experiments.py`, so every surface changes the same way, at once. |
| **CRM events (1.1)** | No payload change. A repeat's initial "Lead" event still goes, as it does today. Its stage strip is hidden, so no later stages go for it. Undo deletes only `pending` rows. A sent stage stays on Meta, and the UI says so. |
| **Claude desk** | The snapshot gains lead quality. No new proposal kinds. Claude never changes stages or reasons. |
| **qa_leaks.py** | The new GET route is walked automatically. Add a cross-account repeat seed (§8.3). |

---

## 7. Edge cases

1. **Shared office phone or email** (two people at one company). Auto-linked as a repeat. **Not the same person** unlinks it, sets `repeat_checked`, and it's never re-linked. It's counted on its own from then on. No late alert or automatic reply, but the page says none went out and the Email button is there.
2. **Placeholder contacts never match.** Five junk leads with `test@test.com` / `1234567890` stay five separate leads, each flagged. They don't fold into one family that hides the next one.
3. **Phone formats:** `+1 (619) 555-7788`, `619.555.7788` and `16195557788` share the key `6195557788`. UK `+44 20 7946 0958` → `2079460958`. A 9-digit number keeps all 9 digits. Under 8 digits, there's no key.
4. **Email** is matched only after lowercasing and trimming. Gmail dots and `+tags` are **not** folded, to avoid false merges.
5. **A repeat of a lead in a campaign the teammate can't see.** The repeat note says "They asked before in another campaign", with no name or link. The alert has the same wording. Counts are per account and stay correct.
6. **First lead was Lost: Spam, then the same spammer again** → repeat: no automatic reply, folded. **Lost: No response**, then back after 40 days → returning, worked as new.
7. **First lead Won** (an existing client fills the form) → returning, with the "Already a client" line.
8. **Older lead stored after a newer one** (catch-up) → the late-arrival relink in §4.3. No second alert.
9. **New → Won directly.** `max_stage` is won. The CRM path already sends the earlier stages.
10. **Qualified → Lost → reopened → Lost.** `max_stage` stays qualified. The reason is cleared on reopen and asked for again.
11. **Wrong click (Won instead of Contacted):** Undo within 10 minutes. After that, admin **Correct**. A teammate can't lower it, and the message "Ask an admin to correct it" explains why.
12. **Undo after the CRM event was sent:** the console restores, and Meta keeps the event (explained in the toast). There's no automatic retraction: that would be a Meta write.
13. **`status=lost` from the API with no reason** (Claude, an old client, the Inbox one-tap): stored as NULL and shown as "No reason given". The Lost view nudges the team to add it.
14. **Clients:** without `clients_update_leads` there's no stage strip (as today), so there's no dialog. With it, they can pick reasons and dismiss junk, but can't link, unlink or correct.
15. **Hand link where the newer lead got further:** the root's `max_stage` rises to it, so the person isn't lost from the qualified count. The repeat's own stage is frozen and its strip hidden.
16. **Linking a lead to itself or its own repeat:** 400. **Linking across accounts:** impossible (RLS + composite FK).
17. **Lead with no email and no phone:** never matched. It can still be linked by hand.
18. **By answer with free text** (more than 12 distinct values): refused with the copy in §5.3. Multi-choice answers are joined.
19. **Deleted or renamed form:** grouped by `form_id`, labelled with the latest `form_name`, or "Form <id>" when it's unknown.
20. **Range with spend but no leads on an ad:** the row shows leads 0, cost per qualified "—". **Deleted ads** appear only if they had leads in the range.
21. **Account time zone:** lead days are `AT TIME ZONE account_info.tz_name()`, complete days only (A4 rule).
22. **PII:** `lost_note` and answers never go into the snapshot, the report or the share link. The junk flag codes are safe to share.
23. **The dev seed's 555-01xx phones and `.example` emails would all be flagged.** `dev_seed.py` moves to `@demo.edgebourne.com` addresses and 555-2xxx numbers, and adds three deliberate samples: one repeat, one returning, one junk.
24. **The QA fake lead `tgqa@example.com` would lose its automatic reply** (test domain). The fake Meta changes it to `tgqa@qa.edgebourne.com` (§8.3), and the `flows.cjs` lookup at line ~334 moves with it.
25. **Settings "Spot repeats" off:** no new links. Existing links stay and still count once, so turning it off doesn't silently change past numbers. A note under the switch says so.
26. **Concurrent fills by the same person** (double tap): the per-account advisory lock serialises them. The second becomes a repeat of the first.

---

## 8. Tests

### 8.1 Unit: `backend/tests/test_lead_quality_logic.py` (no DB)

Grouped as `class <Function>Test`, one assertion per structure where possible:

| Function | Input → expected |
|---|---|
| `raise_max` | `("new","contacted")→"contacted"`; `("qualified","lost")→"qualified"`; `("won","contacted")→"won"`; `("new","lost")→"new"`; `("contacted","contacted")→"contacted"`; `("new","won")→"won"` |
| `max_from_history` | `(["new","qualified","lost"])→"qualified"`; `([], contacted=True)→"contacted"`; `(["lost"])→"new"`; `(["won","contacted"])→"won"`; `(["bogus"])→"new"` |
| `undo_max` | `("qualified", {"max_before":"contacted","max_after":"qualified"})→"contacted"`; `("won", same)→"won"`; `("contacted", {"max_before":"contacted","max_after":"contacted"})→"contacted"` |
| `clean_lost` | `("lost","price","  cheaper quote ")→("price","cheaper quote",None)`; `("lost",None,None)→(None,None,None)`; `("lost","bogus","")→(None,None,"Pick one of the reasons")`; `("contacted","price","x")→(None,None,None)`; a 600-char note is cut to 500 |
| `email_key` | `" Maria@LopezBakery.COM "→"maria@lopezbakery.com"`; `"test@example.com"→None`; `"x@mailinator.com"→None`; `""→None`; `"not-an-email"→None`; `"a.b+c@gmail.com"→"a.b+c@gmail.com"` |
| `phone_key` | `"+1 (619) 555-7788"→"6195557788"`; `"619.555.7788"→"6195557788"`; `"+44 20 7946 0958"→"2079460958"`; `"612345678"→"612345678"`; `"12345"→None`; `"1111111111"→None`; `"1234567890"→None`; `"+15550001111"→None`; `"(619) 555-0142"→None`; `None→None` |
| `flags` | Maria (real data) → `[]`; `{"full_name":"a","email":"test@test.com","phone":"1234567890"}→["fake_phone","test_email","short_name"]`; `email "x@mailinator.com"→["throwaway_email"]`; `name "Test User"→["test_words"]`; `name "Jo Li"→[]`; `name "J K"→["short_name"]`; answers `business="asdf", size="asdf"`→`["test_words","same_answers"]`; answers `"Yes","Yes"`→`[]`; answers `"Bakery","bakery "`→`["same_answers"]` |
| `flag_text` | `["fake_phone","test_email"]→"The phone number looks made up and the email is a test address."`; `[]→""`; three codes → "…, … and …" |
| `match_kind` | `{"status":"contacted"}→"repeat"`; `{"status":"new"}→"repeat"`; `{"status":"qualified"}→"repeat"`; `{"status":"lost","lost_reason":"spam"}→"repeat"`; `{"status":"lost","lost_reason":"duplicate"}→"repeat"`; `{"status":"lost","lost_reason":"no_response"}→"returning"`; `{"status":"lost","lost_reason":None}→"returning"`; `{"status":"won"}→"returning"` |
| `is_junk` | `lost_reason="spam"→True`; flags `["fake_phone"]`, max `new`, status `new` → True; same with max `contacted` → False; same with `junk_dismissed` → False; flags, status lost, reason `price` → False; no flags, lost `no_response` → False |
| `summarize` | Fixture: ad A has 5 people + 1 repeat; max stages `[qualified, qualified, new, new, contacted]`, one of the qualified now lost `price`; one lead lost `spam`; spend 15000. Ad B has 6 people, 3 qualified, spend 12000. Target 6000. → A `{leads:5, fills:6, repeats:1, qualified:2, junk:1, qualified_rate:0.4, junk_rate:0.2, cpq_cents:7500, cpq_enough:False, lost:{"price":1,"spam":1}}`; B `{cpq_cents:4000, cpq_enough:True}`; `best=None` (only one judged); rows sorted B, A; totals `cpl_meta_cents` = 27000/meta_leads, `cpl_real_cents = 27000/(11-1)=2700`. Second fixture with two judged ads → `best` = the cheaper one. Organic lead → a "page" row, last, `spend_cents=None`. No target → `cpq_enough` needs only `qualified ≥ 3`. |
| `summarize` by answer | 13 distinct typed answers → `answer_question_ok=False, rows=[]`; `"Bakery"` and `"bakery"` group together, labelled by the first one seen |
| `lost_counts` | leads lost `[no_response, no_response, None, spam]` plus one repeat lost `price` → `{"no_response":2,"spam":1,"none":1}` (the repeat isn't counted, and the order follows `LOST_REASONS`) |
| `report_logic.lost_line` | `{"no_response":2,"not_fit":1,"spam":1}→"Lost: 4 (2 no response, 1 not a fit, 1 spam or fake)."`; `{}→None`; `{"none":2}→"Lost: 2 (no reason given)."` |

**Ratchet** `test_lead_counts_ratchet` (pure file scan, like iSpend's profile ratchet):
- No `backend/*.py` file (tests excluded) may contain `status IN ('qualified'` or `status = 'won'` inside a query on `leads`.
- Every `FROM leads` query that also says `COUNT(` must reference `repeat_of` or call `lead_quality.counted`. An allowlist holds the 2 intentional ones (the alerts Meta-vs-inbox check, the Leads stage tab counts).

`test_replies_logic`: `auto_reason({"repeat_of": 3, "email": "m@x.com"}, True)→"repeat"`; `junk_flags=["throwaway_email"]→"looks fake"`; `junk_flags=["fake_phone"]` with a valid email → `None`.
`test_reminders_logic`: `untouched` is False for a repeat.

### 8.2 `qa/flows.cjs` checks (new block "L2 lead quality")

Each check asserts server state, not just DOM (audit finding A3-116):
1. Lost opens the dialog. Cancel → `GET /api/leads/<id>` status unchanged.
2. Submit without a reason → "Pick a reason" is visible, and there's no PATCH (`page.on('request')` count).
3. Pick Price + note → server `lost_reason=price`, `lost_note` set. The facts show "Lost because: Price".
4. A lead at Qualified, then Lost → `GET /api/performance` `totals.qualified` is the same before and after. The lead's `max_stage = qualified`.
5. Undo → status back to Qualified, `lost_reason` null, and the pending `crm_events` row for `lost` is gone (fake Meta `CRM_EVENTS` has no Lost event).
6. Leads `?status=lost&why=price` lists only that lead. The Why select shows "Price (1)".
7. Webhook lead `7701…` (fake person A) → becomes a normal lead. A second `7701…` → `repeat_of` = the first id. Exactly one automatic reply email to A's address. The second alert's subject starts "Asked again:". The Open count is unchanged. The first row shows "Asked 2×".
8. Repeat detail → **Not the same person** → `repeat_of` null, `repeat_checked` true, and the Open count rises by 1.
9. Webhook `7703…` (junk) → `junk_flags` includes `fake_phone,test_email,short_name`. No automatic reply in the mail capture. The chip "Looks like junk" is visible. **Mark as lost: spam or fake** → `lost_reason=spam`.
10. A second junk lead → **It's real** → `junk_dismissed` true, and the chip is gone.
11. Results → Lead quality: By ad / By form / By answer switch. The URL carries `lq_by`. At 390 px, `scrollWidth <= clientWidth` and every `#quality-by button` is ≥ 44 px tall.
12. Client login: the Lead quality panel is visible. `POST /api/leads/<id>/same-person` → 403. No `#max-correct` button.
13. Teammate: `PATCH {max_stage:"new"}` → 403.
14. `GET /api/agent/snapshot` (bridge key) contains `lead_quality_by_ad`, and its JSON string contains none of the seeded leads' emails, phones, names or `lost_note` text.
15. The ad-blocker name guard still passes (it already runs over every page).

### 8.3 Fake Meta and seed additions (`dev/fake_meta.py`, `dev_seed.py`, `dev/qa_leaks.py`)

- The `7700…` lead changes to `tgqa@qa.edgebourne.com`, `+16195557700`, so it isn't flagged.
- `7701…`: the same person every time ("Repeat QA", `repeat-qa@qa.edgebourne.com`, `+16195557701`), with `ad_id` = N3, so a repeat comes from a different ad than the first lead.
- `7702…`: organic (no `ad_id`, `is_organic: true`). Shared with the audit fix if it adds this.
- `7703…`: junk (`full_name "a"`, `test@test.com`, `1234567890`, answers `asdf`/`asdf`).
- `/{form}/leads` (catch-up) can return a queued lead older than one already stored (`?_fake_backfill=` control), to exercise the late-arrival relink.
- `dev_seed.py`: non-reserved demo contacts (§7.23), plus Maria asking again from N3 (a repeat), Kevin back after Lost: No response (returning), and one junk lead.
- `dev/qa_leaks.py`: an account-2 lead with the same email as an account-1 lead → after the worker pass, neither has `repeat_of` / `earlier_lead_id`. `/api/performance/quality` for account 2 doesn't include account 1's ad ids.

---

## 9. Rollout

**Depends on:** the audit-fix migration that adds `leads.is_organic` and the `alerted_at` single alert claim. If it hasn't merged when this is built, this migration adds `is_organic BOOLEAN NOT NULL DEFAULT FALSE` with `ADD COLUMN IF NOT EXISTS`, and `store_lead` keeps calling `notify` directly.

1. Migration `NNN_lead_quality.sql`: relative slot **N+4** in 00-PLAN (one file, one go). It backfills `max_stage` in SQL, and may also read L1's `lead_events` stage rows (backfilled from activity) as a fourth source.
2. The worker's one-off `lead_quality_backfill_v1` per account computes keys and flags and links past repeats. No alerts, no CRM events.
3. Settings (per account, This account → Leads): `lead_repeat_check` (default on) and `lead_junk_flags` (default on). No console-wide switch. No owner-only setting.
4. The bridge skill sentence (§4.5). Run `ads/bridge/install.sh` only **after** the server Update (memory: "install bridge skill only after server Update").
5. Docs: README "Pages → Leads / Results" lines, ROADMAP Phase 9 or a new line under "Lead quality", progress log.

**What Eugene does after Update:**
- Nothing is required.
- Expect the numbers to move once:
  - Qualified and cost per qualified lead get *better* wherever a qualified prospect was later lost.
  - Lead counts in Leads, Today and the report may drop by the number of past repeats.
  - Meta's own lead count and cost per lead don't change.
- Optional: open **Leads → Lost**, where "n lost leads have no reason yet", and add reasons to the old ones so the first Lead quality read is useful.
- Phone check: mark one lead Lost on his phone and check that the dialog fits and Undo works.

**Unverified on real Meta:** nothing new. The design adds no Meta call. `is_organic` on real Page leads belongs to the audit fix.

---

## 10. Effort

**M+ (about 4 days):**

| Part | Time | What |
|---|---|---|
| Backend | 1.5 d | pure module and tests, migration, store/match/link, routes, swap 8 count queries, snapshot, report line |
| Frontend | 1.5 d | dialog extension, Leads (dialog, facts, notes, chips, Why filter, same-person picker, undo), Results panel with phone cards, report line, Settings switches |
| QA | 1 d | fake Meta leads, seed, 15 flows checks, leak test, screenshots light/dark, desktop/390 |

It can share the Undo work with Phase 9.4 Leads if that lands first, which saves about 0.3 d.
