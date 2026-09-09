-- 011_content_blocks.sql
-- Moves the copy that was hard-coded in the public Jinja templates into a
-- single editable table. One row per editable block; group_key says which
-- list/section it belongs to, block_key is a stable id for the blocks the
-- templates look up by name (section headings, page heads, CTAs).

CREATE TABLE IF NOT EXISTS content_blocks (
  id SERIAL PRIMARY KEY,
  group_key   TEXT NOT NULL,
  block_key   TEXT NOT NULL DEFAULT '',
  title       TEXT NOT NULL DEFAULT '',
  subtitle    TEXT NOT NULL DEFAULT '',
  body        TEXT NOT NULL DEFAULT '',
  items       TEXT NOT NULL DEFAULT '',
  link_url    TEXT NOT NULL DEFAULT '',
  link_label  TEXT NOT NULL DEFAULT '',
  extra       JSONB NOT NULL DEFAULT '{}'::jsonb,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  is_published BOOLEAN NOT NULL DEFAULT true,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS content_blocks_key_uq
  ON content_blocks (group_key, block_key) WHERE block_key <> '';
CREATE INDEX IF NOT EXISTS content_blocks_group_idx
  ON content_blocks (group_key, sort_order, id);

-- Seed: every string below is the text the templates rendered before this
-- migration, copied verbatim. ON CONFLICT keeps a re-run from duplicating.

INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$services$$,
          $$One partner for the systems$$,
          $$SERVICES$$,
          $$Four ways in. Most engagements use two of them before they are finished.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "your business runs on."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$work$$,
          $$Problems we've$$,
          $$WORK$$,
          $$Ten systems running in production. Clients are described by industry, not by name.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "already solved."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$process$$,
          $$Five steps.$$,
          $$PROCESS$$,
          $$Every engagement runs the same five steps. They exist so you always know what is happening, what you are getting next, and what it costs — and so you can stop after any one of them and still be left with something useful.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "No surprises."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$industries$$,
          $$We already know$$,
          $$INDUSTRIES$$,
          $$Six industries where we have shipped systems that people use every shift. The vocabulary is different; the bottleneck rarely is.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "how your day runs."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$about$$,
          $$Small team.$$,
          $$ABOUT$$,
          $$One senior engineer on your problem, not a bench of juniors learning on it.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "Serious systems."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$contact$$,
          $$Tell us what's slow.$$,
          $$CONTACT$$,
          $$One short conversation about what your team does by hand today. No pitch deck, no obligation.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "We'll take it from there."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$blog$$,
          $$Notes on running$$,
          $$BLOG$$,
          $$Short, concrete pieces on integration, automation and the software small companies actually need.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": "better systems."}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_heads$$,
          $$notfound$$,
          $$This page doesn't exist.$$,
          $$404$$,
          $$The link may be old, or the page was moved.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"accent": ""}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$default$$,
          $$Ready to simplify how your company runs?$$,
          $$NEXT STEP$$,
          $$Tell us what eats your team's time — we'll tell you what it takes to fix it.$$,
          $$A 30-minute call. No deck, no obligation.
