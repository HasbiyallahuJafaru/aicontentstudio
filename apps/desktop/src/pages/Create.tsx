import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, CaretRight, Check, Copy, DownloadSimple, FolderOpen, Scissors, UploadSimple } from '@phosphor-icons/react'
import { call, studio, DEFAULT_CAPTIONS, GENRES, hasKey, label, PLATFORMS, TOPICS, useQuery, voiceOptions, BackendError, startFailures,
  type Brief, type CaptionStyle, type DownloadStatus, type Project, type Settings, type VoiceList } from '../lib/studio'
import { Button, Autocomplete, Choices, ErrorNote, Field, Input, PageHeader, Select, Textarea, cx, spot } from '../components/ui'
import { CaptionPicker, ImageDesignPicker, PalettePicker } from '../components/StylePicker'

const PRESETS = [1, 3, 6]
// Each kind of project is its own short flow; the user picks the kind first, then fills only what that kind needs.
type Kind = 'images' | 'videos' | 'clips'
const VIDEO_STEPS = ['Brief', 'Delivery', 'Look'] as const
const IMAGE_STEPS = ['Quotes', 'Design'] as const
// one bundled photo per kind (scripts/make-create-art.py): the app never fetches the chooser's art
const ART = import.meta.glob('../assets/create/*.webp', { eager: true, import: 'default' }) as Record<string, string>
const artFor = (k: Kind) => ART[`../assets/create/${k}.webp`]
const TITLES: Record<Kind, string> = { images: 'Quote images', videos: 'Narrated videos', clips: 'Clips from a video' }
const MAX_QUOTE = 180
const MAX_QUOTES = 100  // pasted or imported; the AI writes up to 20
const MIN_CLIP = 60  // seconds: the floor (config.MIN_CLIP), owner 2026-11-10: every clip runs a full minute
const ORIENTATIONS = [
  { value: '9:16', label: '9:16 — Shorts, Reels, TikTok' },
  { value: '16:9', label: '16:9 — landscape' },
  { value: '1:1', label: '1:1 — square' },
]

type ClipForm = { source: string; n: number | null; orientation: '9:16' | '16:9' | '1:1'; min_len: number; max_len: number; burn_captions: boolean; fps: number; captions: CaptionStyle }
type Sample = { design: string; label: string; src: string }

const quoteLines = (text: string) => text.split('\n').map((l) => l.trim()).filter(Boolean)

export function Create({ onCreated }: { onCreated: (id: string) => void }) {
  const { data: settings } = useQuery<Settings>('settings.get')
  const [kind, setKind] = useState<Kind | null>(null)
  const [brief, setBrief] = useState<Brief>()
  const [clip, setClip] = useState<ClipForm>({ source: '', n: null, orientation: '9:16', min_len: MIN_CLIP, max_len: 120, burn_captions: true, fps: 30, captions: DEFAULT_CAPTIONS })
  const [own, setOwn] = useState(false)  // quote images: the user's own lines instead of the AI's
  const [quotesText, setQuotesText] = useState('')
  const [custom, setCustom] = useState(false)
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<BackendError>()
  const [keySet, setKeySet] = useState<boolean>()

  useEffect(() => { hasKey('OPENROUTER_API_KEY').then(setKeySet) }, [])

  useEffect(() => {
    if (settings && !brief) {
      setBrief({
        topic: label(settings.default_topic), tone: settings.default_tone, mood: '', audience: '',
        format: 'video', quantity: settings.default_quantity, platforms: ['youtube_shorts', 'instagram_reels', 'tiktok'],
        voice: '', fps: 30, target_seconds: null, subtitles: true, look_filter: 'auto',
        blur_background: false, parallax: false, captions: DEFAULT_CAPTIONS, image_design: 'auto',
        image_font: 'auto', image_position: 'auto', palette: 'auto',
      })
      setCustom(!PRESETS.includes(settings.default_quantity))
    }
  }, [settings, brief])

  const lines = quoteLines(quotesText)
  const quotesOk = lines.length >= 1 && lines.length <= MAX_QUOTES && lines.every((l) => l.length <= MAX_QUOTE)
  const ownQuotes = kind === 'images' && own
  // with their own quotes the theme is optional: a blank one becomes the first quote's opening words
  const briefOk = !!brief && (ownQuotes || !!brief.topic.trim()) && !!brief.platforms.length && brief.quantity >= 1 && brief.quantity <= 20
  const valid = kind === 'clips' ? clip.source.trim().length > 1 : briefOk && (!ownQuotes || quotesOk)
  const steps = kind === 'images' ? IMAGE_STEPS : VIDEO_STEPS

  useEffect(() => {
    // window-level so Ctrl+Enter works after any click (e.g. right after using a dropdown, focus is on body)
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); submit() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!brief) return <PageHeader title="New project" />

  function pick(k: Kind) {
    setKind(k)
    setStep(0)
    setError(undefined)
    if (k === 'images') setBrief({ ...brief!, format: 'image', platforms: ['instagram_feed'] })
    if (k === 'videos') setBrief({ ...brief!, format: 'video', platforms: ['youtube_shorts', 'instagram_reels', 'tiktok'] })
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    if (!kind || saving || !valid) return
    // Ctrl+Enter walks the steps forward; only the last step actually creates the project.
    if (kind !== 'clips' && step < steps.length - 1) { setStep(step + 1); return }
    setSaving(true)
    setError(undefined)
    try {
      const p = await call<Project>('projects.create', kind === 'clips'
        ? { brief: { ...clip, kind: 'clip', source: clip.source.trim() } }
        : { brief: { ...brief!, quotes: ownQuotes ? lines : [],
            topic: (brief!.topic.trim() || lines[0]?.replace(/[.!?,;:].*$/, '').trim().slice(0, 60) || 'my quotes').toLowerCase() } })
      // A failed start still opens the project; its page shows the job error or the action button.
      const failed = (e: unknown) => { startFailures.set(p.id, e as BackendError) }
      if (kind === 'clips') await call('jobs.start', { project_id: p.id, kind: 'clip' }).catch(failed)
      else if (keySet) await call('jobs.start', { project_id: p.id }).catch(failed)
      onCreated(p.id)
    } catch (err) {
      setError(err as BackendError)
      setSaving(false)
    }
  }

  if (!kind) return <Chooser onPick={pick} />

  const back = <Button type="button" onClick={() => setKind(null)}><ArrowLeft size={14} />All formats</Button>
  return (
    <form onSubmit={submit}>
      <PageHeader title={TITLES[kind]}>{back}</PageHeader>
      <div className="grid grid-cols-[440px_minmax(0,1fr)] gap-5 max-[1180px]:grid-cols-[380px_minmax(0,1fr)]">
        <div className="glass grid content-start gap-7 p-8">
          {kind === 'images' && <ImagesForm brief={brief} setBrief={setBrief} own={own} setOwn={setOwn}
            quotesText={quotesText} setQuotesText={setQuotesText} custom={custom} setCustom={setCustom}
            keySet={keySet} error={error} saving={saving} step={step} setStep={setStep} valid={valid} />}
          {kind === 'videos' && <VideoForm brief={brief} setBrief={setBrief} custom={custom} setCustom={setCustom}
            keySet={keySet} error={error} saving={saving} step={step} setStep={setStep} />}
          {kind === 'clips' && <ClipFormFields clip={clip} setClip={setClip} keySet={keySet} error={error} saving={saving} />}
        </div>

        {kind === 'images' && <QuotePreview brief={brief} quotes={own ? lines : []} />}
        {kind === 'videos' && <BatchPreview brief={brief} />}
        {kind === 'clips' && <ClipPreviewPanel form={clip} ready={!!keySet} />}
      </div>
    </form>
  )
}

