CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    notify_new_leads BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mirror of the Meta campaigns we know about; assignment is ours.
CREATE TABLE campaigns (
    id TEXT PRIMARY KEY,                -- Meta campaign id
    name TEXT NOT NULL,
    status TEXT,
    effective_status TEXT,
    objective TEXT,
    daily_budget_cents INTEGER,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE campaign_members (
    campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, user_id)
);

CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    meta_lead_id TEXT NOT NULL UNIQUE,
    created_time TIMESTAMPTZ NOT NULL,   -- when the person submitted the form
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    form_id TEXT,
    form_name TEXT,
    ad_id TEXT,
    ad_name TEXT,
    adset_id TEXT,
    campaign_id TEXT,
    campaign_name TEXT,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    business_type TEXT,
    answers JSONB NOT NULL DEFAULT '[]',  -- every field_data entry as Meta sent it
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'contacted', 'qualified', 'won', 'lost')),
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    first_contacted_at TIMESTAMPTZ,
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    emailed_at TIMESTAMPTZ
);
CREATE INDEX leads_created_idx ON leads (created_time DESC);
CREATE INDEX leads_campaign_idx ON leads (campaign_id);
CREATE INDEX leads_status_idx ON leads (status);

CREATE TABLE lead_notes (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX lead_notes_lead_idx ON lead_notes (lead_id, created_at);

-- Raw Meta webhook deliveries; kept so a failed lead can be retried.
CREATE TABLE webhook_events (
    id SERIAL PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL,
    leadgen_id TEXT,
    processed_at TIMESTAMPTZ,
    error TEXT
);
CREATE INDEX webhook_events_pending_idx ON webhook_events (processed_at) WHERE processed_at IS NULL;

-- Every change anyone (person, server or Claude) makes.
CREATE TABLE activity (
    id SERIAL PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor TEXT NOT NULL,                -- 'user', 'system', 'meta', 'claude'
    action TEXT NOT NULL,
    subject TEXT,
    details JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX activity_at_idx ON activity (at DESC);
