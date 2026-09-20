-- Milestone 7 Phase C: publishing integrations. One row per attempt to send a clip somewhere, and a
-- DPAPI-encrypted store for connection secrets (Buffer OAuth tokens, hosting keys) the Python side owns.

CREATE TABLE credentials (
    name        TEXT PRIMARY KEY,           -- 'buffer', 'publish_host', 'oauth:<state>'
    data        TEXT NOT NULL,              -- base64 DPAPI blob (plaintext JSON only off-Windows)
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE publications (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    clip_idx       INTEGER NOT NULL,
    provider       TEXT NOT NULL DEFAULT 'buffer',
    channel_id     TEXT NOT NULL,
    service        TEXT NOT NULL,
    channel_name   TEXT NOT NULL,
    status         TEXT NOT NULL,           -- scheduled | sent | error | canceled
    due_at         TEXT,
    sent_at        TEXT,
    external_id    TEXT,                    -- Buffer post id
    external_link  TEXT,
    error          TEXT,
    checked_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX publications_project ON publications (project_id);
