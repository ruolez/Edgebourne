-- Phone alerts (Telegram) and the queue every alert goes through.
ALTER TABLE users ADD COLUMN telegram_chat_id BIGINT;
ALTER TABLE users ADD COLUMN telegram_name TEXT;
ALTER TABLE users ADD COLUMN notify_telegram BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN telegram_link_code TEXT;
ALTER TABLE users ADD COLUMN telegram_link_expires TIMESTAMPTZ;

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,                     -- telegram | email
    kind TEXT NOT NULL,                        -- lead | reminder | digest | test | …
    ref TEXT,                                  -- what it is about, e.g. a lead id
    dedupe_key TEXT UNIQUE,                    -- the same alert is never queued twice
    title TEXT NOT NULL,
    lines JSONB NOT NULL DEFAULT '[]',
    url TEXT,
    button TEXT,
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX notifications_pending ON notifications (next_attempt_at) WHERE status = 'pending';
