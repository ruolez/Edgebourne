-- 018_hero_sketch.sql
--
-- The homepage hero's right side becomes a drawn sketch of what we build: one
-- scan runs through the client's own app and lands as finished notes (stock,
-- shipping, the customer's tracking, the books). It replaces the generated
-- scene photo shipped in 017, which read as stock photography.
--
-- The shipped photo is unset only where it is still the shipped one; a photo
-- uploaded in the admin stays, and still takes the sketch's place.

UPDATE settings SET value = ''
 WHERE key = 'hero_image'
   AND value LIKE '%/static/media/hero/cda1cc8ecc8e4544a5a26fc7ef621024-master.webp%';

UPDATE settings SET value = ''
 WHERE key = 'hero_image_alt'
   AND value LIKE 'A business owner leans back with a cup of tea%';

-- One note per line, "Label: result". Line 1 is the scan, lines 2-5 are what
-- lands. Short results fit best (about 20 characters).
INSERT INTO settings (key, value) VALUES
  ('hero_sketch', $$Your packer: Scans order 4127
Stock: Same on every store
Shipping: Best rate, printed
Your customer: Has their tracking
The books: Cost already posted$$)
ON CONFLICT (key) DO NOTHING;
