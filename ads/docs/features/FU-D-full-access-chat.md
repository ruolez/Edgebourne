# FU-D · Full access for the owner's own conversations, with previews that come back into the chat

Unit key: `FU-D-full-access-chat` · Asked by Eugene 2026-11-12 · Meta: **no new write path**. Claude still never writes to Meta; uploads and new ads go through the console as today · Money: none. Every Meta money write still needs Accept.

> **Architect resolutions (2026-11-12), applied below:**
> - Eugene's answer: **"Only me, with a re-check."** Only conversations the **console owner** types himself (Claude page / conversation view) can run with full access, and only after he re-enters his password. Teammates, account admins, clients and **every automatic run** (Diagnose, schedules, the follow-through after an Accept, anything started from ad comments, lead text, alerts, swipes or Meta's advice) keep the cluster-7 sandbox (`bridge.allowed_tools` / `denied_tools` / `private_paths`) exactly.
> - "Only me" is pinned to one person: a new `users.full_access_allowed` flag, set by the migration on the console's first owner (lowest id among admins of every account) and editable nowhere in the UI. A later "admin of every account" doesn't get it.
> - The unlock lives **on the server**, on that sign-in's `user_sessions` row. It ends at sign-out, when the session ends, on **Lock now**, on a password change, and at the latest **12 hours** after unlocking. That's stricter than "expires with the session" (sessions last 31 days); 12 h is one working day.
> - **The server decides, never the Mac.** The flag is fixed at **claim time** on the task row and handed to the Mac in the claim answer, bound to that task's pass (bridge 2.x claims). The bridge runs full only when the server's answer says `access: "full"` for that claimed task. Nothing a browser, a task's text or a request body says can set it.
> - Full = the terminal's tools: Bash, Read/Write/Edit, Glob/Grep, WebFetch/WebSearch, Skill, ToolSearch, Task, the meta-ads MCP **read** tools and Eugene's other MCP servers. It still runs in `dontAsk` mode, so `~/.claude/settings.json` ask rules and the meta-ads guard hook keep **denying** budget, status, publish, delete and targeting writes. Meta write tools are also listed in `--disallowedTools`. Neither file is changed.
> - Renders made in a conversation come back **into that conversation** as image or video attachments (`desk attach`, a new subcommand next to `desk upload`, stored by the console), with **Upload as draft** (the existing media upload, then New ad with it picked, created switched off) and **Change it** (a reply about that preview).
> - Bridge **desk 3.0**. Not installed by this step.
> - Migration **043** (the next free number when built; FU-A, FU-B and FU-C add none). *Built as **044**: FU-B took 043.*
> - *After the security review (2026-11-13): full access works only in the owner's own account (Edge Bourne); a full run's Bash runs inside Claude Code's OS sandbox (`bridge.full_settings`, no network, no Keychain or credentials, the Claude token unset) and the Playwright / Chrome servers are left out; nobody else can reset the flagged owner's password, and a temporary password never unlocks; the flag follows `ADMIN_EMAIL`. The "Sign out everywhere" control named below doesn't exist: the notice and Your account say to change the password, which signs out the other devices and ends full access.*

## Goal

Eugene, 2026-11-12: *"make sure I can talk to claude via web with all tool access just like I would via terminal on my pc, for example I asked to design a new ad and show me preview, but there is no access to video rendering tools... web claude chat fully connected to terminal claude code functionality"*

1. On the Claude page, Eugene taps **Turn on full access**, types his password, and sees **Full access on · until 9:40 PM · Lock now**.
2. What he types from then on runs on his Mac with the same tools as Claude Code in his terminal: rendering videos with ffmpeg and headless Chrome (ad-creative-render), files, the web, his skills, Meta reads.
3. "Design a new ad and show me a preview" ends with the image or video **in the chat**, with **Upload as draft** and **Change it** under it.
4. Nothing else gets more power: other people's requests and automatic runs keep today's sandbox, and Meta money changes still wait for Accept.

## What exists today

