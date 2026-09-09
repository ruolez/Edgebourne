-- 015_plain_language.sql
--
-- A pass over every public string on the site, rewritten in plainer, warmer
-- English: shorter sentences, contractions, everyday words in place of trade
-- terms, and American spelling throughout. No claim, figure or timeline
-- changes -- only the wording around them. Client quotes are left untouched:
-- they are attributed to named roles at real companies and are not ours to
-- rephrase.
--
-- Every statement is guarded on the text that is live today, so a re-run is a
-- no-op and anything already edited in the admin is left alone. Short fields are
-- matched in full; long prose is matched on an md5 of the current value, so the
-- old copy does not have to sit in this file beside the new one.


-- ============ Site copy: headings, sections, cards, CTAs ============

UPDATE content_blocks SET title = $$One team for the systems$$, body = $$Four ways to start. Most projects end up using two of them before they're done.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$services$$
   AND replace(title, chr(13), '') = $$One partner for the systems$$
   AND replace(body, chr(13), '') = $$Four ways in. Most engagements use two of them before they are finished.$$;

UPDATE content_blocks SET body = $$Ten of them, written up in full. We name the industry, never the client.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$work$$
   AND replace(body, chr(13), '') = $$Ten of them written up in full. Clients are described by industry, not by name.$$;

UPDATE content_blocks SET body = $$Every project runs the same five steps. You always know what's happening now, what comes next and what it costs — and you can stop after any step and still keep something useful.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$process$$
   AND md5(replace(body, chr(13), '')) = 'e984a0ed611fc71e76fbf557c3ce7ba3';

UPDATE content_blocks SET body = $$Six industries where we've built systems people use every shift. The words change from one to the next. The bottleneck usually doesn't.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$industries$$
   AND replace(body, chr(13), '') = $$Six industries where we have shipped systems that people use every shift. The vocabulary is different; the bottleneck rarely is.$$;

UPDATE content_blocks SET body = $$One senior engineer on your problem, not a bench of juniors learning on your budget.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$about$$
   AND replace(body, chr(13), '') = $$One senior engineer on your problem, not a bench of juniors learning on it.$$;

UPDATE content_blocks SET body = $$One short conversation about what your team still does by hand. No slide deck, no pressure.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$contact$$
   AND replace(body, chr(13), '') = $$One short conversation about what your team does by hand today. No pitch deck, no obligation.$$;

UPDATE content_blocks SET body = $$Short, practical posts about integration, automation and the software smaller companies actually need.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$blog$$
   AND replace(body, chr(13), '') = $$Short, concrete pieces on integration, automation and the software small companies actually need.$$;

UPDATE content_blocks SET body = $$The link might be old, or the page moved.$$, updated_at = now()
 WHERE group_key = $$page_heads$$ AND block_key = $$notfound$$
   AND replace(body, chr(13), '') = $$The link may be old, or the page was moved.$$;

UPDATE content_blocks SET title = $$Software that fits how you already work$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_services$$
   AND replace(title, chr(13), '') = $$Systems that fit the way you work$$;

UPDATE content_blocks SET title = $$AI for the jobs that are too big to do by hand$$, body = $$Anything a plain rule can handle, a rule keeps handling. The model only looks at what's left — and a person still approves whatever it changes.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai$$
   AND replace(title, chr(13), '') = $$AI on the work that is too big to do by hand$$
   AND replace(body, chr(13), '') = $$Everything a rule can still do, a rule keeps doing. The model only sees what is left over — and a person still approves what it changes.$$;

UPDATE content_blocks SET body = $$The bar on each step shows how much is still left to sort out by the time a record gets there. This is an example — your data decides the real split.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai_cascade$$
   AND replace(body, chr(13), '') = $$The bar above each stage is what still needs handling when a record reaches it. Illustrative — the real split depends on your data.$$;

UPDATE content_blocks SET title = $$Already running for clients$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$home_ai_proof$$
   AND replace(title, chr(13), '') = $$Already running in production$$;

UPDATE content_blocks SET title = $$What it costs and how long it takes$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$process_pricing$$
   AND replace(title, chr(13), '') = $$What it costs, and how long it runs$$;

UPDATE content_blocks SET subtitle = $$HOW PROJECTS ARE SHAPED$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$services_shapes$$
   AND replace(subtitle, chr(13), '') = $$HOW ENGAGEMENTS ARE SHAPED$$;

UPDATE content_blocks SET body = $$We'll only use this to write back to you. No mailing list, no newsletter, nothing shared with anyone.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$contact_form$$
   AND replace(body, chr(13), '') = $$We use this only to reply to you. No list, no newsletter, no sharing.$$;

UPDATE content_blocks SET title = $$Built with$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$work_stack$$
   AND replace(title, chr(13), '') = $$Stack$$;

UPDATE content_blocks SET body = $$Tell us what your team still does by hand. We'll tell you what it would take to get rid of it.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$work_side_cta$$
   AND replace(body, chr(13), '') = $$Tell us what your team does by hand today. We'll tell you what it takes to remove it.$$;

UPDATE content_blocks SET body = $$Custom systems for small and mid-size companies. Built on your own servers, documented, and handed over to you.$$, updated_at = now()
 WHERE group_key = $$sections$$ AND block_key = $$footer_note$$
   AND replace(body, chr(13), '') = $$Custom systems for small and mid-size companies. Built on your own infrastructure, documented, and handed over.$$;

UPDATE content_blocks SET items = $$Over 100 systems in production
Runs on your own server
The code is yours$$, updated_at = now()
 WHERE group_key = $$home_proof$$ AND block_key = $$proof$$
   AND replace(items, chr(13), '') = $$Over 100 systems in production
Deployed on your own server
You own the code$$;

UPDATE content_blocks SET subtitle = $$Simple rules you can read and change.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c1$$
   AND replace(subtitle, chr(13), '') = $$Mappings you can read and change.$$;

UPDATE content_blocks SET subtitle = $$Everything you've already corrected once.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c2$$
   AND replace(subtitle, chr(13), '') = $$Every correction you already made.$$;

UPDATE content_blocks SET subtitle = $$Your catalog, your ledger, your history.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c3$$
   AND replace(subtitle, chr(13), '') = $$Your catalogue, ledger and history.$$;

UPDATE content_blocks SET subtitle = $$The model only sees what's left.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c4$$
   AND replace(subtitle, chr(13), '') = $$The model sees only the remainder.$$;

UPDATE content_blocks SET subtitle = $$It shows its reasoning. You click yes.$$, updated_at = now()
 WHERE group_key = $$home_cascade$$ AND block_key = $$c5$$
   AND replace(subtitle, chr(13), '') = $$Confidence and a reason, then a click.$$;

UPDATE content_blocks SET title = $$AI goes last, not first.$$, body = $$Rules, past corrections and simple lookups handle everything they can. The model only sees the leftovers. That's cheaper per record, easier to predict, and if the model has a bad day the system slows down instead of stopping.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p1$$
   AND replace(title, chr(13), '') = $$AI runs last, not first.$$
   AND md5(replace(body, chr(13), '')) = '69bda2226fcbf8b3f0c9f72242a3ef92';

UPDATE content_blocks SET title = $$Nothing saves itself.$$, body = $$Suggestions come with a confidence score and a reason, and a person says yes. No model edits your catalog or your books on its own.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p2$$
   AND replace(title, chr(13), '') = $$Nothing commits itself.$$
   AND md5(replace(body, chr(13), '')) = '26e63b85fcebeb3c86ab09578412a9d5';

UPDATE content_blocks SET title = $$It works from your data.$$, body = $$The model gets your real numbers — your search terms, your click-through, your product records, your past categories. Not a general impression of your industry.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p3$$
   AND replace(title, chr(13), '') = $$Grounded in your data.$$
   AND md5(replace(body, chr(13), '')) = 'fea9aaca973cef0fbeeafeec39762ab5';

UPDATE content_blocks SET title = $$It gets cheaper as it goes.$$, body = $$Every correction is remembered, so fewer records need the model at all. That share drops month after month, and so does the bill.$$, updated_at = now()
 WHERE group_key = $$home_ai_principles$$ AND block_key = $$p4$$
   AND replace(title, chr(13), '') = $$It gets cheaper over time.$$
   AND replace(body, chr(13), '') = $$Every correction becomes memory, so the share of records needing a model at all falls month over month.$$;

UPDATE content_blocks SET title = $$Catalog copy, at scale.$$, body = $$Titles, descriptions and image alt text across thousands of products, written from your real search data.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a1$$
   AND replace(title, chr(13), '') = $$Catalogue copy at scale.$$
   AND replace(body, chr(13), '') = $$Titles, descriptions and image alt text across thousands of products, written against your real search data.$$;

UPDATE content_blocks SET title = $$Documents turned into data.$$, body = $$Statements, invoices and scanned PDFs read, sorted and filed — including the ones that arrive as a photo of a page.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a2$$
   AND replace(title, chr(13), '') = $$Documents into data.$$
   AND replace(body, chr(13), '') = $$Statements, invoices and scanned PDFs read, structured and filed — including the ones that arrive as a photograph.$$;

UPDATE content_blocks SET title = $$Sorting that learns.$$, body = $$Transactions, products and tickets sorted automatically, and corrected once instead of every month.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a3$$
   AND replace(title, chr(13), '') = $$Classification that learns.$$
   AND replace(body, chr(13), '') = $$Transactions, products and tickets sorted automatically, and corrected once rather than every month.$$;

UPDATE content_blocks SET title = $$Showing up in AI search.$$, updated_at = now()
 WHERE group_key = $$home_ai_apps$$ AND block_key = $$a4$$
   AND replace(title, chr(13), '') = $$AI search visibility.$$;

UPDATE content_blocks SET title = $$916 catalog pages, scored and rewritten$$, updated_at = now()
 WHERE group_key = $$home_ai_proof$$ AND block_key = $$r1$$
   AND replace(title, chr(13), '') = $$916 catalogue pages, scored and rewritten$$;

UPDATE content_blocks SET title = $$Statements in, sorted spending out$$, updated_at = now()
 WHERE group_key = $$home_ai_proof$$ AND block_key = $$r2$$
   AND replace(title, chr(13), '') = $$Statements in, categorised spending out$$;

UPDATE content_blocks SET body = $$We follow one record from start to finish and time what it costs you today.$$, updated_at = now()
 WHERE group_key = $$home_process_steps$$ AND block_key = $$s1$$
   AND replace(body, chr(13), '') = $$We follow one record end to end and time what it costs today.$$;

UPDATE content_blocks SET body = $$A working screen you can log into, before we build the real thing.$$, updated_at = now()
 WHERE group_key = $$home_process_steps$$ AND block_key = $$s2$$
   AND replace(body, chr(13), '') = $$A working screen you can log into, before we build the real one.$$;

UPDATE content_blocks SET body = $$On your server, with your data, in one command.$$, updated_at = now()
 WHERE group_key = $$home_process_steps$$ AND block_key = $$s4$$
   AND replace(body, chr(13), '') = $$On your server, in Docker, with your data.$$;

UPDATE content_blocks SET body = $$We stick around for changes, or hand it over clean.$$, updated_at = now()
 WHERE group_key = $$home_process_steps$$ AND block_key = $$s5$$
   AND replace(body, chr(13), '') = $$We stay on for changes, or hand over clean.$$;

UPDATE content_blocks SET subtitle = $$Multi-store stock, pricing, catalog$$, updated_at = now()
 WHERE group_key = $$home_sectors$$ AND block_key = $$retail-ecommerce$$
   AND replace(subtitle, chr(13), '') = $$Multi-store stock, pricing, catalogue$$;

UPDATE content_blocks SET body = $$A real answer from the person who'd do the work, not an auto-reply.$$, updated_at = now()
 WHERE group_key = $$contact_steps$$ AND block_key = $$n1$$
   AND replace(body, chr(13), '') = $$A real answer from the person who would do the work, not an auto-responder.$$;

UPDATE content_blocks SET body = $$You walk us through the slow part. We ask about volumes, systems, and who touches what.$$, updated_at = now()
 WHERE group_key = $$contact_steps$$ AND block_key = $$n2$$
   AND replace(body, chr(13), '') = $$You walk us through the slow part. We ask about volumes, systems and who touches what.$$;

UPDATE content_blocks SET body = $$What we'd build first, what it costs, and an honest note if you don't need us.$$, updated_at = now()
 WHERE group_key = $$contact_steps$$ AND block_key = $$n3$$
   AND replace(body, chr(13), '') = $$What we would build first, what it costs, and an honest note if you do not need us.$$;

UPDATE content_blocks SET body = $$The best spec is an afternoon spent next to the person doing the job by hand.$$, updated_at = now()
 WHERE group_key = $$about_beliefs$$ AND block_key = $$b1$$
   AND replace(body, chr(13), '') = $$The best specification is an afternoon spent next to the person doing the job by hand.$$;

UPDATE content_blocks SET body = $$A system that ships in pieces pays for itself before the last piece is written.$$, updated_at = now()
 WHERE group_key = $$about_beliefs$$ AND block_key = $$b2$$
   AND replace(body, chr(13), '') = $$A system that ships in phases earns its budget back before the last phase is written.$$;

UPDATE content_blocks SET body = $$Everything runs on servers you control, with the code in your own repository.$$, updated_at = now()
 WHERE group_key = $$about_beliefs$$ AND block_key = $$b3$$
   AND replace(body, chr(13), '') = $$Everything runs in Docker on infrastructure you control, with the code in your repository.$$;

UPDATE content_blocks SET title = $$Plain English$$, body = $$Weekly notes an owner can actually read. Jargon usually hides a decision nobody has made yet.$$, updated_at = now()
 WHERE group_key = $$about_beliefs$$ AND block_key = $$b4$$
   AND replace(title, chr(13), '') = $$Plain language$$
   AND replace(body, chr(13), '') = $$Weekly notes an owner can read. Jargon usually hides an unfinished decision.$$;

UPDATE content_blocks SET body = $$Tell us what's eating your team's time. We'll tell you what it takes to fix it.$$, items = $$A 30-minute call. No slide deck, no obligation.
We reply within one business day.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$default$$
   AND replace(body, chr(13), '') = $$Tell us what eats your team's time — we'll tell you what it takes to fix it.$$
   AND replace(items, chr(13), '') = $$A 30-minute call. No deck, no obligation.
We reply within one business day.$$;

UPDATE content_blocks SET body = $$Most of these started as one slow, manual job nobody wanted to own.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$work$$
   AND replace(body, chr(13), '') = $$Most of these started with one slow, manual job nobody wanted to own.$$;

UPDATE content_blocks SET body = $$Map is a small fixed fee. You end up with a written process map and an honest recommendation — including the one where you buy something instead of building it.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$process$$
   AND md5(replace(body, chr(13), '')) = 'a1b4f6007653badc3bfeb001431ab67a';

UPDATE content_blocks SET body = $$The pattern is usually the same. Two systems that don't talk, and a person in the middle retyping.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$industries$$
   AND replace(body, chr(13), '') = $$The pattern is usually the same — two systems that do not talk, and a person in the middle retyping.$$;

UPDATE content_blocks SET body = $$The first call is free, and it usually saves a few wrong turns.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$about$$
   AND replace(body, chr(13), '') = $$The first call costs nothing and usually saves a few wrong turns.$$;

UPDATE content_blocks SET body = $$We've probably seen a version of it before, and we can tell you quickly whether it's worth building.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$work_detail$$
   AND replace(body, chr(13), '') = $$We've probably seen a version of it before — and we can tell you quickly whether it's worth building.$$;

UPDATE content_blocks SET body = $$Tell us what it looks like in your business and we'll say whether it's worth building.$$, updated_at = now()
 WHERE group_key = $$page_cta$$ AND block_key = $$blog_post$$
   AND replace(body, chr(13), '') = $$Tell us what it looks like in your business and we will say whether it is worth building.$$;

UPDATE content_blocks SET body = $$One flat fee covers Map and Prototype. It's deliberately small, so both of us can decide properly before anyone commits to a build.$$, updated_at = now()
 WHERE group_key = $$process_pricing$$ AND block_key = $$r1$$
   AND md5(replace(body, chr(13), '')) = '3d32a869ecc234de500bd3b3c0f2a596';

UPDATE content_blocks SET body = $$We quote the build once the prototype has settled what it actually is. The number you approve is the number you pay.$$, updated_at = now()
 WHERE group_key = $$process_pricing$$ AND block_key = $$r2$$
   AND replace(body, chr(13), '') = $$Build work is quoted once the prototype has settled the scope, which means the number you approve is the number you pay.$$;

UPDATE content_blocks SET body = $$A working prototype in the first week or two, and a system your team is using a week or two after that. Bigger builds that touch several outside systems take longer — the case studies give their real timelines.$$, updated_at = now()
 WHERE group_key = $$process_pricing$$ AND block_key = $$r3$$
   AND md5(replace(body, chr(13), '')) = '899272283fe306132657a735d2aa5d84';

UPDATE content_blocks SET body = $$A small monthly retainer, and you keep the code and the data whether you keep us or not.$$, updated_at = now()
 WHERE group_key = $$process_pricing$$ AND block_key = $$r4$$
   AND replace(body, chr(13), '') = $$A modest monthly retainer, and you keep the code and the data whether or not you keep us.$$;

UPDATE content_blocks SET body = $$Two systems that should already be talking to each other. Usually two to four weeks, fixed price.$$, updated_at = now()
 WHERE group_key = $$services_shapes$$ AND block_key = $$s1$$
   AND replace(body, chr(13), '') = $$Two systems that should already be talking. Usually two to four weeks, fixed price.$$;

UPDATE content_blocks SET body = $$A full application for one part of the business — the floor, the front desk, the client portal.$$, updated_at = now()
 WHERE group_key = $$services_shapes$$ AND block_key = $$s2$$
   AND replace(body, chr(13), '') = $$A full application for one part of the business — the floor, the desk, the portal.$$;

UPDATE content_blocks SET body = $$A monthly arrangement for changes, monitoring and the next phase, without a new contract every time.$$, updated_at = now()
 WHERE group_key = $$services_shapes$$ AND block_key = $$s3$$
   AND replace(body, chr(13), '') = $$A monthly arrangement: changes, monitoring and the next phase, without a new contract each time.$$;

UPDATE content_blocks SET subtitle = $$We learn how you work before we suggest anything.$$, body = $$We sit with the people doing the job and follow one record all the way through — an order, a delivery, a new product. We count the systems it touches, the steps a person does by hand, and the minutes each one takes. Most projects change shape right here, because the expensive problem is rarely the one that got us called.$$, items = $$A written map of how the work flows today
What the current workaround costs you, in real minutes
A scoped recommendation — including the honest answer, if the right move is to buy something instead of build$$, updated_at = now()
 WHERE group_key = $$process_steps$$ AND block_key = $$s1$$
   AND replace(subtitle, chr(13), '') = $$We learn your process before we propose anything.$$
   AND md5(replace(body, chr(13), '')) = '1f8d82ba68033f088ae6dffa80965395'
   AND md5(replace(items, chr(13), '')) = '845bd039366d7ccb4b4d30e706b4ac90';

UPDATE content_blocks SET body = $$We build the smallest version that proves the idea works — usually one workflow, running on real data, on our servers. Your team clicks around in it. Anything we got wrong becomes obvious in a week instead of in month four, which is the whole reason we do it.$$, items = $$A live prototype you can log into and try
An updated scope with a fixed price
A written list of what we got wrong in Map$$, updated_at = now()
 WHERE group_key = $$process_steps$$ AND block_key = $$s2$$
   AND md5(replace(body, chr(13), '')) = 'f4bb0f0da08000ed6e6ec374083b04ad'
   AND replace(items, chr(13), '') = $$A live prototype you can log into and try
A revised scope with a fixed price
A written list of what we got wrong in Map$$;

UPDATE content_blocks SET subtitle = $$Short cycles, working software, no quiet months.$$, body = $$We build in one to two week cycles against the agreed scope, and you see the running system at the end of each one. We write against your real systems from day one, in a sandbox where the vendor gives us one, because integration surprises found late are the main reason software projects run over.$$, items = $$A running system that grows every cycle
A short written update after each cycle
Access to the code from day one$$, updated_at = now()
 WHERE group_key = $$process_steps$$ AND block_key = $$s3$$
   AND replace(subtitle, chr(13), '') = $$Short cycles, working software, no dark months.$$
   AND md5(replace(body, chr(13), '')) = 'ee7e5dd3492ffac8ba8182249a6de88f'
   AND replace(items, chr(13), '') = $$A running system that grows every cycle
A short written update after each cycle
Access to the repository from day one$$;

UPDATE content_blocks SET subtitle = $$One command to install, on your servers or ours.$$, body = $$The system ships as a Docker stack with health checks, database updates that apply themselves on start-up, and a one-line installer for install, update and remove. We run it next to your current process until the numbers agree, then switch over. Then we train your team on the screens they'll actually use.$$, items = $$Live deployment, with the installer and backups set up
A short guide for whoever runs it day to day
A training session, recorded for the next hire$$, updated_at = now()
 WHERE group_key = $$process_steps$$ AND block_key = $$s4$$
   AND replace(subtitle, chr(13), '') = $$One command to install, on your infrastructure or ours.$$
   AND md5(replace(body, chr(13), '')) = '33541c4e370792b18883cb40681f924c'
   AND replace(items, chr(13), '') = $$Production deployment, the installer and backups configured
A short operator guide
A training session recorded for the next hire$$;

UPDATE content_blocks SET subtitle = $$The people who built it are the people who look after it.$$, body = $$Software that talks to other companies' systems needs someone watching it. We keep an eye on what we run, fix what breaks, and stay on top of the platform changes that show up whether you asked for them or not. Most clients keep a small monthly retainer. Some take the code and run it themselves.$$, items = $$Monitoring, and a response time we agree up front
A monthly note on what changed
The option to walk away with everything, any time$$, updated_at = now()
 WHERE group_key = $$process_steps$$ AND block_key = $$s5$$
   AND replace(subtitle, chr(13), '') = $$The people who built it are the people who maintain it.$$
   AND md5(replace(body, chr(13), '')) = '2e7db943eda2cc9ff85732987dac827c'
   AND replace(items, chr(13), '') = $$Monitored services and an agreed response time
