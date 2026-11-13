-- D3 "Did it work?": before/after results for each change made from the console, at 3, 7 and 14
-- complete days. Recomputed by the worker until final; never written to Meta.
-- Grants come from db.APP_ROLE_SQL at boot (default privileges).
CREATE TABLE change_checks (
    account_id INTEGER NOT NULL DEFAULT app_account() REFERENCES accounts(id),
    change_id INTEGER NOT NULL REFERENCES meta_changes(id) ON DELETE CASCADE,
    horizon SMALLINT NOT NULL CHECK (horizon IN (3, 7, 14)),
    mode TEXT NOT NULL CHECK (mode IN ('self', 'parent', 'version', 'new', 'stopped')),
    scope_level TEXT NOT NULL CHECK (scope_level IN ('campaign', 'adset', 'ad')),
    scope_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('waiting', 'too_early', 'better', 'lean_better', 'same', 'lean_worse',
                                         'worse', 'on_target', 'over_target', 'mixed', 'no_compare',
                                         'stopped', 'not_running')),
    metric TEXT CHECK (metric IN ('cpl_cents', 'cpq_cents')),
    before_start DATE, before_end DATE, after_start DATE, after_end DATE,
    before_totals JSONB,          -- {days, spend_cents, leads, qualified, impressions} plus their rates
    after_totals JSONB,
    after_ready JSONB,            -- {cpl_cents: bool, cpq_cents: bool}: which metric the after side can be read on
    delta_pct INTEGER,            -- after vs before on `metric`, rounded like compare._delta
    confidence SMALLINT,          -- experiments.confidence on `metric`, 0-99
    needs TEXT,                   -- "$30 more spend and 1 more lead"
    target_cents INTEGER,         -- the target `metric` was judged against
    days SMALLINT,                -- complete days on each side (shorter than the horizon when cut by another change)
    cut_by DATE,                  -- the day another change ended the after window
    sentence TEXT NOT NULL,       -- the plain line shown everywhere and sent to Claude
    notes JSONB NOT NULL DEFAULT '[]',
    expect_met BOOLEAN,           -- NULL = no expectation, another horizon, or not judgeable yet
    ready_on DATE,                -- first day this horizon can be read (after_end + 1)
    final BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, change_id, horizon)
);
CREATE INDEX change_checks_open_idx ON change_checks (account_id) WHERE NOT final;
CREATE INDEX change_checks_change_idx ON change_checks (change_id);
ALTER TABLE change_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY account_isolation ON change_checks
    USING (account_id = app_account()) WITH CHECK (account_id = app_account());

-- What Claude said would happen, in a form the check can test: {"metric": "cpl"|"cpq", "op": "<"|"<=", "cents": 4000, "days": 7}
ALTER TABLE desk_proposals ADD COLUMN expect JSONB;

-- "Put it back" says which change it reverses, so the check can say "Put back on Nov 17 by Eugene".
ALTER TABLE meta_changes ADD COLUMN undo_of INTEGER REFERENCES meta_changes(id) ON DELETE SET NULL;
CREATE INDEX meta_changes_undo_idx ON meta_changes (undo_of) WHERE undo_of IS NOT NULL;
