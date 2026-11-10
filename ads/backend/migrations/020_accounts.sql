-- Roadmap 7.1: several ad accounts in one console. Everything that exists is account 1.
-- Isolation is enforced by the database: the app runs as ebads_app (not a superuser), and every
-- account-owned table only shows and accepts rows of the account named in app.account_id.
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ
);
INSERT INTO accounts (id, name) VALUES (1, 'Edge Bourne');
SELECT setval('accounts_id_seq', 1);

ALTER TABLE users ADD COLUMN account_id INTEGER REFERENCES accounts(id);
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'member', 'client'));
UPDATE users SET account_id = 1 WHERE role <> 'admin';

CREATE OR REPLACE FUNCTION app_account() RETURNS integer LANGUAGE sql STABLE AS
$$ SELECT COALESCE(NULLIF(current_setting('app.account_id', true), '')::int, 1) $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ebads_app') THEN
        CREATE ROLE ebads_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO ebads_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ebads_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO ebads_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ebads_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO ebads_app;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['campaigns', 'adsets', 'ads', 'ad_daily', 'leads', 'lead_notes', 'webhook_events', 'crm_events',
                             'meta_cache', 'desk_tasks', 'desk_reports', 'desk_proposals', 'desk_schedules', 'meta_changes',
                             'alerts', 'campaign_builds', 'reply_templates', 'lead_replies', 'experiments', 'swipes',
                             'watched_pages', 'ad_tags', 'activity'] LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN account_id INTEGER NOT NULL DEFAULT 1 REFERENCES accounts(id)', t);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN account_id SET DEFAULT app_account()', t);
        EXECUTE format('CREATE INDEX %I ON %I (account_id)', t || '_account_idx', t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('CREATE POLICY account_isolation ON %I USING (account_id = app_account()) WITH CHECK (account_id = app_account())', t);
    END LOOP;
END $$;

-- Keys that were unique for one account are unique per account now.
ALTER TABLE meta_cache DROP CONSTRAINT meta_cache_pkey;
ALTER TABLE meta_cache ADD PRIMARY KEY (account_id, key);
ALTER TABLE alerts DROP CONSTRAINT alerts_dedupe_key_key;
ALTER TABLE alerts ADD CONSTRAINT alerts_account_dedupe_key UNIQUE (account_id, dedupe_key);
ALTER TABLE swipes DROP CONSTRAINT swipes_library_id_key;
ALTER TABLE swipes ADD CONSTRAINT swipes_account_library_id UNIQUE (account_id, library_id);
