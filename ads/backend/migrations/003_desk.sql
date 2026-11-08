-- AI desk: directions typed in the dashboard, picked up by Claude on Eugene's Mac
-- (ads/bridge), answered with reports and proposals. Proposals are only recorded
-- here; applying them is phase 4 and always needs a person's approval.
CREATE TABLE desk_tasks (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('question', 'review', 'research', 'creative')),
    prompt TEXT NOT NULL,
    campaign_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'claimed', 'running', 'done', 'failed', 'cancelled')),
    progress TEXT,
    summary TEXT,
    error TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX desk_tasks_status_idx ON desk_tasks (status, created_at);

CREATE TABLE desk_reports (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES desk_tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX desk_reports_task_idx ON desk_reports (task_id);

CREATE TABLE desk_proposals (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES desk_tasks(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('budget', 'status', 'creative', 'targeting', 'other')),
    title TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    entity_name TEXT,
    field TEXT,
    current_value TEXT,
    proposed_value TEXT,
    rationale TEXT,
    expected TEXT,
    rollback TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'declined', 'applied', 'failed', 'expired')),
    decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX desk_proposals_task_idx ON desk_proposals (task_id);
