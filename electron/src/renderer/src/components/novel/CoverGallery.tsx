import { useEffect, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import { api, type CoverOut } from '@renderer/lib/api'
import { formatStyleSpec } from '@renderer/lib/coverStyles'
import { CoverModal } from '@renderer/components/novel/CoverModal'
import { CoverThumb } from '@renderer/components/novel/CoverThumb'
// Galeria das capas geradas por IA da novel — preview + download da arte em
// vários formatos (com/sem texto, wallpapers). Re-busca quando um job termina.
export function CoverGallery({
  novelId,
  doneJobsKey,
  defaultStyle
}: {
  novelId: number
  doneJobsKey: string
  defaultStyle: string | null
}): React.JSX.Element | null {
  const [covers, setCovers] = useState<CoverOut[]>([])
  const [loaded, setLoaded] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)
  const [regenAll, setRegenAll] = useState(false)
  const [allMsg, setAllMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    let active = true
    api
      .listCovers(novelId)
      .then((c) => active && setCovers(c))
      .catch(() => active && setCovers([]))
      .finally(() => active && setLoaded(true))
    return () => {
      active = false
    }
  }, [novelId, doneJobsKey])

  if (!loaded || covers.length === 0) return null

  const selected = covers.find((c) => c.id === selectedId) ?? null
  const styleLabel = formatStyleSpec(defaultStyle)
  const cost = (covers.length * 0.2).toFixed(2).replace('.', ',')

  async function regenerateAll(): Promise<void> {
    setRegenAll(true)
    setAllMsg(null)
    try {
      const jobs = await api.regenerateAllCovers(novelId)
      setConfirmAll(false)
      setAllMsg({
        ok: true,
        text: `${jobs.length} capas na fila — acompanhe em Downloads; vão se realinhar ao terminar`
      })
    } catch (err) {
      setAllMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRegenAll(false)
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
          Galeria de capas
          <span className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
            clique pra baixar
          </span>
        </h3>
        {!confirmAll ? (
          <button
            type="button"
            onClick={() => {
              setAllMsg(null)
              setConfirmAll(true)
            }}
            className="font-sans inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-soft)] bg-[var(--paper-100)] px-2.5 py-1 text-[11px] text-[var(--ink-700)] transition-colors hover:border-[var(--stamp-red)] hover:text-[var(--stamp-red)]"
          >
            <RefreshCw className="size-3" /> Regerar todas
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-sans text-[11px] text-[var(--ink-500)]">
              {covers.length} capas{styleLabel ? ` · ${styleLabel}` : ' · automático'} · ~R${cost}?
            </span>
            <button
              type="button"
              onClick={regenerateAll}
              disabled={regenAll}
              className="font-sans inline-flex items-center gap-1 rounded-lg bg-[var(--stamp-red)] px-2.5 py-1 text-[11px] text-[var(--paper-50)] disabled:opacity-50"
            >
              {regenAll ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <RefreshCw className="size-3" />
              )}
              Confirmar
            </button>
            <button
              type="button"
              onClick={() => setConfirmAll(false)}
              disabled={regenAll}
              className="font-sans rounded-lg px-2 py-1 text-[11px] text-[var(--ink-500)] hover:text-[var(--ink-900)]"
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
      {allMsg && (
        <p
          className={
            allMsg.ok
              ? 'font-sans text-[12px] text-[var(--book-3)]'
              : 'font-sans text-[12px] text-[var(--ink-stamp)]'
          }
        >
          {allMsg.text}
        </p>
      )}
      {!styleLabel && (
        <p className="font-sans text-[11px] text-[var(--ink-400)]">
          Sem estilo travado: as capas podem sair com estilos diferentes. Escolha um estilo (no
          dropdown “Regerar capa” de um volume) antes, pra coleção ficar consistente.
        </p>
      )}
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
