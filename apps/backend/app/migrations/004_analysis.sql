-- Milestone 4: deterministic visual analysis of every downloaded asset (PRD §22, §77 quality filter).
-- Runs on the thumbnail, once at download time; motion_score still waits for M5 (needs FFmpeg frames).

ALTER TABLE assets ADD COLUMN subject_position TEXT NOT NULL DEFAULT '';  -- left | center | right
ALTER TABLE assets ADD COLUMN visual_complexity REAL;
ALTER TABLE assets ADD COLUMN temperature   TEXT NOT NULL DEFAULT '';     -- warm | neutral | cool
ALTER TABLE assets ADD COLUMN quality_score REAL;