We reply within one business day.$$,
          $$$$,
          $$Book a call$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$services$$,
          $$Not sure which of these you need?$$,
          $$$$,
          $$Most projects start as a conversation about what's slow today.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$work$$,
          $$See a problem here that looks like yours?$$,
          $$$$,
          $$Most of these started with one slow, manual job nobody wanted to own.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$process$$,
          $$Start at step one.$$,
          $$$$,
          $$Map is a fixed fee and a small one. It ends in a written process map and an honest recommendation — including the one where you buy instead of build.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$industries$$,
          $$Not on the list?$$,
          $$$$,
          $$The pattern is usually the same — two systems that do not talk, and a person in the middle retyping.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$about$$,
          $$Sound like the partner you're after?$$,
          $$$$,
          $$The first call costs nothing and usually saves a few wrong turns.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$blog$$,
          $$Prefer to talk it through?$$,
          $$$$,
          $$Most of these posts started as a question a client asked on a call.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$work_detail$$,
          $$Have a similar problem?$$,
          $$$$,
          $$We've probably seen a version of it before — and we can tell you quickly whether it's worth building.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$page_cta$$,
          $$blog_post$$,
          $$Got a version of this problem?$$,
          $$$$,
          $$Tell us what it looks like in your business and we will say whether it is worth building.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_services$$,
          $$Systems that fit the way you work$$,
          $$WHAT WE DO$$,
          $$$$,
          $$$$,
          $$/services$$,
          $$All services$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_showcase$$,
          $$Problems we've already solved$$,
          $$SELECTED WORK$$,
          $$$$,
          $$$$,
          $$/work$$,
          $$See all ten case studies$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_ai$$,
          $$AI on the work that is too big to do by hand$$,
          $$OPTIMIZE WITH AI$$,
          $$Everything a rule can still do, a rule keeps doing. The model only sees what is left over — and a person still approves what it changes.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_ai_cascade$$,
          $$What happens to one record$$,
          $$$$,
          $$The bar above each stage is what still needs handling when a record reaches it. Illustrative — the real split depends on your data.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_ai_apps$$,
          $$What it does today$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_ai_proof$$,
          $$Already running in production$$,
          $$$$,
          $$If a rule solves your problem, we write the rule and charge you less.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_process$$,
          $$Five steps, no surprises$$,
          $$HOW IT GOES$$,
          $$$$,
          $$$$,
          $$/process$$,
          $$See the full process$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_industries$$,
          $$Industries we already know$$,
          $$WHO WE BUILD FOR$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_testimonials$$,
          $$What it's like to work with us$$,
          $$IN THEIR WORDS$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_faq$$,
          $$Questions we get asked$$,
          $$STRAIGHT ANSWERS$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$home_blog$$,
          $$Notes on running better systems$$,
          $$FROM THE BLOG$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$process_gets$$,
          $$What you get$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$process_pricing$$,
          $$What it costs, and how long it runs$$,
          $$PRICING & SHAPE$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$services_shapes$$,
          $$Three ways to start$$,
          $$HOW ENGAGEMENTS ARE SHAPED$$,
          $$$$,
          $$$$,
          $$/process$$,
          $$See how a project runs$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$industries_caps$$,
          $$What we build here$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$industries_cases$$,
          $$Relevant work$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$about_beliefs$$,
          $$Four things that stay true$$,
          $$HOW WE WORK$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$contact_next$$,
          $$What happens next$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$contact_form$$,
          $$$$,
          $$SEND A MESSAGE$$,
          $$We use this only to reply to you. No list, no newsletter, no sharing.$$,
          $$$$,
          $$$$,
          $$Send message$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$work_problem$$,
          $$$$,
          $$THE PROBLEM$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$work_stack$$,
          $$Stack$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$work_side_cta$$,
          $$Same problem?$$,
          $$$$,
          $$Tell us what your team does by hand today. We'll tell you what it takes to remove it.$$,
          $$$$,
          $$/contact$$,
          $$Book a call$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$work_gallery$$,
          $$What it actually looks like$$,
          $$INSIDE THE SYSTEM$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$work_related$$,
          $$Related work$$,
          $$NEXT$$,
          $$$$,
          $$$$,
          $$/work$$,
          $$All case studies$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$footer_note$$,
          $$$$,
          $$$$,
          $$Custom systems for small and mid-size companies. Built on your own infrastructure, documented, and handed over.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$footer_explore$$,
          $$Explore$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$footer_build$$,
          $$What we build$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$footer_contact$$,
          $$Contact$$,
          $$$$,
          $$$$,
          $$$$,
          $$/contact$$,
          $$Book a call$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$sections$$,
          $$footer_bottom$$,
          $$Replies within one business day$$,
          $$$$,
          $$All rights reserved.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_proof$$,
          $$proof$$,
          $$$$,
          $$$$,
          $$$$,
          $$10 systems in production
