import { useEffect, useState, type ReactNode } from 'react'
import { CaretRight, Check, FolderOpen, Trash } from '@phosphor-icons/react'
import { call, studio, useQuery, BackendError, type SecretName, type Settings as S } from '../lib/studio'
import { Button, ErrorNote, Field, Input, PageHeader, Select } from '../components/ui'
import { ZernioSetup } from '../components/Posting'

const KEYS: { name: SecretName; label: string }[] = [
  { name: 'OPENROUTER_API_KEY', label: 'OpenRouter API key' },
  { name: 'PEXELS_API_KEY', label: 'Pexels API key' },
  { name: 'UNSPLASH_ACCESS_KEY', label: 'Unsplash access key (optional)' },
]

// OpenRouter model ids (checked against openrouter.ai/api/v1/models 2026-11-07), labelled by cost, not by claims.
const WRITERS = [
  { value: 'deepseek/deepseek-v4-pro', label: 'DeepSeek V4 Pro · best value (recommended)' },
  { value: 'anthropic/claude-sonnet-5.5', label: 'Claude Sonnet 5.5 · premium' },
  { value: 'openai/gpt-6.1-sol', label: 'GPT-6.1 Sol · premium' },
  { value: 'google/gemini-3.8-flash', label: 'Gemini 3.8 Flash · mid-price' },
  { value: 'anthropic/claude-haiku-5.5', label: 'Claude Haiku 5.5 · budget' },
  { value: 'deepseek/deepseek-v4.1-flash', label: 'DeepSeek V4.1 Flash · cheapest' },
]
const SCANNERS = [
  { value: 'deepseek/deepseek-v4.1-flash', label: 'DeepSeek V4.1 Flash · cheapest (recommended)' },
  { value: 'anthropic/claude-haiku-5.5', label: 'Claude Haiku 5.5 · budget' },
  { value: 'google/gemini-3.8-flash', label: 'Gemini 3.8 Flash · mid-price' },
]
const QUALITY = [
  { value: '22', label: 'Standard · smaller files' },
  { value: '18', label: 'High (recommended)' },
  { value: '16', label: 'Maximum · largest files' },
]
/** A saved value outside the list (an older custom model or quality) still shows instead of a blank select. */
const withCurrent = (options: { value: string; label: string }[], current: string) =>
  options.some((o) => o.value === current) ? options : [...options, { value: current, label: `${current} (current)` }]

