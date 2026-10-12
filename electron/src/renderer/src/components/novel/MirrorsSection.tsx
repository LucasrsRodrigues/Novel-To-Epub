import { useEffect, useState } from 'react'
import { Link2, Loader2, Plus, Trash2 } from 'lucide-react'
import { api, type Mirror } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'

/** Fontes alternativas (mirrors) da novel. Permite ligar outro site à MESMA
 *  obra (mesmo novel_id → cache/tradução/glossário/capa preservados). Quando o
 *  site primário falha num capítulo, o backend cai pra essas fontes casando
 *  pelo número do título. */
export function MirrorsSection({
  novelId,
  primarySource,
  primaryUrl
}: {
  novelId: number
  primarySource: string
  primaryUrl: string
}): React.JSX.Element {
  const [mirrors, setMirrors] = useState<Mirror[]>([])
  const [loaded, setLoaded] = useState(false)
  const [url, setUrl] = useState('')
  const [adding, setAdding] = useState(false)
  const [removingId, setRemovingId] = useState<number | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    let active = true
    api
      .listMirrors(novelId)
      .then((m) => active && setMirrors(m))
      .catch(() => {})
      .finally(() => active && setLoaded(true))
    return () => {
      active = false
    }
  }, [novelId])

  async function add(): Promise<void> {
    const u = url.trim()
    if (!u || adding) return
    setAdding(true)
    setMsg(null)
    try {
      const m = await api.addMirror(novelId, u)
      setMirrors((prev) => [...prev.filter((x) => x.id !== m.id), m])
      setUrl('')
      setMsg({ ok: true, text: `fonte adicionada (${m.source})` })
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : 'falha ao adicionar' })
    } finally {
      setAdding(false)
    }
  }

  async function remove(id: number): Promise<void> {
    setRemovingId(id)
    try {
      await api.deleteMirror(id)
      setMirrors((prev) => prev.filter((x) => x.id !== id))
    } catch {
      // mantém na lista se falhar
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="font-display flex items-baseline gap-3 text-lg font-medium tracking-tight">
        Fontes alternativas
        <span className="font-sans text-[11px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
          fallback de capítulo
        </span>
      </h3>
      <p className="font-sans text-[13px] leading-snug text-[var(--ink-500)]">
        Ligue outro site à <strong className="font-semibold">mesma obra</strong>. Quando o site
        principal falhar num capítulo, o app busca esse capítulo nas fontes abaixo (casando pelo
        número do título) — sem perder cache, tradução ou capa.
      </p>

      <ul className="space-y-2">
        {/* Fonte primária (read-only) */}
        <li className="flex items-center gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--paper-100)] px-4 py-2.5">
          <Link2 className="size-4 shrink-0 text-[var(--ink-400)]" />
          <div className="min-w-0 flex-1">
            <div className="font-sans flex items-center gap-2 text-[13px] font-medium text-[var(--ink-900)]">
              {primarySource}
              <span className="font-sans rounded-full bg-[var(--paper-300)] px-2 py-0.5 text-[10px] tracking-[0.12em] uppercase text-[var(--ink-500)]">
                principal
              </span>
            </div>
            <div className="font-mono truncate text-[11px] text-[var(--ink-400)]">{primaryUrl}</div>
          </div>
        </li>

        {mirrors.map((m) => (
          <li
            key={m.id}
            className="flex items-center gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--paper-50)] px-4 py-2.5"
          >
            <Link2 className="size-4 shrink-0 text-[var(--ink-400)]" />
            <div className="min-w-0 flex-1">
              <div className="font-sans text-[13px] font-medium text-[var(--ink-900)]">
                {m.source}
              </div>
              <div className="font-mono truncate text-[11px] text-[var(--ink-400)]">
                {m.source_url}
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => remove(m.id)}
              disabled={removingId === m.id}
              aria-label="remover fonte"
            >
              {removingId === m.id ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
            </Button>
          </li>
        ))}

        {loaded && mirrors.length === 0 && (
          <li className="font-sans text-[12px] italic text-[var(--ink-400)]">
            Nenhuma fonte alternativa ainda.
          </li>
        )}
      </ul>

      <div className="flex items-center gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="https://outro-site.com/novel/..."
          className="font-mono flex-1 rounded-lg border border-[var(--border-soft)] bg-[var(--paper-50)] px-3 py-2 text-[12px] text-[var(--ink-900)] outline-none focus:border-[var(--ink-300)]"
        />
        <Button size="sm" onClick={add} disabled={adding || !url.trim()}>
          {adding ? (
            <>
              <Loader2 className="size-3.5 animate-spin" /> validando…
            </>
          ) : (
            <>
              <Plus className="size-3.5" /> Adicionar fonte
            </>
          )}
        </Button>
      </div>
      {msg && (
        <p
          className={[
            'font-sans text-[12px]',
            msg.ok ? 'text-[var(--ink-500)]' : 'text-[var(--ink-stamp)]'
          ].join(' ')}
        >
          {msg.text}
        </p>
      )}
    </section>
  )
}
