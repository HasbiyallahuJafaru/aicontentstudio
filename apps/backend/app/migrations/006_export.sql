-- Milestone 6: render facts for the preview indicators, and one row per export run.

ALTER TABLE renders ADD COLUMN fps REAL;     -- videos: source fps the render preserved (PRD 40 indicators)
ALTER TABLE renders ADD COLUMN width INTEGER;
ALTER TABLE renders ADD COLUMN height INTEGER;

CREATE TABLE exports (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    dir         TEXT NOT NULL,              -- relative to the data folder
    pieces      INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX exports_project ON exports (project_id);
