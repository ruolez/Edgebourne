-- L2 Lead quality: the highest stage a lead reached, why it was lost, repeats and junk flags.
-- No new table: leads already has account_id and the account_isolation policy (020), so every new column is
-- under row-level security. Composite foreign keys keep a link inside one account even if Python got it wrong.
-- Keys, flags and past repeats are filled in by the worker (lead_quality_store.backfill_once): placeholder
-- detection lives in Python (contact.py).

ALTER TABLE leads
    ADD COLUMN max_stage TEXT NOT NULL DEFAULT 'new'
        CHECK (max_stage IN ('new', 'contacted', 'qualified', 'won')),
    ADD COLUMN max_stage_at TIMESTAMPTZ,
    ADD COLUMN lost_reason TEXT
        CHECK (lost_reason IN ('no_response', 'not_fit', 'spam', 'duplicate', 'too_small',
                               'price', 'went_elsewhere', 'other')),
    ADD COLUMN lost_note TEXT,
    ADD COLUMN email_key TEXT,              -- normalised email, NULL when missing or a placeholder
    ADD COLUMN phone_key TEXT,              -- last 10 digits, NULL when missing or a placeholder
    ADD COLUMN earlier_lead_id INTEGER,     -- the first lead of the same person (repeat or returning)
    ADD COLUMN repeat_of INTEGER,           -- set only for a repeat: this row doesn't count
    ADD COLUMN repeat_source TEXT CHECK (repeat_source IN ('auto', 'hand')),
    ADD COLUMN repeat_checked BOOLEAN NOT NULL DEFAULT FALSE,  -- "Not the same person": never linked again by itself
    ADD COLUMN quality_checked BOOLEAN NOT NULL DEFAULT FALSE, -- keys and flags worked out (new leads at insert, old ones by the worker)
    ADD COLUMN junk_flags TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN junk_dismissed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE leads ADD CONSTRAINT leads_account_id_id UNIQUE (account_id, id);
ALTER TABLE leads ADD CONSTRAINT leads_repeat_same_account
    FOREIGN KEY (account_id, repeat_of) REFERENCES leads (account_id, id) ON DELETE SET NULL (repeat_of);
ALTER TABLE leads ADD CONSTRAINT leads_earlier_same_account
    FOREIGN KEY (account_id, earlier_lead_id) REFERENCES leads (account_id, id) ON DELETE SET NULL (earlier_lead_id);
ALTER TABLE leads ADD CONSTRAINT leads_repeat_not_self CHECK (repeat_of IS NULL OR repeat_of <> id);
ALTER TABLE leads ADD CONSTRAINT leads_earlier_not_self CHECK (earlier_lead_id IS NULL OR earlier_lead_id <> id);
ALTER TABLE leads ADD CONSTRAINT leads_lost_reason_only_lost CHECK (lost_reason IS NULL OR status = 'lost');

CREATE INDEX leads_email_key_idx ON leads (account_id, email_key, created_time) WHERE email_key IS NOT NULL;
CREATE INDEX leads_phone_key_idx ON leads (account_id, phone_key, created_time) WHERE phone_key IS NOT NULL;
CREATE INDEX leads_repeat_of_idx ON leads (repeat_of) WHERE repeat_of IS NOT NULL;
CREATE INDEX leads_quality_todo_idx ON leads (account_id, created_time) WHERE NOT quality_checked;

-- The highest stage from what is known: the current stage, every recorded stage move (activity keeps 180 days,
-- lead_events never forgets), every stage queued for Meta (crm_events, kept forever), and a first contact from
-- before L1. Since L1 first_contacted_at is the first *try*: a lead whose only calls went unanswered isn't
-- counted as contacted (00-PLAN C5). Migrations run as the owner, so this crosses accounts; activity.subject,
-- lead_events.lead_id and crm_events.lead_id all name the global serial leads.id.
WITH ranks(stage, r) AS (VALUES ('new', 0), ('contacted', 1), ('qualified', 2), ('won', 3)),
seen AS (
    SELECT l.id, l.status AS stage FROM leads l
    UNION ALL SELECT l.id, 'contacted' FROM leads l
              WHERE l.first_contacted_at IS NOT NULL
              AND (NOT EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id = l.id AND e.kind = 'call' AND e.undone_at IS NULL)
                   OR EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id = l.id AND e.kind = 'call' AND e.undone_at IS NULL
                              AND e.outcome IN ('reached', 'booked')))
    UNION ALL SELECT a.subject::int, a.details->>'to' FROM activity a
              WHERE a.action = 'lead.status' AND a.subject ~ '^\d{1,9}$' AND NOT (a.details ? 'undone')
    UNION ALL SELECT e.lead_id, e.details->>'to' FROM lead_events e WHERE e.kind = 'stage' AND e.undone_at IS NULL
    UNION ALL SELECT c.lead_id, c.stage FROM crm_events c
),
best AS (
    SELECT s.id, (ARRAY['new','contacted','qualified','won'])[MAX(r.r) + 1] AS stage
    FROM seen s JOIN ranks r ON r.stage = s.stage GROUP BY s.id
)
UPDATE leads l SET max_stage = b.stage, max_stage_at = l.status_changed_at
FROM best b WHERE b.id = l.id AND b.stage <> 'new';

-- Leads already Lost keep the reason their last move to Lost carried (L1's "Lost: couldn't reach" sent no_response).
UPDATE leads l SET lost_reason = e.details->>'reason', lost_note = NULLIF(left(e.details->>'note', 500), '')
FROM (SELECT DISTINCT ON (lead_id) lead_id, details FROM lead_events
      WHERE kind = 'stage' AND undone_at IS NULL AND details->>'to' = 'lost'
      ORDER BY lead_id, at DESC, id DESC) e
WHERE e.lead_id = l.id AND l.status = 'lost'
AND e.details->>'reason' IN ('no_response', 'not_fit', 'spam', 'duplicate', 'too_small', 'price', 'went_elsewhere', 'other');
