-- Alerts raised by the rules in alerts.py (once per thing per day), and each person's switch for them.
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    rule TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL,                 -- bad | warn | info
    title TEXT NOT NULL,
    lines JSONB NOT NULL DEFAULT '[]',
    entity_id TEXT,
    campaign_id TEXT,
    href TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX alerts_open ON alerts (rule, entity_id) WHERE resolved_at IS NULL;
ALTER TABLE users ADD COLUMN notify_alerts BOOLEAN NOT NULL DEFAULT TRUE;
