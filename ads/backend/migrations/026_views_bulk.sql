-- Phase 8.4: saved views (a named filter of a page, kept as its URL query), and bulk changes grouped.
CREATE TABLE saved_views (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    page TEXT NOT NULL,
    name TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    shared BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX saved_views_page_idx ON saved_views (account_id, page);
ALTER TABLE saved_views ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON saved_views
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

ALTER TABLE meta_changes ADD COLUMN bulk_id TEXT;
