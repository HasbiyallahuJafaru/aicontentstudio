import { useEffect, useState, type ReactNode } from 'react'
import { Check, FolderOpen } from '@phosphor-icons/react'
import { call, label, studio, TONES, useQuery, BackendError, type SecretName, type Settings as S } from '../lib/studio'
import { Button, ErrorNote, Field, Input, PageHeader } from '../components/ui'

const KEYS: { name: SecretName; label: string }[] = [
  { name: 'DEEPSEEK_API_KEY', label: 'DeepSeek API key' },
  { name: 'PEXELS_API_KEY', label: 'Pexels API key' },
  { name: 'UNSPLASH_ACCESS_KEY', label: 'Unsplash access key' },
]

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

      <Section title="API keys" description="Stored encrypted by Windows and never shown again. Saved immediately.">
        {secrets && KEYS.map((k) => <SecretField key={k.name} name={k.name} text={k.label} isSet={secrets[k.name]} onSaved={setSecrets} />)}
      </Section>

      <Section title="AI" description="Used by DeepSeek when it writes each piece.">
        <Field label="Model">{(id) => <Input id={id} value={form.ai_model} onChange={(e) => set('ai_model', e.target.value)} />}</Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Temperature" hint="0 to 2. Higher is more varied.">
            {(id) => <Input id={id} type="number" step={0.1} min={0} max={2} className="tnum" value={form.ai_temperature}
              onChange={(e) => set('ai_temperature', Number(e.target.value))} />}
          </Field>
          <Field label="Max tokens" hint="256 to 8192.">
            {(id) => <Input id={id} type="number" step={256} min={256} max={8192} className="tnum" value={form.ai_max_tokens}
              onChange={(e) => set('ai_max_tokens', Number(e.target.value))} />}
          </Field>
        </div>
      </Section>

      <Section title="Content defaults" description="Pre-filled every time you start a new project.">
        <Field label="Topic">{(id) => <Input id={id} value={form.default_topic} onChange={(e) => set('default_topic', e.target.value)} />}</Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Tone">
            {(id) => (
              <select id={id} value={form.default_tone} onChange={(e) => set('default_tone', e.target.value as S['default_tone'])}
                className="h-10 rounded-field border border-line bg-black/20 px-3 text-[13px] text-ink hover:border-line-strong focus:border-accent/70 focus:outline-none">
                {TONES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
              </select>
            )}
          </Field>
          <Field label="Quantity" hint="1 to 20 pieces.">
            {(id) => <Input id={id} type="number" min={1} max={20} className="tnum" value={form.default_quantity}
              onChange={(e) => set('default_quantity', Number(e.target.value))} />}
          </Field>
        </div>
      </Section>

      <Section title="Storage" description="Projects, downloaded assets, renders and exports live here.">
        <Field label="Media folder">
          {(id) => (
            <div className="flex gap-2">
              <Input id={id} readOnly value={info?.data_dir ?? ''} className="text-ink-2" />
              <Button onClick={() => studio.openDataDir()}><FolderOpen size={14} />Open</Button>
            </div>
          )}
        </Field>
      </Section>
    </>
  )
}