| What | Where |
|---|---|
| Sign-ins as rows (`user_sessions`, cookie key hashed), sign-out deletes, password change bumps `session_version` | `backend/migrations/034_user_sessions.sql`, `backend/auth.py:18-55`, `161-167`, `213-230` |
| Owner = admin with no account (`is_owner`) | `backend/auth.py:58-60` |
| Creating a request and replying (admins) | `backend/desk_api.py:279-299`, `382-418` |
| Automatic requests: schedules, Diagnose, follow-through after Accept, swipe briefs, polish/render/advice | `desk_api.py:330-340`, `443-450`; `alert_actions_api.py`; `swipes_api.py` (brief → `kind creative` + `swipe_ids`); `ads_api.py` render requests |
| Claim with a per-run pass; the pass binds every agent call to its task and account | `backend/desk_api.py:649-760`, migration `033_desk_claims.sql` |
| "Only the owners wrote this conversation" (`NOT_OWNER_TURN`, `from_owner`) | `backend/desk_api.py:722-760` |
| What the Mac gets for a claimed task | `backend/desk_api.py:763-799` |
| The sandbox: allow list, deny list, private paths, render tools only for render/advice | `bridge/bridge.py:40-131` |
| The headless run: `claude -p … --permission-mode dontAsk` | `bridge/bridge.py:208-296` |
| `desk upload` → `/api/agent/media/upload` → Meta media library | `bridge/desk:130-158`, `backend/desk_api.py:1185-1191`, `ads_api.py:1038-1074`, nginx `ads.conf:78-90` |
| Open risk recorded: render runs' node/ffmpeg reach past file rules | `ads/README.md:209-215`, ROADMAP §5 |
| Conversation view | `frontend/js/conversation.js`, `desk.js:470-500` (reply, `about_proposal`) |
| New ad starts from `?template=`, `?adset=`, `?proposal=` | `frontend/js/new-creative.js:145-200` |
| CSP: `media-src 'self' blob:`, `img-src 'self' … fbcdn` | `nginx/ads.conf:28` |

## Data / migration: `backend/migrations/043_full_access.sql` (one file, written in one go)

```sql
-- FU-D: full access for the console owner's own conversations (Eugene, 2026-11-12: "Only me, with a re-check").
-- The unlock belongs to one sign-in (user_sessions row), never to a browser flag; the Mac learns it only from a claim.

-- Who may ever unlock: the console's first owner. No screen changes it.
ALTER TABLE users ADD COLUMN full_access_allowed BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE users SET full_access_allowed = TRUE
 WHERE id = (SELECT MIN(id) FROM users WHERE role = 'admin' AND account_id IS NULL AND is_active);

-- The unlock, on the sign-in it was made in (no account_id: a sign-in spans accounts, like users).
ALTER TABLE user_sessions ADD COLUMN full_until TIMESTAMPTZ;           -- NULL = locked
ALTER TABLE user_sessions ADD COLUMN full_since TIMESTAMPTZ;
ALTER TABLE user_sessions ADD COLUMN full_fails INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_sessions ADD COLUMN full_fail_at TIMESTAMPTZ;
ALTER TABLE user_sessions ADD COLUMN user_agent TEXT;                  -- shown in the "turned on" notice

-- Per request: the sign-in that typed it (only when that sign-in was unlocked then), and what the Mac got at claim.
ALTER TABLE desk_tasks ADD COLUMN full_session TEXT;                   -- user_sessions.key_hash, never sent anywhere
ALTER TABLE desk_tasks ADD COLUMN access TEXT NOT NULL DEFAULT 'sandbox' CHECK (access IN ('sandbox', 'full'));
ALTER TABLE desk_tasks ADD COLUMN access_note TEXT;                    -- why a typed request ran sandboxed (locked, old helper)

-- Previews Claude made in a conversation. Kept in the database (the server stores no media files), pruned after 30 days.
CREATE TABLE desk_attachments (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    task_id INTEGER NOT NULL REFERENCES desk_tasks(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    mime TEXT NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp', 'video/mp4')),
    name TEXT NOT NULL,
    caption TEXT,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER, height INTEGER, duration_ms INTEGER,
    body BYTEA,                                   -- NULL once pruned
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pruned_at TIMESTAMPTZ,
    meta_ref JSONB,                               -- {"kind": "image", "hash": …} | {"kind": "video", "video_id": …} after Upload as draft
    drafted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    drafted_at TIMESTAMPTZ
);
CREATE INDEX desk_attachments_task ON desk_attachments (account_id, task_id);
ALTER TABLE desk_attachments ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON desk_attachments
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
```

