import { useEffect, useState, type ReactNode } from 'react'
import { ArrowSquareOut, Check } from '@phosphor-icons/react'
import { studio, BackendError, type SecretName } from '../lib/studio'
import { Button, ErrorNote, Field, Input, Reveal, cx } from '../components/ui'
import { ZernioSetup, useZernio } from '../components/Posting'

/** First run: one screen per key, then posting through Zernio, then a summary. Shown after the splash whenever a key the
 *  studio needs is missing; every screen can be skipped and everything stays editable in Settings. */
const KEYS: { name: SecretName; title: string; why: string; where: string; url: string; optional?: boolean }[] = [
  { name: 'OPENROUTER_API_KEY', title: 'Connect the AI', url: 'https://openrouter.ai/keys',
    why: 'An OpenRouter key writes your quotes, scripts and captions, finds the best moments in long videos and voices the narration. You pay OpenRouter directly for what you use.',
    where: 'Sign in at openrouter.ai, open Keys, create a key and paste it here.' },
  { name: 'PEXELS_API_KEY', title: 'Add stock footage', url: 'https://www.pexels.com/api/',
    why: 'A free Pexels key finds the video footage and photos behind every piece.',
    where: 'Sign in at pexels.com, open Image & Video API, and copy your key.' },
  { name: 'UNSPLASH_ACCESS_KEY', title: 'More photos', url: 'https://unsplash.com/oauth/applications', optional: true,
    why: 'Optional. An Unsplash access key adds a second photo library to choose from.',
    where: 'Create an app at unsplash.com/oauth/applications and copy its Access Key. The Secret Key and Application ID are only for signing in Unsplash users, which the studio never does.' },
]
const STEPS = KEYS.length + 2  // the keys, posting, the summary

const LABEL: Record<SecretName, string> = {
  OPENROUTER_API_KEY: 'OpenRouter', PEXELS_API_KEY: 'Pexels', UNSPLASH_ACCESS_KEY: 'Unsplash',
}

export function Setup({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0)
  const [saved, setSaved] = useState<Record<SecretName, boolean>>()
  const [value, setValue] = useState('')
  const [error, setError] = useState<BackendError>()
  const zernio = useZernio()

  useEffect(() => { studio.secretsStatus().then(setSaved) }, [])

  const next = () => { setValue(''); setError(undefined); setStep((s) => s + 1) }
  const key = KEYS[step]

  async function saveAndNext() {
    if (key && value.trim()) setSaved(await studio.setSecret(key.name, value.trim()))
    next()
  }

  let body
  if (key) {
    const isSet = saved?.[key.name]
    body = <>
      <Heading title={key.title} text={key.why} />
      <Field label={`${LABEL[key.name]} key`} hint={isSet
        ? <span className="inline-flex items-center gap-1 text-ok"><Check size={12} weight="bold" />Saved and encrypted on this computer</span>
        : key.where}>
        {(id) => <Input id={id} type="password" autoComplete="off" spellCheck={false} autoFocus value={value}
          placeholder={isSet ? 'Paste a new key to replace it' : 'Paste key'} onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && value.trim() && saveAndNext()} />}
      </Field>
      <Footer>
        <Button variant="ghost" onClick={() => studio.openExternal(key.url)}><ArrowSquareOut size={14} />Get a key</Button>
        <div className="flex gap-2">
          {!value.trim() && <Button variant="ghost" onClick={next}>{isSet ? 'Keep this key' : 'Skip for now'}</Button>}
          <Button variant="primary" disabled={!value.trim()} onClick={saveAndNext}>Save and continue</Button>
        </div>
      </Footer>
    </>
  } else if (step === KEYS.length) {
    body = <>
      <Heading title="Post to your socials" text="Optional. Zernio posts your clips to TikTok, YouTube, Instagram and more at the time you pick, even when this computer is off. You can also do this later in Settings." />
      <ZernioSetup intro={false} onChange={zernio.reload} />
      <Footer>
        <span />
        <Button variant={zernio.connected ? 'primary' : 'ghost'} onClick={next}>
          {zernio.connected ? 'Continue' : 'Skip for now'}</Button>
      </Footer>
    </>
  } else {
    const missing = KEYS.filter((k) => !k.optional && !saved?.[k.name])
    body = <>
      <Heading title={missing.length ? 'Almost there' : "You're set up"} text={missing.length
        ? `Writing and footage need the ${missing.map((k) => LABEL[k.name]).join(' and ')} key. You can add it any time in Settings.`
        : 'Everything is stored encrypted on this computer. Change any of it later in Settings.'} />
      <ul className="grid gap-2 text-[13px]">
        {[...KEYS.map((k) => [LABEL[k.name], !!saved?.[k.name], k.optional] as const),
          ['Posting (Zernio)', !!zernio.connected, true] as const].map(([name, ok, optional]) => (
          <li key={name} className={cx('flex items-center gap-2', ok ? 'text-ink' : 'text-ink-3')}>
            <span className={cx('grid size-5 place-items-center rounded-full', ok ? 'bg-accent text-ink' : 'bg-black/[0.06]')}>
              {ok && <Check size={11} weight="bold" />}</span>
            {name}{!ok && (optional ? ', skipped' : ', not set yet')}
          </li>))}
      </ul>
      <Footer>
        <Button variant="ghost" onClick={() => setStep(0)}>Back to the keys</Button>
        <Button variant="primary" onClick={onDone}>Start creating</Button>
      </Footer>
    </>
  }

  return (
    <div className="ambient relative grid h-full place-items-center overflow-auto px-10 py-10">
      <div className="grid w-full max-w-[520px] gap-6 rounded-[32px] bg-panel px-10 pt-9 pb-8 shadow-[0_30px_80px_-40px_rgb(17_18_20/0.55)]">
        <p className="text-xs text-ink-3" aria-live="polite">Step {step + 1} of {STEPS}</p>
        {error && <ErrorNote error={error} />}
        <div key={step} className="anim-page grid gap-6">{body}</div>
      </div>
    </div>
  )
}

function Heading({ title, text }: { title: string; text: string }) {
  return (
    <div className="grid gap-2">
      <h1 className="font-display text-[30px] leading-[1.1] font-semibold tracking-[-0.03em] text-ink"><Reveal text={title} /></h1>
      <p className="text-[14px] leading-relaxed text-ink-2">{text}</p>
    </div>
  )
}

function Footer({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-between gap-3 pt-1">{children}</div>
}
