# Edit grammar: the shot-level spec for renders that look edited

Written as the director's brief for the render pipeline. Section 1 is the audit of what we ship today,
2-3 are the grammar we are aiming at, 4 is what this machine's ffmpeg can actually deliver (every item
verified on 2026-09-20, not assumed), 5 is the refactor in dependency order.

Source of truth for scope stays `Prd.txt`. This file governs how a piece is CUT, not what it says.

---

## 1. Audit: why our renders read as a slideshow

| What the code does | Where | Why it reads cheap |
|---|---|---|
| One asset per piece. `secondary_query` is only a fallback when the first search returns nothing | `assets/__init__.py:170` | Every "cut" returns to the same clip, same location, same subject, same light. The viewer sees one photo panning, not an edit |
| The "multi-shot timeline" is 2-3 seeks into that single clip plus its own cover frame | `renders.py _shots_for` | The still cutaway is a frame of the shot we just left. It reads as a stutter, not a cutaway |
| Cuts land on arithmetic: `seg = duration / n` | `renders.py _shots_for` | Picture changes mid-word, mid-clause. The edit fights the narration instead of breathing with it |
| One transition exists: hard `concat` | `render.py render_video` | Every genre cuts identically. Hope should dissolve, Hard Truth should cut hard. Right now they are the same film |
| Grade is a 2-term string (`eq=saturation=1.08`) | `render.py LOOKS` | Saturation is not a grade. No shadow lift, no split tone, no highlight roll-off. Footage stays stock-looking |
| `zoompan` runs on un-supersampled stills | `render.py render_video` | zoompan quantises zoom per frame at source resolution: visible stair-step jitter on the Ken Burns shots |
| Dressing is fixed `vignette + noise=alls=4` for all six genres | `render.py render_video` | Cinematic Minimal and Hard Truth get identical texture. Brand collapses into one look |
| Caption word timings are estimated from word length | `renders.py _subtitles_ass` | Karaoke drifts off the voice within ~8 words. The one element the eye checks against the ear |
| Audio is narration + music `amix`, no ducking | `render.py render_video` | Music masks consonants. Narration stops sounding like it is in front |
| Shot 1 is whatever `seek 0` lands on | `renders.py _shots_for` | The 0-3s window that decides 50-60% of the drop-off is left to chance |

The single highest-leverage defect is the first row. Everything else is polish on top of one clip.

---

## 2. The retention spine (applies to every genre)

Research-backed, sources at the bottom.

- **0.0-0.3s**: picture is already in motion on frame one. No fade from black, no static hold, no logo.
- **0-3s**: the hook. 50-60% of everything lost is lost here. Shot 1 is the single best asset in the pool,
  not the first one.
- **Visual change every 1.5-2.5s.** A change is a cut, a motion reversal, a caption group swap or a grade
  shift. Below ~1.2s the brain reads noise; above ~2.5s stimulus density drops and so does retention.
- **B-roll shot length 3-5s max**, and ours should sit shorter because narration is dense.
- **Three b-roll registers per minute**: literal (matches the word), metaphorical (evokes the feeling),
  atmospheric (sets the scene). Mixing registers is what separates an edit from a stock reel.
- **Pattern interrupt every 10-15s**: a speed ramp, a grade shift, a hard cut into silence.
- **Cut on motion.** When the outgoing frame is moving, the eye does not register the cut.
- **Transitions stay under 0.4s.** Longer reads amateur. Most cuts should have no transition at all.
- **Land the last line clean.** Final shot holds ~0.6s past the last word. That is the screenshot frame.

---

## 3. Genre grammar

`brief.tone` already selects these. Today they differ only by a saturation number. They should differ by
cadence, transition, grade, motion, texture and type. Reference creators per genre are the ones the taxonomy
was researched against (`prompts.py GENRES`).

### Hope (hopecore spoken word)
- **Feels like**: a letter read aloud at 2am. Soft, unhurried, handheld.
- **Cadence**: 2.6-3.2s per shot. Slowest of the spoken genres.
- **Shot roles**: atmospheric, atmospheric, literal, metaphorical. Faces in soft light, windows, hands,
  early morning streets. Never a stadium, never a gym.
- **Motion**: slow push-in only, 4-6% over the shot. No pans. Motion never reverses inside a piece.
- **Transition**: `dissolve` 0.35s between every shot. This is the one genre that dissolves throughout.
- **Grade**: warm lift. Shadows lifted and warmed, highlights rolled off soft, saturation held near 1.0.
  Halation bloom at 0.30 opacity. The image should feel like it is glowing slightly from inside.
