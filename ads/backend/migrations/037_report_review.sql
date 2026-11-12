-- W2: a client report per account and period: its note, whether it waits for review, its sending state and
-- the frozen copy that went out. Grants come from db.APP_ROLE_SQL at boot (default privileges).
CREATE TABLE client_reports (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    kind TEXT NOT NULL CHECK (kind IN ('week', 'month')),
    start_day DATE NOT NULL,
    end_day DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting', 'scheduled', 'sending', 'sent', 'skipped')),
    note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
    note_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    note_at TIMESTAMPTZ,
    send_at TIMESTAMPTZ,                  -- when status = 'scheduled'
    decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- who pressed Send / Hold / Don't send
    decided_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,               -- the worker took it ('sending'); a stale claim goes back to 'scheduled'
    round INTEGER NOT NULL DEFAULT 1,     -- 2+ = "Send again with today's figures"
    sent_to TEXT[] NOT NULL DEFAULT '{}', -- this round, saved after each address
    sent_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    snapshot JSONB,                       -- the client view, stored with the first email of its round
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, kind, start_day)
);
CREATE INDEX client_reports_due_idx ON client_reports (status, send_at);
ALTER TABLE client_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON client_reports
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- What already went out under the settings-based state stays sent (no second email after the Update). When it
-- went and to whom wasn't kept, so sent_at stays NULL and there is no copy (the bar says so).
INSERT INTO client_reports (account_id, kind, start_day, end_day, status)
SELECT acct, k, s,
       CASE k WHEN 'week' THEN s + 6 ELSE (date_trunc('month', s) + interval '1 month - 1 day')::date END,
       'sent'
FROM (SELECT CASE WHEN key = 'report_last_sent' THEN 1 ELSE split_part(key, '@', 2)::int END AS acct,
             split_part(value, ':', 1) AS k, split_part(value, ':', 2)::date AS s
      FROM settings
      WHERE (key = 'report_last_sent' OR key ~ '^report_last_sent@\d+$')
        AND value ~ '^(week|month):\d{4}-\d{2}-\d{2}$') x
WHERE EXISTS (SELECT 1 FROM accounts a WHERE a.id = x.acct)
ON CONFLICT (account_id, kind, start_day) DO NOTHING;

-- A send that was half done at the Update carries on with the addresses it already reached.
INSERT INTO client_reports (account_id, kind, start_day, end_day, status, send_at, sent_to)
SELECT acct, split_part(v->>'key', ':', 1), split_part(v->>'key', ':', 2)::date,
       CASE split_part(v->>'key', ':', 1) WHEN 'week' THEN split_part(v->>'key', ':', 2)::date + 6
            ELSE (date_trunc('month', split_part(v->>'key', ':', 2)::date) + interval '1 month - 1 day')::date END,
       'scheduled', now(), ARRAY(SELECT jsonb_array_elements_text(COALESCE(v->'to', '[]'::jsonb)))
FROM (SELECT CASE WHEN key = 'report_sent_to' THEN 1 ELSE split_part(key, '@', 2)::int END AS acct, value::jsonb AS v
      FROM settings
      WHERE (key = 'report_sent_to' OR key ~ '^report_sent_to@\d+$') AND value ~ '^\{.*\}$') x
WHERE v->>'key' ~ '^(week|month):\d{4}-\d{2}-\d{2}$'
  AND EXISTS (SELECT 1 FROM accounts a WHERE a.id = x.acct)
ON CONFLICT (account_id, kind, start_day) DO NOTHING;

-- Accounts that email reports today keep doing it without review; every other account waits for review.
INSERT INTO settings (key, value)
SELECT replace(key, 'report_email', 'report_review'), 'auto' FROM settings
WHERE (key = 'report_email' OR key ~ '^report_email@\d+$') AND value IN ('weekly', 'monthly')
ON CONFLICT (key) DO NOTHING;
