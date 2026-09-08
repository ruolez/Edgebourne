-- The company is written "Edge Bourne Consulting" in prose, page titles and on
-- documents; "EdgeBourne" survives only as the logo wordmark, which is markup in
-- _nav.html / _footer.html and is deliberately not stored here.
--
-- REPLACE rather than an assignment so a value an admin has since customised
-- keeps its wording and only the name changes. Re-running is a no-op: the new
-- name does not contain the old one as a substring.
UPDATE settings
   SET value = REPLACE(value, 'EdgeBourne', 'Edge Bourne Consulting'),
       updated_at = now()
 WHERE value LIKE '%EdgeBourne%';

UPDATE case_studies
   SET summary   = REPLACE(summary, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_md   = REPLACE(body_md, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_html = REPLACE(body_html, 'EdgeBourne', 'Edge Bourne Consulting'),
       updated_at = now()
 WHERE summary LIKE '%EdgeBourne%' OR body_md LIKE '%EdgeBourne%' OR body_html LIKE '%EdgeBourne%';

UPDATE posts
   SET excerpt   = REPLACE(excerpt, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_md   = REPLACE(body_md, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_html = REPLACE(body_html, 'EdgeBourne', 'Edge Bourne Consulting'),
       updated_at = now()
 WHERE excerpt LIKE '%EdgeBourne%' OR body_md LIKE '%EdgeBourne%' OR body_html LIKE '%EdgeBourne%';

UPDATE services
   SET summary   = REPLACE(summary, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_md   = REPLACE(body_md, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_html = REPLACE(body_html, 'EdgeBourne', 'Edge Bourne Consulting'),
       updated_at = now()
 WHERE summary LIKE '%EdgeBourne%' OR body_md LIKE '%EdgeBourne%' OR body_html LIKE '%EdgeBourne%';

UPDATE pages
   SET body_md   = REPLACE(body_md, 'EdgeBourne', 'Edge Bourne Consulting'),
       body_html = REPLACE(body_html, 'EdgeBourne', 'Edge Bourne Consulting'),
       updated_at = now()
 WHERE body_md LIKE '%EdgeBourne%' OR body_html LIKE '%EdgeBourne%';

UPDATE faqs
   SET answer_md   = REPLACE(answer_md, 'EdgeBourne', 'Edge Bourne Consulting'),
       answer_html = REPLACE(answer_html, 'EdgeBourne', 'Edge Bourne Consulting')
 WHERE answer_md LIKE '%EdgeBourne%' OR answer_html LIKE '%EdgeBourne%';
