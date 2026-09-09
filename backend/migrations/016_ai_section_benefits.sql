-- 016_ai_section_benefits.sql
--
-- The homepage AI section explained our architecture instead of answering the
-- only question an owner is asking: what do I get, and what does it cost me?
-- It led with a cascade diagram and four design principles ("AI goes last, not
-- first", "the model only sees the leftovers") -- all true, none of it a reason
-- to buy.
--
-- This rewrites it around the work: the jobs that never reach the top of the
-- list, what they save, what stops the AI going wrong, and why the bill falls
-- rather than climbs. The five-step figure stays, re-labelled as the reason it
-- is cheap to run rather than as a diagram of our design. The Services page
-- carries the same material -- the section's own button links into it -- so it
-- is rewritten to match.
--
-- Guarded on the text live today, so a re-run is a no-op and admin edits stand.

UPDATE content_blocks SET title = $$The jobs that never reach the top of the list$$, body = $$Nine hundred product pages with no descriptions. A drawer of scanned invoices. Three years of transactions to sort. Nobody has a spare month, so it never gets done — and it costs you every month it doesn't. This is the work AI is genuinely good at.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai$$
   AND replace(title, chr(13), '') = $$AI for the jobs that are too big to do by hand$$
   AND md5(replace(body, chr(13), '')) = 'a669c3545c82895b180368a635f5d2b5';

UPDATE content_blocks SET title = $$Why it doesn't cost a fortune to run$$, body = $$Most of your records never reach the AI at all. Cheaper steps handle them first, so you only pay for the hard ones — and there are fewer of those every month.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai_cascade$$
   AND replace(title, chr(13), '') = $$What happens to one record$$
   AND md5(replace(body, chr(13), '')) = '13a02404c24e3dff2140b36f5366bd7e';

UPDATE content_blocks SET title = $$Your rules first$$, subtitle = $$The obvious ones, handled for nothing.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c1$$
   AND replace(title, chr(13), '') = $$Rules$$
   AND replace(subtitle, chr(13), '') = $$Simple rules you can read and change.$$;

UPDATE content_blocks SET title = $$Then what it remembers$$, subtitle = $$Anything you've corrected once, it already knows.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c2$$
   AND replace(title, chr(13), '') = $$Learned memory$$
   AND replace(subtitle, chr(13), '') = $$Everything you've already corrected once.$$;

UPDATE content_blocks SET title = $$Then your own records$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c3$$
   AND replace(title, chr(13), '') = $$Lookups$$;

UPDATE content_blocks SET title = $$AI on the hard ones$$, subtitle = $$Usually a small slice. The only part you pay a model for.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c4$$
   AND replace(title, chr(13), '') = $$AI on what's left$$
   AND replace(subtitle, chr(13), '') = $$The model only sees what's left.$$;

UPDATE content_blocks SET title = $$You have the last word$$, subtitle = $$It shows its reasoning. You say yes, or you don't.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c5$$
   AND replace(title, chr(13), '') = $$A person approves$$
   AND replace(subtitle, chr(13), '') = $$It shows its reasoning. You click yes.$$;

UPDATE content_blocks SET title = $$It won't invent things about your business.$$, body = $$Everything it writes comes out of your own records — your products, your numbers, your search data. If a fact isn't in there, it doesn't reach the page. No made-up specifications, no invented claims for a customer to find.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p1$$
   AND replace(title, chr(13), '') = $$AI goes last, not first.$$
   AND md5(replace(body, chr(13), '')) = '95f03220a21669020d11fa84fc513a27';

UPDATE content_blocks SET title = $$Nothing changes until you say so.$$, body = $$Every suggestion waits for a click, with its reasoning next to it. Your catalog, your prices and your books are never edited by a machine working alone, so a bad suggestion costs you five seconds instead of a week of cleaning up.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p2$$
   AND replace(title, chr(13), '') = $$Nothing saves itself.$$
   AND replace(body, chr(13), '') = $$Suggestions come with a confidence score and a reason, and a person says yes. No model edits your catalog or your books on its own.$$;

UPDATE content_blocks SET title = $$The bill goes down, not up.$$, body = $$It remembers every correction, so it needs to ask the model less often as it goes. Month three costs less than month one for the same work — which is the opposite of how a subscription behaves.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p3$$
   AND replace(title, chr(13), '') = $$It works from your data.$$
   AND md5(replace(body, chr(13), '')) = '3ba951ff835cd5356312c5ded387dc81';

UPDATE content_blocks SET title = $$A bad day at the AI company isn't one at yours.$$, body = $$The AI is the last step, not the foundation. If a model goes down or gets slower, everything else keeps running and you have a few more things to approve by hand. Nothing stops.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p4$$
   AND replace(title, chr(13), '') = $$It gets cheaper as it goes.$$
   AND replace(body, chr(13), '') = $$Every correction is remembered, so fewer records need the model at all. That share drops month after month, and so does the bill.$$;

UPDATE content_blocks SET title = $$What we've actually put it on$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai_apps$$
   AND replace(title, chr(13), '') = $$What it does today$$;

UPDATE content_blocks SET title = $$Product pages written for you.$$, body = $$Titles, descriptions and image text across thousands of products, written from what people actually search for — not from guesswork.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a1$$
   AND replace(title, chr(13), '') = $$Catalog copy, at scale.$$
   AND replace(body, chr(13), '') = $$Titles, descriptions and image alt text across thousands of products, written from your real search data.$$;

UPDATE content_blocks SET title = $$Paperwork typed up for you.$$, body = $$Supplier statements, invoices and scanned PDFs turned into rows you can use, including the ones that arrive as a photo of a page.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a2$$
   AND replace(title, chr(13), '') = $$Documents turned into data.$$
   AND replace(body, chr(13), '') = $$Statements, invoices and scanned PDFs read, sorted and filed — including the ones that arrive as a photo of a page.$$;

UPDATE content_blocks SET title = $$Endless sorting, done once.$$, body = $$Transactions, products and tickets filed automatically. Correct one and it stops asking you about that merchant for good.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a3$$
   AND replace(title, chr(13), '') = $$Sorting that learns.$$
   AND replace(body, chr(13), '') = $$Transactions, products and tickets sorted automatically, and corrected once instead of every month.$$;

UPDATE content_blocks SET title = $$Getting found when customers ask an AI.$$, body = $$Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change it.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a4$$
   AND replace(title, chr(13), '') = $$Showing up in AI search.$$
   AND replace(body, chr(13), '') = $$Whether the assistants your customers now ask are recommending you, and what it takes to change that.$$;

UPDATE content_blocks SET title = $$Two of them, running now$$, body = $$And if a rule would solve your problem, we'll write the rule and charge you less. A good deal of what gets sold as AI is a lookup table with a subscription attached.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai_proof$$
   AND replace(title, chr(13), '') = $$Already running for clients$$
   AND replace(body, chr(13), '') = $$If a rule solves your problem, we write the rule and charge you less.$$;

UPDATE content_blocks SET title = $$See how it works$$, updated_at = now()
 WHERE group_key = $$home_ai_buttons$$ AND block_key = $$b1$$
   AND replace(title, chr(13), '') = $$How we approach AI$$;


-- The same material on the Services page.
UPDATE services SET summary = $$Put AI on the work that's too big to do by hand — product copy, paperwork, endless sorting — with a person approving anything it changes.$$, body_md = $$Most AI pitches start with the model. We start with the job, and with what it costs you when the answer is wrong.

The work worth pointing it at is the work that never gets done: too big for the hours you have, too varied to write rules for. Nine hundred product pages with no descriptions. A drawer of scanned invoices. Three years of transactions nobody has sorted.

Anything a plain rule can still handle, a rule keeps handling. It's faster, it's cheaper, and it can't surprise you.

### What we've actually put it on

- **Product pages written for you.** Titles, descriptions and image text across thousands of products, written from what people actually search for, and scored before and after so you can see it worked.
- **Paperwork typed up for you.** Supplier statements, invoices and scanned PDFs turned into rows you can use — including the ones that arrive as a photo of a page.
- **Endless sorting, done once.** Transactions, products and tickets filed automatically. Correct one and it stops asking you about that merchant for good.
- **Getting found when customers ask an AI.** Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change it.

### What stops it going wrong

**It won't invent things about your business.** Everything it writes comes out of your own records — your products, your numbers, your search data. If a fact isn't in there, it doesn't reach the page. No made-up specifications for a customer to find and no invented claims to answer for.

**Nothing changes until you say so.** Every suggestion waits for a click, with its reasoning beside it. Your catalog, your prices and your books are never edited by a machine working alone. A bad suggestion costs you five seconds instead of a week of cleaning up.

**The bill goes down, not up.** It remembers every correction, so it asks the model less often as it goes. Month three costs less than month one for the same work, which is the opposite of how a subscription behaves.

**A bad day at the AI company isn't one at yours.** The AI runs last, not underneath everything. If a model goes down or slows to a crawl, the rest of the system carries on and you approve a few more things by hand.

### Why it stays affordable

Most of your records never reach the model at all. Your own rules take the obvious ones. What you've already corrected once is remembered. Your catalog and your history answer the next batch. Only what's left — usually a small slice — costs you anything, and that slice shrinks every month.

### What this isn't

We won't sell you a chatbot for your website, and we'll tell you when AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we'll write the rule and charge you less.$$, body_html = $$<p>Most AI pitches start with the model. We start with the job, and with what it costs you when the answer is wrong.</p>
<p>The work worth pointing it at is the work that never gets done: too big for the hours you have, too varied to write rules for. Nine hundred product pages with no descriptions. A drawer of scanned invoices. Three years of transactions nobody has sorted.</p>
<p>Anything a plain rule can still handle, a rule keeps handling. It&rsquo;s faster, it&rsquo;s cheaper, and it can&rsquo;t surprise you.</p>
<h3>What we&rsquo;ve actually put it on</h3>
<ul>
<li><strong>Product pages written for you.</strong> Titles, descriptions and image text across thousands of products, written from what people actually search for, and scored before and after so you can see it worked.</li>
<li><strong>Paperwork typed up for you.</strong> Supplier statements, invoices and scanned PDFs turned into rows you can use — including the ones that arrive as a photo of a page.</li>
<li><strong>Endless sorting, done once.</strong> Transactions, products and tickets filed automatically. Correct one and it stops asking you about that merchant for good.</li>
<li><strong>Getting found when customers ask an AI.</strong> Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change it.</li>
</ul>
<h3>What stops it going wrong</h3>
<p><strong>It won&rsquo;t invent things about your business.</strong> Everything it writes comes out of your own records — your products, your numbers, your search data. If a fact isn&rsquo;t in there, it doesn&rsquo;t reach the page. No made-up specifications for a customer to find and no invented claims to answer for.</p>
<p><strong>Nothing changes until you say so.</strong> Every suggestion waits for a click, with its reasoning beside it. Your catalog, your prices and your books are never edited by a machine working alone. A bad suggestion costs you five seconds instead of a week of cleaning up.</p>
<p><strong>The bill goes down, not up.</strong> It remembers every correction, so it asks the model less often as it goes. Month three costs less than month one for the same work, which is the opposite of how a subscription behaves.</p>
<p><strong>A bad day at the AI company isn&rsquo;t one at yours.</strong> The AI runs last, not underneath everything. If a model goes down or slows to a crawl, the rest of the system carries on and you approve a few more things by hand.</p>
<h3>Why it stays affordable</h3>
<p>Most of your records never reach the model at all. Your own rules take the obvious ones. What you&rsquo;ve already corrected once is remembered. Your catalog and your history answer the next batch. Only what&rsquo;s left — usually a small slice — costs you anything, and that slice shrinks every month.</p>
<h3>What this isn&rsquo;t</h3>
<p>We won&rsquo;t sell you a chatbot for your website, and we&rsquo;ll tell you when AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we&rsquo;ll write the rule and charge you less.</p>$$, updated_at = now()
 WHERE slug = $$optimize-with-ai$$ AND md5(replace(summary, chr(13), '')) = 'a0b60d112aec72cdb68fa2f520d87d69'
   AND md5(replace(body_md, chr(13), '')) = '68af4eb17534408e880cff44282ad457';
