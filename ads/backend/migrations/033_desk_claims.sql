-- Audit 3 (2026-11-11): Claude runs on the Mac.
-- A3-7: claim_hash = sha256 of the pass the Mac gets when it claims a request (desk 2.0 and later).
-- Every call of that run carries it, and it works only for that request, in that request's account.
-- A3-127: mentions = the ads a finished answer names, found once when it finishes, not on every poll.
ALTER TABLE desk_tasks ADD COLUMN claim_hash TEXT;
CREATE UNIQUE INDEX desk_tasks_claim_hash ON desk_tasks (claim_hash) WHERE claim_hash IS NOT NULL;
ALTER TABLE desk_tasks ADD COLUMN mentions TEXT[];
