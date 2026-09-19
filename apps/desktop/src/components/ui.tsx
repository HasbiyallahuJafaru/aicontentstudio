// The small shared component set. Every screen builds from these; no one-off button or input styles.
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { useId } from 'react'

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

export { cx }
