import { useEffect, useState } from 'react'
import { Activity, Check, Loader2, Trash2, X } from 'lucide-react'
import { api, type TranslationDebugStatus, type VolumePinInfo } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'

/**
 * Modal de diagnóstico: mostra estado do cascade pra usuário entender por que
 * tradução tá indo (ou não) pra cada provider. Resolve o caso "configurei Groq
 * mas só vai pro Gemini" — geralmente é pin gravado errado num volume.
 */
export function TranslationDiagnostic({ onClose }: { onClose: () => void }): React.JSX.Element {
  const [status, setStatus] = useState<TranslationDebugStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [clearingPin, setClearingPin] = useState<string | null>(null)

  function load(): void {
    setLoading(true)
    api
      .translationDebugStatus()
      .then(setStatus)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function clearPin(pin: VolumePinInfo): Promise<void> {
    // pin não tem volume_id direto — precisa achar via lookup. Pra simplificar,
    // forçamos resync via re-fetch (backend route apaga por volume_id, mas
    // aqui usuário pode preferir deletar via outro caminho... vou expor por
    // novel_id+volume_title se necessario futuro). Por enquanto, usa lookup
    // via API de volumes da novel.
    const key = `${pin.novel_id}:${pin.volume_title ?? ''}`
    setClearingPin(key)

    try {
      const vols = await api.getNovelVolumes(pin.novel_id)
      const target = vols.find((v) => (v.volume_title ?? '') === (pin.volume_title ?? ''))
      if (!target) throw new Error('volume correspondente não encontrado')
      await api.resetVolumeTranslatorPin(target.id)
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setClearingPin(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
      <div
        className={[
          'flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl',
          'border border-[var(--border-soft)] bg-[var(--paper-50)]',
          'shadow-2xl'
        ].join(' ')}
      >
        {/* Header */}
        <header className="flex items-center gap-3 border-b border-[var(--border-soft)] bg-[var(--paper-100)] px-6 py-3">
          <Activity className="size-4 text-[var(--stamp-red)]" />
          <h2 className="font-display flex-1 text-[18px] font-medium tracking-tight">
            Diagnóstico de tradução
          </h2>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : 'Atualizar'}
          </Button>
          <Button variant="outline" size="sm" onClick={onClose}>
            <X className="size-3.5" />
          </Button>
        </header>

        {err && (
          <div className="font-sans border-b border-[var(--ink-stamp)]/30 bg-[var(--ink-stamp)]/8 px-6 py-2 text-[12px] text-[var(--ink-stamp)]">
            {err}
          </div>
        )}

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {!status ? (
            <div className="flex items-center gap-2 text-[var(--ink-400)]">
              <Loader2 className="size-4 animate-spin" /> Carregando…
            </div>
          ) : (
            <>
              {/* Providers ativos vs inativos */}
              <section className="space-y-2">
                <h3 className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-500)]">
                  Providers configurados
                </h3>
                <div className="flex flex-wrap gap-2">
                  {status.active_providers.map((p) => (
                    <span
                      key={p}
                      className="font-sans inline-flex items-center gap-1.5 rounded-full bg-[var(--book-3)]/15 px-3 py-1 text-[12px] text-[var(--book-3)]"
                    >
                      <Check className="size-3" /> {p}
                    </span>
                  ))}
                  {status.inactive_providers.map((p) => (
                    <span
                      key={p}
                      className="font-sans inline-flex items-center gap-1.5 rounded-full bg-[var(--paper-300)] px-3 py-1 text-[12px] text-[var(--ink-400)]"
                    >
                      <X className="size-3" /> {p}
                    </span>
                  ))}
                </div>
              </section>

              {/* Ordem */}
              <section className="space-y-2">
                <h3 className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-500)]">
                  Ordem do cascade
                </h3>
                <ol className="font-sans flex flex-wrap items-center gap-2 text-[13px]">
                  {status.cascade_order.map((p, i) => (
                    <li key={p} className="flex items-center gap-2">
                      <span className="folio text-[var(--ink-400)]">{i + 1}.</span>
                      <span
                        className={
                          status.active_providers.includes(p)
                            ? 'text-[var(--ink-900)]'
                            : 'text-[var(--ink-400)] line-through'
                        }
                      >
                        {p}
                      </span>
                      {i < status.cascade_order.length - 1 && (
                        <span className="text-[var(--ink-300)]">→</span>
                      )}
                    </li>
                  ))}
                </ol>
              </section>

              {/* Pins */}
              <section className="space-y-2">
                <h3 className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-500)]">
                  Volumes pinados ({status.pins.length})
                </h3>
                {status.pins.length === 0 ? (
                  <p className="font-sans text-[12px] text-[var(--ink-500)]">
                    Nenhum volume pinado ainda. Próxima tradução vai rodar cascade do zero.
                  </p>
                ) : (
                  <p className="font-sans text-[12px] text-[var(--ink-500)]">
                    Esses volumes ficam <em>presos</em> no provider abaixo. Pra forçar o cascade a
                    usar outro provider (ex: Groq após adicionar a key), resete o pin.
                  </p>
                )}
                <ul className="space-y-1.5">
                  {status.pins.map((pin) => {
                    const key = `${pin.novel_id}:${pin.volume_title ?? ''}`
                    const isClearing = clearingPin === key
                    return (
                      <li
                        key={key}
                        className="flex items-center gap-3 rounded-lg border border-[var(--border-soft)] bg-[var(--paper-100)] px-3 py-2"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="font-sans truncate text-[13px]">
                            <span className="font-medium">{pin.novel_title}</span>
                            <span className="text-[var(--ink-500)]">
                              {' '}
                              · {pin.volume_title ?? '(sem título)'}
                            </span>
                          </div>
                          <div className="font-sans text-[11px] text-[var(--ink-500)]">
                            pinado em <strong>{pin.provider}</strong> / {pin.model}
                          </div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={isClearing}
                          onClick={() => clearPin(pin)}
                        >
                          {isClearing ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="size-3.5" />
                          )}
                          Resetar
                        </Button>
                      </li>
                    )
                  })}
                </ul>
              </section>

              {/* Últimas chamadas — o smoking gun */}
              <section className="space-y-2">
                <h3 className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-500)]">
                  Últimas {status.recent_usage.length} chamadas
                </h3>
                {status.recent_usage.length === 0 ? (
                  <p className="font-sans text-[12px] text-[var(--ink-500)]">
                    Nenhuma chamada registrada.
                  </p>
                ) : (
                  <>
                    {/* Resumo: contagem de falhas — chama atenção */}
                    {(() => {
                      const failures = status.recent_usage.filter((u) => u.error_message)
                      if (failures.length === 0) return null
                      const byProv: Record<string, number> = {}
                      failures.forEach((f) => {
                        const p = f.provider ?? '?'
                        byProv[p] = (byProv[p] || 0) + 1
                      })
                      return (
                        <div
                          className="font-sans rounded-lg border border-[var(--ink-stamp)]/40 bg-[var(--ink-stamp)]/8 px-3 py-2 text-[12px] text-[var(--ink-700)]"
                          style={{ backgroundColor: 'rgba(149,40,31,0.08)' }}
                        >
                          <strong>{failures.length}</strong> de {status.recent_usage.length}{' '}
                          {status.recent_usage.length === 1
                            ? 'chamada falhou'
                            : 'chamadas falharam'}{' '}
                          (
                          {Object.entries(byProv)
                            .map(([p, c]) => `${p}: ${c}`)
                            .join(', ')}
                          ). Veja a mensagem de erro de cada uma abaixo — é a chave pra entender por
                          que o cascade está caindo no Gemini.
                        </div>
                      )
                    })()}

                    <table className="font-sans w-full text-[12px]">
                      <thead>
                        <tr className="text-left text-[var(--ink-400)]">
                          <th className="py-1 font-normal tracking-wide uppercase text-[10px]">
                            quando
                          </th>
                          <th className="py-1 font-normal tracking-wide uppercase text-[10px]">
                            provider
                          </th>
                          <th className="py-1 font-normal tracking-wide uppercase text-[10px]">
                            cap
                          </th>
                          <th className="py-1 font-normal tracking-wide uppercase text-[10px]">
                            resultado
                          </th>
                          <th className="py-1 text-right font-normal tracking-wide uppercase text-[10px]">
                            $
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {status.recent_usage.map((u, i) => {
                          const failed = !!u.error_message
                          return (
                            <tr
                              key={i}
                              className={[
                                'border-t border-[var(--border-soft)]',
                                failed ? 'bg-[var(--ink-stamp)]/4' : ''
                              ].join(' ')}
                            >
                              <td className="py-1.5 align-top text-[var(--ink-500)]">
                                {new Date(u.created_at).toLocaleTimeString('pt-BR', {
                                  hour: '2-digit',
                                  minute: '2-digit'
                                })}
                              </td>
                              <td className="py-1.5 align-top">
                                <span
                                  className={[
                                    'rounded px-1.5 py-0.5 text-[10px]',
                                    u.provider === 'gemini'
                                      ? 'bg-[var(--book-7)]/15 text-[var(--book-7)]'
                                      : 'bg-[var(--book-3)]/15 text-[var(--book-3)]'
                                  ].join(' ')}
                                >
                                  {u.provider ?? '?'}
                                </span>
                                <div className="mt-0.5 text-[10px] text-[var(--ink-400)]">
                                  {u.model}
                                </div>
                              </td>
                              <td className="py-1.5 align-top text-[var(--ink-400)]">
                                {u.chapter_index ?? '—'}
                              </td>
                              <td className="py-1.5 align-top">
                                {failed ? (
                                  <div>
                                    <span className="font-sans inline-block rounded bg-[var(--ink-stamp)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[var(--ink-stamp)]">
                                      FALHA
                                    </span>
                                    <div
                                      className="font-mono mt-1 max-w-md break-words text-[10.5px] leading-snug text-[var(--ink-stamp)]"
                                      title={u.error_message ?? ''}
                                    >
                                      {u.error_message}
                                    </div>
                                  </div>
                                ) : (
                                  <span className="font-sans inline-block rounded bg-[var(--book-3)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[var(--book-3)]">
                                    OK
                                  </span>
                                )}
                              </td>
                              <td className="py-1.5 text-right align-top font-mono text-[var(--ink-700)]">
                                ${u.cost_usd.toFixed(4)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