function formatBytes(n: number) {
  return n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${Math.round(n / 1e6)} MB` : `${Math.round(n / 1e3)} KB`
}

/** Space used by created content, and one button to wipe it. Keys and settings stay. */
function StorageSection({ dataDir }: { dataDir?: string }) {
  const { data: usage, reload } = useQuery<{ bytes: number; projects: number }>('storage.usage')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string>()
  const [error, setError] = useState<BackendError>()

  async function clear() {
    if (!confirm('Delete all projects, videos, clips, exports and downloaded footage? Your keys and settings stay. ' +
      "This can't be undone.")) return
    setBusy(true)
    setError(undefined)
    try {
      const { freed } = await call<{ freed: number }>('storage.clear')
      setResult(`Cleared. ${formatBytes(freed)} freed.`)
      reload()
    } catch (e) {
      setError(e as BackendError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Storage" description="Everything the studio creates is kept on this computer.">
      {error && <ErrorNote error={error} />}
      <Field label="Space used" hint={usage ? `${usage.projects} project${usage.projects === 1 ? '' : 's'}` : ' '}>
        {(id) => (
          <div className="flex items-center gap-2">
            <Input id={id} readOnly value={usage ? formatBytes(usage.bytes) : '…'} className="tnum text-ink-2" />
            <Button onClick={() => studio.openDataDir()} title={dataDir}><FolderOpen size={14} />Open folder</Button>
          </div>
        )}
      </Field>
      <div className="flex items-center gap-3">
        <Button onClick={clear} disabled={busy || !usage?.bytes && !usage?.projects}
          className="hover:!bg-[#c42b1c] hover:!text-white"><Trash size={14} />{busy ? 'Clearing…' : 'Clear all content'}</Button>
        {result && <span className="text-xs text-ok">{result}</span>}
      </div>
    </Section>
  )
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="glass mb-5 grid grid-cols-[240px_minmax(0,480px)] gap-10 p-8">
      <div>
        <h2 className="font-display text-[15px] font-semibold tracking-[-0.01em]">{title}</h2>
        <p className="mt-1 text-xs text-ink-3">{description}</p>
      </div>
      <div className="grid gap-5">{children}</div>
    </section>
  )
}

function SecretField({ name, text, isSet, onSaved }: { name: SecretName; text: string; isSet: boolean; onSaved: (s: Record<SecretName, boolean>) => void }) {
  const [value, setValue] = useState('')
  const save = async (v: string) => { onSaved(await studio.setSecret(name, v)); setValue('') }
  return (
    <Field label={text} hint={isSet ? <span className="inline-flex items-center gap-1 text-ok"><Check size={12} weight="bold" />Saved and encrypted on this computer</span> : 'Not set'}>
      {(id) => (
        <div className="flex gap-2">
          <Input id={id} type="password" autoComplete="off" spellCheck={false} value={value}
            placeholder={isSet ? 'Enter a new key to replace it' : 'Paste key'} onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && value.trim() && save(value)} />
          <Button disabled={!value.trim()} onClick={() => save(value)}>Save</Button>
          {isSet && <Button variant="ghost" onClick={() => save('')}>Remove</Button>}
        </div>
      )}
    </Field>
  )
}

export function Settings() {
  const { data, error: loadError, reload } = useQuery<S>('settings.get')
  const info = useQuery<{ data_dir: string }>('app.info').data
  const [form, setForm] = useState<S>()
  const [secrets, setSecrets] = useState<Record<SecretName, boolean>>()
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<BackendError>()

  useEffect(() => { if (data) setForm(data) }, [data])
  useEffect(() => { studio.secretsStatus().then(setSecrets) }, [])

  if (loadError) return <><PageHeader title="Settings" /><ErrorNote error={loadError} action={<Button onClick={reload}>Try again</Button>} /></>
  if (!form) return <PageHeader title="Settings" />

  const set = <K extends keyof S>(k: K, v: S[K]) => { setForm({ ...form, [k]: v }); setSaved(false) }
  const dirty = JSON.stringify(form) !== JSON.stringify(data)

  async function save() {
    setError(undefined)
    try {
      setForm(await call<S>('settings.update', form))
      setSaved(true)
      reload()
    } catch (e) {
      setError(e as BackendError)
    }
  }

  return (
    <>
      <PageHeader title="Settings">
        {saved && !dirty && <span className="text-xs text-ink-3">Saved</span>}
        <Button variant="primary" disabled={!dirty} onClick={save}>Save changes</Button>
      </PageHeader>
      {error && <div className="mb-6"><ErrorNote error={error} /></div>}

      <Section title="API keys" description="Paste each key once. Stored encrypted on this computer, saved straight away.">
        {secrets && KEYS.map((k) => <SecretField key={k.name} name={k.name} text={k.label} isSet={secrets[k.name]} onSaved={setSecrets} />)}
      </Section>

      <Section title="Posting" description="Schedule finished clips to your social accounts. Everything stays on this computer until you post.">
        <ZernioSetup />
      </Section>

      <Section title="AI" description="Which AI writes your content. Billed to your OpenRouter account.">
        <Field label="Writing model" hint="Writes the scripts, hooks, captions and clip picks.">
          {(id) => <Select id={id} value={form.ai_model} onChange={(v) => set('ai_model', v)}
            options={withCurrent(WRITERS, form.ai_model)} />}
        </Field>
        <Field label="Clip finder model" hint="Reads a whole video's transcript to spot the best moments.">
          {(id) => <Select id={id} value={form.ai_model_fast} onChange={(v) => set('ai_model_fast', v)}
            options={withCurrent(SCANNERS, form.ai_model_fast)} />}
        </Field>
      </Section>

      <Section title="Video" description="How finished videos look.">
        <Field label="Quality" hint="Higher looks sharper after upload and makes bigger files.">
          {(id) => <Select id={id} value={String(form.render_crf)} onChange={(v) => set('render_crf', Number(v))}
            options={withCurrent(QUALITY, String(form.render_crf))} />}
        </Field>
        <Field label="Animated titles" hint="Moving hook titles and callouts on each video. Adds about a minute per video.">
          {(id) => (
            <Select id={id} value={form.motion_graphics ? 'on' : 'off'} onChange={(v) => set('motion_graphics', v === 'on')}
              options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />
          )}
        </Field>
        <Field label="Background music" hint="Optional. A music file on this computer, played quietly under the voice.">
          {(id) => <Input id={id} value={form.music_path} placeholder="Path to an mp3 or wav" spellCheck={false}
            onChange={(e) => set('music_path', e.target.value)} />}
        </Field>
      </Section>

      <StorageSection dataDir={info?.data_dir} />

      <details className="group mb-5">
        <summary className="mb-5 flex cursor-pointer list-none items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink">
          <CaretRight size={12} weight="bold" className="transition-transform duration-150 group-open:rotate-90" />
          Advanced: video downloads
        </summary>
        <Section title="Video downloads" description="Only needed if YouTube blocks a download.">
          <Field label="YouTube cookies" hint="A browser you're signed in to YouTube with (Firefox works best), or the path to a cookies.txt file.">
            {(id) => <Input id={id} value={form.ytdlp_cookies} placeholder="e.g. firefox" spellCheck={false}
              onChange={(e) => set('ytdlp_cookies', e.target.value)} />}
          </Field>
        </Section>
      </details>
    </>
  )
}
