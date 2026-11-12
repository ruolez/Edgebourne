-- Audit 3 (2026-11-11), A3-50: a sign-in is a row here, and the cookie carries its key (stored hashed).
-- Signing out deletes the row, so a copy of the cookie stops working too. Sessions from before this
-- migration have no key: those people sign in once more.
CREATE TABLE user_sessions (
    key_hash   TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX user_sessions_user ON user_sessions (user_id);
CREATE INDEX user_sessions_seen ON user_sessions (seen_at);
