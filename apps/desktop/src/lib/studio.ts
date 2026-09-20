// Typed access to the preload bridge. The renderer never touches Node, files or API keys.
import { useEffect, useState } from 'react'
import type { StudioApi } from '../../electron/preload'

declare global {
  interface Window { studio: StudioApi }
}

export const studio = window.studio

export type Tone = (typeof TONES)[number]
export type Format = 'automatic' | 'video' | 'image' | 'video_image'
export type Platform = 'youtube_shorts' | 'instagram_reels' | 'instagram_feed' | 'tiktok'
export type Brief = { topic: string; tone: Tone; mood: string; audience: string; format: Format; quantity: number; platforms: Platform[] }
export type Project = { id: string; name: string; status: string; brief: Brief; created_at: string; updated_at: string; pieces_written?: number }
export type Job = {
  id: string; project_id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  stage: string; progress: number; error: { message: string; detail?: string } | null; updated_at: string
}
export type PieceContent = {
  plan: { angle: string; visual_subject: string; visual_type: 'video' | 'image'; intensity: string; narration_style: string }
  quote: { text: string }
  narration: { text: string; delivery: string }
  visual: { preferred_type: 'video' | 'image'; search_query: string; secondary_query: string; mood: string }
  design: { text_density: string; animation: string; composition: string }
  metadata: { title: string; description: string; caption: string; hashtags: string[]; keywords: string[]; alt_text: string }
  asset?: { id: string; provider: string; asset_type: string }
  visual_error?: string
  error?: string
}
export type Piece = { id: string; idx: number; status: string; angle: string; quote: string; content: PieceContent }
export type Asset = {
  id: string; provider: 'pexels' | 'unsplash'; asset_type: 'image' | 'video'; creator: string; license: string
  source_url: string; width: number; height: number; fps: number; duration: number; created_at: string
  thumb_path: string; dominant_colors: string[]; brightness: number | null; quality_score: number | null
  times_used: number; last_used_at: string | null
}
export type Settings = {
  ai_model: string; ai_temperature: number; ai_max_tokens: number
  default_topic: string; default_tone: Tone; default_quantity: number
  asset_cooldown_days: number; asset_weights: Record<string, number>
  tts_provider: 'windows' | 'kokoro'; tts_voice: string; tts_speed: number; tts_volume: number
  music_path: string; music_volume: number
  render_crf: number; render_audio_bitrate: string; render_width: number; render_height: number
}
export type Render = {
  id: string; piece_id: string; kind: 'video' | 'image'; local_path: string
  duration: number | null; created_at: string; idx: number
}
export type BackendStatus = { state: 'starting' | 'ready' | 'crashed' | 'stopped'; message?: string; detail?: string }
export type SecretName = 'DEEPSEEK_API_KEY' | 'PEXELS_API_KEY' | 'UNSPLASH_ACCESS_KEY'

export const TOPICS = ['Motivation', 'Discipline', 'Personal growth', 'Mindset', 'Productivity', 'Relationships',
  'Reflection', 'Confidence', 'Success', 'Resilience']
export const TONES = ['cinematic', 'reflective', 'calm', 'intense', 'inspirational', 'conversational', 'emotional',
  'minimal', 'thoughtful'] as const
export const FORMATS: { value: Format; label: string }[] = [
  { value: 'automatic', label: 'Automatic' }, { value: 'video', label: 'Video' },
  { value: 'image', label: 'Image' }, { value: 'video_image', label: 'Video + image' },
]
export const PLATFORMS: { value: Platform; label: string }[] = [
  { value: 'youtube_shorts', label: 'YouTube Shorts' }, { value: 'instagram_reels', label: 'Instagram Reels' },
  { value: 'instagram_feed', label: 'Instagram Feed' }, { value: 'tiktok', label: 'TikTok' },
]

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

export const hasKey = async (name: SecretName) => ((await studio.secretsStatus()) as Record<SecretName, boolean>)[name]
