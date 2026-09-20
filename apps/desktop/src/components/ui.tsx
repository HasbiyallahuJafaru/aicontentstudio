// The small shared component set. Every screen builds from these; no one-off button or input styles.
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { useEffect, useId, useRef, useState } from 'react'
import { CaretDown, Check } from '@phosphor-icons/react'

const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(' ')

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; kbd?: string }

export function Button({ variant = 'secondary', kbd, className, children, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={cx(
        'no-drag inline-flex h-10 items-center gap-2 rounded-control px-5 text-[13px] font-medium whitespace-nowrap',
        'transition-[background-color,color,transform,box-shadow] duration-150 active:scale-[0.97]',
        'disabled:pointer-events-none disabled:opacity-40',
        variant === 'primary' && 'bg-ink text-ground shadow-[0_8px_24px_-8px_rgb(255_240_225/0.35)] hover:bg-white',
        variant === 'secondary' && 'bg-white/[0.07] text-ink hover:bg-white/[0.12]',
        variant === 'ghost' && 'px-3 text-ink-2 hover:bg-white/[0.06] hover:text-ink',
        variant === 'danger' && 'text-danger hover:bg-danger/10',
        className,
      )}
    >
      {children}
      {kbd && <kbd className="font-sans text-2xs opacity-60">{kbd}</kbd>}
    </button>
  )
}

export function Field({ label, hint, error, children }: { label: string; hint?: ReactNode; error?: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">{label}</label>
      {children(id)}
      {error ? <p className="text-xs text-danger">{error}</p> : hint && <p className="text-xs text-ink-3">{hint}</p>}
    </div>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={cx(
        'no-drag h-10 w-full rounded-field border border-line bg-black/20 px-3.5 text-[13px] text-ink',
        'placeholder:text-ink-3 hover:border-line-strong focus:border-accent/70 focus:bg-black/30 focus:outline-none',
        'transition-colors duration-150',
        className,
      )}
    />
  )
}

/** A group of mutually exclusive (radio) or independent (checkbox) choices, rendered as quiet chips. */
export function Choices<T extends string | number>({ legend, options, value, onChange, multiple }: {
  legend: string
  options: { value: T; label: string }[]
  value: T | T[]
  onChange: (v: any) => void
  multiple?: boolean
}) {
  const name = useId()
  const selected = (v: T) => (Array.isArray(value) ? value.includes(v) : value === v)
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-[13px] font-medium text-ink">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <label
            key={o.value}
            className={cx(
              'no-drag relative flex h-9 items-center rounded-control border px-4 text-[13px]',
              'transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent',
              selected(o.value) ? 'border-transparent bg-ink font-medium text-ground' : 'border-line bg-white/[0.03] text-ink-2 hover:border-line-strong hover:text-ink',
            )}
          >
            <input
              type={multiple ? 'checkbox' : 'radio'}
              name={name}
              className="sr-only"
              checked={selected(o.value)}
              onChange={() => {
                if (!multiple) return onChange(o.value)
                const arr = value as T[]
                onChange(arr.includes(o.value) ? arr.filter((x) => x !== o.value) : [...arr, o.value])
              }}
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function ErrorNote({ error, action }: { error: { message: string; detail?: string }; action?: ReactNode }) {
  return (
    <div role="alert" className="grid gap-2 rounded-field bg-danger/[0.09] px-5 py-4 text-[13px] shadow-[inset_0_0_0_1px_rgb(242_144_127/0.18)]">
      <div className="flex items-start justify-between gap-4">
        <p className="text-ink">{error.message}</p>
        {action}
      </div>
      {error.detail && (
        <details className="text-xs text-ink-2">
          <summary className="cursor-pointer select-none hover:text-ink">View technical details</summary>
          <pre data-selectable className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-2xs text-ink-3">{error.detail}</pre>
        </details>
      )}
    </div>
  )
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex items-end justify-between gap-6 pb-8">
      <h1 className="font-display text-title font-semibold tracking-[-0.03em]">{title}</h1>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  )
}

/** Shared dropdown popup look (PRD): black background, white text, rounded, airier spacing. */
const POPUP_CLS = 'z-50 grid max-h-[320px] gap-1.5 overflow-y-auto rounded-field bg-black p-1.5 shadow-[inset_0_0_0_1px_rgb(255_244_232/0.1),0_24px_48px_-16px_rgb(0_0_0/0.85)]'
const OPTION_CLS = 'flex w-full items-center justify-between gap-2 rounded-[10px] px-3.5 py-2.5 text-left text-[13px] text-ink transition-colors duration-100 hover:bg-white/[0.08]'

