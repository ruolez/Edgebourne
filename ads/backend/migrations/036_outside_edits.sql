-- D2: budget, bid, dates and audience changes made outside the console are recorded like status changes;
-- a budget change confirmed knowingly says which warning was accepted. No new table: every table here
-- already has account_id and the account_isolation policy.

ALTER TABLE campaigns
    ADD COLUMN start_time TIMESTAMPTZ,
    ADD COLUMN stop_time TIMESTAMPTZ,            -- Meta's campaign end is `stop_time`
    ADD COLUMN spend_cap_cents BIGINT,           -- campaign spending limit (not the account's)
    ADD COLUMN setup_seen_at TIMESTAMPTZ;        -- NULL until a full read stored these fields once
ALTER TABLE adsets
    ADD COLUMN bid_strategy TEXT,
    ADD COLUMN bid_amount_cents INTEGER,
    ADD COLUMN start_time TIMESTAMPTZ,
    ADD COLUMN end_time TIMESTAMPTZ,
    ADD COLUMN targeting_fp TEXT,                -- status_history.targeting_fingerprint of the audience
    ADD COLUMN setup_seen_at TIMESTAMPTZ;

ALTER TABLE status_events DROP CONSTRAINT status_events_field_check;
ALTER TABLE status_events ADD CONSTRAINT status_events_field_check CHECK (field IN (
    'created', 'effective_status', 'configured_status', 'review', 'issues', 'learning',
    'daily_budget', 'lifetime_budget', 'spend_cap', 'bid_strategy', 'bid_amount',
    'start_time', 'end_time', 'targeting'));
CREATE INDEX status_events_budget_idx ON status_events (entity_id, at DESC)
    WHERE field IN ('daily_budget', 'lifetime_budget');
CREATE INDEX status_events_campaign_at_idx ON status_events (campaign_id, at);

ALTER TABLE meta_changes ADD COLUMN accepted TEXT[];   -- warnings confirmed knowingly: {big}, {recent}, {big,recent}
CREATE INDEX meta_changes_budget_idx ON meta_changes (entity_id, created_at DESC)
    WHERE action = 'budget' AND ok;
