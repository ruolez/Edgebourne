-- "Optimize with AI" service. Inserted here rather than in the content seed
-- because 007 only UPDATEs services by slug, which would no-op on a fresh
-- install where this row does not exist yet.
INSERT INTO services (title, slug, summary, body_md, body_html, sort_order, is_published)
VALUES ('Optimize with AI', 'optimize-with-ai', 'Put AI on the work that is too large to do by hand — catalogue copy, document entry, classification — with a person still approving what it changes.', 'Most AI pitches start with the model. We start with the job, and with what it costs when the answer is wrong.

AI belongs on work that is too large to do by hand and too varied to write rules for. Everything a rule can still do, a rule keeps doing — it is faster, cheaper, and it cannot surprise you.

### Where it already earns its place

- **Catalogue copy at scale.** Titles, descriptions and image alt text across thousands of products, written against your real search data rather than guesses, and scored before and after.
- **Documents into data.** Supplier statements, invoices and scanned PDFs read, structured and filed — including the ones that arrive as a photograph of a page.
- **Classification that learns.** Transactions, products and tickets sorted automatically, and corrected once rather than every month.
- **AI search visibility.** Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change that.

### Four rules we build to

**AI runs last, not first.** A cascade of rules, learned memory and lookups handles everything it can. The model only sees what is left over. That is cheaper per record, more predictable, and it means a model outage degrades the system instead of stopping it.

**Nothing commits itself.** Suggestions land as suggestions, with a confidence and a reason, and a person confirms them. Your catalogue, your ledger and your customer records are never edited by a model acting alone.

**It is grounded in your data.** The model is given your actual numbers — search queries, click-through curves, product records, historical categories — not a general impression of your industry. Grounded answers are checkable answers.

**It gets cheaper over time.** Every correction becomes memory. The share of records needing a model at all falls month over month, and so does the bill.

### What this is not

We do not sell a chatbot on your website, and we will say so if AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we will write the rule and charge you less.', '<p>Most AI pitches start with the model. We start with the job, and with what it costs when the answer is wrong.</p>
<p>AI belongs on work that is too large to do by hand and too varied to write rules for. Everything a rule can still do, a rule keeps doing — it is faster, cheaper, and it cannot surprise you.</p>
<h3>Where it already earns its place</h3>
<ul>
<li><strong>Catalogue copy at scale.</strong> Titles, descriptions and image alt text across thousands of products, written against your real search data rather than guesses, and scored before and after.</li>
<li><strong>Documents into data.</strong> Supplier statements, invoices and scanned PDFs read, structured and filed — including the ones that arrive as a photograph of a page.</li>
<li><strong>Classification that learns.</strong> Transactions, products and tickets sorted automatically, and corrected once rather than every month.</li>
<li><strong>AI search visibility.</strong> Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change that.</li>
</ul>
<h3>Four rules we build to</h3>
<p><strong>AI runs last, not first.</strong> A cascade of rules, learned memory and lookups handles everything it can. The model only sees what is left over. That is cheaper per record, more predictable, and it means a model outage degrades the system instead of stopping it.</p>
<p><strong>Nothing commits itself.</strong> Suggestions land as suggestions, with a confidence and a reason, and a person confirms them. Your catalogue, your ledger and your customer records are never edited by a model acting alone.</p>
<p><strong>It is grounded in your data.</strong> The model is given your actual numbers — search queries, click-through curves, product records, historical categories — not a general impression of your industry. Grounded answers are checkable answers.</p>
<p><strong>It gets cheaper over time.</strong> Every correction becomes memory. The share of records needing a model at all falls month over month, and so does the bill.</p>
<h3>What this is not</h3>
<p>We do not sell a chatbot on your website, and we will say so if AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we will write the rule and charge you less.</p>', 5, true)
ON CONFLICT (slug) DO UPDATE SET
  title = EXCLUDED.title, summary = EXCLUDED.summary, body_md = EXCLUDED.body_md,
  body_html = EXCLUDED.body_html, is_published = true, updated_at = now();

-- Keep Custom Reports after it rather than leaving two rows sharing an order.
UPDATE services SET sort_order = 6, updated_at = now() WHERE slug = 'custom-reports';
