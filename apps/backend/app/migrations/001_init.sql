-- Milestone 1. Later tables (content_pieces, assets, asset_usage, renders, audio_assets,
-- generation_jobs, export_jobs) arrive with the phase that first uses them.

CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','queued','generating','rendering','ready','approved','exported','failed')),
    brief       TEXT NOT NULL,              -- CreativeBrief JSON
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX projects_created ON projects (created_at DESC);

CREATE TABLE settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL                    -- JSON
);
