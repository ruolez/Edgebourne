-- Roadmap 5.2: competitor ads worth keeping, the Pages watched, and a weekly check (off).
CREATE TABLE swipes (
    id SERIAL PRIMARY KEY,
    library_id TEXT UNIQUE,
    page_name TEXT NOT NULL,
    page_id TEXT,
    body TEXT,
    title TEXT,
    cta TEXT,
    media_url TEXT,
    started_on DATE,
    stopped_on DATE,
    platforms JSONB NOT NULL DEFAULT '[]',
    notes TEXT,
    tags JSONB NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'claude')),
    saved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    first_saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX swipes_page_idx ON swipes (page_name);

CREATE TABLE watched_pages (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    page_id TEXT,
    search_terms TEXT,
    notes TEXT,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO desk_schedules (name, about, kind, prompt, rule, position) VALUES
('Competitor check',
 'Searches the Ad Library for every watched Page: new ads since last week and ads that have run 30+ days (a sign they work) go into the swipe file, with a short note on what is worth testing here.',
 'research',
 E'Scheduled weekly competitor check. Run `desk watched` for the watched Pages. For each, search the Meta Ad Library (ads_library_search, US, active ads; by Page id when given, otherwise by the name or search terms). Save every ad that is new since the Page was last checked, and every ad that has run 30 days or more, with `desk swipe --file` (library id, page name and id, text, headline, button, start date, platforms, and hook / angle tags in this dashboard''s style). Report: what each competitor is running now, which ads have run longest and why they likely work, and at most three ideas worth testing here (as tags proposals or an experiment, never a change). No budget advice.',
 '{"every": "week", "weekday": 2, "at": "09:30"}', 5);
