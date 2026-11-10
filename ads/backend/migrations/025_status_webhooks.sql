-- Phase 8.3: Meta's ad-account webhooks (status changes, issues, review) land next to lead webhooks.
ALTER TABLE webhook_events ADD COLUMN kind TEXT NOT NULL DEFAULT 'leadgen' CHECK (kind IN ('leadgen', 'ad_account')),
    ADD COLUMN field TEXT, ADD COLUMN object_id TEXT;
CREATE INDEX webhook_events_status_pending ON webhook_events (id) WHERE processed_at IS NULL AND kind = 'ad_account';