- **Texture**: fine grain (`alls=4`), vignette light. Soft, not gritty.
- **Type**: captions on, lowercase, centred low, gentle. No hard highlight colour; white with a warm glow
  instead of the clip engine's yellow.
- **Audio**: music bed present and ducked 6-8dB under narration. Music fades in over 1.5s.

### Hard Truth (speech edit)
- **Feels like**: Goggins/Jocko speech cut by someone angry. Every cut is a punch.
- **Cadence**: 1.4-1.9s per shot. Fastest genre. Accelerating: shots get shorter toward the payoff.
- **Shot roles**: literal and kinetic. Bodies working, rain, iron, stairs, cold water, the 4am street.
- **Motion**: alternating push-in / pull-out at 8-10%, plus one whip-speed shot at the turn.
- **Transition**: none. Hard cuts only. One `fadeblack` 0.2s before the final line, as the breath.
- **Grade**: bleach bypass. Contrast up, saturation pulled to ~0.75, shadows crushed cold, highlights hot.
- **Texture**: coarser grain (`alls=8`), vignette strong, slight `unsharp` for bite.
- **Type**: captions on, uppercase, high-contrast, the clip engine's punch styling.
- **Audio**: music louder (still ducked), and a hard cut to near-silence for the last line.

### Stoic Wisdom
- **Feels like**: Daily Stoic. Still, composed, unimpressed.
- **Cadence**: 3.0-4.0s. Long holds. Stillness is the point.
- **Shot roles**: atmospheric and metaphorical. Stone, sea, marble, candle, empty rooms, weather.
- **Motion**: one very slow move per shot, under 4%. Some shots locked off entirely.
- **Transition**: `fade` 0.3s on the first and last cut only. Hard cuts in the middle.
- **Grade**: cold desaturated. Blue shadows, neutral highs, saturation ~0.85, gentle S-curve.
- **Texture**: minimal grain, mild vignette. Clean.
- **Type**: captions optional and quiet. This genre survives without them.
- **Audio**: sparse music or none. Silence is a legitimate bed here.

### Historical Voices
- **Feels like**: an archive reel with a modern spine.
- **Cadence**: 2.4-3.0s.
- **Shot roles**: metaphorical and atmospheric, period-suggestive without being literal costume drama.
- **Motion**: slow push-in on stills. This genre runs heaviest on stills, so supersampled Ken Burns matters
  most here.
- **Transition**: `fadeblack` 0.25s. The black beat between shots suggests chapters.
- **Grade**: desaturated sepia. Saturation ~0.35, warm mid-tones, lifted blacks like aged print.
- **Texture**: heaviest grain (`alls=10`), strongest vignette, optional 2.39:1 letterbox bars.
- **Type**: the attribution line matters more than karaoke. Author name held on the final shot.
- **Audio**: low strings or none. Never modern percussion.

### Book Wisdom
- **Feels like**: Historical Voices, but present-tense and warmer. Paper, desks, light through a window.
- **Cadence**: 2.6-3.2s.
- **Grade**: cool neutral with a warm paper bias in the mids. Sits between Stoic and Hope.
- **Transition**: `dissolve` 0.3s on alternate cuts only.
- **Texture**: light grain, soft vignette.
- **Type**: captions on, quiet. Attribution held at the end like Historical Voices.

### Cinematic Minimal
- **Feels like**: Mateusz M. The visuals carry it; words are rare and land like titles.
- **Cadence**: 3.5-4.5s, and this is the genre that earns a speed ramp per piece.
- **Shot roles**: atmospheric first, metaphorical second. Scale: landscape, weather, distance, one small figure.
- **Motion**: one continuous move per shot, slow, plus one ramped hero shot at the turn.
- **Transition**: `fadeblack` 0.4s. Black between beats is the format's signature.
- **Grade**: teal-orange with real separation. Cool shadows, warm skin-range mids, saturation ~1.1.
- **Texture**: fine grain, strong halation bloom (0.4), 2.39:1 letterbox bars always.
- **Type**: captions OFF by default. Words appear rarely, as title cards, not karaoke.
- **Audio**: music is the lead, narration sits inside it. Ducking gentler, 4dB.

---

## 4. What this machine's ffmpeg can actually do

ffmpeg 9.0.1-full (gyan.dev). Everything below was run on this box on 2026-09-20 and either passed or is
marked absent. No feature is prescribed that was not executed.

