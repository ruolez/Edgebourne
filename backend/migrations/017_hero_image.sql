-- 017_hero_image.sql
--
-- The homepage hero showed copy and a faint watermark, and nothing a visitor
-- could recognise. It becomes a split hero: copy on the left, the work on the
-- right. The right side is a real case-study screenshot in front of a scene
-- photo: an owner at the end of a calm day, the dashboard all green, the
-- parcels labeled and waiting. The photo ships in static/media/hero/ (cut by
-- hero_image.cut, focus centre) and can be replaced or removed in Admin > Site
-- content; with no photo the screenshot carries the panel alone.
--
-- Every insert is DO NOTHING, so values edited in the admin stand.

INSERT INTO settings (key, value) VALUES
  -- JSON written by hero_image.cut(); empty means "no photo".
  ('hero_image', $${"master": "/static/media/hero/cda1cc8ecc8e4544a5a26fc7ef621024-master.webp", "focus": "center", "portrait": [{"src": "/static/media/hero/3189231b6c56-p-640.webp", "w": 640, "h": 800}, {"src": "/static/media/hero/3189231b6c56-p-819.webp", "w": 819, "h": 1024}], "landscape": [{"src": "/static/media/hero/3189231b6c56-l-800.webp", "w": 800, "h": 600}, {"src": "/static/media/hero/3189231b6c56-l-1200.webp", "w": 1200, "h": 900}], "og": "/static/media/hero/3189231b6c56-og.jpg"}$$),
  ('hero_image_alt', 'A business owner leans back with a cup of tea at the end of the day, a dashboard of green check marks on the wall and labeled parcels ready for pickup.'),
  -- The case study whose screenshot sits in the hero. Its first metric is the
  -- chip on the panel, so the hero only ever states a figure the case study
  -- already backs up.
  ('hero_case_slug', 'shipping-desk-consolidation'),
  ('hero_cta_note', 'A 30-minute call, no obligation. We reply within one business day.')
ON CONFLICT (key) DO NOTHING;

-- The stats band right under the hero still said "10 systems in production"
-- while the hero chip says "Over 100". 013/014 fixed the About band and the
-- "99+" rows; the homepage row seeded as '10' was never touched. Ten is the
-- number of case studies written up, not of systems running.
UPDATE content_blocks SET title = '100+', updated_at = now()
 WHERE group_key = 'home_stats' AND subtitle = 'systems in production' AND title = '10';
