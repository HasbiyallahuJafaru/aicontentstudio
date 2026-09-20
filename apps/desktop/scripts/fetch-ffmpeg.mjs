// Puts the ffmpeg pair the installer ships into resources/ffmpeg. Prefers the ffmpeg already on this machine's
// PATH and downloads a build only when there is none, because the download is ~90 MB.
//
// Why a GPL build: our renders encode with libx264, which is GPL, so the LGPL builds cannot serve us. ffmpeg runs
// as a separate subprocess and nothing links against it, so this is redistribution of an unmodified GPL program:
// we ship its licence and point at its source. See DECISIONS.md. Nothing here is modified, repacked or renamed.
import { execFileSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ZIP = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
const SOURCE = 'https://www.gyan.dev/ffmpeg/builds/#sources'
const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'resources', 'ffmpeg')
const ps = (cmd) => execFileSync('powershell', ['-NoProfile', '-Command', cmd], { stdio: 'inherit' })
const where = (name) => {
  try {
    return execFileSync('where', [name], { encoding: 'utf8' }).split(/\r?\n/).find((l) => l.trim().endsWith('.exe'))
  } catch {
    return undefined
  }
}

if (existsSync(join(out, 'ffmpeg.exe')) && existsSync(join(out, 'ffprobe.exe'))) {
  console.log('ffmpeg already in resources/ffmpeg, nothing to do')
  process.exit(0)
}
mkdirSync(out, { recursive: true })

// This machine's ffmpeg may be the 'full' static build (~222 MB per exe). ACS_FFMPEG_DOWNLOAD=1 forces the
// smaller release-essentials download instead, which is the better trade for a shipped installer.
const local = process.env.ACS_FFMPEG_DOWNLOAD ? {} : { ffmpeg: where('ffmpeg'), ffprobe: where('ffprobe') }
if (local.ffmpeg && local.ffprobe) {
  // The build that ships is whatever this machine renders with, which is also what the tests ran against.
  for (const [name, from] of Object.entries(local)) copyFileSync(from, join(out, `${name}.exe`))
  const version = execFileSync(local.ffmpeg, ['-version'], { encoding: 'utf8' }).split('\n')[0].trim()
  writeFileSync(join(out, 'SOURCE.txt'),
    `Copied unmodified from this build machine's PATH at package time:\n${version}\n\n` +
    `ffmpeg is licensed GPL (this app calls it as a separate process and does not link against it).\n` +
    `Corresponding source for gyan.dev builds: ${SOURCE}\n`)
  console.log(`bundled ${version}`)
  process.exit(0)
}

console.log(`no ffmpeg on PATH, downloading ${ZIP} (~90 MB)`)
const work = mkdtempSync(join(tmpdir(), 'acs-ffmpeg-'))
const zip = join(work, 'ffmpeg.zip')
try {
  ps(`$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '${ZIP}' -OutFile '${zip}' -UseBasicParsing`)
  ps(`Expand-Archive -Path '${zip}' -DestinationPath '${work}' -Force`)
  const root = readdirSync(work).find((n) => n.startsWith('ffmpeg-') && !n.endsWith('.zip'))
  if (!root) throw new Error(`no ffmpeg-* folder in the archive (got: ${readdirSync(work).join(', ')})`)
  for (const exe of ['ffmpeg.exe', 'ffprobe.exe']) copyFileSync(join(work, root, 'bin', exe), join(out, exe))
  for (const doc of ['LICENSE', 'README.txt']) {
    const from = join(work, root, doc)
    if (existsSync(from)) copyFileSync(from, join(out, `ffmpeg-${doc}`))
  }
  writeFileSync(join(out, 'SOURCE.txt'),
    `ffmpeg and ffprobe here are unmodified binaries from ${ZIP}\nCorresponding source: ${SOURCE}\n`)
  console.log('ffmpeg + ffprobe ready in resources/ffmpeg')
} finally {
  rmSync(work, { recursive: true, force: true })
}
