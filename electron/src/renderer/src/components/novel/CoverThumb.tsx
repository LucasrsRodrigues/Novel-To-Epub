import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { fetchDataUrl } from '@renderer/lib/coverFiles'

export function CoverThumb({ url, alt }: { url: string; alt: string }): React.JSX.Element {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    fetchDataUrl(url)
      .then((u) => {
        if (alive) setSrc(u)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [url])
  return src ? (
    <img
      src={src}
      alt={alt}
      className="aspect-[2/3] w-full rounded-md object-cover shadow-[0_2px_8px_rgba(80,50,20,0.18)]"
    />
  ) : (
    <div className="flex aspect-[2/3] w-full items-center justify-center rounded-md bg-[var(--paper-300)]">
      <Loader2 className="size-5 animate-spin text-[var(--ink-400)]" />
    </div>
  )
}
