-- AM-A: the Ads Manager link (Eugene, 2026-11-13). The Mac reads Meta's Ads MCP server; the server stores what it read
-- per console account, bound to a pass it handed out for that account. Reads only: nothing here is ever written to Meta.
-- Grants come from db.APP_ROLE_SQL at boot (default privileges).

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
    scope TEXT,                             -- what Meta allowed the link's login (the narrowest it accepts), owners only
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
-- One open pass per account, whoever asks for a plan at the same time (make_runs inserts ON CONFLICT DO NOTHING).
CREATE UNIQUE INDEX am_link_runs_one_open ON am_link_runs (account_id) WHERE status = 'open';
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