- `jobs.PRUNE` += `("desk_attachments", …)` as an UPDATE that sets `body = NULL, pruned_at = now()` for rows older than 30 days. The row stays, so the chat says "Preview removed after 30 days". Per account, at most **1 GB** of bodies: the oldest are pruned first when an upload would go over.
- `users` stays outside RLS (`qa_leaks.RLS_EXEMPT` already says why). `user_sessions` has no `account_id`. `desk_attachments` is under RLS, and the leak test's "every table with account_id is under RLS" check covers it.

## Backend

### Pure logic (TDD), new `backend/full_access.py`

```python
HOURS = 12
MAX_FAILS = 5
FAIL_WAIT = timedelta(minutes=15)
FULL_KINDS = ("question", "review", "research", "creative")       # typed on the Claude page
AUTOMATIC_OPTIONS = ("schedule", "schedule_id", "alert_key", "alert", "accepted", "advice", "brief")

def may_unlock(user) -> str | None
    # None, or why not: not owner -> "Only the console's owner can turn on full access";
    # not user["full_access_allowed"] -> same sentence (no hint that the flag exists)

def unlock_until(now) -> datetime                        # now + HOURS

def fails_block(fails, fail_at, now) -> datetime | None  # until when wrong passwords block another try

def is_on(full_until, now) -> bool

def request_full(user, session_row, kind, options, swipe_ids, now) -> bool
    # at CREATE time (POST /api/desk/tasks, /reply): True only when ALL hold:
    #   is_owner(user) and user.full_access_allowed and is_on(session_row.full_until, now)
    #   and kind in FULL_KINDS and not swipe_ids and not any(k in options for k in AUTOMATIC_OPTIONS)

def claim_access(task, session, owner_ok, thread_has_others, bridge_version, now) -> tuple[str, str | None]
    # at CLAIM time: ("full", None) or ("sandbox", why) where why is None for a request never meant to be full:
    #   task.full_session is None                      -> ("sandbox", None)
    #   session row gone (signed out / expired)        -> ("sandbox", "Full access had ended (signed out) before your Mac picked this up.")
    #   not is_on(session.full_until, now)             -> ("sandbox", "Full access was locked before your Mac picked this up.")
    #   not owner_ok (no longer owner / allowed / active) -> ("sandbox", "…")
    #   thread_has_others (a teammate or admin wrote in this conversation) -> ("sandbox", "Someone else wrote in this conversation, so it ran with the usual tools.")
    #   task.kind not in FULL_KINDS or automatic options -> ("sandbox", None)
    #   bridge_version < (3, 0)                        -> ("sandbox", "Your Mac helper needs the update for full access (desk 3.0).")
```

### Unlock routes (`backend/auth.py`)

| Route | Owner with the flag | Other owner | Account admin | Teammate | Client |
|---|---|---|---|---|---|
| `POST /api/auth/full-access {password}` | unlocks | 403 | 403 | 403 | 403 (also `CLIENT_MAY` blocks it) |
| `DELETE /api/auth/full-access` (Lock now) | locks | 403 | 403 | 403 | 403 |
| `GET /api/auth/me` → `full_access: {allowed, on, until}` | yes | `{allowed: false}` | absent | absent | absent |

`POST`: `may_unlock`; `fails_block` → 429 "Too many wrong passwords. Try again after 3:12 PM." A wrong password → `full_fails += 1`, 400 field `password` "That password isn't right". A right one → `full_until = unlock_until(now)`, `full_since = now`, `full_fails = 0` on **this** session row only (`key_hash = hash(session.sk)`). Then `log_activity("auth.full_access_on")` and a notice to the owner by email and push: "Full access to your Mac was turned on from Chrome on Mac at 9:40 AM. Not you? Sign out everywhere in Your account." nginx: `location = /api/auth/full-access` gets the same `limit_req zone=adslogin` as sign-in.

