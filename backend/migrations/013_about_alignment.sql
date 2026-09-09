-- The About page contradicted the homepage and priced itself in commits.
--
-- Surgical REPLACE rather than rewriting the whole value, so any edit made in
-- the admin since deploy survives and only these phrases change. Every
-- statement is idempotent: the new wording does not contain the old.

-- 1. The stats band. About and the homepage stated different figures for the
--    same two facts, so a visitor moving between them saw the numbers change.
--    Guarded on the seeded values, so a figure already edited is left alone.
UPDATE content_blocks SET title = '99+', updated_at = now()
 WHERE group_key = 'about_stats' AND subtitle = 'systems in production' AND title = '10';

UPDATE content_blocks SET title = '10', updated_at = now()
 WHERE group_key = 'about_stats' AND subtitle = 'industries served' AND title = '6';

-- "486 commits on the largest build" is an engineering vanity metric; a buyer
--  cannot price a commit. Ownership is the claim that actually differentiates.
UPDATE content_blocks SET title = '100%', subtitle = 'code and data you own', updated_at = now()
 WHERE group_key = 'about_stats' AND title = '486';

-- 2. The prose, in both the markdown source and the rendered HTML.
UPDATE settings SET value = REPLACE(value,
    'nearly five hundred commits deep and still shipping',
    'the deepest-running system in the portfolio, and still shipping'),
  updated_at = now()
 WHERE key IN ('about_md', 'about_html') AND value LIKE '%nearly five hundred commits deep%';

-- Also switches "across" to "including", making the list read as examples
-- rather than an exhaustive six -- which is what conflicted with the
-- industries figure in the band directly above it.
UPDATE settings SET value = REPLACE(value,
    'Together those systems represent well over a thousand commits of production work across distribution, retail, warehousing, legal, finance and professional services.',
    'Together those systems run every day across industries including distribution, retail, warehousing, legal, finance and professional services.'),
  updated_at = now()
 WHERE key IN ('about_md', 'about_html') AND value LIKE '%well over a thousand commits%';

-- The importer carries over four hundred tests, not "over two hundred and
-- fifty" -- the original figure understated it.
UPDATE settings SET value = REPLACE(value,
    'over two hundred and fifty unit tests',
    'over four hundred unit tests'),
  updated_at = now()
 WHERE key IN ('about_md', 'about_html') AND value LIKE '%over two hundred and fifty unit tests%';
