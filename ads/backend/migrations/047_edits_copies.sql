-- AM-C: editing campaigns and ad sets after creation, copies, archive/delete at every level.

-- What the sync stores so the edit form and History can show the current setup (read with the full field set).
ALTER TABLE adsets ADD COLUMN targeting JSONB;                 -- whitelisted targeting (edit_rules.TARGETING_KEYS)
ALTER TABLE adsets ADD COLUMN placements_fp TEXT;              -- fingerprint of the placement keys (Advantage+ = 'auto')
ALTER TABLE adsets ADD COLUMN attribution JSONB;
ALTER TABLE adsets ADD COLUMN destination_type TEXT;
ALTER TABLE adsets ADD COLUMN billing_event TEXT;
ALTER TABLE adsets ADD COLUMN frequency JSONB;                 -- frequency_control_specs
ALTER TABLE adsets ADD COLUMN ever_delivered BOOLEAN NOT NULL DEFAULT FALSE;  -- any impression ever (ad_daily or Meta)
ALTER TABLE campaigns ADD COLUMN special_ad_categories TEXT[];
-- The AM-C setup fields are compared (D2) only once a full read stored them, so the first sync after the update records nothing.
ALTER TABLE adsets ADD COLUMN edit_seen_at TIMESTAMPTZ;
ALTER TABLE campaigns ADD COLUMN edit_seen_at TIMESTAMPTZ;

-- What changed in Ads Manager (D2) now covers the AM-C setup fields too (status_history.EDIT_SETUP).
ALTER TABLE status_events DROP CONSTRAINT status_events_field_check;
ALTER TABLE status_events ADD CONSTRAINT status_events_field_check CHECK (field IN (
    'created', 'effective_status', 'configured_status', 'review', 'issues', 'learning', 'daily_budget', 'lifetime_budget', 'spend_cap',
    'bid_strategy', 'bid_amount', 'start_time', 'end_time', 'targeting',
    'placements', 'optimization_goal', 'attribution', 'frequency', 'special_ad_categories'));

-- Copies: resumable like campaign_builds (one per Make a copy).
CREATE TABLE copy_jobs (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    level TEXT NOT NULL CHECK (level IN ('campaign', 'adset')),
    source_id TEXT NOT NULL,
    target_campaign_id TEXT,                       -- an ad set copied into another campaign
    plan JSONB NOT NULL,                           -- {name, adsets: [{id, name, ads: [ids]}]} picked by the person
    made JSONB NOT NULL DEFAULT '{}',              -- {campaign_id, adsets: {src: new}, ads: {src: new}, unknown}
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'partial', 'done')),
    error TEXT,
    client_key TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, client_key)
);
CREATE INDEX copy_jobs_account_idx ON copy_jobs (account_id, id DESC);
ALTER TABLE copy_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON copy_jobs
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
