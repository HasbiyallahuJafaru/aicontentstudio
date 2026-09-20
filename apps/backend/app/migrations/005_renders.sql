-- Milestone 5: rendered outputs per piece. Rendering rides the existing job system via jobs.kind.

ALTER TABLE generation_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'generate';

CREATE TABLE renders (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    piece_id    TEXT NOT NULL REFERENCES content_pieces (id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('video','image')),
    local_path  TEXT NOT NULL,              -- relative to the media folder
    duration    REAL,                       -- seconds, videos only
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX renders_piece ON renders (piece_id);