A monthly note on what changed
A standing option to walk away with everything$$;

UPDATE content_blocks SET body = $$Your back office was built for a phone-and-fax business, and now it has to feed a storefront, a marketplace and a warehouse. Stock counts drift, because reservations live in one system and sales happen in another. Buying runs on a spreadsheet and somebody's memory of what moved last month. We get the numbers to agree, and give you reorder points you can actually defend.$$, extra = jsonb_set(extra, '{caps}', to_jsonb($$One true sellable-stock number worked out across every channel and pushed on a schedule
Reorder points based on what actually sold, with overrides per product
Barcodes and prices kept in step across several back-office databases$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$distribution-wholesale$$
   AND md5(replace(body, chr(13), '')) = '2701e2869642506a88eb72b95873271e'
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = 'e6361c328ae8c94c2cda61e990e588c5';

UPDATE content_blocks SET body = $$Every new product means the same details typed into six places, and every one of them is a chance to get it wrong. Prices and barcodes disagree between stores. A unit reserved on one channel is still for sale on another, so you oversell, then hold stock back to cover for it — and that cushion is money sitting still. We give you one place where the truth lives.$$, extra = jsonb_set(jsonb_set(extra, '{caps}', to_jsonb($$Add a product once and it reaches the ERP and every storefront, with images and variants
Listings hidden and brought back automatically as stock runs out and returns
AI-assisted catalog SEO, with a person approving every published change$$::text)), '{cases}', to_jsonb($$product-onboarding-automation | Add a product once, everywhere
realtime-inventory-sync | Stop overselling across every storefront
ai-seo-catalog | 916 catalog pages, scored and rewritten$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$retail-ecommerce$$
   AND md5(replace(body, chr(13), '')) = '9267bf2d4cdfa51412aae8e092ce4e96'
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = '10e1f5eac0dc7eb28a815a267177241b'
   AND md5(replace(extra->>$$cases$$, chr(13), '')) = '4dee0bac2c622b585f6c08fa047747d9';

UPDATE content_blocks SET body = $$The floor runs on paper and on the two people who know how it really works. A short delivery turns up weeks later, when somebody checks the books. Nobody can say who packed the order that went out wrong. And counts happen once a year, because they take the building offline. We put a scanner into the workflow, and a record behind every scan.$$, items = $$The floor runs on paper and on two people's memory
Short deliveries found weeks later, when the books are checked
Counts once a year, because they take the building offline$$, extra = jsonb_set(extra, '{caps}', to_jsonb($$Scan deliveries against the purchase order right at the door
Bin and slot tracking, with quantities adjusted in the aisle
A name on every pack, and cycle counts done on a phone$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$warehousing-3pl$$
   AND md5(replace(body, chr(13), '')) = '906ee1302a4e82abed5300e6dece5302'
   AND md5(replace(items, chr(13), '')) = '656942c7a044cbb575ba73bd27b35301'
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = '4308985d64754c02975b386580a68e82';

UPDATE content_blocks SET body = $$The work is billable and the admin isn't, but the admin is what fills the evenings — chasing statuses, rebuilding the same report, retyping a client's details into the third system this week. And your website is a request to an agency who take a fortnight and charge for a paragraph. We take the admin off your hands and give you the keys to the site.$$, items = $$Evenings spent on admin nobody can bill for
The same report rebuilt by hand every month
Two weeks and an invoice to change one paragraph$$, extra = jsonb_set(extra, '{caps}', to_jsonb($$Client portals and intake forms that create the record without a phone call
Reports and documents that build themselves from live data, on a schedule
Websites with a real admin, so your team edits pages, images and menus$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$professional-services$$
   AND md5(replace(body, chr(13), '')) = '8c7463b074f25b215fa5317a1c00feb7'
   AND replace(items, chr(13), '') = $$Evenings spent on admin nobody can bill
The same report rebuilt by hand every month
A fortnight and an invoice to change one paragraph$$
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = 'f29ad585bb46c1d642f75564bc13ba5a';

UPDATE content_blocks SET body = $$Intake is a clipboard, a phone call and a spreadsheet, and the first honest answer a potential client gets about their case is weeks away. Leads go cold in an inbox. Nobody can say what stage a matter is at without asking someone. And changing one intake question means a developer ticket. We make intake self-service and the pipeline something you can see.$$, extra = jsonb_set(extra, '{caps}', to_jsonb($$Guided questionnaires with no login, that give an honest range on the spot
Leads that become tracked cases, moving through named stages with email updates
Drag-and-drop question and template editing, with no developer involved$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$legal$$
   AND md5(replace(body, chr(13), '')) = 'b322c907d6bb26c69197446ec858c584'
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = '6dff41ae41053d0eb93b9eab01c314f8';

UPDATE content_blocks SET body = $$Statements arrive as a CSV from one bank, a spreadsheet from another and a scanned PDF from the third, and somebody spends a day a month turning them into rows. Sorting starts from scratch every period, because nothing remembers what you decided last time. Matching it all up is a game of spot-the-duplicate. We take the typing away and leave the judgment with you.$$, items = $$A CSV from one bank, a spreadsheet from the next, a scan from the third
A day a month spent turning statements into rows
Sorting started from scratch every single period$$, extra = jsonb_set(jsonb_set(extra, '{caps}', to_jsonb($$CSV, spreadsheet and scanned-PDF statements imported, with the bank recognized automatically
Sorting that learns from your corrections, and AI suggestions that are never applied on their own
Duplicates caught in the preview, before anything is saved$$::text)), '{cases}', to_jsonb($$statement-intelligence | Statements in, sorted spending out
owner-editable-website | Websites the owner can actually edit$$::text)), updated_at = now()
 WHERE group_key = $$industries_sectors$$ AND block_key = $$finance-accounting$$
   AND md5(replace(body, chr(13), '')) = '7b38e573046a205abdd08238cb4d159c'
   AND md5(replace(items, chr(13), '')) = 'c1eba917f04deebd548132e3d89c303f'
   AND md5(replace(extra->>$$caps$$, chr(13), '')) = '0f08a022160680f0771438dbf2f51deb'
   AND replace(extra->>$$cases$$, chr(13), '') = $$statement-intelligence | Statements in, categorised spending out
owner-editable-website | Websites the owner can actually edit$$;


-- ============ Services ============

UPDATE services SET summary = $$Internal tools, portals and dashboards for the desk, and scan stations for the warehouse floor. One system, shaped around how your company already works.$$, body_md = $$Off-the-shelf software makes your team work its way. We do the opposite: we build software shaped around the way your company already works, running on your own servers, using your own data.

Some of that happens at a desk. Some of it happens at a receiving door, with a scanner in one hand. It's the same system either way, and that's the point — the moment the floor gets its own separate tool, the numbers start to disagree.

### At the desk

- One screen instead of the six-system copy-and-paste job every time you add a product
- A buying tool that works out reorder points from what actually sold, instead of gut feel
- A statement importer that reads spreadsheets, CSVs and scanned PDFs and sorts the lines for you
- A client intake form with no login, that turns a finished questionnaire into a tracked account
- Dashboards that read live from the systems you already run

### On the floor

- Scan-and-check for incoming deliveries, so a short shipment is caught at the door instead of at month end
- Bin and shelf tracking, with quantities adjusted right there in the aisle
- Two-scan pack and check stations, with every scan tied to the person who made it
- Cycle counts on a phone, written to a proper record instead of a clipboard

### How they're built

Whatever suits the job. Your existing database or a new one. Docker, a one-line installer, and updates that apply themselves.

The floor tools are ordinary web apps, not phone apps — so there's no app store, no device enrollment, and no worrying about which handheld is running an old version. They run on the scanners and phones you already own, and an update is a page refresh.

Where they need a login, they check against the staff list already in your ERP. A new hire is added once, in the place your team already manages people. Someone switched off there loses floor access immediately. Every change carries a name and a time, so you can always see who did what.

You get the code, the installer, and documentation your next hire can actually read.

Have a look at the [warehouse floor suite](/work/warehouse-floor-suite) for four of these running in one building.$$, body_html = $$<p>Off-the-shelf software makes your team work its way. We do the opposite: we build software shaped around the way your company already works, running on your own servers, using your own data.</p>
<p>Some of that happens at a desk. Some of it happens at a receiving door, with a scanner in one hand. It&rsquo;s the same system either way, and that&rsquo;s the point — the moment the floor gets its own separate tool, the numbers start to disagree.</p>
<h3>At the desk</h3>
<ul>
<li>One screen instead of the six-system copy-and-paste job every time you add a product</li>
<li>A buying tool that works out reorder points from what actually sold, instead of gut feel</li>
<li>A statement importer that reads spreadsheets, CSVs and scanned PDFs and sorts the lines for you</li>
<li>A client intake form with no login, that turns a finished questionnaire into a tracked account</li>
<li>Dashboards that read live from the systems you already run</li>
</ul>
<h3>On the floor</h3>
<ul>
<li>Scan-and-check for incoming deliveries, so a short shipment is caught at the door instead of at month end</li>
<li>Bin and shelf tracking, with quantities adjusted right there in the aisle</li>
<li>Two-scan pack and check stations, with every scan tied to the person who made it</li>
<li>Cycle counts on a phone, written to a proper record instead of a clipboard</li>
</ul>
<h3>How they&rsquo;re built</h3>
<p>Whatever suits the job. Your existing database or a new one. Docker, a one-line installer, and updates that apply themselves.</p>
<p>The floor tools are ordinary web apps, not phone apps — so there&rsquo;s no app store, no device enrollment, and no worrying about which handheld is running an old version. They run on the scanners and phones you already own, and an update is a page refresh.</p>
<p>Where they need a login, they check against the staff list already in your ERP. A new hire is added once, in the place your team already manages people. Someone switched off there loses floor access immediately. Every change carries a name and a time, so you can always see who did what.</p>
<p>You get the code, the installer, and documentation your next hire can actually read.</p>
<p>Have a look at the <a href="/work/warehouse-floor-suite">warehouse floor suite</a> for four of these running in one building.</p>$$, updated_at = now()
 WHERE slug = $$custom-web-apps$$ AND md5(replace(summary, chr(13), '')) = 'd7b1aa9d2952538a18427cd21472815c'
   AND md5(replace(body_md, chr(13), '')) = '6eef4fe49dfc4060a481ff6f6e9dc3ca';

UPDATE services SET summary = $$Get the systems you already pay for to swap data on their own — orders, stock, prices, tracking — with retries, logs and nobody retyping anything.$$, body_md = $$Most companies don't need new software. They need the software they already have to talk to each other. We build the piece in the middle that moves the records a person is currently carrying by hand.

**Things we've connected**

- Two back-office databases and a Shopify store, worked into one true stock number and pushed on a schedule
- Orders pulled from Shopify and from an invoicing system into one shipping desk, with tracking written back to both
- Barcodes and prices kept identical across several back offices and several storefronts at once
- A new product entered once and delivered to the ERP and the store, with images, variants and per-store pricing

**Why ours keep running**

Sending the same value twice leaves the same result, so a retry can never corrupt a count. We plan for the limits a platform puts on how often you can call it, instead of finding out the hard way. And anything that costs money is ordered carefully: the step you can't undo happens first, and everything after it can be retried on its own. Buying a shipping label never depends on some other system being up at that moment.

Everything that moves gets written down. So "why did this change at 3pm?" is a ten-second answer instead of an argument.$$, body_html = $$<p>Most companies don&rsquo;t need new software. They need the software they already have to talk to each other. We build the piece in the middle that moves the records a person is currently carrying by hand.</p>
<p><strong>Things we&rsquo;ve connected</strong></p>
<ul>
<li>Two back-office databases and a Shopify store, worked into one true stock number and pushed on a schedule</li>
<li>Orders pulled from Shopify and from an invoicing system into one shipping desk, with tracking written back to both</li>
<li>Barcodes and prices kept identical across several back offices and several storefronts at once</li>
<li>A new product entered once and delivered to the ERP and the store, with images, variants and per-store pricing</li>
</ul>
<p><strong>Why ours keep running</strong></p>
<p>Sending the same value twice leaves the same result, so a retry can never corrupt a count. We plan for the limits a platform puts on how often you can call it, instead of finding out the hard way. And anything that costs money is ordered carefully: the step you can&rsquo;t undo happens first, and everything after it can be retried on its own. Buying a shipping label never depends on some other system being up at that moment.</p>
<p>Everything that moves gets written down. So &ldquo;why did this change at 3pm?&rdquo; is a ten-second answer instead of an argument.</p>$$, updated_at = now()
 WHERE slug = $$systems-integration$$ AND replace(summary, chr(13), '') = $$Make the systems you already pay for exchange data by themselves — orders, stock, prices, tracking — with retries, logging and no retyping.$$
   AND md5(replace(body_md, chr(13), '')) = '15cbcde34f03c3f07c43efed44480849';

UPDATE services SET summary = $$Get rid of the work that comes back every week — matching numbers, reordering, reporting, paperwork — and give those hours back to your team.$$, body_md = $$Every business has jobs that eat hours and add nothing: the Monday report, the reorder spreadsheet, the copy-paste between two screens, the chase for a status update. Those are the things worth automating, and they're usually the cheapest work we do.

**Automations already running**

- Reorder levels worked out from what actually sold, with overrides per product, exported as a spreadsheet or PDF the supplier can read
- Bank and card statements pulled in from CSVs, spreadsheets and scanned PDFs, sorted using what you corrected last time
- Catalog pages scored against clear rules and rewritten by AI, with a person approving every change before it goes live
- Listings hidden and brought back automatically as stock runs out and returns

**Where the judgment stays**

Automation is only worth trusting if it knows what it doesn't know. Ours suggest rather than decide anywhere a mistake would be expensive. An AI-written product description is a suggestion until someone approves it. An unusual reorder quantity gets flagged instead of sent. You trust it because you can see how it got there.

We start with the one job costing your team the most hours, automate it end to end, and only move on once it's been boring for a month.$$, body_html = $$<p>Every business has jobs that eat hours and add nothing: the Monday report, the reorder spreadsheet, the copy-paste between two screens, the chase for a status update. Those are the things worth automating, and they&rsquo;re usually the cheapest work we do.</p>
<p><strong>Automations already running</strong></p>
<ul>
<li>Reorder levels worked out from what actually sold, with overrides per product, exported as a spreadsheet or PDF the supplier can read</li>
<li>Bank and card statements pulled in from CSVs, spreadsheets and scanned PDFs, sorted using what you corrected last time</li>
<li>Catalog pages scored against clear rules and rewritten by AI, with a person approving every change before it goes live</li>
<li>Listings hidden and brought back automatically as stock runs out and returns</li>
</ul>
<p><strong>Where the judgment stays</strong></p>
<p>Automation is only worth trusting if it knows what it doesn&rsquo;t know. Ours suggest rather than decide anywhere a mistake would be expensive. An AI-written product description is a suggestion until someone approves it. An unusual reorder quantity gets flagged instead of sent. You trust it because you can see how it got there.</p>
<p>We start with the one job costing your team the most hours, automate it end to end, and only move on once it&rsquo;s been boring for a month.</p>$$, updated_at = now()
 WHERE slug = $$business-automation$$ AND replace(summary, chr(13), '') = $$Remove the recurring work entirely — reconciliation, reordering, reporting, document generation — and give the hours back to your team.$$
   AND md5(replace(body_md, chr(13), '')) = '973994d39cb90890d3bb8147886fa45e';

UPDATE services SET summary = $$Point AI at the work that's too big to do by hand — catalog copy, typing up documents, sorting — with a person still approving whatever it changes.$$, body_md = $$Most AI pitches start with the model. We start with the job, and with what it costs you when the answer is wrong.

AI belongs on work that's too big to do by hand and too varied to write rules for. Anything a rule can still handle, a rule keeps handling. It's faster, it's cheaper, and it can't surprise you.

### Where it already earns its keep

- **Catalog copy, at scale.** Titles, descriptions and image alt text across thousands of products, written from your real search data rather than guesswork, and scored before and after.
- **Documents turned into data.** Supplier statements, invoices and scanned PDFs read, sorted and filed — including the ones that arrive as a photo of a page.
- **Sorting that learns.** Transactions, products and tickets sorted automatically, and corrected once instead of every month.
- **Showing up in AI search.** Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change it.

### Four rules we build to

**AI goes last, not first.** Rules, past corrections and simple lookups handle everything they can. The model only sees the leftovers. That's cheaper per record, easier to predict, and it means a model having a bad day slows the system down instead of stopping it.

**Nothing saves itself.** Suggestions arrive as suggestions, with a confidence score and a reason, and a person confirms them. Your catalog, your books and your customer records are never edited by a model working alone.

**It works from your data.** The model gets your real numbers — your search terms, your click-through, your product records, your past categories. Not a general impression of your industry. Answers you can check are answers you can use.

**It gets cheaper as it goes.** Every correction is remembered. Fewer records need the model at all as the months go by, and the bill follows.

### What this isn't

We won't sell you a chatbot for your website, and we'll say so if AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we'll write the rule and charge you less.$$, body_html = $$<p>Most AI pitches start with the model. We start with the job, and with what it costs you when the answer is wrong.</p>
<p>AI belongs on work that&rsquo;s too big to do by hand and too varied to write rules for. Anything a rule can still handle, a rule keeps handling. It&rsquo;s faster, it&rsquo;s cheaper, and it can&rsquo;t surprise you.</p>
<h3>Where it already earns its keep</h3>
<ul>
<li><strong>Catalog copy, at scale.</strong> Titles, descriptions and image alt text across thousands of products, written from your real search data rather than guesswork, and scored before and after.</li>
<li><strong>Documents turned into data.</strong> Supplier statements, invoices and scanned PDFs read, sorted and filed — including the ones that arrive as a photo of a page.</li>
<li><strong>Sorting that learns.</strong> Transactions, products and tickets sorted automatically, and corrected once instead of every month.</li>
<li><strong>Showing up in AI search.</strong> Whether the assistants your customers now ask are recommending you, what they say when they do, and what it takes to change it.</li>
</ul>
<h3>Four rules we build to</h3>
<p><strong>AI goes last, not first.</strong> Rules, past corrections and simple lookups handle everything they can. The model only sees the leftovers. That&rsquo;s cheaper per record, easier to predict, and it means a model having a bad day slows the system down instead of stopping it.</p>
<p><strong>Nothing saves itself.</strong> Suggestions arrive as suggestions, with a confidence score and a reason, and a person confirms them. Your catalog, your books and your customer records are never edited by a model working alone.</p>
<p><strong>It works from your data.</strong> The model gets your real numbers — your search terms, your click-through, your product records, your past categories. Not a general impression of your industry. Answers you can check are answers you can use.</p>
<p><strong>It gets cheaper as it goes.</strong> Every correction is remembered. Fewer records need the model at all as the months go by, and the bill follows.</p>
<h3>What this isn&rsquo;t</h3>
<p>We won&rsquo;t sell you a chatbot for your website, and we&rsquo;ll say so if AI is the wrong tool. A good deal of what gets pitched as AI is a lookup table with a subscription attached. If a rule solves your problem, we&rsquo;ll write the rule and charge you less.</p>$$, updated_at = now()
 WHERE slug = $$optimize-with-ai$$ AND md5(replace(summary, chr(13), '')) = '12cbc5b912c12fa483359e568c9e2615'
   AND md5(replace(body_md, chr(13), '')) = 'df13d7191a780e2c0b0c9c5ecf950b7d';

UPDATE services SET summary = $$Reporting built on your live data — trends, totals, charts and profit analysis — as dashboards, scheduled emails or exports.$$, body_md = $$Your data already holds the answers: what's selling, which products earn their shelf space, which customers are actually profitable, how the season is going. A reporting system puts all of that in front of you without anyone exporting a spreadsheet.

- Dashboards with trends, totals and period-on-period comparisons
- Profit and margin by product, customer or channel
- Charts that read live from your ERP, your store and your accounting system
- Scheduled reports delivered to your inbox as a PDF or a spreadsheet

Built on the systems you already run, so the numbers always match the source — and keep themselves up to date.$$, body_html = $$<p>Your data already holds the answers: what&rsquo;s selling, which products earn their shelf space, which customers are actually profitable, how the season is going. A reporting system puts all of that in front of you without anyone exporting a spreadsheet.</p>
<ul>
<li>Dashboards with trends, totals and period-on-period comparisons</li>
<li>Profit and margin by product, customer or channel</li>
<li>Charts that read live from your ERP, your store and your accounting system</li>
<li>Scheduled reports delivered to your inbox as a PDF or a spreadsheet</li>
</ul>
<p>Built on the systems you already run, so the numbers always match the source — and keep themselves up to date.</p>$$, updated_at = now()
 WHERE slug = $$custom-reports$$ AND md5(replace(summary, chr(13), '')) = 'ab75827b723ac924ec75d51b24717aa6'
   AND md5(replace(body_md, chr(13), '')) = '324bb057ec9bdef60af1b7edd08a1730';


-- ============ FAQs ============

UPDATE faqs SET answer_md = $$Getting started is one flat fee, and it gets you a written map of how the work flows today plus a scoped recommendation. That's yours whether you carry on or not. The build is then a fixed price per phase, agreed after the prototype has settled what we're actually building, so the number you approve is the number you pay. Ongoing support is a small monthly retainer you can cancel. We don't bill open-ended hours for work we can define.$$, answer_html = $$<p>Getting started is one flat fee, and it gets you a written map of how the work flows today plus a scoped recommendation. That&rsquo;s yours whether you carry on or not. The build is then a fixed price per phase, agreed after the prototype has settled what we&rsquo;re actually building, so the number you approve is the number you pay. Ongoing support is a small monthly retainer you can cancel. We don&rsquo;t bill open-ended hours for work we can define.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = '20956277942a979b0b79720187c36047'
   AND replace(question, chr(13), '') = $$How do you price work?$$;

UPDATE faqs SET answer_md = $$Most systems are in your team's hands within two to four weeks. You get a prototype you can log into in the first week or two, then a running system a cycle or two after that. Small automations often ship in days. Bigger builds touching several outside systems take longer, and the case studies on this site give their real timelines. Either way there are no quiet months — you see working software every week.$$, answer_html = $$<p>Most systems are in your team&rsquo;s hands within two to four weeks. You get a prototype you can log into in the first week or two, then a running system a cycle or two after that. Small automations often ship in days. Bigger builds touching several outside systems take longer, and the case studies on this site give their real timelines. Either way there are no quiet months — you see working software every week.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = 'a9e7a702f8245e861a774fe245d99a24'
   AND replace(question, chr(13), '') = $$How long does a first system take?$$;

UPDATE faqs SET answer_md = $$You do, both of them, outright. You get the code, the installer and the documentation. There's no license, no platform fee, and no clause that makes leaving expensive. It all ships as a standard setup that another developer can pick up and carry on with. Nothing we build needs us to stick around, which is deliberate — it keeps us honest.$$, answer_html = $$<p>You do, both of them, outright. You get the code, the installer and the documentation. There&rsquo;s no license, no platform fee, and no clause that makes leaving expensive. It all ships as a standard setup that another developer can pick up and carry on with. Nothing we build needs us to stick around, which is deliberate — it keeps us honest.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = '3c876c391e83198d4f2d9a227a2631fc'
   AND replace(question, chr(13), '') = $$Who owns the code and the data?$$;

UPDATE faqs SET answer_md = $$That's most of what we do. We've connected back-office databases, Shopify stores, shipping and carrier platforms, payment processors and accounting systems — often several at once, in both directions. Age is rarely the problem. If a system has an API or a database we can read, we can usually work with it. We check exactly that early on, before you commit to anything.$$, answer_html = $$<p>That&rsquo;s most of what we do. We&rsquo;ve connected back-office databases, Shopify stores, shipping and carrier platforms, payment processors and accounting systems — often several at once, in both directions. Age is rarely the problem. If a system has an API or a database we can read, we can usually work with it. We check exactly that early on, before you commit to anything.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = 'f356825ee61fabfaebbdb0efb7eadf1f'
   AND replace(question, chr(13), '') = $$Will this work with the systems we already have?$$;

UPDATE faqs SET answer_md = $$Usually for the better. Often we build the piece that needs specialist integration work and hand it over, or we work alongside someone in-house who knows your business far better than we ever will. We write for whoever comes next by default: standard tools, plain database changes, documented setup. If your developer would rather own it outright, that's a good outcome, not a lost sale.$$, answer_html = $$<p>Usually for the better. Often we build the piece that needs specialist integration work and hand it over, or we work alongside someone in-house who knows your business far better than we ever will. We write for whoever comes next by default: standard tools, plain database changes, documented setup. If your developer would rather own it outright, that&rsquo;s a good outcome, not a lost sale.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = '4ce72eb65142b287b1efe17bbf00875d'
   AND replace(question, chr(13), '') = $$We already have a developer. Does that change anything?$$;

UPDATE faqs SET answer_md = $$The people who built it look after it. Anything that talks to other companies' systems needs someone watching, because those platforms change whether you asked them to or not. A support retainer covers monitoring, fixes, keeping up with those changes, and small improvements — with a response time we agree up front and a monthly note on what changed. You can also take the whole thing in-house. The installer and the docs exist for exactly that.$$, answer_html = $$<p>The people who built it look after it. Anything that talks to other companies&rsquo; systems needs someone watching, because those platforms change whether you asked them to or not. A support retainer covers monitoring, fixes, keeping up with those changes, and small improvements — with a response time we agree up front and a monthly note on what changed. You can also take the whole thing in-house. The installer and the docs exist for exactly that.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = '937e738f9f736979e6cd29b03f2696d9'
   AND replace(question, chr(13), '') = $$What happens after launch?$$;

UPDATE faqs SET answer_md = $$Systems run on your own servers whenever you want them to, and the data stays in your database. Passwords and keys live in config files, never in the code, and they're hidden in every screen. People only see what their role allows, and anything touching stock or money is written down with a name and a time. If the work involves live data we sign an NDA before we start, and we clean up anything used for a demo.$$, answer_html = $$<p>Systems run on your own servers whenever you want them to, and the data stays in your database. Passwords and keys live in config files, never in the code, and they&rsquo;re hidden in every screen. People only see what their role allows, and anything touching stock or money is written down with a name and a time. If the work involves live data we sign an NDA before we start, and we clean up anything used for a demo.</p>$$
 WHERE md5(replace(answer_md, chr(13), '')) = '66331b24aa9d2f68f1a8f37b6bf947cf'
   AND replace(question, chr(13), '') = $$How do you handle our data?$$;

UPDATE faqs SET question = $$What's the best way to start?$$, answer_md = $$Book a call and tell us about the job that costs your team the most hours — the Monday report, the retyping, the count that never adds up. We'll tell you on that call whether it's a fit and roughly what it would take. If it is, we come out and time the current process, then put a scope and a price in writing. No proposal deck, no procurement theater.$$, answer_html = $$<p>Book a call and tell us about the job that costs your team the most hours — the Monday report, the retyping, the count that never adds up. We&rsquo;ll tell you on that call whether it&rsquo;s a fit and roughly what it would take. If it is, we come out and time the current process, then put a scope and a price in writing. No proposal deck, no procurement theater.</p>$$
 WHERE replace(question, chr(13), '') = $$What is the best way to start?$$
   AND md5(replace(answer_md, chr(13), '')) = '4704779bf13d0f3ca3c464650ec38df8'
   AND replace(question, chr(13), '') = $$What is the best way to start?$$;


-- ============ Case studies ============

UPDATE case_studies SET summary = $$Connected an online store to an older back-office system, so orders, stock and tracking numbers now move between them on their own.$$, body_md = $$**The problem.** Orders came in on the website, but the back-office system that ran buying, invoicing and the warehouse never heard about them until somebody retyped each one. Stock counts drifted a little more every day.

**What we built.** A small service that keeps orders, stock levels and tracking numbers in step between the two systems every few minutes, plus a dashboard showing what has synced and anything that needs a person to look at it.

**The result.** No more typing orders in twice, stock that matches in both systems, and tracking numbers reaching customers the moment a label is printed.$$, body_html = $$<p><strong>The problem.</strong> Orders came in on the website, but the back-office system that ran buying, invoicing and the warehouse never heard about them until somebody retyped each one. Stock counts drifted a little more every day.</p>
<p><strong>What we built.</strong> A small service that keeps orders, stock levels and tracking numbers in step between the two systems every few minutes, plus a dashboard showing what has synced and anything that needs a person to look at it.</p>
<p><strong>The result.</strong> No more typing orders in twice, stock that matches in both systems, and tracking numbers reaching customers the moment a label is printed.</p>$$, updated_at = now()
 WHERE slug = $$order-inventory-sync$$ AND md5(replace(summary, chr(13), '')) = '657668fdb581fc88c42af33ca6d93db8'
   AND md5(replace(body_md, chr(13), '')) = 'c3172acf2d309718b8f1774fdb4418d7';

UPDATE case_studies SET problem_lede = $$Two customers bought the last one within an hour of each other, on two different stores, because neither store knew the other had already sold it. Somebody had to phone one of them and apologize.$$, summary = $$Several stores selling out of one warehouse, overselling it daily. We work out one true number from the ERP and push it to every store automatically.$$, body_md = $$### The problem

One warehouse. Several Shopify stores. One person exporting stock out of the ERP and loading it into each store, whenever they got to it.

Everything went wrong in the gap. Something sold on store A was still for sale on store B until the next export, so the last one got sold twice and somebody had to make the apology call. Orders the supplier hadn't actually confirmed were being counted as stock, so the site promised things that might never turn up. Units held on open quotes from the sales floor were invisible to the website. Products marked discontinued in the ERP were still buyable online. And when something sold out, someone had to remember to hide it, then remember again to bring it back when stock arrived.

The team's answer to all of this was to keep a cushion: list less than you actually have. That cushion was stock that could never be sold, held back permanently, to make up for a number nobody trusted.

### What we built

A service that works out the real sellable quantity for every product and pushes it to every store on a schedule, as often as every five minutes.

"Really sellable" is one line of arithmetic, and every part of it earns its place:

```
sellable = max(0, on hand + confirmed orders in - work in progress - already promised)
```

On hand comes from the ERP. Only purchase orders the **supplier has actually confirmed** count toward stock — the rest are still recorded, so a drop in stock is always explainable, but nothing gets sold against them. Quotes in progress are taken off. And "already promised" — units held by orders that haven't shipped yet — is added up across **every** store rather than one at a time, so something reserved anywhere is reserved everywhere. That one decision is what ended the double-sells.

Two details more than earned their keep. Shopify keeps line items marked as reserved forever on orders that get closed without shipping, so those ghost reservations are looked up separately and added back — otherwise stock quietly disappears and never comes back. And every stock update carries a unique tag, so if a batch gets sent twice the quantity can't be applied twice. We also keep an eye on how much of the store's API allowance is left and slow down before the platform throttles us, instead of finding out the hard way.

Products that hit zero get hidden automatically. Products that come back get put back automatically. Nobody has to remember.

### The result

No more hand-built stock files. The number on the website is the number in the warehouse, refreshed as often as the client likes — five minutes is the floor, and most days they run it far more often than the old manual routine ever managed.

The oversell calls stopped. Once they stopped, the safety cushion wasn't needed any more, and that's where the real money was: stock that had been held back permanently became sellable again.

Every product, on every run, writes a full record — fifteen details covering what was on hand, what was confirmed and unconfirmed on order, what was in progress, what was promised, the old number, the new number, and what the system did about it. When a merchandiser asks why an item went out of stock at three in the afternoon, the answer takes ten seconds instead of a meeting.

### Why it holds up

- **Retries can't do damage.** Five attempts with growing gaps between them, throttling respected, and a unique tag on every stock write, so a retry can never corrupt a count.
- **It bends instead of breaking.** A batch that fails falls back to updating items one at a time, so one bad product can't take down the other two hundred and forty-nine. A run that errors still saves everything it learned before it stopped.
- **Built for millions of rows.** Old logs are cleared in small batches with pauses, indexes are built out of the way of start-up, and row counts use database statistics instead of counting the whole table.
- **One command to install, update or remove.** Health checks throughout, database updates that apply themselves and are safe to re-run, and a watchdog that clears any sync stuck for more than fifteen minutes.$$, body_html = $$<h3>The problem</h3>
<p>One warehouse. Several Shopify stores. One person exporting stock out of the ERP and loading it into each store, whenever they got to it.</p>
<p>Everything went wrong in the gap. Something sold on store A was still for sale on store B until the next export, so the last one got sold twice and somebody had to make the apology call. Orders the supplier hadn&rsquo;t actually confirmed were being counted as stock, so the site promised things that might never turn up. Units held on open quotes from the sales floor were invisible to the website. Products marked discontinued in the ERP were still buyable online. And when something sold out, someone had to remember to hide it, then remember again to bring it back when stock arrived.</p>
<p>The team&rsquo;s answer to all of this was to keep a cushion: list less than you actually have. That cushion was stock that could never be sold, held back permanently, to make up for a number nobody trusted.</p>
<h3>What we built</h3>
<p>A service that works out the real sellable quantity for every product and pushes it to every store on a schedule, as often as every five minutes.</p>
<p>&ldquo;Really sellable&rdquo; is one line of arithmetic, and every part of it earns its place:</p>
<pre><code>sellable = max(0, on hand + confirmed orders in - work in progress - already promised)
</code></pre>
<p>On hand comes from the ERP. Only purchase orders the <strong>supplier has actually confirmed</strong> count toward stock — the rest are still recorded, so a drop in stock is always explainable, but nothing gets sold against them. Quotes in progress are taken off. And &ldquo;already promised&rdquo; — units held by orders that haven&rsquo;t shipped yet — is added up across <strong>every</strong> store rather than one at a time, so something reserved anywhere is reserved everywhere. That one decision is what ended the double-sells.</p>
<p>Two details more than earned their keep. Shopify keeps line items marked as reserved forever on orders that get closed without shipping, so those ghost reservations are looked up separately and added back — otherwise stock quietly disappears and never comes back. And every stock update carries a unique tag, so if a batch gets sent twice the quantity can&rsquo;t be applied twice. We also keep an eye on how much of the store&rsquo;s API allowance is left and slow down before the platform throttles us, instead of finding out the hard way.</p>
<p>Products that hit zero get hidden automatically. Products that come back get put back automatically. Nobody has to remember.</p>
<h3>The result</h3>
<p>No more hand-built stock files. The number on the website is the number in the warehouse, refreshed as often as the client likes — five minutes is the floor, and most days they run it far more often than the old manual routine ever managed.</p>
<p>The oversell calls stopped. Once they stopped, the safety cushion wasn&rsquo;t needed any more, and that&rsquo;s where the real money was: stock that had been held back permanently became sellable again.</p>
<p>Every product, on every run, writes a full record — fifteen details covering what was on hand, what was confirmed and unconfirmed on order, what was in progress, what was promised, the old number, the new number, and what the system did about it. When a merchandiser asks why an item went out of stock at three in the afternoon, the answer takes ten seconds instead of a meeting.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Retries can&rsquo;t do damage.</strong> Five attempts with growing gaps between them, throttling respected, and a unique tag on every stock write, so a retry can never corrupt a count.</li>
<li><strong>It bends instead of breaking.</strong> A batch that fails falls back to updating items one at a time, so one bad product can&rsquo;t take down the other two hundred and forty-nine. A run that errors still saves everything it learned before it stopped.</li>
<li><strong>Built for millions of rows.</strong> Old logs are cleared in small batches with pauses, indexes are built out of the way of start-up, and row counts use database statistics instead of counting the whole table.</li>
<li><strong>One command to install, update or remove.</strong> Health checks throughout, database updates that apply themselves and are safe to re-run, and a watchdog that clears any sync stuck for more than fifteen minutes.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$realtime-inventory-sync$$ AND md5(replace(problem_lede, chr(13), '')) = 'be30cfab4504fe51234a8b3324d8fcf3'
   AND md5(replace(summary, chr(13), '')) = '750c8012f29de0282cdeda29f3bf8f40'
   AND md5(replace(body_md, chr(13), '')) = 'd67a87ce6af11ba0bb7a015f84c66d74';

UPDATE case_studies SET problem_lede = $$The packer reads the address off one screen and types it into another, weighs the box and types that in too, compares carrier tabs by eye, then goes back into two systems to paste the tracking number. Per box.$$, summary = $$Packers retyped every address into a carrier website, then retyped tracking back into two systems. Now one scan prices every carrier, buys the label and updates both.$$, body_md = $$### The problem

Orders arrived in two places: a Shopify store and an in-house invoicing system. Shipping happened in a third place — whichever carrier website happened to be open in a browser tab.

So the packer's job was typing. Read the address off one screen, type it into the carrier's site. Weigh the box, read the display, type the weight in. Open two more tabs to compare prices by eye. Buy the label. Click through a print dialog. Then back to the store to mark the order shipped and paste the tracking number, then into the invoicing system to type the tracking number and the shipping cost onto the invoice. Per box — so a three-box order meant doing all of that three times.

The worst part wasn't the minutes. It was not knowing. If a label purchase timed out, nobody could say whether they'd been charged. And afterwards nobody could say which employee bought which label, or what an order had actually cost to ship.

### What we built

One screen. Scan the order barcode and the shipment builds itself, from whichever system the order came from. The scale fills in the weight by itself, waiting for the reading to settle before it trusts it. Prices come back from every carrier account, cheapest first. One click buys it. The label prints. The store is marked shipped and the customer notified, and the invoice gets its tracking number and shipping cost. Set to automatic, that's zero clicks between the scan and the printed label.

The part that took the most care is the order things happen in, because this is a step that spends money. A label purchase is never just retried and hoped for. Every carrier is asked whether a label already exists before we try to buy again, and every purchase carries a reference the carrier can use to spot a repeat. The rule in the code is one label per shipment, maximum. It can't double-charge you.

Then everything after the purchase is kept separate from it. If the store or the invoicing system can't be reached, the shipment simply sits at "label created" with the problem noted, and a retry finishes the job later. A network hiccup can cost you a minute. It can never cost you a paid-for label.

Five carrier platforms sit behind one screen, with as many accounts of each as the client wants. Weights and sizes convert themselves — pounds and inches at the desk, whatever the carrier wants behind the scenes.

### The result

The shipping desk went from four screens to one. Typing addresses is gone, typing weights is gone, and the two systems that used to be updated by hand are now updated by the same click that buys the label.

Voiding a label is a real undo now: it's canceled with the carrier, the shipment is removed from the store, and the invoice fields are cleared — but only if they still hold what the system put there, so a number a person typed afterwards is never wiped out.

Because every label is tied to whoever bought it, the client can finally answer questions they couldn't before: what did we spend on shipping this week, with which carrier, and from which station. End-of-day carrier paperwork, which used to be put together by hand, is now generated in a way that stops two packing stations from claiming the same label.

### Why it holds up

- **Safe with money by design.** Purchases are checked before they're tried again, everything after the purchase retries on its own, and a void only redoes the steps that actually failed.
- **113 automated tests** across the carrier connections, the tagging rules and the write-back logic, all running without needing a database.
- **Twenty tracked database updates** applied in order at start-up, including one that went back and filled in a readable carrier name on every past shipment, so old records still make sense after a carrier is removed.
- **An installer that sizes itself.** It reads how much memory the server has and sets its limits from that, backs up the database before every update, and offers one last backup before it removes anything.$$, body_html = $$<h3>The problem</h3>
<p>Orders arrived in two places: a Shopify store and an in-house invoicing system. Shipping happened in a third place — whichever carrier website happened to be open in a browser tab.</p>
<p>So the packer&rsquo;s job was typing. Read the address off one screen, type it into the carrier&rsquo;s site. Weigh the box, read the display, type the weight in. Open two more tabs to compare prices by eye. Buy the label. Click through a print dialog. Then back to the store to mark the order shipped and paste the tracking number, then into the invoicing system to type the tracking number and the shipping cost onto the invoice. Per box — so a three-box order meant doing all of that three times.</p>
<p>The worst part wasn&rsquo;t the minutes. It was not knowing. If a label purchase timed out, nobody could say whether they&rsquo;d been charged. And afterwards nobody could say which employee bought which label, or what an order had actually cost to ship.</p>
<h3>What we built</h3>
<p>One screen. Scan the order barcode and the shipment builds itself, from whichever system the order came from. The scale fills in the weight by itself, waiting for the reading to settle before it trusts it. Prices come back from every carrier account, cheapest first. One click buys it. The label prints. The store is marked shipped and the customer notified, and the invoice gets its tracking number and shipping cost. Set to automatic, that&rsquo;s zero clicks between the scan and the printed label.</p>
<p>The part that took the most care is the order things happen in, because this is a step that spends money. A label purchase is never just retried and hoped for. Every carrier is asked whether a label already exists before we try to buy again, and every purchase carries a reference the carrier can use to spot a repeat. The rule in the code is one label per shipment, maximum. It can&rsquo;t double-charge you.</p>
<p>Then everything after the purchase is kept separate from it. If the store or the invoicing system can&rsquo;t be reached, the shipment simply sits at &ldquo;label created&rdquo; with the problem noted, and a retry finishes the job later. A network hiccup can cost you a minute. It can never cost you a paid-for label.</p>
<p>Five carrier platforms sit behind one screen, with as many accounts of each as the client wants. Weights and sizes convert themselves — pounds and inches at the desk, whatever the carrier wants behind the scenes.</p>
<h3>The result</h3>
<p>The shipping desk went from four screens to one. Typing addresses is gone, typing weights is gone, and the two systems that used to be updated by hand are now updated by the same click that buys the label.</p>
<p>Voiding a label is a real undo now: it&rsquo;s canceled with the carrier, the shipment is removed from the store, and the invoice fields are cleared — but only if they still hold what the system put there, so a number a person typed afterwards is never wiped out.</p>
<p>Because every label is tied to whoever bought it, the client can finally answer questions they couldn&rsquo;t before: what did we spend on shipping this week, with which carrier, and from which station. End-of-day carrier paperwork, which used to be put together by hand, is now generated in a way that stops two packing stations from claiming the same label.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Safe with money by design.</strong> Purchases are checked before they&rsquo;re tried again, everything after the purchase retries on its own, and a void only redoes the steps that actually failed.</li>
<li><strong>113 automated tests</strong> across the carrier connections, the tagging rules and the write-back logic, all running without needing a database.</li>
<li><strong>Twenty tracked database updates</strong> applied in order at start-up, including one that went back and filled in a readable carrier name on every past shipment, so old records still make sense after a carrier is removed.</li>
<li><strong>An installer that sizes itself.</strong> It reads how much memory the server has and sets its limits from that, backs up the database before every update, and offers one last backup before it removes anything.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$shipping-desk-consolidation$$ AND md5(replace(problem_lede, chr(13), '')) = '91b17f1feff76655b4af943f4db0e966'
   AND md5(replace(summary, chr(13), '')) = '9fe2e65be6a2d9cd57d0dcb8d2db98da'
   AND md5(replace(body_md, chr(13), '')) = 'c2da9e1e0686cde1808f28daca09db92';

UPDATE case_studies SET summary = $$The same product had different barcodes and different prices in every system. One screen now fixes a barcode everywhere at once and sets a price for every channel.$$, body_md = $$### The problem

Several trading companies, each with its own back-office database. Several storefronts sitting on top of them. One physical catalog underneath all of it — and no agreement anywhere about what a given product's barcode actually was.

Changing a barcode meant opening every system and editing it by hand, then finding out that history didn't follow. Quotes, purchase orders, invoices, credit notes, returns and bin locations all kept the old barcode forever. So old invoices pointed at items the catalog could no longer find, and nobody could tie the two together.

Prices were the same story in a different key. A new cost meant re-keying a price ladder into five places, each with its own markup, worked out on a calculator, and getting it identical every time. It was never identical.

And the question the owner most wanted answered — what did we actually sell last month, across all of it — couldn't be answered at all, because the two halves of the business counted differently and neither knew about the other.

### What we built

One screen. Type a barcode, see everywhere it exists, change it once.

Behind that, a search fans out across every connected back office and checks eight tables in each one — the product list plus every kind of paperwork that has ever mentioned that barcode — along with every storefront listing. The stores are checked at the same time rather than one after another, so the wait is however long the slowest system takes, not all of them added up. The change itself is applied in batches, wrapped up so that any error rolls the whole thing back.

The behavior that took longest to get right is the one that matters most day to day. If the new barcode already exists on one storefront, **that one store is skipped** with the reason written down, and every other system still gets the update. Blocking the whole job because of one clash was the original design, and it was wrong. A partial success, reported honestly, is worth far more than an all-or-nothing failure.

There's also a clean-up tool for the mess that already exists. It works through the paperwork tables a thousand rows at a time looking for **orphans** — barcodes that old records point at but the catalog has lost — and repairs them by matching on product ID or description, saving each one as it goes so a single bad record can't undo the rest. Progress streams onto the screen while it runs.

Prices work the same way: one entry, four tiers, every back office and every storefront, with mirror stores following along automatically and a full before-and-after record for each.

### The result

The catalog tells one story. Fixing a barcode takes one action instead of five, and it reaches the old paperwork as well as the current record, which is what makes historic invoices add up again. Price changes are entered once and land everywhere, each at that store's own markup.

Because the system keeps a local copy of storefront orders and customers alongside the back-office invoices, the reporting screens can finally put both halves of the business on one page, using one consistent rule for what counts as a completed sale — in the shop's own time zone, which is the detail that quietly ruins most attempts at this.

It's the longest-running system in our portfolio and it's still growing. That's not a boast about volume. It's what a system looks like when the client keeps finding new things worth asking it.

### Why it holds up

- **Every change is on the record.** Barcode and price updates are grouped under one batch, and each one saves the old value, the new value, where it went, what it touched and — for anything skipped or failed — why. Price history keeps before and after for all four tiers.
- **The health check tells the truth.** It reports how busy the database connections actually are and reports a failure when they're maxed out, so an overloaded system reads as unhealthy instead of just hanging. A watchdog restarts it when that happens.
- **API limits are learned, not guessed.** The storefront connection tracks the allowance the platform reports back, keeps a reserve, and backs off with a bit of randomness so parallel jobs don't all wake up together and get throttled again.
- **Twenty-nine database updates** applied in order on every deploy, safe to re-run, with the data preserved — and one command to install, update or remove the whole thing.$$, body_html = $$<h3>The problem</h3>
<p>Several trading companies, each with its own back-office database. Several storefronts sitting on top of them. One physical catalog underneath all of it — and no agreement anywhere about what a given product&rsquo;s barcode actually was.</p>
<p>Changing a barcode meant opening every system and editing it by hand, then finding out that history didn&rsquo;t follow. Quotes, purchase orders, invoices, credit notes, returns and bin locations all kept the old barcode forever. So old invoices pointed at items the catalog could no longer find, and nobody could tie the two together.</p>
<p>Prices were the same story in a different key. A new cost meant re-keying a price ladder into five places, each with its own markup, worked out on a calculator, and getting it identical every time. It was never identical.</p>
<p>And the question the owner most wanted answered — what did we actually sell last month, across all of it — couldn&rsquo;t be answered at all, because the two halves of the business counted differently and neither knew about the other.</p>
<h3>What we built</h3>
<p>One screen. Type a barcode, see everywhere it exists, change it once.</p>
<p>Behind that, a search fans out across every connected back office and checks eight tables in each one — the product list plus every kind of paperwork that has ever mentioned that barcode — along with every storefront listing. The stores are checked at the same time rather than one after another, so the wait is however long the slowest system takes, not all of them added up. The change itself is applied in batches, wrapped up so that any error rolls the whole thing back.</p>
<p>The behavior that took longest to get right is the one that matters most day to day. If the new barcode already exists on one storefront, <strong>that one store is skipped</strong> with the reason written down, and every other system still gets the update. Blocking the whole job because of one clash was the original design, and it was wrong. A partial success, reported honestly, is worth far more than an all-or-nothing failure.</p>
<p>There&rsquo;s also a clean-up tool for the mess that already exists. It works through the paperwork tables a thousand rows at a time looking for <strong>orphans</strong> — barcodes that old records point at but the catalog has lost — and repairs them by matching on product ID or description, saving each one as it goes so a single bad record can&rsquo;t undo the rest. Progress streams onto the screen while it runs.</p>
<p>Prices work the same way: one entry, four tiers, every back office and every storefront, with mirror stores following along automatically and a full before-and-after record for each.</p>
<h3>The result</h3>
<p>The catalog tells one story. Fixing a barcode takes one action instead of five, and it reaches the old paperwork as well as the current record, which is what makes historic invoices add up again. Price changes are entered once and land everywhere, each at that store&rsquo;s own markup.</p>
<p>Because the system keeps a local copy of storefront orders and customers alongside the back-office invoices, the reporting screens can finally put both halves of the business on one page, using one consistent rule for what counts as a completed sale — in the shop&rsquo;s own time zone, which is the detail that quietly ruins most attempts at this.</p>
<p>It&rsquo;s the longest-running system in our portfolio and it&rsquo;s still growing. That&rsquo;s not a boast about volume. It&rsquo;s what a system looks like when the client keeps finding new things worth asking it.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Every change is on the record.</strong> Barcode and price updates are grouped under one batch, and each one saves the old value, the new value, where it went, what it touched and — for anything skipped or failed — why. Price history keeps before and after for all four tiers.</li>
<li><strong>The health check tells the truth.</strong> It reports how busy the database connections actually are and reports a failure when they&rsquo;re maxed out, so an overloaded system reads as unhealthy instead of just hanging. A watchdog restarts it when that happens.</li>
<li><strong>API limits are learned, not guessed.</strong> The storefront connection tracks the allowance the platform reports back, keeps a reserve, and backs off with a bit of randomness so parallel jobs don&rsquo;t all wake up together and get throttled again.</li>
<li><strong>Twenty-nine database updates</strong> applied in order on every deploy, safe to re-run, with the data preserved — and one command to install, update or remove the whole thing.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$barcode-price-integrity$$ AND md5(replace(summary, chr(13), '')) = '82dd0b80c7d08c0818f18e12bbea2582'
   AND md5(replace(body_md, chr(13), '')) = '0d7dd35d3e7a58ec316a9501b6112018';

UPDATE case_studies SET problem_lede = $$To add one new product, somebody typed the same fifty-eight details into every back office and every storefront, with different category codes in each, and a calculator open for the price ladder.$$, summary = $$Adding one product meant typing 58 details into every system by hand and getting them identical. Now it's one form, and every destination gets its own prices and categories.$$, body_md = $$### The problem

"To add one new product I have to type it into every one of our systems, by hand, and get it identical every time."

A product record has fifty-eight fields. Each back-office company has its own categories, its own manufacturer list and its own units, so four of those fields are different in every system even though it's the same product. Each one also has its own markup, so the price ladder — cost, price, cash and carry, two delivery tiers, list price — was worked out on a calculator for every destination.

Then the same product all over again in each store: title, description, brand, type, tags, search listing, custom fields, collections, variants, weight, stock per location, and publishing to each sales channel. Plus watermarking the photos first.

It took most of an afternoon per product, and the duplicate barcodes it created turned up weeks later.

### What we built

One form. Enter the product, tick the destinations, submit.

Prices are worked out rather than typed. Each destination has its own formulas, and every formula calculates from the base cost you entered — deliberately not from each other. If cost is 100 and the store's rules are cost × 1.05 and price × 1.20, the price is 120, not 126. That one decision — no formula reads another formula's answer — is what makes the numbers explainable to the person who has to defend them, and it's enforced on the server rather than in the browser.

Checks happen before anything is written. Every barcode and product code is checked against every destination — an exact match, and separately a match on the first fourteen characters of the code, because this client's codes share a stem across pack sizes and a stem clash is a real conflict even when the full code differs. A destination that already has the product is skipped with a specific reason while every other destination still gets it. Partial success, reported honestly, beats an all-or-nothing failure.

Two more things removed real hours. **Sibling mode**: give it an existing barcode and three new details, and it copies the whole fifty-eight-field record for each destination, zeroing out the stock and history. That's how "add the sixteen-ounce version of this" stopped being an afternoon. And **bulk import**: upload a supplier spreadsheet, and the system recognizes its columns from forty-four different ways of spelling the headings, matches the categories per destination, and checks every row for duplicates — including duplicates inside the file itself — before writing anything. Imports run in the background with live progress, and every row goes through exactly the same path as a manual entry, so the same checks and the same record-keeping apply.

### The result

Adding a product went from most of an afternoon to one form, with the price ladder worked out per destination instead of on a calculator.

Duplicate barcodes get caught at entry rather than discovered weeks later, and they no longer block the destinations that are fine. Supplier price lists are imported instead of re-keyed row by row.

Every submission — typed or imported — is saved with the full form, the destinations it aimed at, the ones that worked and the ones that didn't, with reasons. The history screen shows a run that reached four of six destinations as **partial**, not as a pass or a fail, because that's what actually happened and the person looking needs to know which two to chase.

### Why it holds up

- **Database updates fix themselves.** They re-run at every start-up rather than trusting a checklist, they take turns so two copies can't clash, and they're written so a failed one can't take the app down.
- **Passwords are encrypted where they're stored.** Back-office logins and store keys are never handed back out by any screen.
- **It bends instead of breaking.** If a store rejects a combined request, it falls back to individual ones and reports which parts failed. If a version of the store's API is retired, it automatically tries the previous two.
- **One command to install, update or remove,** with the data kept across updates and a status screen showing the running version, the destinations set up, and the pricing formulas in use.$$, body_html = $$<h3>The problem</h3>
<p>&ldquo;To add one new product I have to type it into every one of our systems, by hand, and get it identical every time.&rdquo;</p>
<p>A product record has fifty-eight fields. Each back-office company has its own categories, its own manufacturer list and its own units, so four of those fields are different in every system even though it&rsquo;s the same product. Each one also has its own markup, so the price ladder — cost, price, cash and carry, two delivery tiers, list price — was worked out on a calculator for every destination.</p>
<p>Then the same product all over again in each store: title, description, brand, type, tags, search listing, custom fields, collections, variants, weight, stock per location, and publishing to each sales channel. Plus watermarking the photos first.</p>
<p>It took most of an afternoon per product, and the duplicate barcodes it created turned up weeks later.</p>
<h3>What we built</h3>
<p>One form. Enter the product, tick the destinations, submit.</p>
<p>Prices are worked out rather than typed. Each destination has its own formulas, and every formula calculates from the base cost you entered — deliberately not from each other. If cost is 100 and the store&rsquo;s rules are cost × 1.05 and price × 1.20, the price is 120, not 126. That one decision — no formula reads another formula&rsquo;s answer — is what makes the numbers explainable to the person who has to defend them, and it&rsquo;s enforced on the server rather than in the browser.</p>
<p>Checks happen before anything is written. Every barcode and product code is checked against every destination — an exact match, and separately a match on the first fourteen characters of the code, because this client&rsquo;s codes share a stem across pack sizes and a stem clash is a real conflict even when the full code differs. A destination that already has the product is skipped with a specific reason while every other destination still gets it. Partial success, reported honestly, beats an all-or-nothing failure.</p>
<p>Two more things removed real hours. <strong>Sibling mode</strong>: give it an existing barcode and three new details, and it copies the whole fifty-eight-field record for each destination, zeroing out the stock and history. That&rsquo;s how &ldquo;add the sixteen-ounce version of this&rdquo; stopped being an afternoon. And <strong>bulk import</strong>: upload a supplier spreadsheet, and the system recognizes its columns from forty-four different ways of spelling the headings, matches the categories per destination, and checks every row for duplicates — including duplicates inside the file itself — before writing anything. Imports run in the background with live progress, and every row goes through exactly the same path as a manual entry, so the same checks and the same record-keeping apply.</p>
<h3>The result</h3>
<p>Adding a product went from most of an afternoon to one form, with the price ladder worked out per destination instead of on a calculator.</p>
<p>Duplicate barcodes get caught at entry rather than discovered weeks later, and they no longer block the destinations that are fine. Supplier price lists are imported instead of re-keyed row by row.</p>
<p>Every submission — typed or imported — is saved with the full form, the destinations it aimed at, the ones that worked and the ones that didn&rsquo;t, with reasons. The history screen shows a run that reached four of six destinations as <strong>partial</strong>, not as a pass or a fail, because that&rsquo;s what actually happened and the person looking needs to know which two to chase.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Database updates fix themselves.</strong> They re-run at every start-up rather than trusting a checklist, they take turns so two copies can&rsquo;t clash, and they&rsquo;re written so a failed one can&rsquo;t take the app down.</li>
<li><strong>Passwords are encrypted where they&rsquo;re stored.</strong> Back-office logins and store keys are never handed back out by any screen.</li>
<li><strong>It bends instead of breaking.</strong> If a store rejects a combined request, it falls back to individual ones and reports which parts failed. If a version of the store&rsquo;s API is retired, it automatically tries the previous two.</li>
<li><strong>One command to install, update or remove,</strong> with the data kept across updates and a status screen showing the running version, the destinations set up, and the pricing formulas in use.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$product-onboarding-automation$$ AND md5(replace(problem_lede, chr(13), '')) = '3b788ffa5f0911931ae6ab6d70022825'
   AND md5(replace(summary, chr(13), '')) = 'c1090be3c05d0f6899f11cc0a8a600bc'
   AND md5(replace(body_md, chr(13), '')) = '39265443fcbc4f9c4b619ed1ba315ddc';

UPDATE case_studies SET problem_lede = $$A short delivery was found six weeks later, when the books were checked. Nobody could say who packed the order that went out wrong. And the count that would have caught both takes the building offline for a day.$$, summary = $$Receiving, bin locations, packing and counts all ran on paper and memory. Four small scan apps now write straight into the ERP, with a name on every entry.$$, body_md = $$### The problem

Four separate jobs on one warehouse floor, all running on paper, memory, and the two people who knew how it really worked.

**Receiving** was a printed purchase order and a pen. Short deliveries turned up at month end, long after the supplier would credit them. **Bin locations** lived in one person's head, so a new picker walked the aisles hunting for stock the system said was somewhere. **Packing** had no record of who did it, so a badly packed order was a mystery and nobody learned anything from it. **Counting** happened once a year, took the building offline, and produced numbers that were already out of date by the time they were typed in.

Every one of these was the same problem in different clothes: the work happened away from a desk, and the record of it got written down later, by somebody else, from memory.

### What we built

Four small apps, one per job, all writing into the ERP the client already runs.

At **receiving**, the operator opens the purchase order on a tablet and scans the delivery. Case barcodes are matched to their unit barcode and case size automatically, so a pallet of cases doesn't have to be counted in pieces. Over-deliveries are flagged at the door. When every line is done, the session closes itself after a five-second countdown.

**Bin locations** gives a searchable map of what's in which slot, with quick plus and minus buttons for adjustments made in the aisle, and a spreadsheet export for anyone who still wants the list on paper.

The **pack station** is deliberately the simplest thing in the building: tap your name, scan the order. The first scan is the packer signing for it, the second is the checker confirming it, and a third is refused. Two times and a name, written straight into the ERP's own columns.

**Counts** run on a phone. Scan the shelf tag and the screen shows the bin it should be in, how many are already promised to open orders, and what's on the way from suppliers — so the person counting isn't counting blind. Enter cases and loose pieces and the app shows the arithmetic back in plain words before saving. A change bigger than a set threshold stops and asks.

The technical decision worth naming: where these apps have logins, they check against the ERP's own staff list rather than keeping their own. There's no second list of people to maintain, and switching someone off in the ERP locks them out of the floor immediately.

### The result

Problems are caught at the door instead of at month end, while the supplier will still credit them. Every quantity change carries a name and a time, written into the client's own records so it shows up in their existing reporting with no extra work. Counting happens continuously on a phone instead of once a year with the doors shut.

The four apps never talk to each other. They connect through the ERP: the counting screen reads the pack station's times to warn that an item is being picked right now, reads the bin app's data to tell the counter where to look, and reads the receiving app's updates to flag stock that arrived this morning. One source of truth, four windows onto it, and no middleman to go wrong.

### Why it holds up

- **Changes are safe and reversible.** Receiving updates the order line, the order header and the item quantity as one chain. Anything that fails goes into a retry queue rather than vanishing. Every receipt can be undone, and the undo is built to survive a half-finished failure.
- **A second delivery doesn't wipe out the first.** The receiving app records the ERP's starting quantity the first time it touches a line, so a second delivery against the same order adds to what's there instead of replacing it.
- **Clocks are handled on purpose.** Times are pinned to the warehouse's own time zone, and one app takes its time from the database itself so its history lines up exactly with the ERP's.
- **Each app installs, updates and removes with one command,** backing up its data before every update, with health checks and automatic restarts throughout.$$, body_html = $$<h3>The problem</h3>
<p>Four separate jobs on one warehouse floor, all running on paper, memory, and the two people who knew how it really worked.</p>
<p><strong>Receiving</strong> was a printed purchase order and a pen. Short deliveries turned up at month end, long after the supplier would credit them. <strong>Bin locations</strong> lived in one person&rsquo;s head, so a new picker walked the aisles hunting for stock the system said was somewhere. <strong>Packing</strong> had no record of who did it, so a badly packed order was a mystery and nobody learned anything from it. <strong>Counting</strong> happened once a year, took the building offline, and produced numbers that were already out of date by the time they were typed in.</p>
<p>Every one of these was the same problem in different clothes: the work happened away from a desk, and the record of it got written down later, by somebody else, from memory.</p>
<h3>What we built</h3>
<p>Four small apps, one per job, all writing into the ERP the client already runs.</p>
<p>At <strong>receiving</strong>, the operator opens the purchase order on a tablet and scans the delivery. Case barcodes are matched to their unit barcode and case size automatically, so a pallet of cases doesn&rsquo;t have to be counted in pieces. Over-deliveries are flagged at the door. When every line is done, the session closes itself after a five-second countdown.</p>
<p><strong>Bin locations</strong> gives a searchable map of what&rsquo;s in which slot, with quick plus and minus buttons for adjustments made in the aisle, and a spreadsheet export for anyone who still wants the list on paper.</p>
<p>The <strong>pack station</strong> is deliberately the simplest thing in the building: tap your name, scan the order. The first scan is the packer signing for it, the second is the checker confirming it, and a third is refused. Two times and a name, written straight into the ERP&rsquo;s own columns.</p>
<p><strong>Counts</strong> run on a phone. Scan the shelf tag and the screen shows the bin it should be in, how many are already promised to open orders, and what&rsquo;s on the way from suppliers — so the person counting isn&rsquo;t counting blind. Enter cases and loose pieces and the app shows the arithmetic back in plain words before saving. A change bigger than a set threshold stops and asks.</p>
<p>The technical decision worth naming: where these apps have logins, they check against the ERP&rsquo;s own staff list rather than keeping their own. There&rsquo;s no second list of people to maintain, and switching someone off in the ERP locks them out of the floor immediately.</p>
<h3>The result</h3>
<p>Problems are caught at the door instead of at month end, while the supplier will still credit them. Every quantity change carries a name and a time, written into the client&rsquo;s own records so it shows up in their existing reporting with no extra work. Counting happens continuously on a phone instead of once a year with the doors shut.</p>
<p>The four apps never talk to each other. They connect through the ERP: the counting screen reads the pack station&rsquo;s times to warn that an item is being picked right now, reads the bin app&rsquo;s data to tell the counter where to look, and reads the receiving app&rsquo;s updates to flag stock that arrived this morning. One source of truth, four windows onto it, and no middleman to go wrong.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Changes are safe and reversible.</strong> Receiving updates the order line, the order header and the item quantity as one chain. Anything that fails goes into a retry queue rather than vanishing. Every receipt can be undone, and the undo is built to survive a half-finished failure.</li>
<li><strong>A second delivery doesn&rsquo;t wipe out the first.</strong> The receiving app records the ERP&rsquo;s starting quantity the first time it touches a line, so a second delivery against the same order adds to what&rsquo;s there instead of replacing it.</li>
<li><strong>Clocks are handled on purpose.</strong> Times are pinned to the warehouse&rsquo;s own time zone, and one app takes its time from the database itself so its history lines up exactly with the ERP&rsquo;s.</li>
<li><strong>Each app installs, updates and removes with one command,</strong> backing up its data before every update, with health checks and automatic restarts throughout.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$warehouse-floor-suite$$ AND md5(replace(problem_lede, chr(13), '')) = '2166200cbf3a2d46f909fbaa9b199e04'
   AND md5(replace(summary, chr(13), '')) = '8ea9eeaafae685d84f0eb1e49730d90f'
   AND md5(replace(body_md, chr(13), '')) = '08f4b6247690cbf0a84161be4a5c9a5d';

UPDATE case_studies SET problem_lede = $$The reorder level in the system was a number someone typed once, years ago, for a product that sells nothing like it used to. Everyone knew it was wrong, so everyone ignored it and bought from memory instead.$$, summary = $$Buying ran on a reorder number somebody typed in years ago. Now every level comes from what actually sold, and a supplier order is two clicks.$$, body_md = $$### The problem

Buying was a morning of guesswork. Pull an on-hand report. Eyeball what looks low. Try to remember how fast each item actually moves, whether there's already a truck coming with some of it, and whether a customer quote is holding some more. Divide by the case size in your head. Retype the whole lot into a spreadsheet, format it, email it to the supplier — then key the same order into the ERP a second time by hand.

The system did have a reorder level field. It was a number somebody typed in years ago, when the product sold differently, and everybody knew it was wrong. So the real reorder logic lived in the buyer's head, which meant it left the building when he did.

### What we built

A buying screen where the reorder level is worked out rather than remembered.

For every product, the system reads real invoice history over whatever window you pick — thirty, sixty, ninety or a hundred and eighty days — and works out how much sells per day and per month, ignoring voided invoices. The reorder level is one month of that, rounded up.

The trigger isn't just what's on the shelf, and that's the part buyers care about:

```
what you really have = on hand + already ordered - promised to customers
```

Stock already on its way counts. Stock already promised to a customer doesn't. An item only shows up on the buy list when that real figure drops below its level, which is why the list stopped including things that were already handled.

The suggested quantity covers however long you want to cover — usually four weeks — and rounds **up to whole cases**, because ordering 37 units of something that ships in twelves isn't an order anybody can place.

Then the buyer's judgment gets a home. Seven settings per product: pin your own level, fall back to the ERP's number, leave an item out of ordering entirely while still tracking it, override the quantity, set a longer cover period for something slow-moving, fix a unit cost, or just leave a note. That knowledge used to live in one head. Now it survives that person's vacation.

Finishing the order is two clicks: a spreadsheet or PDF the supplier can read, and a real purchase order written straight into the ERP, with product descriptions re-read at the moment of export so the document never goes out with a stale name.

### The result

The buy list comes from what sold, not from a field nobody trusts. Stock already coming in and stock already promised out are both counted before an item is suggested, so the list is short and everything on it is real.

The order leaves the building as a proper supplier document and lands in the ERP as a purchase order, in the same action. The double typing is gone.

Six of the first seven months after launch were spent tuning it against real buying, which is the pattern we like to see: a short build, then a long conversation with the people using it every morning.

### Why it holds up

- **The math is tested.** The sell-through and case-rounding logic has its own tests covering the awkward cases — no sales history, a zero-day span, an item sitting exactly on its level, and date boundaries.
- **Database hiccups retry instead of crashing.** Every ERP query gets three retries at one, two and four seconds, and it tells the difference between a timeout, a lost connection and a genuinely bad query, which fails fast instead of retrying for nothing.
- **Database changes apply themselves,** safely and on start-up, so an update never needs someone to run a script.
- **One command to install, update or remove,** keeping the data across updates and asking before it deletes anything.$$, body_html = $$<h3>The problem</h3>
<p>Buying was a morning of guesswork. Pull an on-hand report. Eyeball what looks low. Try to remember how fast each item actually moves, whether there&rsquo;s already a truck coming with some of it, and whether a customer quote is holding some more. Divide by the case size in your head. Retype the whole lot into a spreadsheet, format it, email it to the supplier — then key the same order into the ERP a second time by hand.</p>
<p>The system did have a reorder level field. It was a number somebody typed in years ago, when the product sold differently, and everybody knew it was wrong. So the real reorder logic lived in the buyer&rsquo;s head, which meant it left the building when he did.</p>
<h3>What we built</h3>
<p>A buying screen where the reorder level is worked out rather than remembered.</p>
<p>For every product, the system reads real invoice history over whatever window you pick — thirty, sixty, ninety or a hundred and eighty days — and works out how much sells per day and per month, ignoring voided invoices. The reorder level is one month of that, rounded up.</p>
<p>The trigger isn&rsquo;t just what&rsquo;s on the shelf, and that&rsquo;s the part buyers care about:</p>
<pre><code>what you really have = on hand + already ordered - promised to customers
</code></pre>
<p>Stock already on its way counts. Stock already promised to a customer doesn&rsquo;t. An item only shows up on the buy list when that real figure drops below its level, which is why the list stopped including things that were already handled.</p>
<p>The suggested quantity covers however long you want to cover — usually four weeks — and rounds <strong>up to whole cases</strong>, because ordering 37 units of something that ships in twelves isn&rsquo;t an order anybody can place.</p>
<p>Then the buyer&rsquo;s judgment gets a home. Seven settings per product: pin your own level, fall back to the ERP&rsquo;s number, leave an item out of ordering entirely while still tracking it, override the quantity, set a longer cover period for something slow-moving, fix a unit cost, or just leave a note. That knowledge used to live in one head. Now it survives that person&rsquo;s vacation.</p>
<p>Finishing the order is two clicks: a spreadsheet or PDF the supplier can read, and a real purchase order written straight into the ERP, with product descriptions re-read at the moment of export so the document never goes out with a stale name.</p>
<h3>The result</h3>
<p>The buy list comes from what sold, not from a field nobody trusts. Stock already coming in and stock already promised out are both counted before an item is suggested, so the list is short and everything on it is real.</p>
<p>The order leaves the building as a proper supplier document and lands in the ERP as a purchase order, in the same action. The double typing is gone.</p>
<p>Six of the first seven months after launch were spent tuning it against real buying, which is the pattern we like to see: a short build, then a long conversation with the people using it every morning.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>The math is tested.</strong> The sell-through and case-rounding logic has its own tests covering the awkward cases — no sales history, a zero-day span, an item sitting exactly on its level, and date boundaries.</li>
<li><strong>Database hiccups retry instead of crashing.</strong> Every ERP query gets three retries at one, two and four seconds, and it tells the difference between a timeout, a lost connection and a genuinely bad query, which fails fast instead of retrying for nothing.</li>
<li><strong>Database changes apply themselves,</strong> safely and on start-up, so an update never needs someone to run a script.</li>
<li><strong>One command to install, update or remove,</strong> keeping the data across updates and asking before it deletes anything.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$demand-driven-purchasing$$ AND md5(replace(problem_lede, chr(13), '')) = 'a34f018addc719633a2423fac4c6b9cd'
   AND md5(replace(summary, chr(13), '')) = '6fc73a8213be5c0b5a7ef8524b450123'
   AND md5(replace(body_md, chr(13), '')) = '235a3a139d244cc9213e9b91005ac43c';

UPDATE case_studies SET title = $$916 catalog pages, scored and rewritten$$, problem_lede = $$Somebody exported the catalog to a spreadsheet, hand-wrote descriptions one product at a time, and gave up around item eighty. Image alt text never got written at all.$$, summary = $$A 900-page catalog nobody could edit by hand. Every page is now scored against clear rules, rewritten by AI, and approved by a person before it goes live.$$, body_md = $$### The problem

Nine hundred and sixteen pages. Seven hundred and eighteen products, a hundred and ninety-two collections, and a handful of pages and articles.

The old job was a spreadsheet or an agency retainer. Export the catalog, look for blank descriptions, sort by title length to find the ones that'll get cut off in search results, hand-write a description, paste it back into the admin one product at a time, and stop somewhere around item eighty. Duplicate page titles were invisible unless somebody built a pivot table — and the worst duplicates, the ones caused by a *blank* title quietly falling back to the product name, were invisible even then. Image alt text never got written. The keyword data sat in one browser tab and the Google data in another, and nobody put the two together.

Meanwhile the store itself was loading the same analytics script twice on every page, and a reviews widget on pages that had no reviews.

### What we built

A system that scores the catalog, ranks what's wrong, fixes it with AI, and pushes the result to the store — with a person approving every published change.

Scoring is spelled out rather than mysterious. Products are scored on four content checks — title length, description length, enough words on the page, and how many images have alt text — plus thirteen keyword checks covering where keywords appear, how often, how the headings are structured, and the web address. Every threshold is a setting you can change, not a number buried in the code, and checks that don't apply are dropped from the total rather than scored as zero, so a product with no images isn't punished for missing alt text.

Twenty named problems are ranked by how much they matter, and each carries two separate limits: which fields the AI is allowed to write, and which failing checks it's allowed to see. Those limits exist because five different problems all rewrite the description, and one shared limit made "fix all" quietly rewrite everything.

The AI works against the store's own verified data, with a list of keywords it must keep so an existing ranking survives the rewrite, and a final check that **strips out any quote it couldn't have taken word for word from what it was given**. The specification table can only contain facts that were provided. Nothing invented gets published.

Two supporting pieces earn their place. Duplicate detection compares the title as it *actually appears*, falling back to the product name when the SEO title is blank, which is the only way to catch the duplicates that matter. And content-gap discovery joins keyword data against thirty days of Google Search Console figures, then checks that it isn't recommending an article that would compete with a page the store already ranks for.

### The result

All 916 pages are scored and re-scored, and the moment an item changes its old score is thrown away, so a re-check never measures against a stale page.

On the store itself, an independent audit showed real, checkable movement. The product page's layout shift dropped from 0.221 to 0.006 — a 97% improvement — taking its performance score from 77 to 86 in a single verified fix. The Lighthouse SEO score is **100 out of 100** on every page type. Overall speed across product, collection and home pages moved from the high seventies into the mid eighties, against a platform minimum of 60.

Google Search Console tells the slower story: 923 of 1,187 submitted pages indexed, average position improved by nearly two places, and the AI-written blog section growing 41% in clicks — the only section growing at all.

### Why it holds up

- **API limits are handled properly.** Throttling arrives dressed up as a success with an error tucked inside it. The system spots that, works out how long to wait from the platform's own numbers, and respects the wait it's told to take, with a thirty-second cap.
- **Only one process runs the scheduled jobs,** decided through the database, so publishing, data pulls and snapshots can't fire twice no matter how many copies are running.
- **Nothing hangs forever.** A job that dies is marked failed rather than left running, stale jobs are swept up, and a failed analysis stops before the paid AI call whose output would be thrown away anyway.
- **69 tests on the core logic** — link classification, media specs, mention linking and candidate selection — deliberately kept free of database and network.$$, body_html = $$<h3>The problem</h3>
<p>Nine hundred and sixteen pages. Seven hundred and eighteen products, a hundred and ninety-two collections, and a handful of pages and articles.</p>
<p>The old job was a spreadsheet or an agency retainer. Export the catalog, look for blank descriptions, sort by title length to find the ones that&rsquo;ll get cut off in search results, hand-write a description, paste it back into the admin one product at a time, and stop somewhere around item eighty. Duplicate page titles were invisible unless somebody built a pivot table — and the worst duplicates, the ones caused by a <em>blank</em> title quietly falling back to the product name, were invisible even then. Image alt text never got written. The keyword data sat in one browser tab and the Google data in another, and nobody put the two together.</p>
<p>Meanwhile the store itself was loading the same analytics script twice on every page, and a reviews widget on pages that had no reviews.</p>
<h3>What we built</h3>
<p>A system that scores the catalog, ranks what&rsquo;s wrong, fixes it with AI, and pushes the result to the store — with a person approving every published change.</p>
<p>Scoring is spelled out rather than mysterious. Products are scored on four content checks — title length, description length, enough words on the page, and how many images have alt text — plus thirteen keyword checks covering where keywords appear, how often, how the headings are structured, and the web address. Every threshold is a setting you can change, not a number buried in the code, and checks that don&rsquo;t apply are dropped from the total rather than scored as zero, so a product with no images isn&rsquo;t punished for missing alt text.</p>
<p>Twenty named problems are ranked by how much they matter, and each carries two separate limits: which fields the AI is allowed to write, and which failing checks it&rsquo;s allowed to see. Those limits exist because five different problems all rewrite the description, and one shared limit made &ldquo;fix all&rdquo; quietly rewrite everything.</p>
<p>The AI works against the store&rsquo;s own verified data, with a list of keywords it must keep so an existing ranking survives the rewrite, and a final check that <strong>strips out any quote it couldn&rsquo;t have taken word for word from what it was given</strong>. The specification table can only contain facts that were provided. Nothing invented gets published.</p>
<p>Two supporting pieces earn their place. Duplicate detection compares the title as it <em>actually appears</em>, falling back to the product name when the SEO title is blank, which is the only way to catch the duplicates that matter. And content-gap discovery joins keyword data against thirty days of Google Search Console figures, then checks that it isn&rsquo;t recommending an article that would compete with a page the store already ranks for.</p>
<h3>The result</h3>
<p>All 916 pages are scored and re-scored, and the moment an item changes its old score is thrown away, so a re-check never measures against a stale page.</p>
<p>On the store itself, an independent audit showed real, checkable movement. The product page&rsquo;s layout shift dropped from 0.221 to 0.006 — a 97% improvement — taking its performance score from 77 to 86 in a single verified fix. The Lighthouse SEO score is <strong>100 out of 100</strong> on every page type. Overall speed across product, collection and home pages moved from the high seventies into the mid eighties, against a platform minimum of 60.</p>
<p>Google Search Console tells the slower story: 923 of 1,187 submitted pages indexed, average position improved by nearly two places, and the AI-written blog section growing 41% in clicks — the only section growing at all.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>API limits are handled properly.</strong> Throttling arrives dressed up as a success with an error tucked inside it. The system spots that, works out how long to wait from the platform&rsquo;s own numbers, and respects the wait it&rsquo;s told to take, with a thirty-second cap.</li>
<li><strong>Only one process runs the scheduled jobs,</strong> decided through the database, so publishing, data pulls and snapshots can&rsquo;t fire twice no matter how many copies are running.</li>
<li><strong>Nothing hangs forever.</strong> A job that dies is marked failed rather than left running, stale jobs are swept up, and a failed analysis stops before the paid AI call whose output would be thrown away anyway.</li>
<li><strong>69 tests on the core logic</strong> — link classification, media specs, mention linking and candidate selection — deliberately kept free of database and network.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$ai-seo-catalog$$ AND replace(title, chr(13), '') = $$916 catalogue pages, scored and rewritten$$
   AND md5(replace(problem_lede, chr(13), '')) = '3fce754138c40abb206f2243bd8f00a7'
   AND md5(replace(summary, chr(13), '')) = '9e6b16ba42250488ba383300adbb6e62'
   AND md5(replace(body_md, chr(13), '')) = '3368d1f684fe186511ab5fae050bd821';

UPDATE case_studies SET body_md = $$### The problem

Intake was a phone call and a clipboard.

Somebody injured calls the firm. A receptionist takes them through thirty-odd questions out loud. They're told an attorney will call back, and they hang up knowing nothing — not what their claim might be worth, not what happens next, not even whether the firm is taking it. A paralegal then retypes the notes, looks up the state's fault rules and filing deadline in a binder, and forms an opinion.

Every "what's happening with my case?" call after that gets answered by hand.

And the questionnaire itself lived in a Word document. Changing a question meant a developer ticket, so it never changed.

### What we built

A guided questionnaire the client fills in with no login at all, ending in a plain-English summary and a rough range — on screen, in seconds, with the reasoning shown.

That range isn't a lookup table. It runs through six stages. First the answers are read into a strict structure. Then that state's own rules are applied — how shared fault works there, the filing deadline, any cap on damages — from a fifty-state table, and the process can stop outright where the law blocks it. Comparable outcomes, an independent judgment stage and a deliberately pessimistic "lowest number we could still defend" stage all run at the same time.

Then, importantly, **every dollar figure is calculated in code, not by a model.** Losses without paperwork are weighted down before anything is multiplied — undocumented medical bills count for half, unreported cash wages don't count at all. In states where sharing fault bars a claim, the range collapses accordingly. The range gets wider the more information is missing, held between five and sixty percent, and the result is rounded to a sensible number. Confidence comes from that width and is stated openly, alongside what pushed the number up, what pulled it down, and what the client could provide to improve the estimate. The whole working is saved for the firm to look at.

The lead becomes a client account through an emailed link, and the case moves through six named stages the client can see: New, Under review, Documents needed, Negotiating, Settled, Closed. Every stage change and every note posted by staff sends an email automatically.

And the questionnaire is now the firm's to change. A partner drags questions into order, groups them onto pages, and splits or merges pages right in the browser. The layout is saved on the questions themselves and written through one carefully checked step, so there's no developer involved and no way to lose a question by dragging it.

### The result

A potential client gets a clear, explained answer in the same sitting instead of waiting for a callback, which is the difference between a lead and a lost one. Intake staff stop transcribing and start reviewing.

The stage of the case is visible to the client, so the "any update?" calls fall away on their own. Every notification that goes out is logged along with what happened to it, so nobody has to wonder whether the client was told.

And the questionnaire is a living document again. Because it can be changed in an afternoon, it does get changed — which is worth more than any single question on it.

### Why it holds up

- **397 automated tests**, weighted towards exactly the parts that must not drift: the damages math, the state-law gates, the pipeline, and the drag-and-drop layout logic.
- **The process heals itself.** A run that goes quiet is failed automatically, so a deployment mid-estimate can't leave a case stuck waiting forever.
- **Security isn't an afterthought.** Strong password hashing, links stored only as fingerprints, seven-day claim links and one-hour password resets, limits on repeated attempts at intake and login, automatic HTTPS and a strict content policy — and the app refuses to start in production on a default password.
- **One command to install, update or remove,** with database changes and starter data applied safely every time.$$, body_html = $$<h3>The problem</h3>
<p>Intake was a phone call and a clipboard.</p>
<p>Somebody injured calls the firm. A receptionist takes them through thirty-odd questions out loud. They&rsquo;re told an attorney will call back, and they hang up knowing nothing — not what their claim might be worth, not what happens next, not even whether the firm is taking it. A paralegal then retypes the notes, looks up the state&rsquo;s fault rules and filing deadline in a binder, and forms an opinion.</p>
<p>Every &ldquo;what&rsquo;s happening with my case?&rdquo; call after that gets answered by hand.</p>
<p>And the questionnaire itself lived in a Word document. Changing a question meant a developer ticket, so it never changed.</p>
<h3>What we built</h3>
<p>A guided questionnaire the client fills in with no login at all, ending in a plain-English summary and a rough range — on screen, in seconds, with the reasoning shown.</p>
<p>That range isn&rsquo;t a lookup table. It runs through six stages. First the answers are read into a strict structure. Then that state&rsquo;s own rules are applied — how shared fault works there, the filing deadline, any cap on damages — from a fifty-state table, and the process can stop outright where the law blocks it. Comparable outcomes, an independent judgment stage and a deliberately pessimistic &ldquo;lowest number we could still defend&rdquo; stage all run at the same time.</p>
<p>Then, importantly, <strong>every dollar figure is calculated in code, not by a model.</strong> Losses without paperwork are weighted down before anything is multiplied — undocumented medical bills count for half, unreported cash wages don&rsquo;t count at all. In states where sharing fault bars a claim, the range collapses accordingly. The range gets wider the more information is missing, held between five and sixty percent, and the result is rounded to a sensible number. Confidence comes from that width and is stated openly, alongside what pushed the number up, what pulled it down, and what the client could provide to improve the estimate. The whole working is saved for the firm to look at.</p>
<p>The lead becomes a client account through an emailed link, and the case moves through six named stages the client can see: New, Under review, Documents needed, Negotiating, Settled, Closed. Every stage change and every note posted by staff sends an email automatically.</p>
<p>And the questionnaire is now the firm&rsquo;s to change. A partner drags questions into order, groups them onto pages, and splits or merges pages right in the browser. The layout is saved on the questions themselves and written through one carefully checked step, so there&rsquo;s no developer involved and no way to lose a question by dragging it.</p>
<h3>The result</h3>
<p>A potential client gets a clear, explained answer in the same sitting instead of waiting for a callback, which is the difference between a lead and a lost one. Intake staff stop transcribing and start reviewing.</p>
<p>The stage of the case is visible to the client, so the &ldquo;any update?&rdquo; calls fall away on their own. Every notification that goes out is logged along with what happened to it, so nobody has to wonder whether the client was told.</p>
<p>And the questionnaire is a living document again. Because it can be changed in an afternoon, it does get changed — which is worth more than any single question on it.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>397 automated tests</strong>, weighted towards exactly the parts that must not drift: the damages math, the state-law gates, the pipeline, and the drag-and-drop layout logic.</li>
<li><strong>The process heals itself.</strong> A run that goes quiet is failed automatically, so a deployment mid-estimate can&rsquo;t leave a case stuck waiting forever.</li>
<li><strong>Security isn&rsquo;t an afterthought.</strong> Strong password hashing, links stored only as fingerprints, seven-day claim links and one-hour password resets, limits on repeated attempts at intake and login, automatic HTTPS and a strict content policy — and the app refuses to start in production on a default password.</li>
<li><strong>One command to install, update or remove,</strong> with database changes and starter data applied safely every time.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$legal-intake-portal$$ AND md5(replace(body_md, chr(13), '')) = 'b581243aa11c772f3f9149901693763b';

UPDATE case_studies SET title = $$Statements in, sorted spending out$$, problem_lede = $$Every bank exports a different shape, one of them only gives you a scan, and somebody spends a day a month turning all of it into rows — then tags the same coffee shop for the four-hundredth time.$$, summary = $$Four banks, four export formats, one of them a scanned PDF. Now they're dropped in, recognized, read, de-duplicated and sorted from what you corrected last time.$$, body_md = $$### The problem

The Sunday-afternoon spreadsheet.

Download twelve months of statements from four banks. Discover that each one lays its columns out differently, that one calls the money-out column "paid out" and another calls it "debit", and that the credit-card statement is a PDF with no export at all — and on the older accounts, a scan of a PDF.

Retype or paste the rows into a sheet. Flip the signs by hand on the card exports, because they list charges as positive. Tag the same coffee shop as Coffee for the four-hundredth time. Import the same month twice by accident and spend an hour working out why the totals moved. And never notice the small subscription you canceled in March that's still billing you.

### What we built

Drop the files in. That's the whole thing.

The importer knows twelve banks — eight American and four Canadian — and works out which one it's looking at by scoring the file against a description of each, rather than a hand-written parser per bank. That description knows the bank's column headings, whether money out is positive or negative, which columns hold amounts and, for PDFs, its logos, line patterns and section headings. When nothing scores well enough, a general-purpose reader takes over with about sixty ways of spelling nine kinds of column, and picks one date format for the whole column rather than guessing row by row. Scanned PDFs are spotted by how little real text they contain — so a scan buried inside an otherwise readable PDF gets caught too — and are read by OCR before parsing, one at a time so it can't swamp the server.

Sorting happens in four passes, and the order is the point:

1. **Your rules** — contains, starts with, equals or a pattern, with amount ranges and per-account scope. Applied straight away.
2. **What it learned from you**, exact match. Applied straight away. Every time you correct something, it remembers.
3. **Near-matches on the merchant name**, at a deliberately strict cutoff so it only matches names that are almost identical, never just a part of one. That rule exists so a ride from a company is never mixed up with a food delivery from the same company.
4. **Built-in hints** — several hundred common merchants, longest match wins.

Only what survives all four gets offered to an AI model, in batches, and **an AI suggestion is never applied on its own**. Suggested rows don't move money in your totals until a person confirms them, and confirming one teaches the memory.

Duplicates are handled by fingerprinting each row along with a counter, so a re-uploaded file or an overlapping statement gets caught while two genuinely identical charges on the same day both survive.

### The result

A day a month of retyping became dropping files into a browser. Statements that couldn't be imported at all before — the scans — now come in like everything else.

The queue is grouped by merchant, so one keystroke sorts thirty rows, and the system remembers it for good. Because the memory and the rules run before any model does, the cost of sorting falls every month instead of staying flat.

Nothing quietly overwrites anything. Every change is recorded, and a suggestion sits there visibly as a suggestion until somebody accepts it.

### Why it holds up

- **409 automated tests** across reading files, sorting, duplicate detection, reporting and the API, plus a separate set run against the live system, including contrast and accessibility checks.
- **Interrupted work picks itself up.** Files are read in the background, a restart waits for that to finish, and anything whose job died is reset on start-up instead of sitting at "processing" forever.
- **The installer sizes itself to the machine,** working out memory limits and database settings from the server it's on, backing up the database and the stored statements before every update, and setting up HTTPS with automatic renewal.
- **Each user's data is walled off** on every single screen and route, and that's checked by the tests rather than assumed.$$, body_html = $$<h3>The problem</h3>
<p>The Sunday-afternoon spreadsheet.</p>
<p>Download twelve months of statements from four banks. Discover that each one lays its columns out differently, that one calls the money-out column &ldquo;paid out&rdquo; and another calls it &ldquo;debit&rdquo;, and that the credit-card statement is a PDF with no export at all — and on the older accounts, a scan of a PDF.</p>
<p>Retype or paste the rows into a sheet. Flip the signs by hand on the card exports, because they list charges as positive. Tag the same coffee shop as Coffee for the four-hundredth time. Import the same month twice by accident and spend an hour working out why the totals moved. And never notice the small subscription you canceled in March that&rsquo;s still billing you.</p>
<h3>What we built</h3>
<p>Drop the files in. That&rsquo;s the whole thing.</p>
<p>The importer knows twelve banks — eight American and four Canadian — and works out which one it&rsquo;s looking at by scoring the file against a description of each, rather than a hand-written parser per bank. That description knows the bank&rsquo;s column headings, whether money out is positive or negative, which columns hold amounts and, for PDFs, its logos, line patterns and section headings. When nothing scores well enough, a general-purpose reader takes over with about sixty ways of spelling nine kinds of column, and picks one date format for the whole column rather than guessing row by row. Scanned PDFs are spotted by how little real text they contain — so a scan buried inside an otherwise readable PDF gets caught too — and are read by OCR before parsing, one at a time so it can&rsquo;t swamp the server.</p>
<p>Sorting happens in four passes, and the order is the point:</p>
<ol>
<li><strong>Your rules</strong> — contains, starts with, equals or a pattern, with amount ranges and per-account scope. Applied straight away.</li>
<li><strong>What it learned from you</strong>, exact match. Applied straight away. Every time you correct something, it remembers.</li>
<li><strong>Near-matches on the merchant name</strong>, at a deliberately strict cutoff so it only matches names that are almost identical, never just a part of one. That rule exists so a ride from a company is never mixed up with a food delivery from the same company.</li>
<li><strong>Built-in hints</strong> — several hundred common merchants, longest match wins.</li>
</ol>
<p>Only what survives all four gets offered to an AI model, in batches, and <strong>an AI suggestion is never applied on its own</strong>. Suggested rows don&rsquo;t move money in your totals until a person confirms them, and confirming one teaches the memory.</p>
<p>Duplicates are handled by fingerprinting each row along with a counter, so a re-uploaded file or an overlapping statement gets caught while two genuinely identical charges on the same day both survive.</p>
<h3>The result</h3>
<p>A day a month of retyping became dropping files into a browser. Statements that couldn&rsquo;t be imported at all before — the scans — now come in like everything else.</p>
<p>The queue is grouped by merchant, so one keystroke sorts thirty rows, and the system remembers it for good. Because the memory and the rules run before any model does, the cost of sorting falls every month instead of staying flat.</p>
<p>Nothing quietly overwrites anything. Every change is recorded, and a suggestion sits there visibly as a suggestion until somebody accepts it.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>409 automated tests</strong> across reading files, sorting, duplicate detection, reporting and the API, plus a separate set run against the live system, including contrast and accessibility checks.</li>
<li><strong>Interrupted work picks itself up.</strong> Files are read in the background, a restart waits for that to finish, and anything whose job died is reset on start-up instead of sitting at &ldquo;processing&rdquo; forever.</li>
<li><strong>The installer sizes itself to the machine,</strong> working out memory limits and database settings from the server it&rsquo;s on, backing up the database and the stored statements before every update, and setting up HTTPS with automatic renewal.</li>
<li><strong>Each user&rsquo;s data is walled off</strong> on every single screen and route, and that&rsquo;s checked by the tests rather than assumed.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$statement-intelligence$$ AND replace(title, chr(13), '') = $$Statements in, categorised spending out$$
   AND md5(replace(problem_lede, chr(13), '')) = 'a8b40b41f59d8db84380c09085371679'
   AND md5(replace(summary, chr(13), '')) = 'facd533fd188db1d8118a93bacceca42'
   AND md5(replace(body_md, chr(13), '')) = 'f1d31c79213c69f6ae081d6ac8c80aa9';

UPDATE case_studies SET summary = $$Two firms paid a developer to change a paragraph. Both now run their own sites — pages, images, menus — and one moves 40 GB of client files too.$$, body_md = $$### The problem

Two firms, one complaint. Every change to the website went through somebody else.

The accounting practice paid a freelancer — or waited three weeks — every time a service description changed, a new staff bio went up, or the menu needed reordering. Enquiries arrived as forwarded emails and got lost in an inbox. The admin login was a password everybody knew.

The production agency had the website problem plus a bigger one: moving footage. A client with forty gigabytes of camera files either bought a cloud storage seat, split the delivery across five transfer links that expired within the week, or drove a hard drive across town. When the browser tab crashed at eighty percent, the whole thing started again. And nobody could remember which client had sent which take.

### What we built

Two sites, one idea: everything that changes regularly should be editable by the people who own it.

The accounting site ships with a full admin. Create and edit pages in a proper editor, publish or unpublish separately from saving, keep an image library with alt text, drag the navigation into order including nested menus, edit site settings, set up email with a test-send button, and work through a read/unread inbox of enquiries. The admin account is protected by an authenticator app — the setup code is generated on their own server, so nobody else ever sees it — with a lockout after five failed attempts and sessions held server-side rather than in a cookie.

The agency site adds the file problem. Its uploader works in careful steps: register the file, send it in 32 MB pieces, then finish. **The server, not the browser, keeps track of how much has arrived.** A piece that turns up in the wrong place is rejected along with the right position, and the browser picks up from there, retrying with growing gaps. Before the server moves its marker, the file is safely written to disk and trimmed back to the last good point, so a crash costs one piece at most. Starting an upload again for the same file just continues it, which means a closed laptop, a browser restart or a dropped connection all resume exactly where they stopped. On completion the server re-reads the file and checks it matches; if it doesn't, the upload resets rather than accepting bad data.

Client links are created with a label, an expiry date, a size limit and a file limit, are stored only as a fingerprint — the address is shown once and can't be read back out of the system — and can be revoked in one click. Downloads are handed off to the web server rather than tying up the app, which makes them resumable for free.

### The result

Both firms edit their own sites. Pages, images, menus and settings change on the day someone decides they should, which means the site stays true instead of slowly going stale between retainer invoices.

Enquiries land in an inbox with a read state instead of an email thread. The accounting site's whole admin was built and shipped in a day, and has needed two small fixes in the six months since — which is about the right amount of attention for a website.

The agency stopped paying per seat for file transfer, and stopped losing uploads at eighty percent. A producer sends one labeled link with an expiry and a size limit, and the footage arrives checked.

### Why it holds up

- **Content is cleaned on the server.** Only known-safe tags and attributes survive, links are checked, and scripts are dropped along with their contents — so pasting in a document can't bring anything executable with it.
- **Uploads survive a crash by design,** not by luck: write, flush to disk, then move the marker. There's also a free-space floor that refuses new pieces rather than filling the drive.
- **Database changes take turns,** so several copies starting at once can't apply them twice, and the app refuses to create an admin account without a password you supplied.
- **One command handles install, update, certificate renewal and removal** — including a DNS check before requesting a certificate, backups before every update, and automatic renewal that reloads only the web part, for a few seconds.$$, body_html = $$<h3>The problem</h3>
<p>Two firms, one complaint. Every change to the website went through somebody else.</p>
<p>The accounting practice paid a freelancer — or waited three weeks — every time a service description changed, a new staff bio went up, or the menu needed reordering. Enquiries arrived as forwarded emails and got lost in an inbox. The admin login was a password everybody knew.</p>
<p>The production agency had the website problem plus a bigger one: moving footage. A client with forty gigabytes of camera files either bought a cloud storage seat, split the delivery across five transfer links that expired within the week, or drove a hard drive across town. When the browser tab crashed at eighty percent, the whole thing started again. And nobody could remember which client had sent which take.</p>
<h3>What we built</h3>
<p>Two sites, one idea: everything that changes regularly should be editable by the people who own it.</p>
<p>The accounting site ships with a full admin. Create and edit pages in a proper editor, publish or unpublish separately from saving, keep an image library with alt text, drag the navigation into order including nested menus, edit site settings, set up email with a test-send button, and work through a read/unread inbox of enquiries. The admin account is protected by an authenticator app — the setup code is generated on their own server, so nobody else ever sees it — with a lockout after five failed attempts and sessions held server-side rather than in a cookie.</p>
<p>The agency site adds the file problem. Its uploader works in careful steps: register the file, send it in 32 MB pieces, then finish. <strong>The server, not the browser, keeps track of how much has arrived.</strong> A piece that turns up in the wrong place is rejected along with the right position, and the browser picks up from there, retrying with growing gaps. Before the server moves its marker, the file is safely written to disk and trimmed back to the last good point, so a crash costs one piece at most. Starting an upload again for the same file just continues it, which means a closed laptop, a browser restart or a dropped connection all resume exactly where they stopped. On completion the server re-reads the file and checks it matches; if it doesn&rsquo;t, the upload resets rather than accepting bad data.</p>
<p>Client links are created with a label, an expiry date, a size limit and a file limit, are stored only as a fingerprint — the address is shown once and can&rsquo;t be read back out of the system — and can be revoked in one click. Downloads are handed off to the web server rather than tying up the app, which makes them resumable for free.</p>
<h3>The result</h3>
<p>Both firms edit their own sites. Pages, images, menus and settings change on the day someone decides they should, which means the site stays true instead of slowly going stale between retainer invoices.</p>
<p>Enquiries land in an inbox with a read state instead of an email thread. The accounting site&rsquo;s whole admin was built and shipped in a day, and has needed two small fixes in the six months since — which is about the right amount of attention for a website.</p>
<p>The agency stopped paying per seat for file transfer, and stopped losing uploads at eighty percent. A producer sends one labeled link with an expiry and a size limit, and the footage arrives checked.</p>
<h3>Why it holds up</h3>
<ul>
<li><strong>Content is cleaned on the server.</strong> Only known-safe tags and attributes survive, links are checked, and scripts are dropped along with their contents — so pasting in a document can&rsquo;t bring anything executable with it.</li>
<li><strong>Uploads survive a crash by design,</strong> not by luck: write, flush to disk, then move the marker. There&rsquo;s also a free-space floor that refuses new pieces rather than filling the drive.</li>
<li><strong>Database changes take turns,</strong> so several copies starting at once can&rsquo;t apply them twice, and the app refuses to create an admin account without a password you supplied.</li>
<li><strong>One command handles install, update, certificate renewal and removal</strong> — including a DNS check before requesting a certificate, backups before every update, and automatic renewal that reloads only the web part, for a few seconds.</li>
</ul>$$, updated_at = now()
 WHERE slug = $$owner-editable-website$$ AND md5(replace(summary, chr(13), '')) = '6a0bed715269909b6735658272a75d49'
   AND md5(replace(body_md, chr(13), '')) = '45ea04e022d928aeb912d586ca4f07d0';


-- The stat labels under each case study.

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "catalogue pages scored"$$, $$"label": "catalog pages scored"$$)::jsonb, updated_at = now()
 WHERE slug = $$ai-seo-catalog$$ AND metrics::text LIKE $$%"label": "catalogue pages scored"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "tables corrected per barcode"$$, $$"label": "tables fixed per barcode"$$)::jsonb, updated_at = now()
 WHERE slug = $$barcode-price-integrity$$ AND metrics::text LIKE $$%"label": "tables corrected per barcode"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "stock signals reconciled"$$, $$"label": "stock signals combined"$$)::jsonb, updated_at = now()
 WHERE slug = $$realtime-inventory-sync$$ AND metrics::text LIKE $$%"label": "stock signals reconciled"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "banks recognised"$$, $$"label": "banks recognized"$$)::jsonb, updated_at = now()
 WHERE slug = $$statement-intelligence$$ AND metrics::text LIKE $$%"label": "banks recognised"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "stages before AI is asked"$$, $$"label": "passes before AI is asked"$$)::jsonb, updated_at = now()
 WHERE slug = $$statement-intelligence$$ AND metrics::text LIKE $$%"label": "stages before AI is asked"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "ERP tables per scan"$$, $$"label": "ERP records per scan"$$)::jsonb, updated_at = now()
 WHERE slug = $$warehouse-floor-suite$$ AND metrics::text LIKE $$%"label": "ERP tables per scan"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "fields written per item"$$, $$"label": "details written per item"$$)::jsonb, updated_at = now()
 WHERE slug = $$product-onboarding-automation$$ AND metrics::text LIKE $$%"label": "fields written per item"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "spreadsheet headings auto-mapped"$$, $$"label": "spreadsheet headings recognized"$$)::jsonb, updated_at = now()
 WHERE slug = $$product-onboarding-automation$$ AND metrics::text LIKE $$%"label": "spreadsheet headings auto-mapped"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "state rules built in"$$, $$"label": "state rulebooks built in"$$)::jsonb, updated_at = now()
 WHERE slug = $$legal-intake-portal$$ AND metrics::text LIKE $$%"label": "state rules built in"%$$;

