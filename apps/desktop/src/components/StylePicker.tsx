import { useEffect, useId, useState } from 'react'
import { Check } from '@phosphor-icons/react'
import { call, type CaptionStyle, type TextPosition } from '../lib/studio'
import { Choices, Field, Select, cx } from './ui'

type Swatch = { id: string; label: string; src: string }

/** Previews come from the real renderers (backend previews.py); re-fetched, debounced, when a choice changes. */
function useSwatches<T>(method: string, params: object) {
  const [data, setData] = useState<T>()
  const key = JSON.stringify(params)
  useEffect(() => {
    let live = true
    const t = setTimeout(() => { call<T>(method, params).then((d) => live && setData(d), () => {}) }, 220)
    return () => { live = false; clearTimeout(t) }
  }, [method, key])
  return data
}

/** A radio group of rendered swatches: the picture is the label, the name sits under it. */
function SwatchGrid({ legend, swatches, value, onChange, auto, ratio }: {
  legend: string; swatches?: Swatch[]; value: string; onChange: (v: string) => void
  auto?: { label: string; hint: string }; ratio: string
}) {
  const name = useId()
  const tile = (id: string, labelText: string, body: React.ReactNode) => (
    <label key={id} className="no-drag group grid cursor-pointer gap-2">
      <input type="radio" name={name} className="peer sr-only" checked={value === id} onChange={() => onChange(id)} />
      <span className={cx('relative block overflow-hidden rounded-field border transition-[border-color,transform] duration-200',
        'peer-focus-visible:outline-2 peer-focus-visible:outline-offset-4 peer-focus-visible:outline-accent',
        value === id ? 'halo border-transparent' : 'border-line group-hover:border-line-strong')} style={{ aspectRatio: ratio }}>
        {body}
        {value === id && (
          <span aria-hidden className="absolute right-1.5 top-1.5 grid size-6 place-items-center rounded-full bg-accent text-on-accent shadow-[0_0_0_2px_#fff]">
            <Check size={13} weight="bold" />
          </span>
        )}
      </span>
      <span className={cx('text-[12px]', value === id ? 'font-medium text-ink' : 'text-ink-2')}>{labelText}</span>
    </label>
  )
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-[13px] font-medium text-ink">{legend}</legend>
      <div className="grid grid-cols-4 gap-4 p-2">
        {auto && tile('auto', auto.label,
          <span className="grid h-full place-items-center bg-black/[0.03] px-3 text-center text-[12px] leading-snug text-ink-2">{auto.hint}</span>)}
        {swatches
          ? swatches.map((s) => tile(s.id, s.label, <img src={s.src} alt="" className="h-full w-full object-cover" />))
          : Array.from({ length: auto ? 7 : 6 }, (_, i) => tile(`loading-${i}`, ' ', <span className="block h-full w-full animate-pulse bg-black/[0.04]" />))}
      </div>
    </fieldset>
  )
}

const POSITIONS = [{ value: 'auto', label: 'Auto' }, { value: 'top', label: 'Top' }, { value: 'center', label: 'Centre' },
  { value: 'bottom', label: 'Bottom' }]

export function ImageDesignPicker({ design, font, position, onChange }: {
  design: string; font: string; position: TextPosition
  onChange: (patch: { image_design?: string; image_font?: string; image_position?: TextPosition }) => void
}) {
  const data = useSwatches<{ designs: Swatch[]; fonts: Record<string, string> }>('design.previews', { font, position })
  return (
    <div className="grid gap-5">
      <SwatchGrid legend="Image design" ratio="4 / 5" value={design} swatches={data?.designs}
        auto={{ label: 'Auto', hint: 'Mixes the genre’s designs across the batch' }}
        onChange={(v) => onChange({ image_design: v })} />
      <div className="grid grid-cols-2 gap-4">
        <Field label="Headline font">
          {(id) => <Select id={id} value={font} onChange={(v) => onChange({ image_font: v })}
            options={Object.entries(data?.fonts ?? { auto: 'Matches the design' }).map(([value, label]) => ({ value, label }))} />}
        </Field>
        <Choices legend="Text position" value={position} options={POSITIONS}
          onChange={(v) => onChange({ image_position: v })} />
      </div>
    </div>
  )
}

