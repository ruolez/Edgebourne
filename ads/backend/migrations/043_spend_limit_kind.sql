-- FU-B: Claude may suggest a change to the ad account's spending limit (proposal kind spend_limit). Applied only
-- after an Accept, by the backend; no new table (the pause is a per-account setting, the alert uses alerts).
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_kind_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_kind_check
    CHECK (kind IN ('budget', 'status', 'spend_limit', 'creative', 'targeting', 'experiment', 'tags', 'other'));