/** The first screen: what are you making? Each card is one bundled photo (scripts/make-create-art.py, Pexels,
 *  credits in assets/create) with its words on a solid white band laid over it: no gradient, no scrim. */
function Chooser({ onPick }: { onPick: (k: Kind) => void }) {
  const options: { kind: Kind; line: string; gets: string }[] = [
    { kind: 'images', line: 'Designed quote pictures for the feed. Paste your own lines or let the AI write them.',
      gets: '4:5 images, no voice needed' },
    { kind: 'videos', line: 'A voiced short cut to stock footage, colour graded, with subtitles if you want them.',
      gets: '9:16 video, a matching picture optional' },
    { kind: 'clips', line: 'Cut a long talk, podcast or interview into captioned shorts that stand alone.',
      gets: '9:16, 16:9 or 1:1 clips' },
  ]
  return (
    <div>
      <PageHeader title="New project" />
      <h2 className="anim-drift pb-6 text-[15px] text-ink-2" style={{ '--d': '120ms' } as React.CSSProperties}>What are you making?</h2>
      <div className="grid grid-cols-3 gap-5 max-[1100px]:grid-cols-1">
        {options.map((o, i) => (
          <button key={o.kind} type="button" onClick={() => onPick(o.kind)}
            className={cx('glass no-drag group relative isolate block h-[clamp(420px,calc(100dvh-280px),560px)] overflow-hidden text-left',
              'transition-transform duration-300 ease-[var(--ease-premium)] hover:-translate-y-1 max-[1100px]:h-[360px]',
              'focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent')}
            style={{ animationDelay: `${140 + i * 60}ms` }}>
            <img src={artFor(o.kind)} alt="" draggable={false}
              className="absolute inset-0 -z-10 h-full w-full object-cover transition-transform duration-700 ease-[var(--ease-premium)] group-hover:scale-[1.04]" />
            <div className="absolute inset-x-3 bottom-3 grid gap-2 rounded-field bg-panel p-6 shadow-[0_18px_40px_-20px_rgb(17_18_20/0.45)]">
              <h3 className="flex items-center justify-between font-display text-lg font-semibold tracking-[-0.02em]">
                {TITLES[o.kind]}
                <span className="grid size-8 place-items-center rounded-full bg-ink text-white transition-transform duration-300 ease-[var(--ease-premium)] group-hover:translate-x-1">
                  <CaretRight size={14} weight="bold" /></span>
              </h3>
              <p className="text-[13px] leading-relaxed text-ink-2">{o.line}</p>
            </div>
            <span className="absolute left-4 top-4 rounded-full bg-ink px-3 py-1.5 text-2xs font-medium text-white">{o.gets}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** Walks back to an earlier step. Steps ahead stay locked until their turn, so the bar never lies about progress. */
function StepBar({ steps, step, setStep }: { steps: readonly string[]; step: number; setStep: (n: number) => void }) {
  return (
    <div className="flex items-center gap-1">
      {steps.map((label, i) => (
        <button key={label} type="button" disabled={i > step} onClick={() => setStep(i)}
          aria-current={i === step ? 'step' : undefined}
          className={cx('grid flex-1 gap-2 rounded-field pt-1 text-left text-[13px] transition-colors duration-200',
            'disabled:cursor-default', i === step ? 'font-medium text-ink' : i < step ? 'text-ink-2 hover:text-ink' : 'text-ink-3')}>
          {/* the segment fills from the left like a drawn line as its step is reached */}
          <span className="relative h-[2px] overflow-hidden rounded-full bg-line">
            <span className={cx('absolute inset-0 origin-left transition-[transform,background-color] duration-500 ease-[var(--ease-premium)]',
              i === step ? 'bg-pop' : 'bg-line-strong')} style={{ transform: `scaleX(${i <= step ? 1 : 0})` }} />
          </span>
          {label}
        </button>
      ))}
    </div>
  )
}

/** Steps with the direction-aware entrance, the error and the Back / Next / Create row. */
function Stepped({ steps, step, setStep, canNext, canCreate, error, saving, keySet, createLabel, lastHint, children }: {
  steps: readonly string[]; step: number; setStep: (n: number) => void; canNext: boolean; canCreate: boolean
  error?: BackendError; saving: boolean; keySet?: boolean; createLabel: string; lastHint: string; children: React.ReactNode
}) {
  const last = step === steps.length - 1
  // the direction of travel: forward steps arrive from the right, going back arrives from the left
  const prev = useRef(step)
  const dir = step >= prev.current ? 'anim-step-next' : 'anim-step-back'
  useEffect(() => { prev.current = step }, [step])
  return (
    <div className="grid gap-7">
      <StepBar steps={steps} step={step} setStep={setStep} />
      {/* key={step} remounts the panel, which replays the entry animation on every move. */}
      <div key={step} className={cx(dir, 'grid gap-7')}>{children}</div>
      {error && <ErrorNote error={error} />}
      <div className="grid gap-3 border-t border-line pt-6">
        <div className="flex items-center gap-2">
          {step > 0 && <Button type="button" onClick={() => setStep(step - 1)}>Back</Button>}
          {/* distinct keys: React must not reuse the Next element as the submit button, or the click that
              reaches the last step lands on a submit and creates the project */}
          {last ? (
            <Button key="create" variant="primary" type="submit" disabled={!canCreate || saving} kbd="Ctrl Enter">
              {saving ? 'Starting' : keySet ? createLabel : 'Save as draft'}</Button>
          ) : (
            <Button key="next" variant="primary" type="button" disabled={!canNext} kbd="Ctrl Enter"
              onClick={(e) => { e.preventDefault(); setStep(step + 1) }}>
              Next</Button>
          )}
        </div>
        <p className="text-xs text-ink-3">
          {!last ? `${steps[step + 1]} next. Everything here has a working default, so you can skip ahead.`
            : keySet ? lastHint : 'Add your OpenRouter API key in Settings to generate. The brief is saved as a draft until then.'}
        </p>
      </div>
    </div>
  )
}

function Quantity({ brief, set, custom, setCustom }: {
  brief: Brief; set: <K extends keyof Brief>(k: K, v: Brief[K]) => void; custom: boolean; setCustom: (v: boolean) => void
}) {
  return (
    <div className="grid gap-2">
      <Choices legend="How many" value={custom ? -1 : brief.quantity}
        options={[...PRESETS.map((n) => ({ value: n, label: String(n) })), { value: -1, label: 'Custom' }]}
        onChange={(v: number) => { setCustom(v === -1); if (v !== -1) set('quantity', v) }} />
      {custom && (
        <Input type="number" aria-label="Custom quantity" min={1} max={20} value={brief.quantity} className="w-24 tnum"
          onChange={(e) => set('quantity', Math.max(1, Math.min(20, Number(e.target.value) || 1)))} />
      )}
    </div>
  )
}

/** Quote images: the quotes (the AI's or the user's own), then the design, and optionally a voiced 9:16 video of each picture. */
function ImagesForm({ brief, setBrief, own, setOwn, quotesText, setQuotesText, custom, setCustom, keySet, error,
  saving, step, setStep, valid }: {
  brief: Brief; setBrief: (b: Brief) => void; own: boolean; setOwn: (v: boolean) => void
  quotesText: string; setQuotesText: (v: string) => void; custom: boolean; setCustom: (v: boolean) => void
  keySet?: boolean; error?: BackendError; saving: boolean; step: number; setStep: (n: number) => void; valid: boolean
}) {
  const set = <K extends keyof Brief>(k: K, v: Brief[K]) => setBrief({ ...brief, [k]: v })
  const lines = quoteLines(quotesText)
  const long = lines.findIndex((l) => l.length > MAX_QUOTE)
  const n = own ? lines.length : brief.quantity
  const { data: voices } = useQuery<VoiceList>('tts.voices')
  const voiced = brief.format === 'image_voiced'
  return (
    <Stepped steps={IMAGE_STEPS} step={step} setStep={setStep} canNext={valid} canCreate={valid} error={error}
      saving={saving} keySet={keySet} createLabel={`Create ${n} ${n === 1 ? 'quote' : 'quotes'}${voiced ? ' with voiced videos' : ''}`}
      lastHint="The AI picks a photo for each quote and writes its caption. You confirm the photos, then render and export.">
      {step === 0 && (
        <>
          <Choices legend="Who writes the quotes?" value={own ? 'own' : 'ai'} onChange={(v) => setOwn(v === 'own')}
            options={[{ value: 'ai', label: 'The AI' }, { value: 'own', label: 'I have my own' }]} />

          {own && <QuotesInput value={quotesText} onChange={setQuotesText} long={long} count={lines.length} />}

          <Field label={own ? 'Theme' : 'Topic'} hint={own ? 'Optional. Names the project and steers the photos and captions.' : 'Pick a theme or type your own.'}>
            {(id) => <Autocomplete id={id} value={brief.topic} suggestions={TOPICS} maxLength={60} autoFocus={!own}
              onChange={(v) => set('topic', v)} />}
          </Field>

          <Field label="Genre" hint="Sets the voice of the writing and which designs Auto reaches for.">
            {(id) => <Select id={id} value={brief.tone} onChange={(v) => set('tone', v as Brief['tone'])} options={GENRES} />}
          </Field>

          {!own && <Quantity brief={brief} set={set} custom={custom} setCustom={setCustom} />}
        </>
      )}

      {step === 1 && (
        <>
          <Choices legend="Make" value={brief.format} onChange={(v) => setBrief({ ...brief, format: v as Brief['format'],
              platforms: v === 'image_voiced' ? ['instagram_feed', 'instagram_reels', 'tiktok', 'youtube_shorts'] : ['instagram_feed'] })}
            options={[{ value: 'image', label: 'Pictures' }, { value: 'image_voiced', label: 'Pictures + voiced videos' }]} />
          {brief.format === 'image_voiced' && (
            <Field label="Voice" hint="Each quote is also read aloud over its picture as a 9:16 video, 10 seconds or more. One voice across the series keeps it recognisable.">
              {(id) => <Select id={id} value={brief.voice} onChange={(v) => set('voice', v)} options={voiceOptions(voices)} />}
            </Field>
          )}
          <ImageDesignPicker design={brief.image_design} font={brief.image_font} position={brief.image_position}
            onChange={(patch) => setBrief({ ...brief, ...patch })} />
          <PalettePicker value={brief.palette} onChange={(v) => set('palette', v)} />
          <Choices legend="Post to" multiple value={brief.platforms} onChange={(v) => set('platforms', v)} options={PLATFORMS} />
          {!brief.platforms.length && <p className="-mt-5 text-xs text-danger">Choose at least one platform.</p>}
        </>
      )}
    </Stepped>
  )
}

type CsvResult = { quotes: string[]; skipped: { row: number; reason: string }[]; authors: number; header: boolean }

/** The CSV the importer reads, as a file to copy: a header, real attributed quotes, original lines with no author,
 *  and a comma inside a quoted field. quotes_csv.py parses it as is (checked 2026-11-08). */
const SAMPLE_ROWS = [
  'quote,author',
  'Waste no more time arguing about what a good man should be. Be one.,Marcus Aurelius',
  'We suffer more often in imagination than in reality.,Seneca',
  'Well done is better than well said.,Benjamin Franklin',
  'Your comfort zone will kill you.,',
  '"Small steps, taken daily, still count.",',
]

/** A prompt to paste into any AI chat so it writes a quote list this importer reads first time. */
const SAMPLE_PROMPT = [
  'Write 20 short quotes about [YOUR TOPIC] for social media quote images.',
  '',
  'Reply with CSV only, no other text, in exactly this format:',
  '',
  ...SAMPLE_ROWS,
  '',
  'Rules:',
  '- The first row is the header: quote,author',
  `- One quote per row, at most ${MAX_QUOTE} characters. 6 to 22 words reads best on an image.`,
  '- Wrap a quote in double quotes if it contains a comma.',
  '- author is the real person who said or wrote it. Only attribute a quote you are sure is real and correctly attributed; never invent an attribution. Leave author empty for original lines.',
  '- No numbering, emojis, hashtags or repeats.',
  `- At most ${MAX_QUOTES} rows.`,
].join('\n')

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** The user's own quotes: typed, pasted, or imported from a CSV (button or drop). The CSV is parsed by the
 *  backend (quotes_csv.py) and lands here as editable lines, so the box stays the single source of truth. */
function QuotesInput({ value, onChange, long, count }: { value: string; onChange: (v: string) => void; long: number; count: number }) {
  const file = useRef<HTMLInputElement>(null)
  const [note, setNote] = useState<{ name: string } & CsvResult>()
  const [copied, setCopied] = useState(false)
  const [failed, setFailed] = useState<BackendError>()
  const [over, setOver] = useState(false)

  async function load(f: File) {
    setFailed(undefined)
    setNote(undefined)
    if (f.size > 2_000_000) return setFailed(new BackendError('That file is too big for a quote list.', `${f.name} is over 2 MB.`))
    const bytes = new Uint8Array(await f.arrayBuffer())
    let bin = ''
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
    try {
      const r = await call<CsvResult>('quotes.from_csv', { data_b64: btoa(bin) })
      onChange([...quoteLines(value), ...r.quotes].join('\n'))
      setNote({ name: f.name, ...r })
    } catch (e) {
      setFailed(e as BackendError)
    }
  }

  const error = long >= 0 ? `Line ${long + 1} is over ${MAX_QUOTE} characters.`
    : count > MAX_QUOTES ? `Up to ${MAX_QUOTES} quotes per project; this has ${count}.` : undefined
  return (
    <div className="grid gap-3">
      <Field label="Your quotes" error={error}
        hint={`One per line, up to ${MAX_QUOTES}. Add an author after a dash: Waste no more time. — Marcus Aurelius`}>
        {(id) => <Textarea id={id} rows={7} value={value} autoFocus spellCheck
          className={cx(over && 'border-ink bg-white')}
          placeholder={'Your comfort zone will kill you.\nLife has no script. Live it.\nOr drop a CSV here'}
          onChange={(e) => onChange(e.target.value)}
          onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setOver(true) } }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { const f = e.dataTransfer.files[0]; setOver(false); if (f) { e.preventDefault(); load(f) } }} />}
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <input ref={file} type="file" accept=".csv,.tsv,.txt,text/csv" className="sr-only" aria-label="Import a CSV of quotes"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) load(f) }} />
        <Button type="button" onClick={() => file.current?.click()}>Import a CSV</Button>
        {count > 0 && <Button type="button" onClick={() => { onChange(''); setNote(undefined) }}>Clear</Button>}
        <span className="tnum text-xs text-ink-3">{count} {count === 1 ? 'quote' : 'quotes'}</span>
      </div>
      <p className="text-xs text-ink-3">A quote column and an optional author column, with or without a header row. Excel, Sheets and Numbers exports all work.</p>
      <div className="grid gap-2 rounded-field bg-black/[0.04] px-4 py-3 text-xs text-ink-2 shadow-[inset_0_0_0_1px_rgb(17_18_20/0.08)]">
        <p>Not sure of the format? Download the sample, or copy a prompt for ChatGPT, Claude or Gemini. Swap in your topic, save its reply as a .csv file and import it.</p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => download('quotes-sample.csv', '﻿' + SAMPLE_ROWS.join('\r\n') + '\r\n', 'text/csv;charset=utf-8')}>
            <DownloadSimple size={14} />Download sample CSV
          </Button>
          <Button type="button" onClick={async () => { await navigator.clipboard.writeText(SAMPLE_PROMPT); setCopied(true); setTimeout(() => setCopied(false), 1800) }}>
            {copied ? <Check size={14} weight="bold" /> : <Copy size={14} />}{copied ? 'Prompt copied' : 'Copy AI prompt'}
          </Button>
          <Button type="button" variant="ghost" onClick={() => download('quotes-prompt.txt', SAMPLE_PROMPT, 'text/plain;charset=utf-8')}>
            Download prompt
          </Button>
        </div>
      </div>
      {note && (
        <div role="status" className="grid gap-1 rounded-field bg-black/[0.04] px-4 py-3 text-xs text-ink-2 shadow-[inset_0_0_0_1px_rgb(17_18_20/0.08)]">
          <p><span className="font-medium text-ink">Added {note.quotes.length} {note.quotes.length === 1 ? 'quote' : 'quotes'}</span> from {note.name}
            {note.authors ? `, ${note.authors} with an author` : ''}.</p>
          {note.skipped.length > 0 && (
            <p>Skipped {note.skipped.length}: {note.skipped.slice(0, 4).map((s) => `row ${s.row} (${s.reason})`).join(', ')}
              {note.skipped.length > 4 ? ` and ${note.skipped.length - 4} more` : ''}.</p>
          )}
        </div>
      )}
      {failed && <ErrorNote error={failed} />}
    </div>
  )
}