`DELETE`: `full_until = NULL` (`auth.full_access_off`). Also cleared by: sign-out (row deleted), password change (`UPDATE user_sessions SET full_until = NULL WHERE user_id = …` in `change_password`), an admin password reset, deactivation, and `current_user()` failing (row deleted).

### Requests and the claim (`backend/desk_api.py`)

- `create_task` and `reply`: when `full_access.request_full(...)` holds, store `desk_tasks.full_session = <this session's key_hash>`. The request body can't influence it: any `full`, `access` or `options.full` field is ignored (the clean step drops unknown keys, as now).
- `claim_next()`: inside the same `UPDATE … RETURNING` transaction, read the claimed task's `full_session`, the session row and user, `NOT_OWNER_TURN` for its thread, and `bridge_version`. Compute `claim_access(...)` and write `access` and `access_note` on the task **before** the answer leaves. Only a task claimed with a pass (bridge ≥ 2.0) can ever be full, because the pass is what binds the Mac's run to it.
- `task_payload` (wait and `GET /api/agent/tasks/<id>`) returns `access` and `access_note` (never `full_session`). The bridge reads `access` from the claim answer and **checks it once more** with `GET /api/agent/tasks/<id>` carrying the pass before launching. Both must say `full`.
- `log_activity("desk.run_full", subject=task_id)` at claim when full.
- Locking while a full run is going doesn't end it (it finishes, its turn says "Ran with full access"); **Stop** ends it as today. Later turns are sandboxed.

### Attachments

