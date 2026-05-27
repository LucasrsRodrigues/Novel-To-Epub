import { useEffect, useMemo, useState } from 'react'
import { Loader2, Save, Trash2, X, RotateCcw, FileText } from 'lucide-react'
import { api, type ChapterDetail, type ChapterSummary, type VolumeOut } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'

interface Props {
  novelId: number
  volume: VolumeOut  // contexto: range + language + volume_id pra rebuild
  onClose: () => void
  /** Disparado quando uma tradução é salva — caller pode atualizar lista/contadores. */
  onTranslationSaved?: () => void
}

/**
 * Editor manual de capítulos. Lista os caps do volume à esquerda (highlight nos
 * sem tradução), editor HTML side-by-side à direita: EN read-only | PT editável.
 * Após salvar, dispara rebuild do volume pra atualizar o .epub.
 */
export function ChapterEditor({
  novelId, volume, onClose, onTranslationSaved
}: Props): React.JSX.Element {
  const language = volume.translate_to ?? 'pt-BR'
  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [detail, setDetail] = useState<ChapterDetail | null>(null)
  const [draft, setDraft] = useState<{ title: string; html: string }>({ title: '', html: '' })
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState<'all' | 'failed'>('failed')

  // Carrega lista de caps
  useEffect(() => {
    setLoading(true)
    api
      .listChapters(novelId, { language, start: volume.start, end: volume.end ?? undefined })
      .then((list) => {
        setChapters(list)
        // Auto-seleciona o primeiro sem tradução (provavelmente o que o user quer editar)
        const firstFailed = list.find((c) => !c.has_translation)
        setSelectedIdx(firstFailed?.index ?? list[0]?.index ?? null)
      })
      .catch((err) => setMsg({ ok: false, text: String(err) }))
      .finally(() => setLoading(false))
  }, [novelId, language, volume.start, volume.end])

  // Carrega detalhe quando muda cap selecionado
  useEffect(() => {
    if (selectedIdx == null) return
    setLoadingDetail(true)
    setMsg(null)
    api
      .getChapter(novelId, selectedIdx, language)
      .then((d) => {
        setDetail(d)
        setDraft({
          title: d.title_pt ?? d.title_en,
          html: d.html_pt ?? d.html_en
        })
      })
      .catch((err) => setMsg({ ok: false, text: String(err) }))
      .finally(() => setLoadingDetail(false))
  }, [selectedIdx, novelId, language])

  const visibleChapters = useMemo(
    () => (filter === 'failed' ? chapters.filter((c) => !c.has_translation) : chapters),
    [chapters, filter]
  )
  const failedCount = chapters.filter((c) => !c.has_translation).length

  async function save(): Promise<void> {
    if (selectedIdx == null) return
    setSaving(true)
    setMsg(null)
    try {
      await api.saveChapterTranslation(novelId, selectedIdx, {
        title: draft.title, html: draft.html, language
      })
      // Atualiza lista localmente
      setChapters((prev) =>
        prev.map((c) =>
          c.index === selectedIdx
            ? { ...c, has_translation: true, translation_source: 'manual', title_pt: draft.title }
            : c
        )
      )
      setDetail((d) =>
        d ? { ...d, title_pt: draft.title, html_pt: draft.html, translation_source: 'manual' } : d
      )
      setMsg({ ok: true, text: 'Tradução salva. Clique Recompilar pra atualizar o EPUB.' })
      onTranslationSaved?.()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSaving(false)
    }
  }

  async function discard(): Promise<void> {
    if (selectedIdx == null || !detail?.translation_source) return
    if (!confirm(`Remover tradução do cap ${selectedIdx}? O capítulo voltará pro inglês no EPUB.`)) return
    try {
      await api.deleteChapterTranslation(novelId, selectedIdx, language)
      setChapters((prev) =>
        prev.map((c) =>
          c.index === selectedIdx
            ? { ...c, has_translation: false, translation_source: null, title_pt: null }
            : c
        )
      )
      setDetail((d) => (d ? { ...d, title_pt: null, html_pt: null, translation_source: null } : d))
      setDraft({ title: detail.title_en, html: detail.html_en })
      setMsg({ ok: true, text: 'Tradução removida.' })
      onTranslationSaved?.()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  async function rebuild(): Promise<void> {
    setRebuilding(true)
    setMsg(null)
    try {
      await api.rebuildVolume(volume.id)
      setMsg({ ok: true, text: 'EPUB recompilado.' })
      onTranslationSaved?.()
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[var(--paper-50)]">
      {/* Header */}
      <header className="flex items-center gap-4 border-b border-[var(--border-soft)] bg-[var(--paper-100)] px-6 py-3">
        <FileText className="size-4 shrink-0 text-[var(--ink-400)]" />
        <div className="min-w-0 flex-1">
          <div className="font-display truncate text-[15px] font-medium tracking-tight">
            Editor · {volume.volume_title ?? `caps ${volume.start}–${volume.end}`}
          </div>
          <div className="font-sans text-[11px] tracking-wide text-[var(--ink-500)]">
            {chapters.length} caps · {failedCount} sem tradução · lingua: {language}
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={rebuild} disabled={rebuilding}>
          {rebuilding ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
          Recompilar EPUB
        </Button>
        <Button variant="outline" size="sm" onClick={onClose}>
          <X className="size-3.5" /> Fechar
        </Button>
      </header>

      {/* Body: split */}
      <div className="flex min-h-0 flex-1">
        {/* Sidebar: lista de caps */}
        <aside className="flex w-72 shrink-0 flex-col border-r border-[var(--border-soft)] bg-[var(--paper-100)]">
          <div className="flex gap-1 border-b border-[var(--border-soft)] p-2 text-[11px]">
            <button
              type="button"
              onClick={() => setFilter('failed')}
              className={[
                'font-sans flex-1 rounded px-2 py-1 tracking-wide uppercase',
                filter === 'failed' ? 'bg-[var(--ink-stamp)]/15 text-[var(--ink-stamp)]' : 'text-[var(--ink-500)]'
              ].join(' ')}
            >
              Sem tradução ({failedCount})
            </button>
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={[
                'font-sans flex-1 rounded px-2 py-1 tracking-wide uppercase',
                filter === 'all' ? 'bg-[var(--paper-300)] text-[var(--ink-700)]' : 'text-[var(--ink-500)]'
              ].join(' ')}
            >
              Todos ({chapters.length})
            </button>
          </div>
          {loading ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2 className="size-5 animate-spin text-[var(--ink-400)]" />
            </div>
          ) : (
            <ul className="flex-1 overflow-y-auto py-1">
              {visibleChapters.map((c) => {
                const active = c.index === selectedIdx
                return (
                  <li key={c.index}>
                    <button
                      type="button"
                      onClick={() => setSelectedIdx(c.index)}
                      className={[
                        'font-sans flex w-full items-start gap-2 px-3 py-2 text-left text-[12px]',
                        active
                          ? 'bg-[var(--paper-200)] border-l-2 border-[var(--stamp-red)]'
                          : 'hover:bg-[var(--paper-200)] border-l-2 border-transparent'
                      ].join(' ')}
                    >
                      <span className="folio shrink-0 w-7 text-[var(--ink-400)]">
                        {String(c.index).padStart(2, '0')}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{c.title_pt ?? c.title_en}</span>
                        <span className="block text-[10px] tracking-wide text-[var(--ink-400)]">
                          {c.has_translation
                            ? c.translation_source === 'manual'
                              ? '✎ manual'
                              : '✓ IA'
                            : '— sem tradução'}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
              {visibleChapters.length === 0 && (
                <li className="px-3 py-6 text-center text-[12px] text-[var(--ink-500)]">
                  {filter === 'failed' ? 'Nenhum cap falhou ✨' : 'Vazio.'}
                </li>
              )}
            </ul>
          )}
        </aside>

        {/* Main: editor */}
        <main className="flex min-w-0 flex-1 flex-col">
          {selectedIdx == null ? (
            <div className="flex flex-1 items-center justify-center text-[var(--ink-400)]">
              Selecione um capítulo
            </div>
          ) : loadingDetail || !detail ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2 className="size-6 animate-spin text-[var(--ink-400)]" />
            </div>
          ) : (
            <>
              {/* Title bar */}
              <div className="border-b border-[var(--border-soft)] px-6 py-3">
                <div className="folio text-[var(--ink-400)]">cap {detail.index}</div>
                <input
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  className="font-display mt-0.5 w-full bg-transparent text-[20px] font-medium tracking-tight outline-none focus:border-b focus:border-[var(--stamp-red)]"
                  placeholder="Título traduzido"
                />
                <div className="font-sans mt-1 text-[11px] tracking-wide text-[var(--ink-400)]">
                  EN: <span className="italic">{detail.title_en}</span>
                </div>
              </div>

              {/* Split: EN | PT */}
              <div className="grid min-h-0 flex-1 grid-cols-2">
                <section className="flex min-h-0 flex-col border-r border-[var(--border-soft)] bg-[var(--paper-100)]">
                  <div className="font-sans border-b border-[var(--border-soft)] px-4 py-2 text-[10px] tracking-[0.18em] uppercase text-[var(--ink-500)]">
                    Original (EN) · read-only
                  </div>
                  <pre className="font-sans flex-1 overflow-auto whitespace-pre-wrap break-words p-4 text-[13px] leading-relaxed text-[var(--ink-700)]">
                    {detail.html_en}
                  </pre>
                </section>
                <section className="flex min-h-0 flex-col">
                  <div className="font-sans flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2 text-[10px] tracking-[0.18em] uppercase text-[var(--ink-500)]">
                    <span>Tradução ({language})</span>
                    {detail.translation_source && (
                      <span
                        className={[
                          'rounded px-1.5 py-0.5 normal-case tracking-normal text-[10px]',
                          detail.translation_source === 'manual'
                            ? 'bg-[var(--stamp-red)]/10 text-[var(--stamp-red)]'
                            : 'bg-[var(--paper-300)] text-[var(--ink-500)]'
                        ].join(' ')}
                      >
                        {detail.translation_source === 'manual' ? '✎ manual' : detail.translation_source}
                      </span>
                    )}
                  </div>
                  <textarea
                    value={draft.html}
                    onChange={(e) => setDraft({ ...draft, html: e.target.value })}
                    spellCheck={true}
                    className="font-sans min-h-0 flex-1 resize-none bg-transparent p-4 text-[13px] leading-relaxed text-[var(--ink-900)] outline-none"
                    placeholder="Cole a tradução em HTML (preserve as tags <p>)"
                  />
                </section>
              </div>

              {/* Footer */}
              <footer className="flex flex-wrap items-center gap-3 border-t border-[var(--border-soft)] bg-[var(--paper-100)] px-6 py-3">
                <Button onClick={save} disabled={saving} size="sm">
                  {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                  Salvar
                </Button>
                {detail.translation_source && (
                  <Button variant="outline" size="sm" onClick={discard}>
                    <Trash2 className="size-3.5" /> Remover tradução
                  </Button>
                )}
                {msg && (
                  <span
                    className={[
                      'font-sans text-[12px]',
                      msg.ok ? 'text-[var(--book-3)]' : 'text-[var(--ink-stamp)]'
                    ].join(' ')}
                  >
                    {msg.text}
                  </span>
                )}
              </footer>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
