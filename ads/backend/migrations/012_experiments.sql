-- Tests Eugene runs on the ads (roadmap 3.1). Each arm is one or more ads or ad sets:
-- [{"label": "A", "name": "Original", "ad_ids": ["…"], "adset_ids": []}].
CREATE TABLE experiments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    hypothesis TEXT,
    metric TEXT NOT NULL CHECK (metric IN ('cpl', 'cpql', 'ctr', 'hook')),
    arms JSONB NOT NULL,
    start_day DATE NOT NULL,
    end_day DATE,
    target_cents INTEGER,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'stopped')),
    winner TEXT,
    verdict TEXT,
    notes TEXT,
    proposal_id INTEGER REFERENCES desk_proposals(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);
CREATE INDEX experiments_status_idx ON experiments (status, start_day DESC);

-- Claude can propose a test; approving it creates the record.
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_kind_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_kind_check
    CHECK (kind IN ('budget', 'status', 'creative', 'targeting', 'experiment', 'other'));
