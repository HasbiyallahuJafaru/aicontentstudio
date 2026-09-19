import { useEffect, useRef, useState } from 'react'
import { Aperture, ArrowUpRight } from '@phosphor-icons/react'
import { studio } from '../lib/studio'
import { Button } from '../components/ui'
import splashVideo from '../assets/splash.webm'

const DEVELOPER_URL = 'https://hasbiyallahu.xyz'

export function Splash({ onCreate }: { onCreate: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [videoOk, setVideoOk] = useState(true)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) videoRef.current?.pause()
  }, [])

  return (
    <div className="relative h-full overflow-hidden bg-[#101113]">
      {videoOk && (
        <video
          ref={videoRef}
          className="absolute inset-0 size-full object-cover"
          src={splashVideo}
          autoPlay
          muted
          loop
          playsInline
          onError={() => setVideoOk(false)}
        />
      )}
      <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_50%_10%,rgba(10_9_8/0.18),rgba(10_9_8/0.6)_55%,rgba(10_9_8/0.85))]" />

      <div className="relative grid h-full content-center justify-items-center gap-7 px-10 text-center">
        <Aperture size={40} weight="fill" className="text-accent drop-shadow-[0_2px_12px_rgba(0,0,0,0.45)]" />
        <div className="grid gap-3">
          <h1 className="font-display text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] text-ink">
            AI Social Content Studio
          </h1>
          <p className="mx-auto max-w-[52ch] text-[15px] leading-relaxed text-ink-2">
            A short brief becomes finished social content: quotes, narration, visuals and captions,
            written and kept entirely on your own computer.
          </p>
        </div>
        <div className="mt-1 flex items-center gap-3">
          <Button variant="primary" onClick={onCreate}>Let&apos;s create content</Button>
          <Button variant="secondary" onClick={() => studio.openExternal(DEVELOPER_URL)}>
            Meet our developer<ArrowUpRight size={14} />
          </Button>
        </div>
      </div>

      <p className="absolute bottom-4 right-5 text-2xs text-ink-3">Waves: Adam S. Keck, CC BY-SA 4.0</p>
    </div>
  )
}
