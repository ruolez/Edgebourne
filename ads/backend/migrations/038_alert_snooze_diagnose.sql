-- W1a: snooze alerts ("Got it"), the figure each alert judged, and Diagnose with Claude runs.
-- Grants come from db.APP_ROLE_SQL at boot (default privileges).

-- The figure the rule judged (percent used, cost per lead in cents, dry days…), so a snooze can tell
-- "clearly worse". NULL for old rows and for rules without one.
ALTER TABLE alerts ADD COLUMN measure NUMERIC;
-- Raised while snoozed: stored and shown in the Inbox, never sent.
ALTER TABLE alerts ADD COLUMN quiet BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE alert_snoozes (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    rule TEXT NOT NULL,
    entity_id TEXT NOT NULL,                 -- ad / ad set / campaign id, or 'account'
    campaign_id TEXT,                        -- for teammate scoping, copied from the alert
    mode TEXT NOT NULL CHECK (mode IN ('days', 'worse')),
    until TIMESTAMPTZ,                       -- mode 'days' only
    baseline NUMERIC,                        -- alerts.measure when snoozed
    baseline_level TEXT NOT NULL CHECK (baseline_level IN ('bad', 'warn', 'info')),
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    end_reason TEXT CHECK (end_reason IN ('expired', 'worse', 'cleared', 'by_hand')),
    ended_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CHECK ((mode = 'days') = (until IS NOT NULL)),
    CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);
-- One live snooze per problem per account.
CREATE UNIQUE INDEX alert_snoozes_live ON alert_snoozes (account_id, rule, entity_id) WHERE ended_at IS NULL;
ALTER TABLE alert_snoozes ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON alert_snoozes
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- Diagnose runs: a Desk run kind of their own, read-only on the Mac ('diagnose' is listed explicitly
-- among the bridge's read-only kinds).
ALTER TABLE desk_tasks DROP CONSTRAINT desk_tasks_kind_check;
ALTER TABLE desk_tasks ADD CONSTRAINT desk_tasks_kind_check
    CHECK (kind IN ('question', 'review', 'research', 'creative', 'polish', 'render', 'advice', 'diagnose'));
CREATE INDEX desk_tasks_alert_key_idx ON desk_tasks ((options->>'alert_key')) WHERE kind = 'diagnose';
