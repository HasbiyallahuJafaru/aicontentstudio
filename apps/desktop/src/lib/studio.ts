// Typed access to the preload bridge. The renderer never touches Node, files or API keys.
import { useEffect, useState } from 'react'
import type { StudioApi } from '../../electron/preload'

declare global {
  interface Window { studio: StudioApi }
}

export const studio = window.studio

export type Tone = string
export const GENRES: { value: string; label: string }[] = [
  { value: 'hope', label: 'Hope — spoken word (hopecore)' },
  { value: 'speech', label: 'Hard Truth — speech edit' },
  { value: 'stoic', label: 'Stoic Wisdom' },
  { value: 'history', label: 'Historical Voices' },
  { value: 'books', label: 'Book Wisdom' },
  { value: 'cinema', label: 'Cinematic Minimal' },
]
export type Format = 'automatic' | 'video' | 'image' | 'video_image' | 'image_voiced'  // image_voiced: quote picture + the same picture read aloud as a 9:16 video
export type Platform = 'youtube_shorts' | 'instagram_reels' | 'instagram_feed' | 'tiktok'
export type Look = 'auto' | 'none' | 'warm' | 'cool' | 'mono' | 'vivid'
export type CaptionStyle = {
  style: 'karaoke' | 'pop' | 'clean' | 'boxed' | 'minimal' | 'serif'; font: string
  position: 'lower' | 'middle' | 'upper'; size: 'small' | 'medium' | 'large'
  highlight: 'auto' | 'palette' | 'yellow' | 'orange' | 'green' | 'red' | 'white'; case: 'auto' | 'upper' | 'lower' | 'as_spoken'
}
export const DEFAULT_CAPTIONS: CaptionStyle = { style: 'karaoke', font: 'auto', position: 'lower', size: 'medium', highlight: 'auto', case: 'auto' }
export type TextPosition = 'auto' | 'top' | 'center' | 'bottom'
export type Brief = { kind?: never; topic: string; tone: string; mood: string; audience: string; format: Format; quantity: number; platforms: Platform[]; voice: string; fps: number; target_seconds: number | null; subtitles: boolean; look_filter: Look; blur_background: boolean; parallax: boolean
  captions: CaptionStyle; image_design: string; image_font: string; image_position: TextPosition; quotes?: string[]; palette: string }
export type ClipBrief = {
  kind: 'clip'; source: string; n: number | null; min_len: number; max_len: number
  orientation: '9:16' | '16:9' | '1:1'; burn_captions: boolean; fps: number; captions: CaptionStyle
  thumb?: string  // the link's own thumbnail, fetched right after create (media path)
}
export type Project = { id: string; name: string; status: string; brief: Brief | ClipBrief; created_at: string; updated_at: string; pieces_written?: number
  rendered?: number; cover?: string | null; quote?: string | null }  // list-only: real output for cards
