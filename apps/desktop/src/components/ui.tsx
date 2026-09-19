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
        'no-drag inline-flex h-8 items-center gap-2 rounded-control px-3 text-[13px] font-medium whitespace-nowrap',
        'transition-[background-color,color,transform] duration-150 active:scale-[0.98]',
        'disabled:pointer-events-none disabled:opacity-40',
        variant === 'primary' && 'bg-ink text-ground hover:bg-white',
        variant === 'secondary' && 'bg-raised text-ink hover:bg-line',
        variant === 'ghost' && 'text-ink-2 hover:bg-raised hover:text-ink',
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
        'no-drag h-8 w-full rounded-control border border-line bg-raised px-2.5 text-[13px] text-ink',
        'placeholder:text-ink-3 hover:border-line-strong focus:border-accent/70 focus:outline-none',
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
              'no-drag relative flex h-8 items-center rounded-control border px-3 text-[13px]',
              'transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent',
              selected(o.value) ? 'border-ink/80 bg-ink/[0.07] text-ink' : 'border-line text-ink-2 hover:border-line-strong hover:text-ink',
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
    <div role="alert" className="grid gap-2 rounded-panel bg-danger/[0.07] px-4 py-3 text-[13px]">
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
      <h1 className="font-display text-title font-semibold tracking-[-0.02em]">{title}</h1>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  )
}

export { cx }