/** Narrated videos: the brief in three passes (what, how it sounds, how it looks). */
function VideoForm({ brief, setBrief, custom, setCustom, keySet, error, saving, step, setStep }: {
  brief: Brief; setBrief: (b: Brief) => void; custom: boolean; setCustom: (v: boolean) => void
  keySet?: boolean; error?: BackendError; saving: boolean; step: number; setStep: (n: number) => void
}) {
  const { data: voices } = useQuery<VoiceList>('tts.voices')
  const set = <K extends keyof Brief>(k: K, v: Brief[K]) => setBrief({ ...brief, [k]: v })
  const valid = !!brief.topic.trim() && !!brief.platforms.length && brief.quantity >= 1 && brief.quantity <= 20
  // Step 1 only owns the topic and quantity; platforms move to step 2, so Next must not wait on them.
  const canNext = step === 0 ? !!brief.topic.trim() && brief.quantity >= 1 && brief.quantity <= 20 : valid
  return (
    <Stepped steps={VIDEO_STEPS} step={step} setStep={setStep} canNext={canNext} canCreate={valid} error={error}
      saving={saving} keySet={keySet} createLabel="Create and generate"
      lastHint="The AI plans the batch, then writes each piece. You can cancel at any time.">
      {step === 0 && (
        <>
          <Field label="Topic" hint="Pick a theme or type your own.">
            {(id) => <Autocomplete id={id} value={brief.topic} suggestions={TOPICS} maxLength={60} autoFocus
              onChange={(v) => set('topic', v)} />}
          </Field>
          <Field label="Genre" hint="The format and voice, modelled on the top-performing motivational pages.">
            {(id) => <Select id={id} value={brief.tone} onChange={(v) => set('tone', v as Brief['tone'])} options={GENRES} />}
          </Field>
          <Quantity brief={brief} set={set} custom={custom} setCustom={setCustom} />
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
          <Choices legend="Platforms" multiple value={brief.platforms} onChange={(v) => set('platforms', v)} options={PLATFORMS} />
          {!brief.platforms.length && <p className="-mt-5 text-xs text-danger">Choose at least one platform.</p>}
          <Field label="Narration voice" hint="Google's Gemini voices, read in the delivery each piece is written for.">
            {(id) => <Select id={id} value={brief.voice} onChange={(v) => set('voice', v)} options={voiceOptions(voices)} />}
          </Field>
          <Choices legend="Video length" value={brief.target_seconds ?? -1}
            options={[{ value: -1, label: 'Auto' }, { value: 15, label: '~15s' }, { value: 30, label: '~30s' },
              { value: 45, label: '~45s' }, { value: 60, label: '~60s' }]}
            onChange={(v: number) => set('target_seconds', v === -1 ? null : v)} />
        </>
      )}

      {step === 2 && (
        <>
          <div className="grid gap-2">
            <Choices legend="Subtitles" value={brief.subtitles ? 'on' : 'off'}
              options={[{ value: 'on', label: 'On, through the whole video' }, { value: 'off', label: 'Off' }]}
              onChange={(v) => set('subtitles', v === 'on')} />
            <p className="text-xs text-ink-3">Most people watch short videos muted. Without subtitles, only the opening title shows on screen.</p>
          </div>
          {brief.subtitles && <CaptionPicker value={brief.captions} onChange={(c) => set('captions', c)} />}

          <Choices legend="Matching feed picture" value={brief.format === 'video_image' ? 'yes' : 'no'}
            options={[{ value: 'no', label: 'Video only' }, { value: 'yes', label: 'Also a 4:5 picture' }]}
            onChange={(v) => set('format', v === 'yes' ? 'video_image' : 'video')} />
          {brief.format === 'video_image' && (
            <ImageDesignPicker design={brief.image_design} font={brief.image_font} position={brief.image_position}
              onChange={(patch) => setBrief({ ...brief, ...patch })} />
          )}

          <PalettePicker value={brief.palette} onChange={(v) => set('palette', v)} />
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
    </Stepped>
  )
}

/** ClipperAi's plain downloader: the video itself, saved to Downloads, no clipping. Polls the backend's status. */
function DownloadOnly({ url }: { url: string }) {
  const [token, setToken] = useState<string>()
  const [state, setState] = useState<DownloadStatus>()
  const [error, setError] = useState<BackendError>()

  useEffect(() => { setToken(undefined); setState(undefined); setError(undefined) }, [url])  // a new link starts fresh
  useEffect(() => {
    if (!token) return
    let live = true
    const tick = async () => {
      try {
        const s = await call<DownloadStatus>('downloader.status', { token })
        if (!live) return
        setState(s)
        if (s.status === 'fetching') setTimeout(tick, 700)
      } catch (e) { if (live) setError(e as BackendError) }
    }
    tick()
    return () => { live = false }
  }, [token])

  async function start() {
    setError(undefined)
    try { setToken((await call<{ token: string }>('downloader.start', { url })).token) } catch (e) { setError(e as BackendError) }
  }

  const fetching = state?.status === 'fetching' || (!!token && !state)
  const failure = error ?? state?.error
  return (
    <div className="-mt-2 grid gap-2">
      {state?.status === 'ready' ? (
        <p className="flex items-center gap-3 text-[13px] text-ink-2">
          <span className="min-w-0 truncate">Saved to Downloads: {state.title}</span>
          <Button variant="ghost" className="shrink-0"
            onClick={() => call('downloader.reveal', { token }).catch((e) => setError(e as BackendError))}>
            <FolderOpen size={14} />Show in folder</Button>
        </p>
      ) : (
        <div className="flex items-center gap-3">
          <Button variant="ghost" className="-ml-3 w-fit" disabled={fetching} onClick={start}
            title="Save the video itself to your Downloads folder, without clipping it">
            <DownloadSimple size={14} />{fetching ? `Downloading ${state?.progress ?? 0}%` : 'Just download the video'}
          </Button>
          {fetching && (
            <div className="h-0.5 flex-1 overflow-hidden rounded-full bg-line" role="progressbar"
              aria-valuenow={state?.progress ?? 0} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full origin-left bg-pop transition-transform duration-500 ease-out-expo"
                style={{ transform: `scaleX(${Math.max((state?.progress ?? 0) / 100, 0.02)})` }} />
            </div>
          )}
        </div>
      )}
      {failure && <ErrorNote error={failure} />}
    </div>
  )
}

function ClipFormFields({ clip, setClip, keySet, error, saving }: {
  clip: ClipForm; setClip: (c: ClipForm) => void; keySet?: boolean; error?: BackendError; saving: boolean
}) {
  const [over, setOver] = useState(false)
  const floor = useQuery<{ min_clip: number }>('app.info').data?.min_clip ?? MIN_CLIP  // the backend's floor wins
  const choose = async () => { const path = await studio.pickVideo(); if (path) setClip({ ...clip, source: path }) }
  return (
    <>
      <Field label="Video" hint="Paste a YouTube or other link, or use a video already on this computer: choose it, or drop it here.">
        {(id) => (
          <div className={cx('flex gap-2 rounded-field transition-shadow duration-150', over && 'shadow-[0_0_0_2px_var(--color-accent)]')}
            onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setOver(true) } }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              const f = e.dataTransfer.files[0]; setOver(false)
              if (f) { e.preventDefault(); const path = studio.pathForFile(f); if (path) setClip({ ...clip, source: path }) }
            }}>
            <Input id={id} value={clip.source} spellCheck={false} autoFocus
              placeholder="https://… or choose a video file" onChange={(e) => setClip({ ...clip, source: e.target.value })} />
            <Button type="button" className="shrink-0" onClick={choose}><UploadSimple size={14} />Choose a file</Button>
          </div>
        )}
      </Field>
      {/^https?:\/\//.test(clip.source.trim()) && <DownloadOnly url={clip.source.trim()} />}

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
      {clip.burn_captions && <CaptionPicker value={clip.captions} onChange={(c) => setClip({ ...clip, captions: c })} />}

      <Choices legend="Frame rate" value={clip.fps}
        options={[{ value: 30, label: '30 fps' }, { value: 60, label: '60 fps' }]}
        onChange={(v: number) => setClip({ ...clip, fps: v })} />

      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink">
          <CaretRight size={12} weight="bold" className="transition-transform duration-150 group-open:rotate-90" />
          Advanced
        </summary>
        <div className="grid grid-cols-2 gap-4 pt-5">
          <Field label="Shortest (s)" hint={`Every clip runs at least ${floor} seconds.`}>
            {(id) => <Input id={id} type="number" min={floor} max={600} className="tnum" value={clip.min_len}
              onChange={(e) => setClip({ ...clip, min_len: Number(e.target.value) })}
              onBlur={() => setClip({ ...clip, min_len: Math.max(floor, Math.min(600, clip.min_len || floor)),
                max_len: Math.max(clip.max_len, Math.max(floor, clip.min_len || floor) + 15) })} />}
          </Field>
          <Field label="Longest (s)" hint="Aim for clips at most this long.">
            {(id) => <Input id={id} type="number" min={floor + 15} max={900} className="tnum" value={clip.max_len}
              onChange={(e) => setClip({ ...clip, max_len: Number(e.target.value) })}
              onBlur={() => setClip({ ...clip, max_len: Math.max(clip.min_len + 15, Math.min(900, clip.max_len || 90)) })} />}
          </Field>
        </div>
      </details>

      {error && <ErrorNote error={error} />}

      <div className="grid gap-3 border-t border-line pt-6">
        <div><Button variant="primary" type="submit" disabled={clip.source.trim().length < 2 || saving} kbd="Ctrl Enter">
          <Scissors size={14} />{saving ? 'Starting' : 'Clip this video'}</Button></div>
        <p className="text-xs text-ink-3">
          {keySet
            ? 'The video is transcribed, then the AI picks the moments. You can cancel at any time.'
            : 'Add your OpenRouter API key in Settings to clip.'}
        </p>
      </div>
    </>
  )
}

