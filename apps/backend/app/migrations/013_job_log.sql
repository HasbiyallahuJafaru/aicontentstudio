-- 2026-11-08: every job keeps a step log (JSON list of {step, status, secs, error?, detail?}) so the app can show
-- exactly which step of which piece is running, finished or failed, during the job and after it.
ALTER TABLE generation_jobs ADD COLUMN log TEXT;
