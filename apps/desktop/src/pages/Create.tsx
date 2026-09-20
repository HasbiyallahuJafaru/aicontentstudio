import { useEffect, useState, type FormEvent } from 'react'
import { CaretRight, Scissors } from '@phosphor-icons/react'
import { call, FORMATS, GENRES, hasKey, label, PLATFORMS, TOPICS, useQuery, BackendError,
  type Brief, type Project, type Settings, type VoiceList } from '../lib/studio'
import { Button, Autocomplete, Choices, ErrorNote, Field, Input, PageHeader, Select, cx } from '../components/ui'

const PRESETS = [1, 3, 6]
// The write brief in three passes: what to make, how it sounds, how it looks. Only the first has required fields.
const STEPS = ['Brief', 'Delivery', 'Look'] as const
const ORIENTATIONS = [
  { value: '9:16', label: '9:16 — Shorts, Reels, TikTok' },
  { value: '16:9', label: '16:9 — landscape' },
  { value: '1:1', label: '1:1 — square' },
]

type ClipForm = { source: string; n: number | null; orientation: '9:16' | '16:9' | '1:1'; min_len: number; max_len: number; burn_captions: boolean; fps: number }

export function Create({ onCreated }: { onCreated: (id: string) => void }) {
  const { data: settings } = useQuery<Settings>('settings.get')
  const [mode, setMode] = useState<'write' | 'clip'>('write')
  const [brief, setBrief] = useState<Brief>()
  const [clip, setClip] = useState<ClipForm>({ source: '', n: null, orientation: '9:16', min_len: 30, max_len: 60, burn_captions: true, fps: 30 })
  const [custom, setCustom] = useState(false)
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [keySet, setKeySet] = useState<boolean>()
  const [groqSet, setGroqSet] = useState<boolean>()

  useEffect(() => { hasKey('DEEPSEEK_API_KEY').then(setKeySet); hasKey('GROQ_API_KEY').then(setGroqSet) }, [])

  useEffect(() => {
    if (settings && !brief) {
      setBrief({
        topic: label(settings.default_topic), tone: settings.default_tone, mood: '', audience: '',
        format: 'video_image', quantity: settings.default_quantity, platforms: ['youtube_shorts', 'instagram_reels', 'tiktok'],
        voice: '', fps: 30, target_seconds: null, subtitles: false, look_filter: 'auto',
        blur_background: false, parallax: false,
      })
      setCustom(!PRESETS.includes(settings.default_quantity))
    }
  }, [settings, brief])

  useEffect(() => {
    // window-level so Ctrl+Enter works after any click (e.g. right after using a dropdown, focus is on body)
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); submit() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!brief) return <PageHeader title="New project" />

  const writeValid = !!brief.topic.trim() && !!brief.platforms.length && brief.quantity >= 1 && brief.quantity <= 20
  const clipValid = clip.source.trim().length > 1

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    if (saving || (mode === 'write' ? !writeValid : !clipValid)) return
    // Ctrl+Enter walks the wizard forward; only the last step actually creates the project.
    if (mode === 'write' && step < STEPS.length - 1) { setStep(step + 1); return }
    setSaving(true)
    setError(undefined)
    try {
      const p = await call<Project>('projects.create', mode === 'clip'
        ? { brief: { ...clip, kind: 'clip', source: clip.source.trim() } }
        : { brief: { ...brief!, topic: brief!.topic.trim().toLowerCase() } })
      // A failed start still opens the project; its page shows the job error or the action button.
      if (mode === 'clip') await call('jobs.start', { project_id: p.id, kind: 'clip' }).catch(() => {})
      else if (keySet) await call('jobs.start', { project_id: p.id }).catch(() => {})
      onCreated(p.id)
    } catch (err) {
      setError(err as BackendError)
      setSaving(false)
    }
  }

  const clipSourceOk = clipValid
  return (
    <form onSubmit={submit}>
      <PageHeader title="New project" />
      <div className="grid grid-cols-[440px_minmax(0,1fr)] gap-5 max-[1180px]:grid-cols-[380px_minmax(0,1fr)]">
        <div className="glass grid content-start gap-7 p-8">
          <Choices legend="What do you want to make?" value={mode} onChange={(v) => setMode(v as typeof mode)}
            options={[{ value: 'write', label: 'Write content' }, { value: 'clip', label: 'Clip from video' }]} />

          {mode === 'write' ? <WriteForm brief={brief} setBrief={setBrief} custom={custom} setCustom={setCustom}
            keySet={keySet} error={error} saving={saving} step={step} setStep={setStep} /> : (
            <>
              <Field label="Video" hint="A YouTube or other link, or a path to a file on this computer.">
                {(id) => (
                  <Input id={id} value={clip.source} spellCheck={false} autoFocus
                    placeholder="https://… or C:\videos\talk.mp4" onChange={(e) => setClip({ ...clip, source: e.target.value })} />
                )}
              </Field>

              <Field label="Orientation">
                {(id) => (
                  <Select id={id} value={clip.orientation} options={ORIENTATIONS}
                    onChange={(v) => setClip({ ...clip, orientation: v as ClipForm['orientation'] })} />
                )}
              </Field>

              <div className="grid gap-2">
                <Choices legend="How many clips" value={clip.n ?? -1}
                  options={[{ value: -1, label: 'Auto' }, { value: 3, label: '3' }, { value: 5, label: '5' }, { value: 10, label: '10' }]}
                  onChange={(v: number) => setClip({ ...clip, n: v === -1 ? null : v })} />
                <p className="text-xs text-ink-3">Auto picks about one clip per minute of video, judging by what's said.</p>
              </div>

              <Choices legend="Captions" value={clip.burn_captions ? 'burn' : 'clean'}
                options={[{ value: 'burn', label: 'Burned in' }, { value: 'clean', label: 'Clean video' }]}
                onChange={(v) => setClip({ ...clip, burn_captions: v === 'burn' })} />

              <Choices legend="Frame rate" value={clip.fps}
                options={[{ value: 30, label: '30 fps' }, { value: 60, label: '60 fps' }]}
                onChange={(v: number) => setClip({ ...clip, fps: v })} />

              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink">
                  <CaretRight size={12} weight="bold" className="transition-transform duration-150 group-open:rotate-90" />
                  Advanced
                </summary>
                <div className="grid grid-cols-2 gap-4 pt-5">
                  <Field label="Shortest (s)" hint="Aim for clips at least this long.">
                    {(id) => <Input id={id} type="number" min={5} max={600} className="tnum" value={clip.min_len}
                      onChange={(e) => setClip({ ...clip, min_len: Math.max(5, Math.min(600, Number(e.target.value) || 30)) })} />}
                  </Field>
                  <Field label="Longest (s)" hint="Aim for clips at most this long.">
                    {(id) => <Input id={id} type="number" min={10} max={900} className="tnum" value={clip.max_len}
                      onChange={(e) => setClip({ ...clip, max_len: Math.max(10, Math.min(900, Number(e.target.value) || 60)) })} />}
                  </Field>
                </div>
              </details>

              {error && <ErrorNote error={error} />}

              <div className="grid gap-3 border-t border-line pt-6">
                <div><Button variant="primary" type="submit" disabled={!clipSourceOk || saving} kbd="Ctrl Enter">
                  <Scissors size={14} />{saving ? 'Starting' : 'Clip this video'}</Button></div>
                <p className="text-xs text-ink-3">
                  {groqSet && keySet
                    ? 'Groq transcribes the video, DeepSeek picks the moments. You can cancel at any time.'
                    : 'Add a Groq API key (transcription) and a DeepSeek API key (selection) in Settings to clip.'}
                </p>
              </div>
            </>
          )}
        </div>

        {mode === 'write'
          ? <BatchPreview brief={brief} />
          : <ClipPreviewPanel form={clip} groqSet={!!groqSet} deepseekSet={!!keySet} />}
      </div>
    </form>
  )
}

