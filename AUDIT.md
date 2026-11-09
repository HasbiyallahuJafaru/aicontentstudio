# System audit tracker (2026-11-09)

Full audit of the app: render pipeline, clipper, AI writing, jobs/data/posting, desktop UI. Work through it phase by
phase. When an item is fixed: tick it, add the date and one line on how it was verified (test name, ffprobe check,
real post). Items marked **(verified)** were reproduced or confirmed in code during the audit; the rest come from
code reading and should be confirmed before fixing.

Severity: **C** critical · **H** high · **M** medium · **L** low. Status: `[ ]` open · `[x]` fixed · `[-]` won't fix
(say why).

---

## Already fixed

- [x] **R0 (C) Posted videos warp their first ~3 s.** `loudnorm` misstamped the opening AAC packets (1 sample apart
  for 0.64 s, then a jump to 3.0 s); local players ignore it, platform transcoders obey it.
  Fix: `loudnorm=...,aresample=48000,asetpts=N/SR/TB` in `clipper/render_clip.py` and `render.py`, plus guard
  `render.audio_misstamped` (in `validate_video` and after every clip render).
  Verified 2026-11-09: reproduced on a 12 s real clip, fixed output has 0 misstamped packets, real 14 s two-range clip
  renders clean, test `AudioStamps`, backend 225/225 OK. **Still open:** re-post a fresh render to confirm on a platform;
  old renders still carry the bug (re-render, or re-encode audio only with `-c:v copy`).

---

## Phase 1: render correctness (every post is affected)

Status 2026-11-09: done except R10 (zoompan stair-step, suspected, needs a visual check) and R15 (platform
spec research). Backend tests 226/226 OK. Not yet verified: a real post of a new render; full `npm test` smoke.

- [x] **R1 (C, verified) zoompan re-times shots to the output fps.** `render.py:244-253`. `zoompan d=1:fps=N` emits
  one frame per input frame stamped at the output rate: 25 fps source at 30 out plays 1.2x fast (4 s became 3.33 s),
  59.94 fps plays at half speed, `-loop 1` stills (read at 25 fps) shrink. Video ends seconds before the audio, cuts
  drift off the narration. Fix: `fps={fps}` before zoompan in `geom`; `-framerate {fps}` on the `-loop 1` input.
  **Fixed 2026-11-09:** `fps` conform before zoompan, `-framerate` on stills. Harness: 25/60 fps and still-first cases went from 1.5-3.0 s of video to exactly 3.6 s / 108 frames; test `test_mixed_frame_rates_keep_their_planned_length`.
- [x] **R2 (H) Quality check can't see R1.** `render.py` `validate_video` compares `format.duration` (the longest
  stream). Fix: check the video stream's own duration / `nb_frames/fps` to about one frame, and audio separately.
  **Fixed 2026-11-09:** `validate_video` checks each stream's own length (±0.25 s) and yuv420p limited range.
- [x] **R3 (H) Film grain blows the bitrate.** `edit.py` LOOKS grain, encoded CRF-only at `render.py:339`. Grain 8
  (speech) = 24.5 Mbps, grain 10 (history) = 50.7 Mbps; a 60 s piece is about 380 MB, over the Instagram Reels cap,
  and platforms turn temporal grain into blocks. Fix: `-maxrate 10M -bufsize 20M`; cap grain at 5 or use static `allf=u`.
  **Fixed 2026-11-09:** `-maxrate 12M -bufsize 24M` on both encoders (`render.DELIVERY`); grain capped at 5 in `edit.LOOKS` (speech 8, history 10, mono 6 were the outliers).
- [x] **R4 (H) Stills make the output full range / BT.601.** Any timeline containing a still comes out `yuvj420p`,
  range pc, matrix bt470bg; `format=yuv420p` doesn't reset it. Fix: `scale=out_range=tv:out_color_matrix=bt709` before
  the final format, plus `-color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709`.
  **Fixed 2026-11-09:** `scale=out_range=tv:out_color_matrix=bt709` + `setparams` before `[vout]`; still-first renders now yuv420p/tv/bt709.
