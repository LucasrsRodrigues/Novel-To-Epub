import { useEffect, useState } from 'react'
import { BookOpen, RefreshCw } from 'lucide-react'
import { api, type NovelSummary } from '@renderer/lib/api'
import { Button } from '@renderer/components/ui/button'
import { Folio } from '@renderer/components/decorative/Folio'
import { Ribbon } from '@renderer/components/decorative/Ribbon'
import { StackedBooks } from '@renderer/components/decorative/StackedBooks'
import { Stamp } from '@renderer/components/decorative/Stamp'

const RIBBON_COLORS = [
  'var(--bookmark-ribbon)',
  'var(--book-1)',
  'var(--book-3)',
  'var(--book-4)',
  'var(--book-5)'
]

function NovelCard({
  novel,
  ribbonColor,
  onClick
}: {
  novel: NovelSummary
  ribbonColor: string
  onClick: () => void
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'group relative flex gap-5 rounded-2xl border bg-[var(--paper-100)] p-5 text-left',
        'border-[var(--border-soft)] cursor-pointer',
        'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_1px_3px_rgba(80,50,20,0.05),0_14px_28px_-18px_rgba(80,50,20,0.20)]',
        'transition-all duration-300 hover:-translate-y-0.5 hover:border-[var(--ink-300)] hover:shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_2px_6px_rgba(80,50,20,0.08),0_24px_38px_-18px_rgba(80,50,20,0.28)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/30 focus-visible:ring-offset-2 focus-visible:ring-offset-background'
      ].join(' ')}
    >
      {/* Cover with ribbon */}
      <div className="relative shrink-0">
        {novel.cover_url ? (
          <img
            src={novel.cover_url}
            alt={novel.title}
            className="h-32 w-22 rounded-md object-cover shadow-[0_2px_8px_rgba(80,50,20,0.25),0_1px_2px_rgba(80,50,20,0.15)]"
            style={{ width: 88 }}
          />
        ) : (
          <div
            className="flex h-32 items-center justify-center rounded-md bg-[var(--paper-300)]"
            style={{ width: 88 }}
          >
            <BookOpen className="size-7 text-[var(--ink-400)]" />
          </div>
        )}
        {/* hanging bookmark ribbon */}
        <Ribbon
          color={ribbonColor}
          width={14}
          height={26}
          className="absolute -top-1 right-2"
        />
      </div>

      {/* Info */}
      <div className="flex min-w-0 flex-1 flex-col">
        <h3 className="font-display truncate text-lg leading-tight font-medium tracking-tight text-[var(--ink-900)]">
          {novel.title}
        </h3>
        <p className="font-sans truncate text-[13px] italic text-[var(--ink-500)]">
          {novel.author ?? 'autor desconhecido'}
        </p>
        <div className="mt-auto flex items-end justify-between pt-3">
          <span className="font-display text-[28px] leading-none font-medium italic text-[var(--ink-900)]">
            {novel.chapters}
            <span className="font-sans text-[10px] not-italic font-medium tracking-[0.18em] uppercase text-[var(--ink-400)]">
              {' '}cap
            </span>
          </span>
          <span className="font-sans text-[10px] tracking-[0.16em] uppercase text-[var(--ink-400)]">
            {novel.source}
          </span>
        </div>
      </div>
    </button>
  )
}

export function Library({
  onOpenNovel
}: {
  onOpenNovel?: (id: number) => void
} = {}): React.JSX.Element {
  const [novels, setNovels] = useState<NovelSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load(): void {
    setError(null)
    api
      .library()
      .then(setNovels)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }

  useEffect(load, [])

  const count = novels?.length ?? 0

  return (
    <div className="space-y-10">
      <header className="space-y-3">
        <Folio n="ii" />
        <h2 className="font-display text-[2.5rem] leading-none font-medium tracking-tight">
          Biblioteca
        </h2>
        <p className="font-sans max-w-md text-[15px] leading-relaxed text-[var(--ink-500)]">
          Suas novels em cache local. Cada uma com seu universo de personagens
          e termos — visite o <em className="font-display italic">Glossário</em> pra revisar.
        </p>
      </header>

      {/* Hero card */}
      <section
        className={[
          'relative flex items-center gap-6 overflow-hidden rounded-3xl border px-8 py-6',
          'border-[var(--border-soft)] bg-[var(--paper-100)]',
          'shadow-[0_1px_0_rgba(255,250,235,0.85)_inset,0_2px_4px_rgba(80,50,20,0.04),0_24px_48px_-22px_rgba(80,50,20,0.25)]'
        ].join(' ')}
      >
        {/* Stamp seal floating top-right */}
        <Stamp className="absolute -right-3 -top-3 rotate-[8deg]" size={90} />

        <StackedBooks className="-mb-4 shrink-0" />

        <div className="flex-1 space-y-3">
          <p className="folio text-[var(--ink-400)]">— Personal Library · {count} obras —</p>
          <h3 className="font-display text-2xl leading-tight font-medium tracking-tight">
            Cada livro um <em className="italic">mundo</em> — guardados em paz.
          </h3>
          <p className="font-sans text-[13px] leading-relaxed text-[var(--ink-500)]">
            Capítulos baixados e traduções ficam em cache local. Re-gerar o EPUB
            não consome nenhuma rede nem nenhum token.
          </p>
          <div className="pt-2">
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="size-3.5" /> Atualizar
            </Button>
          </div>
        </div>
      </section>

      {error && (
        <p className="font-sans text-sm text-[var(--ink-stamp)]">{error}</p>
      )}

      {novels && novels.length === 0 && (
        <div className="py-16 text-center">
          <p className="font-display text-xl italic text-[var(--ink-400)]">
            Nada catalogado ainda.
          </p>
          <p className="font-sans mt-2 text-sm text-[var(--ink-500)]">
            Crie uma nova captura pra começar.
          </p>
        </div>
      )}

      {novels && novels.length > 0 && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {novels.map((novel, idx) => (
            <NovelCard
              key={novel.id}
              novel={novel}
              ribbonColor={RIBBON_COLORS[idx % RIBBON_COLORS.length]}
              onClick={() => onOpenNovel?.(novel.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