export type Clip = {
  id: string; project_id: string; idx: number; start_at: number; end_at: number; score: number
  reason: string; hook: string; title: string; description: string; hashtags: string[]
  posts: Record<string, string>; status: 'ready' | 'rejected' | 'exported'
  video_path: string; cover_path: string; created_at: string
}
export type DownloadStatus = {
  status: 'fetching' | 'ready' | 'error'; progress: number; title: string | null; path: string | null
  error: { message: string; detail?: string } | null
}
/** One line of "Schedule all": a clip or a piece, and how its posting went. */
export type ScheduleItem = { key: string; title: string; cover?: string | null; video: boolean; clip_idx?: number; piece_id?: string }
export type ScheduleResult = { key: string; ok: boolean; error?: string }
export type Publication = {
  id: string; project_id: string; clip_idx: number; provider: string; channel_id: string; service: string
  channel_name: string; status: string; due_at: string | null; sent_at: string | null
  external_link: string | null; error: string | null; created_at: string; piece_id: string | null
}
export type Job = {
  id: string; project_id: string; kind?: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  stage: string; progress: number; error: { message: string; detail?: string } | null; updated_at: string
  log: JobStep[]  // every step so far: "Piece 3 (2 of 5): Encoding video", with its time and any error
}
export type JobStep = { step: string; status: 'running' | 'done' | 'failed' | 'cancelled'; secs: number; error?: string; detail?: string }
export type PieceContent = {
  plan: { angle: string; visual_subject: string; visual_type: 'video' | 'image'; intensity: string; narration_style: string }
  quote: { text: string }
  narration?: { text: string; delivery: string } | null  // quote images have none
  visual: { preferred_type: 'video' | 'image'; search_query: string; secondary_query: string; mood: string }
  design?: { text_density: string; animation: string; composition: string } | null  // narrated videos only
  metadata: { title: string; description: string; caption: string; hashtags: string[]; keywords: string[]; alt_text: string }
  asset?: { id: string; provider: string; asset_type: string }
  visual_error?: string
  render_error?: string  // the last render of this piece failed; cleared by the next good render
  render_error_detail?: string
  review?: FootageReview  // footage options waiting for the user's pick; nothing full-size downloaded yet
  error?: string
}
export type FootageOption = {
  key: string; queries: string[]; thumb: string; note: 'used' | 'similar' | null
  candidate: { provider: string; asset_type: 'video' | 'image'; creator: string; duration: number; width: number; height: number }
}
export type FootageReview = { want: number; type: 'video' | 'image'; picked: string[]; options: FootageOption[] }
export type PieceStatus = 'written' | 'rendering' | 'ready' | 'exported' | 'failed'
export type Piece = { id: string; idx: number; status: PieceStatus; angle: string; quote: string; project_id: string; content: PieceContent }
export type Asset = {
  id: string; provider: 'pexels' | 'unsplash'; asset_type: 'image' | 'video'; creator: string; license: string
  source_url: string; width: number; height: number; fps: number; duration: number; created_at: string
  thumb_path: string; dominant_colors: string[]; brightness: number | null; quality_score: number | null
  times_used: number; last_used_at: string | null
}
export type Settings = {
  ai_model: string; ai_model_fast: string; ai_temperature: number; ai_max_tokens: number
  default_topic: string; default_tone: Tone; default_quantity: number
  asset_cooldown_days: number; asset_weights: Record<string, number>
  music_path: string; music_volume: number
  render_crf: number; render_audio_bitrate: string; render_width: number; render_height: number
  ytdlp_cookies: string; motion_graphics: boolean
}
export type Render = {
  id: string; piece_id: string; kind: 'video' | 'image'; local_path: string
  duration: number | null; fps: number | null; width: number | null; height: number | null
  created_at: string; idx: number
}
export type QueueData = {
  pieces: { id: string; idx: number; status: PieceStatus; quote: string; project_id: string; project: string
    created_at: string; renders: number; cover: string | null }[]
  jobs: (Job & { project: string })[]
}
export type ExportRun = { id: string; project_id: string; dir: string; path: string; pieces: number
  created_at: string; project: string; covers: string[] }
export type BackendStatus = { state: 'starting' | 'ready' | 'crashed' | 'stopped'; message?: string; detail?: string }
export type VoiceList = { value: string; label: string }[]
/** Narration picker options: narrator personas + Gemini voices from tts.voices, empty = the genre's narrator. */
export const voiceOptions = (voices?: VoiceList) => [{ value: '', label: 'Default · the genre narrator' }, ...(voices ?? [])]
export type SecretName = 'OPENROUTER_API_KEY' | 'PEXELS_API_KEY' | 'UNSPLASH_ACCESS_KEY'

export const TOPICS = ['Motivation', 'Discipline', 'Personal growth', 'Mindset', 'Productivity', 'Relationships',
  'Reflection', 'Confidence', 'Success', 'Resilience']
export const FORMATS: { value: Format; label: string }[] = [
  { value: 'automatic', label: 'Automatic' }, { value: 'video', label: 'Video' },
  { value: 'image', label: 'Image' }, { value: 'video_image', label: 'Video + image' },
  { value: 'image_voiced', label: 'Quote image + voiced video' },
]
export const PLATFORMS: { value: Platform; label: string }[] = [
  { value: 'youtube_shorts', label: 'YouTube Shorts' }, { value: 'instagram_reels', label: 'Instagram Reels' },
  { value: 'instagram_feed', label: 'Instagram Feed' }, { value: 'tiktok', label: 'TikTok' },
]

/** Create opens the new project even when its first job couldn't start; this hands that error to the project
 * page, which shows it once (a swallowed error left "Nothing generated yet" with no reason). */
