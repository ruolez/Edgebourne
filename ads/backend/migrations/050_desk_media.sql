-- The Claude page shows and takes more than Claude's own pictures and videos (2026-11-14, Eugene: "show previews of
-- images or videos or pages", "attach my own files"):
--   * a page Claude built (a landing-page draft, a comparison sheet): kind 'page', kept as one self-contained HTML
--     file and served with scripts off;
--   * a file a person sends with a message (a raw clip, a photo, a screenshot): source 'user'. It is uploaded while the
--     message is being written (task_id NULL) and tied to the message when that is sent; iPhone clips are QuickTime;
--   * something already in the account an answer shows large (an ad as Meta shows it, a lead form): desk_tasks.shows,
--     a list of {type, id, name, caption, placement}. Nothing is copied: the page reads the ad or form when it draws it.
ALTER TABLE desk_attachments DROP CONSTRAINT desk_attachments_kind_check;
ALTER TABLE desk_attachments ADD CONSTRAINT desk_attachments_kind_check CHECK (kind IN ('image', 'video', 'page'));
ALTER TABLE desk_attachments DROP CONSTRAINT desk_attachments_mime_check;
ALTER TABLE desk_attachments ADD CONSTRAINT desk_attachments_mime_check
    CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/quicktime', 'text/html'));
ALTER TABLE desk_attachments ADD COLUMN source TEXT NOT NULL DEFAULT 'claude' CHECK (source IN ('claude', 'user'));
ALTER TABLE desk_attachments ADD COLUMN created_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE desk_attachments ALTER COLUMN task_id DROP NOT NULL;
-- Only a person's file may wait for its message; what Claude attaches always belongs to a request.
ALTER TABLE desk_attachments ADD CONSTRAINT desk_attachments_unsent_check CHECK (task_id IS NOT NULL OR source = 'user');
CREATE INDEX desk_attachments_unsent ON desk_attachments (created_at) WHERE task_id IS NULL;

ALTER TABLE desk_tasks ADD COLUMN shows JSONB NOT NULL DEFAULT '[]';
