-- Milestone 7 Phase B: the ClipperAi engine. One row per clipped moment of a clip project's source video.

CREATE TABLE clips (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    start_at    REAL NOT NULL,              -- seconds into the source
    end_at      REAL NOT NULL,
    score       INTEGER NOT NULL,           -- model's 0-100 clip score
    reason      TEXT NOT NULL,              -- why the moment works (pass 1)
    hook        TEXT NOT NULL,              -- on-screen opening line
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    hashtags    TEXT NOT NULL,              -- json array
    posts       TEXT NOT NULL,              -- json {network: post copy}
    status      TEXT NOT NULL DEFAULT 'ready',   -- ready | approved | rejected | exported
    video_path  TEXT,                       -- relative to the media folder
    cover_path  TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX clips_project ON clips (project_id);