| Route | Who | What |
|---|---|---|
| `POST /api/agent/tasks/<id>/attachments` (multipart `file`, `caption`) | the Mac, with that task's pass | stores a preview on that task (open task only, `_open_task`); type sniffed from the bytes (JPEG `FF D8 FF`, PNG `89 50 4E 47`, WebP `RIFF….WEBP`, MP4 `ftyp` box); images ≤ 10 MB, videos ≤ 60 MB, ≤ 12 per task; anything else → 400 in plain words ("Only JPG, PNG, WebP images or MP4 videos") |
| `GET /api/desk/attachments/<id>` | admins of the account (the Claude page's audience) | the bytes, `Content-Type` from the row, `Content-Disposition: inline`, `Cache-Control: private, max-age=3600`, Range requests (Safari needs them for video; `send_file(BytesIO, conditional=True)`) |
| `POST /api/desk/attachments/<id>/draft` | owner or this account's admin | Upload as draft: the bytes go through the existing media upload (`ads_api.upload_file` split into `upload_path(path, name, mime, actor)`) into the ad account's library. `meta_ref` stored; a second tap reuses it. Answers `{next: "/new-ad.html?media=image:<hash>&from=/desk.html%23r/<task>"}` |
| `GET /api/desk` | admins | each task's `attachments: [{id, kind, name, caption, width, height, duration_ms, pruned, drafted}]` (no bytes) |

Teammates and clients never reach the Claude page (`admin_required`), so they get 403 here too. nginx gets `location ~ ^/api/agent/tasks/[0-9]+/attachments$` with `client_max_body_size 70m`, a 300 s body timeout and no request buffering, as the upload location has.

### Uploads and Meta writes

Unchanged: Claude never creates ads. "Upload as draft" is a person's tap. It uploads media (logged in `meta_changes` as an upload, as today) and opens New ad with the media picked, which creates the ad **switched off** after its usual confirmation. The meta-ads MCP create tools stay off the Mac's lists.

## Bridge (`ads/bridge/`, desk 3.0)

### `bridge.py`

```python
FULL_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch",
              "Skill", "ToolSearch", "Task", "TodoWrite"]
FULL_MCP_SERVERS = ("playwright", "brave-search")      # Eugene's other servers, allowed whole (mcp__<server>)
META_WRITE_TOOLS = [...]   # every meta-ads tool name NOT in READ_TOOLS (ads_activate_entity, ads_update_entity,
                           #  ads_create_*, ads_delete_*, ads_boost_ig_post, ads_creative_* writes, ads_catalog_* writes,
                           #  ads_experiment_*create/update, ads_pixel_* create/update/delete, ads_*custom_audience writes,
                           #  ads_finalize_local_ad_image_upload, ads_log_ui_interaction, offer_report)

def allowed_tools(skill_dir, workdir, kind="question", web=False, access="sandbox"):
    if access != "full":
        return <today's list, unchanged>                       # the sandbox, exactly
    return (FULL_TOOLS + [f"mcp__{s}" for s in FULL_MCP_SERVERS]
            + [f"mcp__meta-ads__{n}" for n in READ_TOOLS] + [f"mcp__claude_ai_Meta_Ads__{n}" for n in READ_TOOLS])

def denied_tools(workdir, home, private=(), access="sandbox"):
    base = <today's list>                                     # .env, ~/.config, ~/.ssh, ~/.aws, ~/.gnupg, Keychains
    if access != "full":
        return base + private rules (unchanged)
    return base + [f"mcp__meta-ads__{n}" for n in META_WRITE_TOOLS] + [f"mcp__claude_ai_Meta_Ads__{n}" for n in META_WRITE_TOOLS] + [
        "Bash(meta:*)",                                # the Meta Ads CLI (writes go through Accept only)
        "Bash(security:*)", "Bash(launchctl:*)",       # Keychain and LaunchAgents
        f"Edit(/{home}/.claude/settings.json)", f"Edit(/{home}/.claude/settings.local.json)",
        f"Edit(/{home}/.claude/hooks/**)", f"Edit(/{home}/.claude/skills/ads-desk/**)",
        f"Edit(/{home}/Library/LaunchAgents/**)"]

def run_access(task, confirm):  # "full" only when the claim answer AND a fresh GET with the pass both say so, with a pass
    return "full" if task.get("claim_token") and task.get("access") == "full" and confirm == "full" else "sandbox"
```

`run_task`:
- `access = run_access(task, task_state_access(...))`.
- Full: `--permission-mode dontAsk` (kept: anything not allowed, every `ask` rule in `~/.claude/settings.json` and the meta-ads guard hook's prompts are denied in headless runs), no `private_paths`, limit `RENDER_LIMIT_SECONDS` (50 min), `--max-turns 200`. The prompt stays `/ads-desk run <id>`.
- Sandbox: byte-for-byte today's command line.
- The log line names the access: `task 41 (creative, full access): starting Claude`.

### `desk` helper

- `VERSION = "3.0"`.
- New `desk attach <id> <path> [--caption T]`: the path must resolve inside the workspace (`media_input`, realpath, so a render under `creatives/` qualifies). Size and type are checked locally first, then a multipart POST to `/api/agent/tasks/<id>/attachments` with the pass. It prints `{"id": …}`. Allowed in **every** run that has `Bash(<skill>/desk:*)`, so render runs (sandbox) can show previews too.

### Skill (`ads/bridge/skill/SKILL.md`)

A new section **"Full access runs"**:
- `desk task <id>` shows `access`. With `full`, the run has the terminal's tools for **this owner's request**. It still never writes to Meta: budget, status, publish, delete, targeting and creating ads come back as suggestions, as everywhere. `Bash(meta …)` and the MCP write tools are refused.
- **A preview is the end of a design request.** Render with ad-creative-render in `creatives/<date>-desk-<id>/`, then `desk attach <id> <file> --caption "4:5 static, version A"` for each image or video. Post a short report saying what each preview is, and end with "Tap Upload as draft to make it an ad (switched off), or Change it to tell me what to change."
- A `creative` suggestion with its `payload.media` is still the way to propose a ready ad. Attach the preview too, so the chat shows it.
- An `about_attachment` reply ("Change it") names the preview to change. Read its caption and the earlier turn.

`install.sh`: no change, beyond copying the new `desk` and skill. **Not run in this step.**

## UI

Words are plain throughout. Classes use the `fa-` (full access) and `att-` (attachments) prefixes. Phones get 44 px targets and 16 px fields (the password), nothing past the edge at 320 px, and pinch zoom stays off.

### Claude page and conversation view (owner with the flag only)

- **Off:** a quiet line above the composer (`#fa-bar`): "Claude runs with read-only tools on your Mac. **Turn on full access**" (link button, ≥ 44 px).
- **Turn on full access** opens a dialog (`confirmDialog` with a password field, `autocomplete="current-password"`, 16 px):
  - Title: "Full access for your own requests"
  - Body: "What you type here, until you lock it or for 12 hours, runs on your Mac like Claude Code in your terminal: files, video rendering, the web, your skills. Meta changes still wait for your Accept. Requests from your team, clients and automatic runs keep the read-only tools."
  - Field "Your password", button **Turn on**. A wrong password shows its error under the field. The "too many tries" message names the time.
- **On:** an amber bar (not violet: violet means Claude; amber means "careful") `#fa-bar.fa-on`: "**Full access on** · until 9:40 PM PT · **Lock now**". It sits on the Claude page above the composer and on every conversation view, and as a small amber dot next to Claude in the rail. In an account other than Edge Bourne it adds: "This conversation's answers are visible to <account>'s admins."
- Each turn says how it ran, in its meta line: "Ran with full access" (amber tag) or "Ran with the usual tools" with `access_note` when it was meant to be full ("Full access was locked before your Mac picked this up.").
- Teammates, account admins and other owners see none of this (the bar and its button aren't rendered; the routes answer 403).

### Attachments in a turn (`js/conversation.js`, new `js/attach.js`)

- Under the turn's answer, a strip of previews (`.att-list`). An image is `<img>` sized from its width and height through CSSOM. A video is `<video controls playsinline preload="metadata">` from `/api/desk/attachments/<id>` (same origin, so the CSP holds), without autoplay. A caption under each.
- Each preview has two buttons:
  - **Upload as draft** (owner and account admins): confirm "Upload this to the ad account's media library and start a new ad with it? The ad is created switched off; nothing spends until you turn it on." → POST draft → New ad opens with the media picked. Once done the button reads "Uploaded · Open New ad".
  - **Change it**: puts "About this preview (<caption>): " into the reply box, focuses it, and sends `about_attachment: <id>` with the reply (stored in the reply's `options.about_attachment`, shown in the thread).
- Pruned: "Preview removed after 30 days." Phone: previews full width (`max-height: 70vh`), buttons stacked full width at 320 px.

### New ad (`js/new-creative.js`)

`?media=image:<hash>` or `?media=video:<id>` picks that media in the library tab (or shows "Getting the video ready…" via `/api/media/video/<id>` until Meta finishes processing). Everything else is unchanged: a stepper, Create with its confirmation, the ad created off.

### Your account

The sign-ins list (if shown) and the Sign out everywhere text add: "Signing out also ends full access."

## Money and security rules

- **The server decides.** Full requires: the owner with the `full_access_allowed` flag, an unlocked sign-in **at creation and again at claim**, a typed kind, no automatic origin, no one else in the thread, and a bridge ≥ 3.0 with a claim pass. The Mac never infers it. It reads `access` from the claim answer and confirms it with its pass.
- **Forgery cases**, each a refusal test below: a body field `full`; a teammate's reply in the owner's thread; a Diagnose, schedule, swipe brief or follow-through request created while unlocked; an old helper (2.6); a request typed by an account admin; the owner after Lock now or sign-out; a stolen pass reused on another task (existing claim checks).
- **Re-check:** a password per unlock, 5 wrong tries block for 15 min (plus nginx's sign-in rate limit), at most 12 h, and a notice by email and push on every unlock.
- **Meta money:** dontAsk keeps the guard hook's and `settings.json`'s asks as denials. The MCP write tools and `meta` CLI are denied explicitly. The skill says suggestions only. Only Accept writes.
- **Residual risk, written in README "Claude on the Mac":** a full run's Bash can reach anything Eugene's user can, as his terminal can, including the environment's Claude token and files the Read rules cover. The deny rules guard the obvious paths (Keychain tool, LaunchAgents, Claude settings, hooks, the ads-desk skill), but they aren't a wall. That's the accepted cost of "like the terminal", limited to his own typed requests, re-checked by password, timed and visible. The cluster-7 sandbox stays as before for everything else.
- **Previews** are served same-origin, typed from their bytes, size-capped, `nosniff`, under RLS, and pruned.

## Tests

### Unit: `backend/tests/test_full_access_logic.py` (write first)

| Case | Expected |
|---|---|
| `may_unlock` for owner+flag / owner without flag / account admin / client | None / sentence / sentence / sentence |
| `fails_block(5, now-10 min, now)` / `(5, now-16 min)` / `(4, now)` | now+5 min / None / None |
| `is_on(None)`, `is_on(now+1s)`, `is_on(now-1s)` | False, True, False |
| `request_full` owner+flag, unlocked, kind `question`, no options | True |
| … kind `diagnose` / `polish` / `render` / `advice` | False |
| … options `{"schedule": "Daily"}` / `{"accepted": {...}}` / `{"alert_key": "x"}` / `swipe_ids [3]` | False each |
| … session locked / account admin / owner without flag | False each |
| `claim_access` session row missing | `("sandbox", "…signed out…")` |
| … `full_until` past | `("sandbox", "…locked…")` |
| … thread has another writer | `("sandbox", "Someone else wrote…")` |
| … bridge (2, 6) | `("sandbox", "…needs the update…")` |
| … all good, bridge (3, 0) | `("full", None)` |
| … `full_session` None | `("sandbox", None)` |
| `unlock_until(now)` | now + 12 h |

`test_desk_logic.py`: the attachment sniffer (pure `attachments.sniff(head_bytes)`) maps the four signatures and refuses GIF, HTML ("<!doctype"), MOV (`ftypqt`) and an MP4 with an HTML body. The size rule per kind. `clean_reply` keeps `about_attachment` only as an int.

### Bridge: `bridge/test_bridge.py` (host Python)

- `allowed_tools(..., access="sandbox")` equals today's list for every kind (a frozen expected list per kind in the test), so the sandbox can't drift.
- `access="full"` contains `Bash`, `Write`, `Edit`, `WebFetch` and `mcp__playwright`, and **no** name from `META_WRITE_TOOLS`.
- `denied_tools(..., access="full")` contains every `META_WRITE_TOOLS` name for both MCP prefixes, `Bash(meta:*)`, `Bash(security:*)`, and `Edit(//…/.claude/settings.json)` and the hooks.
- `META_WRITE_TOOLS ∪ READ_TOOLS` covers every tool the meta-ads server lists today (a fixed list in the test, updated by hand when Meta adds tools). The two sets don't overlap.
- `run_access`: no `claim_token` → sandbox; `access: "full"` but the confirm read says `sandbox` → sandbox; both full → full.
- The command line for a full task carries `--permission-mode dontAsk` (never `bypassPermissions`).
- `desk attach` refuses a path outside the workspace (symlink to `~/.ssh` resolved), a 61 MB video and a `.gif`.

### `dev/qa_desk_states.py` (extended; plays the Mac against the real database)

Checks print as JSON and are read by flows.cjs:
1. Owner session unlocked (set `full_until` on a QA session row) + task created through the route → claim with bridge version 3.0 → `access == "full"` in the wait answer and in `GET /api/agent/tasks/<id>` with the pass.
2. The same, bridge version 2.6 → `sandbox` with the update note.
3. Lock between create and claim → `sandbox` "locked".
4. Session row deleted (sign-out) before claim → `sandbox` "signed out".
5. An account admin's reply in that thread, then the owner's next turn → `sandbox` "Someone else wrote".
6. Created while unlocked: Diagnose, a schedule's run-now, a swipe brief, the follow-through after Accept → all `sandbox` with no note.
7. A body `{"full": true, "options": {"access": "full"}}` from an account admin → `full_session` NULL, `sandbox`.
8. The pass of task A asking `GET /api/agent/tasks/B` → 403 (existing claim rule, still holds).
9. Attachment POST without the pass on a pass-claimed task → 403; with it → 201; on a finished task → 409; a 61 MB body → 400.

### `dev/qa_leaks.py`

Seed one marked `desk_attachments` row per account (a 1×1 PNG). `GET /api/desk/attachments/<other account's id>` → 404 for the switched owner and account 2's admin. Account 2's client → 403 on the route. `GET /api/desk` never lists the other account's attachment names. The RLS sweep finds `desk_attachments` under its policy.

### `qa/flows.cjs` (new block "Full access", about 18 checks)

1. Owner on `desk.html`: `#fa-bar` reads "read-only tools" with **Turn on full access**.
2. A wrong password → field error, no amber bar. **Refusal.**
3. The right password → `#fa-bar.fa-on` "Full access on · until", plus an amber rail dot. `GET /api/auth/me` `full_access.on === true`. Notification queued (`/push/_sent` or the mail catcher shows "Full access to your Mac was turned on").
4. A request typed now → `qa_desk_states` claim with 3.0 → the turn shows "Ran with full access".
5. **Lock now** → bar back to off. The next typed request, claimed → "Ran with the usual tools", no note (it was never meant to be full).
6. Unlock, type, Lock **before** the claim → the turn shows "Full access was locked before your Mac picked this up."
7. Five wrong passwords → "Too many wrong passwords. Try again after …". **Refusal.**
8. Account admin session: no `#fa-bar`; `POST /api/auth/full-access` → 403. **Refusal.**
9. A second owner (QA-made admin of every account, flag false): no bar, POST → 403. **Refusal.**
10. Client: POST → 403 "read-only". **Refusal.**
11. Sign out and back in → the bar is off (the unlock didn't survive). **Refusal.**
12. Password change in Your account → the unlock is cleared.
13. Attachments: QA posts a PNG and a short MP4 (`ads/dev/media`) to a running QA task with its pass → the turn shows `.att-list img` and `.att-list video` whose `src` is `/api/desk/attachments/<id>`. The video answers a `Range: bytes=0-1` request with 206.
14. **Upload as draft** → confirm → New ad opens with `media=image:` and the library tile selected; the fake's `adimages` has it. Create → the new ad is **Off**.
15. **Change it** → the reply box starts "About this preview" and the sent reply carries `options.about_attachment`.
16. A GIF upload → 400 with "Only JPG, PNG, WebP images or MP4 videos". **Refusal.**
17. Phone 390 and 320: the password field is 16 px, Lock now ≥ 44 px, previews within the width, buttons stacked.
18. Ad-blocker guard sweep passes (`fa-`, `att-`, `attach.js`).

### Screenshots

`qa/shots.cjs`: `desk.html` with full access on (set through the API before the shot) and a conversation with one image and one video preview. Check them light and dark, desktop and 390 px.

## Live checks owed (with Eugene)

1. After the Update and `ads/bridge/install.sh` (desk 3.0; first check for a running Desk task): turn on full access, ask "design a 4:5 static for N2 with a bigger headline and show me a preview". Expect the render on the Mac with ad-creative-render, the preview in the chat, then Upload as draft → New ad → created off.
2. In that run, ask Claude to "raise the campaign budget to $25/day yourself". Expect a refusal plus a suggestion. `~/.claude/hooks/meta-ads-guard.log` shows the denial if it tried.
3. Confirm `dontAsk` denies the meta-ads guard hook's `ask` decision in a headless run, as `meta-ads/CLAUDE.md` step 4 states, with the broader allow list.
4. A video preview plays on his iPhone (Safari Range requests).
5. The email and push "Full access was turned on" arrive.

## Out of scope

- Interactive back-and-forth inside one run (a run still ends; replies continue the session, as today).
- Full access for anyone but the flagged owner, or for automatic runs. An OS sandbox (`sandbox-exec`) around full runs stays a later step (ROADMAP §5 open risk).
- Claude creating ads or drafts on Meta by itself (MCP create tools stay off).
- Streaming the run's terminal output into the browser.
