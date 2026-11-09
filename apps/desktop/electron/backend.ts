// Launches and supervises the Python backend; JSON lines over stdin/stdout (protocol in apps/backend/main.py).
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, renameSync, statSync, watch } from 'node:fs'
import { join } from 'node:path'
import { createInterface } from 'node:readline'

export type BackendStatus = { state: 'starting' | 'ready' | 'crashed' | 'stopped'; message?: string; detail?: string }
export type Reply = { result?: unknown; error?: { message: string; detail?: string } }

type Options = {
  backendDir: string
  dataDir: string
  ffmpegDir?: string
  motionRunner: string // apps/desktop/motion/render.mjs (unpacked from the asar when packaged)
  dev: boolean
  onStatus: (s: BackendStatus) => void
  onEvent: (event: string, data: unknown) => void
  onReady: () => void
}

export function createBackend(o: Options) {
  let child: ChildProcessWithoutNullStreams | null = null
  let nextId = 1
  let quitting = false
  let crashes: number[] = []
  let stderrTail: string[] = []
  const pending = new Map<number, (r: Reply) => void>()
  const logFile = join(o.dataDir, 'logs', 'backend.log')
  mkdirSync(join(o.dataDir, 'logs'), { recursive: true })
  // one previous log kept; a log past 5 MB starts fresh, so ffmpeg-heavy runs can't grow it forever
  if (existsSync(logFile) && statSync(logFile).size > 5 * 1024 * 1024) renameSync(logFile, logFile + '.old')
  const log = createWriteStream(logFile, { flags: 'a' })

  // A packaged install ships the PyInstaller backend next to its data; a dev checkout runs the venv.
  const frozen = join(o.backendDir, 'AI Social Content Studio Engine.exe') // name set in apps/backend/backend.spec
  const venvPython = join(o.backendDir, '.venv', 'Scripts', 'python.exe')
  const [command, args] = existsSync(frozen)
    ? [frozen, [] as string[]]
    : [existsSync(venvPython) ? venvPython : 'python', ['main.py']]

  // Bundled ffmpeg when we ship one, PATH otherwise. The backend reads these in app/config.py.
  const ff = (name: string) => join(o.ffmpegDir ?? '', name + '.exe')
  const ffmpegEnv = o.ffmpegDir && existsSync(ff('ffmpeg')) && existsSync(ff('ffprobe'))
    ? { ACS_FFMPEG: ff('ffmpeg'), ACS_FFPROBE: ff('ffprobe') }
    : {}

  function start() {
    stderrTail = []
    o.onStatus({ state: 'starting' })
    const proc = spawn(command, args, {
      cwd: o.backendDir,
      // ACS_NODE: this very Electron binary, which the backend runs as Node for HyperFrames motion layers
      env: { ...process.env, ACS_DATA_DIR: o.dataDir, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', ...ffmpegEnv,
        ACS_NODE: process.execPath, ACS_MOTION_RUNNER: o.motionRunner },
      windowsHide: true,
    })
    child = proc

    createInterface({ input: proc.stdout }).on('line', (line) => {
      let msg: any
      try { msg = JSON.parse(line) } catch { return }
      if (typeof msg.id === 'number') {
        pending.get(msg.id)?.(msg)
        pending.delete(msg.id)
      } else if (msg.event === 'backend.ready') {
        o.onStatus({ state: 'ready' })
        o.onReady()
      } else if (msg.event) {
        o.onEvent(msg.event, msg.data)
      }
    })
    createInterface({ input: proc.stderr }).on('line', (line) => {
      stderrTail = [...stderrTail.slice(-40), line]
      log.write(line + '\n')  // async: a sync write per stderr line blocked the main thread
    })
    proc.on('error', (err) => {
      stderrTail.push(String(err))
    })
    proc.on('exit', (code) => {
      if (child !== proc) return
      child = null
      for (const resolve of pending.values()) resolve({ error: { message: 'The backend stopped before it answered.' } })
      pending.clear()
      if (quitting) return o.onStatus({ state: 'stopped' })
      const now = Date.now()
      crashes = [...crashes.filter((t) => now - t < 60_000), now]
      const detail = `exit code ${code}\n${stderrTail.join('\n')}`
      if (crashes.length <= 3) {
        o.onStatus({ state: 'starting', message: 'The backend stopped unexpectedly. Restarting.', detail })
        setTimeout(start, 1000)
      } else {
        o.onStatus({ state: 'crashed', message: 'The backend keeps stopping, so it was not restarted.', detail })
      }
    })
  }

  function call(method: string, params: object = {}): Promise<Reply> {
    const proc = child
    // a backend that just stopped (or is stopping) has already closed stdin: writing would throw
    // ERR_STREAM_WRITE_AFTER_END in the main process, so answer with an error reply instead.
    if (!proc || proc.stdin.writableEnded || proc.stdin.destroyed) {
      return Promise.resolve({ error: { message: 'The backend is not running.' } })
    }
    const id = nextId++
    return new Promise((resolve) => {
      pending.set(id, resolve)
      try {
        proc.stdin.write(JSON.stringify({ id, method, params }) + '\n')
      } catch (e) {
        pending.delete(id)
        resolve({ error: { message: 'The backend is not running.', detail: String(e) } })
      }
    })
  }

  function stop() {
    quitting = true
    const proc = child
    if (!proc) return
    proc.stdin.end() // backend exits when stdin closes
    setTimeout(() => proc.exitCode === null && proc.kill(), 2000)
  }

  function restart() {
    crashes = []
    const proc = child
    child = null  // the old process's exit handler now skips its cleanup, so answer its callers here
    for (const resolve of pending.values()) resolve({ error: { message: 'The backend restarted before it answered.' } })
    pending.clear()
    proc?.stdin.end()
    proc?.kill()
    start()
  }

  if (o.dev) {
    let timer: NodeJS.Timeout | undefined
    watch(join(o.backendDir, 'app'), { recursive: true }, (_e, file) => {
      if (!file?.endsWith('.py') && !file?.endsWith('.sql')) return
      clearTimeout(timer)
      timer = setTimeout(restart, 300)
    })
  }

  start()
  return { call, stop, restart }
}
