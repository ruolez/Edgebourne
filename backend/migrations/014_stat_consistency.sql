-- Three numbers disagreed with each other across the site.
-- All guarded on the current value, so a figure since edited in the admin is
-- left alone, and re-running changes nothing.

-- 1. Industries: the band claimed ten, while the Industries page head says
--    "Six industries where we have shipped systems". Six is what the site
--    actually substantiates -- six sectors on that page, six named in the
--    About copy -- so the band comes down to meet it.
UPDATE content_blocks SET title = '6', updated_at = now()
 WHERE group_key IN ('home_stats', 'about_stats')
   AND subtitle = 'industries served' AND title = '10';

-- 2. Systems: the hero chip says "Over 100", the bands said "99+". Those are
--    different claims (99+ includes 99). Both become 100+, which matches the
--    chip and reads better in large type.
UPDATE content_blocks SET title = '100+', updated_at = now()
 WHERE group_key IN ('home_stats', 'about_stats')
   AND subtitle = 'systems in production' AND title = '99+';

-- 3. The Work page head said "Ten systems running in production", which
--    contradicted both of the above -- a reader saw 100+ on the homepage and
--    ten one click later. Ten is the number of case studies written up, not
--    the number of systems, so the lede now says exactly that. It also reads
--    as stronger: a selection from a larger body of work.
UPDATE content_blocks
   SET body = 'Ten of them written up in full. Clients are described by industry, not by name.',
       updated_at = now()
 WHERE group_key = 'page_heads' AND block_key = 'work'
   AND body = 'Ten systems running in production. Clients are described by industry, not by name.';
