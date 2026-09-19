-- Milestone 2: generated content and the jobs that produce it.

CREATE TABLE content_pieces (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,           -- 1-based position in the batch
    status      TEXT NOT NULL DEFAULT 'written'
                CHECK (status IN ('written','rendering','ready','approved','exported','failed')),
    angle       TEXT NOT NULL,
    quote       TEXT NOT NULL,              -- denormalised for similarity checks against history
    content     TEXT NOT NULL,              -- PieceContent JSON (+ plan item)
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (project_id, idx)
);
CREATE INDEX content_pieces_created ON content_pieces (created_at DESC);

CREATE TABLE generation_jobs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','completed','failed','cancelled')),
    stage       TEXT NOT NULL DEFAULT '',
    progress    REAL NOT NULL DEFAULT 0,    -- 0..1, derived from real pipeline steps
    error       TEXT,                       -- {"message","detail"} JSON when failed
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX generation_jobs_project ON generation_jobs (project_id, created_at DESC);
