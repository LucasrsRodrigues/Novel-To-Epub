import { useState } from 'react'
import { Eraser, Loader2 } from 'lucide-react'
import { api, type GlossaryCleanupReport } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'

/**
 * "Limpar glossário": junta duplicatas ("Reflection"/"Reflections") e tira do
 * prompt palavras comuns que a IA cadastrou como nome ("Time", "Body") e lixo.
 * Primeiro mostra a prévia (nada muda); só aplica depois de confirmar.
 * Personagens e entradas manuais/da wiki nunca são ignorados.
 */
export function GlossaryCleanup({
  novelId,
  onApplied
}: {
  novelId: number
  onApplied: () => void
}): React.JSX.Element {
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<GlossaryCleanupReport | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  async function run(apply: boolean): Promise<void> {
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.cleanGlossary(novelId, apply)
      if (!apply) {
        const nothing = r.duplicates_removed + r.common_words_ignored + r.junk_ignored === 0
        if (nothing) setMsg({ ok: true, text: 'glossário já está limpo' })
        else setPreview(r)
        return
      }
      setPreview(null)
      setMsg({
        ok: true,
        text: `limpo: ${r.total} → ${r.remaining_active} termos ativos`
      })
      onApplied()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" disabled={busy} onClick={() => run(false)}>
          {busy && !preview ? <Loader2 className="animate-spin" /> : <Eraser />}
          Limpar glossário
        </Button>
        {msg && (
          <span
            className={`font-sans text-[12px] ${msg.ok ? 'text-[var(--ink-500)]' : 'text-[var(--ink-stamp)]'}`}
          >
            {msg.text}
          </span>
        )}
      </div>

      {preview && (
        <div className="space-y-3 rounded-xl border border-[var(--border-medium)] bg-[var(--paper-100)] p-4">
          <p className="font-sans text-[13px] leading-relaxed text-[var(--ink-700)]">
            De <strong>{preview.total}</strong> termos, ficam{' '}
            <strong>{preview.remaining_active}</strong> ativos: {preview.duplicates_removed}{' '}
            duplicatas juntadas, {preview.common_words_ignored} palavras comuns e{' '}
            {preview.junk_ignored} sem sentido saem do prompt. Personagens e entradas manuais/da
            wiki não são tocados.
          </p>
          {preview.common_words.length > 0 && (
            <div className="space-y-1.5">
              <p className="font-sans text-[11px] tracking-[0.14em] uppercase text-[var(--ink-400)]">
                Palavras comuns (passam a ser traduzidas normalmente)
              </p>
              <p className="font-sans text-[12px] leading-relaxed text-[var(--ink-600)]">
                {preview.common_words.slice(0, 60).join(', ')}
                {preview.common_words.length > 60 && ` … +${preview.common_words.length - 60}`}
              </p>
            </div>
          )}
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => run(true)}>
              {busy && <Loader2 className="animate-spin" />}
              Aplicar limpeza
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => setPreview(null)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
