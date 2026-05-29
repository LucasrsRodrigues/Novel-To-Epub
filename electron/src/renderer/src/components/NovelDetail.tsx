import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  Download,
  ExternalLink,
  FileEdit,
  Hammer,
  ImageIcon,
  Languages,
  Loader2,
  Monitor,
  Plus,
  RefreshCw,
  Send,
  Smartphone,
  Sparkles,
  Trash2,
  X
} from 'lucide-react'
import {
  api,
  type CoverKind,
  type CoverOut,
  type WallpaperFmt,
  type GlossaryEntry,
  type JobStatus,
  type NovelDetail as NovelDetailT,
  type VolumeOut
} from '@renderer/lib/api'
import { useJobs } from '@renderer/context/JobsContext'
import { COVER_STYLES } from '@renderer/lib/coverStyles'
import { Button } from '@renderer/components/ui/button'
import { Folio } from '@renderer/components/decorative/Folio'
import { Ribbon } from '@renderer/components/decorative/Ribbon'
import { ChapterEditor } from '@renderer/components/ChapterEditor'

export function NovelDetail({
  novelId,
  onBack,
  onCaptureMore,
  onOpenGlossary
}: {
  novelId: number
  onBack: () => void
  onCaptureMore: (url: string) => void
  onOpenGlossary: (novelId: number) => void
}): React.JSX.Element {
  const [novel, setNovel] = useState<NovelDetailT | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [glossary, setGlossary] = useState<GlossaryEntry[] | null>(null)
  const [persistedVolumes, setPersistedVolumes] = useState<VolumeOut[]>([])
  const [showFullDesc, setShowFullDesc] = useState(false)
  const [editorVolume, setEditorVolume] = useState<VolumeOut | null>(null)
  // Idioma-alvo configurado — usado pelo botão "Traduzir" do volume.
  const [targetLang, setTargetLang] = useState('pt-BR')
  // Estilos de capa habilitados nas Configurações (ids). Definem o comportamento
  // do botão de capa: 0 = automático, 1 = direto, 2+ = menu de escolha.
  const [enabledStyles, setEnabledStyles] = useState<string[]>([])
  const { jobs } = useJobs()

  useEffect(() => {
    api
      .getNovelDetail(novelId)
      .then(setNovel)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    api
      .getGlossary(novelId)
      .then(setGlossary)
      .catch(() => {})
    api
      .getNovelVolumes(novelId)
      .then(setPersistedVolumes)
      .catch(() => setPersistedVolumes([]))
    api
      .getSettings()
      .then((s) => {
        setTargetLang(s.target_language || 'pt-BR')
        setEnabledStyles(s.cover_styles_enabled ?? [])
      })
      .catch(() => {})
  }, [novelId])

  // Re-busca volumes quando um job da mesma novel termina (acabou de gerar
  // ou regerar capa). Detecta isso watching jobs `done` matchando source_url.
  const doneJobsKey = useMemo(() => {
    if (!novel) return ''
    return Object.values(jobs)
      .filter((j) => j.status === 'done' && urlsMatch(j.url, novel.source_url))
      .map((j) => `${j.id}:${j.updated_at}`)
      .join('|')
  }, [jobs, novel])
  useEffect(() => {
    if (!novel) return
    api
      .getNovelVolumes(novelId)
      .then(setPersistedVolumes)
      .catch(() => {})
  }, [doneJobsKey, novelId, novel])

  // Volumes = persistido (DB) + jobs ativos (in-memory) que ainda nao viraram
  // EPUB. Persistido vem primeiro (mais recentes); jobs em curso no topo.
  type DisplayVolume =
    | { kind: 'persisted'; vol: VolumeOut; createdAt: string }
    | { kind: 'job'; job: JobStatus; createdAt: string }
  const volumes = useMemo<DisplayVolume[]>(() => {
    if (!novel) return []
    const persisted: DisplayVolume[] = persistedVolumes.map((v) => ({
      kind: 'persisted',
      vol: v,
      createdAt: v.created_at
    }))
    // Inclui jobs ainda nao concluidos (queued/running) ou que falharam
    // (erro/zero output). Done duplicaria persistido — pula.
    const activeJobs: DisplayVolume[] = Object.values(jobs)
      .filter((j) => urlsMatch(j.url, novel.source_url))
      .filter((j) => j.status !== 'done')
      .map((j) => ({ kind: 'job' as const, job: j, createdAt: j.created_at }))
    return [...activeJobs, ...persisted].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  }, [jobs, novel, persistedVolumes])

  const characters = glossary?.filter((e) => e.kind === 'character').slice(0, 6) ?? []

  if (error) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="size-4" /> voltar à Biblioteca
        </Button>
        <p className="font-sans text-[var(--ink-stamp)]">{error}</p>
      </div>
    )
  }

  if (!novel) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="size-4" /> voltar à Biblioteca
        </Button>
        <p className="font-sans text-[var(--ink-400)]">Carregando…</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {editorVolume && (
        <ChapterEditor
          novelId={novelId}
          volume={editorVolume}
          onClose={() => setEditorVolume(null)}
          onTranslationSaved={() => {
            // Refresh lista de volumes (translation_failed pode ter mudado)
            api
              .getNovelVolumes(novelId)
              .then(setPersistedVolumes)
              .catch(() => {})
          }}
        />
      )}
      <Button variant="ghost" size="sm" onClick={onBack}>
        <ChevronLeft className="size-4" /> Biblioteca
      </Button>

      <header className="space-y-2">
        <Folio n={String(novel.id).padStart(3, '0')} />
        <h2 className="font-display text-[2.5rem] leading-[1.05] font-medium tracking-tight">
          {novel.title}
        </h2>
        <p className="font-display text-base italic text-[var(--ink-500)]">
          {novel.author ?? 'autor desconhecido'} ·{' '}
          <span className="font-sans not-italic text-[11px] tracking-[0.16em] uppercase">
            {novel.source}
          </span>
        </p>
      </header>

      {/* Hero: cover + description */}
      <section
        className={[
          'flex gap-8 rounded-3xl border bg-[var(--paper-100)] px-8 py-8',
          'border-[var(--border-soft)]',
          'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_2px_4px_rgba(80,50,20,0.04),0_24px_48px_-22px_rgba(80,50,20,0.25)]'
        ].join(' ')}
      >
        <div className="relative shrink-0">
          {novel.cover_url ? (
            <img
              src={novel.cover_url}
              alt={novel.title}
              className="h-56 w-40 rounded-md object-cover shadow-[0_4px_14px_rgba(80,50,20,0.32),0_2px_3px_rgba(80,50,20,0.18)]"
            />
          ) : (
            <div className="flex h-56 w-40 items-center justify-center rounded-md bg-[var(--paper-300)]">
              <BookOpen className="size-10 text-[var(--ink-400)]" />
            </div>
          )}
          <Ribbon
            color="var(--bookmark-ribbon)"
            width={18}
            height={32}
            className="absolute -top-1 right-3"
          />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          {novel.description ? (
            <>
              <p
                className={[
                  'font-sans text-[14px] leading-relaxed text-[var(--ink-700)]',
                  showFullDesc ? '' : 'line-clamp-5'
                ].join(' ')}
              >
                {novel.description}
              </p>
              {novel.description.length > 280 && (
                <button
                  type="button"
                  onClick={() => setShowFullDesc((v) => !v)}
                  className="font-sans text-[12px] text-[var(--stamp-red)] hover:underline"
                >
                  {showFullDesc ? 'mostrar menos' : 'ler mais'}
                </button>
              )}
            </>
          ) : (
            <p className="font-sans text-[14px] italic text-[var(--ink-400)]">
              Sem descrição capturada.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button onClick={() => onCaptureMore(novel.source_url)} size="sm">
              <Plus className="size-3.5" /> Capturar mais capítulos
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href={novel.source_url} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" /> Fonte
              </a>
            </Button>
            {novel.wiki_url && (
              <Button variant="outline" size="sm" asChild>
                <a href={novel.wiki_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3.5" /> Wiki
                </a>
              </Button>
            )}
          </div>
        </div>
      </section>

      {/* Stats row */}
      <section className="grid grid-cols-3 gap-4">
        <StatTile label="capítulos em cache" value={String(novel.chapters)} />
        <StatTile
          label="entradas no glossário"
          value={String(glossary?.length ?? '—')}
          onClick={() => onOpenGlossary(novel.id)}
        />
        <StatTile label="volumes baixados" value={String(volumes.length)} />
      </section>

      {/* Volumes section */}
      <section className="space-y-3">
        <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
          Volumes
          <span className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
            {volumes.length} {volumes.length === 1 ? 'edição' : 'edições'}
          </span>
        </h3>
        {volumes.length === 0 ? (
          <p className="font-sans text-[13px] text-[var(--ink-500)]">
            Nenhum volume desta novel foi gerado ainda. Use{' '}
            <em className="font-display italic">Capturar mais capítulos</em> pra criar o primeiro.
          </p>
        ) : (
          <ul className="space-y-2">
            {volumes.map((v) =>
              v.kind === 'persisted' ? (
                <PersistedVolumeRow
                  key={`p-${v.vol.id}`}
                  vol={v.vol}
                  novelId={novelId}
                  targetLang={targetLang}
                  enabledStyles={enabledStyles}
                  defaultStyle={novel.default_cover_style}
                  onVolumeUpdated={(updated) =>
                    setPersistedVolumes((prev) =>
                      prev.map((x) => (x.id === updated.id ? updated : x))
                    )
                  }
                  onVolumeDeleted={(id) =>
                    setPersistedVolumes((prev) => prev.filter((x) => x.id !== id))
                  }
                  onOpenEditor={setEditorVolume}
                />
              ) : (
                <ActiveJobRow key={`j-${v.job.id}`} job={v.job} />
              )
            )}
          </ul>
        )}
      </section>

      {/* Galeria de capas geradas por IA */}
      <CoverGallery novelId={novelId} doneJobsKey={doneJobsKey} />

      {/* Glossary preview */}
      {characters.length > 0 && (
        <section className="space-y-3">
          <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
            Personagens conhecidos
            <button
              type="button"
              onClick={() => onOpenGlossary(novel.id)}
              className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--stamp-red)] hover:underline"
            >
              ver glossário completo →
            </button>
          </h3>
          <div className="flex flex-wrap gap-2">
            {characters.map((c) => (
              <span
                key={c.term}
                className={[
                  'font-display inline-flex items-center gap-2 rounded-full border bg-[var(--paper-100)] px-3 py-1 text-[14px]',
                  'border-[var(--border-soft)] text-[var(--ink-900)]'
                ].join(' ')}
              >
                {c.term}
                {c.gender !== 'n/a' && c.gender !== 'unknown' && (
                  <span className="font-sans text-[10px] tracking-wide uppercase text-[var(--ink-400)]">
                    {c.gender}
                  </span>
                )}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function StatTile({
  label,
  value,
  onClick
}: {
  label: string
  value: string
  onClick?: () => void
}): React.JSX.Element {
  const interactive = !!onClick
  const Tag = interactive ? 'button' : 'div'
  return (
    <Tag
      type={interactive ? 'button' : undefined}
      onClick={onClick}
      className={[
        'rounded-2xl border bg-[var(--paper-100)] px-5 py-4 text-left',
        'border-[var(--border-soft)]',
        'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_1px_2px_rgba(80,50,20,0.04)]',
        interactive
          ? 'cursor-pointer transition-colors hover:bg-[var(--paper-200)] hover:border-[var(--ink-300)]'
          : ''
      ].join(' ')}
    >
      <div className="font-display text-3xl font-medium tracking-tight italic text-[var(--ink-900)]">
        {value}
      </div>
      <div className="font-sans mt-1 text-[10px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
        {label}
      </div>
    </Tag>
  )
}

// As imagens da galeria vêm do backend (http://127.0.0.1:8000). No app empacotado
// o renderer roda em file:// → <img src> cross-origin é bloqueado pelo ORB do
// Chromium. fetch() passa (CORS liberado), então buscamos os bytes e os
// convertemos em data: URL (decodifica em qualquer contexto, sem precisar
// revogar object URL).
async function fetchDataUrl(url: string): Promise<string> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`falha ao carregar (${res.status})`)
  const blob = await res.blob()
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('falha ao ler imagem'))
    reader.readAsDataURL(blob)
  })
}

function slugifyName(s: string): string {
  return (
    s
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'capa'
  )
}

async function downloadCover(url: string, filename: string): Promise<void> {
  const dataUrl = await fetchDataUrl(url)
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function CoverThumb({ url, alt }: { url: string; alt: string }): React.JSX.Element {
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

// Galeria das capas geradas por IA da novel — preview + download da arte em
// vários formatos (com/sem texto, wallpapers). Re-busca quando um job termina.
function CoverGallery({
  novelId,
  doneJobsKey
}: {
  novelId: number
  doneJobsKey: string
}): React.JSX.Element | null {
  const [covers, setCovers] = useState<CoverOut[]>([])
  const [loaded, setLoaded] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    api
      .listCovers(novelId)
      .then(setCovers)
      .catch(() => setCovers([]))
      .finally(() => setLoaded(true))
  }, [novelId, doneJobsKey])

  if (!loaded || covers.length === 0) return null

  const selected = covers.find((c) => c.id === selectedId) ?? null

  return (
    <section className="space-y-3">
      <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
        Galeria de capas
        <span className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
          clique pra baixar
        </span>
      </h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {covers.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setSelectedId(c.id)}
            className="group flex flex-col gap-2 rounded-xl border border-[var(--border-soft)] bg-[var(--paper-100)] p-3 text-left transition-colors hover:border-[var(--ink-300)] hover:bg-[var(--paper-200)]"
          >
            <CoverThumb url={api.coverFileUrl(c.id, 'titled')} alt={c.volume_title ?? 'capa'} />
            <div
              className="font-display truncate text-[13px] font-medium"
              title={c.volume_title ?? ''}
            >
              {c.volume_title ?? 'Capa da novel'}
            </div>
          </button>
        ))}
      </div>
      {selected && (
        <CoverModal
          cover={selected}
          onClose={() => setSelectedId(null)}
          onUpdated={(u) => setCovers((prev) => prev.map((x) => (x.id === u.id ? u : x)))}
        />
      )}
    </section>
  )
}