UPDATE case_studies
   SET metrics = replace(metrics::text, $$"label": "developer tickets to edit pages"$$, $$"label": "developer tickets to edit a page"$$)::jsonb, updated_at = now()
 WHERE slug = $$owner-editable-website$$ AND metrics::text LIKE $$%"label": "developer tickets to edit pages"%$$;


-- The client label, the search-result title and description.

UPDATE case_studies SET meta_description = $$One warehouse, several storefronts, one true sellable number. How we ended double-sold stock with a number the system works out and listings that hide themselves.$$, updated_at = now()
 WHERE slug = $$realtime-inventory-sync$$ AND md5(replace(meta_description, chr(13), '')) = '0ebefb34c3761d24b0f265156e94fce6';

UPDATE case_studies SET meta_description = $$Scan, price five carriers, buy the label, and write the tracking back to both order systems — without ever losing a paid-for label to an outage.$$, updated_at = now()
 WHERE slug = $$shipping-desk-consolidation$$ AND replace(meta_description, chr(13), '') = $$Scan, rate five carriers, buy the label, and write tracking back to both order systems — without ever losing a purchased label to an outage.$$;

UPDATE case_studies SET meta_description = $$One screen that fixes a barcode in eight tables per database and every storefront at once, and sets four price tiers in a single entry.$$, updated_at = now()
 WHERE slug = $$barcode-price-integrity$$ AND replace(meta_description, chr(13), '') = $$A single console that corrects a barcode in eight tables per database and every storefront at once, and sets four price tiers in one entry.$$;

