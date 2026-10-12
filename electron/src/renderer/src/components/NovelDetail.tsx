import { useEffect, useMemo, useState } from 'react'
import { BookOpen, ChevronLeft, Download, ExternalLink, Loader2, Plus, Send } from 'lucide-react'
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
import { ActiveJobRow } from '@renderer/components/novel/ActiveJobRow'
import { CoverGallery } from '@renderer/components/novel/CoverGallery'
import { MirrorsSection } from '@renderer/components/novel/MirrorsSection'
import { PersistedVolumeRow } from '@renderer/components/novel/PersistedVolumeRow'
import { StatTile } from '@renderer/components/novel/StatTile'
import { slugifyName, urlsMatch } from '@renderer/lib/novel'

export function NovelDetail({
  novelId,
  onBack,
  onCaptureMore,
  onOpenGlossary
}: {
  novelId: number
  onBack: () => void
  onCaptureMore: (url: string, coverStyle: string | null) => void
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
  // Ações em lote da seção Volumes (baixar tudo / enviar tudo pro Kindle).
  const [kindleAllBusy, setKindleAllBusy] = useState(false)
  const [bulkMsg, setBulkMsg] = useState<{ ok: boolean; text: string } | null>(null)
  // Download "Baixar tudo": null = ocioso; -1 = preparando (sem total); 0..1 = transferindo.
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null)
  const { jobs } = useJobs()

  useEffect(() => {
    // Respostas que chegam depois de trocar de novel/desmontar sao descartadas.
    let active = true
    api
      .getNovelDetail(novelId)
      .then((n) => active && setNovel(n))
      .catch((e) => active && setError(e instanceof Error ? e.message : String(e)))
    api
      .getGlossary(novelId)
      .then((g) => active && setGlossary(g))
      .catch(() => {})
    api
      .getNovelVolumes(novelId)
      .then((v) => active && setPersistedVolumes(v))
      .catch(() => active && setPersistedVolumes([]))
    api
      .getSettings()
      .then((s) => {
        if (!active) return
        setTargetLang(s.target_language || 'pt-BR')
        setEnabledStyles(s.cover_styles_enabled ?? [])
      })
      .catch(() => {})
    return () => {
      active = false
    }
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
    // So quando aparece/muda um job concluido: a carga inicial ja e do efeito
    // acima (antes este efeito dependia do objeto `novel` e re-buscava os
    // volumes de novo assim que a novel chegava).
    if (!doneJobsKey) return
    let active = true
    api
      .getNovelVolumes(novelId)
      .then((v) => active && setPersistedVolumes(v))
      .catch(() => {})
    return () => {
      active = false
    }
  }, [doneJobsKey, novelId])

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

  // Volumes "prontos" (tradução completa) — alvo das ações em lote. Mesma regra
  // que esconde .epub/Kindle no card quando faltam caps traduzidos.
  const readyVolumes = persistedVolumes.filter((v) => !(v.translate_to && v.translation_failed > 0))

  // Baixa o .zip de todos os volumes. No Electron, o processo MAIN faz o fetch +
  // grava no disco (o binário não passa pelo IPC — antes corrompia o .zip); o
  // progresso chega por evento. No browser (dev:web), cai no fetch + blob URL.
  async function downloadAll(): Promise<void> {
    setBulkMsg(null)
    const url = api.allVolumesZipUrl(novelId)
    const name = `${slugifyName(novel?.title ?? 'volumes')}.zip`
    // window.api só existe no Electron (preload); no dev:web é undefined.
    const downloadFile = window.api?.downloadFile

    setDownloadProgress(-1) // preparando (backend está montando o zip)
    if (downloadFile) {
      try {
        const r = await downloadFile(url, name, (pct) => setDownloadProgress(pct))
        if (r.error) {
          setBulkMsg({ ok: false, text: r.error })
        } else if (r.canceled) {
          setBulkMsg({ ok: false, text: 'download cancelado' })
        } else {
          const mb = ((r.bytes ?? 0) / 1048576).toFixed(1).replace('.', ',')
          setBulkMsg({ ok: true, text: `salvo (${mb} MB): ${r.filePath}` })
        }
      } catch (err) {
        setBulkMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
      } finally {
        setDownloadProgress(null)
      }
      return
    }

    // Fallback browser (dev:web): fetch + blob URL.
    try {
      const res = await fetch(url)
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || `falha no download (${res.status})`)
      }
      const blob = await res.blob()
      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(objUrl)
      const mb = (blob.size / 1048576).toFixed(1).replace('.', ',')
      setBulkMsg({ ok: true, text: `zip pronto (${mb} MB)` })
    } catch (err) {
      setBulkMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setDownloadProgress(null)
    }
  }

  async function sendAllKindle(): Promise<void> {
    setKindleAllBusy(true)
    setBulkMsg(null)
    try {
      const r = await api.sendAllToKindle(novelId)
      const failed = r.results.filter((x) => !x.ok)
      setBulkMsg({
        ok: failed.length === 0,
        text:
          failed.length === 0
            ? `${r.sent} volume(s) enviados para ${r.to}`
            : `${r.sent}/${r.total} enviados — falharam: ${failed.map((f) => f.title).join(', ')}`
      })
    } catch (err) {
      setBulkMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setKindleAllBusy(false)
    }
  }

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
            <Button
              onClick={() => onCaptureMore(novel.source_url, novel.default_cover_style)}
              size="sm"
            >
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
            Volumes
            <span className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
              {volumes.length} {volumes.length === 1 ? 'edição' : 'edições'}
            </span>
          </h3>
          {readyVolumes.length >= 2 && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={downloadAll}
                disabled={downloadProgress !== null}
                title={`Baixa os ${readyVolumes.length} volumes prontos num único .zip`}
              >
                {downloadProgress !== null ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Download className="size-3.5" />
                )}
                {downloadProgress === -1
                  ? 'Preparando…'
                  : downloadProgress !== null
                    ? `Baixando ${Math.round(downloadProgress * 100)}%`
                    : 'Baixar tudo'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={sendAllKindle}
                disabled={kindleAllBusy}
                title={`Envia os ${readyVolumes.length} volumes prontos pro Kindle`}
              >
                {kindleAllBusy ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Send className="size-3.5" />
                )}
                Kindle tudo
              </Button>
            </div>
          )}
        </div>
        {/* Barra de progresso do download (determinada na transferência). */}
        {downloadProgress !== null && downloadProgress >= 0 && (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--paper-200)]">
            <div
              className="h-full rounded-full bg-[var(--stamp-red)] transition-[width] duration-150"
              style={{ width: `${Math.round(downloadProgress * 100)}%` }}
            />
          </div>
        )}
        {bulkMsg && (
          <span
            className={[
              'font-sans block text-[11px]',
              bulkMsg.ok ? 'text-[var(--book-3)]' : 'text-[var(--ink-stamp)]'
            ].join(' ')}
          >
            {bulkMsg.text}
          </span>
        )}
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

      {/* Fontes alternativas (mirrors) — resiliência a cap quebrado */}
      <MirrorsSection
        novelId={novelId}
        primarySource={novel.source}
        primaryUrl={novel.source_url}
      />

      {/* Galeria de capas geradas por IA */}
      <CoverGallery
        novelId={novelId}
        doneJobsKey={doneJobsKey}
        defaultStyle={novel.default_cover_style}
      />

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
