-- 2026-11-08: there is no approve step any more (owner: post or "Schedule all" straight from a render). Anything
-- approved before then becomes plain ready, so no "Approved" label is left anywhere.
UPDATE clips SET status = 'ready' WHERE status = 'approved';
UPDATE content_pieces SET status = 'ready' WHERE status = 'approved';
