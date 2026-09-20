-- Hopecore is the default genre, and the studio voice is Kokoro's am_adam rather than a SAPI voice.
-- Rows still holding the previous shipped defaults ('cinematic' predates the tone->genre swap) move forward;
-- anything the user deliberately changed is left alone.
UPDATE settings SET value = json_set(value, '$.default_tone', 'hope')
 WHERE key = 'app' AND json_extract(value, '$.default_tone') IN ('cinematic', 'cinema');

UPDATE settings SET value = json_set(value, '$.tts_provider', 'kokoro')
 WHERE key = 'app' AND json_extract(value, '$.tts_provider') = 'windows';
