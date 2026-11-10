-- Roadmap 5.1: one value per ad per dimension, so results can be grouped by idea.
CREATE TABLE ad_tags (
    ad_id TEXT NOT NULL,
    dimension TEXT NOT NULL CHECK (dimension IN ('hook', 'angle', 'persona', 'format', 'offer')),
    value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'claude', 'seed', 'copied')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ad_id, dimension)
);
CREATE INDEX ad_tags_dim_idx ON ad_tags (dimension, value);

-- N1–N5 and N1 v2, from the creative round notes (creatives/2026-11-07-new5/README.md, "one audience per ad").
INSERT INTO ad_tags (ad_id, dimension, value, source) VALUES
('120252672229040312', 'hook', 'Pain statement', 'seed'), ('120252672229040312', 'angle', 'One simple system', 'seed'),
('120252672229040312', 'persona', 'Owner-operators on paper and spreadsheets', 'seed'),
('120252690325970312', 'hook', 'Pain statement', 'seed'), ('120252690325970312', 'angle', 'One simple system', 'seed'),
('120252690325970312', 'persona', 'Owner-operators on paper and spreadsheets', 'seed'),
('120252672229400312', 'hook', 'Outcome promise', 'seed'), ('120252672229400312', 'angle', 'Customers order online', 'seed'),
('120252672229400312', 'persona', 'Wholesale and distribution', 'seed'),
('120252672230740312', 'hook', 'Command', 'seed'), ('120252672230740312', 'angle', 'Connect your systems', 'seed'),
('120252672230740312', 'persona', 'Businesses on several systems', 'seed'),
('120252672232030312', 'hook', 'Question', 'seed'), ('120252672232030312', 'angle', 'Reports that build themselves', 'seed'),
('120252672232030312', 'persona', 'Ops and office managers', 'seed'),
('120252672233160312', 'hook', 'Outcome promise', 'seed'), ('120252672233160312', 'angle', 'Quote to invoice in one flow', 'seed'),
('120252672233160312', 'persona', 'Service businesses that quote jobs', 'seed')
ON CONFLICT DO NOTHING;
INSERT INTO ad_tags (ad_id, dimension, value, source)
SELECT id, d.dim, d.val, 'seed' FROM (VALUES ('120252672229040312'), ('120252690325970312'), ('120252672229400312'),
    ('120252672230740312'), ('120252672232030312'), ('120252672233160312')) AS a(id)
CROSS JOIN (VALUES ('format', '9 s motion video, 4:5'), ('offer', 'Free intro call')) AS d(dim, val)
ON CONFLICT DO NOTHING;

-- Claude can suggest tags (a Polish or review run); approving applies them.
ALTER TABLE desk_proposals DROP CONSTRAINT desk_proposals_kind_check;
ALTER TABLE desk_proposals ADD CONSTRAINT desk_proposals_kind_check
    CHECK (kind IN ('budget', 'status', 'creative', 'targeting', 'experiment', 'tags', 'other'));