Docker-deployed on your own server
You own the code$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_stats$$,
          $$s1$$,
          $$10$$,
          $$systems in production$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_stats$$,
          $$s2$$,
          $$6$$,
          $$industries served$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_stats$$,
          $$s3$$,
          $$0$$,
          $$per-seat licence fees$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_stats$$,
          $$s4$$,
          $$100%$$,
          $$of the code is yours$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_cascade$$,
          $$c1$$,
          $$Rules$$,
          $$Mappings you can read and change.$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${"fill": "100%", "kind": "", "done": false}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_cascade$$,
          $$c2$$,
          $$Learned memory$$,
          $$Every correction you already made.$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${"fill": "58%", "kind": "", "done": false}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_cascade$$,
          $$c3$$,
          $$Lookups$$,
          $$Your catalogue, ledger and history.$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${"fill": "34%", "kind": "", "done": false}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_cascade$$,
          $$c4$$,
          $$AI on what's left$$,
          $$The model sees only the remainder.$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${"fill": "17%", "kind": "is-ai", "done": false}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_cascade$$,
          $$c5$$,
          $$A person approves$$,
          $$Confidence and a reason, then a click.$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${"fill": "17%", "kind": "is-end", "done": true}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_principles$$,
          $$p1$$,
          $$AI runs last, not first.$$,
          $$$$,
          $$Rules, learned memory and lookups handle everything they can. The model only sees the remainder — cheaper per record, more predictable, and a model outage degrades the system instead of stopping it.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_principles$$,
          $$p2$$,
          $$Nothing commits itself.$$,
          $$$$,
          $$Suggestions arrive with a confidence and a reason, and a person confirms them. Catalogues and ledgers are never edited by a model acting alone.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_principles$$,
          $$p3$$,
          $$Grounded in your data.$$,
          $$$$,
          $$The model gets your actual numbers — search queries, click-through curves, product records, historical categories — not a general impression of your industry.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_principles$$,
          $$p4$$,
          $$It gets cheaper over time.$$,
          $$$$,
          $$Every correction becomes memory, so the share of records needing a model at all falls month over month.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_apps$$,
          $$a1$$,
          $$Catalogue copy at scale.$$,
          $$$$,
          $$Titles, descriptions and image alt text across thousands of products, written against your real search data.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_apps$$,
          $$a2$$,
          $$Documents into data.$$,
          $$$$,
          $$Statements, invoices and scanned PDFs read, structured and filed — including the ones that arrive as a photograph.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_apps$$,
          $$a3$$,
          $$Classification that learns.$$,
          $$$$,
          $$Transactions, products and tickets sorted automatically, and corrected once rather than every month.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_apps$$,
          $$a4$$,
          $$AI search visibility.$$,
          $$$$,
          $$Whether the assistants your customers now ask are recommending you, and what it takes to change that.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_proof$$,
          $$r1$$,
          $$916 catalogue pages, scored and rewritten$$,
          $$$$,
          $$$$,
          $$$$,
          $$/work/ai-seo-catalog$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_proof$$,
          $$r2$$,
          $$Statements in, categorised spending out$$,
          $$$$,
          $$$$,
          $$$$,
          $$/work/statement-intelligence$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_buttons$$,
          $$b1$$,
          $$How we approach AI$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#optimize-with-ai$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_ai_buttons$$,
          $$b2$$,
          $$Talk about your data$$,
          $$$$,
          $$$$,
          $$$$,
          $$/contact$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_process_steps$$,
          $$s1$$,
          $$Map$$,
          $$$$,
          $$We follow one record end to end and time what it costs today.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_process_steps$$,
          $$s2$$,
          $$Prototype$$,
          $$$$,
          $$A working screen you can log into, before we build the real one.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_process_steps$$,
          $$s3$$,
          $$Build$$,
          $$$$,
          $$Working software in front of you every week.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_process_steps$$,
          $$s4$$,
          $$Deploy$$,
          $$$$,
          $$On your server, in Docker, with your data.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_process_steps$$,
          $$s5$$,
          $$Support$$,
          $$$$,
          $$We stay on for changes, or hand over clean.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$retail-ecommerce$$,
          $$Retail & ecommerce$$,
          $$Multi-store stock, pricing, catalogue$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$wholesale-distribution$$,
          $$Wholesale & distribution$$,
          $$Purchasing, order entry, invoicing$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$warehouse-logistics$$,
          $$Warehouse & logistics$$,
          $$Scanning, bins, picking, shipping$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$legal-services$$,
          $$Legal services$$,
          $$Client intake, documents, case files$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$professional-services$$,
          $$Professional services$$,
          $$Client portals, statements, reporting$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_sectors$$,
          $$food-beverage$$,
          $$Food & beverage$$,
          $$Lot tracking, replenishment, margins$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          5)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$home_tech$$,
          $$tech$$,
          $$$$,
          $$BUILT WITH$$,
          $$$$,
          $$Python
