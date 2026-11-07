// Renders one HyperFrames composition dir to an alpha WebM: node render.mjs <compositionDir> <out.webm>
// The backend runs this with the app's own Electron binary as Node (ELECTRON_RUN_AS_NODE=1), so an installed copy
// needs no separate Node. The browser comes from HYPERFRAMES_BROWSER_PATH (the backend points it at Edge or
// Chrome) and ffmpeg from HYPERFRAMES_FFMPEG_PATH (the bundled one). Prints one JSON line: {ok, seconds} or {error}.
import { createRenderJob, executeRenderJob } from '@hyperframes/producer'

const [dir, out] = process.argv.slice(2)
const t0 = Date.now()
try {
  // ponytail: layers render at 30 fps whatever the video's rate; overlay holds frames, which reads fine for type
  await executeRenderJob(createRenderJob({ fps: 30, quality: 'standard', format: 'webm' }), dir, out)
  console.log(JSON.stringify({ ok: true, seconds: (Date.now() - t0) / 1000 }))
} catch (e) {
  console.log(JSON.stringify({ error: String(e?.message ?? e).slice(0, 2000) }))
  process.exitCode = 1
}
