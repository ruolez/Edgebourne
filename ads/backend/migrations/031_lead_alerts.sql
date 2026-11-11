-- Every lead Meta sends is announced once (email, phone alerts, automatic reply), whichever path
-- stored it: the webhook, the catch-up or Refresh. store_lead inserts alerted_at as NULL and the
-- pass that queues the alerts claims it. Rows that exist already, and rows inserted any other way
-- (dev seed, QA), count as announced.
ALTER TABLE leads ADD COLUMN alerted_at TIMESTAMPTZ DEFAULT now();
CREATE INDEX leads_unannounced_idx ON leads (created_time) WHERE alerted_at IS NULL;

-- A form filled in without an ad (a Page post, a shared link) is a real lead, not a test one.
ALTER TABLE leads ADD COLUMN is_organic BOOLEAN NOT NULL DEFAULT FALSE;

-- A lead ping that fails waits longer each time (1, 5, 15, then 60 minutes) instead of every pass.
ALTER TABLE webhook_events ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- The new-lead email goes through the notification queue (claimed, retried) and keeps its HTML part.
ALTER TABLE notifications ADD COLUMN html TEXT;
