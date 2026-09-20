import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Check, FolderOpen, Plug, PlugsConnected } from '@phosphor-icons/react'
import { call, studio, GENRES, useQuery, BackendError, type SecretName, type Settings as S } from '../lib/studio'
import { Button, ErrorNote, Field, Input, PageHeader, Select } from '../components/ui'

const KEYS: { name: SecretName; label: string }[] = [
  { name: 'DEEPSEEK_API_KEY', label: 'DeepSeek API key' },
  { name: 'PEXELS_API_KEY', label: 'Pexels API key' },
  { name: 'UNSPLASH_ACCESS_KEY', label: 'Unsplash access key' },
  { name: 'GROQ_API_KEY', label: 'Groq API key' },
  { name: 'METRICOOL_API_KEY', label: 'Metricool API key' },
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

type BufferConnection = { connected: boolean }

function Publishing({ form, set }: { form: S; set: <K extends keyof S>(k: K, v: S[K]) => void }) {
  const { data: buffer, reload: reloadBuffer } = useQuery<BufferConnection>('publish.buffer_connection')
  const { data: host } = useQuery<{ configured: boolean; keys_set: boolean }>('publish.host_status')
  const [connecting, setConnecting] = useState(false)
  const [hostKeys, setHostKeys] = useState({ access_key_id: '', secret_access_key: '' })
  const [metricool, setMetricool] = useState<string>()
  const [error, setError] = useState<BackendError>()
  const poll = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearInterval(poll.current), [])

  async function connect() {
    setError(undefined)
    try {
      const url = await call<string>('publish.buffer_connect_url')
      studio.openExternal(url)
      setConnecting(true)
      window.clearInterval(poll.current)
      poll.current = window.setInterval(async () => {
        const c = await call<BufferConnection>('publish.buffer_connection').catch(() => null)
        if (c?.connected) { window.clearInterval(poll.current); setConnecting(false); reloadBuffer() }
      }, 2000)
      window.setTimeout(() => { setConnecting(false); window.clearInterval(poll.current) }, 300_000)
    } catch (e) { setError(e as BackendError) }
  }

  async function disconnect() {
    setError(undefined)
    try { await call('publish.buffer_disconnect'); reloadBuffer() } catch (e) { setError(e as BackendError) }
  }

  async function saveHost() {
    setError(undefined)
    try { await call('publish.host_save', { endpoint: form.publish_host_endpoint, bucket: form.publish_host_bucket,
      public_url: form.publish_host_public_url, region: form.publish_host_region, ...hostKeys })
      setHostKeys({ access_key_id: '', secret_access_key: '' })
    } catch (e) { setError(e as BackendError) }
  }

  async function checkMetricool() {
    setError(undefined); setMetricool(undefined)
    try {
      const r = await call<{ connected: boolean; tools: string[] }>('publish.metricool_status')
      setMetricool(`Connected · ${r.tools.length} tools available`)
    } catch (e) { setMetricool(`Not connected: ${(e as BackendError).message}`) }
  }

  return (
    <div className="grid gap-6">
      {error && <ErrorNote error={error} />}

      <div className="grid gap-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-medium text-ink">Buffer</p>
            <p className="mt-0.5 text-xs text-ink-3">{buffer?.connected
              ? 'Connected — approved clips can be published to your channels.'
              : 'Register a public OAuth app at developers.buffer.com, add http://127.0.0.1:8787/callback as a redirect URL, paste its client id here, then connect.'}</p>
          </div>
          {buffer?.connected
            ? <Button variant="ghost" onClick={disconnect}>Disconnect</Button>
            : <Button disabled={connecting} onClick={connect}>
                <Plug size={14} />{connecting ? 'Waiting for Buffer…' : 'Connect Buffer'}</Button>}
        </div>
        <Field label="Buffer client id" hint="From your OAuth app at developers.buffer.com. Saved with the changes button above.">
          {(id) => <Input id={id} value={form.buffer_client_id} spellCheck={false}
            onChange={(e) => set('buffer_client_id', e.target.value)} />}
        </Field>
      </div>

      <div className="grid gap-4 border-t border-line pt-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-medium text-ink">Media host</p>
            <p className="mt-0.5 text-xs text-ink-3">Buffer fetches videos from a public link, so published clips are
              copied to your own S3-compatible bucket (Cloudflare R2 works). {host?.configured ? 'Configured.' : 'Not configured yet.'}</p>
          </div>
          <Button disabled={!form.publish_host_endpoint} onClick={saveHost}>Save host</Button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Endpoint" hint="e.g. https://<account>.r2.cloudflarestorage.com">
            {(id) => <Input id={id} value={form.publish_host_endpoint} spellCheck={false}
              onChange={(e) => set('publish_host_endpoint', e.target.value)} />}
          </Field>
          <Field label="Bucket">
            {(id) => <Input id={id} value={form.publish_host_bucket} spellCheck={false}
              onChange={(e) => set('publish_host_bucket', e.target.value)} />}
          </Field>
          <Field label="Public URL" hint="Where the bucket is reachable, e.g. a custom domain.">
            {(id) => <Input id={id} value={form.publish_host_public_url} spellCheck={false}
              onChange={(e) => set('publish_host_public_url', e.target.value)} />}
          </Field>
          <Field label="Region" hint="auto for Cloudflare R2.">
            {(id) => <Input id={id} value={form.publish_host_region} spellCheck={false}
              onChange={(e) => set('publish_host_region', e.target.value)} />}
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Access key id" hint={host?.keys_set ? <span className="inline-flex items-center gap-1 text-ok"><Check size={12} weight="bold" />Keys saved</span> : 'From your host.'}>
            {(id) => <Input id={id} type="password" autoComplete="off" value={hostKeys.access_key_id}
              onChange={(e) => setHostKeys({ ...hostKeys, access_key_id: e.target.value })} />}
          </Field>
          <Field label="Secret access key">
            {(id) => <Input id={id} type="password" autoComplete="off" value={hostKeys.secret_access_key}
              onChange={(e) => setHostKeys({ ...hostKeys, secret_access_key: e.target.value })} />}
          </Field>
        </div>
      </div>

      <div className="grid gap-4 border-t border-line pt-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-medium text-ink">Metricool</p>
            <p className="mt-0.5 text-xs text-ink-3">Uses the Metricool API key above. Posts a clip's copy through
              Metricool's own scheduler.</p>
          </div>
          <Button onClick={checkMetricool}><PlugsConnected size={14} />Check connection</Button>
        </div>
        {metricool && <p className="text-xs text-ink-2">{metricool}</p>}
      </div>
    </div>
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
        <div className="grid grid-cols-3 gap-4">
          <Field label="Genre">
            {(id) => (
              <Select id={id} value={form.default_tone} onChange={(v) => set('default_tone', v as S['default_tone'])}
                options={GENRES} />
            )}
          </Field>
          <Field label="Quantity" hint="1 to 20 pieces.">
            {(id) => <Input id={id} type="number" min={1} max={20} className="tnum" value={form.default_quantity}
              onChange={(e) => set('default_quantity', Number(e.target.value))} />}
          </Field>
          <Field label="Asset cooldown" hint="Days before a visually similar asset can be used again.">
            {(id) => <Input id={id} type="number" min={0} max={365} className="tnum" value={form.asset_cooldown_days}
              onChange={(e) => set('asset_cooldown_days', Number(e.target.value))} />}
          </Field>
        </div>
      </Section>

      <Section title="Narration" description="The voice that reads each piece aloud in rendered videos.">
        <Field label="Voice engine" hint="Kokoro is a local neural voice (default; download it once with python -m app.tts download). Windows voices are always available.">
          {(id) => (
            <Select id={id} value={form.tts_provider} onChange={(v) => set('tts_provider', v as S['tts_provider'])}
              options={[{ value: 'kokoro', label: 'Kokoro (local neural)' }, { value: 'windows', label: 'Windows voices (offline)' }]} />
          )}
        </Field>
        <Field label="Voice name" hint="Leave empty for the default voice.">
          {(id) => <Input id={id} value={form.tts_voice} placeholder="e.g. Microsoft Zira Desktop" spellCheck={false}
            onChange={(e) => set('tts_voice', e.target.value)} />}
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Speed" hint="0.5 to 2. 1 is normal speech.">
            {(id) => <Input id={id} type="number" step={0.1} min={0.5} max={2} className="tnum" value={form.tts_speed}
              onChange={(e) => set('tts_speed', Number(e.target.value))} />}
          </Field>
          <Field label="Volume" hint="0 to 1.">
            {(id) => <Input id={id} type="number" step={0.05} min={0} max={1} className="tnum" value={form.tts_volume}
              onChange={(e) => set('tts_volume', Number(e.target.value))} />}
          </Field>
        </div>
      </Section>

      <Section title="Render" description="How videos and images are rendered when you press Render on a project.">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Quality" hint="14 to 32. Lower is sharper and larger files.">
            {(id) => <Input id={id} type="number" step={1} min={14} max={32} className="tnum" value={form.render_crf}
              onChange={(e) => set('render_crf', Number(e.target.value))} />}
          </Field>
          <Field label="Music volume" hint="0 to 0.5, mixed under the narration.">
            {(id) => <Input id={id} type="number" step={0.05} min={0} max={0.5} className="tnum" value={form.music_volume}
              onChange={(e) => set('music_volume', Number(e.target.value))} />}
          </Field>
        </div>
        <Field label="Music file" hint="Optional background track, fades in and out under the narration.">
          {(id) => <Input id={id} value={form.music_path} placeholder="Path to an mp3 or wav on this computer" spellCheck={false}
            onChange={(e) => set('music_path', e.target.value)} />}
        </Field>
      </Section>

      <Section title="Publishing" description="Send approved clips to Buffer or Metricool. Everything stays local until you publish.">
        <Publishing form={form} set={set} />
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
