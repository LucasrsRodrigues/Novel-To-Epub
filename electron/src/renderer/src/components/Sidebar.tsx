import { cn } from '@renderer/lib/utils'
import { useJobs } from '@renderer/context/JobsContext'
import { Book } from '@renderer/components/decorative/Book'
import { Logo } from '@renderer/components/decorative/Logo'

export type View = 'new' | 'downloads' | 'library' | 'glossary' | 'usage' | 'settings'

interface NavItem {
  id: View
  label: string
  description: string
  color: string
  letter: string
}

const ITEMS: NavItem[] = [
  { id: 'new', label: 'Nova captura', description: 'criar', color: 'var(--book-1)', letter: 'N' },
  { id: 'downloads', label: 'Downloads', description: 'fila ao vivo', color: 'var(--book-2)', letter: 'D' },
  { id: 'library', label: 'Biblioteca', description: 'em cache', color: 'var(--book-3)', letter: 'B' },
  { id: 'glossary', label: 'Glossário', description: 'termos', color: 'var(--book-4)', letter: 'G' },
  { id: 'usage', label: 'Custos', description: 'gastos Gemini', color: 'var(--book-6)', letter: '$' },
  { id: 'settings', label: 'Configurações', description: 'preferências', color: 'var(--book-5)', letter: 'C' }
]

export function Sidebar({
  view,
  onNavigate
}: {
  view: View
  onNavigate: (v: View) => void
}): React.JSX.Element {
  const { jobs, connected } = useJobs()
  const active = Object.values(jobs).filter(
    (j) => j.status === 'running' || j.status === 'queued'
  ).length

  return (
    <aside className="surface-paper relative flex w-72 shrink-0 flex-col rounded-none border-y-0 border-l-0 px-4 pt-12 pb-7">
      {/* drag-region: usuario arrasta a janela a partir do header (titlebar oculta) */}
      <div className="drag-region px-3 pb-7">
        <Logo size="md" />
        <p className="folio mt-1.5 text-[0.7rem] text-[var(--ink-400)]">
          Personal Library · Est. 2026
        </p>
      </div>

      <nav className="flex-1 space-y-1">
        {ITEMS.map((item) => {
          const isActive = view === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                'group relative flex w-full items-center gap-3.5 rounded-xl px-3 py-2.5',
                'transition-all duration-200',
                isActive
                  ? 'bg-[var(--paper-200)] shadow-[inset_0_1px_0_rgba(255,250,235,0.85),0_1px_2px_rgba(80,50,20,0.05)]'
                  : 'hover:bg-[var(--paper-100)]/70'
              )}
            >
              {/* active accent stripe */}
              {isActive && (
                <span
                  className="absolute left-0 top-2.5 bottom-2.5 w-1 rounded-r-full"
                  style={{ backgroundColor: item.color }}
                />
              )}
              <Book
                color={item.color}
                letter={item.letter}
                size={34}
                showRibbon={isActive}
                className={cn(
                  'transition-transform duration-300',
                  isActive ? 'scale-110 -rotate-3' : 'group-hover:scale-105 group-hover:-rotate-2'
                )}
              />
              <span className="flex flex-1 flex-col items-start">
                <span
                  className={cn(
                    'font-sans text-[14px] tracking-tight transition-colors',
                    isActive
                      ? 'font-semibold text-[var(--ink-900)]'
                      : 'font-medium text-[var(--ink-700)] group-hover:text-[var(--ink-900)]'
                  )}
                >
                  {item.label}
                </span>
                <span
                  className={cn(
                    'font-sans text-[11px] tracking-wide',
                    isActive ? 'text-[var(--ink-500)]' : 'text-[var(--ink-400)]'
                  )}
                >
                  {item.description}
                </span>
              </span>
              {item.id === 'downloads' && active > 0 && (
                <span
                  className="font-sans flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[var(--stamp-red)] px-1.5 text-[10px] font-bold text-[var(--paper-100)] shadow-[0_1px_2px_rgba(120,40,30,0.3)]"
                >
                  {active}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* connection footer */}
      <div className="font-sans mt-4 flex items-center gap-2 rounded-xl border border-[var(--border-soft)] bg-[var(--paper-50)] px-3 py-2 text-[11px]">
        <span
          className={cn(
            'inline-block size-1.5 rounded-full',
            connected ? 'bg-[var(--book-3)]' : 'bg-[var(--ink-300)]'
          )}
        />
        <span className="text-[var(--ink-500)]">
          backend {connected ? 'conectado' : 'desconectado'}
        </span>
      </div>
    </aside>
  )
}
