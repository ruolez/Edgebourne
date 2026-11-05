-- 020_free_call_cta.sql
--
-- The closing call to action on /process led with the paid Map step ("Map is
-- a small fixed fee"). The ask at the end of a page is the free call, so it
-- now says that, and the button on every closing call to action names it.
--
-- Guarded on the wording live today, so a re-run is a no-op and admin edits
-- stand.

UPDATE content_blocks
   SET title = $$Start with a free call.$$,
       body = $$Walk us through your process, idea or a problem. In 30 minutes we'll talk through how we can help and what it would take.$$,
       updated_at = now()
 WHERE group_key = 'page_cta' AND block_key = 'process'
   AND replace(title, chr(13), '') = $$Start at step one.$$
   AND replace(body, chr(13), '') = $$Map is a small fixed fee. You end up with a written process map and an honest recommendation — including the one where you buy something instead of building it.$$;

UPDATE content_blocks
   SET link_label = $$Book a free call$$, updated_at = now()
 WHERE group_key = 'page_cta' AND block_key = 'default' AND link_label = $$Book a call$$;