UPDATE case_studies SET meta_description = $$One form replaces typing 58 details into every back office and storefront, with prices worked out per destination and duplicates caught before anything is written.$$, updated_at = now()
 WHERE slug = $$product-onboarding-automation$$ AND md5(replace(meta_description, chr(13), '')) = 'e04b912c4e1302640015aca2523e85be';

UPDATE case_studies SET meta_description = $$Receiving, bin locations, packing and counts on scanners and phones, writing straight into the existing ERP with a name on every entry.$$, updated_at = now()
 WHERE slug = $$warehouse-floor-suite$$ AND md5(replace(meta_description, chr(13), '')) = 'ea474f06cbb525bbf24bdbfb833eed10';

UPDATE case_studies SET meta_title = $$Buying driven by what actually sold$$, meta_description = $$Reorder levels worked out from invoice history, set against stock already coming in and already promised, rounded to whole cases, and sent as a supplier order.$$, updated_at = now()
 WHERE slug = $$demand-driven-purchasing$$ AND replace(meta_title, chr(13), '') = $$Purchasing driven by real sales velocity$$
   AND md5(replace(meta_description, chr(13), '')) = '6f71c4dabbc0d686024daaf095d926bb';

UPDATE case_studies SET client = $$Single-brand online retailer with a large catalog$$, meta_title = $$AI catalog SEO, with a person approving every change$$, meta_description = $$916 pages scored against clear rules, 20 kinds of problem ranked, AI writing titles and alt text — and nothing published without approval.$$, updated_at = now()
 WHERE slug = $$ai-seo-catalog$$ AND replace(client, chr(13), '') = $$Single-brand online retailer with a large catalogue$$
   AND replace(meta_title, chr(13), '') = $$AI catalogue SEO with a human in the loop$$
   AND replace(meta_description, chr(13), '') = $$916 pages scored against weighted rules, 20 issue types ranked, AI agents writing titles and alt text — nothing published without approval.$$;