Flask
FastAPI
PostgreSQL
Docker
nginx
JavaScript
React
TypeScript
Shopify GraphQL
Stripe
SQL Server
Redis
Celery
Tesseract OCR$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_steps$$,
          $$s1$$,
          $$Map$$,
          $$We learn your process before we propose anything.$$,
          $$We sit with the people doing the work and follow one record end to end — an order, a delivery, a new product. We count the systems it touches, the steps a person performs, and the minutes each takes. Most projects change shape here, because the expensive problem is rarely the one that got us called.$$,
          $$A written process map
A timed cost of the current workaround
A scoped recommendation — including the honest answer if the right move is to buy something instead of build$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_steps$$,
          $$s2$$,
          $$Prototype$$,
          $$You use a working screen before we build the real one.$$,
          $$We build the narrowest version of the thing that proves it works — usually one workflow against real data, running on our infrastructure. Your team clicks it. Assumptions that were wrong become obvious in a week rather than in month four, which is the entire point of doing it.$$,
          $$A live prototype you can log into and try
A revised scope with a fixed price
A written list of what we got wrong in Map$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_steps$$,
          $$s3$$,
          $$Build$$,
          $$Short cycles, working software, no dark months.$$,
          $$We build in one-to-two week cycles against the agreed scope. You see the running system at the end of each one. Integrations are written against your real systems from the start, in a sandbox where the vendor provides one, because integration surprises found late are the main reason software projects overrun.$$,
          $$A running system that grows every cycle
A short written update after each cycle
Access to the repository from day one$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_steps$$,
          $$s4$$,
          $$Deploy$$,
          $$One command to install, on your infrastructure or ours.$$,
          $$The system ships as a Docker Compose stack with healthchecks, plain-SQL migrations that run at boot, and a one-line installer that handles install, update and remove. We run it alongside your existing process until the numbers agree, then switch over. We train your team on the screens they will actually use.$$,
          $$Production deployment, the installer and backups configured
A short operator guide
A training session recorded for the next hire$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_steps$$,
          $$s5$$,
          $$Support$$,
          $$The people who built it are the people who maintain it.$$,
          $$Software that touches other companies' APIs needs someone watching it. We monitor the services we run, fix what breaks, and keep up with the platform version changes that arrive whether you asked for them or not. Most clients keep a small monthly retainer; some take the code and run it themselves.$$,
          $$Monitored services and an agreed response time
A monthly note on what changed
A standing option to walk away with everything$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_pricing$$,
          $$r1$$,
          $$Onboarding is a fixed fee$$,
          $$$$,
          $$A flat onboarding fee covers Map and Prototype. It is deliberately small — it exists so both of us can decide properly before anyone commits to a build.$$,
          $$$$,
          $$$$,
          $$$$,
          $${"title_setting": "onboarding_fee", "body_setting": "onboarding_fee_note"}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_pricing$$,
          $$r2$$,
          $$A fixed price per phase$$,
          $$$$,
          $$Build work is quoted once the prototype has settled the scope, which means the number you approve is the number you pay.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_pricing$$,
          $$r3$$,
          $$Two to four weeks$$,
          $$$$,
          $$A working prototype in the first week or two, and a system your team is using one or two weeks after that. Larger builds spanning several external systems run longer — the case studies name their real timelines.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$process_pricing$$,
          $$r4$$,
          $$Support you can cancel$$,
          $$$$,
          $$A modest monthly retainer, and you keep the code and the data whether or not you keep us.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$distribution-wholesale$$,
          $$Distribution & wholesale$$,
          $$$$,
          $$Your back office was built for a phone-and-fax business and now has to feed a storefront, a marketplace and a warehouse. Stock counts drift because reservations live in one system and sales happen in another. Purchasing runs on a spreadsheet and someone's memory of what moved last month. We make the numbers agree and the reorders defensible.$$,
          $$A back office built for phone and fax, now feeding three channels
