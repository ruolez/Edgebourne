-- Lead stages sent to Meta (Conversions API for CRM), one row per lead and stage.
CREATE TABLE crm_events (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    meta_lead_id TEXT,
    stage TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | sent | failed | skipped
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    UNIQUE (lead_id, stage)
);
CREATE INDEX crm_events_pending ON crm_events (lead_id, id) WHERE status = 'pending';
