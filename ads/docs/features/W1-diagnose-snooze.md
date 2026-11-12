# W1 · Diagnose with Claude, snooze alerts, lead-quality alerts

> **Architect resolutions (00-PLAN.md), applied below:**
> - Split into two build steps:
>   - **W1a** (snooze + diagnose + the alert contract): step **3** of 9, migration **N+2**, after D2 and W2.
>   - **W1b** (`qualified_low`, `junk_high`): step **6**, no migration, after L2. It reads L2's columns and fragments directly, with **no `db.has_column` detection**.
> - C9: **`followups_overdue` is dropped.** L1 owns follow-ups (Today rows, notifications, digest, `?due=` filters). The column is `next_step_at`, not `next_step_due_at`.
> - C7 and C8:
>   - Lost-reason keys are L2's (`went_elsewhere`, not `elsewhere`).
>   - Junk is L2's `lead_quality.is_junk`, over **counted leads** in the window. The title reads "33% of leads from “…” look like junk".
>   - Qualified uses `lead_quality.qualified()`. Worked = `max_stage <> 'new' OR status = 'lost'`.
> - C16 (W1a owns the contract):
>   - An event raised with `resolved: False` stays open until its owner closes it.
>   - Needs action = open conditions + open warn/bad events, not snoozed, plus waiting suggestions.
>   - `DONE_OK = {"outside_edit", "change_result"}` get a **Done** action (admins) that sets `resolved_at`.
>   - `report_review` and `booking_unmatched` close only through their own buttons.
> - C17 and S9: Today shows the Needs-action set plus L1's lead buckets, ranked by `today.rank` (W1a adds it if 9.4 hasn't). There's no 3-day window.
> - C19 and S7: W1a builds `confirmDialog` `choices` (`{options:[{value,label,hint}], required, submitOnPick}`) and `field.multiline` (16 px on coarse pointers). The Got-it and Diagnose dialogs use them; L2 reuses them.
> - C26:
>   - `PLAYBOOKS` gains `outside_edit` (D2, present when W1a is built) and later `change_result` (D3).
>   - `WORSE` gains `numbers_off` later (D1).
>   - `report_review`, `report_sent`, `booking_*`: neither snoozable nor diagnosable.
> - Security:
>   - A **money alert already at `bad`** offers only **Remind me tomorrow**.
>   - `diagnose` is added **explicitly** to the bridge's read-only kinds (asserted by `qa_agent_diagnose.py`).
>   - Recipients come from `notify.account_admin_ids()`.
> - S1: dates are "Fri, Nov 14" (`words.weekday`).
> - Bridge VERSION is **1.11** (D2 takes 1.10; C27).

Unit key: `W1-diagnose-snooze`. Two proposals from the audit, built as one unit because they share the
same buttons on the same alert row:

- **Diagnose with Claude from any alert or Inbox item.** Medium value, effort S, no Meta writes.
- **Acknowledge or snooze alerts, plus lead-quality alerts.** Medium value, effort S, no Meta writes.

Designed against the code on 2026-11-11: `backend/alerts.py`, `inbox.py`, `home_api.py`,
`advice_api.py` (5.4 pattern), `desk_api.py`, `status_history.py`, `frontend/js/{inbox,home,settings,creative}.js`
and migrations up to `030`. The Phase 9 redesign (Today queue, Inbox Needs action / FYI, `format.js`
vocabulary, `entityLink()`) and the audit-fix workflow are changing the same files at the same time,
so this spec names functions and contracts, not line numbers.

---

## 1. Goal

1. **Stop the daily nagging without hiding the problem.** Today a lasting condition (a tired ad, 80%
   of the spending limit used, no leads for 3 days) raises a new row and a new Telegram, push or email
   message every day, because the dedupe key includes the date (`f"{rule}:{entity}:{today}"`).
   Eugene can't say "I know". After this unit an admin can tap **Got it** and choose either
   **In 3 days** or **Only if it gets worse**. A snoozed alert stays visible in the Inbox, quietly,
   and sends no messages. It comes back by itself when the date passes, when the figure gets clearly
   worse (for example 80% → 95% of the limit), or, once it clears, the next time it happens.
