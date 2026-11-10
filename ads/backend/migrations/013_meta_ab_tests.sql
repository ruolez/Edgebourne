-- Roadmap 3.2: a tracked test can also run on Meta as an A/B test (ad study).
-- meta_study: {"id", "type", "start_day", "end_day", "daily_budget_cents", "created_at", "fetched_at", "status", "results"}.
ALTER TABLE experiments ADD COLUMN meta_study JSONB;

ALTER TABLE meta_changes DROP CONSTRAINT meta_changes_level_check;
ALTER TABLE meta_changes ADD CONSTRAINT meta_changes_level_check CHECK (level IN ('campaign', 'adset', 'ad', 'study'));
