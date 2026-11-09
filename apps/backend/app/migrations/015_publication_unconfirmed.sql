-- 2026-11-09: a post whose request may have reached Zernio with no answer back (a timeout, a dropped reply). A retry
-- reuses the row's id as the Idempotency-Key, so the same post can never go out twice.
ALTER TABLE publications ADD COLUMN unconfirmed INTEGER NOT NULL DEFAULT 0;
