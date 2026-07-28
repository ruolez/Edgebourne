-- Billing module: customers, projects, estimates, invoices, payments,
-- refunds, credit ledger, recurring subscriptions, Stripe plumbing.
--
-- Conventions that differ from 001_init.sql, deliberately:
--
--   * FOREIGN KEYS. The content tables are independent islands with nothing to
--     enforce. Billing is a graph: an orphaned invoice_line is silent corruption
--     of a financial record. RESTRICT on customers (archive, never delete),
--     CASCADE on lines (they have no life of their own), SET NULL on
--     provenance links (a project can be tidied up; the invoice survives).
--
--   * MONEY IS INTEGER MINOR UNITS. Every money column ends in _cents (BIGINT),
--     quantities are qty_milli (x1000), tax rates are tax_rate_milli (percent
--     x1000, so 8875 = 8.875%). No NUMERIC, no float, no Decimal reaches Python.
--     A raw un-filtered {{ x_cents }} in a template is therefore visually
--     obvious in review. See backend/money.py.
--
--   * Totals are STORED and recomputed by billing.recompute_totals() inside the
--     mutating transaction; paid/status are recomputed by
--     billing.refresh_invoice_state() with SUM over source rows, never
--     incremented and never taken from a webhook field.
--
--   * `overdue` is NEVER stored -- it is a function of the wall clock, so a
--     stored flag is wrong every night at midnight. Compute it in the query:
--       (status IN ('open','partial') AND due_date < current_date) AS is_overdue

-- ---------------------------------------------------------------------------
-- customers
-- ---------------------------------------------------------------------------

