# AM-A · The Ads Manager link: the Mac reads what only Ads Manager's own tools show

Unit key: `AM-A-link` · Asked by Eugene 2026-11-13 · Meta: **reads only**, through Meta's Ads MCP server on the Mac. No new write path; no MCP write tool is ever called · Money: none. Nothing here changes a budget, a status or anything live.

> **Architect resolutions (2026-11-13), applied below:**
> - Eugene's answer 2, "Direct link": the Mac helper talks to `https://mcp.facebook.com/ads` itself, as its own MCP client (streamable HTTP, JSON-RPC), with MCP authorization (OAuth 2.1 + PKCE S256 + resource indicator), its token in **its own** Keychain item (`ads-manager-link`), never Claude Code's credentials. Calls are fixed code, no Claude in the loop.
> - Client registration, in this order (MCP spec 2025-11-25 "Client Registration Approaches"): **(1) dynamic client registration** (RFC 7591; what Claude Code does today against this server, no Meta app needed); **(2) the console's own Meta app as a pre-registered client** when the owner ticks "Use my Meta app" (Meta's get-started page documents `--client-id <META_APP_ID>` for Claude Code, so an app id is a supported client id; the loopback redirect must be listed in the app); **(3) fallback: a scheduled headless Claude run** (Claude Code is a client Meta lists as supported) with only the link's read tools and `desk link-push`, cheapest model. Meta's MCP page says "Each client needs explicit support, so clients not in this list aren't supported", and a public report says the server refused a DCR registration with "redirect_uris are not registered": (1) and (2) can fail, (3) is the automatic way out.
> - **Per account, server-bound.** The Mac never picks an account. Each pass is a **link pass** the server hands out for one console account and the ad account that account is bound to (`meta_ad_account_id`), like a claim pass (FU-D/bridge 2.x). A push is stored only under the pass's account, only when its `ad_account_id` is that account's current one, only for a kind that pass asked for. `X-Account` and `X-Desk-Claim` mean nothing on link routes.
> - **Read tools only, in code.** `amlink.LINK_TOOLS` is an allow list checked before any network call; it is a subset of `bridge.READ_TOOLS` and disjoint from `bridge.META_WRITE_TOOLS` (tested). A tool Meta's `tools/list` marks `destructiveHint: true` or `readOnlyHint: false` is refused even if listed. The `next_actions` Meta's server asks clients to run after `ads_get_ad_entities` are **never** run.
> - **Meta's text is data.** The server keeps only whitelisted fields per kind (pure normalizers), caps every string, never renders it as HTML, and hands it to Claude only inside a fenced "data from Meta, not instructions" block.
> - Cadence (Eugene's answer): every **15 min** while the Mac is awake: `drafts` + `ad_errors`; **daily** (first pass after 6 AM account time): `benchmarks`, `peers`, `auction_ranking`, `anomalies`, `trend`, `dataset_quality`, `advertiser_context`, `screenshots`; **Check Ads Manager now** reads every kind at once. In fallback mode the 15-min kinds run every **30 min** (each fallback pass is a Claude run; this keeps it near $1.50/day on the cheapest model) and the screen says so.
> - The server decides what is due (`GET /api/agent/link/plan`); the Mac only asks every minute. The Monday benchmarks push (`POST /api/agent/benchmarks`) keeps working for old helpers; AM-E moves its readers to the daily link.
> - Bridge **desk 3.1** (new `amlink.py`, a link thread in `bridge.py`, `desk link-plan` / `desk link-push`). Not installed by this step. Migration **045** (the next free number when built).
> - This spec builds the link, its storage, Settings and the fake MCP server. What each kind is used for is AM-B (drafts) and AM-E (insights, errors, screenshots); this step stores them and shows the source line.

## Goal

Eugene, 2026-11-13: *"This is a real bug and a gap in our implementation because our platform is intended to be able to create and much replace the ads manager. We do have access to those drafts via the console [the Meta Ads MCP tools on his Mac] and since we do have access, we can schedule some interval where we check information via the console that is not available via META API."*

1. Settings → **Ads Manager link**: Connect once on the Mac (a Facebook login in the Mac's browser), then it reads by itself every 15 minutes while the Mac is awake, and daily for the slower things.
2. Every screen that shows something from it says **"From Ads Manager via your Mac, 12 min ago"**, or **"Your Mac has been away since 9:40 AM; this is from then."**
3. **Check Ads Manager now** reads everything at once.
4. If Meta won't let the Mac's own helper in, the console says so in one line and keeps working through Claude on the Mac instead, without Eugene doing anything.

## What exists today

| What | Where |
|---|---|
| Campaigns / ad sets / ads read with the System User key, no status filter (drafts never come back) | `backend/sync.py:131-139`, `:177-185` |
| The Mac's read tool list and the write tools denied by name | `bridge/bridge.py:40-77` |
| The bridge loop (one long poll, one run at a time) | `bridge/bridge.py:400-424` |
| `desk` helper: config, Keychain key, headers (`X-Account`), `call` | `bridge/desk:48-130` |
| Mac key check, `X-Account` choosing the account on agent routes without a task | `backend/desk_api.py:706-724`, `backend/accounts_api.py:54-75` |
| Claim passes: hashed per task, bound account, refusal rules (the pattern this copies) | `backend/desk_api.py:727-813` |
| Monday benchmarks pushed from the Mac into a settings key, any account the header names | `backend/advice_api.py:227-240`, `dev/qa_agent_benchmarks.py` |
| Today's "How you compare" card from that key | `frontend/js/home.js:326-331` |
| The Mac's state in one sentence | `backend/desk_view.py:239-263` |
| Settings sections, aliases, owner-only group | `frontend/settings.html:32-240`, `frontend/js/settings.js:14-40` |
| Fake Graph API (the fake MCP joins its process) | `dev/fake_meta.py`, `docker-compose.dev.yml:25-31` |
| Leak test, RLS sweep | `dev/qa_leaks.py:27`, `:150-157` |

## Data / migration: `backend/migrations/045_ads_manager_link.sql` (one file, written in one go)

```sql
-- AM-A: the Ads Manager link (Eugene, 2026-11-13). The Mac reads Meta's Ads MCP server; the server stores what it read
-- per console account, bound to a pass it handed out for that account.

-- Console-wide: one Mac, one Facebook login. No account_id (like user_sessions); only owners read the name.
CREATE TABLE am_link (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT 'not_connected'
        CHECK (state IN ('not_connected', 'connecting', 'connected', 'expired', 'refused', 'fallback', 'off')),
    client_kind TEXT CHECK (client_kind IN ('dcr', 'app', 'claude')),
    connected_as TEXT,                      -- a name Meta showed (<= 120 chars), owners only
    connected_at TIMESTAMPTZ,
    last_ok_at TIMESTAMPTZ,                 -- the last pass that read anything, any account
    last_error TEXT,                        -- plain words, <= 300 chars
    fallback_reason TEXT,                   -- why the direct link was refused (<= 300 chars)
    connect_requested_at TIMESTAMPTZ,       -- Connect / Reconnect pressed; the Mac starts the login once
    connect_requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    use_app BOOLEAN NOT NULL DEFAULT FALSE, -- try the console's Meta app id as the client before DCR
    helper_version TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO am_link (id) VALUES (1);

-- One pass per account per read: what the server asked for, bound to that account's ad account.
CREATE TABLE am_link_runs (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    pass_hash TEXT NOT NULL UNIQUE,         -- sha256 of the pass; the pass itself is sent once
    ad_account_id TEXT NOT NULL,            -- digits, as stored in settings when the pass was made
    kinds TEXT[] NOT NULL,
    scope TEXT,                             -- one ad id for a single screenshot (AM-E), else NULL
    mode TEXT NOT NULL CHECK (mode IN ('direct', 'claude')),
    forced_by INTEGER REFERENCES users(id) ON DELETE SET NULL,   -- Check now
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'failed', 'no_access', 'expired')),
    error TEXT,
    pushed JSONB NOT NULL DEFAULT '{}',     -- {kind: rows kept}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX am_link_runs_recent ON am_link_runs (account_id, created_at DESC);
ALTER TABLE am_link_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON am_link_runs
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- The latest normalized read per kind (and per entity where a kind has one). Replaced, never appended.
CREATE TABLE am_snapshots (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('benchmarks', 'peers', 'auction_ranking', 'anomalies', 'trend',
                                       'dataset_quality', 'advertiser_context', 'ad_errors')),
    scope TEXT NOT NULL DEFAULT '',         -- '' = the ad account
    data JSONB NOT NULL,                    -- whitelisted fields only (am_link.normalize)
    fetched_at TIMESTAMPTZ NOT NULL,        -- when the Mac read it (clamped to [run created, now])
    run_id INTEGER REFERENCES am_link_runs(id) ON DELETE SET NULL,
    via TEXT NOT NULL CHECK (via IN ('direct', 'claude')),
    PRIMARY KEY (account_id, kind, scope)
);
ALTER TABLE am_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON am_snapshots
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
```

- Drafts get their own table in AM-B (`am_drafts`), screenshots in AM-E (`am_screens`); their kinds are accepted by the push route only once those tables exist (a kind table in `am_link.KINDS`).
- Per-account switch: settings key `am_link_on` (default `"1"`), so an account whose ad account Eugene's Facebook login doesn't reach can be turned off (or is marked `no_access` by the Mac).
- `jobs.PRUNE` += `("am_link_runs", "created_at < now() - interval '30 days'")`.
- `am_link` has no `account_id`, so the RLS sweep doesn't apply; both other tables are under RLS and the sweep covers them.

## Backend

### Pure logic (TDD first), new `backend/am_link.py`

```python
FAST_KINDS = ("drafts", "ad_errors")
DAILY_KINDS = ("benchmarks", "peers", "auction_ranking", "anomalies", "trend", "dataset_quality",
               "advertiser_context", "screenshots")
KINDS = FAST_KINDS + DAILY_KINDS
FAST_MINUTES = {"direct": 15, "claude": 30}
DAILY_HOUR = 6                      # account time
CHECK_NOW_GAP = timedelta(minutes=2)
RUN_OPEN = timedelta(minutes=30)    # a pass not finished by then expires
AWAY_AFTER = timedelta(minutes=45)  # no pass at all for this long while one was due = "the Mac has been away"
MAX_PUSH_BYTES = 2_000_000
STR_MAX = 300

def due_kinds(last_ok, now_local, mode, forced) -> list[str]
    # last_ok: {kind: datetime of the last kept read}; forced (Check now) -> every kind.
    # fast kinds when older than FAST_MINUTES[mode]; daily kinds once per account day after DAILY_HOUR.

def normalize(kind, raw) -> tuple[dict | list | None, str | None]
    # (whitelisted data, None) or (None, why refused). One function per kind, each keeping only listed keys,
    # ints/floats/bools as such, strings cut to STR_MAX, ids digits-only, lists capped (drafts 200, errors 200,
    # anomalies 50). Unknown keys are dropped; names of unknown draft fields are kept as a list (AM-B).
    # A raw value that isn't the expected shape -> refused, nothing stored ("Meta's answer had an unexpected shape").

def push_refusal(run, account_ad_account, body, now) -> str | None
    # run: the am_link_runs row the pass names (None = unknown pass). Refused when: no run; run not 'open'
    # or older than RUN_OPEN; body.kind not in run.kinds; body.ad_account_id != run.ad_account_id;
    # run.ad_account_id != the account's current meta_ad_account_id (switched since the pass was made);
    # body too large. None = keep it.

def source(fetched_at, link_state, last_pass_at, now, tz, mode) -> dict
    # {"words": "From Ads Manager via your Mac, 12 min ago" | "From Ads Manager via Claude on your Mac, 2 h ago"
    #  | "Your Mac has been away since 9:40 AM; this is from then." | "Not read yet: connect the Ads Manager link in Settings.",
    #  "fetched_at", "stale": bool}

def link_status_words(state, client_kind, fallback_reason) -> str
    # the one sentence Settings and the Claude page show
```

### Routes

| Route | Owner | Account admin | Teammate | Client | Mac (bearer key) |
|---|---|---|---|---|---|
| `GET /api/am-link` (state, per-account last read per kind, source words) | all of it, `connected_as` | this account; no `connected_as` | 403 | 403 | — |
| `POST /api/am-link/connect` (Connect / Reconnect) | yes | 403 | 403 | 403 | — |
| `POST /api/am-link/disconnect` | yes (tells the Mac to delete its Keychain item, state `off`) | 403 | 403 | 403 | — |
| `PATCH /api/am-link {use_app}` | yes | 403 | 403 | 403 | — |
| `PATCH /api/am-link/account {on}` (this account's switch) | yes | yes | 403 | 403 | — |
| `POST /api/am-link/check` (Check Ads Manager now, this account) | yes | yes | 403 | 403 | — |
| `GET /api/agent/link/plan?timeout=25` | — | — | — | — | long poll: `{mode, connect: {...} \| null, disconnect: bool, runs: [{pass, run_id, account_id, ad_account_id, kinds, scope}]}` |
| `POST /api/agent/link/status` | — | — | — | — | `{state, client_kind, connected_as, error, fallback_reason}` console-wide |
| `POST /api/agent/link/push` (header `X-Link-Pass`) | — | — | — | — | `{kind, ad_account_id, fetched_at, via, tool, result}` |
| `POST /api/agent/link/finish` (header `X-Link-Pass`) | — | — | — | — | `{status: done \| failed \| no_access, error}` |
| `GET /api/agent/link/runs/<run_id>` (header `X-Link-Pass`) | — | — | — | — | that run's account, ad account, kinds and the tool + arguments per kind (403 for another run's pass) |

- `plan` (in `backend/am_link_api.py`, `agent_bp`): refuses with 403 a request carrying `X-Desk-Claim` (a Claude desk run never reads the plan or pushes link data; checked in `bind_claim` by adding the link routes to `PICK_ROUTES`). Under `account_ctx.all_accounts()` it lists open accounts with `meta_ad_account_id` set and `am_link_on`, computes `due_kinds` from each account's `am_snapshots` / `am_drafts` times, skips an account with a run still `open`, and inserts one `am_link_runs` row per account with a fresh `secrets.token_urlsafe(32)` pass (stored hashed). Nothing due → waits (1 s steps) up to `timeout`, so Check now reaches the Mac within a second. Expires `open` runs older than `RUN_OPEN` first.
- `push`: the pass alone decides the account (`account_ctx.set_current(run.account_id)`, `X-Account` ignored). `push_refusal` → 409 with the reason, nothing stored. Then `normalize(kind, result)` → refused shape → 422, nothing stored. Else upsert `am_snapshots` (or the kind's own table), `fetched_at` clamped to `[run.created_at - 1 min, now]`, `pushed[kind] = n`.
- `finish`: `no_access` → this account's line says "Your Facebook login on the Mac can't see this ad account"; `failed` → `error` kept (plain words from the Mac).
- `status`: writes `am_link`; `connected` clears `connect_requested_at`. A transition to `fallback` or `expired` raises the `link_down` alert (below).
- `/api/am-link/check`: owner or this account's admin; at most once per `CHECK_NOW_GAP` per account (429 "Checked a moment ago. Try again in a minute."); sets `am_link_force:<account>` (console-wide key) read by the next plan.
- `POST /api/agent/benchmarks` stays as is (old helpers), but the route now refuses a request without a desk claim pass when the link is `connected` (the daily link owns benchmarks; prevents the header-chosen-account path). With a pass it keeps working inside that task's account.

### Alerts

`alerts.DEFAULTS["link_down"] = {"on": True, "hours": 6}`: a condition in category `system` (`inbox.CATEGORY`), level `info` (FYI) when the link is `expired` or `refused` without fallback, or no pass finished for `hours` while the Mac's bridge was seen; `warn` after 24 h. Snoozable (`snooze.choices` "In 3 days"). Closes by itself on the next good pass. Raised once for the console under account 1's admins (the Mac is Eugene's).

## Bridge (`ads/bridge/`, desk 3.1)

### New `ads/bridge/amlink.py` (host Python, stdlib only)

```python
MCP_URL = "https://mcp.facebook.com/ads"          # ADS_LINK_MCP overrides only with ADS_DESK_CONFIG set (tests)
PROTOCOL = "2025-11-25"
KEYCHAIN_SERVICE = "ads-manager-link"             # its own item; never "Claude Code-credentials" or ads-desk-claude
REDIRECT_PORT = 47615                             # http://localhost:47615/callback (listed in the Meta app for client "app")
LINK_TOOLS = {                                    # the only tools this client may ever call
    "drafts": "ads_get_ad_entities", "ad_errors": "ads_get_errors",
    "benchmarks": "ads_insights_industry_benchmark", "peers": "ads_insights_performance_vs_peers",
    "auction_ranking": "ads_insights_auction_ranking_benchmarks", "anomalies": "ads_insights_anomaly_signal",
    "trend": "ads_insights_performance_trend", "dataset_quality": "ads_get_dataset_quality",
    "advertiser_context": "ads_insights_advertiser_context", "screenshots": "ads_get_ad_preview_screenshot",
    "_accounts": "ads_get_ad_accounts",           # connected-as and no_access checks
}
```

- **Discovery** (MCP authorization): unauthenticated `initialize` → 401 → `WWW-Authenticate` `resource_metadata` (else `/.well-known/oauth-protected-resource/ads`, then the root) → `authorization_servers[0]` → AS metadata (`/.well-known/oauth-authorization-server[/path]`, then OpenID configuration, in the spec's order). Refuse to continue unless `code_challenge_methods_supported` has `S256`. Every endpoint must be `https` (plain `http` only for `localhost` / `fake-meta` hosts when `ADS_DESK_CONFIG` is set).
- **Registration**: `use_app` → client id = the console's Meta app id (sent in the plan's `connect`) with the fixed redirect; else DCR `POST registration_endpoint {client_name: "Edge Bourne Ads console (Mac)", redirect_uris: ["http://localhost:47615/callback"], grant_types: ["authorization_code", "refresh_token"], token_endpoint_auth_method: "none"}`. A DCR refusal moves to the app id when one is known, then to fallback.
- **Login**: PKCE verifier (43-128 chars) + S256 challenge, random `state`, `resource=https://mcp.facebook.com/ads` in the authorization **and** token requests, scope from the 401's `scope` else `scopes_supported` (else omitted). A one-shot loopback server on `127.0.0.1:47615` (5 min) receives the code, checks `state`, answers a plain "You can close this tab" page. The browser is opened with `open <url>` (tests: `ADS_LINK_OPEN=fetch` follows the fake's auto-approve redirect itself).
- **Tokens**: `{client_id, access_token, refresh_token, expires_at, issuer}` as one JSON blob in the Keychain item `ads-manager-link` (account = console base URL), written through `security -i` with the command on **stdin**, so the token is never on a command line. Refresh 2 min before expiry; a rotated refresh token replaces the old one. `invalid_grant` → state `expired` ("Reconnect needed"), never a loop. Tests use `ADS_LINK_TOKEN_FILE` (honoured only with `ADS_DESK_CONFIG` set).
- **Transport**: POST JSON-RPC to the MCP URL with `Accept: application/json, text/event-stream`, `Authorization: Bearer`, `MCP-Protocol-Version`, and the `Mcp-Session-Id` the `initialize` answer gave; reads either a JSON body or SSE `data:` lines. `notifications/initialized` after `initialize`. One session per pass; closed after (`DELETE` with the session id, errors ignored).
- **Read-only guard**: `call_tool(name, args)` raises `NotAllowed` before any network unless `name in LINK_TOOLS.values()`; `tools/list` is read once per session and a listed tool with `annotations.readOnlyHint is False` or `destructiveHint is True` is refused for the session (state `failed`, "Meta marks this tool as one that changes things; the link won't call it"). `next_actions` in any answer is ignored.
- **Arguments**: built from a table `TOOL_ARGS[kind](ad_account_id, scope)` (e.g. drafts: `{"ad_account_id": "act_<id>", "object_state": "draft", "limit": 25}` + `after` cursors, at most 10 pages), checked against the tool's `inputSchema` from `tools/list` (required keys present, no key the schema lacks); a mismatch is reported as "Meta changed the tool `ads_get_errors`; update the Mac helper", never guessed around.
- **Per pass**: `_accounts` once per session; an ad account not in it → `finish no_access`. Each kind's raw result (the tool's `structuredContent`, else the JSON text content; images as `{mime, data_b64}`) → `push`. One kind failing doesn't stop the others; the pass finishes `failed` with the first error.
- **Fallback decision** (pure `fallback_reason(step, http_status, body)`): DCR 400 `invalid_redirect_uri` / `invalid_client_metadata` / "redirect_uris are not registered"; authorize error `invalid_client` / `unauthorized_client`; token `invalid_client`; MCP 403 naming an unsupported client → fallback. `access_denied` (Eugene said no) → `not_connected` with "You didn't allow it on the Facebook page". Network errors → retry next minute, never fallback.

### `bridge.py`

- A second thread `link_loop(cfg)` started in `main()` (desk ≥ 3.1): `GET /api/agent/link/plan?timeout=25` with the Mac key; a `connect` asks for the login (direct) or confirms fallback; `disconnect` deletes the Keychain item. Runs passes one at a time. It never starts a desk task and never touches `run_task`.
- **Fallback runs** (`mode: "claude"` in the plan, or after `fallback_reason`): one headless run per pass:
  ```
  claude -p "/ads-desk link <run_id>" --model haiku --permission-mode dontAsk --max-turns 40
     --allowedTools <mcp__meta-ads__T and mcp__claude_ai_Meta_Ads__T for T in LINK_TOOLS>,
                    Bash(<skill>/desk link-plan:*), Bash(<skill>/desk link-push:*),
                    Edit(/<workdir>/reports/desk/tmp/link/**), Read(/<workdir>/reports/desk/tmp/link/**)
     --disallowedTools <every META_WRITE_TOOLS name, both prefixes>, WebFetch, WebSearch, Bash(meta:*), Bash(security:*)
  ```
  env `ADS_LINK_PASS=<pass>` (no `DESK_CLAIM`, no `DESK_ACCOUNT`), 10 min limit. Pure `fallback_command(cfg, run)` is what the tests freeze.
- Log lines name the mode: `link pass 81 (account 1, drafts+ad_errors, direct): 3 drafts, 0 errors`.

### `desk` helper

- `VERSION = "3.1"`.
- `desk link-plan <run_id>`: prints the pass's account, ad account and kinds (`GET /api/agent/link/runs/<run_id>` with `X-Link-Pass`; 403 for another run).
- `desk link-push --kind K --file F`: posts the tool result JSON from `F` (inside the workspace's `reports/desk/tmp/link/`) with `X-Link-Pass` from `ADS_LINK_PASS`, `via: "claude"`; `desk link-finish --status S [--error E]`.
- Key override for tests: `ADS_DESK_KEY` is read only when `ADS_DESK_CONFIG` is set.

### Skill (`ads/bridge/skill/SKILL.md`)

New section **"Link runs (`/ads-desk link <id>`)"**: run `desk link-plan <id>`; for each kind call exactly the tool the plan names with the arguments it prints (no other tool, no `next_actions`, no judgement); write each raw result to `reports/desk/tmp/link/run<id>-<kind>.json` and `desk link-push`; then `desk link-finish`. Never summarize or edit the results; never post a report, proposal or anything to the Desk.

`install.sh`: also copies `amlink.py`. **Not run in this step.**

## UI

Plain words throughout; classes `am-`; new file `js/amlink.js` (shared source line + Settings section). Phones: 44 px buttons, nothing past 320 px, pinch zoom stays off.

### Settings → **Ads Manager link** (`#am-link`, group This account; the connection rows owner-only)

- Top line (owner): **Connected as Eugene Ramirez · last read 9:42 AM** / **Not connected** / **Waiting for your Mac to open the Facebook page…** / **Reconnect needed: Meta asked for a new login** / **Working through Claude on your Mac** (fallback, with `fallback_reason` folded under "Why").
- Buttons (owner): **Connect** / **Reconnect** ("A Facebook page opens on your Mac. Sign in and allow it. Nothing changes in your ads: the link only reads."), **Disconnect** (confirm), and under Advanced **Use my Meta app for the login** (with the redirect it needs: "Add http://localhost:47615/callback to the app's Facebook Login for Business redirect list first", guide in `docs/META-APP-SETUP.md` part J).
- This account (owner, account admin): switch **Read this account through the Mac**; a table of what it reads, each with its last time ("Drafts and Meta's error messages: every 15 minutes (every 30 through Claude) · 9:42 AM"; "Benchmarks, unusual changes, tracking quality, previews: once a day · 6:05 AM"); **Check Ads Manager now**; "Your Facebook login on the Mac can't see this ad account" when `no_access`.
- Mac helper too old (< 3.1): "Update the Mac helper to connect Ads Manager (run ads/bridge/install.sh on the Mac)."
- Teammates and clients: the section isn't listed; its routes answer 403.

### The source line everywhere

`ui.linkNote(source)` renders `am_link.source(...)` words as a muted line with a clock icon (same place and style as `ui.sourceNote`). Every AM-B / AM-E block uses it; QA checks each one carries it.

## Money and security rules

- **Reads only.** `LINK_TOOLS` is the whole list, enforced before the network; Meta's tool annotations can only narrow it. The fallback run's allow list is the same set; every write tool is denied by name. The server has no route that would turn a link result into a Meta write; AM-B's finishing and applying go through the console's existing confirmations.
- **Server-bound passes.** A push lands only in the account its pass was made for, only for that account's current ad account, only for the kinds asked, only within 30 minutes; a desk run's pass and the `X-Account` header are ignored or refused on link routes. A stolen pass can write one kind of whitelisted data into one account for 30 minutes, nothing else.
- **Untrusted text.** Normalizers keep listed keys only; strings are cut; nothing from Meta becomes HTML (`esc` everywhere, `textContent` for long text) or a link (Ads Manager links are built by the console from ids). Claude sees it only in the snapshot's fenced data block (AM-E).
- **Tokens.** The link's token lives only in the Keychain item `ads-manager-link`, written through stdin; never in a file, a log, a command line or the console. Disconnect deletes it. Claude Code's own credentials are never read by `amlink.py`.
- **OAuth.** PKCE S256 required (refuse without it), `state` checked, `resource` sent, HTTPS endpoints only, loopback redirect bound to 127.0.0.1, refresh tokens rotated.

## Fake MCP server (`dev/fake_mcp.py`, a Flask blueprint mounted at `/mcp-fake` in `fake_meta.py`'s process)

- `GET /mcp-fake/.well-known/oauth-protected-resource` (`resource`, `authorization_servers`, `scopes_supported: ["ads_mcp_management", "ads_read"]`), `GET /mcp-fake/.well-known/oauth-authorization-server` (with `code_challenge_methods_supported: ["S256"]`, `registration_endpoint`).
- `POST /mcp-fake/register` (DCR; refusable), `GET /mcp-fake/authorize` (checks client, redirect, S256 challenge, `resource`; `auto=approve` / `auto=deny` redirect at once), `POST /mcp-fake/token` (code + verifier, refresh with rotation; the old refresh token is refused after rotation; `expires_in` settable).
- `POST /mcp-fake/mcp`: `initialize` (401 with `WWW-Authenticate: Bearer resource_metadata="…", scope="ads_mcp_management ads_read"` without a token), `tools/list` (every tool name `bridge.READ_TOOLS` and `META_WRITE_TOOLS` hold, with `annotations` readOnly/destructive set truthfully and an `inputSchema` per link tool), `tools/call` for each link tool with data consistent with `fake_meta.py`'s campaign, ad set and ads (it imports them).
- `ads_get_ad_entities` with `object_state: "draft"` returns the real 2026-11-13 shape (`ad_drafts`, `ad_object_id`, `values.{field}.new`, `active_errors`, `publish_error`, cursor paging) and a `next_actions` naming `ads_activate_entity` (the client must ignore it). The drafts themselves are AM-B's.
- Write tools answer `isError` and are counted (`WRITE_CALLS`); QA asserts the count stays 0.
- Controls: `/fake/_mcp?refuse_dcr=1|refuse_client=1|deny=1|expire=1|readonly_lie=<tool>|shape=<kind>|no_access=<act>|reset=1`, `/fake/_mcp_hits` (every JSON-RPC method + tool + args, and `write_calls`).
- `docker-compose.dev.yml`: `fake-meta` also mounts `./ads/bridge:/bridge:ro`, so QA runs the link client in that container against `http://localhost:5001/mcp-fake` and the console at `http://ads-backend:5000` (Host `ads.localhost`), keys and tokens from `ADS_DESK_KEY` / `ADS_LINK_TOKEN_FILE` in `/tmp`. The user's Keychain is never touched.

## Tests

### Unit: `backend/tests/test_am_link_logic.py` (write first)

| Case | Expected |
|---|---|
| `due_kinds` fast kinds read 14 min ago, direct | none fast |
| … 16 min ago, direct / 16 min ago, claude / 31 min ago, claude | both fast / none / both fast |
| daily kinds read yesterday 6:05, now 5:59 / 6:01 account time | none / all daily |
| daily read today 6:05, now 23:00; across a DST change (America/Los_Angeles) | none; one per account day |
| `forced` | every kind |
| `push_refusal` unknown pass / run `done` / run 31 min old | refusal each |
| … kind not asked / payload ad account `act_2` vs run `1` / account switched its ad account since the pass | refusal each |
| … good | None |
| `normalize("ad_errors", …)` with extra keys, a 5,000-char message, `<script>` in a summary, a non-digit entity id | extra keys gone, message cut at 300, text kept as text (never altered into HTML), row dropped |
| `normalize(kind, "not json")`, a list where a dict is expected | `(None, "…unexpected shape")` |
| `source` 12 min old, link connected / fallback / Mac away since 9:40 / never read | the four sentences |
| `link_status_words` per state | fixed sentences |

`backend/tests/test_am_link_routes.py` (Flask test client, database, `WORKERS_ENABLED=0`): plan makes one run per eligible account with hashed passes; a second plan while open makes none; a push with account 2's pass is stored under account 2 whatever `X-Account` says; a push carrying `X-Desk-Claim` → 403; Check now twice in 2 min → 429; teammate / client on every `/api/am-link*` route → 403; account admin on `connect` → 403.

### Bridge: `bridge/test_bridge.py` (host Python)

- `set(LINK_TOOLS.values()) <= set(READ_TOOLS)` and disjoint from `META_WRITE_TOOLS`.
- `call_tool("ads_update_entity", …)` raises `NotAllowed` with no HTTP request made (a fake opener records zero calls); so does every name in `META_WRITE_TOOLS`.
- A `tools/list` with `readOnlyHint: false` on `ads_get_errors` → the session refuses it.
- An answer with `next_actions: [{tool: "ads_activate_entity", …}]` → no further call.
- PKCE: verifier length and alphabet; challenge = base64url(sha256(verifier)) without padding; AS metadata without `S256` → refuse; `http://` AS endpoint with a non-test config → refuse.
- `WWW-Authenticate` parsing (quoted `resource_metadata`, `scope`), discovery URL order for issuers with and without a path.
- `fallback_reason` table: DCR refusals and `invalid_client` → fallback; `access_denied` → not connected; timeouts → retry.
- Token store: the Keychain write builds a `security -i` stdin script and passes no secret in `argv`.
- `fallback_command`: `--model haiku`, `dontAsk`, allow list = link tools (both prefixes) + `desk link-plan` / `desk link-push` + the tmp folder; every `META_WRITE_TOOLS` name in `--disallowedTools`; no `Bash(` other than those two.

### `qa/flows.cjs` (new block "Ads Manager link", ~16 checks)

1. Owner, Settings `#am-link`: "Not connected", **Connect** present; a teammate session: no `#am-link` in the list, `GET /api/am-link` 403. **Refusal.**
2. Connect → "Waiting for your Mac…"; QA runs `amlink.py --once` in the fake-meta container (`ADS_LINK_OPEN=fetch`) → DCR, login, token; the section reads "Connected as Eugene (fake)" and the fake's `/token` saw `code_verifier` and `resource`.
3. The first pass stores drafts + errors + daily kinds for account 1; Settings shows each time; `/fake/_mcp_hits` shows only `LINK_TOOLS` names and `write_calls == 0`.
4. Account 2 with its own ad account: a run for it; its push lands in account 2; account 1's screens don't change. A push replayed with account 2's pass but `ad_account_id` of account 1 → 409. **Refusal.**
5. `X-Desk-Claim` on `/api/agent/link/push` → 403. **Refusal.**
6. `/fake/_mcp?shape=ad_errors` → push 422, nothing stored, the line keeps its old time. **Refusal.**
7. `/fake/_mcp?readonly_lie=ads_get_errors` → that kind refused on the Mac, the run `failed` with the plain reason. **Refusal.**
8. Expired refresh (`expire=1`) → "Reconnect needed", `link_down` FYI in the Inbox; Reconnect → connected; the alert closes.
9. `refuse_dcr=1` with no app id → state "Working through Claude on your Mac"; the next plan says `mode: "claude"`; `qa_desk_states.py link-push` (playing the fallback run with the pass) stores rows with `via: claude`; the source line says "via Claude on your Mac".
10. Check Ads Manager now → a plan within 2 s with every kind; again at once → "Checked a moment ago". **Refusal.**
11. Mac away: runs back-dated 2 h → every link block says "Your Mac has been away since …".
12. Disconnect → the plan carries `disconnect`; the token file is gone; state "Not connected".
13. Client session: every `/api/am-link*` → 403. **Refusal.**
14. Phone 390 and 320: buttons ≥ 44 px, nothing past the edge.
15. Guard sweep: no ad-blocker names (`am-`, `amlink.js`).
16. No console errors.

### `dev/qa_leaks.py`

Seed one marked `am_link_runs` and `am_snapshots` row per account (`data` holding the mark). Every GET route walk must not show the other account's mark (`/api/am-link`, Today, Results, Tracking health). The RLS sweep finds both tables under `account_isolation`. Account 2's admin: `GET /api/am-link` has no `connected_as`.

### Screenshots

`qa/shots.cjs`: Settings `#am-link` connected, fallback, and not connected; light and dark, desktop and 390 px.

## Live checks owed (with Eugene, on his Mac, after the Update and `ads/bridge/install.sh` desk 3.1)

1. Connect: does `mcp.facebook.com/ads` accept DCR from the Mac helper? Record the AS metadata (issuer, endpoints, scopes, `client_id_metadata_document_supported`) and the exact refusal if not. If refused: try "Use my Meta app" with the redirect added (part J); if that is refused too, confirm fallback works and costs what the plan says.
2. The real `inputSchema` of each link tool (`tools/list`): fix `TOOL_ARGS` and the fake to match before relying on any kind.
3. Token lifetime and refresh-token rotation on Meta's server; that Disconnect + Reconnect gives a working token.
4. A real drafts read for account 1 (AM-B live checks follow).
5. The Keychain item `ads-manager-link` exists and Claude Code's own `meta-ads` login still works afterwards (two clients, two tokens).
6. A fallback run on the real Mac costs and takes what it should (one pass < 2 min).

## Out of scope

- Any MCP write, any `ads_activate_entity`, any draft publishing through MCP (Eugene's answer 1).
- Reading Ads Manager with the System User through MCP on the server. Meta's page allows an **Employee-role** system user token on the MCP server; it would cover the insight kinds without the Mac, but drafts are scoped to the person who staged them, so it can't replace the link. A possible later step.
- Customer-list data, pixels, catalogs.
- Streaming or showing raw MCP answers.

Sources read for this spec: MCP authorization spec 2025-11-25 (modelcontextprotocol.io/specification/2025-11-25/basic/authorization); Meta "MCP" overview (developers.facebook.com/documentation/mcp: "Each client needs explicit support…"); Meta Ads MCP get started (…/ads-mcp-server-get-started: `--client-id <META_APP_ID>`, `ads_mcp_management` + `ads_read`, Employee-role system user tokens only); a public Claude Code issue reporting "redirect_uris are not registered" on DCR against `mcp.facebook.com/ads`.
