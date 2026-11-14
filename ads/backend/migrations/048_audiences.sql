-- AM-D: the account's audiences (custom, lookalike, saved), as last read from Meta, and where ad sets use them.
-- Nothing here holds contact data: customer lists Meta already has are listed by name and size only, never made or uploaded here.
CREATE TABLE audiences (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    id TEXT NOT NULL,                         -- Meta's id (digits)
    kind TEXT NOT NULL CHECK (kind IN ('custom', 'lookalike', 'saved')),
    subtype TEXT,                             -- WEBSITE, ENGAGEMENT, LOOKALIKE, CUSTOM (customer list: listed, never made here) …
    name TEXT NOT NULL,
    description TEXT,                         -- plain words the console wrote when it made it, else Meta's (<= 300)
    size_lower BIGINT, size_upper BIGINT,     -- NULL = Meta reports none yet
    ready TEXT,                               -- 'ready' | 'filling' | 'too_small' | 'problem'
    status_words TEXT,                        -- Meta's delivery / operation status in plain words (<= 200)
    retention_days INTEGER,
    source_kind TEXT,                         -- website | page | instagram | lead_form | video | lookalike | customer_list | saved | other
    who TEXT,                                 -- the rule's event (all_visitors, lead_generation_submitted …), audience_rules.WHO
    detail TEXT,                              -- a website rule's address fragment (<= 200)
    source_id TEXT,                           -- the pixel / Page / Instagram account / form / video; lookalike: the audience it is like
    lookalike JSONB,                          -- {country, ratio}
    targeting JSONB,                          -- saved audiences: whitelisted targeting (edit_rules.TARGETING_KEYS)
    made_here BOOLEAN NOT NULL DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    client_key TEXT,                          -- the New audience click that made it (a second send gives the same audience)
    time_created TIMESTAMPTZ,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    gone_at TIMESTAMPTZ,                      -- not listed by a complete read any more
    PRIMARY KEY (account_id, id),
    UNIQUE (account_id, client_key)
);
CREATE INDEX audiences_listed ON audiences (account_id, gone_at, kind);
ALTER TABLE audiences ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON audiences
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- Where used: filled by the sync from each ad set's targeting (full reads only) and by the console's own edits.
ALTER TABLE adsets ADD COLUMN audience_ids TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE adsets ADD COLUMN excluded_audience_ids TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX adsets_audiences ON adsets USING GIN (audience_ids);
CREATE INDEX adsets_excluded_audiences ON adsets USING GIN (excluded_audience_ids);
-- Ad sets read before this update get their audiences on the next full sync.
