-- AM-B: Ads Manager drafts read through the Mac link (AM-A). Kept per console account, bound to the link pass that read them.
-- Nothing here is ever written back to Meta: a draft is finished by the console's own builders (created paused) and
-- discarded by Eugene in Ads Manager.
CREATE TABLE am_drafts (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    draft_id TEXT NOT NULL,                    -- Meta's ad_object_id (digits)
    object_type TEXT NOT NULL CHECK (object_type IN ('campaign', 'adset', 'ad')),
    parent_id TEXT,                            -- parent_ad_object_id (a draft or a live object)
    action TEXT NOT NULL,                      -- 'add' or Meta's word for an edit (<= 20 chars, lower case)
    meta_status TEXT,                          -- EDITING …
    validation_status TEXT,                    -- VALIDATED …
    source TEXT,                               -- mcp_campaign_creation, ads_manager …
    time_updated TIMESTAMPTZ,
    fields JSONB NOT NULL,                     -- {field: {"old": …, "new": …}} whitelisted (am_drafts.FIELDS)
    other_fields TEXT[] NOT NULL DEFAULT '{}', -- names of fields the console doesn't read (shown as "Also set: …")
    problems JSONB NOT NULL DEFAULT '[]',      -- active_errors + publish_error, [{message, field}] cut to 300 chars
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL,         -- the last link read that returned it
    gone_at TIMESTAMPTZ,                       -- a complete read no longer returned it (published or discarded in Ads Manager)
    run_id INTEGER REFERENCES am_link_runs(id) ON DELETE SET NULL,
    finished_build_id INTEGER REFERENCES campaign_builds(id) ON DELETE SET NULL,
    finished_entity TEXT,                      -- 'campaign:<id>' | 'adset:<id>' | 'ad:<id>' made from it
    finished_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    finished_at TIMESTAMPTZ,
    applied JSONB NOT NULL DEFAULT '{}',       -- edit drafts: {field: meta_changes id} applied from here
    PRIMARY KEY (account_id, draft_id)
);
CREATE INDEX am_drafts_open ON am_drafts (account_id, gone_at, time_updated DESC);
ALTER TABLE am_drafts ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON am_drafts
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

ALTER TABLE campaign_builds ADD COLUMN draft_id TEXT;   -- the Ads Manager draft this build finished

-- The drafts read keeps its time (and how many it held) with the other kinds, so what is due and the source line work alike.
ALTER TABLE am_snapshots DROP CONSTRAINT am_snapshots_kind_check;
ALTER TABLE am_snapshots ADD CONSTRAINT am_snapshots_kind_check CHECK (kind IN ('benchmarks', 'peers', 'auction_ranking', 'anomalies',
    'trend', 'dataset_quality', 'advertiser_context', 'ad_errors', 'drafts'));