UPDATE case_studies SET meta_description = $$A questionnaire with no login that explains a rough range on screen, opens a tracked case, and lets partners rebuild the questions by dragging them.$$, updated_at = now()
 WHERE slug = $$legal-intake-portal$$ AND md5(replace(meta_description, chr(13), '')) = '37111bba54bc8e1cd5c0a63aa637129d';

UPDATE case_studies SET meta_title = $$Bank statements imported, read and sorted$$, meta_description = $$Twelve banks recognized automatically, scanned PDFs read by OCR, duplicates caught, and four passes of sorting that learn from your corrections.$$, updated_at = now()
 WHERE slug = $$statement-intelligence$$ AND replace(meta_title, chr(13), '') = $$Bank statements imported, OCR'd and categorised$$
   AND md5(replace(meta_description, chr(13), '')) = '61f2adf65e8320e8600d69aee8de9788';

UPDATE case_studies SET client = $$An accounting practice and a film production agency$$, meta_description = $$Two firms running their own websites — pages, images, menus, two-factor login — plus client uploads that pick up again after a closed laptop.$$, updated_at = now()
 WHERE slug = $$owner-editable-website$$ AND replace(client, chr(13), '') = $$An accountancy practice and a film production agency$$
   AND md5(replace(meta_description, chr(13), '')) = '764d8c7f298313650bd495156e8ca297';