export function CaptionPicker({ value, onChange }: { value: CaptionStyle; onChange: (v: CaptionStyle) => void }) {
  const { style, ...rest } = value
  const data = useSwatches<{ styles: Swatch[]; fonts: Record<string, string> }>('captions.previews', { style: rest })
  const set = <K extends keyof CaptionStyle>(k: K, v: CaptionStyle[K]) => onChange({ ...value, [k]: v })
  return (
    <div className="grid gap-5">
      <SwatchGrid legend="Subtitle style" ratio="9 / 16" value={style} swatches={data?.styles}
        onChange={(v) => set('style', v as CaptionStyle['style'])} />
      <div className="grid grid-cols-2 gap-4">
        <Field label="Subtitle font">
          {(id) => <Select id={id} value={value.font} onChange={(v) => set('font', v)}
            options={Object.entries(data?.fonts ?? { auto: 'Matches the style' }).map(([v, label]) => ({ value: v, label }))} />}
        </Field>
        <Field label="Highlight colour">
          {(id) => <Select id={id} value={value.highlight} onChange={(v) => set('highlight', v as CaptionStyle['highlight'])}
            options={[{ value: 'auto', label: 'Matches the style' }, { value: 'palette', label: "The project's palette" },
              { value: 'yellow', label: 'Yellow' }, { value: 'orange', label: 'Orange' }, { value: 'green', label: 'Green' },
              { value: 'red', label: 'Red' }, { value: 'white', label: 'White (no highlight)' }]} />}
        </Field>
      </div>
      <Choices legend="Subtitle position" value={value.position} onChange={(v) => set('position', v)}
        options={[{ value: 'lower', label: 'Lower third' }, { value: 'middle', label: 'Middle' }, { value: 'upper', label: 'Upper' }]} />
      <div className="grid grid-cols-2 gap-4">
        <Choices legend="Size" value={value.size} onChange={(v) => set('size', v)}
          options={[{ value: 'small', label: 'Small' }, { value: 'medium', label: 'Medium' }, { value: 'large', label: 'Large' }]} />
        <Choices legend="Letter case" value={value.case} onChange={(v) => set('case', v)}
          options={[{ value: 'auto', label: 'Auto' }, { value: 'upper', label: 'CAPS' }, { value: 'lower', label: 'lower' },
            { value: 'as_spoken', label: 'As spoken' }]} />
      </div>
    </div>
  )
}

// Footage colour. Keys match the backend's visual.PALETTES; the dots are only a hint of each look.
const PALETTES: { value: string; label: string; dots: string[] }[] = [
  { value: 'auto', label: 'Auto', dots: [] },
  { value: 'warm', label: 'Warm and golden', dots: ['#f3d3a1', '#e8a25b', '#a8572a'] },
  { value: 'cool', label: 'Cool blues', dots: ['#c9d8e6', '#6f93b8', '#2e4a66'] },
  { value: 'earth', label: 'Earth and green', dots: ['#c9bb8f', '#6e7f4a', '#3f4b2e'] },
  { value: 'mono', label: 'Black and white', dots: ['#ededed', '#8a8a8a', '#2a2a2a'] },
  { value: 'dark', label: 'Dark and moody', dots: ['#5a4636', '#2a221d', '#0f0d0c'] },
  { value: 'light', label: 'Bright and airy', dots: ['#fbf7f0', '#eadfcd', '#cfc2ae'] },
]

/** Picks the colour the stock footage should already have: photos are filtered at the source (fewer, better
 *  searches), videos are ranked by how well they match. */
export function PalettePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const name = useId()
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-[13px] font-medium text-ink">Footage colour</legend>
      <div className="flex flex-wrap gap-2.5 p-1">
        {PALETTES.map((p) => (
          <label key={p.value} className={cx(
            'no-drag relative flex h-9 cursor-pointer items-center gap-2 rounded-control border px-3.5 text-[13px] transition-colors duration-150',
            'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent',
            value === p.value ? 'chip-on halo-sm' : 'border-line bg-black/[0.03] text-ink-2 hover:border-line-strong hover:text-ink')}>
            <input type="radio" name={name} className="sr-only" checked={value === p.value} onChange={() => onChange(p.value)} />
            {!!p.dots.length && (
              <span aria-hidden className="flex -space-x-1">
                {p.dots.map((d) => <span key={d} className="size-3 rounded-full shadow-[0_0_0_1.5px_rgb(17_18_20/0.22)]" style={{ background: d }} />)}
              </span>
            )}
            {p.label}
          </label>
        ))}
      </div>
      <p className="text-xs text-ink-3">Auto keeps the subject first and leans toward the genre's usual look.</p>
    </fieldset>
  )
}
