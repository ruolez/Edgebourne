-- Emails to leads: templates (Settings → Lead replies) and every reply sent, by hand or automatically.
CREATE TABLE reply_templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO reply_templates (name, subject, body, position) VALUES (
    'First reply',
    'Your free intro call with Edge Bourne',
    E'Hi {first_name},\n\nThanks for asking for a free intro call. I''m {my_name} from Edge Bourne.\n\nI''ll call you at {phone} today. If another time suits you better, just reply to this email.\n\nYou can also pick a time yourself: {booking_link}\n\nTalk soon,\n{my_name}\nEdge Bourne',
    0);

CREATE TABLE lead_replies (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    template_id INTEGER REFERENCES reply_templates(id) ON DELETE SET NULL,
    auto BOOLEAN NOT NULL DEFAULT FALSE,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX lead_replies_one_auto ON lead_replies (lead_id) WHERE auto;
CREATE INDEX lead_replies_lead ON lead_replies (lead_id, created_at);
