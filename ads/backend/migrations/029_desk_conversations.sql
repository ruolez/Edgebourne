-- The Claude page as conversations: a reply is a new run in the same thread (thread_id = the first
-- run; NULL on the first run itself). Each run keeps its progress lines and the competitor ads it saved.
ALTER TABLE desk_tasks ADD COLUMN thread_id INTEGER REFERENCES desk_tasks(id) ON DELETE CASCADE;
ALTER TABLE desk_tasks ADD COLUMN steps JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE desk_tasks ADD COLUMN swipe_ids INTEGER[] NOT NULL DEFAULT '{}';
CREATE INDEX desk_tasks_thread_idx ON desk_tasks (thread_id) WHERE thread_id IS NOT NULL;

-- A run started from another run's suggestion continues that conversation.
WITH RECURSIVE up(id, root) AS (
    SELECT id, id FROM desk_tasks WHERE options->>'from_task' IS NULL
    UNION ALL
    SELECT c.id, up.root FROM desk_tasks c JOIN up ON (c.options->>'from_task')::int = up.id
)
UPDATE desk_tasks t SET thread_id = up.root FROM up WHERE t.id = up.id AND up.root <> t.id;

-- 'revised' = sent back to Claude with a note, instead of accepted or declined.
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_status_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_status_check
    CHECK (status IN ('pending', 'applying', 'approved', 'declined', 'applied', 'failed', 'expired', 'revised'));
