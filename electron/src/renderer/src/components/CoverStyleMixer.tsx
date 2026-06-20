import { Plus, X } from 'lucide-react'
import {
  type CoverStyleOption,
  COVER_STYLE_LABELS,
  encodeStyleSpec,
  normalizedWeights,
  parseStyleSpec
} from '@renderer/lib/coverStyles'

/**
 * Editor de mistura ponderada de estilos de capa.
 *
 * Controlado: `value` é o spec codificado "id:peso,id:peso,..." ('' = automático).
 *
 * UX: cada estilo tem um PESO INDEPENDENTE (slider + campo numérico). Mexer num
 * peso NÃO altera o número dos outros — os pesos são relativos e a conversão pra
 * % só aparece no resumo "Mistura final" embaixo (read-only). Isso evita o efeito
 * confuso de "mexo num e o % do outro pula" que acontece quando cada linha mostra
 * o % normalizado (que recalcula sempre que o total muda).
 */
export function CoverStyleMixer({
  value,
  onChange,
  options
}: {
  value: string
  onChange: (spec: string) => void
  options: CoverStyleOption[]
}): React.JSX.Element {
  const items = parseStyleSpec(value)
  const pcts = normalizedWeights(items)
  const selectedIds = new Set(items.map((i) => i.id))
  const available = options.filter((o) => !selectedIds.has(o.id))

  function commit(next: { id: string; weight: number }[]): void {
    onChange(encodeStyleSpec(next))
  }

  function addStyle(id: string): void {
    if (!id) return
    commit([...items, { id, weight: 50 }])
  }

  function setWeight(idx: number, weight: number): void {
    const w = Math.max(1, Math.min(100, Math.round(weight) || 1))
    commit(items.map((it, i) => (i === idx ? { ...it, weight: w } : it)))
  }

  function remove(idx: number): void {
    commit(items.filter((_, i) => i !== idx))
  }

  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="font-sans rounded-lg border border-dashed border-[var(--border-soft)] bg-[var(--paper-50)] px-3 py-2.5 text-[12px] text-[var(--ink-500)]">
          <strong className="text-[var(--ink-700)]">Automático</strong> — a IA decide o estilo pelo
          conteúdo. Adicione um ou mais estilos abaixo pra travar a direção de arte (e misturar com
          pesos).
        </p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((it, idx) => (
            <li
              key={it.id}
              className="rounded-lg border border-[var(--border-soft)] bg-[var(--paper-50)] px-3 py-2.5"
            >
              <div className="flex items-center gap-2">
                <span className="font-sans flex-1 text-[13px] font-medium text-[var(--ink-800)]">
                  {COVER_STYLE_LABELS[it.id] ?? it.id}
                </span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={it.weight}
                  onChange={(e) => setWeight(idx, Number(e.target.value))}
                  aria-label={`Peso de ${COVER_STYLE_LABELS[it.id] ?? it.id}`}
                  className="font-mono h-7 w-14 rounded-md border border-[var(--border-medium)] bg-[var(--paper-100)] px-2 text-right text-[13px] tabular-nums text-[var(--ink-800)] outline-none focus-visible:border-[var(--stamp-red)] focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/15"
                />
                <button
                  type="button"
                  onClick={() => remove(idx)}
                  aria-label={`Remover ${COVER_STYLE_LABELS[it.id] ?? it.id}`}
                  className="rounded p-1 text-[var(--ink-400)] transition-colors hover:bg-[var(--paper-200)] hover:text-[var(--ink-stamp)]"
                >
                  <X className="size-3.5" />
                </button>
              </div>
              <input
                type="range"
                min={1}
                max={100}
                value={it.weight}
                onChange={(e) => setWeight(idx, Number(e.target.value))}
                className="mt-1.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[var(--paper-300)] accent-[var(--stamp-red)]"
              />
            </li>
          ))}
        </ul>
      )}

      {available.length > 0 && (
        <div className="flex items-center gap-2">
          <Plus className="size-3.5 text-[var(--ink-400)]" />
          <select
            value=""
            onChange={(e) => {
              addStyle(e.target.value)
              e.target.value = ''
            }}
            className={[
              'font-sans h-9 flex-1 rounded-lg border bg-[var(--paper-50)] px-3 text-[13px]',
              'border-[var(--border-medium)] text-[var(--ink-700)]',
              'outline-none focus-visible:border-[var(--stamp-red)] focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/15'
            ].join(' ')}
          >
            <option value="">
              {items.length === 0 ? 'Adicionar estilo…' : 'Adicionar mais um estilo à mistura…'}
            </option>
            {available.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {items.length >= 2 && (
        <div className="rounded-lg bg-[var(--paper-100)] px-3 py-2">
          <div className="font-sans mb-1 text-[10px] font-medium tracking-[0.14em] text-[var(--ink-400)] uppercase">
            Mistura final
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {items.map((it, idx) => (
              <span key={it.id} className="font-sans text-[12px] text-[var(--ink-700)]">
                {COVER_STYLE_LABELS[it.id] ?? it.id}{' '}
                <strong className="font-mono text-[var(--stamp-red)] tabular-nums">
                  {pcts[idx]}%
                </strong>
              </span>
            ))}
          </div>
          <p className="font-sans mt-1.5 text-[11px] leading-relaxed text-[var(--ink-400)]">
            Os pesos são independentes — ajuste um sem mexer nos outros. O % final é a proporção
            entre eles; o de maior peso domina paleta e clima, os menores entram como motivos e
            detalhes.
          </p>
        </div>
      )}
    </div>
  )
}