// Linha de uma resolução no modal: rótulo + botões (download local / nativo).
function ResolutionRow({
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

function CoverModal({
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
            <h3 className="font-display text-lg font-medium tracking-tight">
              {cover.volume_title ?? 'Capa da novel'}
            </h3>

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

function PersistedVolumeRow({
  vol,
  novelId,
  targetLang,
  enabledStyles,
  defaultStyle,
  onVolumeUpdated,
  onVolumeDeleted,
  onOpenEditor
}: {
  vol: VolumeOut
  novelId: number
  targetLang: string
  enabledStyles: string[]
  defaultStyle: string | null
  onVolumeUpdated: (v: VolumeOut) => void
  onVolumeDeleted: (id: number) => void
  onOpenEditor: (vol: VolumeOut) => void
}): React.JSX.Element {
  const [sending, setSending] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [translatingNow, setTranslatingNow] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [coverMenuOpen, setCoverMenuOpen] = useState(false)
  // Estilos do menu, na ordem do catálogo (só os habilitados nas Configurações).
  const menuStyles = COVER_STYLES.filter((s) => enabledStyles.includes(s.id))
  void novelId // referenced no botão Editor via onOpenEditor; mantido pra futura expansão
  // Tradução incompleta = ainda tem caps em EN. Volume nao deve ser tratado
  // como "pronto" — esconde .epub/Kindle/Regerar capa e mostra Retraduzir.
  const incompleteTranslation = !!vol.translate_to && vol.translation_failed > 0
  // Volume sem tradução nenhuma → oferece "Traduzir" (substitui no lugar).
  const untranslated = !vol.translate_to

  async function sendKindle(): Promise<void> {
    setSending(true)
    setSendMsg(null)
    try {
      const res = await api.sendVolumeToKindle(vol.id)
      setSendMsg({ ok: true, text: `enviado para ${res.to}` })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSending(false)
    }
  }

  async function regenerateCover(coverStyle?: string | null): Promise<void> {
    setCoverMenuOpen(false)
    setRegenerating(true)
    setSendMsg(null)
    try {
      await api.regenerateVolumeCover(vol.id, coverStyle ?? null)
      setSendMsg({
        ok: true,
        text: vol.ai_cover
          ? 'novo job criado — capa será regerada (~R$0,20)'
          : 'novo job criado — capa por IA será gerada (~R$0,20)'
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRegenerating(false)
    }
  }

  // Comportamento do botão de capa conforme estilos habilitados nas Configurações:
  // 0 = automático (IA decide); 1 = vai direto nele; 2+ = abre menu pra escolher.
  function onCoverButtonClick(): void {
    if (menuStyles.length >= 2) {
      setCoverMenuOpen((v) => !v)
    } else {
      regenerateCover(menuStyles[0]?.id ?? null)
    }
  }

  // Item 1: traduz um volume que foi baixado sem tradução. Re-usa os capítulos
  // já em cache (só roda o tradutor), e substitui o volume original no lugar
  // (replace_volume_id) pra não duplicar a edição na biblioteca.
  async function translateVolume(): Promise<void> {
    setTranslatingNow(true)
    setSendMsg(null)
    try {
      await api.createDownload({
        url: vol.source_url,
        start: vol.start,
        end: vol.end,
        with_cover: vol.with_cover,
        translate_to: targetLang,
        volume_title: vol.volume_title,
        ai_cover: vol.ai_cover,
        replace_volume_id: vol.id
      })
      setSendMsg({
        ok: true,
        text: `tradução iniciada (${targetLang}) — acompanhe em Downloads; substitui esta edição ao terminar`
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setTranslatingNow(false)
    }
  }

  // Item 3: remove o volume (registro + .epub). Usado pra limpar duplicatas.
  async function removeVolume(): Promise<void> {
    setDeleting(true)
    setSendMsg(null)
    try {
      await api.deleteVolume(vol.id)
      onVolumeDeleted(vol.id)
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  async function rebuildEpub(): Promise<void> {
    setRebuilding(true)
    setSendMsg(null)
    try {
      const updated = await api.rebuildVolume(vol.id)
      onVolumeUpdated(updated)
      setSendMsg({ ok: true, text: 'EPUB recompilado (sem custo)' })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRebuilding(false)
    }
  }

  async function retryTranslation(): Promise<void> {
    setRetrying(true)
    setSendMsg(null)
    try {
      // Re-enqueue mesmo job (cache de traducao pula caps OK, so falhos batem
      // o Gemini de novo). Mesmo padrao do "Continuar tradução" em Downloads.
      await api.createDownload({
        url: vol.source_url,
        start: vol.start,
        end: vol.end,
        with_cover: vol.with_cover,
        translate_to: vol.translate_to,
        volume_title: vol.volume_title,
        ai_cover: vol.ai_cover
      })
      setSendMsg({
        ok: true,
        text: `novo job criado — ${vol.translation_failed} caps serão retentados`
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRetrying(false)
    }
  }

  return (
    <li
      className={[
        'flex flex-col gap-3 rounded-xl border bg-[var(--paper-100)] px-4 py-3',
        'border-[var(--border-soft)]'
      ].join(' ')}
    >
      {/* Título + meta: linha própria, largura total — nunca é esmagado pelos botões. */}
      <div className="min-w-0">
        <div className="font-display text-[15px] font-medium leading-snug tracking-tight">
          {vol.volume_title ?? `Capítulos ${vol.start}–${vol.end ?? '?'}`}
        </div>
        <div className="font-sans mt-0.5 text-[11px] tracking-wide text-[var(--ink-500)]">
          caps {vol.start}–{vol.end ?? '?'} · {vol.translate_to ?? 'original'}
          {vol.ai_cover && ' · capa IA'}
          {incompleteTranslation && (
            <span className="text-[var(--ink-stamp)]">
              {' '}
              · {vol.translation_failed} falharam tradução
            </span>
          )}
        </div>
      </div>

      {/* Ações: linha própria que quebra; Excluir isolado à direita. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {incompleteTranslation ? (
            // Tradução incompleta: Retraduzir (Gemini) OU Editar (manual). Esconde
            // .epub/Kindle/capa pra evitar leitor levar EPUB pensando que está ok.
            <>
              <Button size="sm" onClick={retryTranslation} disabled={retrying}>
                {retrying ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="size-3.5" />
                )}
                Retraduzir
              </Button>
              <Button variant="outline" size="sm" onClick={() => onOpenEditor(vol)}>
                <FileEdit className="size-3.5" /> Editar caps
              </Button>
            </>
          ) : (
            <>
              <Button asChild variant="outline" size="sm">
                <a href={api.volumeFileUrl(vol.id)} download>
                  <Download className="size-3.5" /> .epub
                </a>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={rebuildEpub}
                disabled={rebuilding}
                title="Re-monta o EPUB do cache atual (sem custo)"
              >
                {rebuilding ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Hammer className="size-3.5" />
                )}
                Recompilar
              </Button>
              {untranslated && (
                <Button size="sm" onClick={translateVolume} disabled={translatingNow}>
                  {translatingNow ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Languages className="size-3.5" />
                  )}
                  Traduzir
                </Button>
              )}
              <div className="relative">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onCoverButtonClick}
                  disabled={regenerating}
                  title={
                    vol.ai_cover
                      ? 'Gera uma nova capa por IA (~R$0,20)'
                      : 'Gera uma capa por IA pra este volume (~R$0,20)'
                  }
                >
                  {regenerating ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <ImageIcon className="size-3.5" />
                  )}
                  {vol.ai_cover ? 'Regerar capa' : 'Gerar capa'}
                  {menuStyles.length >= 2 && <ChevronDown className="size-3.5" />}
                </Button>

                {coverMenuOpen && menuStyles.length >= 2 && (
                  <>
                    {/* backdrop transparente: clique fora fecha o menu */}
                    <div className="fixed inset-0 z-40" onClick={() => setCoverMenuOpen(false)} />
                    <div
                      className={[
                        'absolute left-0 top-full z-50 mt-1 max-h-72 w-56 overflow-y-auto',
                        'rounded-xl border border-[var(--border-medium)] bg-[var(--paper-50)] py-1',
                        'shadow-[0_8px_24px_rgba(80,50,20,0.18)]'
                      ].join(' ')}
                    >
                      <button
                        type="button"
                        onClick={() => regenerateCover(null)}
                        className="font-sans block w-full px-3 py-1.5 text-left text-[13px] text-[var(--ink-700)] hover:bg-[var(--paper-200)]"
                      >
                        Automático <span className="text-[var(--ink-400)]">(IA decide)</span>
                      </button>
                      <div className="my-1 border-t border-[var(--border-soft)]" />
                      {menuStyles.map((style) => (
                        <button
                          key={style.id}
                          type="button"
                          onClick={() => regenerateCover(style.id)}
                          className="font-sans flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-[13px] text-[var(--ink-700)] hover:bg-[var(--paper-200)]"
                        >
                          {style.label}
                          {style.id === defaultStyle && (
                            <span className="text-[10px] tracking-wide text-[var(--stamp-red)]">
                              padrão
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <Button variant="outline" size="sm" onClick={sendKindle} disabled={sending}>
                {sending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Send className="size-3.5" />
                )}
                Kindle
              </Button>
            </>
          )}
        </div>

        {confirmDelete ? (
          <span className="flex items-center gap-1.5">
            <span className="font-sans text-[11px] text-[var(--ink-500)]">Excluir?</span>
            <Button variant="outline" size="sm" onClick={removeVolume} disabled={deleting}>
              {deleting ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
              Sim
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(false)}
              disabled={deleting}
            >
              Cancelar
            </Button>
          </span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmDelete(true)}
            title="Remove este volume (registro + arquivo .epub). Não apaga capítulos do cache."
            className="text-[var(--ink-stamp)]"
          >
            <Trash2 className="size-3.5" /> Excluir
          </Button>
        )}
      </div>

      {sendMsg && (
        <span
          className={[
            'font-sans text-[11px]',
            sendMsg.ok ? 'text-[var(--book-3)]' : 'text-[var(--ink-stamp)]'
          ].join(' ')}
        >
          {sendMsg.text}
        </span>
      )}
    </li>
  )
}

function ActiveJobRow({ job }: { job: JobStatus }): React.JSX.Element {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0
  return (
    <li
      className={[
        'flex items-center gap-4 rounded-xl border bg-[var(--paper-100)] px-4 py-3',
        'border-[var(--border-soft)]'
      ].join(' ')}
    >
      <div className="min-w-0 flex-1">
        <div className="font-display truncate text-[15px] font-medium tracking-tight">
          {job.volume_title ?? job.title ?? 'sem título'}
        </div>
        <div className="font-sans text-[11px] tracking-wide text-[var(--ink-500)]">
          caps {job.start}–{job.end ?? '?'} · {job.translate_to ?? 'original'} · {pct}%
        </div>
      </div>
      <span className="font-sans text-[10px] tracking-[0.18em] uppercase text-[var(--ink-400)]">
        {job.status === 'error' ? 'erro' : 'em andamento'}
      </span>
    </li>
  )
}

// Matcha duas URLs ignorando fragment/trailing slash, e tambem comparando
// hosts diferentes do mesmo mirror (novelbin.me vs novelbin.com etc).
function urlsMatch(a: string, b: string): boolean {
  if (!a || !b) return false
  const norm = (u: string): string => {
    try {
      const parsed = new URL(u)
      const path = parsed.pathname.replace(/\/$/, '')
      return path.toLowerCase()
    } catch {
      return u.toLowerCase()
    }
  }
  return norm(a) === norm(b)
}
