-- One ad, several versions: Meta can't edit a creative, but a running ad can be pointed at a new
-- one and keeps its ID and results. Each switch is kept so results can be read per version.
CREATE TABLE ad_versions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    ad_id TEXT NOT NULL,
    number INTEGER NOT NULL,
    creative_id TEXT NOT NULL,
    label TEXT,
    title TEXT,
    body TEXT,
    restored_from INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_on DATE,               -- in the ad account's time zone; NULL for the original
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    proposal_id INTEGER REFERENCES desk_proposals(id) ON DELETE SET NULL,
    UNIQUE (account_id, ad_id, number)
);
CREATE INDEX ad_versions_ad_idx ON ad_versions (ad_id, number);
ALTER TABLE ad_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON ad_versions
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
