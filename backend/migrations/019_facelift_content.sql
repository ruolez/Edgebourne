-- 019_facelift_content.sql
--
-- The homepage read as calm and beige: one offer ("Book a call"), no human on
-- the page, and results written as small grey labels. This adds what the new
-- layout needs, all of it editable in the admin:
--
--   * hero buttons that name the offer, plus a low-commitment second one (a
--     written workflow review, no call needed) in place of "See our work",
--     which the showcase right below already covers;
--   * the founder, shown in the hero, the closing call to action and on About
--     (Admin > Site content; the photo is optional, initials stand in);
--   * a "what changes" strip: three jobs, how they ran by hand and how they
--     run now, each with one figure the linked case study already backs up,
--     and a free-workflow-review call to action under it;
--   * an icon per industry tile.
--
-- Updates are guarded on the wording live today and inserts are DO NOTHING,
-- so a re-run is a no-op and anything edited in the admin stands.

UPDATE settings SET value = 'Book my free 30-min call'
 WHERE key = 'hero_cta_primary' AND value = 'Book a call';

UPDATE settings SET value = 'Get a free workflow review'
 WHERE key = 'hero_cta_secondary' AND value = 'See our work';
UPDATE settings SET value = '/contact?topic=review'
 WHERE key = 'hero_cta_secondary_url' AND value = '/work';

INSERT INTO settings (key, value) VALUES
  ('founder_name', 'Eugene'),
  ('founder_role', 'Founder & lead engineer'),
  -- JSON written by hero_image.cut_avatar(); empty means "initials only".
  ('founder_photo', ''),
  ('hero_trust_line', 'Over 100 systems running in warehouses, stores and law firms. You talk to the person who builds yours.'),
  ('cta_signoff', 'I read every message myself and reply within one business day.')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------- before/after
-- Each tile: the job (extra.job + extra.icon), the outcome as a headline
-- (title), how it ran by hand (subtitle), how it runs now (body), and one
-- figure from the case study it links to (extra.value + extra.label).
INSERT INTO content_blocks (group_key, block_key, title, subtitle, body, link_url, link_label, extra, sort_order)
VALUES
  ('sections', 'home_before_after', $$Your team stops doing the computer's job$$, 'WHAT CHANGES',
   $$Three jobs our clients used to do by hand, and how they run now. Every number comes from the case study behind it.$$,
   '', '', '{}', 0),
  ('sections', 'home_before_after_cta', $$Still doing one of these by hand?$$, '',
   $$Describe the job and we'll reply in writing with how we can help and roughly what it costs. No call needed.$$,
   '/contact?topic=review', 'Get a free workflow review', '{}', 0)
ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;

INSERT INTO content_blocks (group_key, block_key, title, subtitle, body, link_url, link_label, extra, sort_order)
VALUES
  ('home_before_after', 'shipping', $$From scan to printed label on one screen$$,
   $$The address typed in twice, carrier sites checked one by one, tracking pasted back by hand. For every box.$$,
   $$One screen compares five carriers, prints the best rate and sends the tracking to both systems.$$,
   '/work/shipping-desk-consolidation', 'See the shipping desk',
   '{"job": "Shipping desk", "icon": "truck", "value": "5", "label": "carrier platforms on one screen"}', 1),
  ('home_before_after', 'stock', $$Never sell the last one twice$$,
   $$Stock files uploaded to each store by hand, so two customers could buy the same last item.$$,
   $$Every store updates itself, as often as every five minutes. Nobody uploads a file.$$,
   '/work/realtime-inventory-sync', 'See the stock sync',
   '{"job": "Stock across stores", "icon": "cart", "value": "0", "label": "stock files uploaded by hand"}', 2),
  ('home_before_after', 'purchasing', $$Reorders that work themselves out$$,
   $$Reorder levels typed in by hand, and a list that still included what you ordered last week.$$,
   $$Reorder levels come from what actually sold, counting stock already on its way.$$,
   '/work/demand-driven-purchasing', 'See the purchasing tool',
   '{"job": "Purchasing", "icon": "chart", "value": "2", "label": "clicks to a supplier order"}', 3)
ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;

-- ---------------------------------------------------------------- industry icons
UPDATE content_blocks SET extra = extra || '{"icon": "cart"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'retail-ecommerce' AND NOT extra ? 'icon';
UPDATE content_blocks SET extra = extra || '{"icon": "truck"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'wholesale-distribution' AND NOT extra ? 'icon';
UPDATE content_blocks SET extra = extra || '{"icon": "box"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'warehouse-logistics' AND NOT extra ? 'icon';
UPDATE content_blocks SET extra = extra || '{"icon": "scale"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'legal-services' AND NOT extra ? 'icon';
UPDATE content_blocks SET extra = extra || '{"icon": "briefcase"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'professional-services' AND NOT extra ? 'icon';
UPDATE content_blocks SET extra = extra || '{"icon": "leaf"}'::jsonb
 WHERE group_key = 'home_sectors' AND block_key = 'food-beverage' AND NOT extra ? 'icon';

-- ---------------------------------------------------------------- contact step 2
-- The call is for any process, idea or problem, not only "the slow part".
UPDATE content_blocks
   SET body = $$You walk us through your process, idea or a problem, and we propose possible solutions for your needs.$$,
       updated_at = now()
 WHERE group_key = 'contact_steps' AND block_key = 'n2'
   AND replace(body, chr(13), '') = $$You walk us through the slow part. We ask about volumes, systems, and who touches what.$$;

-- ---------------------------------------------------------------- hero animation
-- The hero sketch showed one shipping job, so the company read as a logistics
-- shop. It is replaced by an animated reel in four parts (automate, connect,
-- save time, grow); this is the tab name and handwritten line for each.
-- hero_sketch (018) is no longer read.
INSERT INTO settings (key, value) VALUES
  ('hero_scenes', $$Automate: the busywork runs itself
Connect: all your systems, talking
Save time: hours back, every week
Grow: less waste, better margins$$)
ON CONFLICT (key) DO NOTHING;
