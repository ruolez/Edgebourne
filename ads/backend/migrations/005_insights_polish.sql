-- Richer daily numbers (video funnel, all clicks), the post behind each ad (comments),
-- a short-lived cache for on-demand Meta reads (breakdowns, rankings, comments,
-- activity), task options for polish/render runs, and a machine-readable payload on
-- proposals so "create this ad" can be approved with one click.
ALTER TABLE ad_daily ADD COLUMN clicks_all INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN video_3s INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN thruplays INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN video_p25 INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN video_p50 INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN video_p75 INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ad_daily ADD COLUMN video_p100 INTEGER NOT NULL DEFAULT 0;

ALTER TABLE ads ADD COLUMN story_id TEXT;

CREATE TABLE meta_cache (
    key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE desk_tasks DROP CONSTRAINT desk_tasks_kind_check;
ALTER TABLE desk_tasks ADD CONSTRAINT desk_tasks_kind_check
    CHECK (kind IN ('question', 'review', 'research', 'creative', 'polish', 'render'));
ALTER TABLE desk_tasks ADD COLUMN options JSONB NOT NULL DEFAULT '{}';
ALTER TABLE desk_tasks ADD COLUMN scorecard JSONB;

ALTER TABLE desk_proposals ADD COLUMN payload JSONB;
