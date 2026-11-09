-- 2026-11-09: AI max tokens was capped at 8192, which was also its default, so every saved settings row holds 8192
-- and the "raise AI max tokens" advice could never be followed. The cap is now 32768 and the default 16384: lift
-- rows still on the old ceiling to the new default (a lower value someone chose is left alone).
UPDATE settings SET value = json_set(value, '$.ai_max_tokens', 16384)
WHERE key = 'app' AND json_extract(value, '$.ai_max_tokens') = 8192;
