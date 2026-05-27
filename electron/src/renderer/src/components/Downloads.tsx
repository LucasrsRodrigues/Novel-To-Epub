import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock,
  Download,
  ImageIcon,
  Loader2,
  RefreshCw,
  Send,
  X
} from 'lucide-react'
import { api, type JobStatus, type TranslationFailure } from '@renderer/lib/api'
import { useJobs } from '@renderer/context/JobsContext'
import { cn } from '@renderer/lib/utils'
import { Button } from '@renderer/components/ui/button'
import { Progress } from '@renderer/components/ui/progress'
import { Folio } from '@renderer/components/decorative/Folio'
import { Ribbon } from '@renderer/components/decorative/Ribbon'

const SPINE_COLORS = [
  'var(--book-1)',
  'var(--book-2)',
  'var(--book-3)',
  'var(--book-4)',
  'var(--book-5)',
  'var(--book-6)'
]

function StatusIcon({ status }: { status: JobStatus['status'] }): React.JSX.Element | null {
  switch (status) {
    case 'queued':
      return <Clock className="size-4 text-[var(--ink-400)]" />
    case 'running':
      return <Loader2 className="size-4 animate-spin text-[var(--stamp-red)]" />
    case 'done':
      return <CircleCheck className="size-4 text-[var(--book-3)]" />
    case 'error':
      return <CircleAlert className="size-4 text-[var(--ink-stamp)]" />
    case 'cancelled':
      return <X className="size-4 text-[var(--ink-400)]" />
  }
}

function statusLabel(job: JobStatus): string {
  switch (job.status) {
    case 'queued':
      return 'na fila'
    case 'running':
      if (job.stage === 'meta') return 'buscando lista de capítulos'
      if (job.stage === 'translate') return 'traduzindo'
      if (job.stage === 'cover') return 'gerando capa com IA'
      return 'baixando'
    case 'done': {
      const parts: string[] = ['concluído']
      if (job.translate_to) parts.push(job.translate_to)
      if (job.translation_failed > 0)
        parts.push(`${job.translation_failed} caps em EN (falha)`)
      return parts.join(' · ')
    }
    case 'error':
      return `erro · ${job.error ?? 'desconhecido'}`
    case 'cancelled':
      return 'cancelado'
  }
}

/** Categoriza a `reason` da falha numa label curta + dica de ação. Heuristica
 *  por keywords na mensagem da exception do Gemini (finish_reason/block_reason). */
function classifyFailure(reason: string): { kind: string; hint: string } {
  const r = reason.toLowerCase()
  if (r.includes('safety') || r.includes('block_reason') && !r.includes('block_reason=none')) {
    return {
      kind: 'Bloqueado por filtro de conteúdo (hard guardrail)',
      hint: 'Os safety filters configuráveis já estão em BLOCK_NONE — o que sobrou é guardrail interno do Gemini (raro). Costuma envolver menor de idade em contexto sexual. Tente outro modelo (Pro) ou traduza esse cap manualmente.'
    }
  }
  if (r.includes('max_tokens') || r.includes('finish_reason=2')) {
    return {
      kind: 'Resposta truncada (capítulo muito longo)',
      hint: 'O JSON foi cortado no meio. Continuar pode funcionar se for transiente; senão, capítulo precisa de divisão.'
    }
  }
  if (r.includes('unavailable') || r.includes('503') || r.includes('high demand') || r.includes('overload')) {
    return {
      kind: 'Gemini sobrecarregado (503 UNAVAILABLE)',
      hint: 'API do Gemini com pico de demanda. O retry automático já tentou 5x com backoff exponencial (até 60s entre tentativas). Aguarde uns minutos e clique Continuar tradução.'
    }
  }
  if (r.includes('rate') || r.includes('quota') || r.includes('429') || r.includes('resource_exhausted') || r.includes('tokens per minute')) {
    return {
      kind: 'Rate limit / quota (429)',
      hint: 'Provider bateu limite por minuto/dia. Cascade respeita Retry-After do header — clique Continuar tradução em alguns segundos.'
    }
  }
  if (r.includes('cooldown') || r.includes('todos os providers em cooldown') || r.includes('próximo provider disponível')) {
    // Tenta extrair os "~Ns" da mensagem
    const m = r.match(/~?(\d+)s/)
    const eta = m ? `${m[1]}s` : 'menos de 90s'
    return {
      kind: `Cascade em cooldown — aguarde ${eta}`,
      hint: 'Todos os providers do cascade bateram rate-limit em sequência. Aguarde o ETA mostrado e clique Continuar tradução. Considere adicionar mais providers (OpenRouter, Cerebras) pra alternância.'
    }
  }
  if (r.includes('500') || r.includes('502') || r.includes('504') || r.includes('internal')) {
    return {
      kind: 'Erro interno do Gemini (5xx)',
      hint: 'Falha temporária no GCP. Retry automático já tentou. Aguarde e clique Continuar tradução.'
    }
  }
  if (r.includes('json') || r.includes('parsed') || r.includes('validation')) {
    return {
      kind: 'JSON inválido / schema',
      hint: 'Gemini devolveu algo que não bate com o schema. Retry costuma resolver.'
    }
  }
  return { kind: 'Erro desconhecido', hint: 'Veja o motivo cru abaixo.' }
}

