-- Hero/footer strapline: "WEB & MOBILE APPS" shortens to "APPS" to make room
-- for AI, now that it is a service in its own right.
--
-- Guarded on the old value so a strapline an admin has since edited in
-- Admin > Site content is left alone. Re-running is a no-op.
UPDATE settings
   SET value = 'APPS · INTEGRATION · AUTOMATION · AI',
       updated_at = now()
 WHERE key = 'hero_eyebrow'
   AND value = 'WEB & MOBILE APPS · INTEGRATION · AUTOMATION';
