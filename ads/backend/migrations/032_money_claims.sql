-- Audit 3 (2026-11-11): money and proposal paths.
-- A3-40, A3-68, A3-79: a proposal whose write Meta didn't answer, or whose apply was cut off (a restart),
-- is kept as 'unknown' ("check Ads Manager") instead of going back to waiting, so it is never sent twice.
-- applying_at dates the claim: writes since then decide what it becomes, and the worker settles claims
-- older than ten minutes.
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_status_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_status_check
    CHECK (status IN ('pending', 'applying', 'approved', 'declined', 'applied', 'failed', 'expired', 'revised', 'unknown'));
ALTER TABLE desk_proposals ADD COLUMN applying_at TIMESTAMPTZ;