function FailureDetails({ failures }: { failures: TranslationFailure[] }): React.JSX.Element {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="font-sans flex items-center gap-1 text-[12px] text-[var(--ink-500)] hover:text-[var(--ink-700)]"
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        {open ? 'Ocultar' : 'Ver'} motivo{failures.length === 1 ? '' : 's'} da falha
      </button>
      {open && (
        <ul className="mt-2 space-y-2">
          {failures.map((f) => {
            const cls = classifyFailure(f.reason)
            return (
              <li
                key={f.chapter}
                className="rounded-md border border-[var(--border-soft)] bg-[var(--paper-50)] px-3 py-2"
              >
                <div className="font-sans flex items-baseline gap-2 text-[12px]">
                  <span className="folio text-[var(--ink-400)]">cap {f.chapter}</span>
                  <span className="truncate italic text-[var(--ink-500)]">{f.title}</span>
                </div>
                <div className="font-sans mt-1 text-[12px] font-medium text-[var(--ink-stamp)]">
                  {cls.kind}
                </div>
                <div className="font-sans mt-0.5 text-[11px] leading-snug text-[var(--ink-500)]">
                  {cls.hint}
                </div>
                <details className="mt-1">
                  <summary className="font-sans cursor-pointer text-[11px] text-[var(--ink-400)] hover:text-[var(--ink-500)]">
                    mensagem crua
                  </summary>
                  <pre className="font-mono mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-snug text-[var(--ink-700)]">
                    {f.reason}
                  </pre>
                </details>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function JobCard({
  job,
  spineColor,
  index
}: {
  job: JobStatus
  spineColor: string
  index: number
}): React.JSX.Element {
  const [sending, setSending] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [regeneratingCover, setRegeneratingCover] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0
  const hasTranslationFailures = job.status === 'done' && job.translation_failed > 0
  const canRegenerateCover = job.status === 'done' && job.ai_cover
  const canCancel = job.status === 'queued' || job.status === 'running'
  // Durante 'meta' o `total` ainda e 0 — barra rainbow indeterminada ajuda o
  // user a ver que esta progredindo (especialmente pra adapters lentos como
  // NovelFull que paginam ~60 vezes a TOC antes de ter o total).
  const indeterminate = job.status === 'running' && job.total === 0

  async function sendKindle(): Promise<void> {
    setSending(true)
    setSendMsg(null)
    try {
      const res = await api.sendToKindle(job.id)
      setSendMsg({ ok: true, text: `enviado para ${res.to}` })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSending(false)
    }
  }

  async function regenerateCover(): Promise<void> {
    setRegeneratingCover(true)
    setSendMsg(null)
    try {
      // Preferencial: endpoint baseado em volume_id (persistido em SQLite,
      // sobrevive a restart). Fallback pro endpoint baseado em job_id pra
      // jobs gerados em versao antiga do backend (sem volume_id propagado).
      if (job.volume_id != null) {
        await api.regenerateVolumeCover(job.volume_id)
      } else {
        await api.regenerateCover(job.id)
      }
      setSendMsg({ ok: true, text: 'novo job criado — capa será regerada (~R$0,20)' })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRegeneratingCover(false)
    }
  }

  async function cancelJob(): Promise<void> {
    setCancelling(true)
    setSendMsg(null)
    try {
      await api.cancelDownload(job.id)
      // O WS publica o evento 'cancelled' — UI atualiza via JobsContext.
      // Nao precisamos setar estado local; o badge muda sozinho.
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setCancelling(false)
    }
  }

  async function retryTranslation(): Promise<void> {
    setRetrying(true)
    setSendMsg(null)
    try {
      // Re-submete os mesmos params. Cache pula os caps ja traduzidos com sucesso;
      // só os que falharam batem o Gemini de novo.
      await api.createDownload({
        url: job.url,
        start: job.start,
        end: job.end,
        with_cover: job.with_cover,
        translate_to: job.translate_to,
        volume_title: job.volume_title,
        ai_cover: job.ai_cover
      })
      setSendMsg({
        ok: true,
        text: `novo job criado — ${job.translation_failed} caps serão retentados`
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRetrying(false)
    }
  }

  return (
    <article
      className={[
        'relative overflow-hidden rounded-2xl border bg-[var(--paper-100)] pl-6 pr-6 py-5',
        'border-[var(--border-soft)]',
        'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_1px_3px_rgba(80,50,20,0.05),0_14px_28px_-18px_rgba(80,50,20,0.20)]'
      ].join(' ')}
    >
      {/* book spine on the left edge */}
      <span
        className="absolute left-0 top-0 bottom-0 w-[5px]"
        style={{ backgroundColor: spineColor }}
      />

      {/* hanging ribbon for completed jobs */}
      {job.status === 'done' && (
        <Ribbon
          color="var(--bookmark-ribbon)"
          width={14}
          height={26}
          className="absolute -top-1 right-6"
        />
      )}

      <div className="space-y-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="folio mb-1 text-[var(--ink-400)]">№ {String(index).padStart(3, '0')}</div>
            <h3 className="font-display truncate text-lg leading-tight font-medium tracking-tight">
              {job.volume_title ?? job.title ?? job.url}
            </h3>
            {job.volume_title && job.title && (
              <p className="font-display mt-0.5 truncate text-[13px] italic text-[var(--ink-500)]">
                de {job.title}
              </p>
            )}
            <p className="font-sans mt-1 flex items-center gap-1.5 text-[12px] tracking-wide uppercase text-[var(--ink-500)]">
              <StatusIcon status={job.status} />
              {statusLabel(job)}
            </p>
          </div>
          <span className="font-display text-[28px] leading-none italic text-[var(--ink-400)]">
            {pct}<span className="text-sm">%</span>
          </span>
        </div>

        <Progress
          value={indeterminate ? 100 : pct}
          rainbow={
            indeterminate || (job.translate_to !== null && job.stage === 'translate')
          }
        />

        <div className="font-sans flex items-center justify-between text-[12px] text-[var(--ink-500)]">
          <span className="truncate italic">{job.current ?? '—'}</span>
          <span className="folio shrink-0 pl-2 text-[var(--ink-400)]">
            {job.done}/{job.total || '?'}
          </span>
        </div>

        {canCancel && (
          <div className="flex items-center gap-2 pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={cancelJob}
              disabled={cancelling}
            >
              {cancelling ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <X className="size-3.5" />
              )}
              Cancelar
            </Button>
            {sendMsg && !sendMsg.ok && (
              <span className="font-sans text-[12px] text-[var(--ink-stamp)]">
                {sendMsg.text}
              </span>
            )}
          </div>
        )}

        {job.status === 'done' && (
          <>
            {hasTranslationFailures && (
              <div
                className={[
                  'rounded-lg border px-3 py-2 mt-1',
                  'border-[var(--ink-stamp)]/40'
                ].join(' ')}
                style={{ backgroundColor: 'rgba(149,40,31,0.08)' }}
              >
                <div className="flex items-center gap-2.5">
                  <CircleAlert className="size-4 shrink-0 text-[var(--ink-stamp)]" />
                  <span className="font-sans flex-1 text-[12px] leading-snug text-[var(--ink-700)]">
                    <strong className="font-semibold">{job.translation_failed} capítulo
                    {job.translation_failed === 1 ? '' : 's'}</strong> ficaram em inglês (falha na
                    tradução). Os já traduzidos estão em cache — continuar não gasta tokens neles.
                  </span>
                </div>
                {job.translation_failures && job.translation_failures.length > 0 && (
                  <FailureDetails failures={job.translation_failures} />
                )}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {hasTranslationFailures && (
                <Button size="sm" onClick={retryTranslation} disabled={retrying}>
                  {retrying ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3.5" />
                  )}
                  Continuar tradução
                </Button>
              )}
              <Button asChild variant={hasTranslationFailures ? 'outline' : 'outline'} size="sm">
                <a href={api.fileUrl(job.id)} download>
                  <Download className="size-3.5" /> Baixar .epub
                </a>
              </Button>
              {canRegenerateCover && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={regenerateCover}
                  disabled={regeneratingCover}
                >
                  {regeneratingCover ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <ImageIcon className="size-3.5" />
                  )}
                  Regerar capa
                </Button>
              )}
              <Button
                variant={hasTranslationFailures ? 'outline' : 'default'}
                size="sm"
                onClick={sendKindle}
                disabled={sending}
              >
                {sending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Send className="size-3.5" />
                )}
                Enviar pro Kindle
              </Button>
              {sendMsg && (
                <span
                  className={cn(
                    'font-sans text-[12px]',
                    sendMsg.ok ? 'text-[var(--book-3)]' : 'text-[var(--ink-stamp)]'
                  )}
                >
                  {sendMsg.text}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </article>
  )
}

export function Downloads(): React.JSX.Element {
  const { jobs } = useJobs()
  const list = Object.values(jobs).sort((a, b) => b.created_at.localeCompare(a.created_at))

  if (list.length === 0) {
    return (
      <div className="space-y-10">
        <header className="space-y-3">
          <Folio n="iii" />
          <h2 className="font-display text-[2.5rem] leading-none font-medium tracking-tight">
            Downloads
          </h2>
          <p className="font-sans max-w-md text-[15px] leading-relaxed text-[var(--ink-500)]">
            A fila de capturas em andamento — acompanhe progresso ao vivo via WebSocket.
          </p>
        </header>
        <div className="py-16 text-center">
          <p className="font-display text-xl italic text-[var(--ink-400)]">
            Nenhum download ainda.
          </p>
          <p className="font-sans mt-2 text-sm text-[var(--ink-500)]">
            Crie um em <em className="font-display italic">Nova captura</em>.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      <header className="space-y-3">
        <Folio n="iii" />
        <h2 className="font-display text-[2.5rem] leading-none font-medium tracking-tight">
          Downloads
        </h2>
        <p className="font-sans text-[15px] leading-relaxed text-[var(--ink-500)]">
          {list.length} captura{list.length === 1 ? '' : 's'} na fila.
        </p>
      </header>
      <div className="space-y-4">
        {list.map((job, idx) => (
          <JobCard
            key={job.id}
            job={job}
            spineColor={SPINE_COLORS[idx % SPINE_COLORS.length]}
            index={list.length - idx}
          />
        ))}
      </div>
    </div>
  )
}
