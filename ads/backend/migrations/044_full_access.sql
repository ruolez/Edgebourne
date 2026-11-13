-- FU-D: full access for the console owner's own conversations (Eugene, 2026-11-12: "Only me, with a re-check").
-- The unlock belongs to one sign-in (user_sessions row), never to a browser flag; the Mac learns it only from a claim.

-- Who may ever unlock: the console's first owner. No screen changes it.
ALTER TABLE users ADD COLUMN full_access_allowed BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE users SET full_access_allowed = TRUE
 WHERE id = (SELECT MIN(id) FROM users WHERE role = 'admin' AND account_id IS NULL AND is_active);

-- The unlock, on the sign-in it was made in (no account_id: a sign-in spans accounts, like users).
ALTER TABLE user_sessions ADD COLUMN full_until TIMESTAMPTZ;           -- NULL = locked
ALTER TABLE user_sessions ADD COLUMN full_since TIMESTAMPTZ;
ALTER TABLE user_sessions ADD COLUMN full_fails INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_sessions ADD COLUMN full_fail_at TIMESTAMPTZ;
ALTER TABLE user_sessions ADD COLUMN user_agent TEXT;                  -- shown in the "turned on" notice

-- Per request: the sign-in that typed it (only when that sign-in was unlocked then), and what the Mac got at claim.
ALTER TABLE desk_tasks ADD COLUMN full_session TEXT;                   -- user_sessions.key_hash, never sent anywhere
ALTER TABLE desk_tasks ADD COLUMN access TEXT NOT NULL DEFAULT 'sandbox' CHECK (access IN ('sandbox', 'full'));
ALTER TABLE desk_tasks ADD COLUMN access_note TEXT;                    -- why a typed request ran sandboxed (locked, old helper)

-- Previews Claude made in a conversation. Kept in the database (the server stores no media files), pruned after 30 days.
CREATE TABLE desk_attachments (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    task_id INTEGER NOT NULL REFERENCES desk_tasks(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    mime TEXT NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp', 'video/mp4')),
    name TEXT NOT NULL,
    caption TEXT,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER, height INTEGER, duration_ms INTEGER,
    body BYTEA,                                   -- NULL once pruned
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pruned_at TIMESTAMPTZ,
    meta_ref JSONB,                               -- {"kind": "image", "hash": …} | {"kind": "video", "video_id": …} after Upload as draft
    drafted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    drafted_at TIMESTAMPTZ
);
CREATE INDEX desk_attachments_task ON desk_attachments (account_id, task_id);
ALTER TABLE desk_attachments ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON desk_attachments
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());