Reservations in one system, sales in another, counts that drift
Buying decided by a spreadsheet and last month's memory$$,
          $$$$,
          $$$$,
          $${"caps": "True sellable-stock computed across every channel and pushed on a schedule\nReorder points from real sales velocity, with per-product overrides\nBarcode and price consistency across multiple back-office databases", "cases": "realtime-inventory-sync | Stop overselling across every storefront\ndemand-driven-purchasing | Reorder points that follow real demand\nbarcode-price-integrity | One barcode truth across every system"}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$retail-ecommerce$$,
          $$Multi-store retail & e‑commerce$$,
          $$$$,
          $$Every new product means the same data typed into six places, and every one of them is a chance to be wrong. Prices and barcodes disagree between stores. A unit reserved on one channel is still for sale on another, so you oversell, then hold back stock to compensate — and that cushion is capital doing nothing. We give you one place where the truth lives.$$,
          $$The same new product typed into six places
Prices and barcodes that disagree between stores
Stock held back to cover for overselling$$,
          $$$$,
          $$$$,
          $${"caps": "Add a SKU once; it reaches the ERP and every storefront with images and variants\nAutomatic publish and unpublish as availability crosses zero\nAI-assisted catalogue SEO with a human approving every published change", "cases": "product-onboarding-automation | Add a product once, everywhere\nrealtime-inventory-sync | Stop overselling across every storefront\nai-seo-catalog | 916 catalogue pages, scored and rewritten"}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$warehousing-3pl$$,
          $$Warehousing & 3PL$$,
          $$$$,
          $$The floor runs on paper and on the two people who know how it really works. A short delivery is found weeks later at reconciliation. Nobody can say who packed the order that went out wrong. Counts happen once a year because they take the building offline. We put a scanner in the workflow and an audit trail behind every scan.$$,
          $$The floor runs on paper and on two people's memory
Short deliveries found weeks later, at reconciliation
Counts once a year, because they take the building offline$$,
          $$$$,
          $$$$,
          $${"caps": "Scan-verify inbound deliveries against the purchase order at the door\nBin and slot tracking with transactional quantity updates\nPer-packer accountability and mobile cycle counts written to an audit table", "cases": "warehouse-floor-suite | Four scan stations, one shared source of truth\nrealtime-inventory-sync | Stop overselling across every storefront"}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$professional-services$$,
          $$Professional services$$,
          $$$$,
          $$The work is billable and the admin is not, yet the admin is what fills the evenings — chasing statuses, rebuilding the same report, retyping a client's details into the third system this week. And your website is a change request to an agency who take a fortnight and charge for a paragraph. We automate the admin and hand you the keys to the site.$$,
          $$Evenings spent on admin nobody can bill
The same report rebuilt by hand every month
A fortnight and an invoice to change one paragraph$$,
          $$$$,
          $$$$,
          $${"caps": "Client portals and intake flows that create the record without a phone call\nScheduled reporting and document generation from live data\nWebsites with a real CMS, so your team edits pages, media and navigation", "cases": "owner-editable-website | Websites the owner can actually edit\nlegal-intake-portal | Intake without the clipboard or the callback"}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$legal$$,
          $$Legal$$,
          $$$$,
          $$Intake is a clipboard, a phone call and a spreadsheet, and the first honest answer a potential client gets about their case is weeks away. Leads go cold in an inbox. Nobody can say which stage a matter is at without asking. And every change to the intake questions is a developer ticket. We make intake self-service and the pipeline visible.$$,
          $$Intake is a clipboard, a phone call and a spreadsheet
Leads going cold in an inbox
A developer ticket to change one intake question$$,
          $$$$,
          $$$$,
          $${"caps": "No-login guided questionnaires that produce a transparent range summary immediately\nLeads converted into tracked accounts through a defined stage pipeline with email notifications\nDrag-and-drop questionnaire and template building, with no developer involved", "cases": "legal-intake-portal | Intake without the clipboard or the callback\nowner-editable-website | Websites the owner can actually edit"}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$industries_sectors$$,
          $$finance-accounting$$,
          $$Finance & accounting$$,
          $$$$,
          $$Statements arrive as CSV from one bank, Excel from another and a scanned PDF from the third, and somebody spends a day a month turning them into rows. Categorisation is redone from scratch every period because nothing remembers last time's decisions. Reconciliation is a game of find-the-duplicate. We automate the ingestion and keep the judgement with you.$$,
          $$CSV from one bank, Excel from the next, a scan from the third
