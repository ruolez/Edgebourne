-- Merge "Mobile & Scanner Apps" into "Custom Web Apps".
--
-- They were never really two services: everything mobile in the portfolio is a
-- responsive web app running on warehouse hardware, not a native build. Merging
-- says that plainly and frees the fourth slot in the homepage services grid
-- (which shows the first four) for "Optimize with AI".
UPDATE services
   SET title = 'Custom Web & Mobile Apps',
       summary = 'Internal tools, portals and dashboards for the desk — and scan stations for the warehouse floor. One system, shaped around how your company already works.',
       body_md = 'Off-the-shelf software makes your team adapt to it. We build the opposite: applications shaped around the way your company already works, running on your own infrastructure, using your own data.

Some of that work happens at a desk. Some of it happens at a receiving door with a scanner in one hand. It is the same system either way — which is the point, because the moment the floor gets its own disconnected tool, the numbers start to disagree.

### At the desk

- One screen that replaces a six-system copy-and-paste job when a new product is added
- A purchasing tool that computes reorder points from real sales velocity instead of gut feel
- A statement importer that reads CSV, Excel and scanned PDFs and categorises the lines for you
- A client intake portal with no login, that turns a completed questionnaire into a tracked account
- Operations dashboards that read live from the systems you already run

### On the floor

- Barcode scan-and-verify for inbound deliveries, so a short shipment is caught at the door rather than at month end
- Bin and slot location tracking, with quantity adjustments made in the aisle
- Two-scan pack and check stations, with each scan attributed to the person who made it
- Mobile cycle counts that write to an audit table instead of a clipboard

### How they are built

Server-rendered or single-page, whichever suits the job. PostgreSQL, or the SQL Server you already run. Plain migrations, Docker, a one-line installer.

The floor tools are **responsive web apps**, not native ones — which means no app store, no device enrolment, and no version drift across a fleet of handhelds. They run on the scanners and phones you already own, and an update is a page refresh.

Where they have logins, they authenticate against your existing ERP user tables, so a new hire is added once in the system where staff are already managed — and someone disabled there is locked out of the floor immediately. Every write carries a user and a timestamp. Accountability is the point, not a side effect.

You get the repository, the installer and documentation your next hire can read.

See the [warehouse floor suite](/work/warehouse-floor-suite) for four of these running in one building.',
       body_html = '<p>Off-the-shelf software makes your team adapt to it. We build the opposite: applications shaped around the way your company already works, running on your own infrastructure, using your own data.</p>
<p>Some of that work happens at a desk. Some of it happens at a receiving door with a scanner in one hand. It is the same system either way — which is the point, because the moment the floor gets its own disconnected tool, the numbers start to disagree.</p>
<h3>At the desk</h3>
<ul>
<li>One screen that replaces a six-system copy-and-paste job when a new product is added</li>
<li>A purchasing tool that computes reorder points from real sales velocity instead of gut feel</li>
<li>A statement importer that reads CSV, Excel and scanned PDFs and categorises the lines for you</li>
<li>A client intake portal with no login, that turns a completed questionnaire into a tracked account</li>
<li>Operations dashboards that read live from the systems you already run</li>
</ul>
<h3>On the floor</h3>
<ul>
<li>Barcode scan-and-verify for inbound deliveries, so a short shipment is caught at the door rather than at month end</li>
<li>Bin and slot location tracking, with quantity adjustments made in the aisle</li>
<li>Two-scan pack and check stations, with each scan attributed to the person who made it</li>
<li>Mobile cycle counts that write to an audit table instead of a clipboard</li>
</ul>
<h3>How they are built</h3>
<p>Server-rendered or single-page, whichever suits the job. PostgreSQL, or the SQL Server you already run. Plain migrations, Docker, a one-line installer.</p>
<p>The floor tools are <strong>responsive web apps</strong>, not native ones — which means no app store, no device enrolment, and no version drift across a fleet of handhelds. They run on the scanners and phones you already own, and an update is a page refresh.</p>
<p>Where they have logins, they authenticate against your existing ERP user tables, so a new hire is added once in the system where staff are already managed — and someone disabled there is locked out of the floor immediately. Every write carries a user and a timestamp. Accountability is the point, not a side effect.</p>
<p>You get the repository, the installer and documentation your next hire can read.</p>
<p>See the <a href="/work/warehouse-floor-suite">warehouse floor suite</a> for four of these running in one building.</p>',
       sort_order = 1,
       is_published = true,
       updated_at = now()
 WHERE slug = 'custom-web-apps';

-- Unpublished rather than deleted: the row keeps its history and can be
-- restored from the admin if the merge is ever reversed.
UPDATE services SET is_published = false, updated_at = now() WHERE slug = 'mobile-apps';

UPDATE services SET sort_order = 2, updated_at = now() WHERE slug = 'systems-integration';
UPDATE services SET sort_order = 3, updated_at = now() WHERE slug = 'business-automation';
UPDATE services SET sort_order = 4, updated_at = now() WHERE slug = 'optimize-with-ai';
UPDATE services SET sort_order = 5, updated_at = now() WHERE slug = 'custom-reports';

-- The footer's "What we build" column listed the two services separately, so
-- they collapse into one entry here too -- retitle the surviving row and drop
-- the one whose anchor no longer exists, rather than repointing both at the
-- same target and leaving a duplicate.
UPDATE content_blocks
   SET title = 'Web & mobile apps', updated_at = now()
 WHERE group_key = 'footer_build' AND link_url = '/services#custom-web-apps';

DELETE FROM content_blocks
 WHERE group_key = 'footer_build' AND link_url = '/services#mobile-apps';
