-- Claude's regular checks. Each run is an ordinary Desk task; all start switched off.
CREATE TABLE desk_schedules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    about TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'review',
    prompt TEXT NOT NULL,
    rule JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_task_id INTEGER REFERENCES desk_tasks(id) ON DELETE SET NULL,
    skipped INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO desk_schedules (name, about, prompt, rule, position) VALUES
('Daily health check',
 'Rejected ads, delivery problems, ads with no impressions, spend against the budget, lead volume and the spending limit. No budget advice.',
 E'Scheduled daily health check. Health only, no budget advice: rejected or disapproved ads, delivery errors, ads with zero impressions yesterday, yesterday''s and this week''s spend against the daily budget (Meta may spend up to 1.75x the daily budget on one day), leads yesterday against the last 7 days, the spending limit, and whether form leads are still arriving in the inbox. When everything is fine, say so in five lines or fewer. Propose something only if it is broken.',
 '{"every": "day", "at": "08:30"}', 1),
('Optimizer review',
 'Cost per lead against the $60 target for each ad and ad set over the last 7 days, with the minimum-data rule. Proposes keep, scale (+20% at most), pause or new creative.',
 E'Scheduled optimizer review (every few days). Judge each ad set and ad on cost per lead against the $60 target over the last 7 complete days, with the minimum-data rule. Propose scaling a clear winner by at most +20% (one budget change per campaign, at least 3 days after the last one), hold what is near target, propose pausing clear losers, and ask for fresh creative when cost per lead is 30% or more over target. Proposals only; nothing changes until Eugene approves.',
 '{"every": "days", "days": 3, "at": "09:00"}', 2),
('Monday summary',
 'Last week against the week before: spend, leads, cost per lead, lead stages, what changed, and the three priorities for this week.',
 E'Scheduled Monday summary. Last week (Monday to Sunday) against the week before: spend, leads, cost per lead, lead stages from the inbox (contacted, qualified, won), what changed in the account and why, what needs attention this week, and the three priorities. Plain words, under 400 words.',
 '{"every": "week", "weekday": 0, "at": "08:00"}', 3),
('Monthly audit',
 'Last month: account health, creative fatigue, frequency, wasted spend, tracking quality, which ads to retire and 3-5 new concepts to test.',
 E'Scheduled monthly audit of last month: an account health score, creative fatigue per ad (frequency, click rate and cost per 1,000 impressions trend), audience overlap, wasted spend, tracking quality (dataset and lead form), which creatives to retire and 3-5 genuinely different new concepts to test next.',
 '{"every": "month", "monthday": 1, "at": "09:00"}', 4);
