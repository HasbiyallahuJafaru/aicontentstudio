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
export type Project = { id: string; name: string; status: string; brief: Brief; created_at: string; updated_at: string }
export type Settings = {
  ai_model: string; ai_temperature: number; ai_max_tokens: number
  default_topic: string; default_tone: Tone; default_quantity: number
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

/** Load data from the backend; reloads when the backend (re)becomes ready. */
export function useQuery<T>(method: string, params?: object) {
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
  }, [method, key, status.state, tick])
  return { data, error, loading: data === undefined && !error, reload: () => setTick((t) => t + 1) }
}

export const label = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')

export function formatDate(iso: string) {
  const d = new Date(iso)
  const today = new Date().toDateString() === d.toDateString()
  return today
    ? `Today, ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
}
