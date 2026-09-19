-- Milestone 3: downloaded visual assets and where pieces used them.
-- Analysis columns (dominant_colors, brightness, saturation, contrast) are placeholders until M4, motion_score until M5.

CREATE TABLE assets (
    id                TEXT PRIMARY KEY,
    provider          TEXT NOT NULL CHECK (provider IN ('pexels','unsplash')),
    provider_asset_id TEXT NOT NULL,
    asset_type        TEXT NOT NULL CHECK (asset_type IN ('image','video')),
    creator           TEXT NOT NULL DEFAULT '',
    license           TEXT NOT NULL DEFAULT '',
    source_url        TEXT NOT NULL DEFAULT '',   -- provider page, for attribution
    local_path        TEXT NOT NULL,              -- relative to the media folder
    thumb_path        TEXT NOT NULL DEFAULT '',   -- relative to the media folder
    width             INTEGER NOT NULL DEFAULT 0,
    height            INTEGER NOT NULL DEFAULT 0,
    fps               REAL NOT NULL DEFAULT 0,    -- videos only
    duration          REAL NOT NULL DEFAULT 0,    -- videos only, seconds
    hash              TEXT NOT NULL DEFAULT '',   -- sha256 of the downloaded file (exact duplicates)
    perceptual_hash   TEXT NOT NULL DEFAULT '',   -- dHash of the thumbnail (visually similar)
    dominant_colors   TEXT NOT NULL DEFAULT '[]', -- M4
    brightness        REAL,                       -- M4
    saturation        REAL,                       -- M4
    contrast          REAL,                       -- M4
    motion_score      REAL,                       -- M5
    themes            TEXT NOT NULL DEFAULT '[]', -- M4: visual categories for the category cooldown
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (provider, provider_asset_id)
);
CREATE INDEX assets_type ON assets (asset_type, created_at DESC);

CREATE TABLE asset_usage (
    asset_id   TEXT NOT NULL REFERENCES assets (id) ON DELETE CASCADE,
    piece_id   TEXT NOT NULL REFERENCES content_pieces (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (asset_id, piece_id)
);
CREATE INDEX asset_usage_asset ON asset_usage (asset_id, created_at DESC);