-- Screenshot captions and two lines of the Built-with list.

UPDATE case_studies
   SET gallery = replace(gallery::text, $$4,195 of 4,812 products reconciled against one storefront$$, $$4,195 of 4,812 products checked against one storefront$$)::jsonb, updated_at = now()
 WHERE slug = $$realtime-inventory-sync$$ AND gallery::text LIKE $$%4,195 of 4,812 products reconciled against one storefront%$$;

UPDATE case_studies
   SET gallery = replace(gallery::text, $$on-hand plus confirmed PO, less in-progress and committed$$, $$on hand plus confirmed orders in, less work in progress and stock already promised$$)::jsonb, updated_at = now()
 WHERE slug = $$realtime-inventory-sync$$ AND gallery::text LIKE $$%on-hand plus confirmed PO, less in-progress and committed%$$;

UPDATE case_studies
   SET gallery = replace(gallery::text, $$84 units short across two lines, itemised against the PO$$, $$84 units short across two lines, listed line by line against the order$$)::jsonb, updated_at = now()
 WHERE slug = $$warehouse-floor-suite$$ AND gallery::text LIKE $$%84 units short across two lines, itemised against the PO%$$;

UPDATE case_studies
   SET gallery = replace(gallery::text, $$One decision categorises every charge from the same merchant$$, $$One decision sorts every charge from the same merchant$$)::jsonb, updated_at = now()
 WHERE slug = $$statement-intelligence$$ AND gallery::text LIKE $$%One decision categorises every charge from the same merchant%$$;

UPDATE case_studies
   SET stack = array_replace(stack, $$29 idempotent SQL migrations$$, $$29 database updates, safe to re-run$$), updated_at = now()
 WHERE slug = $$barcode-price-integrity$$ AND stack @> ARRAY[$$29 idempotent SQL migrations$$]::text[];

UPDATE case_studies
   SET stack = array_replace(stack, $$PostgreSQL 15 with 73 tables and 75 idempotent migrations$$, $$PostgreSQL 15 with 73 tables and 75 re-runnable migrations$$), updated_at = now()
 WHERE slug = $$ai-seo-catalog$$ AND stack @> ARRAY[$$PostgreSQL 15 with 73 tables and 75 idempotent migrations$$]::text[];

UPDATE case_studies
   SET stack = array_replace(stack, $$OpenRouter with a live, switchable model catalogue$$, $$OpenRouter with a live, switchable model catalog$$), updated_at = now()
 WHERE slug = $$ai-seo-catalog$$ AND stack @> ARRAY[$$OpenRouter with a live, switchable model catalogue$$]::text[];

UPDATE case_studies
   SET stack = array_replace(stack, $$Server-side HTML sanitisation with a strict tag allowlist$$, $$Server-side HTML cleaning with a strict tag allowlist$$), updated_at = now()
 WHERE slug = $$owner-editable-website$$ AND stack @> ARRAY[$$Server-side HTML sanitisation with a strict tag allowlist$$]::text[];

