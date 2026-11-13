-- D1 Match Ads Manager: Meta's own account total per day, and each check or pull of older days.
-- Read-only on Meta (insights GETs); nothing here is ever written to Meta.
-- Grants come from db.APP_ROLE_SQL at boot (default privileges).

-- Meta's own account-level total per day (what Ads Manager shows), read nightly or on "Check now".
-- Compared with SUM(ad_daily) at read time, so a later hourly sync is never judged against an old sum.
CREATE TABLE meta_day_totals (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    day DATE NOT NULL,                        -- the ad account's time zone, like ad_daily.day
    spend_cents BIGINT NOT NULL DEFAULT 0,
    leads INTEGER NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, day)
);
ALTER TABLE meta_day_totals ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON meta_day_totals
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- One row per check or pull: what was read, how far it got, what Meta changed.
CREATE TABLE numbers_runs (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('nightly', 'check', 'pull', 'report')),
    start_day DATE NOT NULL,
    end_day DATE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,   -- NULL for the worker
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    ok BOOLEAN,
    error TEXT,                                -- plain words (meta_client.plain), never the raw token-bearing text
    parts_done INTEGER NOT NULL DEFAULT 0,
    parts_total INTEGER NOT NULL DEFAULT 0,
    changed JSONB,                             -- [{day, spend_cents, leads}] deltas the restate wrote
    summary JSONB                              -- numbers_check.summary() after the run
);
CREATE INDEX numbers_runs_recent_idx ON numbers_runs (account_id, id DESC);
ALTER TABLE numbers_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON numbers_runs
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