2. **Alert on lead quality, not just ad health.** Two new rules (W1b, after L2), all inside the pure
   `alerts.evaluate()`:
   - few leads qualify
   - many leads look like junk (L2's definition; W1b ships after L2)
   - ~~leads waiting on a follow-up~~ (dropped: L1 owns follow-ups, 00-PLAN C9)

   An ad that brings cheap junk leads will no longer look healthy.
3. **Hand Claude the exact problem.** A **Diagnose with Claude** button sits on every alert that
   Claude can actually look into, in the Inbox, on Today and on a rejected ad or an ad with issues.
   The button opens an editable request that already names the alert, the ids, the figures and the
   playbook. It starts a read-only Desk run, kind `diagnose`, with one open run per problem. The alert
   then shows *Waiting for your Mac*, *Claude is on it* or *N suggestions*. Anything Claude suggests
   still goes through the existing Accept sheet. No new path can apply anything.

Non-goals:
- No automation of any kind: snooze never pauses, edits or applies anything.
- No new Meta calls from the server.
- No change to how proposals are applied.
- No per-person snooze: messages go to every admin, so a snooze applies to the whole account and shows who set it.

---

## 2. User flow

### 2.1 Snooze ("Got it") on desktop

1. Inbox → an open condition alert, e.g. *"82% of the account spending limit is used"*. The detail
   pane shows the existing action (**Open**) plus **Got it…** (admins), and **Diagnose with Claude**
   when Claude can look into it.
2. **Got it…** opens a small dialog:
   - Title: **Got it. When should this come back?**
   - Option A, button **In 3 days**. Sub-line: *"Stays in the Inbox without messages until Fri, Nov 14. Comes back sooner if it gets worse."*
   - Option B, button **Only if it gets worse**. Sub-line: *"No messages while it stays like this. You'll hear again at 95% of the limit. It ends by itself when this clears up."* The second sentence comes from `snooze.worse_hint()`.
   - **Cancel**.
3. After a choice, a toast says *"Snoozed until Fri"* or *"Snoozed: you'll hear if it gets worse"*,
   with **Undo**, which calls DELETE.
4. The item moves to the FYI side of the Inbox (Phase 9 triage) and drops out of the needs-action
   count. The detail shows the chip *"Snoozed until Fri, Nov 14 · Eugene"* or *"Snoozed until it gets
   worse · Eugene"*, and a **Wake it now** link.
5. Today: the alert leaves the queue ("Needs you" today). One quiet line at the end of the queue,
   **"2 snoozed alerts"**, links to `/inbox.html?show=fyi`. Until Phase 9 ships the FYI tab, the link
   is `?show=all`.
6. Settings → Alerts gets a **Snoozed now** list. Each entry shows the title, who snoozed it, until
   when or "until it gets worse", and a **Wake it now** button.

**Wake-up message.** It goes to the same people and channels as a normal alert:
- *"Worse: 96% of the account spending limit is used"*, line 1: *"You snoozed this at 82% on Nov 10."*
- *"Back as promised: “N3” looks tired"*, line 1: *"You asked to be reminded on Nov 10."*

### 2.2 Snooze on phones (390 px)

- Today, the Inbox list and Inbox items on phones currently navigate straight to `href` (`inbox.js pick()`).
  For alert items that carry actions (`actions.length > 0`), a tap opens the detail view instead.
  That is the "working Inbox detail" in Phase 9.3. If 9.3 lands first, reuse it. If not, this unit
  adds a full-width detail with a **Back** button (`history.pushState`, so the phone's Back button
  closes it).
- In the detail, buttons stack full width, each at least 44 px tall: **Open the ad** / **Diagnose with Claude** / **Got it…**.
- The Got-it dialog is a bottom dialog with two 44 px choice buttons and their sub-lines underneath.
  Its class is `al-choice`, not `.sheet`, which is the phone More dialog and must not be reused.
- On Today, each queue row has one primary button (**Open**) and a 44 px **⋯** button. The ⋯ button
  opens the same choice dialog with **Diagnose with Claude** and **Got it…**, so rows don't overflow at 320 px.

### 2.3 Diagnose with Claude on desktop

1. Inbox detail, Today queue row (⋯ on phones), or the ad page Overview status block when the ad is
   rejected or has issues: **Diagnose with Claude** (violet `btn-claude-outline`, spark icon). Admins only.
2. It opens a dialog:
   - Title: **Diagnose with Claude**
   - Body: *"Claude reads your ads on your Mac and tells you what's wrong and what to do. It changes nothing on Meta: any change comes back as a suggestion for you to accept or decline."*
   - Label **What Claude will look at**, with a textarea pre-filled from `GET /api/diagnose/draft`.
     Mono-free, 16 px on phones, 8 rows, character counter "1,240 / 4,000".
   - Small line: *"Uses the “spending without leads” checklist."* (the playbook label).
   - If the Mac is offline: note *"Your Mac is offline, so this waits until it's back."*. If it isn't set up: *"Set up your Mac on the Claude page first; this waits until then."*
   - Buttons **Cancel** / **Send to Claude** (`btn-claude`).
3. Toast: *"Sent to Claude. Follow it on the Claude page."* If a run is already open: *"Claude is already on this one."* with **Open**.
4. The button on that alert (and on every alert of the same problem, same rule and thing) becomes a chip
   that links to `/desk.html#r/<task_id>`:
   - **Waiting for your Mac** while queued
   - **Claude is on it** while claimed or running
   - **3 suggestions** (`btn-claude`) when the run left pending proposals; it links to the Claude page Accept sheet (`#waiting` or `#p/<id>`)
   - **Read Claude's answer** when done with no pending suggestions; next to it, **Diagnose again**
   - after a failed or cancelled run, the button again
5. On the Claude page the run shows as **Diagnosis** in `RUN_WORDS` / `KIND_LABELS`, with the alert
   title as its context line. Proposals use the normal suggestion card and the Accept sheet. The Inbox
   item for each proposal ("Claude suggests: …") gets the line *"From: No leads for 3 days in “Edge Bourne…”"*.

### 2.4 Diagnose on phones

- Same dialog, full height, with the textarea at 16 px so iOS doesn't zoom. The keyboard must not hide
  **Send to Claude**: the button row is sticky at the bottom of the dialog.
- The chip states are the same, as 44 px buttons.

---

## 3. Data model

Migration `NNN_alert_snooze_diagnose.sql`, written in one go (dev applies files as soon as they're saved; see ROADMAP §5):

```sql
-- W1: snooze alerts ("Got it"), the figure each alert judged, lead-quality alerts, Diagnose runs.

-- The figure the rule judged (percent used, cost per lead in cents, dry days…), so a snooze can tell
-- "clearly worse". NULL for old rows and for rules without one.
ALTER TABLE alerts ADD COLUMN measure NUMERIC;
-- Raised while snoozed: stored and shown in the Inbox, never sent.
ALTER TABLE alerts ADD COLUMN quiet BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE alert_snoozes (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    rule TEXT NOT NULL,
    entity_id TEXT NOT NULL,                 -- ad / ad set / campaign id, or 'account'
    campaign_id TEXT,                        -- for teammate scoping, copied from the alert
    mode TEXT NOT NULL CHECK (mode IN ('days', 'worse')),
    until TIMESTAMPTZ,                       -- mode 'days' only
    baseline NUMERIC,                        -- alerts.measure when snoozed
    baseline_level TEXT NOT NULL CHECK (baseline_level IN ('bad', 'warn', 'info')),
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    end_reason TEXT CHECK (end_reason IN ('expired', 'worse', 'cleared', 'by_hand')),
    ended_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CHECK ((mode = 'days') = (until IS NOT NULL)),
    CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);
-- One live snooze per problem per account.
CREATE UNIQUE INDEX alert_snoozes_live ON alert_snoozes (account_id, rule, entity_id) WHERE ended_at IS NULL;
ALTER TABLE alert_snoozes ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON alert_snoozes
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- Diagnose runs: a Desk run kind of their own. Read-only on the Mac: 'diagnose' is added EXPLICITLY to the
-- bridge's read-only kinds (not left to the unknown-kind default; 00-PLAN §3).
ALTER TABLE desk_tasks DROP CONSTRAINT desk_tasks_kind_check;
ALTER TABLE desk_tasks ADD CONSTRAINT desk_tasks_kind_check
    CHECK (kind IN ('question', 'review', 'research', 'creative', 'polish', 'render', 'advice', 'diagnose'));
CREATE INDEX desk_tasks_alert_key_idx ON desk_tasks ((options->>'alert_key')) WHERE kind = 'diagnose';
```

Grants: `db.APP_ROLE_SQL` already grants on all tables and sequences at startup. Check that the grant
loop covers new tables, as it did for `ad_versions`.

Pruning: add `("alert_snoozes", "ended_at IS NOT NULL AND ended_at < now() - interval '180 days'")` to `jobs.PRUNE`.

**Contracts with sibling units (00-PLAN build order, no column detection).** W1b is built after L2, so it reads these directly:

| Piece | Comes from | Used for |
|---|---|---|
| `lead_quality.counted()`, `qualified()` (SQL fragments) | L2 | the leads in the window, and qualified = reached `qualified` or `won` (`max_stage`) |
| `lead_quality.is_junk(row)` (pure) | L2 | `junk_high`: lost as `spam`, or flagged as looking fake, never contacted and not dismissed. `not_fit` is a real person, not junk. Repeats are already folded by `repeat_of`. |
| `leads.lost_reason` keys | L2 | `no_response`, `not_fit`, `too_small`, `price`, `went_elsewhere`, `spam`, `duplicate`, `other` |

Overdue follow-ups are **not** an alert rule: L1 covers them in Today, notifications and the digest (00-PLAN C9).

---

## 4. Backend

### 4.1 Modules

| File | New / changed | What |
|---|---|---|
| `backend/snooze.py` | **new**, pure | worse-rules, choices, wake decisions, hints, until-date maths |
| `backend/diagnose.py` | **new**, pure | playbook per rule, episode key, prompt builder |
| `backend/alert_actions_api.py` | **new** | routes for snooze and diagnose (blueprint `alert_actions`) |
| `backend/alerts.py` | changed | `measure` on every alert, 2 new rules (W1b) + `DEFAULTS`, `_dry_streak`, snapshot adds `lead_quality` (W1b), `raise_found` applies snoozes, `run` ends cleared snoozes and resolves `outside_edit` events older than 72 h |
| `backend/status_history.py` | changed | rejection / issues alerts pass `measure` (2 / 1) |
| `backend/inbox.py` | changed | `CATEGORY` for new rules, episode collapse, `quiet` rows read, snooze + diagnose fields, `actions` |
| `backend/home_api.py` | changed | `attention()` drops snoozed, adds the "N snoozed" line, passes alert id / actions |
| `backend/advice_api.py` → `desk_api.py` | refactor | `fix_runs()` becomes `desk_api.latest_runs(kind, option_key, keys=None)`, used by advice and diagnose (reused in two places, so extracting it is justified) |
| `backend/settings_api.py` | changed | `alerts` payload adds `snoozed: snooze_rows()` and `lead_columns: {lost_reason, next_step}` |
| `backend/jobs.py` | changed | PRUNE line |
| `ads/bridge/skill/SKILL.md`, `bridge/desk`, `bridge.py` | changed | "Kind `diagnose`" section; `diagnose` added explicitly to the read-only kinds; VERSION 1.11 (no `MIN_BRIDGE` change, no hold) |

### 4.2 Pure functions (signatures)

`snooze.py`:

```python
DAYS_DEFAULT = 3
WAKE_HOUR = 8  # a "days" snooze ends at 8 AM in the ad account's time zone

def choices(alert: dict) -> list[dict]:
    """What "Got it" offers for this alert row (rule, kind, level, resolved_at).
    [] for event alerts, resolved alerts, info alerts (never messaged) and rules not in WORSE.
    tracking, or a money alert (inbox.CATEGORY == "money") already at level "bad"
             → [{"mode": "days", "days": 1, "label": "Remind me tomorrow"}]   (00-PLAN §3: a red money alert waits a day at most)
    else     → [{"mode": "days", "days": 3, "label": "In 3 days"},
                {"mode": "worse", "days": None, "label": "Only if it gets worse"}]"""

def until_for(now_local: datetime, days: int) -> datetime:
    """WAKE_HOUR local on the date `days` after now_local's date (aware datetime, account tz)."""

def worse(rule: str, baseline: float | None, measure: float | None,
          base_level: str, level: str) -> bool:
    """Clearly worse than when snoozed: level went up (warn → bad), or the rule's own step (WORSE)
    was crossed. Unknown baseline or measure → level only."""

def decide(snooze: dict, alert: dict, now: datetime) -> str:
    """'wake_worse' | 'wake_expired' | 'quiet'. Worse wins over expired."""

def worse_hint(rule: str, measure: float | None, money=alerts.money) -> str:
    """The sentence under "Only if it gets worse", in plain words."""

def woke_line(snooze: dict, verdict: str, tz) -> str:
    """First line of a wake-up message: "You snoozed this at 82% on Nov 10." /
    "You asked to be reminded on Nov 10." """

def snooze_words(snooze: dict, tz) -> str:
    """Chip text: "Snoozed until Fri, Nov 14" / "Snoozed until it gets worse"."""
```

`WORSE`. Each existing `add(...)` in `evaluate()` gets a `measure=` argument:

| Rule | `measure` | Clearly worse when | `worse_hint` (example) |
|---|---|---|---|
| `ad_rejected` | 1 = has issues, 2 = rejected | measure > baseline | 1: "You'll hear again if Meta rejects it outright." 2: "It ends by itself when the ad is approved or switched off." |
| `no_delivery` | hours live, nobody has seen it | ≥ baseline + 48 | "You'll hear again if it's still unseen 2 days from now." |
| `fatigue` | frequency (1 decimal) | ≥ baseline + 1.0 | "You'll hear again if people see it 4.4 times a week." |
| `week_overspend` | 7-day spend, cents | ≥ baseline × 1.25 | "You'll hear again if 7 days' spend passes $175." |
| `spend_cap` | % of the limit used | band(measure) > band(baseline), bands: < 95, 95–99.9, ≥ 100 | < 95: "You'll hear again at 95% of the limit." ≥ 95: "You'll hear again when the limit is reached." |
| `cap_soon` | days left | measure ≤ 1 < baseline | "You'll hear again a day before it runs out." |
| `pace_over` | % over target | ≥ baseline + 15 | "You'll hear again if the month heads 35% over." |
| `cpl_high` | cost per lead, cents (no leads → spend, cents) | ≥ baseline × 1.25 | "You'll hear again if a lead costs $100 or more." |
| `no_leads` | dry days in a row (`_dry_streak`, up to 14) | ≥ baseline × 2 | "You'll hear again after 6 days without a lead." |
| `stale_data` | hours since the last pull | ≥ baseline + 24 | "You'll hear again if Meta is still silent a day from now." |
| `events_quiet` | None (level only) | level only | "It ends by itself when lead stages reach Meta again." |
| `tracking` | Meta leads in 2 days | n/a: only "Remind me tomorrow" | n/a |
| `qualified_low` | % qualified | ≤ baseline − 10 | "You'll hear again if it drops to 7%." |
| `junk_high` | % junk | ≥ baseline + 15 | "You'll hear again if junk reaches 48%." |
| `day_overspend`, `ad_approved`, `changed_outside`, `learning_limited` | n/a | not snoozable (info, or events) | n/a |

`alerts.py` additions (pure):

```python
def _dry_streak(rows: list[dict], today: date) -> int:
    """Days in a row, ending yesterday, with spend > 0 and no lead."""

def _lead_quality_alerts(lq: dict, rules: dict, add) -> None   # inside evaluate
```

New `DEFAULTS` entries (all on; numbers are suggestions to confirm with Eugene):

```python
"qualified_low": {"on": True, "percent": 20, "min_leads": 10},
"junk_high": {"on": True, "percent": 30, "min_leads": 10},
```

Rule definitions. The window is the 14 days that end 2 days ago, in the account time zone. Leads less
than 2 days old haven't had a fair chance to be worked, so they're left out.

- **`qualified_low`** (W1b), per campaign. Only `lead_quality.counted()` leads. *Worked* = `max_stage <> 'new' OR status = 'lost'`. *Qualified* = `lead_quality.qualified()`.
  - Fires when `worked ≥ min_leads` and `qualified / worked × 100 < percent`.
  - Level `warn`, `entity_id` = campaign id, `href` `/leads.html?campaign=<id>`, `measure` = the % rounded to 1 decimal.
  - Title: `Only 17% of leads from “Edge Bourne - Free intro call - Leads” qualify`.
  - Lines:
    - `2 of 12 leads the team worked in the last 14 days were qualified. You're alerted below 20%.`
    - The worst ad, only when it has ≥ 5 worked leads and the lowest rate: `Lowest: “N3”, 0 of 7 qualified.`
    - `Cheap leads that don't qualify cost more than they look.`
  - Leads still `new` never count against the rate. Untouched leads belong to L1 (Today, reminders, digest).
- **`junk_high`** (W1b), per campaign. *Leads* = `lead_quality.counted()` leads in the window; *junk* = rows where `lead_quality.is_junk` (L2).
  - Fires when `leads ≥ min_leads`, `junk ≥ 3` and `junk / leads × 100 > percent`.
  - Title: `33% of leads from “…” look like junk`.
  - Lines: `4 of 12 leads in the last 14 days look like junk (marked spam or fake, or fake-looking details and never contacted).` plus the worst-ad line.
  - `href` `/leads.html?campaign=<id>&status=lost&why=spam`.
- ~~`followups_overdue`~~: dropped (00-PLAN C9). L1's Today rows, notifications and digest cover overdue follow-ups.
- **`no_leads`** (W1a) now uses `_dry_streak` for its measure and title: `No leads for 5 days in “…”`. It still
  fires only when the streak ≥ `days`. This changes the title text of the existing rule, so update its
  test.

Snapshot additions (`alerts.snapshot`, database side):

```python
"lead_quality": {cid: {"name": str, "leads": int, "worked": int, "qualified": int, "junk": int,
                       "by_ad": [{"ad_id", "ad_name", "leads", "worked", "qualified", "junk"}]}},
```

One query over `leads WHERE {lead_quality.counted()}` in the window returns the rows (`max_stage`, `status`,
`lost_reason`, `junk_flags`, `junk_dismissed`). They're grouped in Python by campaign and ad, with `is_junk`
from L2 (W1b). Teammate scoping isn't needed in the snapshot: alerts are
account-wide and `campaign_id` scopes who sees them.

`diagnose.py`:

```python
PLAYBOOKS = {  # rule → (skill on the Mac, plain label for the dialog, what to focus on)
    "ad_rejected":      ("meta-ads", "Meta's ad rules", "policy: why Meta stopped it and the smallest edit that passes"),
    "no_delivery":      ("meta-ads-doctor", "ads that don't deliver", "delivery: review, audience, bid, budget, learning"),
    "learning_limited": ("meta-ads-doctor", "ads that don't deliver", "delivery: learning phase, budget vs target × 50 / 7"),
    "fatigue":          ("creative-fatigue-detection", "tired ads", "frequency, click and cost trends; what to refresh"),
    "cpl_high":         ("cpa-diagnostics", "why leads got expensive", "which of auction, creative, audience, form changed"),
    "no_leads":         ("meta-ads-doctor", "spending without leads", "placement mix, delivery, form, tracking, sample size"),
    "week_overspend":   ("pacing-monitor", "spend pace", "budget vs schedule, Meta's 1.75× / 7× rules"),
    "day_overspend":    ("pacing-monitor", "spend pace", "same"),
    "spend_cap":        ("pacing-monitor", "spend pace", "days left at this pace; what happens when the limit is reached"),
    "cap_soon":         ("pacing-monitor", "spend pace", "same"),
    "pace_over":        ("pacing-monitor", "spend pace", "projected month vs target"),
    "events_quiet":     ("meta-ads-doctor", "tracking", "dataset stats and quality; what stopped sending"),
    "changed_outside":  ("meta-ads", "what changed outside the console", "account activity log: who changed what, when"),
    "qualified_low":    ("meta-ads-doctor", "lead quality", "message fit, form questions, audience; lead stages by ad"),
    "junk_high":        ("meta-ads-doctor", "lead quality", "same, plus higher-intent form"),
}
# Not offered: tracking (the console's Page link, which Claude can't see), stale_data (the console's
# token), ad_approved (good news), report_review / report_sent / booking_* (not about ads).
# Added by other units: "outside_edit" (D2, present when W1a is built), "change_result" (D3).

def can_diagnose(rule: str) -> bool
def episode_key(rule: str, entity_id: str) -> str          # "no_leads:120252638288040312"
def playbook(rule: str) -> dict                             # {"skill", "label", "focus"}
def context(alert: dict, names: dict, first_seen: datetime | None, snooze: dict | None) -> dict
    """What goes into options.alert: rule, level, title, lines, measure, entity ids by level
    (ad_id / adset_id / campaign_id, resolved via `names`), first_seen, open (bool)."""
def prompt(ctx: dict, pb: dict, tz) -> str
    """The editable request, ≤ desk_api.MAX_PROMPT. Lines are trimmed to 300 chars each, 6 lines max."""
```

Prompt template (`prompt()` output):

```
Diagnose this alert from the console. Read only: change nothing on Meta.

Alert: No leads for 5 days in “Edge Bourne - Free intro call - Leads”
$100 spent since Nov 5 and not one lead. Check the form and the ads.
Open since Nov 9 (3 days).
About: campaign “Edge Bourne - Free intro call - Leads” (120252638288040312)
Use the meta-ads-doctor playbook: placement mix, delivery, form, tracking, sample size.

Tell me what is wrong, the evidence (complete days only), and what to do. If the data is too thin to
judge, say so. Suggest at most 3 changes as proposals; I'll accept or decline each one.
```

A cleared alert adds `It cleared on Nov 11: explain what happened and whether it can come back.` and
drops "Open since". A snoozed alert adds `Snoozed by Eugene until it gets worse.`

### 4.3 Wiring into the alert pipeline

`alerts.raise_found(found, now=None)` is shared by `run()` and `status_history`:

1. Load live snoozes for the `(rule, entity_id)` pairs in `found` (one query).
2. For each alert with a snooze, `verdict = snooze.decide(s, a, now)`:
   - `quiet` → `a["quiet"] = True`, so the row is stored with `quiet = TRUE` and nothing is queued.
   - `wake_worse` / `wake_expired` → end the snooze (`end_reason` 'worse' / 'expired'). Change the
     alert key to `f"{a['key']}:w{s['id']}"` so that a quiet row stored earlier the same day doesn't
     swallow the wake-up through `ON CONFLICT DO NOTHING`. Prefix the title with "Worse: " or
     "Back as promised: ", and put `woke_line()` in front of `lines`.
3. INSERT now writes `measure` and `quiet`. Notifications are skipped when `quiet` (and for `info`, as today).

`alerts.run()`, after the existing auto-close of conditions:
- For live snoozes whose pair is no longer in `found`: end them with 'cleared', **unless** Meta data
  is stale (`snap["last_pull_age_h"] > rules["stale_data"]["hours"]`). An outage must not reset
  Eugene's snoozes and then re-alert everything once data comes back.
- For live `days` snoozes whose `until` has passed but whose condition is gone: end them with 'expired'. This is housekeeping only.

`notify.queue` recipients: use whatever account-scoped admin list the tenant-isolation fix produces
(the audit cluster on `notify.admin_ids` leaking across accounts). Don't add a new call to the
unscoped one.

### 4.4 Inbox and Today shaping (pure parts in `inbox.py`)

- `CATEGORY` adds `"qualified_low": "leads", "junk_high": "leads"` (W1b).
- **Owner-closed events (00-PLAN C16):** an event alert with `resolved_at IS NULL` is open. `triage()` (W1a builds it if 9.4 hasn't): Needs action = open conditions + open events at warn/bad, not snoozed, + waiting suggestions; FYI = the rest. `DONE_OK = {"outside_edit", "change_result"}` add the action `"done"` for admins (`POST /api/alerts/<id>/done` → `resolved_at = now()`, logs `alert.done`).
- **Episode collapse** in `build()`: condition alerts with the same `(rule, entity_id)` whose newest
  row is still open collapse into one item, keyed by the newest row (`alert:<id>`). The item gains
  `since` (the first row's `created_at`) and `days_open`. Resolved episodes keep their newest row only.
  Each day's new row is a new key, so an unsnoozed problem resurfaces as unread once a day (the daily
  reminder). Quiet rows don't resurface.
- `quiet` rows: `unread = False` even without a read mark.
- Fields per alert item:
  - `alert_id`
  - `snooze` (`{mode, until, by, words}` or None)
  - `diagnose` (the latest run `{id, status, waiting}` or None; admins only)
  - `actions`, a list of `"snooze"`, `"wake"`, `"diagnose"`, `"done"`, computed from the role and from `snooze.choices` / `diagnose.can_diagnose` / `DONE_OK`
- `counts()` and the Phase 9 needs-action count leave out items with a live snooze. `triage()`, if
  Phase 9 adds one, puts them in FYI.
- Proposal items whose task is kind `diagnose` get `lines = ["From: " + options.alert.title]`.
- `home_api.attention()`:
  - drops alerts with a live snooze
  - adds `{"level": "info", "text": "2 snoozed alerts", "href": "/inbox.html?show=fyi", "action": "See them"}` when there are any
  - each alert entry carries `alert_id`, `rule` and `actions`, plus `diagnose` for admins

### 4.5 Routes (`alert_actions_api.py`)

| Route | Who | Behaviour |
|---|---|---|
| `POST /api/alerts/<int:alert_id>/snooze` body `{mode: "days"\|"worse", days?: 1\|3}` | `admin_required` (owner admin and account admin) | 404 if the row isn't in this account (RLS). 409 *"This has already cleared."* if `resolved_at`. 409 *"This one can't be snoozed."* if `choices()` is empty. 400 if the mode/days pair isn't in `choices()`. Inserts with `baseline = alerts.measure` of the **newest** row of the episode. A unique violation (a second admin got there first) returns the live snooze with 200. Logs `alert.snoozed {rule, entity, mode, until}`. Returns `{snooze, item}` |
| `DELETE /api/alerts/<int:alert_id>/snooze` | admin | Ends the live snooze for that episode with `by_hand` and `ended_by`. Used by Undo, Wake it now and Settings. Logs `alert.woken`. 404 if none |
| `GET /api/diagnose/draft?alert_id=N` or `?ad_id=X` | admin | `{prompt, playbook: {skill, label}, run: {id, status, waiting} \| null, bridge: {online, has_key}}`. 404 if the alert or ad is unknown, 409 if `can_diagnose` is false. For `ad_id` it uses the newest `ad_rejected` alert of that ad if one exists, else builds the context from the `ads` row (`effective_status`, `issues`) with `rule = "ad_rejected"`, refused unless the status is DISAPPROVED or WITH_ISSUES |
| `POST /api/diagnose` body `{alert_id \| ad_id, prompt}` | admin | Same lookup. An empty prompt gives 400 *"Tell Claude what you'd like"* (field `prompt`). Over 4,000 characters gives 400 *"Keep it under 4,000 characters"*. If a run for `episode_key` is queued, claimed or running, returns 200 `{task_id, already: true}`. Otherwise inserts `desk_tasks (kind 'diagnose', prompt, campaign_id, created_by, options)` and returns 201 `{task_id}`. `options` = `{alert_key, alert: ctx, playbook: skill, focus, source: "alert"\|"ad", ad_id?, ad_name?}`; `ad_id` / `ad_name` let the Claude page's "By ad" grouping and the ad page find it. Logs `desk.task_created {kind: diagnose, rule}` |

Teammates and read-only clients get 403 on all four routes (`admin_required`). `GET /api/inbox` and
`GET /api/home` show teammates the snooze chip read-only, with no `actions`. Clients see neither snooze
nor diagnose fields; `inbox.items_for` already limits them to status alerts, so strip
`snooze`/`diagnose`/`actions` for `role == "client"`.

`GET /api/settings` → `alerts.snoozed`: live snoozes with title (from `alert_id`), `words`, `by`, `alert_id`.

The agent side needs nothing new. `GET /api/agent/tasks/<id>` already returns `options`, and
`/api/agent/snapshot` already has `lead_stages_by_ad`. Optional, not in v1: add `open_alerts` to the
snapshot so the Monday summary knows what's snoozed.

### 4.6 Mac skill (`ads/bridge/skill/SKILL.md`, "Kind `diagnose`")

1. Read `options.alert` and `options.playbook`. Load that skill (and the `meta-ads` router for anything
   it doesn't cover). Run `desk snapshot` for lead quality when the rule is `qualified_low` or `junk_high`.
2. First check, with fresh read-only Meta calls on complete days, whether the alert still holds. If it
   doesn't, say so in the first line of the report.
3. Report: **What's wrong** / **Why: the evidence** (numbers and days) / **What to do**. "Not enough
   data yet" is a valid answer (the 2× target, 3-lead rule).
4. At most 3 proposals, using the existing kinds and money rules: budget changes at most +20% and at
   least 3 days apart, new things off, never delete. A spending-limit raise is `other`, because it's a
   billing setting Eugene changes himself.
5. Tools: the read-only list. `bridge.py` lists `diagnose` **explicitly** among the read-only kinds (one-line change, tested), rather than relying on the unknown-kind default. Turns 80, normal time limit.

Bump `bridge/desk` VERSION to 1.11 (D2 takes 1.10) and re-run `install.sh`. Don't change `MIN_BRIDGE` and don't hold
runs: an older skill still answers, because the prompt carries the whole request.

---

## 5. Frontend

### 5.1 Files

| File | Change |
|---|---|
| `frontend/js/alertmenu.js` (**new**; no ad-like token) | `snoozeDialog(item) → Promise<snooze\|null>`, `diagnoseDialog({alertId\|adId}) → Promise<task_id\|null>`, `runChip(run, {again})` → HTML, `snoozeChip(s)` → HTML, `wake(alertId)`. Builds on the Phase 9.2 shared Dialog if it exists, else on `<dialog>` the way `confirmDialog` does |
| `frontend/js/format.js` | Vocabulary: `RUN_STATE = {queued: "Waiting for your Mac", claimed: "Claude is on it", running: "Claude is on it"}`, `suggestions(n)` → "1 suggestion" / "3 suggestions" (Phase 9 word), `snoozeWords(s)` |
| `frontend/js/inbox.js` | Detail renders `actions` (Got it… / Wake it now / Diagnose or the run chip), `snoozeChip`; phone tap opens the detail for items with actions; FYI placement through Phase 9 triage |
| `frontend/js/home.js` | Queue rows: ⋯ menu on phones, inline buttons on desktop; "N snoozed alerts" line; the advice `fixButton` reuses `runChip` |
| `frontend/js/creative.js` | Ad Overview status block: when DISAPPROVED or WITH_ISSUES and admin, show **Diagnose with Claude** or the run chip (from `/api/diagnose/draft?ad_id=` `run`) |
| `frontend/js/settings.js` | `RULE_UI` gets 3 rows; new **Snoozed now** list under the rules |
| `frontend/js/tasks.js`, `board.js` | `KIND_LABELS.diagnose = "Diagnosis"`, `RUN_WORDS.diagnose = "Diagnosis"`; context line = `options.alert.title` |
| `frontend/js/conversation.js` | `asked()`: a diagnose run shows Eugene's (edited) prompt like a question, with a small "From an alert: <title>" link to `/inbox.html#alert:<id>` |
| `frontend/css/shell.css` | `.al-acts`, `.al-choice`, `.al-chip`, `.dg-form`, `.dg-count`; phone rules (≥ 44 px, 16 px textarea); violet stays reserved for Claude |

Class and id names to use: `al-acts`, `al-choice`, `al-chip`, `al-snoozed`, `dg-form`, `dg-prompt`,
`dg-count`, `dg-send`, `ib-acts`. None of them start with ad-, ads-, adset, advert, sponsor, banner or
promo, and none reuse `.sheet`, `.step`, `.report` or `.confirm`. The QA guard
(`qa/flows.cjs` ad-blocker check) covers them.

### 5.2 Exact copy

| Where | Text |
|---|---|
| Got-it button | **Got it…** (aria-label "Snooze this alert") |
| Dialog title | **Got it. When should this come back?** |
| Choice 1 | **In 3 days**: "Stays in the Inbox without messages until {Fri, Nov 14}. Comes back sooner if it gets worse." |
| Choice 1 (tracking) | **Remind me tomorrow**: "Leads may be getting lost, so this can only wait a day." |
| Choice 2 | **Only if it gets worse**: "No messages while it stays like this. {worse_hint} It ends by itself when this clears up." |
| Toasts | "Snoozed until Fri" · "Snoozed: you'll hear if it gets worse" · **Undo** · "Woken: it's back in Needs action" |
| Chip | "Snoozed until Fri, Nov 14 · Eugene" · "Snoozed until it gets worse · Eugene" |
| Wake link | **Wake it now** |
| Today line | "{n} snoozed alert(s)" + **See them** |
| Settings list title | **Snoozed now** · empty: "Nothing is snoozed. Use Got it on an alert to stop the daily messages for a while." |
| Diagnose button | **Diagnose with Claude** |
| Diagnose dialog | Title **Diagnose with Claude** · body "Claude reads your ads on your Mac and tells you what's wrong and what to do. It changes nothing on Meta: any change comes back as a suggestion for you to accept or decline." · label **What Claude will look at** · "Uses the “{label}” checklist." · **Cancel** / **Send to Claude** |
| Mac notes | "Your Mac is offline, so this waits until it's back." · "Set up your Mac on the Claude page first; this waits until then." |
| Diagnose toasts | "Sent to Claude. Follow it on the Claude page." · "Claude is already on this one." **Open** |
| Run chips | **Waiting for your Mac** · **Claude is on it** · **{n} suggestion(s)** · **Read Claude's answer** · **Diagnose again** |
| Settings rule rows | "Few leads qualify (last 14 days, leads someone has worked)": below [20] % qualified, with at least [10] leads · "Many leads look like junk": above [30] %, with at least [10] leads; hint: "Junk = marked Spam or fake, or fake-looking details and never contacted." (Overdue follow-ups have no rule: Today and the reminders cover them.) |
| Snoozed state on a teammate's view | chip only, no buttons |

---

## 6. Interaction with other features

- **Phase 9.4 Today queue and Inbox triage:**
  - Snoozed items are FYI and left out of the needs-action badge (`inbox_unread` keeps its meaning; the new count excludes snoozed items).
  - Diagnose and Got it are the queue row's secondary actions.
  - Any suggestion opens the Accept sheet, never a bare button (9.4 rule).
  - Whichever of W1 and 9.4 lands second adapts the row template. The data fields above are the contract.
- **Phase 9.3 entity links and phone Inbox detail:** alert titles get `entityLink()` for the entity.
  The phone detail is shared; W1 adds its action row only.
- **Phase 9.2 `format.js` vocabulary:** "Suggestion", "Accept", "Conversation" and "Delivering"; run
  chip words live in `format.js`, not per page.
- **5.4 Fix with Claude:** same pattern, with one helper `desk_api.latest_runs(kind, option_key)`.
  The advice chip moves to `runChip`, and its wording changes from "N to approve" to "N suggestions" as Phase 9 asks.
- **Accept sheet and money rules:** untouched. Diagnose proposals use the existing proposal kinds and
  `money_rules`; status and budget proposals still need the confirmation that shows dollars.
- **Alerts engine (2.2), status history (8.2):** `raise_found` stays the single entry point. Event
  alerts aren't snoozable. The existing auto-close of conditions stays.
- **Notifications (`notify.py`, Telegram, push, email):** quiet rows queue nothing. Wake-ups use the
  normal dedupe (`alert:<id>:<uid>`) on a new row. Depends on the tenant fix scoping recipients.
- **Reminders (1.4) and L1 follow-ups:** no alert rule for follow-ups (00-PLAN C9), so nothing duplicates Today, reminders or the digest.
- **Sibling proposals:**
  - Lost reasons / max stage turn on `junk_high` and a better qualified count.
  - L2's `is_junk` is the junk definition (flags included).
  - None of them is required for W1 to ship.
- **Agency mode / RLS:** `alert_snoozes` has `account_id` and a policy. Desk runs carry the account as
  today, and the bridge sets `DESK_ACCOUNT` per task. `dev/qa_leaks.py` walks the new GET route with
  the other account's alert and ad ids.
- **Client reports, Compare, Gallery:** none.

---

## 7. Edge cases

1. **A condition clears, then returns.** The snooze ends ('cleared') and the return alerts normally
   ("until it changes").
2. **Meta outage.** Alerts vanish because data is stale. Snoozes are kept while
   `last_pull_age_h > stale_data.hours`, so nothing re-alerts in a burst afterwards.
3. **It gets worse mid-day after today's quiet row exists.** The wake-up uses the key suffix `:w<snooze id>`, so a message is still sent.
4. **A days-snooze expires while the condition holds.** The next hourly run sends "Back as promised…" with the suffixed key.
5. **Two admins snooze at once.** The unique partial index means the second request gets the live snooze (200). The chip names the first person.
6. **Snoozing from an older row of an open episode.** The baseline is the newest row's `measure`. The route resolves the episode.
7. **Rows from before the migration have `measure` NULL.** The snooze wakes on level only, and the hint falls back to "You'll hear again if it turns red." (or the rule's ends-by-itself line).
8. **Thresholds changed while snoozed.** The baseline stays. `spend_cap` uses fixed bands (95 / 100). A rule switched off ends its snoozes as 'cleared' at the next run.
9. **Rejected ad with no alert row** (rule off, or the alert was raised before W1). The ad page's
   Diagnose builds its context from the `ads` row. The episode key `ad_rejected:<ad_id>` is shared
   with any later alert, so there's still only one open run.
10. **Diagnosing an alert that cleared.** Allowed for 3 days after it cleared ("why did it happen"); the prompt says it cleared. Older resolved items show no button.
11. **The Mac is offline or not set up.** The run queues, and the chip says "Waiting for your Mac". Today's existing "N requests waiting: your Mac is offline" line still applies.
12. **The prompt is edited down to nothing.** 400 with field `prompt`. The structured context stays in `options`, so editing can't drop the ids Claude needs.
13. **Diagnose Again while suggestions are pending.** Allowed. The chip shows the newest run. Older pending suggestions stay on the Claude page.
14. **Teammate on an assigned campaign.** They see the snooze chip but no actions, and get 403 if they call the route. Clients see none of it.
15. **Junk rule on an account with few reasons recorded.** Flagged, never-contacted leads still count as junk (L2), so the rule works before reasons are recorded.
16. **Small accounts** (fewer than 10 worked leads in 14 days). Lead-quality rules stay silent: "insufficient data" is a valid outcome.
17. **The team never updates stages.** The qualified rate isn't judged on `new` leads. Stalled leads are L1's ("No next step" in Today and `?due=none`). Untouched `new` leads are left to reminders.
18. **Phone at 320 px.** The ⋯ menu keeps queue rows to one button. The dialog's buttons stay above the keyboard.
19. **Info alerts** (`day_overspend`, `changed_outside`). They're never messaged, so there's no Got it. They can still be marked read.

---

## 8. Tests

### 8.1 Unit, pure (`backend/tests/`)

`test_snooze_logic.py` (`snooze` grouped by function, inputs as named constants):

| Case | Input | Expected |
|---|---|---|
| spend cap below the band | `worse("spend_cap", 82, 94, "warn", "warn")` | False |
| spend cap crosses 95 | `worse("spend_cap", 82, 96, "warn", "warn")` | True |
| inside the top band | `worse("spend_cap", 96, 99, "warn", "warn")` | False |
| reached | `worse("spend_cap", 96, 100, "warn", "bad")` | True |
| cost per lead +24% | `worse("cpl_high", 8000, 9900, "warn", "warn")` | False |
| cost per lead +25% | `worse("cpl_high", 8000, 10000, "warn", "warn")` | True |
| dry streak doubled | `worse("no_leads", 3, 5, …)` / `(3, 6)` | False / True |
| fatigue +1.0 | `worse("fatigue", 3.4, 4.3, …)` / `(3.4, 4.4)` | False / True |
| qualified −10 points | `worse("qualified_low", 18, 9, …)` / `(18, 8)` | False / True |
| level escalation, no measures | `worse("events_quiet", None, None, "warn", "bad")` | True |
| unknown measure, same level | `worse("cpl_high", None, 12000, "warn", "warn")` | False |
| issues → rejected | `worse("ad_rejected", 1, 2, "bad", "bad")` | True |
| decide: quiet | snooze days until `2026-11-12T16:00Z`, now `15:59Z`, not worse | `"quiet"` |
| decide: expired | same, now `16:00Z` | `"wake_expired"` |
| decide: worse beats expired | expired and worse | `"wake_worse"` |
| decide: worse mode never expires | mode worse, now + 30 days, not worse | `"quiet"` |
| until_for crosses midnight | `until_for(2026-11-10 23:30 America/Los_Angeles, 3)` | `2026-11-13 08:00 America/Los_Angeles` |
| until_for over DST end | `until_for(2026-10-31 12:00 LA, 3)` | `2026-11-03 08:00 LA` (UTC offset −8) |
| choices: event | `{"rule": "learning_limited", "kind": "event", "level": "warn"}` | `[]` |
| choices: info | `{"rule": "day_overspend", "kind": "condition", "level": "info"}` | `[]` |
| choices: resolved | `resolved_at` set | `[]` |
| choices: tracking | `{"rule": "tracking", "kind": "condition", "level": "bad"}` | `[{"mode": "days", "days": 1, "label": "Remind me tomorrow"}]` |
| choices: default | `cpl_high` warn | two choices, labels "In 3 days", "Only if it gets worse" |
| hint spend cap | `worse_hint("spend_cap", 82)` / `(96)` | "You'll hear again at 95% of the limit." / "You'll hear again when the limit is reached." |
| hint cpl | `worse_hint("cpl_high", 8000)` | "You'll hear again if a lead costs $100 or more." |
| hint no_leads | `worse_hint("no_leads", 3)` | "You'll hear again after 6 days without a lead." |
| woke line | worse, baseline 82, created `2026-11-10` | "You snoozed this at 82% on Nov 10." |
| property (fast-check-style loop, `random` with a seed) | for every rule in WORSE and any baseline b > 0: `worse(rule, b, b, l, l)` | always False (snoozing never wakes on an unchanged figure); every "× k" step also requires `measure > baseline`, so b = 0 never wakes either |

`test_alerts_logic.py` additions:

| Case | Input | Expected |
|---|---|---|
| measure on spend cap | `cap={"limit_cents": 15000, "spent_cents": 12300}` | one `spend_cap`, `measure == 82.0` |
| dry streak | `camp_days c1` = 2 days with leads, then 5 days spend 2000 / leads 0 | `_dry_streak == 5`; `no_leads` title "No leads for 5 days in “Leads”", `measure == 5` |
| streak below rule | 2 dry days, rule days 3 | no `no_leads` |
| qualified low fires | `lead_quality={"c1": {"name": "Leads", "worked": 12, "qualified": 2, "junk": None, "by_ad": [{"ad_id": "a3", "ad_name": "N3", "worked": 7, "qualified": 0, "junk": None}]}}` | one `qualified_low` for c1, `measure == 16.7`, lines[0] "2 of 12 leads the team worked in the last 14 days were qualified. You're alerted below 20%.", lines[1] "Lowest: “N3”, 0 of 7 qualified." |
| qualified at threshold | worked 12, qualified 3 (25%) | nothing |
| too few worked | worked 9, qualified 0 | nothing |
| junk fires | leads 12, junk 4 | `junk_high`, `measure == 33.3`, title "33% of leads from “Leads” look like junk" |
| junk too few | leads 12, junk 2 | nothing |
| no follow-up rule | `"followups_overdue" not in alerts.DEFAULTS` | True (00-PLAN C9) |
| healthy account still raises nothing | existing `QuietTests` with empty `lead_quality` | `[]` |

`test_inbox_logic.py` additions:
- **Collapse.** Rows `{id 10, cpl_high, c1, Nov 9, open}` and `{id 14, cpl_high, c1, Nov 10, open}` give
  one item, key `alert:14`, `since` Nov 9, `days_open == 2`.
- **Quiet row.** A `quiet` row with no read mark gives `unread == False`, and `counts()["unread"]` leaves it out.
- **Snooze attached.** `snooze` is set and the needs-action count leaves the item out.
- **Client.** The item has no `snooze`, `diagnose` or `actions` keys.
- **Proposal from a diagnose task.** `lines == ["From: No leads for 5 days in “Leads”"]`.

`test_diagnose_logic.py`:
- `playbook("cpl_high") == {"skill": "cpa-diagnostics", "label": "why leads got expensive", "focus": …}`
- `can_diagnose("tracking") is False`, `can_diagnose("stale_data") is False`, `can_diagnose("report_review") is False`, `can_diagnose("outside_edit") is True`, `can_diagnose("qualified_low") is True`
- `episode_key("no_leads", "120252638288040312") == "no_leads:120252638288040312"`
- `prompt(ctx)` for the no_leads example equals the template in §4.2 exactly (account tz America/Los_Angeles)
- 12 lines of 1,000 characters → `len(prompt) <= 4000`, 6 lines kept, each ≤ 300 characters
- a cleared ctx contains "It cleared on Nov 11" and no "Open since"
- the prompt always contains "Read only: change nothing on Meta."

`test_desk_logic.py`: `latest_runs` shaping (pure part: newest per key wins, `waiting` counted). It is
not pure today, so split the row-to-map step into a pure helper only if needed for the test.

### 8.2 `qa/flows.cjs` (new block "Alerts: snooze and diagnose")

The setup goes through `docker exec … python` the way the advice block does. It inserts alerts with
`alerts.raise_found([...])` for the current account and resets `alert_snoozes` and `notifications`
between checks.

1. An open `spend_cap` alert at measure 82 → Inbox detail shows **Got it…** and **Diagnose with Claude**.
2. **Got it…** → the dialog lists "In 3 days" and "Only if it gets worse", with "You'll hear again at 95% of the limit."
3. Choose **Only if it gets worse** → chip "Snoozed until it gets worse"; the item is out of the needs-action count; the Today queue no longer lists it and shows "1 snoozed alert".
4. Server: `raise_found` at measure 85 queues no `notifications` row and stores `quiet = true`. At measure 96 one notification row is queued with title starting "Worse:", and the snooze has `end_reason = 'worse'`.
5. Undo in the toast → the snooze is gone and the item is back in needs action.
6. **In 3 days** → chip "Snoozed until <weekday>"; Settings → Alerts → Snoozed now lists it → **Wake it now** ends it (`by_hand`).
7. A `tracking` alert offers only "Remind me tomorrow".
8. An event alert (`learning_limited`) and an info alert show no **Got it…**.
9. Teammate session: `POST /api/alerts/<id>/snooze` and `POST /api/diagnose` return 403; the chip is visible with no buttons. Client session: the Inbox has no `.al-acts`.
10. Diagnose on a `no_leads` alert: the textarea contains `120252638288040312` and "spending without leads" is named. Edit and **Send to Claude** → `desk_tasks` row kind `diagnose`, `options.alert_key = "no_leads:120252638288040312"`. A second POST returns `already: true`.
11. The chip reads "Waiting for your Mac" and links to `/desk.html#r/<id>`.
12. `dev/qa_agent_diagnose.py` (new, modelled on `qa_agent_advice.py`) claims the task, asserts that `options.alert.rule` and `options.playbook` came through, and posts a report plus one `status` proposal. The Inbox chip then reads "1 suggestion"; it opens the Accept sheet, the confirmation appears and is cancelled; the fake Meta status is unchanged.
13. Ad page: `fake_review?ad=<N3>&to=WITH_ISSUES` + sync → Overview shows **Diagnose with Claude**, and its run shares `ad_rejected:<id>` with the alert's chip.
14. Lead-quality rule: seed 12 non-test leads on the campaign, 2–16 days old (2 qualified, 6 contacted, 4 lost), run `alerts.run()` → the Inbox Leads category shows "Only 17% of leads from …"; Settings shows the 2 new rows (W1b).
15. Phone 390 px: tapping an alert opens the detail and Back closes it; every new button is ≥ 44 px; the diagnose textarea's computed font-size is 16 px; no horizontal overflow at 320 px.
16. The ad-blocker name guard passes for `alertmenu.js` and the new classes.
17. Leak test (`dev/qa_leaks.py`): `/api/diagnose/draft?alert_id=<other account's id>` returns 404.

### 8.3 Fake Meta

No new Graph endpoints: snooze and diagnose make no server-side Meta calls. Reuse
`fake_review?to=WITH_ISSUES|DISAPPROVED` for the ad page check. For the spending-limit check, write
`account_snapshot` with `spend_cap_cents` / `amount_spent_cents` through `settings_store` in the QA
setup instead of a fake endpoint.

---

## 9. Rollout

- Migration `NNN_alert_snooze_diagnose.sql`: relative slot **N+2** in 00-PLAN (after D2 and W2); the actual number is the next free one at build time. Write it in one go. W1b has no migration.
- **Settings switches:** the two new rules (W1b) appear in Settings → Alerts, **on** by default with
  20% / 10 leads and 30% / 10 leads. There's no global switch. Snooze and Diagnose are
  always available to admins.
- **Commit order** (ROADMAP §4, tests first):
  1. `snooze.py` + `diagnose.py` + tests
  2. alerts measure + new rules + tests
  3. migration + raise_found/run wiring
  4. routes
  5. Inbox / Today / ad page / Settings UI + `alertmenu.js`
  6. skill 1.10
  7. QA block
- **Eugene, after Update:**
  1. Nothing is required: no Meta setup and no new Meta writes.
  2. Optional: re-run `ads/bridge/install.sh` on the Mac so Claude follows the diagnose recipe (skill 1.10). Older helpers still answer diagnose runs as plain questions.
  3. Glance at Settings → Alerts and confirm the lead-quality thresholds. Edge Bourne's target is $60 per qualified lead, so ~20% qualified at the current cost per lead is roughly the break-even point. Ask him.
- **Unverified live:**
  - a real Diagnose run end to end on the Mac
  - wake-up messages through Telegram, push and email (same path as today's alerts)
  - the lead-quality rules on real stage data (Edge Bourne has few worked leads, so expect silence at first)

## 10. Effort

| Part | Estimate |
|---|---|
| Snooze: pure module + tests, measures in evaluate, migration, raise_found/run, routes | 0.75 day |
| Lead-quality rules + snapshot queries + tests | 0.5 day |
| Diagnose: pure module + tests, routes, `latest_runs` refactor, skill section | 0.5 day |
| Frontend: `alertmenu.js`, Inbox / Today / ad page / Settings, phone detail, CSS | 0.75 day |
| QA block + qa_agent_diagnose + leak test + screenshots | 0.5 day |
| **Total** | **~3 days (M)**. Each proposal said S; together, with the phone work and QA, they come to M |

Open decisions for Eugene:
1. The default thresholds for the two lead rules.
2. Snooze is shared by all admins of an account. That's the proposed default, because messages go to all of them.
3. "In 3 days" as the only fixed choice, or also "1 week".
