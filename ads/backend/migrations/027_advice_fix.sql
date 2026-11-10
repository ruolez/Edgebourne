-- "Fix with Claude" on Meta's advice: a Desk run of its own kind.
ALTER TABLE desk_tasks DROP CONSTRAINT desk_tasks_kind_check;
ALTER TABLE desk_tasks ADD CONSTRAINT desk_tasks_kind_check
    CHECK (kind IN ('question', 'review', 'research', 'creative', 'polish', 'render', 'advice'));