CREATE TABLE customers (
    id                      SERIAL PRIMARY KEY,
    display_name            TEXT NOT NULL,
    company                 TEXT NOT NULL DEFAULT '',
    contact_name            TEXT NOT NULL DEFAULT '',
    email                   TEXT NOT NULL DEFAULT '',
    cc_emails               TEXT NOT NULL DEFAULT '',
    phone                   TEXT NOT NULL DEFAULT '',
    website                 TEXT NOT NULL DEFAULT '',
    address_line1           TEXT NOT NULL DEFAULT '',
    address_line2           TEXT NOT NULL DEFAULT '',
    address_city            TEXT NOT NULL DEFAULT '',
    address_region          TEXT NOT NULL DEFAULT '',
    address_postcode        TEXT NOT NULL DEFAULT '',
    address_country         TEXT NOT NULL DEFAULT '',
    tax_number              TEXT NOT NULL DEFAULT '',
    -- A customer's currency is set once and inherited read-only by every
    -- document. The ledger sums amount_cents without regard to currency, which
    -- is only correct while a customer never mixes them; /admin/billing/audit
    -- flags any customer that does.
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    terms_days              INTEGER NOT NULL DEFAULT 14,
    default_tax_rate_milli  INTEGER NOT NULL DEFAULT 0,
    notes_md                TEXT NOT NULL DEFAULT '',
    notes_html              TEXT NOT NULL DEFAULT '',
    is_archived             BOOLEAN NOT NULL DEFAULT false,
    lead_id                 INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    -- Two ids: switching Stripe modes must never hand a test cus_ to the live
    -- API. Which one is used is derived from the secret key prefix.
    stripe_customer_id      TEXT,
    stripe_customer_id_test TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_active ON customers (is_archived, display_name);
CREATE INDEX idx_customers_lead   ON customers (lead_id) WHERE lead_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------

CREATE TABLE projects (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL,
    code            TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('lead','active','on_hold','completed','cancelled')),
    start_date      DATE,
    end_date        DATE,
    budget_cents    BIGINT NOT NULL DEFAULT 0 CHECK (budget_cents >= 0),
    description_md  TEXT NOT NULL DEFAULT '',
    description_html TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_customer ON projects (customer_id, status, id);
CREATE INDEX idx_projects_status   ON projects (status, id);

-- ---------------------------------------------------------------------------
-- document numbering
--
-- Not a SEQUENCE: nextval() does not roll back, so every failed save would burn
-- a number. Not a `settings` counter: TEXT value means a read-modify-write in
-- Python and no room for per-year scoping. This is one row-locked statement
-- that rolls back with the enclosing transaction:
--
--   INSERT INTO document_counters (scope, period, next_value) VALUES (%s, %s, 2)
--   ON CONFLICT (scope, period)
--   DO UPDATE SET next_value = document_counters.next_value + 1
--   RETURNING next_value - 1 AS n;
--
-- Numbers are allocated at ISSUE time, not creation: deleting an abandoned
-- draft must not leave a gap, and a draft has no legal existence.
-- ---------------------------------------------------------------------------

CREATE TABLE document_counters (
    scope      TEXT NOT NULL,          -- 'invoice' | 'estimate'
    period     TEXT NOT NULL,          -- '2026', or '' when numbering is not periodic
    next_value INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (scope, period)
);

-- ---------------------------------------------------------------------------
-- subscriptions (recurring retainers) -- declared before invoices so invoices
-- can reference them
-- ---------------------------------------------------------------------------

CREATE TABLE subscriptions (
    id                    SERIAL PRIMARY KEY,
    customer_id           INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    project_id            INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    name                  TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active','paused','ended')),
    currency              CHAR(3) NOT NULL DEFAULT 'USD',
    interval              TEXT NOT NULL DEFAULT 'monthly'
                          CHECK (interval IN ('weekly','monthly','quarterly','semiannual','annual')),
    interval_count        INTEGER NOT NULL DEFAULT 1 CHECK (interval_count >= 1),
    -- Periods are computed as start_date + n*interval with the day clamped to
    -- anchor_day, NEVER by mutating the previous date -- otherwise Jan 31 walks
    -- to Feb 28 and then Mar 28 and drifts forever. See scheduler.add_months().
    anchor_day            INTEGER NOT NULL DEFAULT 1 CHECK (anchor_day BETWEEN 1 AND 31),
    start_date            DATE NOT NULL,
    end_date              DATE,
    timezone              TEXT NOT NULL DEFAULT 'UTC',
    run_hour              INTEGER NOT NULL DEFAULT 7 CHECK (run_hour BETWEEN 0 AND 23),
    next_run_at           TIMESTAMPTZ,
    last_run_at           TIMESTAMPTZ,
    occurrences_generated INTEGER NOT NULL DEFAULT 0,
    max_occurrences       INTEGER,
    terms_days            INTEGER NOT NULL DEFAULT 14,
    discount_cents        BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    auto_send             BOOLEAN NOT NULL DEFAULT true,
    notes_md              TEXT NOT NULL DEFAULT '',
    terms_md              TEXT NOT NULL DEFAULT '',
    last_error            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subscriptions_due ON subscriptions (status, next_run_at);
CREATE INDEX idx_subscriptions_customer ON subscriptions (customer_id, id);

-- ---------------------------------------------------------------------------
-- estimates  (an ACCEPTED estimate is the work order -- there is no separate
-- orders table. /admin/estimates?status=accepted is the "Work orders" view.)
-- ---------------------------------------------------------------------------

CREATE TABLE estimates (
    id                SERIAL PRIMARY KEY,
    number            TEXT,                  -- NULL while draft
    customer_id       INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    project_id        INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title             TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','sent','accepted','declined','expired')),
    currency          CHAR(3) NOT NULL DEFAULT 'USD',
    issue_date        DATE NOT NULL DEFAULT current_date,
    valid_until       DATE,
    subtotal_cents    BIGINT NOT NULL DEFAULT 0,
    discount_cents    BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    tax_cents         BIGINT NOT NULL DEFAULT 0,
    total_cents       BIGINT NOT NULL DEFAULT 0,
    notes_md          TEXT NOT NULL DEFAULT '',
    terms_md          TEXT NOT NULL DEFAULT '',
    -- Only sha256(token) is stored, so a pg_dump in /var/backups contains no
    -- working links. previous_token_hash gives a 24h grace window on rotation.
    token_hash            BYTEA,
    previous_token_hash   BYTEA,
    token_expires_at      TIMESTAMPTZ,
    token_rotated_at      TIMESTAMPTZ,
    sent_at           TIMESTAMPTZ,
    first_viewed_at   TIMESTAMPTZ,
    last_viewed_at    TIMESTAMPTZ,
    accepted_at       TIMESTAMPTZ,
    accepted_name     TEXT,
    accepted_ip       TEXT,
    accepted_user_agent TEXT,
    declined_at       TIMESTAMPTZ,
    created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partial unique indexes: many NULL drafts, exactly one of each real number.
CREATE UNIQUE INDEX uq_estimates_number ON estimates (number) WHERE number IS NOT NULL;
CREATE UNIQUE INDEX uq_estimates_token  ON estimates (token_hash) WHERE token_hash IS NOT NULL;
CREATE INDEX idx_estimates_customer ON estimates (customer_id, id DESC);
CREATE INDEX idx_estimates_status   ON estimates (status, issue_date DESC, id DESC);

-- ---------------------------------------------------------------------------
-- invoices
-- ---------------------------------------------------------------------------

CREATE TABLE invoices (
    id                SERIAL PRIMARY KEY,
    number            TEXT,                  -- NULL while draft
    customer_id       INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    project_id        INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    estimate_id       INTEGER REFERENCES estimates(id) ON DELETE SET NULL,
    subscription_id   INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
    title             TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','open','partial','paid','void',
                                        'uncollectible','disputed')),
    currency          CHAR(3) NOT NULL DEFAULT 'USD',
    issue_date        DATE NOT NULL DEFAULT current_date,
    due_date          DATE,
    period_start      DATE,
    period_end        DATE,
    subtotal_cents    BIGINT NOT NULL DEFAULT 0,
    discount_cents    BIGINT NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    tax_cents         BIGINT NOT NULL DEFAULT 0,
    total_cents       BIGINT NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    -- Owned by billing.refresh_invoice_state(); always recomputed with SUM over
    -- payments/refunds/credits, never incremented.
    amount_paid_cents BIGINT NOT NULL DEFAULT 0,
    balance_due_cents BIGINT GENERATED ALWAYS AS (total_cents - amount_paid_cents) STORED,
    -- Bumped by any post-issue edit; carried in Stripe metadata so a webhook
    -- arriving for a stale version is credited but flagged for review.
    version           INTEGER NOT NULL DEFAULT 1,
    notes_md          TEXT NOT NULL DEFAULT '',
    terms_md          TEXT NOT NULL DEFAULT '',
    token_hash            BYTEA,
    previous_token_hash   BYTEA,
    token_expires_at      TIMESTAMPTZ,
    token_rotated_at      TIMESTAMPTZ,
    sent_at           TIMESTAMPTZ,
    first_viewed_at   TIMESTAMPTZ,
    last_viewed_at    TIMESTAMPTZ,
    issued_at         TIMESTAMPTZ,
    paid_at           TIMESTAMPTZ,
    voided_at         TIMESTAMPTZ,
    created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_invoices_number ON invoices (number) WHERE number IS NOT NULL;
CREATE UNIQUE INDEX uq_invoices_token  ON invoices (token_hash) WHERE token_hash IS NOT NULL;
CREATE INDEX idx_invoices_customer ON invoices (customer_id, id DESC);
CREATE INDEX idx_invoices_status   ON invoices (status, due_date, id DESC);
CREATE INDEX idx_invoices_open     ON invoices (due_date) WHERE status IN ('open','partial');
-- A double scheduler run cannot duplicate a period's invoice.
CREATE UNIQUE INDEX uq_invoices_sub_period ON invoices (subscription_id, period_start)
       WHERE subscription_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- line items
--
-- Three tables with identical columns, not one polymorphic table. Without an
-- ORM nothing remembers a discriminator for you, and a forgotten
-- "AND doc_type='invoice'" produces a plausible-looking WRONG NUMBER on an
-- invoice -- the worst failure mode this module has. Separate tables make that
-- bug inexpressible and give ON DELETE CASCADE for free. The duplication is
-- absorbed by the LINE_TABLES whitelist in backend/billing.py.
-- ---------------------------------------------------------------------------

CREATE TABLE invoice_lines (
    id              SERIAL PRIMARY KEY,
    invoice_id      INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    kind            TEXT NOT NULL DEFAULT 'item' CHECK (kind IN ('item','heading')),
    description     TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '',
    qty_milli       BIGINT NOT NULL DEFAULT 1000 CHECK (qty_milli >= 0),
    unit            TEXT NOT NULL DEFAULT '',
    unit_price_cents BIGINT NOT NULL DEFAULT 0,
    tax_rate_milli  INTEGER NOT NULL DEFAULT 0
                    CHECK (tax_rate_milli BETWEEN 0 AND 100000),
    -- Cannot disagree with qty x price. Mirrored in money.line_amount().
    amount_cents    BIGINT GENERATED ALWAYS AS
                    (round(qty_milli::numeric * unit_price_cents / 1000)::bigint) STORED
);
CREATE INDEX idx_invoice_lines ON invoice_lines (invoice_id, sort_order, id);

CREATE TABLE estimate_lines (
    id              SERIAL PRIMARY KEY,
    estimate_id     INTEGER NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    kind            TEXT NOT NULL DEFAULT 'item' CHECK (kind IN ('item','heading')),
    description     TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '',
    qty_milli       BIGINT NOT NULL DEFAULT 1000 CHECK (qty_milli >= 0),
    unit            TEXT NOT NULL DEFAULT '',
    unit_price_cents BIGINT NOT NULL DEFAULT 0,
    tax_rate_milli  INTEGER NOT NULL DEFAULT 0
                    CHECK (tax_rate_milli BETWEEN 0 AND 100000),
    amount_cents    BIGINT GENERATED ALWAYS AS
                    (round(qty_milli::numeric * unit_price_cents / 1000)::bigint) STORED
);
CREATE INDEX idx_estimate_lines ON estimate_lines (estimate_id, sort_order, id);

CREATE TABLE subscription_lines (
    id              SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    kind            TEXT NOT NULL DEFAULT 'item' CHECK (kind IN ('item','heading')),
    description     TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '',
    qty_milli       BIGINT NOT NULL DEFAULT 1000 CHECK (qty_milli >= 0),
    unit            TEXT NOT NULL DEFAULT '',
    unit_price_cents BIGINT NOT NULL DEFAULT 0,
    tax_rate_milli  INTEGER NOT NULL DEFAULT 0
                    CHECK (tax_rate_milli BETWEEN 0 AND 100000),
    amount_cents    BIGINT GENERATED ALWAYS AS
                    (round(qty_milli::numeric * unit_price_cents / 1000)::bigint) STORED
);
CREATE INDEX idx_subscription_lines ON subscription_lines (subscription_id, sort_order, id);

-- ---------------------------------------------------------------------------
-- payments
--
-- invoice_id NULL means money on account (a retainer deposit, or the overspill
-- half of an overpayment). That keeps
--     amount_paid_cents = SUM(payments WHERE invoice_id = X)
-- a true invariant instead of a special case.
-- ---------------------------------------------------------------------------

CREATE TABLE payments (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    invoice_id      INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    method          TEXT NOT NULL DEFAULT 'other'
                    CHECK (method IN ('card','bank_transfer','check','cash','credit','other')),
    amount_cents    BIGINT NOT NULL CHECK (amount_cents > 0),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    status          TEXT NOT NULL DEFAULT 'succeeded'
                    CHECK (status IN ('pending','processing','succeeded','failed','canceled')),
    received_on     DATE NOT NULL DEFAULT current_date,
    reference       TEXT NOT NULL DEFAULT '',      -- cheque no., wire ref
    memo            TEXT NOT NULL DEFAULT '',
    -- Stripe. livemode is stamped at creation and compared against the event's
    -- livemode in the webhook; a mismatch is ignored rather than applied.
    livemode                   BOOLEAN NOT NULL DEFAULT false,
    stripe_checkout_session_id TEXT,
    stripe_payment_intent_id   TEXT,
    stripe_charge_id           TEXT,
    stripe_balance_txn_id      TEXT,
    fee_cents                  BIGINT NOT NULL DEFAULT 0,
    -- Short-lived token used in Stripe's success_url. Never the invoice token:
    -- whatever URL we hand Stripe is stored on the session and visible in the
    -- Dashboard, and the invoice token is a long-lived payment credential.
    receipt_token              TEXT,
    receipt_token_expires_at   TIMESTAMPTZ,
    invoice_version            INTEGER,
    needs_review               BOOLEAN NOT NULL DEFAULT false,
    review_reason              TEXT,
    last_event_at              TIMESTAMPTZ,
    session_expires_at         TIMESTAMPTZ,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- These indexes, not the application logic, are what actually stop Stripe's
-- at-least-once delivery from being counted twice.
CREATE UNIQUE INDEX uq_payments_pi ON payments (stripe_payment_intent_id)
       WHERE stripe_payment_intent_id IS NOT NULL;
CREATE UNIQUE INDEX uq_payments_cs ON payments (stripe_checkout_session_id)
       WHERE stripe_checkout_session_id IS NOT NULL;
CREATE UNIQUE INDEX uq_payments_receipt ON payments (receipt_token)
       WHERE receipt_token IS NOT NULL;
CREATE INDEX idx_payments_invoice  ON payments (invoice_id, status);
CREATE INDEX idx_payments_customer ON payments (customer_id, received_on DESC, id DESC);
CREATE INDEX idx_payments_review    ON payments (needs_review) WHERE needs_review;

-- ---------------------------------------------------------------------------
-- refunds
-- ---------------------------------------------------------------------------

CREATE TABLE refunds (
    id               SERIAL PRIMARY KEY,
    payment_id       INTEGER NOT NULL REFERENCES payments(id) ON DELETE RESTRICT,
    invoice_id       INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    customer_id      INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    amount_cents     BIGINT NOT NULL CHECK (amount_cents > 0),
    currency         CHAR(3) NOT NULL DEFAULT 'USD',
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','succeeded','failed','canceled','error')),
    reason           TEXT NOT NULL DEFAULT '',
    stripe_refund_id TEXT,
    initiated_by     TEXT NOT NULL DEFAULT 'admin',   -- 'admin' | 'stripe_dashboard'
    created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    error            TEXT,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_refunds_stripe ON refunds (stripe_refund_id)
       WHERE stripe_refund_id IS NOT NULL;
CREATE INDEX idx_refunds_payment ON refunds (payment_id, status);
CREATE INDEX idx_refunds_invoice ON refunds (invoice_id, status);

-- ---------------------------------------------------------------------------
-- credit_ledger  (append-only)
--
--   SIGN CONVENTION -- positive means the customer owes us MORE, negative means
--   the customer owes us LESS. balance = SUM(delta_cents). A negative balance is
--   credit on account.
--
-- Every sign bug in this kind of system traces back to an unwritten convention,
-- so it is written here and again at the top of the ledger section of
-- backend/billing.py.
--
-- Append-only is enforced by convention: billing.py contains no UPDATE or
-- DELETE against this table. A trigger would be stronger, but this project has
-- no PL/pgSQL anywhere. Deliberate, documented gap.
-- ---------------------------------------------------------------------------

CREATE TABLE credit_ledger (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    kind         TEXT NOT NULL CHECK (kind IN (
                     'invoice','invoice_void','invoice_adjust',
                     'payment','payment_void','refund',
                     'credit_grant','credit_apply','chargeback','writeoff')),
    delta_cents  BIGINT NOT NULL,
    currency     CHAR(3) NOT NULL DEFAULT 'USD',
    invoice_id   INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    payment_id   INTEGER REFERENCES payments(id) ON DELETE SET NULL,
    refund_id    INTEGER REFERENCES refunds(id) ON DELETE SET NULL,
    memo         TEXT NOT NULL DEFAULT '',
    occurred_on  DATE NOT NULL DEFAULT current_date,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ledger_customer ON credit_ledger (customer_id, occurred_on, id);
CREATE INDEX idx_ledger_invoice  ON credit_ledger (invoice_id) WHERE invoice_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- subscription_runs
--
-- period_key is deterministic from the period start ('2026-07', '2026-Q3',
-- '2026', '2026-W30'). The unique constraint -- not the advisory lock -- is what
-- guarantees a period is never generated twice.
-- ---------------------------------------------------------------------------

CREATE TABLE subscription_runs (
    id              SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    period_key      TEXT NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE,
    scheduled_for   TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','success','failed','skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    last_error      TEXT,
    invoice_id      INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_sub_run_period ON subscription_runs (subscription_id, period_key);
CREATE INDEX idx_sub_runs_retry ON subscription_runs (status, next_attempt_at)
       WHERE status = 'failed';

-- ---------------------------------------------------------------------------
-- stripe_events
--
-- Dedupe keys on PROCESSED STATUS, not on row existence. The naive
-- "ON CONFLICT DO NOTHING, skip if duplicate" pattern loses an event forever:
-- insert, fail, return 500, Stripe retries, retry sees the conflict and skips.
-- ---------------------------------------------------------------------------

CREATE TABLE stripe_events (
    id                SERIAL PRIMARY KEY,
    stripe_event_id   TEXT NOT NULL,
    type              TEXT NOT NULL,
    livemode          BOOLEAN NOT NULL DEFAULT false,
    api_version       TEXT,
    created_at_stripe TIMESTAMPTZ,
    payload           JSONB,
    status            TEXT NOT NULL DEFAULT 'received'
                      CHECK (status IN ('received','processed','ignored','failed')),
    attempts          INTEGER NOT NULL DEFAULT 1,
    error             TEXT,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at      TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_stripe_events ON stripe_events (stripe_event_id);
CREATE INDEX idx_stripe_events_retry ON stripe_events (status, received_at)
       WHERE status IN ('received','failed');
CREATE INDEX idx_stripe_events_recent ON stripe_events (received_at DESC);

-- ---------------------------------------------------------------------------
-- email_log
--
-- Invoices are not fire-and-forget. A lost lead notification is annoying; a
-- silently unsent invoice is revenue nobody discovers for thirty days -- and
-- sent_at would already be set, so the admin believes it went out.
-- send_after supports billing_send_delay_minutes: a scheduler-generated invoice
-- sits briefly so a mistake is "delete a draft", not "apologise to the client".
-- ---------------------------------------------------------------------------

CREATE TABLE email_log (
    id              SERIAL PRIMARY KEY,
    kind            TEXT NOT NULL,
    to_addr         TEXT NOT NULL,
    cc_addr         TEXT NOT NULL DEFAULT '',
    subject         TEXT NOT NULL,
    body_text       TEXT NOT NULL DEFAULT '',
    body_html       TEXT,
    customer_id     INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    invoice_id      INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    estimate_id     INTEGER REFERENCES estimates(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','sending','sent','failed','permanently_failed','canceled')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    send_after      TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at TIMESTAMPTZ,
    error           TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_email_queue ON email_log (status, send_after)
       WHERE status IN ('queued','failed');
CREATE INDEX idx_email_invoice ON email_log (invoice_id, id DESC);
CREATE INDEX idx_email_recent  ON email_log (created_at DESC);

-- ---------------------------------------------------------------------------
-- invoice_views -- collections signal ("opened three times, hasn't paid") and
-- dispute evidence. Safe to prune; the financial tables never are.
-- ---------------------------------------------------------------------------

CREATE TABLE invoice_views (
    id          SERIAL PRIMARY KEY,
    invoice_id  INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
    estimate_id INTEGER REFERENCES estimates(id) ON DELETE CASCADE,
    ip          TEXT NOT NULL DEFAULT '',
    user_agent  TEXT NOT NULL DEFAULT '',
    viewed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_invoice_views ON invoice_views (invoice_id, viewed_at DESC);

-- ---------------------------------------------------------------------------
-- scheduler_state -- daily-job gating plus the heartbeat. Without the heartbeat
-- surfaced on the dashboard, a dead scheduler is invisible for a month -- and a
-- month of unbilled retainers.
-- ---------------------------------------------------------------------------

CREATE TABLE scheduler_state (
    key         TEXT PRIMARY KEY,
    last_run_at TIMESTAMPTZ,
    detail      TEXT NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- billing_audit -- who did what, for money mutations
-- ---------------------------------------------------------------------------

CREATE TABLE billing_audit (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username   TEXT NOT NULL DEFAULT '',
    ip         TEXT NOT NULL DEFAULT '',
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL DEFAULT '',
    entity_id  INTEGER,
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_billing_audit ON billing_audit (created_at DESC);
CREATE INDEX idx_billing_audit_entity ON billing_audit (entity, entity_id, id DESC);

-- ---------------------------------------------------------------------------
-- default settings (ON CONFLICT DO NOTHING, per 002_seed.sql's convention)
-- ---------------------------------------------------------------------------

INSERT INTO settings (key, value) VALUES
    ('billing_enabled',                 '1'),
    ('billing_currency',                'USD'),
    ('billing_default_terms_days',      '14'),
    ('billing_tax_rate_milli',          '0'),
    ('billing_tax_label',               'Tax'),
    ('billing_tax_number',              ''),
    ('billing_allow_partial_payment',   '1'),
    ('billing_min_payment_cents',       '100'),
    ('billing_statement_descriptor_suffix', ''),
    ('billing_invoice_prefix',          'INV'),
    ('billing_estimate_prefix',         'EST'),
    ('billing_number_pad',              '4'),
    ('billing_number_period',           'year'),
    ('billing_company_name',            'EdgeBourne'),
    ('billing_company_address',         ''),
    ('billing_company_email',           ''),
    ('billing_company_phone',           ''),
    ('billing_company_logo',            ''),
    ('billing_payment_instructions',    ''),
    ('billing_default_terms_text',      ''),
    ('billing_footer_notes',            ''),
    ('billing_timezone',                'UTC'),
    ('billing_run_hour',                '7'),
    ('billing_default_auto_send',       '1'),
    ('billing_send_delay_minutes',      '15'),
    ('billing_auto_send_max_cents',     '1000000'),
    ('billing_catchup_mode',            'all'),
    ('billing_reminder_enabled',        '0'),
    ('billing_reminder_days',           '-3,0,7,14,30'),
    ('billing_estimate_valid_days',     '30'),
    ('billing_token_ttl_days',          '90'),
    ('billing_admin_alert_email',       ''),
    ('billing_test_email_override',     '')
ON CONFLICT (key) DO NOTHING;
