import { useEffect, useState, type FormEvent } from 'react'
import { CaretRight } from '@phosphor-icons/react'
import { call, FORMATS, hasKey, label, PLATFORMS, TONES, TOPICS, useQuery, BackendError, type Brief, type Project, type Settings } from '../lib/studio'
import { Button, Choices, ErrorNote, Field, Input, PageHeader, cx } from '../components/ui'

const PRESETS = [1, 3, 6]

export function Create({ onCreated }: { onCreated: (id: string) => void }) {
  const { data: settings } = useQuery<Settings>('settings.get')
  const [brief, setBrief] = useState<Brief>()
  const [custom, setCustom] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [keySet, setKeySet] = useState<boolean>()

  useEffect(() => { hasKey('DEEPSEEK_API_KEY').then(setKeySet) }, [])

  useEffect(() => {
    if (settings && !brief) {
      setBrief({
        topic: label(settings.default_topic), tone: settings.default_tone, mood: '', audience: '',
        format: 'automatic', quantity: settings.default_quantity, platforms: ['youtube_shorts', 'instagram_reels', 'tiktok'],
      })
      setCustom(!PRESETS.includes(settings.default_quantity))
    }
  }, [settings, brief])

  if (!brief) return <PageHeader title="New project" />
  const set = <K extends keyof Brief>(k: K, v: Brief[K]) => setBrief({ ...brief, [k]: v })
  const valid = brief.topic.trim() && brief.platforms.length && brief.quantity >= 1 && brief.quantity <= 20

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    if (!valid || saving) return
    setSaving(true)
    setError(undefined)
    try {
      const p = await call<Project>('projects.create', { brief: { ...brief, topic: brief!.topic.trim().toLowerCase() } })
      // A failed start still opens the project; its page shows the job error or the Generate button.
      if (keySet) await call('jobs.start', { project_id: p.id }).catch(() => {})
      onCreated(p.id)
    } catch (err) {
      setError(err as BackendError)
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} onKeyDown={(e) => (e.ctrlKey || e.metaKey) && e.key === 'Enter' && submit()}>
      <PageHeader title="New project" />
      <div className="grid grid-cols-[440px_minmax(0,1fr)] gap-5 max-[1180px]:grid-cols-[380px_minmax(0,1fr)]">
        <div className="glass grid content-start gap-7 p-8">
          <Field label="Topic" hint="Pick a theme or type your own.">
            {(id) => (
              <>
                <Input id={id} list="topics" value={brief.topic} maxLength={60} onChange={(e) => set('topic', e.target.value)} autoFocus />
                <datalist id="topics">{TOPICS.map((t) => <option key={t} value={t} />)}</datalist>
              </>
            )}
          </Field>

          <Choices legend="Tone" value={brief.tone} onChange={(v) => set('tone', v)}
            options={TONES.map((t) => ({ value: t, label: label(t) }))} />

          <Choices legend="Output" value={brief.format} onChange={(v) => set('format', v)} options={FORMATS} />

          <div className="grid gap-2">
            <Choices legend="Quantity" value={custom ? -1 : brief.quantity}
              options={[...PRESETS.map((n) => ({ value: n, label: String(n) })), { value: -1, label: 'Custom' }]}
              onChange={(v: number) => { setCustom(v === -1); if (v !== -1) set('quantity', v) }} />
            {custom && (
              <Input type="number" aria-label="Custom quantity" min={1} max={20} value={brief.quantity} className="w-24 tnum"
                onChange={(e) => set('quantity', Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
            )}
          </div>

          <Choices legend="Platforms" multiple value={brief.platforms} onChange={(v) => set('platforms', v)} options={PLATFORMS} />
          {!brief.platforms.length && <p className="-mt-5 text-xs text-danger">Choose at least one platform.</p>}

          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink">
              <CaretRight size={12} weight="bold" className="transition-transform duration-150 group-open:rotate-90" />
              Advanced
            </summary>
            <div className="grid gap-5 pt-5">
              <Field label="Mood" hint="Optional, for example quiet determination.">
                {(id) => <Input id={id} value={brief.mood} maxLength={80} onChange={(e) => set('mood', e.target.value)} />}
              </Field>
              <Field label="Audience" hint="Optional, for example young professionals.">
                {(id) => <Input id={id} value={brief.audience} maxLength={80} onChange={(e) => set('audience', e.target.value)} />}
              </Field>
            </div>
          </details>

          {error && <ErrorNote error={error} />}

          <div className="grid gap-3 border-t border-line pt-6">
            <div><Button variant="primary" type="submit" disabled={!valid || saving} kbd="Ctrl Enter">{saving ? 'Starting' : keySet ? 'Create and generate' : 'Save as draft'}</Button></div>
            <p className="text-xs text-ink-3">{keySet ? 'DeepSeek plans the batch, then writes each piece. You can cancel at any time.'
              : 'Add your DeepSeek API key in Settings to generate. The brief is saved as a draft until then.'}</p>
          </div>
        </div>

        <BatchPreview brief={brief} />
      </div>
    </form>
  )
}

/** What the batch will produce: one frame per output, at the real aspect ratio. */
function BatchPreview({ brief }: { brief: Brief }) {
  const frames = Array.from({ length: brief.quantity }, (_, i) => i)
  const kinds = brief.format === 'video_image' ? ['video', 'image'] : [brief.format === 'image' ? 'image' : 'video']
  const spec = {
    automatic: '1080 × 1920 video or 1080 × 1350 image, chosen per piece',
    video: '1080 × 1920 video, 9:16',
    image: '1080 × 1350 image, 4:5',
    video_image: 'A 9:16 video and a 4:5 image per piece',
  }[brief.format]

  return (
    <section aria-label="Batch preview" className="glass relative isolate sticky top-0 self-start overflow-hidden p-7">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(80%_60%_at_80%_0%,rgb(240_135_58/0.18),transparent_70%)]" />
      <div className="flex items-baseline justify-between gap-4 pb-6">
        <h2 className="font-display text-lg font-semibold tracking-[-0.02em]">{brief.topic.trim() || 'Untitled'}, {brief.tone}</h2>
        <p className="tnum text-xs text-ink-3">{brief.quantity} {brief.quantity === 1 ? 'piece' : 'pieces'}</p>
      </div>
      <div className="grid max-h-[calc(100dvh-280px)] grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-3 overflow-y-auto">
        {frames.map((i) => (
          <div key={`${brief.format}-${i}`} className="anim-slot grid gap-1.5" style={{ '--i': i } as React.CSSProperties}>
            <div className={cx('grid gap-1.5', kinds.length === 2 && 'grid-cols-[9fr_7.2fr] items-end')}>
              {kinds.map((k) => (
                <div key={k} className={cx('rounded-[10px] bg-black/30 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)]', k === 'video' ? 'aspect-[9/16]' : 'aspect-[4/5]')} />
              ))}
            </div>
            <span className="tnum text-2xs text-ink-3">{String(i + 1).padStart(3, '0')}</span>
          </div>
        ))}
      </div>
      <p className="pt-5 text-xs text-ink-3">{spec}. For {brief.platforms.map((p) => PLATFORMS.find((x) => x.value === p)!.label).join(', ') || 'no platform yet'}.</p>
    </section>
  )
}
