INSERT INTO settings (key, value) VALUES
  ('site_title', 'EdgeBourne'),
  ('hero_eyebrow_strong', 'CUSTOM SOLUTIONS'),
  ('hero_eyebrow', 'WEB & MOBILE APPS · INTEGRATION · AUTOMATION'),
  ('hero_title', 'Run the business.'),
  ('hero_title_accent', 'We''ll run the systems.'),
  ('hero_sub', 'Custom web and mobile apps, automation and integration for small and mid-size companies — built to fit the way you already work.'),
  ('hero_cta_primary', 'Book a call'),
  ('hero_cta_primary_url', '/contact'),
  ('hero_cta_secondary', 'See our work'),
  ('hero_cta_secondary_url', '/work'),
  ('seo_default_title', 'EdgeBourne — Custom Software, Integration & Automation'),
  ('seo_default_description', 'Custom web and mobile apps, automation and integration for small and mid-size companies — built to fit the way you already work.'),
  ('contact_email', 'eugene@stop-by.com'),
  ('notify_email', ''),
  ('phone', ''),
  ('social_linkedin', ''),
  ('social_github', ''),
  ('about_md', 'EdgeBourne exists for one reason: most small and mid-size companies run on systems that don''t talk to each other. Orders live in one place, inventory in another, accounting in a third — and people fill the gaps by retyping data.

We build the connective tissue. Custom web and mobile applications, integrations between the platforms you already use, and automation that removes the repetitive work entirely.

**How we work**

- **Small, senior, direct.** You talk to the people building your system — no account managers, no hand-offs.
- **Built around your workflow.** We start from how your company actually operates, not from a template.
- **Boringly reliable.** Docker deployments, monitored services, plain documentation your next hire can read.

If your team spends hours a week moving data between systems, that''s usually the first thing we fix — and it usually pays for itself within months.'),
  ('about_html', '<p>EdgeBourne exists for one reason: most small and mid-size companies run on systems that don&rsquo;t talk to each other. Orders live in one place, inventory in another, accounting in a third &mdash; and people fill the gaps by retyping data.</p>
<p>We build the connective tissue. Custom web and mobile applications, integrations between the platforms you already use, and automation that removes the repetitive work entirely.</p>
<p><strong>How we work</strong></p>
<ul>
<li><strong>Small, senior, direct.</strong> You talk to the people building your system &mdash; no account managers, no hand-offs.</li>
<li><strong>Built around your workflow.</strong> We start from how your company actually operates, not from a template.</li>
<li><strong>Boringly reliable.</strong> Docker deployments, monitored services, plain documentation your next hire can read.</li>
</ul>
<p>If your team spends hours a week moving data between systems, that&rsquo;s usually the first thing we fix &mdash; and it usually pays for itself within months.</p>'),
  ('smtp_host', ''),
  ('smtp_port', ''),
  ('smtp_user', ''),
  ('smtp_password', ''),
  ('smtp_from', ''),
  ('smtp_tls', 'starttls')
ON CONFLICT (key) DO NOTHING;

INSERT INTO services (title, slug, summary, body_md, body_html, sort_order, is_published) VALUES
(
  'Custom Web Apps',
  'custom-web-apps',
  'Dashboards, portals and internal tools built around your workflows — fast, secure and easy for your team to use.',
  'Off-the-shelf software makes your team adapt to it. We build the opposite: web applications shaped around the way your company already works.

- Internal tools and dashboards that replace spreadsheet sprawl
- Customer and vendor portals
- Order, inventory and operations management systems
- Reporting that pulls live data from the systems you already run

Every app ships in Docker, behind proper authentication, with documentation your team can actually use.',
  '<p>Off-the-shelf software makes your team adapt to it. We build the opposite: web applications shaped around the way your company already works.</p>
<ul>
<li>Internal tools and dashboards that replace spreadsheet sprawl</li>
<li>Customer and vendor portals</li>
<li>Order, inventory and operations management systems</li>
<li>Reporting that pulls live data from the systems you already run</li>
</ul>
<p>Every app ships in Docker, behind proper authentication, with documentation your team can actually use.</p>',
  1, true
),
(
  'Mobile Apps',
  'mobile-apps',
  'iOS and Android apps that put your operations in your team''s pocket — scanning, field work, approvals on the go.',
  'When the work happens away from a desk — in a warehouse, on a delivery route, at a client site — a mobile app is the difference between data entered now and data entered never.

- Barcode scanning and warehouse workflows
- Field service and delivery apps
- Approvals and notifications for managers on the move
- Offline-first designs that sync when connectivity returns

We build for both platforms from a single codebase where it makes sense, and native where it doesn''t.',
  '<p>When the work happens away from a desk &mdash; in a warehouse, on a delivery route, at a client site &mdash; a mobile app is the difference between data entered now and data entered never.</p>
<ul>
<li>Barcode scanning and warehouse workflows</li>
<li>Field service and delivery apps</li>
<li>Approvals and notifications for managers on the move</li>
<li>Offline-first designs that sync when connectivity returns</li>
</ul>
<p>We build for both platforms from a single codebase where it makes sense, and native where it doesn&rsquo;t.</p>',
  2, true
),
(
  'Systems Integration',
  'systems-integration',
  'Connect your ERP, e-commerce, warehouse and accounting systems so data flows automatically — no retyping, no drift.',
  'Most companies don''t need new software — they need their existing software to talk. We connect the systems you already run so information moves by itself.

- E-commerce ↔ back office: orders, inventory, tracking numbers
- ERP and accounting sync
- Shipping platforms, 3PLs and carrier APIs
- Legacy databases exposed safely to modern tools

Integrations run as monitored services with retries, logging and alerting — so when something upstream breaks, you know before your customers do.',
  '<p>Most companies don&rsquo;t need new software &mdash; they need their existing software to talk. We connect the systems you already run so information moves by itself.</p>
<ul>
<li>E-commerce &harr; back office: orders, inventory, tracking numbers</li>
<li>ERP and accounting sync</li>
<li>Shipping platforms, 3PLs and carrier APIs</li>
<li>Legacy databases exposed safely to modern tools</li>
</ul>
<p>Integrations run as monitored services with retries, logging and alerting &mdash; so when something upstream breaks, you know before your customers do.</p>',
  3, true
),
(
  'Business Automation',
  'business-automation',
  'Automate the repetitive work — reports, syncing, notifications, document generation — so your team focuses on customers.',
  'Every business has jobs that eat hours and add nothing: compiling the Monday report, copying invoices between systems, chasing status updates. Those are automation targets.

- Scheduled reports delivered to your inbox
- Document generation: invoices, labels, quotes, packing lists
- Alert and notification pipelines
- Data cleanup and reconciliation jobs

We start with the task that costs your team the most time, automate it end-to-end, and expand from there.',
  '<p>Every business has jobs that eat hours and add nothing: compiling the Monday report, copying invoices between systems, chasing status updates. Those are automation targets.</p>
<ul>
<li>Scheduled reports delivered to your inbox</li>
<li>Document generation: invoices, labels, quotes, packing lists</li>
<li>Alert and notification pipelines</li>
<li>Data cleanup and reconciliation jobs</li>
</ul>
<p>We start with the task that costs your team the most time, automate it end-to-end, and expand from there.</p>',
  4, true
);

INSERT INTO case_studies (title, slug, client, summary, body_md, body_html, tech_tags, sort_order, is_published) VALUES
(
  'Order & Inventory Sync for a Distribution Company',
  'order-inventory-sync',
  'Sample Client',
  'Connected an e-commerce storefront to a legacy back-office system — orders, inventory and tracking numbers now flow automatically in both directions.',
  '*This is a sample case study — edit or delete it in the admin panel, then publish your own.*

**The problem.** Orders arrived in the online store, but the back-office system that ran purchasing, invoicing and the warehouse never heard about them until someone retyped each one. Inventory counts drifted daily.

**What we built.** A monitored integration service that syncs orders, stock levels and shipment tracking between the two systems every few minutes, with a small dashboard showing sync status and any records that need human attention.

**The result.** Zero manual order entry, inventory accurate across both systems, and tracking numbers back to customers the moment labels are printed.',
  '<p><em>This is a sample case study &mdash; edit or delete it in the admin panel, then publish your own.</em></p>
<p><strong>The problem.</strong> Orders arrived in the online store, but the back-office system that ran purchasing, invoicing and the warehouse never heard about them until someone retyped each one. Inventory counts drifted daily.</p>
<p><strong>What we built.</strong> A monitored integration service that syncs orders, stock levels and shipment tracking between the two systems every few minutes, with a small dashboard showing sync status and any records that need human attention.</p>
<p><strong>The result.</strong> Zero manual order entry, inventory accurate across both systems, and tracking numbers back to customers the moment labels are printed.</p>',
  ARRAY['Python', 'PostgreSQL', 'Docker', 'REST APIs'],
  1, false
);

INSERT INTO posts (title, slug, excerpt, body_md, body_html, is_published) VALUES
(
  'Five signs your business has outgrown its spreadsheets',
  'outgrown-spreadsheets',
  'Spreadsheets are where good processes go to hide. Here are the warning signs that yours are costing you real money — and what to do about it.',
  '*This is a sample post — edit or delete it in the admin panel, then publish your own.*

Spreadsheets are brilliant right up until the moment they quietly become your company''s operating system. Here are five signs you''ve crossed that line:

1. **One person owns "the file."** If a single employee''s vacation halts a process, the spreadsheet is a system — an unbacked-up, permission-free system.
2. **You email copies around.** The moment two versions exist, one of them is wrong.
3. **Monday mornings start with copy-paste.** Recurring manual data transfer is the clearest automation target there is.
4. **Formulas nobody dares touch.** Business logic lives in a cell only its author understood — and they left in 2023.
5. **The numbers never quite match.** When the spreadsheet, the accounting system and the warehouse each tell a different story, people stop trusting all three.

None of these need a big-bang ERP project to fix. The usual path is small: pick the most painful workflow, move it into a purpose-built tool with a real database, and connect it to the systems around it.',
  '<p><em>This is a sample post &mdash; edit or delete it in the admin panel, then publish your own.</em></p>
<p>Spreadsheets are brilliant right up until the moment they quietly become your company&rsquo;s operating system. Here are five signs you&rsquo;ve crossed that line:</p>
<ol>
<li><strong>One person owns &ldquo;the file.&rdquo;</strong> If a single employee&rsquo;s vacation halts a process, the spreadsheet is a system &mdash; an unbacked-up, permission-free system.</li>
<li><strong>You email copies around.</strong> The moment two versions exist, one of them is wrong.</li>
<li><strong>Monday mornings start with copy-paste.</strong> Recurring manual data transfer is the clearest automation target there is.</li>
<li><strong>Formulas nobody dares touch.</strong> Business logic lives in a cell only its author understood &mdash; and they left in 2023.</li>
<li><strong>The numbers never quite match.</strong> When the spreadsheet, the accounting system and the warehouse each tell a different story, people stop trusting all three.</li>
</ol>
<p>None of these need a big-bang ERP project to fix. The usual path is small: pick the most painful workflow, move it into a purpose-built tool with a real database, and connect it to the systems around it.</p>',
  false
);
