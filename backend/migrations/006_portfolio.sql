-- Portfolio build: case studies grow the fields a real portfolio page needs,
-- plus two small content tables of their own.
--
-- Notes on the shapes chosen here:
--
--   * metrics and gallery are JSONB, not side tables. They are ordered, small
--     (<= 4 metrics, a handful of images), never queried across rows and only
--     ever read whole with their parent. A join table would buy nothing and
--     cost an extra query on every case-study render.
--
--   * stack is deliberately separate from tech_tags. tech_tags is the short
--     card badge list; stack is the full "what this was built on" rundown.
--
--   * testimonials.is_approved defaults to FALSE and the public site renders
--     only approved rows. Quotes are drafted for the client, then published by
--     the client -- never the other way round.

ALTER TABLE case_studies
    ADD COLUMN IF NOT EXISTS industry     TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS engagement   TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS problem_lede TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS metrics      JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS gallery      JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS stack        TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS is_featured  BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_case_studies_featured
    ON case_studies (sort_order, id) WHERE is_published AND is_featured;
CREATE INDEX IF NOT EXISTS idx_case_studies_industry
    ON case_studies (industry) WHERE is_published;

CREATE TABLE IF NOT EXISTS testimonials (
    id              SERIAL PRIMARY KEY,
    quote           TEXT NOT NULL,
    author_role     TEXT NOT NULL DEFAULT '',
    industry        TEXT NOT NULL DEFAULT '',
    case_study_slug TEXT NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_approved     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_testimonials_approved
    ON testimonials (is_approved, sort_order, id);
-- Not a foreign key: a quote may outlive the case study it was gathered for,
-- and the slug is also allowed to be blank (a site-wide quote).
CREATE INDEX IF NOT EXISTS idx_testimonials_slug
    ON testimonials (case_study_slug);

CREATE TABLE IF NOT EXISTS faqs (
    id           SERIAL PRIMARY KEY,
    question     TEXT NOT NULL,
    answer_md    TEXT NOT NULL DEFAULT '',
    answer_html  TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_faqs_published
    ON faqs (is_published, sort_order, id);
