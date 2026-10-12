import { useEffect, useState } from 'react'
import { Download, Loader2, Monitor, Smartphone, Sparkles, X } from 'lucide-react'
import { api, type CoverKind, type CoverOut, type WallpaperFmt } from '@renderer/lib/api'
import { formatStyleSpec } from '@renderer/lib/coverStyles'
import { CoverThumb } from '@renderer/components/novel/CoverThumb'
import { downloadCover } from '@renderer/lib/coverFiles'
import { slugifyName } from '@renderer/lib/novel'

// Linha de uma resolução no modal: rótulo + botões (download local / nativo).
export function ResolutionRow({
  title,
  children
}: {
  title: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-soft)] py-2">
      <span className="font-sans text-[12px] text-[var(--ink-700)]">{title}</span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

export function CoverModal({
  cover,
  onClose,
  onUpdated
}: {
  cover: CoverOut
  onClose: () => void
  onUpdated: (c: CoverOut) => void
}): React.JSX.Element {
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [bust, setBust] = useState(0) // força recarregar o preview após regerar

  const base = slugifyName(cover.volume_title ?? `capa-${cover.id}`)

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function download(kind: CoverKind, opts: { native?: boolean } = {}): void {
    const suffix = {
      titled: '',
      raw: '-sem-texto',
      phone: '-wallpaper-celular',
      pc: '-wallpaper-pc',
      pc_hd: '-wallpaper-pc-2560'
    }[kind]
    const isWallpaper = kind === 'phone' || kind === 'pc' || kind === 'pc_hd'
    // wallpaper local = jpg; capa/arte e wallpaper nativo (Gemini) = png
    const ext = isWallpaper && !opts.native ? 'jpg' : 'png'
    const nativeTag = opts.native ? '-nativo' : ''
    setErr(null)
    downloadCover(
      api.coverFileUrl(cover.id, kind, { native: opts.native, download: true }),
      `${base}${suffix}${nativeTag}.${ext}`
    ).catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }

  async function run(key: string, fn: () => Promise<CoverOut>): Promise<void> {
    setBusy(key)
    setErr(null)
    try {
      onUpdated(await fn())
      setBust((b) => b + 1)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const btn =
    'font-sans inline-flex items-center gap-1 rounded-md border border-[var(--border-soft)] bg-[var(--paper-100)] px-2.5 py-1 text-[11px] text-[var(--ink-700)] transition-colors hover:border-[var(--stamp-red)] hover:text-[var(--stamp-red)] disabled:opacity-50'

  // Botão de wallpaper nativo: baixa se já gerado, senão gera (Gemini, pago).
  const nativeBtn = (fmt: WallpaperFmt, aspect: string): React.JSX.Element =>
    cover.native_aspects.includes(aspect) ? (
      <button type="button" className={btn} onClick={() => download(fmt, { native: true })}>
        <Sparkles className="size-3" /> Nativo ✓
      </button>
    ) : (
      <button
        type="button"
        className={btn}
        disabled={busy !== null}
        onClick={() => run(`native:${fmt}`, () => api.generateNativeWallpaper(cover.id, fmt))}
      >
        {busy === `native:${fmt}` ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <Sparkles className="size-3" />
        )}
        Gerar nativo (~R$0,20)
      </button>
    )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-[var(--border-medium)] bg-[var(--paper-50)] p-6 shadow-[0_24px_60px_-20px_rgba(80,50,20,0.5)]">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-[var(--ink-400)] transition-colors hover:bg-[var(--paper-200)] hover:text-[var(--ink-700)]"
        >
          <X className="size-4" />
        </button>

        <div className="grid gap-6 sm:grid-cols-[200px_1fr]">
          <div className="shrink-0">
            <CoverThumb
              key={bust}
              url={api.coverFileUrl(cover.id, 'titled')}
              alt={cover.volume_title ?? 'capa'}
            />
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-lg font-medium tracking-tight">
                {cover.volume_title ?? 'Capa da novel'}
              </h3>
              <span
                className="font-sans inline-flex items-center gap-1 rounded-full border border-[var(--border-soft)] bg-[var(--paper-200)] px-2 py-0.5 text-[11px] tracking-wide text-[var(--ink-600)]"
                title="Estilo de arte usado nesta capa"
              >
                <Sparkles className="size-3 text-[var(--ink-400)]" />
                {formatStyleSpec(cover.cover_style) ?? 'Automático'}
              </span>
            </div>

            <div className="mt-3">
              <ResolutionRow title="Original (2:3)">
                <button type="button" className={btn} onClick={() => download('titled')}>
                  <Download className="size-3" /> Com título
                </button>
                {cover.has_raw && (
                  <button type="button" className={btn} onClick={() => download('raw')}>
                    <Download className="size-3" /> Sem texto
                  </button>
                )}
              </ResolutionRow>

              {cover.has_raw ? (
                <>
                  <ResolutionRow title="Wallpaper celular · 1080×1920">
                    <button type="button" className={btn} onClick={() => download('phone')}>
                      <Smartphone className="size-3" /> Baixar
                    </button>
                    {nativeBtn('phone', '9:16')}
                  </ResolutionRow>
                  <ResolutionRow title="Wallpaper PC · 1920×1080">
                    <button type="button" className={btn} onClick={() => download('pc')}>
                      <Monitor className="size-3" /> Baixar
                    </button>
                    {nativeBtn('pc', '16:9')}
                  </ResolutionRow>
                  <ResolutionRow title="Wallpaper PC alta · 2560×1440">
                    <button type="button" className={btn} onClick={() => download('pc_hd')}>
                      <Monitor className="size-3" /> Baixar
                    </button>
                    {nativeBtn('pc_hd', '16:9')}
                  </ResolutionRow>
                </>
              ) : (
                <div className="mt-3 rounded-lg border border-[var(--border-soft)] bg-[var(--paper-100)] p-3">
                  <p className="font-sans text-[12px] leading-relaxed text-[var(--ink-500)]">
                    Esta capa foi gerada antes de guardarmos a arte sem texto. Gere de novo a arte
                    (mesma cena e estilo, reusa o prompt) pra liberar o download <em>sem texto</em>{' '}
                    e os wallpapers.
                  </p>
                  <button
                    type="button"
                    className={btn + ' mt-2'}
                    disabled={busy !== null}
                    onClick={() => run('regen', () => api.regenerateCoverArt(cover.id))}
                  >
                    {busy === 'regen' ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Sparkles className="size-3" />
                    )}
                    Gerar arte sem texto (Gemini · ~R$0,20)
                  </button>
                </div>
              )}
            </div>

            {err && <p className="font-sans mt-3 text-[12px] text-[var(--ink-stamp)]">{err}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