| Capability | Filter | Status |
|---|---|---|
| 3D LUT film grades | `lut3d` | **Verified.** Loads a generated 17^3 `.cube` |
| Halation / bloom | `split` + `gblur` + `curves` + `blend=screen` | **Verified** at 0.32 opacity |
| Micro-contrast | `unsharp` | Verified in the same chain |
| Real transitions | `xfade` | **Verified**, 57 transitions. 3-shot chain, duration maths exact (5.2s from 3x2s with 0.4 + 0.3 overlaps) |
| Speed ramps | `setpts` | **Verified** inside an xfade chain |
| Optical-flow slow motion | `minterpolate` | Present. Very slow in `mci` mode; budget one short shot or skip |
| Jitter-free Ken Burns | `scale=iw*4` before `zoompan` | **Verified.** This is the fix for our stair-step stills |
| Music ducking | `sidechaincompress` | **Verified** with `asplit` on the loudnormed narration |
| Letterbox bars | `drawbox` | Verified |
| Stabilisation | `vidstabdetect` / `vidstabtransform` | Present (two-pass) |
| Scene detection | `scdet`, `blurdetect`, `signalstats`, `thumbnail` | Present. Real shot selection inside a stock clip, and real motion scores for `visual.py` |
| Local transcription | `whisper` filter | Compiled in, but needs a ggml model file we do not bundle |
| GPU encode | NVENC / AMF / Vulkan / OpenCL / libplacebo | Present. Not needed yet; `veryfast` x264 is fine at our lengths |
| Glow / light leaks | `frei0r` | **Absent.** Enabled at build, plugin DLLs not installed. Do not prescribe frei0r |

**Windows gotcha, verified today:** `lut3d=file=C:/path.cube` fails with `No option name near '/...'`. It needs
the same treatment as `drawtext`: single-quote the value and escape the drive colon, giving
`lut3d=file='C\:/path.cube'`. `render.py esc()` already does this. The clipper's alternative (run ffmpeg with
`cwd` set to the output dir and pass relative paths) also works and is cleaner for multi-file graphs.

---

## 5. The refactor, in dependency order

**Status 2026-09-20: phases A-F implemented** (`app/edit.py` is the grammar, `renders.py` plans, `render.py` cuts).
Three deliberate deviations, all ponytail calls:
- **No migration.** `content_pieces.content` is a JSON column, so the pool went in as `content.assets` with
  `content.asset` kept as the hero shot. Every existing reader, renderer and the Preview UI needed no change.
- **Curves, not `lut3d`.** Per-channel `curves` + `eq` + `colorbalance` reaches these six looks with no generated
  files, no cache and no Windows path escaping in the runtime path. `lut3d` stays the upgrade when a genre needs
  true cross-channel grading; the ceiling is marked in `edit.py`.
- **Shot 1 is the model's, not the scorer's.** The prompt now demands the most kinetic shot first, so re-sorting
  the pool by `quality_score` would fight the beat mapping. Left to the writer.
Still open from Phase F: `visual.py motion_score` for video assets via `signalstats`/`scdet`.



Each phase is shippable on its own and ends with the standard gate (`npm test`, screenshots, `graphify update .`,
handover). Phases A and B are where the quality actually comes from; C-F are the finish.

### Phase A: a shot list per piece, not one asset
The unlock. Without it, every later phase polishes a single clip.

- `creative/schemas.py` + `prompts.py`: replace `visual.search_query` / `secondary_query` with
  `visual.shots: [{query, role, beat}]`, 3-6 entries. `role` is `literal|metaphorical|atmospheric`,
  `beat` is the narration phrase this shot sits under. Keep `search_query` as shot 1's query so nothing
  downstream breaks during the migration.
- `SYSTEM` prompt gains a shot-list section: each query is a different subject AND a different setting;
  no two shots in a piece may share a location; the mix must contain at least one of each role; shot 1 is
  the hook and must be the most kinetic.
- `assets/__init__.py`: `_assign_one` becomes `_assign_many` and returns an ordered pool. Dedupe inside the
  piece with the existing `dhash`/`hamming` (reject a shot within Hamming 10 of another shot in the same
  piece), not just across the project.
- Schema/migration: `content_pieces.content.asset` becomes `assets: [...]`. Add `app/migrations/NNN_shot_pool.sql`.
  Keep reading the old single-asset shape so existing projects still render.
- Cost note: this multiplies provider searches per piece. `SEARCH_LIMIT` can drop from 8 to 5 to compensate.

### Phase B: cut to the voice, not to a divisor
- Get real word timings. The narration is one short file and we already have a Groq Whisper client
  (`clipper/transcribe.py`). Feed the narration wav through it and reuse the words for BOTH the karaoke ASS
  and the cut points. Fall back to today's length-weighted estimator when no Groq key is set, so nothing
  regresses for a keyless user.