A day a month spent turning statements into rows
Categorisation redone from scratch every period$$,
          $$$$,
          $$$$,
          $${"caps": "CSV, Excel and scanned-PDF statement import with automatic bank detection and OCR\nCategorisation that learns from your corrections, with AI suggestions never auto-confirmed\nDuplicate detection at preview, before anything is committed", "cases": "statement-intelligence | Statements in, categorised spending out\nowner-editable-website | Websites the owner can actually edit"}$$::jsonb,
          5)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$services_shapes$$,
          $$s1$$,
          $$A single integration$$,
          $$FROM 2 WEEKS$$,
          $$Two systems that should already be talking. Usually two to four weeks, fixed price.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$services_shapes$$,
          $$s2$$,
          $$A system your team lives in$$,
          $$FROM 6 WEEKS$$,
          $$A full application for one part of the business — the floor, the desk, the portal.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$services_shapes$$,
          $$s3$$,
          $$Ongoing partner$$,
          $$MONTHLY$$,
          $$A monthly arrangement: changes, monitoring and the next phase, without a new contract each time.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_beliefs$$,
          $$b1$$,
          $$Watch first, build second$$,
          $$$$,
          $$The best specification is an afternoon spent next to the person doing the job by hand.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_beliefs$$,
          $$b2$$,
          $$Small pieces, in production$$,
          $$$$,
          $$A system that ships in phases earns its budget back before the last phase is written.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_beliefs$$,
          $$b3$$,
          $$Your server, your source$$,
          $$$$,
          $$Everything runs in Docker on infrastructure you control, with the code in your repository.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_beliefs$$,
          $$b4$$,
          $$Plain language$$,
          $$$$,
          $$Weekly notes an owner can read. Jargon usually hides an unfinished decision.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_stats$$,
          $$s1$$,
          $$10$$,
          $$systems in production$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_stats$$,
          $$s2$$,
          $$6$$,
          $$industries served$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_stats$$,
          $$s3$$,
          $$486$$,
          $$commits on the largest build$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$about_stats$$,
          $$s4$$,
          $$1 day$$,
          $$typical reply time$$,
          $$$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$contact_steps$$,
          $$n1$$,
          $$We reply within one business day.$$,
          $$$$,
          $$A real answer from the person who would do the work, not an auto-responder.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$contact_steps$$,
          $$n2$$,
          $$A 30-minute call.$$,
          $$$$,
          $$You walk us through the slow part. We ask about volumes, systems and who touches what.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$contact_steps$$,
          $$n3$$,
          $$A written summary and a price.$$,
          $$$$,
          $$What we would build first, what it costs, and an honest note if you do not need us.$$,
          $$$$,
          $$$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e1$$,
          $$Work$$,
          $$$$,
          $$$$,
          $$$$,
          $$/work$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e2$$,
          $$Services$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e3$$,
          $$Process$$,
          $$$$,
          $$$$,
          $$$$,
          $$/process$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e4$$,
          $$Industries$$,
          $$$$,
          $$$$,
          $$$$,
          $$/industries$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e5$$,
          $$About$$,
          $$$$,
          $$$$,
          $$$$,
          $$/about$$,
          $$$$,
          $${}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_explore$$,
          $$e6$$,
          $$Blog$$,
          $$$$,
          $$$$,
          $$$$,
          $$/blog$$,
          $$$$,
          $${}$$::jsonb,
          5)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b1$$,
          $$Custom web apps$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#custom-web-apps$$,
          $$$$,
          $${}$$::jsonb,
          0)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b2$$,
          $$Systems integration$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#systems-integration$$,
          $$$$,
          $${}$$::jsonb,
          1)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b3$$,
          $$Business automation$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#business-automation$$,
          $$$$,
          $${}$$::jsonb,
          2)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b4$$,
          $$Optimize with AI$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#optimize-with-ai$$,
          $$$$,
          $${}$$::jsonb,
          3)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b5$$,
          $$Mobile & floor tools$$,
          $$$$,
          $$$$,
          $$$$,
          $$/services#mobile-apps$$,
          $$$$,
          $${}$$::jsonb,
          4)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
INSERT INTO content_blocks
  (group_key, block_key, title, subtitle, body, items, link_url, link_label, extra, sort_order)
  VALUES ($$footer_build$$,
          $$b6$$,
          $$Case studies$$,
          $$$$,
          $$$$,
          $$$$,
          $$/work$$,
          $$$$,
          $${}$$::jsonb,
          5)
  ON CONFLICT (group_key, block_key) WHERE block_key <> '' DO NOTHING;
