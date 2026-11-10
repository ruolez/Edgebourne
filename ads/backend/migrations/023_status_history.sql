-- Phase 8.1: status history. Sync compares what Meta says now with what was stored and keeps every change.
ALTER TABLE campaigns ADD COLUMN configured_status TEXT, ADD COLUMN issues JSONB,
    ADD COLUMN created_time TIMESTAMPTZ, ADD COLUMN updated_time TIMESTAMPTZ;
ALTER TABLE adsets ADD COLUMN configured_status TEXT, ADD COLUMN issues JSONB, ADD COLUMN learning JSONB,
    ADD COLUMN created_time TIMESTAMPTZ, ADD COLUMN updated_time TIMESTAMPTZ;
ALTER TABLE ads ADD COLUMN configured_status TEXT, ADD COLUMN updated_time TIMESTAMPTZ;

CREATE TABLE status_events (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    level TEXT NOT NULL CHECK (level IN ('campaign', 'adset', 'ad')),
    entity_id TEXT NOT NULL,
    entity_name TEXT,
    campaign_id TEXT,
    adset_id TEXT,
    field TEXT NOT NULL CHECK (field IN ('created', 'effective_status', 'configured_status', 'review', 'issues', 'learning')),
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL CHECK (source IN ('poll', 'webhook', 'console', 'backfill')),
    detail JSONB,
    change_id INTEGER REFERENCES meta_changes(id) ON DELETE SET NULL,
    meta_time TIMESTAMPTZ,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX status_events_entity_idx ON status_events (entity_id, at DESC);
CREATE INDEX status_events_account_idx ON status_events (account_id, at DESC);
ALTER TABLE status_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON status_events
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