- [x] **R5 (L) Colour tags partial on every output** (clips: `color_space=unknown`). Same tag flags on both encoders
  (`render.py:339`, `render_clip.py:64`).
  **Fixed 2026-11-09:** Frames tagged with `setparams` (CLI flags alone don't stick in ffmpeg 9); renders and clips probe tv/bt709/bt709/bt709.
- [x] **R6 (M) Speed-ramp shot drops to ~15 fps and makes the file VFR.** `render.py:232/256`, `setpts=1.8*PTS` after
  zoompan with no `fps`. Zoom also reaches only 1/1.8 of its target. Fix: `setpts` before zoompan, `fps={fps}` after,
  optionally `-fps_mode cfr`.
  **Fixed 2026-11-09:** Ramp `setpts` now before the `fps` conform; ramp case has no frame gaps, CFR.
- [x] **R7 (M) Audio ends 0.6 s before the video; music fade cut off.** `render.py:324-332`, `amix duration=first`
  follows the narration. Fix: `apad=whole_dur={duration}` on `[na]` before `asplit`.
  **Fixed 2026-11-09:** `apad=whole_dur` on the narration; audio = video = 3.6 s in every harness case.
- [x] **R8 (M) Clip captions drift behind the voice** (~0.18 s over 28 joins). `render_clip.py:41-49` vs
  `tighten.retime`: trims round to the frame grid, captions use exact sums. Fix: snap range edges to `round(t*fps)/fps`
  before `retime` and render.
  **Fixed 2026-11-09:** Ranges snapped to the source frame grid (`ff.frame_rate`) before `retime`; 28-range test: video = audio, within one frame of caption timing.
- [x] **R9 (L) Keyframe interval ~8 s** (x264 default 250). Fix: `-g {2*fps}` on both encoders.
  **Fixed 2026-11-09:** `-force_key_frames expr:gte(t,n_forced*2)`: keyframes every 2.0 s, checked by ffprobe.
- [ ] **R10 (M, suspected) zoompan stair-steps on video shots** (only stills are supersampled). Fix: supersample video
  shots too, or scale+crop with float expressions.
- [x] **R11 (L) Music + narration can clip** (`amix normalize=0`, no limiter). Fix: `alimiter=limit=0.89` after amix.
  **Fixed 2026-11-09:** `alimiter=limit=0.89` after the music `amix`.
- [x] **R12 (L) Odd render sizes allowed** (`settings.py:61-62`); libx264 fails on them. Validate/round to even.
  **Fixed 2026-11-09:** `Settings._even` rounds render width/height down to even.
- [x] **R13 (L) Apostrophe in the Windows username breaks subtitled renders** (`render.py:294-296`, absolute `ass='...'`
  path). Fix: relative path + `cwd`, as `render_clip` does.
  **Fixed 2026-11-09:** Subtitle burn runs ffmpeg from the .ass folder with relative names (out/narration resolved absolute).
- [x] **R14 (L) 60 fps default for stills** (`render.py:205`) is effectively dead code and expensive where it fires.
  Default to 30.
  **Fixed 2026-11-09:** Still default is 30 fps; test updated.
- [ ] **R15 (L, suspected) Platform spec gaps:** X max 1200x1900 and 140 s for non-premium; Instagram API documents
  128 kbps audio (we use 192k). Check against Zernio's per-network limits.
- [x] **R16 (H, verified by measurement) Cold-open clip renders use ~4 GB RAM.** `render_clip.py:37-49`: all ranges
  trim one decoded `[0:v]`, the late teaser plays first so concat buffers every body frame (4218 MB vs 347 MB in
  order). Fix: teaser (or every range) gets its own `-ss/-t` input.
  **Fixed 2026-11-09:** Each range is its own `-ss/-t` input. Cold open 1080p, 57 s span: 4903 MB -> 906 MB peak (ffmpeg -benchmark).
- [x] **R17 (M) No stall watchdog on clip renders** (`clipper/ff.py:12`, only a 3600 s timeout). Reuse the
  `-progress` watchdog from `render.py`.
  **Fixed 2026-11-09:** `ff.ffmpeg` uses `-progress` + a 180 s stall watchdog alongside the hard timeout.

## Phase 2: posting safety and data loss

Status 2026-11-09: all 19 done. Backend tests 232/232 OK (6 new in `test_zernio.Safety`), desktop typecheck + build
OK. Not yet verified: clicking through the dialogs in the real app, a real Zernio timeout, `npm test` smoke.

- [x] **P1 (H, verified) Posts can go out twice.** `publish/zernio.py:202-210`: `Idempotency-Key` is a fresh uuid per
  attempt; a timeout after Zernio created the post saves `status='error'` with no external id, and `posts.taken()`
  ignores error rows, so retry posts again. Fix: key from (piece/clip, account, due_at), save a `pending` row before
  sending, look up / reuse the key on retry.
  **Fixed 2026-11-09:** Transport errors on writes and 5xx answers raise `zernio.Unconfirmed`; the row is saved with `unconfirmed=1` (migration 015) and a retry reuses its id as the Idempotency-Key. Test `test_an_unanswered_post_retries_under_the_same_key` (502, then retry: same key, one row). Edge left: a backend crash before the row is saved still gets a fresh key.
- [x] **P2 (H) PostDialog / ScheduleAllDialog close mid-upload.** `components/Posting.tsx:254-266`, `:379-393`,
  `ui.tsx:142-150`: Cancel/X/Escape/backdrop still close while "Uploading to Zernio…", the request keeps running,
  user posts again. Fix: block closing while busy, and send the idempotency key from P1.
  **Fixed 2026-11-09:** `Dialog locked` while uploading: Escape, backdrop, X and Cancel do nothing until Zernio answers (PostDialog, ScheduleAllDialog). Typecheck + build OK; not clicked through in the app.
- [x] **P3 (H) Deleting content leaves its Zernio posts live.** `projects.py:141`, `content.py:184`, `clips.py:116`,
  `storage.py:18`, migration `012` (`piece_id` no FK). Fix: `zernio.unschedule` live rows before deleting, or refuse
  the delete while posts are scheduled.
  **Fixed 2026-11-09:** `posts.release` unschedules waiting posts then drops the rows, from project delete, piece delete, clip delete and Clear storage; refuses (deletes nothing) when Zernio can't be reached. Tests `test_deleting_a_project_unschedules_its_posts`, `test_delete_is_refused_when_zernio_cant_cancel`.
- [x] **P4 (H) Re-clipping attaches old publication chips to new clips.** Publications keyed by `(project_id,
  clip_idx)`; `clips.py:55` deletes clips, not publications. New clip 01 shows "Posted", Schedule all skips it, link
  opens the wrong post. Fix: key publications to clip id, or detach on re-clip. (Also `Clips.tsx:93-95`, `:180`.)
  **Fixed 2026-11-09:** Re-clip refuses while clip posts are scheduled; a successful re-clip clears the old clips' post history with them. Test `test_reclip_is_refused_while_clip_posts_wait`.
- [x] **P5 (H, verified) Clip posting never shows the per-account result.** `Clips.tsx:190-191`: `onChanged` unmounts
  the dialog right after `setSent()`, so `SentList` never renders. Fix: `onDone` refreshes only; close from "Done".
  **Fixed 2026-11-09:** Clip `onChanged` only refreshes; the dialog stays on the per-account result until Done.
- [x] **P6 (H, verified) "Try again" always regenerates the whole batch.** `pages/Project.tsx:139-142`: calls
  `generate()` whatever `job.kind` failed; cancelled text always says "Generation was cancelled"; `jobs.recover()`
  (`jobs.py:193`) writes "Generate again to retry" onto render/clip jobs. Fix: retry the same kind with the same
  `piece_ids`; word messages per kind.
  **Fixed 2026-11-09:** `retry()` restarts the failed job's own kind (render/export/clip/visuals); per-kind cancelled text; `jobs.recover` writes per-kind messages (`STOPPED`). A retried render re-renders every piece, not only the subset that was asked for.
- [x] **P7 (H) Failed/cancelled re-render destroys the good render.** `renders.py:120-175`, `render.py:215/341`,
  `render_clip.py`: ffmpeg `-y` straight onto `NNN-video.mp4`, row still "ready". Fix: render to `*.part.mp4`, replace
  after validation (motion.py already does this).
  **Fixed 2026-11-09:** `render_video` encodes to `*.part.mp4` and `os.replace`s it over the old render only after `validate_video` passes.
- [x] **P8 (M) Re-clip deletes the previous take before the new one succeeds.** `clips.py:55-58`. Fix: render to a
  staging folder and swap rows/files on success.
  **Fixed 2026-11-09:** Re-clip renders into `clips/<pid>.next` and swaps folder + rows in one step at the end. Test `test_a_failed_reclip_keeps_the_previous_take`; `test_clipper_port` checks the swapped path exists.
- [x] **P9 (H, verified) Project delete not refused while a job runs; deletes almost no files.** `projects.py:141-145`.
  Thread crashes with TypeError, ffmpeg keeps writing; `renders/<pid>`, `clips/<pid>`, narration WAVs, clipwork source
  stay forever. Fix: `jobs.ensure_idle(id)`, then remove the project's media.
  **Fixed 2026-11-09:** `projects.delete` calls `jobs.ensure_idle`, releases posts, removes `renders/<pid>` and `clips/<pid>`. (Narration WAVs and clipwork sources: S1.)
- [x] **P10 (H, verified) Two jobs can start on one project** (double-click "Download and render").
  `jobs.py:85-99`: check and INSERT not atomic across 4 RPC threads. Fix: module lock around check+insert, or
  `BEGIN IMMEDIATE` + partial unique index on running jobs.
  **Fixed 2026-11-09:** `jobs._start_lock` around check + insert. Test `test_two_starts_at_once_make_one_job`.
- [x] **P11 (M) Regenerate not blocked during a render; edits lost.** `content.py:197-229`; render writes back stale
  `content_data` (`renders.py:176-195`). Same race in `visuals.pick` (`assets/__init__.py:346`). Fix: `ensure_idle`, or
  write only owned keys.
  **Fixed 2026-11-09:** `content.regenerate` and `visuals.pick` call `jobs.ensure_idle(..., doing)`.
- [x] **P12 (M) Footage picks race "Download and render".** `components/FootageReview.tsx:20-37`: unawaited parallel
  `visuals.pick` calls, no rollback on failure, removing the last shot never saved. Fix: await pending saves (or send
  picks with `jobs.start`), serialise per piece, roll back on error.
  **Fixed 2026-11-09:** Footage picks save one after another per piece, roll back on failure, and Download and render awaits them.
- [x] **P13 (M) Exports of same-named projects overwrite and delete each other.** `export.py:30-51`, `150-158`. Fix:
  add the project id to the folder name.
  **Fixed 2026-11-09:** Exports go to `exports/<date>/<project>-<id6>/`; delete removes only that folder (older shared-folder exports keep the old name matching).
- [x] **P14 (M) Pieces stuck in `rendering`** after cancel or crash (`renders.py:116-118`, `183-184`, `jobs.py:344`).
  Fix: reset to `written` in the Cancelled path and `recover()`; close running job-log steps.
  **Fixed 2026-11-09:** `jobs.UNSTICK` puts a 'rendering' piece back to ready (has renders) or written, on cancel and in `recover()`.
- [x] **P15 (M) A failed export/render marks the whole project "Failed"** (`jobs.py:306-317`, `321`). Fix: only
  `generate`/`clip` change the project status.
  **Fixed 2026-11-09:** Only generate/clip jobs change the project's status (`owns_stage` in `_run`).
- [x] **P16 (L) `posts.schedule` KeyError on missing `due_at`** after earlier items were sent (`posts.py:383/391`).
  **Fixed 2026-11-09:** `posts.schedule` reads `due_at` with `.get` in both places.
- [x] **P17 (L) `publications()` deletes our record on any "not found" message** (`zernio.py:278`, `posts.py:417-420`).
  Only on a real 404 from `/v1/posts/{id}`.
  **Fixed 2026-11-09:** `refresh`/`unschedule` treat only a real `HTTP 404` detail as gone.
- [x] **P18 (L) Error details can carry the signed upload URL** (`zernio.py:139`, `repr(e)`). Show class + message only.
  **Fixed 2026-11-09:** `zernio._why`: class + message in details, never `repr` (no signed upload URL).
- [x] **P19 (L) PostDialog accepts a past date/time**; ScheduleAll's default slot can go stale while open.
  **Fixed 2026-11-09:** Post's time field has `min=now`; Schedule all's stale times are refused per item by the backend with a plain message.

## Phase 3: generation crashes and AI writing bugs

Status 2026-11-09: done (W6 partly). Backend tests 236/236 OK, typecheck OK. Not yet verified: a real generation
with the default reasoning model at ~60 s, and how Gemini TTS sounds with the comma-per-line pauses.

- [x] **W1 (H, verified) "~60 s" length always fails validation.** `creative/prompts.py:203` asks for
  `target_seconds*2.4` words (144 at 60 s); `creative/schemas.py:47` caps narration at 700 chars. 45 s is borderline;
  backend allows 180 s (`projects.py:31`). Fix: raise `max_length` (e.g. 3000) or derive it from the target.
  **Fixed 2026-11-09:** Narration cap 700 -> 3000 characters. Test `test_a_sixty_second_narration_validates_and_keeps_its_lines`.
- [x] **W2 (H, verified) One truncated group reply kills the job.** `creative/model.py:73-77` catches only
  ValueError/AttributeError; `finish_reason=length` raises UserError. The advice "raise AI max tokens" is impossible:
  default 8192 is already the cap (`settings.py:32`). Likely trigger: reasoning model (deepseek-v4-pro) thinking
  tokens + 4 video pieces. Fix: catch UserError, fall back to per-piece writes (or halve the group); raise the cap or
  size groups from `max_tokens`.
  **Fixed 2026-11-09:** `OutOfRoom` (finish_reason=length) is caught by `write_pieces`, so the group falls back to one piece at a time; cap 8192 -> 32768, default 16384, migration 016 lifts saved 8192 rows. Test `test_a_truncated_group_reply_falls_back_to_single_pieces`.
- [x] **W3 (H) Regenerating quote or narration desyncs them.** `content.py:209-226` replaces only one scope; the
  narration speaks the old quote, captions/title stay on the old quote. Fix: narration regen passes the current
  quote as `given_quote`; quote regen also regenerates narration + metadata.
  **Fixed 2026-11-09:** Narration regen writes around the current quote (`given_quote`); quote regen also takes the new narration, hook, callouts and metadata. `test_m6` asserts the given quote.
- [x] **W4 (H) Contradictory prompt for an author-less user quote.** `prompts.py:184` always demands a real author
  while the same message says `author = null`; narration can speak an invented author. Fix: drop the REAL-quote line
  when a quote is given; add "This line has no author: never name or imply one."
  **Fixed 2026-11-09:** The REAL-quote demand is skipped for user quotes; an authorless line adds "This line has no author. Never name or imply one". Test `test_a_fixed_quote_with_no_author_never_asks_for_one`.
- [x] **W5 (M) Line breaks erased before TTS.** `schemas.py:150` `Text` collapses all whitespace, so the "short lines,
  let silence work" pause plan never reaches the voice. Fix: keep newlines, map them to sentence breaks / "..." for TTS.
  **Fixed 2026-11-09:** `schemas.Lines` keeps line breaks (spaces collapse per line); `tts.spoken` turns each unpunctuated line end into a comma for the voice. Same test as W1.
- [x] **W6 (L) Within-batch duplicates only partly guarded.** "No author twice in a batch" (`prompts.py:54`) is never
  enforced; fallback rewrite (`content.py:141`) sees only earlier quote texts. Fix: add accepted openings and authors
  to `avoid`.
  **Fixed 2026-11-09:** Partly: each accepted piece's opening line joins `openings`, so later groups in the batch avoid it. Not done: enforcing "no author twice" in code (the prompt still asks).
- [x] **W7 (L) Quote-image fallback prompt is weak** (facet "quote", "Other pieces cover: none", asks for design hints
  that don't exist). Pass accepted siblings, drop the design-hints wording.
  **Fixed 2026-11-09:** Quote-image one-piece prompt drops the empty facet, a photo subject equal to the topic, "Other pieces cover: none" and the design-hints wording.
- [x] **W8 (L) Regenerating "design" costs a full model call** and sets `design=None` for quote images.
  **Fixed 2026-11-09:** "design" regen is a local `design.another` pick (next design in the genre rotation), no model call. Test `test_new_design_rotates_without_a_model_call`.
- [x] **W9 (M) Create swallows a failed job start.** `pages/Create.tsx:99-100` `.catch(() => {})`; project opens on
  "Nothing generated yet" with no reason. Fix: show the error.
  **Fixed 2026-11-09:** Create stores a failed first-job start in `startFailures`; the project page shows it once.

## Phase 4: quote trust and legal

Status 2026-11-09: done (Q1 partly). Backend tests 237/237 OK. Not yet verified against the real fast model.

- [x] **Q1 (H) Nothing checks that a "real" quote is real.** Only `_signed` (`content.py:60`) checks the author isn't
  blank. Temperature 1.0 (`settings.py:31`) and a growing 200-line `too_similar` history push the model toward obscure
  or invented lines over time. Fix (cheapest first): required `quote.source` (work + chapter/letter) shown in the UI;
  one verification call per batch on `ai_model_fast` ("verbatim from {source} by {author}? yes/no/unsure", reject
  non-yes); writing temperature ~0.6; best: bundled public-domain corpus, model picks from retrieved candidates.
  **Fixed 2026-11-09:** Partly: one `verify_quotes` call per batch on `ai_model_fast` (temperature 0); a quote judged "no" (invented, paraphrased or misattributed) fails its piece with a plain reason; quote regen checks too. Fails open when the check can't run; "unsure" passes. Test `test_a_quote_the_checker_calls_fake_is_failed_not_kept`. Not done: a `quote.source` field, a lower writing temperature (a user setting), a bundled public-domain corpus.
- [x] **Q2 (H) "A translation is fine" points at copyrighted text.** `prompts.py:32`. Famous versions are modern
  (Hays' Marcus Aurelius 2002, Campbell's Seneca 1969, Barks' Rumi, Mitchell's Lao Tzu, Kaufmann's Nietzsche). Fix:
  "Only translations published before 1929 (Marcus Aurelius: George Long 1862; Seneca: Gummere 1917-25; Epictetus:
  Oldfather 1925 or Long; Lao Tzu: Legge 1891). Never Rumi via Coleman Barks."
  **Fixed 2026-11-09:** ATTRIBUTION now requires pre-1929 translations (Long, Gummere, Oldfather, Legge) and names the modern ones to avoid, Rumi via Barks included.
- [x] **Q3 (H, verified) Helen Keller listed for Hope** (`prompts.py:97`) though she died 1968, breaking the prompt's
  own "died before 1955" rule; Napoleon and Franklin are misattribution-heavy. Drop them or check a death-year table.
  **Fixed 2026-11-09:** Helen Keller dropped from Hope; Franklin and Napoleon dropped from Hard Truth.
- [x] **Q4 (M) Historical Voices / Book Wisdom invite invented context** ("the narration sets the moment the line came
  from", `prompts.py:114`). Fix: "Only state context you are certain is documented (the work, roughly when). Never
  invent where or to whom a line was said."
  **Fixed 2026-11-09:** History voice: may name the work and roughly when, only when certain; never invents where or to whom.

## Phase 5: virality pass (needs owner sign-off; changes what the content says)

Status 2026-11-09 (owner approved): 22 of 31 done (V8, V17, V27, V30 partly). Open, each a real build: V10-V12
(crop tracking over the whole span, speaker choice, no-face fit), V14 (ASS hook fallback), V15-V16 (verbatim
Whisper prompt, cuts inside silences), V19 (hallucination filter), V26 (beat-matched edit), V31 (footage scoring).
Backend tests 239/239 OK. Not yet verified: a real clip run and a real generation with the new prompts.

### Clipper
- [x] **V1 (H) Clip count makes filler by design.** `clips.py:77` one clip per source minute (up to 30); pass 1 asks
  for `min(3n, 90)` non-overlapping 48 s+ moments (`clipper/select.py:188`), so the model tiles the whole transcript.
  Fix: about one clip per 5-8 min, cap 8-12, ask for at most 2n, allow fewer.
  **Fixed 2026-11-09:** n = about one clip per 6 min, capped at 10; pass 1 asks for at most 2n (cap 40) and is told fewer strong moments beat many weak ones. Test `test_clip_count_is_one_per_six_minutes_capped_at_ten`.
- [x] **V2 (H, verified) Padding added after the payoff.** `clips.py:22-37` `_at_least` grows the clip later first to
  reach the 60 s floor: endings run past the punchline, can overlap the next clip. Fix: never grow past the chosen end
  (ask pass 1 for ~1.15x raw length, grow only into setup, or drop short clips). Also return a re-planned `ranges`
  when the loop runs out (stored times disagree with the render).
  **Fixed 2026-11-09:** `_at_least` grows only EARLIER (into the setup), never past the payoff; ranges always planned on the returned span. Test `test_a_short_pick_grows_into_its_setup_never_past_its_payoff`.
- [x] **V3 (H) One 60 s floor for every clip** (owner decision 2026-11-08; flagged for review, not overridden). Strong
  podcast moments are often 20-45 s; Reels/Shorts reward completion. Suggestion: two bands, "punch" 20-45 s and
  "story" 60-90 s; 60 s floor only when targeting TikTok monetisation.
  **Fixed 2026-11-09:** Floor 60 -> 20 s (`config.MIN_CLIP`, brief default, Create form); PASS1 lets the arc set the length. Set 60 in Create for TikTok Creator Rewards.
- [x] **V4 (H, verified) Cold open and trims are guessed timestamps.** `select.py:191-196` sends pass 2 untimed text
  but asks for seconds (`PASS2` lines 36-40), so the teaser is half a sentence. Fix: `[t]` marks per sentence, or have
  the model quote the cold-open sentence and locate it in `words`.
  **Fixed 2026-11-09:** Pass 2 candidates carry `[time]` before every sentence (`select.timed`); trims and cold open are read off those marks. Test `test_pass_two_sees_sentence_times`.
- [x] **V5 (H, verified by probe) Clips end on the next sentence's first word** ("...is patience. So"). `clips.py:93`
  +0.2 s pad + `tighten.keep` (`tighten.py:256`). Fix: only words with `start < snapped end`; pad is air only.
  **Fixed 2026-11-09:** Words starting after the snapped end are dropped before planning; the 0.2 s pad is air only.
- [x] **V6 (H) No loopable endings.** Add to PASS1/PASS2: "end within 0.3 s of the payoff line; prefer endings that
  loop into the opening line".
  **Fixed 2026-11-09:** PASS1: end within a breath of the payoff, no wrap-up, prefer endings that loop into the first line; PASS2: the end lands on the payoff line.
- [x] **V7 (M, verified by probe) Multi-word emphasis never coloured.** `captions.py:217` `bare()` strips spaces
  ("tenthousandhours"). Split entries on whitespace; same in `motion.anchor_time`.
  **Fixed 2026-11-09:** Emphasis phrases split into words before matching. Test `test_multi_word_emphasis_is_coloured` (fails without the fix).
- [x] **V8 (M) No story-structure check.** Pass 1 should return `hook_line`, `payoff_line`, `question_opened`; reject
  candidates with the payoff in the first third.
  **Fixed 2026-11-09:** Partly: PASS1 asks for the payoff in the final third. No hook_line/payoff_line fields or rejection logic.
- [x] **V9 (H) Soft picture from upscaling.** `acquire.py:112` caps at 1080p; a 9:16 crop is 607 px wide, about 2x
  upscaled with push-ins. Fix: allow 1440p/2160p for 9:16, or cap push-in on 1080p sources.
  **Fixed 2026-11-09:** yt-dlp `res:1440`.
- [ ] **V10 (M) Crop jumps to centre on short no-face ranges.** `crop.py:60-62`, per-range `crop_filter`. Fix: track
  once over the clip span, carry last known x. (Also fixes the per-range detector cost, E1.)
- [ ] **V11 (M) Two-person shots follow the bigger face, not the speaker** (`crop.py:36`). Hysteresis toward the
  current track; YuNet mouth landmarks for active speaker.
- [ ] **V12 (M) Screen content / no-face footage gets a blind centre crop.** Fit over a blurred copy instead.
- [x] **V13 (M) Captions under TikTok's right rail.** `captions.py:209-216` symmetric 80 px margins, lines to ~920 px at
  y≈71%. Fix: right margin ~160 px or ~14-char karaoke lines.
  **Fixed 2026-11-09:** Vertical clips get a 160 px right margin (TikTok/Reels rail).
- [ ] **V14 (M) Hook title vanishes silently** when Edge/Node is missing (`motion.layers` returns []). Fall back to an
  ASS-rendered hook line.
- [ ] **V15 (M) Fillers rarely cut**: Whisper drops "um/uh" from text, audio keeps them. Verbatim-style Whisper prompt,
  then cut.
- [ ] **V16 (M) Cut points rely on Whisper word times** (`tighten.py:264-266`). Place cuts inside detected silence.
- [x] **V17 (M) Non-English sources:** no CJK sentence punctuation (`select.py:205-206`), CJK words joined with spaces,
  English-only fillers, prompts don't pass `transcript["language"]`.
  **Fixed 2026-11-09:** Partly: CJK sentence ends in `snap`/`timed`; PASS2 writes copy in the transcript's language. Not done: CJK word joining, non-English fillers.
- [x] **V18 (L-M) Speech over music:** no silence evidence means every gap > 0.5 s is cut (`tighten.py:236`), music
  stutters. Cut only gaps > 1.0 s or skip tightening.
  **Fixed 2026-11-09:** No silence evidence: only gaps over 1.0 s are cut (was 0.5 s).
- [ ] **V19 (L) Whisper silence hallucinations** ("Thank you for watching.") not filtered (`transcribe.py:402`). Drop
  high `no_speech_prob` / repeated segments.
- [x] **V20 (L) Cover frame at 1 s** catches the hook mid-animation (`render_clip.py:340`). Take ~1.6 s.
  **Fixed 2026-11-09:** Cover at min(1.6 s, half the clip).

### Writing
- [x] **V21 (H) Hope genre slop.** `prompts.py:99` "Name the quiet battles nobody sees", `prompts.py:70` "a name for
  something the listener knows but never says". Proposed: "Open on one small, specific detail from the topic's world
  (an object, a place, a gesture) the listener has lived. Hope comes from that detail turning, never from reassurance.
  Banned: 'nobody sees', 'a kind of tired', 'it's okay to', 'you're not alone'."
  **Fixed 2026-11-09:** Hope voice and the hook rule rewritten as proposed (specific lived detail; banned phrases).
- [x] **V22 (H) Stoic genre is a fixed recipe** (`prompts.py:110`, control / mortality / duty every time; breaks the
  no-recipe rule). Proposed: "Stoic lens on THIS topic: what a Stoic would notice about it, said plainly. Use the
  dichotomy of control or mortality only when the topic invites it."
  **Fixed 2026-11-09:** Stoic voice: a Stoic lens on THIS topic; control/mortality only when invited.
- [x] **V23 (H) Hard Truth ends the same way** (`prompts.py:106`, "hold the line"). Proposed: "Escalate through concrete
  costs specific to the topic. End on a decision the listener can make today, in your own words (never 'hold the
  line', 'stay hard', 'get after it')."
  **Fixed 2026-11-09:** Hard Truth: concrete costs, ends on a decision today; banned stock phrases.
- [x] **V24 (H) No default narration length** (Auto refers to an undefined default). Proposed: "Default narration is
  55-80 words (about 22-32 s aloud), Cinematic Minimal 25-45. The hook line is at most 12 words, spoken within 1.5 s."
  **Fixed 2026-11-09:** Default 55-80 words (Cinematic Minimal 25-45); hook line at most 12 words.
- [x] **V25 (H) Narration ends on the author's name** (`prompts.py:81`), a retention dip, no loop. Proposed: "Say the
  quote last; never 'as X once said'. The author appears on screen, not spoken. The final line should make the first
  line read differently on a rewatch." Plus a 0.6-1.0 s hold whose last frame matches the first.
  **Fixed 2026-11-09:** Quote said LAST, never the author aloud (credited in the caption, since quote text isn't burned into videos); last line reframes the first. Not done: the matching last/first frame hold.
- [ ] **V26 (M) Edit ignores narration beats.** `edit.py:120-137` rotates `assets[i % len]` on a fixed rhythm; the
  prompt's 4 beats (`prompts.py:84-87`) are unused. Fix: `line` on `Shot`, beat boundaries via `motion.anchor_time`,
  sub-cuts re-enter the same asset.
- [x] **V27 (M) One post-text set for every platform** (`prompts.py:148`, `platforms/__init__.py`,
  `zernio.piece_texts`). Proposed: `title` = what someone would type to find this (≤60 chars); `caption` line 1 = the
  searchable phrase, then 1-2 lines adding a detail; `description` YouTube only, 1 sentence + quote source; drop
  `keywords` or map it.
  **Fixed 2026-11-09:** Partly: title = search phrase (60 chars, example), description = YouTube with author and work, caption line 1 = searchable phrase + author credit. Still one metadata set mapped per platform.
- [x] **V28 (M) Every caption ends on "Save this for... / Send this to..."** (`prompts.py:150-151`). Proposed: "Most
  captions need no ask. At most 1 in 3 per batch, never two alike."
  **Fixed 2026-11-09:** At most 1 in 3 captions per batch ends on an ask, never two alike.
- [x] **V29 (M) Choppy "AI poetry" cadence** (`prompts.py:74-77`). Proposed: "Mix sentence lengths like speech: mostly
  full sentences, at most two fragments. Show the 'but/so' logic; don't start lines with those words."
  **Fixed 2026-11-09:** Mostly full sentences of mixed length, at most two fragments; no lines starting with but/so.
- [x] **V30 (M) One voice (Charon) for every genre** (`tts.py:27`, `renders.py:92-93`), generic TTS instructions
  (`tts.py:46`). Per-genre default voice (hope Sulafat/Achernar, speech Algenib, stoic Gacrux, cinema Enceladus,
  history/books Sadaltager) and the genre's voice line in `instructions`.
  **Fixed 2026-11-09:** Partly: `tts.GENRE_VOICES` default voice per genre when the brief picks none. Not done: the genre's voice line in the TTS instructions.
- [ ] **V31 (L) Footage scoring trusts search order**, favours centred subjects to leave room for a quote that isn't
  burned into videos (`assets/__init__.py:63`); the kinetic hook shot becomes the 4:5 quote-image background
  (`renders.py:116`). Score composition only for images; use the atmospheric shot for 4:5.

## Phase 6: stability, disk and speed

Status 2026-11-09: 16 done (several partly), S20 and E2 won't fix. Open: S12 (orphaned ffmpeg on close),
S18 (explicit IPC allowlist), S19 (Create drafts), E1 (with V10), E3, E5-E8. Backend 239/239, typecheck + build OK.

- [x] **S1 (M) Unlimited disk growth.** Narration WAVs never deleted (`tts.py:75`); `media/tmp/*-frame.jpg`,
  `*-subs.ass` never cleaned (`renders.py:155`, `210`); clipwork source has no size limit (`acquire.py:47`) and
  outlives the project; `assets/__init__.py:428` deletes render rows without files.
  **Fixed 2026-11-09:** Partly: narration WAVs and tmp frame/subtitle files are deleted after each piece; swapped-in footage deletes the old render files; yt-dlp `max_filesize` 8 GB. Not done: clipwork sources outliving their project (shared by source key).
- [x] **S2 (M) Slow calls on the 4 RPC threads freeze the UI.** `rpc.py:116`, `posts.py:371-425`,
  `zernio.py:130-142`, `content.regenerate`; `backend.call` has no timeout (`backend.ts:94-110`); `checked_at` not
  stamped on failure. Fix: publishing as a job or own thread; stamp on failure; short refresh timeout.
  **Fixed 2026-11-09:** Partly: a failed status check stamps `checked_at`, so offline calendars stop retrying on every list. Not done: moving publishing off the RPC threads.
- [x] **S3 (M) Whole video read into memory, single PUT, no retry** (`zernio.py:133-136`); Schedule all repeats
  `accounts()` + creator-info per item. Stream from file, retry once, `check()` once per batch.
  **Fixed 2026-11-09:** Upload streams from disk (`content=file`, explicit Content-Length) with one retry; `test_zernio` still checks the exact bytes. Not done: one `check()` per Schedule-all batch.
- [x] **S4 (M) Two projects rendering at once corrupt each other's subtitles** (`renders.py:51`,
  `clipper/transcribe.py:46-56`, shared `media/tmp/narration/audio/00000.flac`). Per-call temp dir.
  **Fixed 2026-11-09:** Narration transcription runs in a per-call `TemporaryDirectory`.
- [x] **S5 (H, probe) `media://` ignores Range requests** (`electron/main.ts:74-81`): returns 200 + full file, so
  seeking long videos stalls. Answer Range with 206 + `Content-Range` from an fs stream.
  **Fixed 2026-11-09:** `media://` answers Range with 206 + Content-Range from a file stream (416 out of bounds). Probed in Electron: 100-199 -> 100 bytes, 99000- -> 1000 bytes, past end -> 416, no Range -> 200 whole file.
- [x] **S6 (M) Every progress tick refetches all pieces and renders** (`pages/Project.tsx:19-22`, `Clips.tsx:69`),
  about 4 RPCs/s during a render. Refetch on status/stage change only.
  **Fixed 2026-11-09:** Pieces, renders and clips refetch on job status/stage, not every progress tick.
- [x] **S7 (M) Queue progress is a frozen snapshot** (`pages/Queue.tsx:25-56`), contradicting "appear here live".
  Subscribe to `job.*` events.
  **Fixed 2026-11-09:** Queue reloads on job events (progress at most once a second).
- [x] **S8 (M) Dome background animates under reduced motion and at idle** (`DomeBackground.tsx`, 252 tiles of
  animated WebP). Static posters under reduced motion, pause while a dialog is open / hidden, fewer tiles.
  **Fixed 2026-11-09:** Partly: the dome isn't shown under reduced motion. Idle GPU cost otherwise unchanged (not measured).
- [x] **S9 (M) Dialogs close by accident and lose edits** (`ui.tsx:142-150`): backdrop closes on drag-release, one
  Escape closes stacked dialogs and leaves fullscreen. Require mousedown+click on backdrop; Escape closes topmost only.
  **Fixed 2026-11-09:** Done with P2: the backdrop closes only on a press that starts and ends on it; Escape closes only the topmost dialog, and nothing while locked.
- [x] **S10 (L-M) Clear storage leaves exports on disk** (`storage.py:12-26`, exports live outside `MEDIA_DIR`) and
  reports locked files as freed.
  **Fixed 2026-11-09:** Partly: Clear storage removes and counts `exports/`. Not done: reporting files Windows kept locked.
- [x] **S11 (L-M) Cancel lags by minutes** (`clipper/ff.py:12-18`, `clips.py:99`); `jobs.cancel` accepts any id
  forever. Poll a cancel event; refuse non-running ids.
  **Fixed 2026-11-09:** Partly: `jobs.cancel` ignores ids that aren't running. Not done: polling cancel inside a long ffmpeg run.
- [ ] **S12 (L) Closing the app orphans ffmpeg / motion Chromium** (`backend.ts:113-128`, `render.py:347`,
  `motion.py:83`). Windows Job Object (kill on close) or kill tracked children on stdin EOF.
- [x] **S13 (L) Backend restart leaves in-flight calls hanging** (`backend.ts:285-292`); no per-call timeout.
  **Fixed 2026-11-09:** `restart()` answers in-flight calls. No per-call timeout on purpose: Zernio uploads can take minutes.
- [x] **S14 (L) Job Cancel gives no feedback**, unhandled rejection (`JobProgress.tsx:57`).
  **Fixed 2026-11-09:** Cancel shows Cancelling… and catches errors.
- [x] **S15 (L) Settings key save has no error handling** (`Settings.tsx:97`); `secrets.ts` `all()` throws on one bad
  entry so no keys load (`main.ts:90`); secrets file written non-atomically.
  **Fixed 2026-11-09:** Key save failures show in the field; secrets written to .tmp then renamed; a corrupt file or an undecryptable entry no longer blocks the other keys.
- [x] **S16 (L, suspected) Migrations not transactional** (`database.py:20-24`): a crash mid-migration crash-loops the
  backend on "duplicate column". Wrap each in BEGIN/COMMIT with the `user_version` bump.
  **Fixed 2026-11-09:** Each migration runs inside BEGIN/COMMIT with its user_version bump.
- [x] **S17 (L) Backend log grows forever, written synchronously** on the Electron main thread (`backend.ts:71`).
  **Fixed 2026-11-09:** Log written through an async stream; over 5 MB it rotates to backend.log.old at start.
- [ ] **S18 (L, suspected) IPC allowlist is a denylist** (`main.ts:94-97`): everything but `secrets.*` is callable, no
  `senderFrame` check. Low risk while CSP/sandbox hold; make it an explicit allowlist.
- [ ] **S19 (L) Create drafts lost on navigation** (`App.tsx:64` remounts pages); Ctrl+Enter key-repeat skips steps.
- [-] **S20 (L) No Approve action in Preview** (`Check` imported but unused in `Preview.tsx`). Confirm with owner
  whether intended.
  **Won't fix: no approve step is an owner decision (2026-11-08; `test_m6.test_4_there_is_no_approve_step`).**

### Efficiency
- [ ] **E1 Face detection reopens the video and detector per range** (`render_clip.py:310`), often 20-40 times a
  clip. One pass per clip span (see V10).
- [-] **E2 `_at_least` reruns silencedetect up to 8 times per clip** (`clips.py:26`). Detect once on the Whisper FLAC
  chunks and cache next to `transcript.json`.
  **Won't fix for now: each silencedetect is a short seeked run; cache it if a profile shows it matters.**
- [ ] **E3 Hook layers render serially** (~30 s each in Edge, ~15 min for 30 clips, `clips.py:96`). Render in parallel
  before the loop.
- [x] **E4 Local sources re-hashed with sha256 every run** (`acquire.py:81`). Key on path + size + mtime first.
  **Fixed 2026-11-09:** keyed on path + size + mtime (local files cached before re-transcribe once).
- [ ] **E5 Unused generated fields** (`mood`, `text_density`, `animation`, `batch_theme`, `keywords`, `description`
  beyond YouTube): about 10-15% of output tokens per piece. Drop them from the shapes.
- [ ] **E6 Big prompts resent on every rewrite** (~11.5k chars per 4-piece group; repair resends the full
  conversation). Keep the stable prefix first for provider caching; merge plan + write for ≤4 videos.
- [ ] **E7 Repeat check** runs difflib against 200 history lines; normalised exact match first if history grows.
- [ ] **E8 Masonry relayout** on every render (`Library.tsx:75` new `items` array). Fine at current scale.

---

## Checked and fine (no action)
SQL is parameterised; `media://` path containment is correct; `openExportPath` and `openExternal` (https only) are
safe; renderer can't call `secrets.*`; Zernio key is DPAPI-encrypted and never logged; schedule times are UTC with
offsets (DST safe); yt-dlp filenames are sanitised; `jobs.recover()` fails stale jobs on start; no double encodes;
faststart on both encoders; H.264 High, AAC 48 kHz; contextIsolation + sandbox on, nodeIntegration off; typecheck clean.