export const startFailures = new Map<string, BackendError>()

export class BackendError extends Error {
  constructor(message: string, public detail?: string) { super(message) }
}

export async function call<T>(method: string, params?: object): Promise<T> {
  const reply = await studio.call(method, params)
  if (reply.error) throw new BackendError(reply.error.message, reply.error.detail)
  return reply.result as T
}

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>({ state: 'starting' })
  useEffect(() => {
    studio.status().then(setStatus)
    return studio.onStatus((s) => setStatus(s as BackendStatus))
  }, [])
  return status
}

/** Whether the window is fullscreen. Fullscreen hides the system controls, so the UI draws its own exit. */
export function useFullScreen() {
  const [flag, setFlag] = useState(false)
  const [fills, setFills] = useState(false)
  useEffect(() => {
    // Two sources, either one is enough. The main process's flag can lag the resize (enter-full-screen doesn't
    // reliably fire on Windows, and a resize can land before isFullScreen flips), so the page also checks its own
    // geometry: a window exactly the size of the screen is fullscreen, and that answer is instant.
    const geometry = () => setFills(window.innerWidth >= screen.width && window.innerHeight >= screen.height)
    const ask = () => { studio.isFullScreen().then(setFlag) }
    const check = () => { geometry(); ask(); setTimeout(ask, 250) }
    check()
    window.addEventListener('resize', check)
    const off = studio.onFullScreen((on) => setFlag(on))
    return () => { window.removeEventListener('resize', check); off() }
  }, [])
  return flag || fills
}

/** Load data from the backend; reloads when the backend (re)becomes ready or `refresh` changes. */
export function useQuery<T>(method: string, params?: object, refresh?: unknown) {
  const status = useBackendStatus()
  const [data, setData] = useState<T>()
  const [error, setError] = useState<BackendError>()
  const [tick, setTick] = useState(0)
  const key = JSON.stringify(params ?? {})
  useEffect(() => {
    if (status.state !== 'ready') return
    let live = true
    call<T>(method, params).then((d) => live && (setData(d), setError(undefined)), (e) => live && setError(e))
    return () => { live = false }
  }, [method, key, status.state, tick, refresh])
  return { data, error, loading: data === undefined && !error, reload: () => setTick((t) => t + 1) }
}

export const label = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')

/** Local media file (paths are stored relative to the media folder, posix style). */
export const mediaUrl = (rel: string) => `media:///${rel.replace(/\\/g, '/')}`

export function formatDate(iso: string) {
  const d = new Date(iso)
  const today = new Date().toDateString() === d.toDateString()
  return today
    ? `Today, ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
}

/** Latest generation job of a project, live via backend job.* events. */
export function useJob(projectId: string) {
  const { data, reload } = useQuery<Job | null>('jobs.latest', { project_id: projectId })
  const [live, setLive] = useState<Job | null>()
  useEffect(() => studio.onEvent((event, d) => {
    const job = d as Job
    if (event.startsWith('job.') && job.project_id === projectId) setLive(job)
  }), [projectId])
  useEffect(() => setLive(undefined), [data])
  return { job: live !== undefined ? live : data, reload }
}

/** Whether any job (writing, rendering, clipping) is running right now: the stats answer at load, then the live
 *  job.* events keep it current. Drives the ambient motion, so the app only moves while it really works. */
/** Whether the OS asks for reduced motion; follows the setting live. */
export function useReducedMotion() {
  const query = '(prefers-reduced-motion: reduce)'
  const [reduced, setReduced] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setReduced(m.matches)
    on()
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return reduced
}

export function useBusy() {
  const stats = useQuery<{ generating: number }>('app.stats').data
  const [running, setRunning] = useState<Set<string>>()
  useEffect(() => studio.onEvent((event, d) => {
    if (!event.startsWith('job.')) return
    const job = d as Job
    setRunning((prev) => {
      const next = new Set(prev)
      if (job.status === 'queued' || job.status === 'running') next.add(job.id)
      else next.delete(job.id)
      return next
    })
  }), [])
  return running ? running.size > 0 : (stats?.generating ?? 0) > 0
}

export const hasKey = async (name: SecretName) => ((await studio.secretsStatus()) as Record<SecretName, boolean>)[name]
