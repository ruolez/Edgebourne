-- Audit 2 (2026-11-10).
-- A2: a proposal is claimed ('applying') before anything is sent to Meta, so a double click or a
-- second tab can't apply it twice.
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_status_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_status_check
    CHECK (status IN ('pending', 'applying', 'approved', 'declined', 'applied', 'failed', 'expired'));

-- A16: campaign assignments belong to the campaign's account, under the same row-level security.
ALTER TABLE campaign_members ADD COLUMN account_id INTEGER REFERENCES accounts(id);
UPDATE campaign_members m SET account_id = c.account_id FROM campaigns c WHERE c.id = m.campaign_id;
UPDATE campaign_members SET account_id = 1 WHERE account_id IS NULL;
ALTER TABLE campaign_members ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE campaign_members ALTER COLUMN account_id SET DEFAULT app_account();
CREATE INDEX campaign_members_account_idx ON campaign_members (account_id);
ALTER TABLE campaign_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON campaign_members
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- A2: one build per click (the browser sends a key with Create).
ALTER TABLE campaign_builds ADD COLUMN client_key TEXT;
CREATE UNIQUE INDEX campaign_builds_client_key ON campaign_builds (account_id, client_key) WHERE client_key IS NOT NULL;

-- A12 + L7: an admin with an account_id is that account's admin only (Eugene's own admin row has none
-- and sees every account). session_version ends every other session when a password changes.
ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;