/** Branded dropdown (replaces the unreadable native select popup): keyboard aware, closes on outside click.
 * The popup is pinned to the screen spot where it opened - it does not travel with page scroll. */
export function Select<T extends string>({ id, value, options, onChange, className }: {
  id?: string
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [rect, setRect] = useState<{ left: number; top: number; width: number }>()
  const ref = useRef<HTMLDivElement>(null)
  const current = options.find((o) => o.value === value)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const indexOf = (v: T) => Math.max(0, options.findIndex((o) => o.value === v))

  function toggle() {
    const r = ref.current?.getBoundingClientRect()
    if (r) setRect({ left: r.left, top: r.bottom + 6, width: r.width })
    setActive(indexOf(value))
    setOpen((o) => !o)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); toggle() }
      return
    }
    if (e.key === 'Escape' || e.key === 'Tab') setOpen(false)
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); setOpen(false); onChange(options[active].value) }
  }

  return (
    <div ref={ref} className={cx('relative', className)}>
      <button type="button" id={id} aria-haspopup="listbox" aria-expanded={open}
        onClick={toggle} onKeyDown={onKeyDown}
        className={cx('flex h-10 w-full items-center justify-between gap-2 rounded-field border bg-black/20 px-3.5 text-left text-[13px] text-ink',
          'transition-colors duration-150 focus:outline-none',
          open ? 'border-accent/70 bg-black/30' : 'border-line hover:border-line-strong')}>
        {current?.label}
        <CaretDown size={13} className={cx('shrink-0 text-ink-3 transition-transform duration-150', open && 'rotate-180')} />
      </button>
      {open && rect && (
        <ul role="listbox" style={{ position: 'fixed', top: rect.top, left: rect.left, width: rect.width }} className={POPUP_CLS}>
          {options.map((o, i) => (
            <li key={o.value}>
              <button type="button" role="option" aria-selected={o.value === value}
                onMouseEnter={() => setActive(i)}
                onClick={() => { setOpen(false); onChange(o.value) }}
                className={cx(OPTION_CLS, i === active && 'bg-white/[0.08]', o.value === value && 'font-medium')}>
                {o.label}
                {o.value === value && <Check size={13} weight="bold" className="shrink-0 text-accent" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Text input with branded suggestions (replaces the native datalist popup on Create). */
export function Autocomplete({ id, value, suggestions, onChange, onFocus, ...rest }: Omit<
  InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> & {
  value: string
  suggestions: string[]
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [rect, setRect] = useState<{ left: number; top: number; width: number }>()
  const ref = useRef<HTMLDivElement>(null)
  const typed = value.trim().toLowerCase()
  const list = suggestions.filter((s) => s.toLowerCase() !== typed &&
    (typed === '' || s.toLowerCase().includes(typed)))

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  function show() {
    const r = ref.current?.getBoundingClientRect()
    if (r) setRect({ left: r.left, top: r.bottom + 6, width: r.width })
    setOpen(true)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (open && e.key === 'Escape') { e.preventDefault(); setOpen(false); return }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!open) { show(); return }
      e.preventDefault()
      setActive((a) => (e.key === 'ArrowDown' ? Math.min(a + 1, list.length - 1) : Math.max(a - 1, -1)))
    } else if (e.key === 'Enter' && open && active >= 0 && list[active]) {
      e.preventDefault()
      onChange(list[active])
      setOpen(false)
      setActive(-1)
    }
  }

  return (
    <div ref={ref} className="relative">
      <Input {...rest} id={id} value={value} role="combobox" aria-expanded={open} autoComplete="off"
        onFocus={(e) => { onFocus?.(e); show() }}
        onChange={(e) => { onChange((e.target as HTMLInputElement).value); show(); setActive(-1) }}
        onKeyDown={onKeyDown} />
      {open && rect && list.length > 0 && (
        <ul role="listbox" style={{ position: 'fixed', top: rect.top, left: rect.left, width: rect.width }} className={POPUP_CLS}>
          {list.map((s, i) => (
            <li key={s}>
              <button type="button" role="option" aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => { onChange(s); setOpen(false); setActive(-1) }}
                className={cx(OPTION_CLS, i === active && 'bg-white/[0.08]')}>
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export { cx }