- `renders.py _shots_for` becomes a real planner: take the genre's cadence window, walk the word list, and
  place each cut at the nearest silence or clause boundary (a gap of >180ms between words, or a word ending
  in `.?!,`). Never cut inside a word. Assign pool shots to beats in order, honouring `beat` from Phase A.
- Shot 1 gets the pool's highest `quality_score` asset, overriding model order. The hook is not left to chance.
- Hold the last shot ~0.6s past the final word.

### Phase C: real grades and per-genre dressing
- New `app/looks.py`: generates the six genre `.cube` files (17^3) from tone-curve parameters into
  `media/tmp/luts/` on first use, cached by hash. Generating them ourselves keeps the repo license-clean; no
  downloaded LUT pack of uncertain provenance enters the tree (note it in `DECISIONS.md`).
- `render.py LOOKS` becomes a table of `{lut, bloom, grain, vignette, unsharp, bars}` per genre, replacing the
  `eq` strings. `GENRE_LOOKS` in `renders.py` then selects a full look, not a saturation number.
- Escape the LUT path with `esc()` and single quotes. Verified necessary above.
- Keep the Create page's manual Look picker working by mapping its options onto the same table.

### Phase D: transitions, motion, ramps
- `render_video` grows a transition stage: when a shot carries `transition`, chain `xfade` pairwise instead of
  `concat`. Timeline maths must subtract the overlap from the total or the last shot gets clipped: with N shots
  and transitions `t_i`, total = sum(lengths) - sum(t_i), and each `offset` is cumulative length minus
  cumulative overlap. Verified exact.
- Supersample before `zoompan` on stills (`scale=iw*4:ih*4`). Kills the stair-step.
- Per-genre motion amplitude and direction, alternating so two neighbouring shots never move the same way.
- One ramp per piece for Cinematic Minimal and Hard Truth: `setpts=1.8*PTS` on the turn shot. Because narration
  is the master clock and b-roll is silent, ramping is free as long as shot lengths still sum to the narration.

### Phase E: audio that sounds mixed
- Duck music under narration with `sidechaincompress` (`asplit` the loudnormed narration into the mix and the
  sidechain key). Verified chain in section 4. Per-genre depth: 8dB Hard Truth, 6dB Hope, 4dB Cinematic.
- Extend the music tail fade to match the held last shot.

### Phase F: verification that matches the bar
- Extend `validate_video` with two cheap checks: first-frame luma is not near-black (we never open on black),
  and the shot count matches the plan.
- `visual.py` finally gets its real `motion_score` for video assets via `signalstats`/`scdet`, which feeds the
  hook-shot pick in Phase B.

---

## 6. Ceilings and honest limits

- **Stock is stock.** Pexels/Unsplash cannot give us a continuous scene from multiple angles. Our "coverage"
  is always assembled from unrelated clips. The grammar above hides that with register mixing and a single
  grade across all shots; it does not eliminate it. A shared LUT is what makes eight unrelated clips read as
  one film.
- **`minterpolate` is expensive.** At 1080x1920 it can cost more than the rest of the render. Cap it at one
  shot under 1.5s, or ship the cheaper `setpts` ramp and skip optical flow.
- **Word timings need Groq.** The local `whisper` filter exists but needs a model file we do not ship. Until
  we decide to bundle one, keyless users keep the estimator and slightly looser karaoke.
- **No frei0r.** Light leaks and lens flares are off the table with this build. Halation via `gblur` + `blend`
  covers most of what they would have bought us.
- **More assets per piece means more API calls.** Watch the provider rate limits before raising shot counts.

---

## Sources

Cut cadence, hook window, b-roll length and register mixing:
- https://www.opus.pro/research/broll-visual-effects-short-form
- https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention
- https://aibrify.com/blog/short-form-video-editing-captions-b-roll-guide
- https://aibrify.com/blog/youtube-shorts-retention-curve-playbook
- https://shortzly.com/blog/short-form-video-pacing-editing-guide
- https://www.capcut.com/create/short-form-video-hooks-first-3-second-patterns

Genre references: `prompts.py GENRES` (researched 2026-09-20), plus https://www.youtube.com/@TheMiro0r
for Cinematic Minimal and https://aesthetics.fandom.com/wiki/Hopecore for the hopecore visual register.

ffmpeg capability claims in section 4 were executed locally on 2026-09-20, not taken from documentation.
