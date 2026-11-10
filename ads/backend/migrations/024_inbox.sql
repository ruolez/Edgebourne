-- Phase 8.2: alerts raised by a status change (approved, learning limited, changed outside) are events,
-- not conditions: the hourly check must not close them. Inbox read state per person.
ALTER TABLE alerts ADD COLUMN kind TEXT NOT NULL DEFAULT 'condition' CHECK (kind IN ('condition', 'event'));

CREATE TABLE inbox_reads (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, user_id, item_key)
);
ALTER TABLE inbox_reads ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON inbox_reads
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