UPDATE case_studies
   SET gallery = replace(gallery::text, $$Gross range, money in the client's pocket, the deadline that matters$$, $$The range, what would actually reach the client's pocket, the deadline that matters$$)::jsonb, updated_at = now()
 WHERE slug = $$legal-intake-portal$$ AND gallery::text LIKE $$%Gross range, money in the client's pocket, the deadline that matters%$$;


-- ============ Blog posts ============

UPDATE posts SET title = $$What retyping one order actually costs you$$, excerpt = $$Everyone says retyping an order takes a minute. Timed honestly it takes four to nine, and the typing is the cheapest part of the bill.$$, body_md = $$Ask an owner what it costs to retype an order into a second system and you'll usually get a shrug. "A minute, maybe two." That answer is why the problem sticks around for years.

Here's the arithmetic, done honestly.

### Start with the real minutes

Retyping an order is rarely one action. It's: open the second system, find or create the customer, key in the line items, check the units, fix the one line that doesn't match, save, then go back and mark the first system as done. Time it with a stopwatch instead of from memory. In every warehouse and back office we've measured, the honest number lands somewhere between four and nine minutes. Not one or two.

Take the low end. Four minutes, sixty orders a day, five days a week. That's twenty hours a week. One full-time person, doing nothing but reading a screen and typing what it says into another screen.

At $25 an hour all in, that's roughly $26,000 a year. It's a real number, it appears in no budget line, and nobody owns it.

### Then add the mistakes

People copying numbers get them wrong somewhere between half a percent and one percent of the time. Call it 0.5%. Sixty orders a day is about fifteen thousand a year, so seventy-five orders leave your building with something wrong on them.

The cost of a wrong order isn't the typing. It's the phone call, the return label, the credit note, the second shipment, the apology, and now and then the customer who doesn't come back. Most people, pressed, put the all-in cost of one wrong shipment north of $80. Seventy-five of those is another $6,000 — and that assumes you catch them.

A typing mistake is also the worst kind, because you can't see it happen. Nothing breaks. The screen looks right. It shows up two weeks later as a stock count that won't add up.

### Now the part nobody prices

The retyping job is almost always done by one person who's unusually good at it. They know the units are cases in one system and singles in the other. They know customer 4412 is really the same as customer 4412-B. They know which three products always need a manual override.

None of that is written down anywhere. It lives in one head.

When that person is on vacation, output halves and mistakes triple. When they leave, you find out you never had a documented process — you had a person, and you called it a process. That's the risk that actually keeps owners up at night, and it doesn't show up in any hourly calculation.

### And the part that's hardest to see

Retyping sets the pace for everything downstream. If orders are keyed in once a day at 4pm, your warehouse can't pick before 4pm, your stock levels are a day out of date, and your website is promising things you don't have. The delay isn't the typing. It's the batching the typing forces on you.

We watched a company move from a once-a-day manual push to a five-minute automatic sync and find that the real win wasn't the twenty hours. It was that the website stopped overselling, because reserved stock finally moved in near real time instead of overnight.

### What to do about it

You don't need to replace your systems. You need the two you have to hand each other the specific records a person is currently carrying between them.

Three questions decide whether it's worth doing:

1. **Can both systems be reached?** If system A has an API or a database you can read, and system B has an API or a database you can write to, the job is doable. Most business software from the last twenty years qualifies, including a surprising amount of the old stuff.
2. **Is there one shared identifier?** A product code, a barcode, an order number, a customer ID. If the two systems agree on one, the connection is straightforward. If they don't, the first piece of work is agreeing on one — and that's worth doing on its own.
3. **What happens when it fails?** The answer must not be "quietly." A good connection writes down every record it moved, retries what it can, and puts whatever it can't in a queue somebody can actually see.

### The honest test

Pick the record you retype most. Count how many times a day someone reads it in one system and types it into another. Multiply by four minutes. Multiply by 250 days.

If the answer is more than a couple of weeks of somebody's year, this isn't an annoyance. It's an unbudgeted salary, an invisible error rate, and a single point of failure with a friendly face.

That's usually the first thing worth fixing, and it usually pays for itself well before the year is out.$$, body_html = $$<p>Ask an owner what it costs to retype an order into a second system and you&rsquo;ll usually get a shrug. &ldquo;A minute, maybe two.&rdquo; That answer is why the problem sticks around for years.</p>
<p>Here&rsquo;s the arithmetic, done honestly.</p>
<h3>Start with the real minutes</h3>
<p>Retyping an order is rarely one action. It&rsquo;s: open the second system, find or create the customer, key in the line items, check the units, fix the one line that doesn&rsquo;t match, save, then go back and mark the first system as done. Time it with a stopwatch instead of from memory. In every warehouse and back office we&rsquo;ve measured, the honest number lands somewhere between four and nine minutes. Not one or two.</p>
<p>Take the low end. Four minutes, sixty orders a day, five days a week. That&rsquo;s twenty hours a week. One full-time person, doing nothing but reading a screen and typing what it says into another screen.</p>
<p>At $25 an hour all in, that&rsquo;s roughly $26,000 a year. It&rsquo;s a real number, it appears in no budget line, and nobody owns it.</p>
<h3>Then add the mistakes</h3>
<p>People copying numbers get them wrong somewhere between half a percent and one percent of the time. Call it 0.5%. Sixty orders a day is about fifteen thousand a year, so seventy-five orders leave your building with something wrong on them.</p>
<p>The cost of a wrong order isn&rsquo;t the typing. It&rsquo;s the phone call, the return label, the credit note, the second shipment, the apology, and now and then the customer who doesn&rsquo;t come back. Most people, pressed, put the all-in cost of one wrong shipment north of $80. Seventy-five of those is another $6,000 — and that assumes you catch them.</p>
<p>A typing mistake is also the worst kind, because you can&rsquo;t see it happen. Nothing breaks. The screen looks right. It shows up two weeks later as a stock count that won&rsquo;t add up.</p>
<h3>Now the part nobody prices</h3>
<p>The retyping job is almost always done by one person who&rsquo;s unusually good at it. They know the units are cases in one system and singles in the other. They know customer 4412 is really the same as customer 4412-B. They know which three products always need a manual override.</p>
<p>None of that is written down anywhere. It lives in one head.</p>
<p>When that person is on vacation, output halves and mistakes triple. When they leave, you find out you never had a documented process — you had a person, and you called it a process. That&rsquo;s the risk that actually keeps owners up at night, and it doesn&rsquo;t show up in any hourly calculation.</p>
<h3>And the part that&rsquo;s hardest to see</h3>
<p>Retyping sets the pace for everything downstream. If orders are keyed in once a day at 4pm, your warehouse can&rsquo;t pick before 4pm, your stock levels are a day out of date, and your website is promising things you don&rsquo;t have. The delay isn&rsquo;t the typing. It&rsquo;s the batching the typing forces on you.</p>
<p>We watched a company move from a once-a-day manual push to a five-minute automatic sync and find that the real win wasn&rsquo;t the twenty hours. It was that the website stopped overselling, because reserved stock finally moved in near real time instead of overnight.</p>
<h3>What to do about it</h3>
<p>You don&rsquo;t need to replace your systems. You need the two you have to hand each other the specific records a person is currently carrying between them.</p>
<p>Three questions decide whether it&rsquo;s worth doing:</p>
<ol>
<li><strong>Can both systems be reached?</strong> If system A has an API or a database you can read, and system B has an API or a database you can write to, the job is doable. Most business software from the last twenty years qualifies, including a surprising amount of the old stuff.</li>
<li><strong>Is there one shared identifier?</strong> A product code, a barcode, an order number, a customer ID. If the two systems agree on one, the connection is straightforward. If they don&rsquo;t, the first piece of work is agreeing on one — and that&rsquo;s worth doing on its own.</li>
<li><strong>What happens when it fails?</strong> The answer must not be &ldquo;quietly.&rdquo; A good connection writes down every record it moved, retries what it can, and puts whatever it can&rsquo;t in a queue somebody can actually see.</li>
</ol>
<h3>The honest test</h3>
<p>Pick the record you retype most. Count how many times a day someone reads it in one system and types it into another. Multiply by four minutes. Multiply by 250 days.</p>
<p>If the answer is more than a couple of weeks of somebody&rsquo;s year, this isn&rsquo;t an annoyance. It&rsquo;s an unbudgeted salary, an invisible error rate, and a single point of failure with a friendly face.</p>
<p>That&rsquo;s usually the first thing worth fixing, and it usually pays for itself well before the year is out.</p>$$, updated_at = now()
 WHERE slug = $$cost-of-retyping-data$$ AND replace(title, chr(13), '') = $$What re-typing one order actually costs you$$
   AND replace(excerpt, chr(13), '') = $$Everyone says re-keying an order takes a minute. Timed honestly it takes four to nine, and the typing is the cheapest part of the bill.$$
   AND md5(replace(body_md, chr(13), '')) = 'aa6a55e28d10aa2070f8499843573f01';

UPDATE posts SET title = $$The four points where a spreadsheet stops working$$, excerpt = $$Spreadsheets don't fail slowly. They fail at four specific points, and each one has a warning sign you can check this afternoon.$$, body_md = $$Nobody sets out to run their company on a spreadsheet. It just happens. Someone builds a tracker for one job, it works, and five years later that file is how the company decides what to buy, what to ship and who to invoice.

The useful question isn't "are spreadsheets bad." They're not. The question is: where exactly does yours stop working, and how will you know you've gone past it?

There are four points, and they're easier to spot than people expect.

### One: two people editing at once

This one's simple arithmetic. One person editing a file is fine. The moment a second person needs to change it on the same day, you have a problem, and there are only bad answers to it.

Cloud spreadsheets push this point back, they don't remove it. They let people edit at the same time without giving you any way to lock a row, check what was typed, or see who changed a cell and why. The failure is quiet: two people fix the same row differently, the last one wins, and neither of them knows.

**The warning sign:** somebody in your company says "don't touch the file, I'm in it."

### Two: around 5,000 rows

The exact number depends on your computer, but the behavior doesn't. Somewhere in the low thousands of rows with live formulas, three things happen together. The file gets slow enough that people avoid opening it. Filters and sorts get applied and left applied. And nobody reads the whole sheet any more.

That last one is the real problem. Under a few hundred rows, a person can scan the sheet and spot something wrong. Past a few thousand, nobody ever sees the whole thing. Mistakes stop being caught by eye, and nothing else is catching them, because a spreadsheet doesn't check anything. A cell that should hold a quantity will happily accept the word "backorder" and say nothing.

**The warning sign:** you have rows nobody has looked at in a year, and you wouldn't bet money on what's in them.

### Three: the first lookup between files

The moment one sheet reads from another, you've built yourself a database with none of the safety features. No way to keep records in step, no way to undo a half-finished change, no backup plan. You also now have a data model — you just haven't written it down.

This one's worth watching because it's where the upkeep stops being proportional. Every new file added to the web multiplies the ways the web can break. Rename a column in one place and a formula somewhere else quietly breaks. Nothing shows an error. A number just goes wrong.

**The warning sign:** somebody has to open the files in a particular order for the numbers to come out right.

### Four: the file has a keeper

This is the one that actually costs money. It arrives when the spreadsheet holds logic only one person understands — a pricing rule buried in a nested formula, a column that has to be cleared every Monday, a tab that looks unused but isn't.

At that point the spreadsheet isn't a document any more. It's an undocumented piece of software with one maintainer, no version history, no tests and no backups, running part of your business. If that person leaves, you can't hire a replacement, because the job description is "know this file."

**The warning sign:** one person's vacation changes what the company can get done that week.

### What crossing one should actually trigger

Not a big system replacement. The most common mistake we see is jumping from "the spreadsheet is struggling" to "we need an ERP", which is a two-year project to solve a two-week problem.

Cross one or two, and the answer is usually a small purpose-built tool: a real table, a form that checks what you type, a list view and a login. That's days of work, not months, and it clears up the "who's editing" and "is this even a number" problems outright, while leaving the process exactly as your team runs it.

Cross three, and the useful move is deciding which system owns which piece of information. You don't have to build anything yet — just answer "where does the true price live?" and "where does the true stock number live?" Half the tangle of files usually disappears once those have answers.

Cross four, and the priority isn't efficiency, it's risk. Get the logic out of that one head and into something written down and testable, even if the screen it lives behind is plain.

### Keep the spreadsheet where it's brilliant

Spreadsheets are still the best tool ever built for exploring a question, trying out a scenario, and doing a one-off piece of analysis. Those uses have no breaking points. Nothing piles up.

The trouble only starts when a spreadsheet stops answering a question and starts holding a record — when it becomes the place the company looks to find out what's true. Records need rules, history and access control. Spreadsheets have none of the three, by design.

So run the four warning signs. If you can name the person who owns the file, you already have your answer.$$, body_html = $$<p>Nobody sets out to run their company on a spreadsheet. It just happens. Someone builds a tracker for one job, it works, and five years later that file is how the company decides what to buy, what to ship and who to invoice.</p>
<p>The useful question isn&rsquo;t &ldquo;are spreadsheets bad.&rdquo; They&rsquo;re not. The question is: where exactly does yours stop working, and how will you know you&rsquo;ve gone past it?</p>
<p>There are four points, and they&rsquo;re easier to spot than people expect.</p>
<h3>One: two people editing at once</h3>
<p>This one&rsquo;s simple arithmetic. One person editing a file is fine. The moment a second person needs to change it on the same day, you have a problem, and there are only bad answers to it.</p>
<p>Cloud spreadsheets push this point back, they don&rsquo;t remove it. They let people edit at the same time without giving you any way to lock a row, check what was typed, or see who changed a cell and why. The failure is quiet: two people fix the same row differently, the last one wins, and neither of them knows.</p>
<p><strong>The warning sign:</strong> somebody in your company says &ldquo;don&rsquo;t touch the file, I&rsquo;m in it.&rdquo;</p>
<h3>Two: around 5,000 rows</h3>
<p>The exact number depends on your computer, but the behavior doesn&rsquo;t. Somewhere in the low thousands of rows with live formulas, three things happen together. The file gets slow enough that people avoid opening it. Filters and sorts get applied and left applied. And nobody reads the whole sheet any more.</p>
<p>That last one is the real problem. Under a few hundred rows, a person can scan the sheet and spot something wrong. Past a few thousand, nobody ever sees the whole thing. Mistakes stop being caught by eye, and nothing else is catching them, because a spreadsheet doesn&rsquo;t check anything. A cell that should hold a quantity will happily accept the word &ldquo;backorder&rdquo; and say nothing.</p>
<p><strong>The warning sign:</strong> you have rows nobody has looked at in a year, and you wouldn&rsquo;t bet money on what&rsquo;s in them.</p>
<h3>Three: the first lookup between files</h3>
<p>The moment one sheet reads from another, you&rsquo;ve built yourself a database with none of the safety features. No way to keep records in step, no way to undo a half-finished change, no backup plan. You also now have a data model — you just haven&rsquo;t written it down.</p>
<p>This one&rsquo;s worth watching because it&rsquo;s where the upkeep stops being proportional. Every new file added to the web multiplies the ways the web can break. Rename a column in one place and a formula somewhere else quietly breaks. Nothing shows an error. A number just goes wrong.</p>
<p><strong>The warning sign:</strong> somebody has to open the files in a particular order for the numbers to come out right.</p>
<h3>Four: the file has a keeper</h3>
<p>This is the one that actually costs money. It arrives when the spreadsheet holds logic only one person understands — a pricing rule buried in a nested formula, a column that has to be cleared every Monday, a tab that looks unused but isn&rsquo;t.</p>
<p>At that point the spreadsheet isn&rsquo;t a document any more. It&rsquo;s an undocumented piece of software with one maintainer, no version history, no tests and no backups, running part of your business. If that person leaves, you can&rsquo;t hire a replacement, because the job description is &ldquo;know this file.&rdquo;</p>
<p><strong>The warning sign:</strong> one person&rsquo;s vacation changes what the company can get done that week.</p>
<h3>What crossing one should actually trigger</h3>
<p>Not a big system replacement. The most common mistake we see is jumping from &ldquo;the spreadsheet is struggling&rdquo; to &ldquo;we need an ERP&rdquo;, which is a two-year project to solve a two-week problem.</p>
<p>Cross one or two, and the answer is usually a small purpose-built tool: a real table, a form that checks what you type, a list view and a login. That&rsquo;s days of work, not months, and it clears up the &ldquo;who&rsquo;s editing&rdquo; and &ldquo;is this even a number&rdquo; problems outright, while leaving the process exactly as your team runs it.</p>
<p>Cross three, and the useful move is deciding which system owns which piece of information. You don&rsquo;t have to build anything yet — just answer &ldquo;where does the true price live?&rdquo; and &ldquo;where does the true stock number live?&rdquo; Half the tangle of files usually disappears once those have answers.</p>
<p>Cross four, and the priority isn&rsquo;t efficiency, it&rsquo;s risk. Get the logic out of that one head and into something written down and testable, even if the screen it lives behind is plain.</p>
<h3>Keep the spreadsheet where it&rsquo;s brilliant</h3>
<p>Spreadsheets are still the best tool ever built for exploring a question, trying out a scenario, and doing a one-off piece of analysis. Those uses have no breaking points. Nothing piles up.</p>
<p>The trouble only starts when a spreadsheet stops answering a question and starts holding a record — when it becomes the place the company looks to find out what&rsquo;s true. Records need rules, history and access control. Spreadsheets have none of the three, by design.</p>
<p>So run the four warning signs. If you can name the person who owns the file, you already have your answer.</p>$$, updated_at = now()
 WHERE slug = $$when-spreadsheets-break$$ AND replace(title, chr(13), '') = $$The four thresholds where a spreadsheet stops working$$
   AND replace(excerpt, chr(13), '') = $$Spreadsheets do not fail gradually. They fail at four identifiable thresholds, and each one has a tell you can check this afternoon.$$
   AND md5(replace(body_md, chr(13), '')) = '11439495d9b48a35c113f5afdb3bce91';

UPDATE posts SET title = $$Buy or build: an hour's work to get an answer you can defend$$, excerpt = $$Four questions and a scoring table that settle the buy-versus-build argument with evidence, instead of whoever sounds most certain in the meeting.$$, body_md = $$"Should we buy something off the shelf or build it?" is the biggest software question a mid-size company asks, and it usually gets decided by whoever sounds most certain in the meeting.

It deserves better than that. Here's an approach that takes about an hour and gives you an answer you can defend.

### First, throw out the two lazy answers

**"Always buy — building is expensive and risky."** True for anything that isn't specific to you. Nobody should build their own accounting system, email, or payroll. It's also how companies end up with eleven subscriptions that don't talk to each other and a person whose full-time job is moving data between them.

**"Always build — off-the-shelf never fits."** Usually said by someone who enjoys building. Every system you build is a system you look after forever.

The real answer is almost always: buy the standard stuff, build the parts that connect it and the parts that are genuinely yours.

### The four questions

Run the process you're thinking about through these. Answer honestly, in writing.

**1. Is this something that sets you apart, or just something you have to do?**
Does the way you do this have anything to do with why customers pick you? Your pick-and-pack sequence, your pricing rules, your customer onboarding might. Your general ledger doesn't.

**2. How much would you have to change to fit the product?**
Get specific. Not "some setup" — list the actual steps your team would do differently. If that list is more than three steps and includes one your customers would notice, that's a real cost.

**3. Does it need to touch systems you already run?**
Count them. A tool that lives on its own island can be bought cheaply. A tool that has to read from your ERP and write to your store already needs custom work, and the question becomes whether you're buying a product plus that work, or just building one thing.

**4. What is the workaround costing you today?**
Hours a week, mistakes, and how many people know how it works. If the answer is "twenty hours and one person," the way things are now isn't free and shouldn't be scored as if it were.

### The scoring table

| Signal | Points to BUY | Points to BUILD |
|---|---|---|
| Standard business function (payroll, accounts, email, basic CRM) | Strong buy | — |
| It's part of how you compete | — | Strong build |
| A product fits with no change to how you work | Strong buy | — |
| You'd change 3+ steps to fit the product | — | Build |
| Only one system involved | Buy | — |
| Has to read or write 2+ systems you already run | — | Build the connection at least |
| Requirements are steady and standard for the industry | Buy | — |
| Requirements change as your business does | — | Build |
| Under about 5 users, occasional use | Strong buy | — |
| A team using it daily, all day | — | Build is defensible |
| Nobody does this by hand today | Buy | — |
| Somebody spends 10+ hrs/week on the workaround | — | Build |
| You have nobody to look after software | Strong buy | — |
| A vendor would hold data you must control | — | Build |

Add up each column. A clear majority is your answer. A tie usually means the honest answer is a third option.

### The third option, which is usually right

Buy the platform. Build the fit.

Keep the commercial system you already pay for — the ERP, the store, the accounting package — and build the thin layer that makes it work the way your business works. That layer is small, it's genuinely yours, and it's where nearly all the value is.

In practice that looks like: a scan station that writes into your existing ERP and signs people in against the staff list that's already there, so there's no second list to keep up. A service that works out your true sellable stock and pushes it to your store. A one-screen tool that replaces the six-system copy-and-paste job of adding a product. None of these replace a platform. All of them remove a person-shaped gap between platforms.

### Three costs people forget, on both sides

**Buying has a build cost.** Moving your data over, connecting it up, training, and the process changes you swore you wouldn't make. Budget it as real money.

**Building has a running cost.** Hosting, updates, and someone who can change it in two years. Ask whoever builds it — in-house or outside — what happens when you need a change and they're not available. If there's no good answer, the price is wrong.

**Both have an exit cost.** With a vendor, ask how you get your data out and what that costs. With custom work, ask who owns the code and whether another developer could pick it up. "You own the code, it runs in Docker, the database changes are plain SQL" is a real answer. "It's on our platform" isn't.

### The one-hour version

Write the process down on a page. Time the current workaround. Answer the four questions. Fill in the table. If it says buy, buy it without guilt. If it says build, scope the smallest version that removes the pain — one workflow, not a platform — and ship that first.

