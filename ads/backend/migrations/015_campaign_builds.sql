-- Roadmap 4.3: a new campaign built in the console. The spec is what was filled in; `made`
-- records every Meta id created so far, so a build that stopped halfway resumes instead of
-- creating duplicates. Everything is created PAUSED; publishing is a separate step.
CREATE TABLE campaign_builds (
    id SERIAL PRIMARY KEY,
    spec JSONB NOT NULL,
    made JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'partial', 'created', 'published')),
    error TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
