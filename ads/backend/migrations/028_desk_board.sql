-- The Claude page as one board: requests can be cleared away (kept for Claude's memory and each
-- ad's story), a finished one is "new" until opened, and a queued one can be moved to the front.
ALTER TABLE desk_tasks ADD COLUMN archived_at TIMESTAMPTZ;
ALTER TABLE desk_tasks ADD COLUMN seen_at TIMESTAMPTZ;
ALTER TABLE desk_tasks ADD COLUMN queue_rank INTEGER NOT NULL DEFAULT 0;
UPDATE desk_tasks SET seen_at = now() WHERE status IN ('done', 'failed', 'cancelled');
UPDATE desk_tasks SET archived_at = now() WHERE status = 'cancelled';
CREATE INDEX desk_tasks_queue_idx ON desk_tasks (queue_rank, id) WHERE status = 'queued';
