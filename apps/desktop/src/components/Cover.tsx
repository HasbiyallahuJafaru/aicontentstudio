// A project's or piece's face: its real rendered image when there is one, otherwise its own written line set on a
// warm frame. Never a stock stand-in or a placeholder: every pixel shown is something the studio actually made.
import { mediaUrl } from '../lib/studio'
import { cx } from './ui'

export function Cover({ src, quote, ratio = '4/5', className, size = 'md' }: {
  src?: string | null; quote?: string | null; ratio?: '4/5' | '9/16'; className?: string; size?: 'sm' | 'md' | 'lg'
}) {
  const text = size === 'lg' ? 'text-[19px] p-6' : size === 'md' ? 'text-[13px] p-4' : 'text-[8px] p-1.5 leading-tight'
  return (
    <div style={{ aspectRatio: ratio }} className={cx(
      'relative isolate overflow-hidden rounded-[18px] bg-ink',
      'shadow-[0_18px_40px_-16px_rgb(17_18_20/0.22),inset_0_0_0_1px_rgb(17_18_20/0.1)]', className)}>
      {src ? (
        <img src={mediaUrl(src)} alt="" loading="lazy" decoding="async"
          className="absolute inset-0 -z-10 size-full object-cover transition-transform duration-700 ease-[var(--ease-premium)] group-hover:scale-[1.04]" />
      ) : (
        <>
          {/* the studio lamp, small: a warm glow in the corner so a text-only frame still feels lit */}
          {quote && (
            <p className={cx('absolute inset-x-0 bottom-0 font-display font-semibold tracking-[-0.01em] text-white text-balance', text)}>
              {quote}
            </p>
          )}
        </>
      )}
    </div>
  )
}
