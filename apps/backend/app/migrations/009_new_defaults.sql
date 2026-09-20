-- New content defaults: blank topic (nothing pre-filled), one piece at a time, Kokoro's am_adam as the studio voice.
-- Only rewrites values still sitting on the previous defaults, so a deliberate choice is never overwritten.
UPDATE settings SET value = json_set(value, '$.default_topic', '')
 WHERE key = 'app' AND json_extract(value, '$.default_topic') = 'discipline';

UPDATE settings SET value = json_set(value, '$.default_quantity', 1)
 WHERE key = 'app' AND json_extract(value, '$.default_quantity') = 6;

UPDATE settings SET value = json_set(value, '$.tts_voice', 'am_adam')
 WHERE key = 'app' AND json_extract(value, '$.tts_voice') = '';
