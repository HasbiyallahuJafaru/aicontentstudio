-- 2026-11-08: quote images and narrated videos can be posted too. A piece's posts carry its id (clip posts leave it
-- NULL); clip_idx then holds the piece's number so the row still sorts and reads like a clip post.
ALTER TABLE publications ADD COLUMN piece_id TEXT;
