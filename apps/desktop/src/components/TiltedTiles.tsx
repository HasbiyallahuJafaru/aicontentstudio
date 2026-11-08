import type { CSSProperties } from 'react'

/** A tilted wall of image columns drifting past (the React Bits Pro "Tilted Tiles" idea, our own CSS: no license,
 * no dependency). Each column holds its images twice and slides by half its height, so the loop never shows a seam;
 * neighbouring columns run opposite ways at different speeds. Motion lives in index.css under no-preference, so
 * reduced motion leaves a still wall. */
export function TiltedTiles({ images, columns = 11, className }: { images: string[]; columns?: number; className?: string }) {
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className ?? ''}`}>
      <div className="absolute left-1/2 top-1/2 grid w-[160%] -translate-x-1/2 -translate-y-1/2 -rotate-[14deg] gap-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {Array.from({ length: columns }, (_, c) => {
          const strip = images.map((_, i) => images[(i + c * 3) % images.length])  // each column starts elsewhere
          return (
            <div key={c} className={`tile-col grid gap-3 ${c % 2 ? 'tile-down' : ''}`}
              style={{ '--dur': `${48 + (c % 3) * 14}s` } as CSSProperties}>
              {[...strip, ...strip].map((src, i) => (
                <img key={i} src={src} alt="" draggable={false} className="aspect-[4/5] w-full rounded-[10px] object-cover" />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
