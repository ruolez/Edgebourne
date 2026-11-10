-- Roadmap 4.1: forms built in the console are Meta writes too.
ALTER TABLE meta_changes DROP CONSTRAINT meta_changes_level_check;
ALTER TABLE meta_changes ADD CONSTRAINT meta_changes_level_check CHECK (level IN ('campaign', 'adset', 'ad', 'study', 'form'));