/** Walks back to an earlier step. Steps ahead stay locked until their turn, so the bar never lies about progress. */
function StepBar({ step, setStep }: { step: number; setStep: (n: number) => void }) {
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((label, i) => (
        <button key={label} type="button" disabled={i > step} onClick={() => setStep(i)}
          aria-current={i === step ? 'step' : undefined}
          className={cx('grid flex-1 gap-2 rounded-field pt-1 text-left text-[13px] transition-colors duration-200',
            'disabled:cursor-default', i === step ? 'font-medium text-ink' : i < step ? 'text-ink-2 hover:text-ink' : 'text-ink-3')}>
          <span className={cx('h-[2px] rounded-full transition-colors duration-300',
            i === step ? 'bg-accent' : i < step ? 'bg-line-strong' : 'bg-line')} />
          {label}
        </button>
      ))}
    </div>
  )
}

/** The write-content brief, split across STEPS so no single screen is a wall of controls. */
function WriteForm({ brief, setBrief, custom, setCustom, keySet, error, saving, step, setStep }: {
  brief: Brief; setBrief: (b: Brief) => void; custom: boolean; setCustom: (v: boolean) => void
  keySet?: boolean; error?: BackendError; saving: boolean; step: number; setStep: (n: number) => void
}) {
  const { data: voices } = useQuery<VoiceList>('tts.voices')
  const set = <K extends keyof Brief>(k: K, v: Brief[K]) => setBrief({ ...brief, [k]: v })
  const valid = brief.topic.trim() && brief.platforms.length && brief.quantity >= 1 && brief.quantity <= 20
  // Step 1 only owns the topic and quantity; platforms move to step 2, so Next must not wait on them.
  const canLeaveStep = step === 0 ? !!brief.topic.trim() && brief.quantity >= 1 && brief.quantity <= 20 : !!valid
  const last = step === STEPS.length - 1
  const voiceOptions = [
    { value: '', label: 'Studio default (Settings)' },
    ...(voices?.kokoro ?? []).map((v) => ({ value: `kokoro:${v}`, label: `Kokoro \u00b7 ${v}` })),
    ...(voices?.windows ?? []).map((v) => ({ value: `windows:${v}`, label: `Windows \u00b7 ${v}` })),
  ]
  return (
    <div className="grid gap-7">
      <StepBar step={step} setStep={setStep} />

      {/* key={step} remounts the panel, which replays the entry animation on every move. */}
      <div key={step} className="anim-page grid gap-7">
        {step === 0 && (
          <>
            <Field label="Topic" hint="Pick a theme or type your own.">
              {(id) => (
                <Autocomplete id={id} value={brief.topic} suggestions={TOPICS} maxLength={60} autoFocus
                  onChange={(v) => set('topic', v)} />
              )}
            </Field>

            <Field label="Genre" hint="The format and voice, modelled on the top-performing motivational pages.">
              {(id) => (
                <Select id={id} value={brief.tone} onChange={(v) => set('tone', v as Brief['tone'])}
                  options={GENRES} />
              )}
            </Field>

            <div className="grid gap-2">
              <Choices legend="Quantity" value={custom ? -1 : brief.quantity}
                options={[...PRESETS.map((n) => ({ value: n, label: String(n) })), { value: -1, label: 'Custom' }]}
                onChange={(v: number) => { setCustom(v === -1); if (v !== -1) set('quantity', v) }} />
              {custom && (
                <Input type="number" aria-label="Custom quantity" min={1} max={20} value={brief.quantity} className="w-24 tnum"
                  onChange={(e) => set('quantity', Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
              )}
            </div>

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
          </>
        )}

        {step === 1 && (
          <>
            <Choices legend="Output" value={brief.format} onChange={(v) => set('format', v)} options={FORMATS} />

            <Choices legend="Platforms" multiple value={brief.platforms} onChange={(v) => set('platforms', v)} options={PLATFORMS} />
            {!brief.platforms.length && <p className="-mt-5 text-xs text-danger">Choose at least one platform.</p>}

            <Field label="Narration voice" hint="Kokoro voices are local neural voices. Empty uses the Settings default.">
              {(id) => (
                <Select id={id} value={brief.voice} onChange={(v) => set('voice', v)} options={voiceOptions} />
              )}
            </Field>

            <Choices legend="Video length" value={brief.target_seconds ?? -1}
              options={[{ value: -1, label: 'Auto' }, { value: 15, label: '~15s' }, { value: 30, label: '~30s' },
                { value: 45, label: '~45s' }, { value: 60, label: '~60s' }]}
              onChange={(v: number) => set('target_seconds', v === -1 ? null : v)} />
          </>
        )}

        {step === 2 && (
          <>
            <Choices legend="Subtitles" value={brief.subtitles ? 'on' : 'off'}
              options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]}
              onChange={(v) => set('subtitles', v === 'on')} />

            <Choices legend="Frame rate" value={brief.fps}
              options={[{ value: 30, label: '30 fps' }, { value: 60, label: '60 fps' }]}
              onChange={(v: number) => set('fps', v)} />

            <Field label="Look">
              {(id) => (
                <Select id={id} value={brief.look_filter} onChange={(v) => set('look_filter', v as Brief['look_filter'])}
                  options={[
                    { value: 'auto', label: 'Auto (matches the genre)' },
                    { value: 'none', label: 'Natural (no filter)' }, { value: 'warm', label: 'Warm' },
                    { value: 'cool', label: 'Cool' }, { value: 'mono', label: 'Mono' },
                    { value: 'vivid', label: 'Vivid' }]} />
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Choices legend="Blur background" value={brief.blur_background ? 'on' : 'off'}
                options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]}
                onChange={(v) => set('blur_background', v === 'on')} />
              <Choices legend="Parallax move" value={brief.parallax ? 'on' : 'off'}
                options={[{ value: 'off', label: 'Off' }, { value: 'on', label: 'On' }]}
                onChange={(v) => set('parallax', v === 'on')} />
            </div>
          </>
        )}
      </div>

      {error && <ErrorNote error={error} />}

      <div className="grid gap-3 border-t border-line pt-6">
        <div className="flex items-center gap-2">
          {step > 0 && <Button type="button" onClick={() => setStep(step - 1)}>Back</Button>}
          {last ? (
            <Button variant="primary" type="submit" disabled={!valid || saving} kbd="Ctrl Enter">
              {saving ? 'Starting' : keySet ? 'Create and generate' : 'Save as draft'}</Button>
          ) : (
            <Button variant="primary" type="button" disabled={!canLeaveStep} onClick={() => setStep(step + 1)} kbd="Ctrl Enter">
              Next</Button>
          )}
        </div>
        <p className="text-xs text-ink-3">
          {!last ? `${STEPS[step + 1]} next. Everything here has a working default, so you can skip ahead.`
            : keySet ? 'DeepSeek plans the batch, then writes each piece. You can cancel at any time.'
              : 'Add your DeepSeek API key in Settings to generate. The brief is saved as a draft until then.'}
        </p>
      </div>
    </div>
  )
}

