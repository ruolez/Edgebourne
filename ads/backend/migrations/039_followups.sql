-- L1 Phases A + B: follow-up queue and booked calls. A lead history that is never pruned, call outcomes,
-- the next step and booked calls. No booking tool yet (Eugene, 2026-11-11), so no `bookings` table: Phase C
-- adds it with its own migration. Grants come from db.APP_ROLE_SQL at boot (default privileges).

-- 1. Lead history. jobs.PRUNE never lists it (a unit test guards that).
CREATE TABLE lead_events (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor TEXT NOT NULL DEFAULT 'user' CHECK (actor IN ('user', 'system', 'meta', 'claude', 'booking')),
    kind TEXT NOT NULL CHECK (kind IN (
        'received', 'call', 'stage', 'owner', 'note', 'email', 'email_auto', 'alert_failed',
        'next_set', 'next_done', 'next_cleared',
        'booked', 'call_moved', 'call_canceled', 'call_held', 'no_show', 'booking_removed',
        -- L2's kinds, listed now so L2 needs no constraint change (00-PLAN C11)
        'lost_reason', 'max_stage', 'repeat', 'returning', 'linked', 'unlinked', 'not_junk')),
    outcome TEXT CHECK (outcome IN ('reached', 'no_answer', 'voicemail', 'wrong_number', 'booked')),
    ref_id BIGINT,                        -- lead_notes.id or lead_replies.id
    details JSONB NOT NULL DEFAULT '{}',
    undone_at TIMESTAMPTZ,                -- Undo marks, never deletes
    undone_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CHECK ((kind = 'call') = (outcome IS NOT NULL))
);
CREATE INDEX lead_events_lead ON lead_events (lead_id, at);
CREATE INDEX lead_events_calls ON lead_events (account_id, at) WHERE kind = 'call' AND undone_at IS NULL;
CREATE INDEX lead_events_account_idx ON lead_events (account_id);
ALTER TABLE lead_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON lead_events
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- 2. The lead's follow-up state, kept in step with lead_events by followup.py (one place).
ALTER TABLE leads
    ADD COLUMN call_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN unanswered_streak INTEGER NOT NULL DEFAULT 0,  -- calls since the last time they were reached
    ADD COLUMN ever_reached BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN last_call_at TIMESTAMPTZ,
    ADD COLUMN last_outcome TEXT,
    ADD COLUMN next_step_kind TEXT CHECK (next_step_kind IN ('call_back', 'proposal', 'follow_up', 'other')),
    ADD COLUMN next_step_text TEXT,                           -- only for 'other', at most 120 characters
    ADD COLUMN next_step_at TIMESTAMPTZ,
    ADD COLUMN next_step_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN booked_at TIMESTAMPTZ,                         -- first time a call was booked; kept after cancel / no-show
    ADD COLUMN meeting_at TIMESTAMPTZ,                        -- when the booked call is (NULL = "not sure yet")
    ADD COLUMN meeting_status TEXT CHECK (meeting_status IN ('scheduled', 'held', 'no_show', 'canceled')),
    ADD COLUMN booking_source TEXT CHECK (booking_source IN ('call', 'manual', 'calcom', 'calendly', 'savvycal', 'other')),
    ADD CONSTRAINT leads_next_step_whole CHECK ((next_step_kind IS NULL) = (next_step_at IS NULL));
CREATE INDEX leads_next_step_idx ON leads (next_step_at) WHERE next_step_at IS NOT NULL;
CREATE INDEX leads_meeting_idx ON leads (meeting_at) WHERE meeting_status = 'scheduled';
CREATE INDEX leads_booked_idx ON leads (booked_at) WHERE booked_at IS NOT NULL;

-- 3. Backfill from what `activity` still holds (180 days). Migrations run as the owner (no row-level
-- security), so account_id is copied explicitly. A stage move undone before today keeps its mark.
INSERT INTO lead_events (account_id, lead_id, at, user_id, actor, kind, details, undone_at, undone_by)
SELECT a.account_id, l.id, a.at, a.user_id,
       CASE WHEN a.actor IN ('user', 'system', 'meta', 'claude') THEN a.actor ELSE 'system' END,
       CASE a.action WHEN 'lead.received' THEN 'received' WHEN 'lead.status' THEN 'stage'
                     WHEN 'lead.owner' THEN 'owner' WHEN 'lead.reply' THEN 'email'
                     WHEN 'lead.reply_auto' THEN 'email_auto' WHEN 'lead.email_failed' THEN 'alert_failed' END,
       (a.details - 'undone') || '{"backfilled": true}'::jsonb,
       CASE WHEN a.details ? 'undone' THEN COALESCE(u.at, a.at) END,
       CASE WHEN a.details ? 'undone' THEN u.user_id END
FROM activity a
JOIN leads l ON l.id::text = a.subject AND l.account_id = a.account_id
LEFT JOIN LATERAL (SELECT x.at, x.user_id FROM activity x
                   WHERE x.action = 'lead.status_undone' AND x.subject = a.subject AND x.details->>'event_id' = a.id::text
                   ORDER BY x.at LIMIT 1) u ON a.action = 'lead.status'
WHERE a.action IN ('lead.received', 'lead.status', 'lead.owner', 'lead.reply', 'lead.reply_auto', 'lead.email_failed');

INSERT INTO lead_events (account_id, lead_id, at, actor, kind, details)
SELECT l.account_id, l.id, l.created_time, 'meta', 'received',
       jsonb_build_object('ad', l.ad_name, 'test', l.is_test, 'organic', l.is_organic, 'backfilled', true)
FROM leads l WHERE NOT EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id = l.id AND e.kind = 'received');

INSERT INTO lead_events (account_id, lead_id, at, user_id, actor, kind, ref_id, details)
SELECT n.account_id, n.lead_id, n.created_at, n.user_id, 'user', 'note', n.id, '{"backfilled": true}'::jsonb
FROM lead_notes n;
