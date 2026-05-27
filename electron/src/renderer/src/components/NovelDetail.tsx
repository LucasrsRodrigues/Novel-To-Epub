import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  ChevronLeft,
  Download,
  ExternalLink,
  FileEdit,
  Hammer,
  ImageIcon,
  Loader2,
  Plus,
  RefreshCw,
  Send
} from 'lucide-react'
import {
  api,
  type GlossaryEntry,
  type JobStatus,
  type NovelDetail as NovelDetailT,
  type VolumeOut
} from '@renderer/lib/api'
import { useJobs } from '@renderer/context/JobsContext'
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
    api.getNovelVolumes(novelId).then(setPersistedVolumes).catch(() => {})
  }, [doneJobsKey, novelId, novel])

  // Volumes = persistido (DB) + jobs ativos (in-memory) que ainda nao viraram
  // EPUB. Persistido vem primeiro (mais recentes); jobs em curso no topo.
  type DisplayVolume =
    | { kind: 'persisted'; vol: VolumeOut; createdAt: string }
    | { kind: 'job'; job: JobStatus; createdAt: string }
  const volumes = useMemo<DisplayVolume[]>(() => {
    if (!novel) return []
    const persisted: DisplayVolume[] = persistedVolumes.map((v) => ({
      kind: 'persisted', vol: v, createdAt: v.created_at
    }))
    // Inclui jobs ainda nao concluidos (queued/running) ou que falharam
    // (erro/zero output). Done duplicaria persistido — pula.
    const activeJobs: DisplayVolume[] = Object.values(jobs)
      .filter((j) => urlsMatch(j.url, novel.source_url))
      .filter((j) => j.status !== 'done')
      .map((j) => ({ kind: 'job' as const, job: j, createdAt: j.created_at }))
    return [...activeJobs, ...persisted].sort((a, b) =>
      b.createdAt.localeCompare(a.createdAt)
    )
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
            api.getNovelVolumes(novelId).then(setPersistedVolumes).catch(() => {})
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
          {novel.author ?? 'autor desconhecido'} · <span className="font-sans not-italic text-[11px] tracking-[0.16em] uppercase">{novel.source}</span>
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
                  onVolumeUpdated={(updated) =>
                    setPersistedVolumes((prev) =>
                      prev.map((x) => (x.id === updated.id ? updated : x))
                    )
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

function PersistedVolumeRow({
  vol, novelId, onVolumeUpdated, onOpenEditor
}: {
  vol: VolumeOut
  novelId: number
  onVolumeUpdated: (v: VolumeOut) => void
  onOpenEditor: (vol: VolumeOut) => void
}): React.JSX.Element {
  const [sending, setSending] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null)
  void novelId  // referenced no botão Editor via onOpenEditor; mantido pra futura expansão
  // Tradução incompleta = ainda tem caps em EN. Volume nao deve ser tratado
  // como "pronto" — esconde .epub/Kindle/Regerar capa e mostra Retraduzir.
  const incompleteTranslation = !!vol.translate_to && vol.translation_failed > 0

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

  async function regenerateCover(): Promise<void> {
    setRegenerating(true)
    setSendMsg(null)
    try {
      await api.regenerateVolumeCover(vol.id)
      setSendMsg({ ok: true, text: 'novo job criado — capa será regerada (~R$0,20)' })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRegenerating(false)
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
        'flex flex-wrap items-center gap-3 rounded-xl border bg-[var(--paper-100)] px-4 py-3',
        'border-[var(--border-soft)]'
      ].join(' ')}
    >
      <div className="min-w-0 flex-1">
        <div className="font-display truncate text-[15px] font-medium tracking-tight">
          {vol.volume_title ?? `Capítulos ${vol.start}–${vol.end ?? '?'}`}
        </div>
        <div className="font-sans text-[11px] tracking-wide text-[var(--ink-500)]">
          caps {vol.start}–{vol.end ?? '?'} · {vol.translate_to ?? 'original'}
          {vol.ai_cover && ' · capa IA'}
          {incompleteTranslation && (
            <span className="text-[var(--ink-stamp)]">
              {' '}· {vol.translation_failed} falharam tradução
            </span>
          )}
        </div>
      </div>
      {incompleteTranslation ? (
        // Tradução incompleta: Retraduzir (Gemini) OU Editar (manual). Esconde
        // .epub/Kindle/Regerar capa pra evitar leitor levar EPUB pensando que ok.
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
          {vol.ai_cover && (
            <Button
              variant="outline"
              size="sm"
              onClick={regenerateCover}
              disabled={regenerating}
            >
              {regenerating ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <ImageIcon className="size-3.5" />
              )}
              Regerar capa
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={sendKindle} disabled={sending}>
            {sending ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
            Kindle
          </Button>
        </>
      )}
      {sendMsg && (
        <span
          className={[
            'font-sans w-full text-[11px]',
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