/** What clipping produces: one 9:16 frame per clip and the pipeline in words. */
function ClipPreviewPanel({ form, groqSet, deepseekSet }: { form: ClipForm; groqSet: boolean; deepseekSet: boolean }) {
  const [w, h] = form.orientation === '16:9' ? [16, 9] : form.orientation === '1:1' ? [1, 1] : [9, 16]
  const ready = groqSet && deepseekSet
  return (
    <section aria-label="Clip preview" className="glass relative isolate sticky top-0 self-start overflow-hidden p-7">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(80%_60%_at_80%_0%,rgb(240_135_58/0.18),transparent_70%)]" />
      <div className="flex items-baseline justify-between gap-4 pb-6">
        <h2 className="font-display text-lg font-semibold tracking-[-0.02em]">Clip from video</h2>
        <p className="tnum text-xs text-ink-3">{form.n ? `${form.n} clips` : 'auto count'}</p>
      </div>
      <div className="flex items-end gap-3">
        <div className="rounded-[10px] bg-black/30 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1)]"
          style={{ width: form.orientation === '16:9' ? 216 : form.orientation === '1:1' ? 122 : 69, aspectRatio: `${w} / ${h}` }} />
        <div className="grid gap-1.5 pb-1">
          {[1, 2, 3].map((i) => (
            <div key={i} className={cx('rounded-[8px] bg-black/20 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.08)]', i === 1 ? 'h-5 w-40' : 'h-3 w-32')} />
          ))}
        </div>
      </div>
      <ol className="grid gap-2.5 pt-6 text-[13px] text-ink-2">
        <li>1. The video downloads (or a local file is used as-is).</li>
        <li>2. Groq transcribes every word with timestamps.</li>
        <li>3. DeepSeek finds the {form.min_len}-{form.max_len}s moments that stand alone and writes per-platform post copy.</li>
        <li>4. Each clip is cropped to the speaker, captioned{form.burn_captions ? ', captions burned in,' : ''} and rendered as {form.orientation} MP4.</li>
      </ol>
      <p className="pt-5 text-xs text-ink-3">
        {ready ? 'Every clip keeps its caption file, cover frame and post copy for review here.'
          : 'Needs a Groq key and a DeepSeek key in Settings before clipping can start.'}
      </p>
    </section>
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
