import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CircleAlert,
  CircleCheck,
  Download,
  Eye,
  Languages,
  Loader2,
  Sparkles
} from 'lucide-react'
import { api, type JobStatus, type NovelPreview } from '@renderer/lib/api'
import { useJobs } from '@renderer/context/JobsContext'
import { Button } from '@renderer/components/ui/button'
import { Input } from '@renderer/components/ui/input'
import { Label } from '@renderer/components/ui/label'
import { Checkbox } from '@renderer/components/ui/checkbox'
import { Progress } from '@renderer/components/ui/progress'
import { Card } from '@renderer/components/ui/card'
import { Folio } from '@renderer/components/decorative/Folio'

function statusLabel(job: JobStatus): string {
  switch (job.status) {
    case 'queued':
      return 'Na fila...'
    case 'running':
      if (job.stage === 'meta') return 'Buscando lista de capítulos...'
      if (job.stage === 'translate') return 'Traduzindo capítulos'
      if (job.stage === 'cover') return 'Gerando capa com IA'
      return 'Baixando capítulos'
    case 'done':
      return 'Concluído'
    case 'error':
      return `Erro: ${job.error ?? 'desconhecido'}`
    case 'cancelled':
      return 'Cancelado'
  }
}

export function NewCapture({
  prefilledUrl,
  onUsedPrefill
}: {
  prefilledUrl?: string | null
  onUsedPrefill?: () => void
} = {}): React.JSX.Element {
  const [url, setUrl] = useState('')

  // Quando a app injeta uma URL (ex: clique em "Capturar mais" no NovelDetail),
  // pré-preenche o campo e limpa o flag pra não re-aplicar.
  useEffect(() => {
    if (prefilledUrl) {
      setUrl(prefilledUrl)
      onUsedPrefill?.()
    }
  }, [prefilledUrl, onUsedPrefill])

  const [volumeTitle, setVolumeTitle] = useState('')
  const [start, setStart] = useState('1')
  const [end, setEnd] = useState('')
  const [withCover, setWithCover] = useState(true)
  const [translate, setTranslate] = useState(false)
  const [aiCover, setAiCover] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const { jobs } = useJobs()

  const job = jobId ? jobs[jobId] : undefined
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0

  // Sites que JÁ entregam PT-BR — tradução é desnecessária (e custaria $$ à toa).
  // Hostname do user é normalizado pra match com .com.br / subdomínios.
  const PT_NATIVE_HOSTS = ['novelmania.com.br']
  // Sites que estruturam volumes nativamente. Pro resto (NovelBin, NovelFull...)
  // o preview é decorativo e custa rede — só dispara sob pedido (botão "Pré-visualizar").
  const HOSTS_WITH_VOLUMES = ['novelmania.com.br']

  function matchHost(rawUrl: string, hosts: string[]): boolean {
    try {
      const host = new URL(rawUrl.trim()).hostname.replace(/^www\./, '')
      return hosts.some((d) => host === d || host.endsWith('.' + d))
    } catch {
      return false
    }
  }

  const sourceIsPtNative = useMemo(() => matchHost(url, PT_NATIVE_HOSTS), [url])
  const sourceHasVolumes = useMemo(() => matchHost(url, HOSTS_WITH_VOLUMES), [url])

  // Preview da novel — busca metadata + volumes.
  // Auto-dispara (debounced) APENAS pra sites que entregam volumes (dropdown útil).
  // Pra outros, mostra botão "Pré-visualizar" opcional — evita um request lento
  // que só renderia título/capa decorativos.
  const [preview, setPreview] = useState<NovelPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [selectedVolumeIdx, setSelectedVolumeIdx] = useState<number | -1>(-1)
  // Token de cancelamento da request mais recente — evita race condition se o user
  // edita a URL enquanto uma chamada (auto ou manual) ainda está no ar.
  const previewReqRef = useRef(0)

  async function runPreview(rawUrl: string): Promise<void> {
    const trimmed = rawUrl.trim()
    if (!trimmed || !trimmed.startsWith('http')) return
    const token = ++previewReqRef.current
    setPreviewLoading(true)
    setPreviewErr(null)
    try {
      const data = await api.previewNovel(trimmed)
      if (token === previewReqRef.current) setPreview(data)
    } catch (err) {
      if (token === previewReqRef.current) {
        setPreviewErr(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (token === previewReqRef.current) setPreviewLoading(false)
    }
  }

  // Reseta preview a cada mudança de URL e dispara auto-preview SÓ se o host
  // suporta volumes. O ++previewReqRef invalida requests in-flight de URLs antigas.
  useEffect(() => {
    setPreview(null)
    setPreviewErr(null)
    setSelectedVolumeIdx(-1)
    previewReqRef.current++
    if (!sourceHasVolumes) return
    const trimmed = url.trim()
    if (!trimmed || !trimmed.startsWith('http')) return
    const t = setTimeout(() => {
      void runPreview(trimmed)
    }, 800)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, sourceHasVolumes])

  // Auto-desliga tradução quando fonte é PT-BR
  useEffect(() => {
    if (sourceIsPtNative && translate) {
      setTranslate(false)
    }
  }, [sourceIsPtNative, translate])

  // Quando user seleciona um volume, auto-preenche start/end/volume_title
  function selectVolume(idx: number): void {
    setSelectedVolumeIdx(idx)
    if (idx === -1 || !preview) return
    const v = preview.volumes[idx]
    setStart(String(v.start))
    setEnd(String(v.end))
    setVolumeTitle(v.name)
  }

  async function onSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await api.createDownload({
        url: url.trim(),
        start: Number(start) || 1,
        end: end ? Number(end) : null,
        with_cover: withCover,
        translate_to: translate ? 'pt-BR' : null,
        volume_title: volumeTitle.trim() || null,
        ai_cover: aiCover
      })
      setJobId(res.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-10">
      <header className="space-y-3">
        <Folio n="i" />
        <h2 className="font-display text-[2.5rem] leading-none font-medium tracking-tight">
          Nova captura
        </h2>
        <p className="font-sans max-w-md text-[15px] leading-relaxed text-[var(--ink-500)]">
          Cole a URL de uma novel, escolha o intervalo de capítulos, e deixe a alquimia transformar
          em <em className="font-display italic text-[var(--ink-700)]">livro de verdade</em>.
        </p>
      </header>

      <Card>
        <form onSubmit={onSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="url">URL da novel</Label>
            <Input
              id="url"
              placeholder="https://novelbin.me/novel-book/... ou https://novelmania.com.br/novels/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            {previewLoading && (
              <div className="font-sans flex items-center gap-2 pt-1 text-[12px] text-[var(--ink-500)]">
                <Loader2 className="size-3.5 animate-spin" /> Lendo página da novel…
              </div>
            )}
            {/* Sites sem volumes nativos: nao disparamos preview automatico
                (poupa um request lento que so renderiza titulo/capa decorativos).
                Mostra um link opt-in pra quem quiser ver a previa. */}
            {!sourceHasVolumes && !preview && !previewLoading && url.trim().startsWith('http') && (
              <button
                type="button"
                onClick={() => void runPreview(url)}
                className="font-sans inline-flex items-center gap-1.5 pt-1 text-[12px] text-[var(--ink-500)] underline decoration-[var(--ink-300)] underline-offset-4 transition-colors hover:text-[var(--stamp-red)] hover:decoration-[var(--stamp-red)]"
              >
                <Eye className="size-3.5" /> Pré-visualizar (opcional)
              </button>
            )}
            {previewErr && (
              <div className="font-sans pt-1 text-[12px] text-[var(--ink-stamp)]">{previewErr}</div>
            )}
            {preview && (
              <div
                className={[
                  'mt-3 flex gap-4 rounded-xl border bg-[var(--paper-50)] p-3',
                  'border-[var(--border-soft)]'
                ].join(' ')}
              >
                {preview.cover_url ? (
                  <img
                    src={preview.cover_url}
                    alt=""
                    className="size-16 shrink-0 rounded object-cover shadow-sm"
                  />
                ) : (
                  <div className="size-16 shrink-0 rounded bg-[var(--paper-300)]" />
                )}
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="font-display truncate text-[15px] font-medium tracking-tight">
                    {preview.title}
                  </div>
                  <div className="font-sans text-[11px] tracking-wide text-[var(--ink-500)]">
                    {preview.author ?? 'autor desconhecido'} ·{' '}
                    <strong>{preview.total_chapters}</strong> caps
                    {preview.volumes.length > 0 && (
                      <>
                        {' '}
                        · <strong>{preview.volumes.length}</strong> volumes detectados
                      </>
                    )}
                  </div>
                  {preview.volumes.length > 0 && (
                    <div className="pt-1.5">
                      <select
                        value={selectedVolumeIdx}
                        onChange={(e) => selectVolume(Number(e.target.value))}
                        className={[
                          'font-sans w-full rounded-md border bg-[var(--paper-100)] px-2 py-1.5 text-[12px]',
                          'border-[var(--border-soft)] focus:border-[var(--stamp-red)] focus:outline-none'
                        ].join(' ')}
                      >
                        <option value={-1}>— Selecione um volume pra auto-preencher —</option>
                        {preview.volumes.map((v, i) => (
                          <option key={i} value={i}>
                            {v.name} (caps {v.start}–{v.end}, {v.chapter_count})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="volume-title">
              Título do volume
              <span className="font-sans ml-1 text-[10px] tracking-[0.18em] text-[var(--ink-400)]">
                opcional
              </span>
            </Label>
            <Input
              id="volume-title"
              placeholder="ex: Volume 1 — O Sistema Vampírico"
              value={volumeTitle}
              onChange={(e) => setVolumeTitle(e.target.value)}
            />
            <p className="font-sans text-[11px] leading-relaxed text-[var(--ink-400)]">
              Se preenchido, vira o título do EPUB e o nome do arquivo. A novel original fica como
              série (Kindle agrupa).
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="start">Início</Label>
              <Input
                id="start"
                type="number"
                min={1}
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end">Fim</Label>
              <Input
                id="end"
                type="number"
                min={1}
                placeholder="até o último"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-3 border-t border-[var(--border-soft)] pt-5">
            <label className="font-sans flex cursor-pointer items-center gap-3 text-[14px] text-[var(--ink-700)]">
              <Checkbox checked={withCover} onCheckedChange={(v) => setWithCover(v === true)} />
              Incluir capa
            </label>
            <label
              className={[
                'font-sans flex items-start gap-3 text-[14px]',
                sourceIsPtNative
                  ? 'cursor-not-allowed text-[var(--ink-400)]'
                  : 'cursor-pointer text-[var(--ink-700)]'
              ].join(' ')}
            >
              <Checkbox
                className="mt-0.5"
                checked={translate}
                disabled={sourceIsPtNative}
                onCheckedChange={(v) => setTranslate(v === true)}
              />
              <div className="flex flex-col">
                <span className="inline-flex items-center gap-1.5">
                  <Languages className="size-4 text-[var(--stamp-red)]" />
                  Traduzir para PT-BR <span className="text-[var(--ink-400)]">(cascade IA)</span>
                </span>
                {sourceIsPtNative && (
                  <span className="font-sans text-[11px] leading-relaxed text-[var(--book-3)]">
                    ✓ Fonte já é PT-BR nativa — tradução desnecessária (R$ 0).
                  </span>
                )}
              </div>
            </label>
            <label className="font-sans flex cursor-pointer items-start gap-3 text-[14px] text-[var(--ink-700)]">
              <Checkbox
                className="mt-0.5"
                checked={aiCover}
                onCheckedChange={(v) => setAiCover(v === true)}
              />
              <div className="flex flex-col">
                <span className="inline-flex items-center gap-1.5">
                  <Sparkles className="size-4 text-[var(--book-5)]" />
                  Gerar capa com IA <span className="text-[var(--ink-400)]">(Gemini Image)</span>
                </span>
                <span className="font-sans text-[11px] leading-relaxed text-[var(--ink-400)]">
                  Lê o glossário + amostras dos capítulos pra criar uma capa que reflete o arco do
                  volume.
                </span>
              </div>
            </label>
          </div>

          {error && (
            <p className="font-sans flex items-center gap-2 text-sm text-[var(--ink-stamp)]">
              <CircleAlert className="size-4" />
              {error}
            </p>
          )}

          <Button
            type="submit"
            variant="rainbow"
            size="lg"
            disabled={submitting || !url.trim()}
            className="w-full"
          >
            {submitting ? (
              <>
                <Loader2 className="size-5 animate-spin" />
                Enviando...
              </>
            ) : (
              <>
                <Download className="size-5" />
                Baixar e gerar EPUB
              </>
            )}
          </Button>
        </form>
      </Card>

      {job && (
        <Card>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <h3 className="font-display flex items-center gap-2 text-lg font-medium">
                {job.status === 'done' && <CircleCheck className="size-5 text-[var(--book-3)]" />}
                {job.status === 'error' && (
                  <CircleAlert className="size-5 text-[var(--ink-stamp)]" />
                )}
                {job.title ?? 'Processando...'}
              </h3>
              <p className="font-sans text-sm text-[var(--ink-500)]">{statusLabel(job)}</p>
            </div>
            <span className="font-display text-2xl italic text-[var(--ink-400)]">
              {pct}
              <span className="text-base">%</span>
            </span>
          </div>
          <Progress value={pct} rainbow />
          <div className="font-sans flex items-center justify-between text-[12px] text-[var(--ink-500)]">
            <span className="truncate">{job.current ?? '—'}</span>
            <span className="folio shrink-0 pl-3 text-[var(--ink-400)]">
              {job.done}/{job.total || '?'}
            </span>
          </div>
        </Card>
      )}
    </div>
  )
}
