INSERT INTO services (title, slug, summary, body_md, body_html, sort_order, is_published)
SELECT
  'Custom Reports',
  'custom-reports',
  'Reporting systems built on your live data — trends, totals, graphs and profit analysis, delivered as dashboards, scheduled emails or exports.',
  'Your data already holds the answers — sales trends, top products, profit by customer, seasonal patterns. A custom reporting system puts them in front of you without exporting a single spreadsheet.

- Interactive dashboards with trends, totals and period comparisons
- Profit and margin analysis by product, customer or channel
- Graphs that pull live from your ERP, e-commerce and accounting systems
- Scheduled reports delivered to your inbox as PDF or Excel

Built on the systems you already run, so the numbers always match the source — and update themselves.',
  '<p>Your data already holds the answers &mdash; sales trends, top products, profit by customer, seasonal patterns. A custom reporting system puts them in front of you without exporting a single spreadsheet.</p>
<ul>
<li>Interactive dashboards with trends, totals and period comparisons</li>
<li>Profit and margin analysis by product, customer or channel</li>
<li>Graphs that pull live from your ERP, e-commerce and accounting systems</li>
<li>Scheduled reports delivered to your inbox as PDF or Excel</li>
</ul>
<p>Built on the systems you already run, so the numbers always match the source &mdash; and update themselves.</p>',
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM services),
  true
WHERE NOT EXISTS (SELECT 1 FROM services WHERE slug = 'custom-reports');