/** The batch's first images exactly as they will be designed: the user's own quotes in the chosen design (Auto
 *  resolved per piece like the render does), drawn by the real renderer. Only the photo will differ. */
function QuotePreview({ brief, quotes }: { brief: Brief; quotes: string[] }) {
  const params = { design_name: brief.image_design, genre: brief.tone, font: brief.image_font,
    position: brief.image_position, quotes: quotes.slice(0, 3), swatches: false }
  const [data, setData] = useState<{ samples: Sample[]; own: boolean; photo: boolean; key: string }>()
  const key = JSON.stringify(params)
  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      call<{ samples: Sample[]; own: boolean; photo: boolean }>('design.previews', params).then((d) => live && setData({ ...d, key }), () => {})
    }, 300)
    return () => { live = false; clearTimeout(t) }
  }, [key])
  const n = quotes.length || brief.quantity
  const stale = !!data && data.key !== key  // a choice changed: the old images dim until the new ones arrive
  const [first, ...rest] = data?.samples ?? []
  const slots = Math.min(Math.max(n - 1, 0), 2)  // never promise an image the batch won't have
  return (
    <section aria-label="Preview" className="glass relative isolate sticky top-0 grid gap-6 self-start overflow-hidden p-8">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-display text-lg font-semibold tracking-[-0.02em]">Preview</h2>
        <p className="tnum text-xs text-ink-3">{n} {n === 1 ? 'image' : 'images'}</p>
      </div>
      <div aria-busy={stale || !data} className={cx('grid items-start gap-4 transition-opacity duration-300',
        slots ? 'grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]' : 'grid-cols-[minmax(0,1fr)] max-w-[420px]', stale && 'opacity-50')}>
        <Print sample={first} index={1} />
        {slots > 0 && <div className="grid gap-4">{Array.from({ length: slots }, (_, i) => <Print key={i} sample={rest[i]} index={i + 2} />)}</div>}
      </div>
      <div className="grid gap-3 border-t border-line pt-5">
        <p className="text-[13px] text-ink-2">
          {data?.own ? 'Your quotes, set exactly as they will render.' : 'Sample lines in your design; the AI writes the real ones.'}
          {' '}{data?.photo ? 'The photo here is from your Library; each' : 'Shown without a photo until your Library has one; each'}
          {' '}image gets its own photo, which you confirm before rendering.
        </p>
        <ul className="grid gap-2 text-[13px] text-ink-2">
          {['A designed 1080 × 1350 image per quote', 'Caption, hashtags and alt text per platform', 'Render, then export for scheduling'].map((g) => (
            <li key={g} className="flex items-center gap-2.5"><Check size={13} weight="bold" className="shrink-0 text-accent-ink" />{g}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function Print({ sample, index }: { sample?: Sample; index: number }) {
  return (
    <figure className="grid gap-2">
      <div className={cx('aspect-[4/5] overflow-hidden rounded-[12px] bg-black/[0.04] shadow-[0_18px_40px_-18px_rgb(17_18_20/0.22),inset_0_0_0_1px_rgb(17_18_20/0.1)]',
        !sample && 'animate-pulse')}>
        {sample && <img key={sample.src.slice(-32)} src={sample.src} alt="" className="anim-fade h-full w-full object-cover" />}
      </div>
      <figcaption className="tnum text-2xs text-ink-3">{String(index).padStart(3, '0')}{sample ? ` · ${sample.label}` : ''}</figcaption>
    </figure>
  )
}

/** What clipping produces: one 9:16 frame per clip and the pipeline in words. */
function ClipPreviewPanel({ form, ready }: { form: ClipForm; ready: boolean }) {
  const [w, h] = form.orientation === '16:9' ? [16, 9] : form.orientation === '1:1' ? [1, 1] : [9, 16]
  return (
    <section aria-label="Clip preview" className="glass relative isolate sticky top-0 self-start overflow-hidden p-7">
      <div className="flex items-baseline justify-between gap-4 pb-6">
        <h2 className="font-display text-lg font-semibold tracking-[-0.02em]">Clip from video</h2>
        <p className="tnum text-xs text-ink-3">{form.n ? `${form.n} clips` : 'auto count'}</p>
      </div>
      <div className="flex items-end gap-3">
        <div className="rounded-[10px] bg-white shadow-[inset_0_0_0_1px_rgb(17_18_20/0.1)]"
          style={{ width: form.orientation === '16:9' ? 216 : form.orientation === '1:1' ? 122 : 69, aspectRatio: `${w} / ${h}` }} />
        <div className="grid gap-1.5 pb-1">
          {[1, 2, 3].map((i) => (
            <div key={i} className={cx('rounded-[8px] bg-black/[0.05] shadow-[inset_0_0_0_1px_rgb(17_18_20/0.08)]', i === 1 ? 'h-5 w-40' : 'h-3 w-32')} />
          ))}
        </div>
      </div>
      <ol className="grid gap-2.5 pt-6 text-[13px] text-ink-2">
        <li>1. The video downloads (or a local file is used as-is).</li>
        <li>2. Whisper transcribes every word with timestamps.</li>
        <li>3. The AI finds the {form.min_len}-{form.max_len}s moments that stand alone and writes per-platform post copy.</li>
        <li>4. Each clip is cropped to the speaker, captioned{form.burn_captions ? ', captions burned in,' : ''} and rendered as {form.orientation} MP4.</li>
      </ol>
      <p className="pt-5 text-xs text-ink-3">
        {ready ? 'Every clip keeps its caption file, cover frame and post copy for review here.'
          : 'Needs an OpenRouter key in Settings before clipping can start.'}
      </p>
    </section>
  )
}

// How each genre sounds, in a line (the full voice spec lives in the backend's creative/prompts.py GENRES).
const GENRE_FEEL: Record<string, string> = {
  hope: 'Gentle, unhurried spoken word that ends on earned hope.',
  speech: 'Short, hard sentences that escalate and call you to hold the line.',
  stoic: 'Calm journal voice: control, mortality, duty over feeling.',
  history: 'Real documented words from public-domain figures, set in their moment.',
  books: 'Documented lines from public-domain classics, bridged into today.',
  cinema: 'Very few words, each one an image. The visuals carry it.',
}

/** What the batch will produce: one lit frame per output at its real aspect ratio, and what each piece contains. */
function BatchPreview({ brief }: { brief: Brief }) {
  const frames = Array.from({ length: brief.quantity }, (_, i) => i)
  const kinds = brief.format === 'video_image' ? ['video', 'image'] : ['video']
  const spec = brief.format === 'video_image' ? 'A 9:16 video and a 4:5 image per piece' : '1080 × 1920 video, 9:16'
  const topic = brief.topic.trim()
  const genre = GENRES.find((g) => g.value === brief.tone)?.label.split(' — ')[0] ?? label(brief.tone)
  const gets = ['A quote and spoken narration', 'Footage cut to the voice, graded and captioned', 'Title, caption and hashtags per platform']

  return (
    <section aria-label="Batch preview" className="glass relative isolate sticky top-0 grid gap-7 self-start overflow-hidden p-8">
      <div className="grid gap-2">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className={cx('font-display text-[28px] leading-tight font-semibold tracking-[-0.03em] text-balance', !topic && 'text-ink-3')}>
            {topic || 'Your topic'}
          </h2>
          <p className="tnum shrink-0 text-xs text-ink-3">{brief.quantity} {brief.quantity === 1 ? 'piece' : 'pieces'}</p>
        </div>
        <p className="text-[13px] text-ink-2"><span className="font-medium text-accent-ink">{genre}.</span> {GENRE_FEEL[brief.tone]}</p>
      </div>

      <div className="grid max-h-[calc(100dvh-460px)] min-h-[150px] grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-3 overflow-y-auto">
        {frames.map((i) => (
          <div key={`${brief.format}-${i}`} className="anim-slot grid gap-1.5" style={{ '--i': i } as React.CSSProperties}>
            <div className={cx('grid gap-1.5', kinds.length === 2 && 'grid-cols-[9fr_7.2fr] items-end')}>
              {kinds.map((k) => (
                <div key={k} className={cx('relative overflow-hidden rounded-[12px] bg-ink',
                  'shadow-[0_12px_28px_-14px_rgb(17_18_20/0.22),inset_0_0_0_1px_rgb(17_18_20/0.1)]', k === 'video' ? 'aspect-[9/16]' : 'aspect-[4/5]')}>
                  {k === 'video' && topic && (
                    <span className="absolute inset-x-2 bottom-2 line-clamp-2 font-display text-[10px] leading-tight font-semibold text-white/80">{topic}</span>
                  )}
                </div>
              ))}
            </div>
            <span className="tnum text-2xs text-ink-3">{String(i + 1).padStart(3, '0')}</span>
          </div>
        ))}
      </div>

      <div className="grid gap-4 border-t border-line pt-6">
        <ul className="grid gap-2 text-[13px] text-ink-2">
          {gets.map((g) => (
            <li key={g} className="flex items-center gap-2.5"><Check size={13} weight="bold" className="shrink-0 text-accent-ink" />{g}</li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-1.5">
          {brief.platforms.map((pl) => (
            <span key={pl} className="rounded-full bg-black/[0.06] px-3 py-1 text-2xs text-ink-2 shadow-[inset_0_0_0_1px_rgb(17_18_20/0.08)]">
              {PLATFORMS.find((x) => x.value === pl)!.label}
            </span>
          ))}
          {!brief.platforms.length && <span className="text-xs text-danger">No platform picked yet</span>}
        </div>
        <p className="text-xs text-ink-3">{spec}.</p>
      </div>
    </section>
  )
}
