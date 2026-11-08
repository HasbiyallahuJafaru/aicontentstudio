import { useEffect, useMemo, useRef, type CSSProperties } from 'react'

const COLUMNS = 28   // tiles around the full circle
const ROWS = 9       // rings, centred on the horizon
const STEP = 360 / COLUMNS

/** The app's background (owner request 2026-11-08, reference: a dome gallery): the viewer stands inside a sphere
 * whose inner wall is lined with rounded tiles of short looping clips (animated WebP) in even rows and columns, turning slowly. CSS 3D only, no
 * WebGL: each tile is turned to its column and row, then pushed out to the wall facing the centre; one CSS animation
 * spins the sphere (index.css `dome-spin`, still under reduced motion). Tiles are greyscale so the colourful UI
 * stays in front. Decorative: aria-hidden, no pointer events. */
export function DomeBackground({ images }: { images: string[] }) {
  const stage = useRef<HTMLDivElement>(null)
  const tiles = useMemo(() => Array.from({ length: COLUMNS * ROWS }, (_, i) => {
    const col = i % COLUMNS
    const row = Math.floor(i / COLUMNS) - (ROWS - 1) / 2
    // neighbours rarely repeat: step through the clips by strides that skip around the set
    return { i, src: images[(i * 5 + row * 3) % images.length], lon: col * STEP + (row % 2 ? STEP / 2 : 0), lat: row * STEP }
  }), [images])

  // the dome's radius follows the window; the camera sits well inside it, so the wall curves away at the edges
  useEffect(() => {
    const el = stage.current
    if (!el) return
    const fit = () => {
      const r = Math.max(el.clientWidth, el.clientHeight) * 1.3
      el.style.setProperty('--r', `${r}px`)
      el.style.setProperty('--tile', `${(2 * Math.PI * r / COLUMNS) * 0.74}px`)
    }
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    fit()
    return () => ro.disconnect()
  }, [])

  if (!images.length) return null
  return (
    <div ref={stage} aria-hidden className="dome-stage pointer-events-none absolute inset-0 overflow-hidden">
      <div className="dome-sphere">
        {tiles.map((t) => (
          <span key={t.i} className="dome-tile" style={{ '--lon': `${t.lon}deg`, '--lat': `${t.lat}deg` } as CSSProperties}>
            <img src={t.src} alt="" draggable={false} />
          </span>
        ))}
      </div>
    </div>
  )
}