The companies that get this right are rarely the ones with the strongest opinion. They're the ones who wrote it down.$$, body_html = $$<p>&ldquo;Should we buy something off the shelf or build it?&rdquo; is the biggest software question a mid-size company asks, and it usually gets decided by whoever sounds most certain in the meeting.</p>
<p>It deserves better than that. Here&rsquo;s an approach that takes about an hour and gives you an answer you can defend.</p>
<h3>First, throw out the two lazy answers</h3>
<p><strong>&ldquo;Always buy — building is expensive and risky.&rdquo;</strong> True for anything that isn&rsquo;t specific to you. Nobody should build their own accounting system, email, or payroll. It&rsquo;s also how companies end up with eleven subscriptions that don&rsquo;t talk to each other and a person whose full-time job is moving data between them.</p>
<p><strong>&ldquo;Always build — off-the-shelf never fits.&rdquo;</strong> Usually said by someone who enjoys building. Every system you build is a system you look after forever.</p>
<p>The real answer is almost always: buy the standard stuff, build the parts that connect it and the parts that are genuinely yours.</p>
<h3>The four questions</h3>
<p>Run the process you&rsquo;re thinking about through these. Answer honestly, in writing.</p>
<p><strong>1. Is this something that sets you apart, or just something you have to do?</strong>
Does the way you do this have anything to do with why customers pick you? Your pick-and-pack sequence, your pricing rules, your customer onboarding might. Your general ledger doesn&rsquo;t.</p>
<p><strong>2. How much would you have to change to fit the product?</strong>
Get specific. Not &ldquo;some setup&rdquo; — list the actual steps your team would do differently. If that list is more than three steps and includes one your customers would notice, that&rsquo;s a real cost.</p>
<p><strong>3. Does it need to touch systems you already run?</strong>
Count them. A tool that lives on its own island can be bought cheaply. A tool that has to read from your ERP and write to your store already needs custom work, and the question becomes whether you&rsquo;re buying a product plus that work, or just building one thing.</p>
<p><strong>4. What is the workaround costing you today?</strong>
Hours a week, mistakes, and how many people know how it works. If the answer is &ldquo;twenty hours and one person,&rdquo; the way things are now isn&rsquo;t free and shouldn&rsquo;t be scored as if it were.</p>
<h3>The scoring table</h3>
<table>
<thead>
<tr>
<th>Signal</th>
<th>Points to BUY</th>
<th>Points to BUILD</th>
</tr>
</thead>
<tbody>
<tr>
<td>Standard business function (payroll, accounts, email, basic CRM)</td>
<td>Strong buy</td>
<td>—</td>
</tr>
<tr>
<td>It&rsquo;s part of how you compete</td>
<td>—</td>
<td>Strong build</td>
</tr>
<tr>
<td>A product fits with no change to how you work</td>
<td>Strong buy</td>
<td>—</td>
</tr>
<tr>
<td>You&rsquo;d change 3+ steps to fit the product</td>
<td>—</td>
<td>Build</td>
</tr>
<tr>
<td>Only one system involved</td>
<td>Buy</td>
<td>—</td>
</tr>
<tr>
<td>Has to read or write 2+ systems you already run</td>
<td>—</td>
<td>Build the connection at least</td>
</tr>
<tr>
<td>Requirements are steady and standard for the industry</td>
<td>Buy</td>
<td>—</td>
</tr>
<tr>
<td>Requirements change as your business does</td>
<td>—</td>
<td>Build</td>
</tr>
<tr>
<td>Under about 5 users, occasional use</td>
<td>Strong buy</td>
<td>—</td>
</tr>
<tr>
<td>A team using it daily, all day</td>
<td>—</td>
<td>Build is defensible</td>
</tr>
<tr>
<td>Nobody does this by hand today</td>
<td>Buy</td>
<td>—</td>
</tr>
<tr>
<td>Somebody spends 10+ hrs/week on the workaround</td>
<td>—</td>
<td>Build</td>
</tr>
<tr>
<td>You have nobody to look after software</td>
<td>Strong buy</td>
<td>—</td>
</tr>
<tr>
<td>A vendor would hold data you must control</td>
<td>—</td>
<td>Build</td>
</tr>
</tbody>
</table>
<p>Add up each column. A clear majority is your answer. A tie usually means the honest answer is a third option.</p>
<h3>The third option, which is usually right</h3>
<p>Buy the platform. Build the fit.</p>
<p>Keep the commercial system you already pay for — the ERP, the store, the accounting package — and build the thin layer that makes it work the way your business works. That layer is small, it&rsquo;s genuinely yours, and it&rsquo;s where nearly all the value is.</p>
<p>In practice that looks like: a scan station that writes into your existing ERP and signs people in against the staff list that&rsquo;s already there, so there&rsquo;s no second list to keep up. A service that works out your true sellable stock and pushes it to your store. A one-screen tool that replaces the six-system copy-and-paste job of adding a product. None of these replace a platform. All of them remove a person-shaped gap between platforms.</p>
<h3>Three costs people forget, on both sides</h3>
<p><strong>Buying has a build cost.</strong> Moving your data over, connecting it up, training, and the process changes you swore you wouldn&rsquo;t make. Budget it as real money.</p>
<p><strong>Building has a running cost.</strong> Hosting, updates, and someone who can change it in two years. Ask whoever builds it — in-house or outside — what happens when you need a change and they&rsquo;re not available. If there&rsquo;s no good answer, the price is wrong.</p>
<p><strong>Both have an exit cost.</strong> With a vendor, ask how you get your data out and what that costs. With custom work, ask who owns the code and whether another developer could pick it up. &ldquo;You own the code, it runs in Docker, the database changes are plain SQL&rdquo; is a real answer. &ldquo;It&rsquo;s on our platform&rdquo; isn&rsquo;t.</p>
<h3>The one-hour version</h3>
<p>Write the process down on a page. Time the current workaround. Answer the four questions. Fill in the table. If it says buy, buy it without guilt. If it says build, scope the smallest version that removes the pain — one workflow, not a platform — and ship that first.</p>
<p>The companies that get this right are rarely the ones with the strongest opinion. They&rsquo;re the ones who wrote it down.</p>$$, updated_at = now()
 WHERE slug = $$buy-or-build-framework$$ AND replace(title, chr(13), '') = $$Buy or build: an hour-long decision you can defend$$
   AND md5(replace(excerpt, chr(13), '')) = 'faa16bcb718c2536fa092d493b29acfb'
   AND md5(replace(body_md, chr(13), '')) = '9f0b9f8fcd4f515e4e8acd7f4fb51e0e';

UPDATE posts SET title = $$What overselling really costs, and the formula that ends it$$, excerpt = $$Cancellations are the cheapest part of overselling. The expensive part is the stock you hold back forever because you don't trust the number.$$, body_md = $$Overselling looks like a small problem. A customer orders something you don't have, you apologize, you refund, you move on. Once a week, maybe. Annoying, not fatal.

It isn't a small problem, and the reason is that the part you can see is the smallest part of it.

### What one oversell actually costs

Start with the direct costs of a single incident:

- Somebody finds it — usually a picker, usually after the order has been paid for.
- Somebody calls or emails the customer. Ten minutes, plus the part nobody enjoys.
- You refund, substitute, or back-order. Each of those costs something to handle.
- If part of the order already shipped, you're now paying for a split shipment.

Call it thirty to sixty minutes of attention and somewhere between $30 and $100, before you count anything you can't put a number on.

Now the parts that never appear on an invoice:

**Marketplace penalties.** If you sell anywhere besides your own site, your cancellation rate is scored. Enough cancellations and you lose your buy-box position, your search placement, or the account. This is the cost that turns an annoyance into a serious problem, and it builds up quietly until you cross a line.

**Trust, in the wrong places.** The customer who gets the cancellation is more likely than average to be a new customer, because your regulars buy the things you always have. So the cost lands hardest on exactly the relationships you spent marketing money to create.

**The cushion.** This is the big one, and almost nobody counts it. After enough oversells, somebody decides to hold stock back — list 90% of what you have and keep a buffer. That buffer is now inventory you can never sell. On a $1M stock position, a 10% cushion is $100,000 of working capital sitting there doing nothing, forever, to make up for a number you don't trust.

That's the real price of overselling. Not the cancellations, but the money you tie up avoiding them.

### Why the number is wrong to begin with

Almost always, one of four things:

1. **Stock is counted in one system and sold in another,** and the thing keeping them in step is a person, or a nightly job, or both.
2. **Reserved stock is invisible.** Units set aside for an open order, a pick in progress or a wholesale hold are still being counted as available.
3. **Reservations are per store, not shared.** Something reserved by store A is still shown as available by store B. If you run more than one sales channel out of one warehouse, this alone will oversell you steadily.
4. **Incoming stock is treated as if it's here.** A confirmed purchase order is real, but it isn't on the shelf, and mixing the two makes you look better stocked than you are.

### The formula that ends it

The fix is to stop publishing "whatever the warehouse system says" and start publishing a number you work out. In the systems we build, sellable stock is one line, worked out per product, on a schedule:

```
sellable = max(0, on hand + confirmed orders in - work in progress - already promised)
```

Four parts, and each one has to earn its place:

- **on hand** — physically in the building, according to one system. One system. If two systems disagree about what's on hand, that's a separate problem you have to fix first.
- **confirmed orders in** — stock on a confirmed purchase order. Only include this if you're willing to sell against it, and only if your confirmations are honest. Plenty of people set this to zero, and that's a perfectly good answer.
- **work in progress** — units on picks, transfers or jobs in flight. Physically there, not available.
- **already promised** — units set aside for open orders. This is the one that has to be added up across **every** sales channel, not per store. Something reserved anywhere is reserved everywhere.

The `max(0, ...)` matters more than it looks. Without it, one bad count produces a negative number, and a negative number pushed into a store does anything from hiding the listing to deleting it. Stop at zero and let the sorting-out happen in the warehouse, not on your product page.

The second half of the fix is what happens when the number hits zero: the listing gets hidden automatically, and comes back automatically when stock returns. Doing it by hand drifts within a week, every time.

### Getting it right in practice

Even a correct formula causes trouble if it's pushed carelessly. Three rules that matter:

**Send the number, not the change.** Setting a product to 12 units has to be safe to do twice. If your sync sends "add 3" instead of "make it 12", a retry will corrupt the count.

**Plan for API limits.** Store platforms limit how often you can call them. A sync that ignores that gets throttled exactly when you have the most to update — on a busy day. Budget the calls, back off when you're told to, and update the things that changed first.

**Write everything down.** When a merchandiser asks why a product went out of stock at 3pm, "here's the record: 40 on hand, 40 promised, 0 sellable, pushed at 15:02" ends the conversation in ten seconds. Without it, you're re-arguing whether the system can be trusted every week.

### What good looks like

You stop hearing about oversells. Then, a few weeks later, somebody asks whether you still need the cushion — and the answer is no, because the number on the site is now the real number.

That's where the money actually is.$$, body_html = $$<p>Overselling looks like a small problem. A customer orders something you don&rsquo;t have, you apologize, you refund, you move on. Once a week, maybe. Annoying, not fatal.</p>
<p>It isn&rsquo;t a small problem, and the reason is that the part you can see is the smallest part of it.</p>
<h3>What one oversell actually costs</h3>
<p>Start with the direct costs of a single incident:</p>
<ul>
<li>Somebody finds it — usually a picker, usually after the order has been paid for.</li>
<li>Somebody calls or emails the customer. Ten minutes, plus the part nobody enjoys.</li>
<li>You refund, substitute, or back-order. Each of those costs something to handle.</li>
<li>If part of the order already shipped, you&rsquo;re now paying for a split shipment.</li>
</ul>
<p>Call it thirty to sixty minutes of attention and somewhere between $30 and $100, before you count anything you can&rsquo;t put a number on.</p>
<p>Now the parts that never appear on an invoice:</p>
<p><strong>Marketplace penalties.</strong> If you sell anywhere besides your own site, your cancellation rate is scored. Enough cancellations and you lose your buy-box position, your search placement, or the account. This is the cost that turns an annoyance into a serious problem, and it builds up quietly until you cross a line.</p>
<p><strong>Trust, in the wrong places.</strong> The customer who gets the cancellation is more likely than average to be a new customer, because your regulars buy the things you always have. So the cost lands hardest on exactly the relationships you spent marketing money to create.</p>
<p><strong>The cushion.</strong> This is the big one, and almost nobody counts it. After enough oversells, somebody decides to hold stock back — list 90% of what you have and keep a buffer. That buffer is now inventory you can never sell. On a $1M stock position, a 10% cushion is $100,000 of working capital sitting there doing nothing, forever, to make up for a number you don&rsquo;t trust.</p>
<p>That&rsquo;s the real price of overselling. Not the cancellations, but the money you tie up avoiding them.</p>
<h3>Why the number is wrong to begin with</h3>
<p>Almost always, one of four things:</p>
<ol>
<li><strong>Stock is counted in one system and sold in another,</strong> and the thing keeping them in step is a person, or a nightly job, or both.</li>
<li><strong>Reserved stock is invisible.</strong> Units set aside for an open order, a pick in progress or a wholesale hold are still being counted as available.</li>
<li><strong>Reservations are per store, not shared.</strong> Something reserved by store A is still shown as available by store B. If you run more than one sales channel out of one warehouse, this alone will oversell you steadily.</li>
<li><strong>Incoming stock is treated as if it&rsquo;s here.</strong> A confirmed purchase order is real, but it isn&rsquo;t on the shelf, and mixing the two makes you look better stocked than you are.</li>
</ol>
<h3>The formula that ends it</h3>
<p>The fix is to stop publishing &ldquo;whatever the warehouse system says&rdquo; and start publishing a number you work out. In the systems we build, sellable stock is one line, worked out per product, on a schedule:</p>
<pre><code>sellable = max(0, on hand + confirmed orders in - work in progress - already promised)
</code></pre>
<p>Four parts, and each one has to earn its place:</p>
<ul>
<li><strong>on hand</strong> — physically in the building, according to one system. One system. If two systems disagree about what&rsquo;s on hand, that&rsquo;s a separate problem you have to fix first.</li>
<li><strong>confirmed orders in</strong> — stock on a confirmed purchase order. Only include this if you&rsquo;re willing to sell against it, and only if your confirmations are honest. Plenty of people set this to zero, and that&rsquo;s a perfectly good answer.</li>
<li><strong>work in progress</strong> — units on picks, transfers or jobs in flight. Physically there, not available.</li>
<li><strong>already promised</strong> — units set aside for open orders. This is the one that has to be added up across <strong>every</strong> sales channel, not per store. Something reserved anywhere is reserved everywhere.</li>
</ul>
<p>The <code>max(0, ...)</code> matters more than it looks. Without it, one bad count produces a negative number, and a negative number pushed into a store does anything from hiding the listing to deleting it. Stop at zero and let the sorting-out happen in the warehouse, not on your product page.</p>
<p>The second half of the fix is what happens when the number hits zero: the listing gets hidden automatically, and comes back automatically when stock returns. Doing it by hand drifts within a week, every time.</p>
<h3>Getting it right in practice</h3>
<p>Even a correct formula causes trouble if it&rsquo;s pushed carelessly. Three rules that matter:</p>
<p><strong>Send the number, not the change.</strong> Setting a product to 12 units has to be safe to do twice. If your sync sends &ldquo;add 3&rdquo; instead of &ldquo;make it 12&rdquo;, a retry will corrupt the count.</p>
<p><strong>Plan for API limits.</strong> Store platforms limit how often you can call them. A sync that ignores that gets throttled exactly when you have the most to update — on a busy day. Budget the calls, back off when you&rsquo;re told to, and update the things that changed first.</p>
<p><strong>Write everything down.</strong> When a merchandiser asks why a product went out of stock at 3pm, &ldquo;here&rsquo;s the record: 40 on hand, 40 promised, 0 sellable, pushed at 15:02&rdquo; ends the conversation in ten seconds. Without it, you&rsquo;re re-arguing whether the system can be trusted every week.</p>
<h3>What good looks like</h3>
<p>You stop hearing about oversells. Then, a few weeks later, somebody asks whether you still need the cushion — and the answer is no, because the number on the site is now the real number.</p>
<p>That&rsquo;s where the money actually is.</p>$$, updated_at = now()
 WHERE slug = $$the-oversell-problem$$ AND replace(title, chr(13), '') = $$The true cost of overselling, and the formula that ends it$$
   AND md5(replace(excerpt, chr(13), '')) = 'fc0741a6245acc504e1021d16e05ab52'
   AND md5(replace(body_md, chr(13), '')) = '2d849e6dd6d25695470af051f617335f';


-- ============ Hero, SEO defaults and the About page ============

UPDATE settings SET value = $$Covers Map and Prototype. We credit it against the build if you go ahead.$$, updated_at = now()
 WHERE key = $$onboarding_fee_note$$ AND replace(value, chr(13), '') = $$Covers Map and Prototype. Credited against the build if you go ahead.$$;

UPDATE settings SET value = $$Custom web and mobile apps, automation and integration for small and mid-size companies, built to fit the way you already work.$$, updated_at = now()
 WHERE key = $$seo_default_description$$ AND replace(value, chr(13), '') = $$Custom web and mobile apps, automation and integration for small and mid-size companies — built to fit the way you already work.$$;

UPDATE settings SET value = $$Edge Bourne Consulting exists for one reason. Most small and mid-size companies run on systems that don't talk to each other. Orders live in one place, stock in another, accounting in a third — and people fill the gaps by retyping things.

We build the piece in the middle. Custom web and mobile apps, connections between the platforms you already use, and automation that takes the repetitive work away entirely.

**What we've actually built**

Everything in the portfolio on this site is real software, running today. A stock engine that pulls two databases and a storefront into one number, so a multi-store retailer stops overselling. A shipping desk that gathers orders from two systems, compares carrier prices and writes the tracking back to both. A barcode and price system that keeps several back offices and several storefronts telling the same story — the longest-running system we have, and still growing. Four scan stations on one warehouse floor. A buying tool that decides what to order from what actually sold.

Between them, those systems run every day across industries including distribution, retail, warehousing, legal, finance and professional services.

**How we work**

- **Small, senior, direct.** You talk to the people building your system. No account managers, no handoffs, no junior developer learning on your budget.
- **Built around how you work.** We start from how your company actually runs. Our warehouse tools sign people in against the staff list already in the client's ERP, rather than creating a second list to keep in step. Small thing, but it's the general idea in practice.
- **Boringly reliable.** Deployments that install in one command. Database changes that apply themselves on start-up. A record of anything that touches money or stock. Proper tests where the logic deserves them — the statement importer alone carries over four hundred.
- **Yours at the end.** You own the code and the data. It runs on your own servers if you want it to. Nothing we build needs us to stay.

**What we don't do**

We don't take on work we'd have to learn on your budget. We don't rebuild systems that are working fine. And we don't sell a platform. If the honest answer to your problem is "buy the off-the-shelf tool," we'll say so in the first conversation — and then quote you for the work that makes it fit.

If your team spends hours a week moving data between systems, that's usually the first thing we fix. And it usually pays for itself within months.$$, updated_at = now()
 WHERE key = $$about_md$$ AND md5(replace(value, chr(13), '')) = 'cd3953e775a5446d50fbdee5c6d39bf1';

UPDATE settings SET value = $$<p>Edge Bourne Consulting exists for one reason. Most small and mid-size companies run on systems that don&rsquo;t talk to each other. Orders live in one place, stock in another, accounting in a third — and people fill the gaps by retyping things.</p>
<p>We build the piece in the middle. Custom web and mobile apps, connections between the platforms you already use, and automation that takes the repetitive work away entirely.</p>
<p><strong>What we&rsquo;ve actually built</strong></p>
<p>Everything in the portfolio on this site is real software, running today. A stock engine that pulls two databases and a storefront into one number, so a multi-store retailer stops overselling. A shipping desk that gathers orders from two systems, compares carrier prices and writes the tracking back to both. A barcode and price system that keeps several back offices and several storefronts telling the same story — the longest-running system we have, and still growing. Four scan stations on one warehouse floor. A buying tool that decides what to order from what actually sold.</p>
<p>Between them, those systems run every day across industries including distribution, retail, warehousing, legal, finance and professional services.</p>
<p><strong>How we work</strong></p>
<ul>
<li><strong>Small, senior, direct.</strong> You talk to the people building your system. No account managers, no handoffs, no junior developer learning on your budget.</li>
<li><strong>Built around how you work.</strong> We start from how your company actually runs. Our warehouse tools sign people in against the staff list already in the client&rsquo;s ERP, rather than creating a second list to keep in step. Small thing, but it&rsquo;s the general idea in practice.</li>
<li><strong>Boringly reliable.</strong> Deployments that install in one command. Database changes that apply themselves on start-up. A record of anything that touches money or stock. Proper tests where the logic deserves them — the statement importer alone carries over four hundred.</li>
<li><strong>Yours at the end.</strong> You own the code and the data. It runs on your own servers if you want it to. Nothing we build needs us to stay.</li>
</ul>
<p><strong>What we don&rsquo;t do</strong></p>
<p>We don&rsquo;t take on work we&rsquo;d have to learn on your budget. We don&rsquo;t rebuild systems that are working fine. And we don&rsquo;t sell a platform. If the honest answer to your problem is &ldquo;buy the off-the-shelf tool,&rdquo; we&rsquo;ll say so in the first conversation — and then quote you for the work that makes it fit.</p>
<p>If your team spends hours a week moving data between systems, that&rsquo;s usually the first thing we fix. And it usually pays for itself within months.</p>$$, updated_at = now()
 WHERE key = $$about_html$$ AND md5(replace(value, chr(13), '')) = '7de4734abe6165da9b5f085865844d9f';


-- The seeded hero strip, for installs that never had the live edit applied.
UPDATE content_blocks
   SET items = $$Over 100 systems in production
Runs on your own server
The code is yours$$, updated_at = now()
 WHERE group_key = $$home_proof$$ AND block_key = $$proof$$
   AND replace(items, chr(13), '') = $$10 systems in production
Docker-deployed on your own server
You own the code$$;
