-- AM-E: Meta's picture of each ad, read through the Mac's Ads Manager link (AM-A), one ad per link pass. The other
-- extra insights (benchmarks, peers, auction ranking, unusual changes, trends, error messages, tracking quality, business
-- context) stay in am_snapshots. Reads only: nothing here is ever written to Meta.
CREATE TABLE am_screens (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    ad_id TEXT NOT NULL,
    placement TEXT NOT NULL DEFAULT '',      -- '' = Meta's default; else a placement key Meta named (<= 40)
    mime TEXT NOT NULL CHECK (mime IN ('image/png', 'image/jpeg', 'image/webp')),
    width INTEGER, height INTEGER,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    body BYTEA,                              -- NULL once pruned (after 30 days: "Get it again")
    fetched_at TIMESTAMPTZ NOT NULL,
    run_id INTEGER REFERENCES am_link_runs(id) ON DELETE SET NULL,
    via TEXT NOT NULL CHECK (via IN ('direct', 'claude')),
    PRIMARY KEY (account_id, ad_id, placement)
);
ALTER TABLE am_screens ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON am_screens
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- A scoped pass (one ad's picture) is looked up by its ad for the 2-minute gap and the daily round.
CREATE INDEX am_link_runs_scope ON am_link_runs (account_id, scope, created_at DESC) WHERE scope IS NOT NULL;
