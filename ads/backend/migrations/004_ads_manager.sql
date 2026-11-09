-- Ads page: ad sets, creative details on ads, and a log of every change made to Meta
-- from the dashboard (who, what, old -> new, result).
CREATE TABLE adsets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    campaign_id TEXT,
    status TEXT,
    effective_status TEXT,
    daily_budget_cents INTEGER,
    lifetime_budget_cents INTEGER,
    optimization_goal TEXT,
    learning_stage TEXT,
    delivery JSONB,
    targeting_summary TEXT,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE campaigns ADD COLUMN lifetime_budget_cents INTEGER;
ALTER TABLE campaigns ADD COLUMN bid_strategy TEXT;

ALTER TABLE ads ADD COLUMN creative_id TEXT;
ALTER TABLE ads ADD COLUMN object_type TEXT;
ALTER TABLE ads ADD COLUMN title TEXT;
ALTER TABLE ads ADD COLUMN body TEXT;
ALTER TABLE ads ADD COLUMN cta_type TEXT;
ALTER TABLE ads ADD COLUMN video_id TEXT;
ALTER TABLE ads ADD COLUMN image_url TEXT;
ALTER TABLE ads ADD COLUMN created_time TIMESTAMPTZ;
ALTER TABLE ads ADD COLUMN issues JSONB;

CREATE TABLE meta_changes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    level TEXT NOT NULL CHECK (level IN ('campaign', 'adset', 'ad')),
    entity_id TEXT NOT NULL,
    entity_name TEXT,
    campaign_id TEXT,
    action TEXT NOT NULL,          -- status | budget | duplicate | create
    old_value TEXT,
    new_value TEXT,
    ok BOOLEAN NOT NULL,
    error TEXT,
    proposal_id INTEGER REFERENCES desk_proposals(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX meta_changes_entity_idx ON meta_changes (entity_id, created_at DESC);
CREATE INDEX meta_changes_campaign_idx ON meta_changes (campaign_id, created_at DESC);
