import { useState } from 'react'
import { Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { api, type JobStatus } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'

export function ActiveJobRow({ job }: { job: JobStatus }): React.JSX.Element {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0
  const [resuming, setResuming] = useState(false)
  const [discarding, setDiscarding] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  // Captura pendente (cancelada, com erro, ou interrompida por restart) pode ser
  // retomada: o cache pula o que já foi baixado/traduzido, só falta o resto.
  const resumable =
    job.status === 'cancelled' || job.status === 'error' || job.status === 'interrupted'

  const label =
    job.status === 'error'
      ? 'erro'
      : job.status === 'cancelled'
        ? 'cancelado'
        : job.status === 'interrupted'
          ? 'interrompido'
          : job.status === 'queued'
            ? 'na fila'
            : 'em andamento'

  async function resume(): Promise<void> {
    setResuming(true)
    setErr(null)
    try {
      // Re-roda o MESMO job no backend (preserva cover_style/skip_chapters etc).
      // O JobsContext atualiza a linha via WS — sai de 'cancelado' p/ 'na fila'.
      await api.resumeDownload(job.id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'falha ao continuar')
    } finally {
      setResuming(false)
    }
  }

  async function discard(): Promise<void> {
    setDiscarding(true)
    setErr(null)
    try {
      // Remove a captura pendente + intenção persistida. Não toca no cache.
      await api.discardDownload(job.id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'falha ao descartar')
      setDiscarding(false)
    }
  }

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
        {err && <div className="font-sans mt-1 text-[11px] text-[var(--ink-stamp)]">{err}</div>}
      </div>
      {resumable && (
        <>
          <Button variant="outline" size="sm" onClick={resume} disabled={resuming || discarding}>
            {resuming ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            Continuar captura
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={discard}
            disabled={resuming || discarding}
            aria-label="descartar captura"
          >
            {discarding ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Trash2 className="size-3.5" />
            )}
          </Button>
        </>
      )}
      <span
        className={[
          'font-sans text-[10px] tracking-[0.18em] uppercase',
          resumable ? 'text-[var(--ink-stamp)]' : 'text-[var(--ink-400)]'
        ].join(' ')}
      >
        {label}
      </span>
    </li>
  )
}
