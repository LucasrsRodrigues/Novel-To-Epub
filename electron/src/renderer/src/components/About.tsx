import { BookOpen, Languages, Sparkles, Send, ScrollText, Heart } from 'lucide-react'

// GitHub mark — esta versao do lucide-react nao exporta um icon GitHub,
// entao inline o SVG oficial (MIT, github/octicons) pra manter consistencia.
function Github({ className }: { className?: string }): React.JSX.Element {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  )
}
import { Logo } from '@renderer/components/decorative/Logo'
import { Stamp } from '@renderer/components/decorative/Stamp'
import { StackedBooks } from '@renderer/components/decorative/StackedBooks'
import { Folio } from '@renderer/components/decorative/Folio'
import { Card } from '@renderer/components/ui/card'

const REPO_URL = 'https://github.com/LucasrsRodrigues/Novel-To-Epub'
const AUTHOR_URL = 'https://github.com/LucasrsRodrigues'

interface Feature {
  icon: React.ComponentType<{ className?: string }>
  title: string
  text: string
  color: string
}

const FEATURES: Feature[] = [
  {
    icon: BookOpen,
    title: 'Multi-site',
    text: 'NovelBin, NovelMania e mais via adapters plugáveis. Adicionar site novo é criar um arquivo.',
    color: 'var(--book-1)'
  },
  {
    icon: Languages,
    title: 'Tradução cascade',
    text: 'Groq → OpenRouter → Cerebras → Gemini, com fallback automático. Glossário mantém nomes consistentes.',
    color: 'var(--book-4)'
  },
  {
    icon: Sparkles,
    title: 'Capa por IA',
    text: 'Brief visual derivado dos primeiros capítulos + tipografia editorial sobreposta via Pillow.',
    color: 'var(--book-5)'
  },
  {
    icon: Send,
    title: 'Direto pro Kindle',
    text: 'Envio por email (SMTP) configurável. Volumes viram série — o Kindle agrupa.',
    color: 'var(--book-2)'
  }
]

// Link externo abre via shell.openExternal (configurado no main process via
// setWindowOpenHandler). Aqui é só um <a target="_blank">.
function ExternalLink({
  href,
  children,
  className
}: {
  href: string
  children: React.ReactNode
  className?: string
}): React.JSX.Element {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={[
        'font-sans inline-flex items-center gap-1.5 text-[13px] transition-colors',
        'text-[var(--ink-700)] underline decoration-[var(--ink-300)] underline-offset-4',
        'hover:text-[var(--stamp-red)] hover:decoration-[var(--stamp-red)]',
        className ?? ''
      ].join(' ')}
    >
      {children}
    </a>
  )
}

export function About(): React.JSX.Element {
  return (
    <div className="space-y-12">
      {/* HERO — logo grande + ilustração + stamp */}
      <header className="relative">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-4">
            <Folio n="i" />
            <Logo size="lg" />
            <p className="font-display max-w-md text-[18px] leading-snug text-[var(--ink-700)]">
              Web novels viram{' '}
              <em className="italic text-[var(--stamp-red)]">livros de verdade</em> —
              tradução, capa e Kindle, num clique.
            </p>
            <p className="font-sans max-w-md text-[13px] leading-relaxed text-[var(--ink-500)]">
              Cole a URL de uma novel, escolha o intervalo, e o app baixa, traduz
              (opcional), gera capa e monta um EPUB pronto pro leitor. Cache em SQLite
              garante zero re-trabalho.
            </p>
          </div>
          <div className="relative shrink-0">
            <StackedBooks className="scale-90 origin-top-right" />
            <Stamp
              className="absolute -bottom-2 -left-6 -rotate-[12deg]"
              size={88}
              centerWord="Novel"
            />
          </div>
        </div>
      </header>

      {/* FEATURES — grid 2x2 */}
      <section className="space-y-4">
        <h3 className="font-display text-[13px] font-semibold tracking-[0.18em] text-[var(--ink-400)] uppercase">
          O que faz
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {FEATURES.map((f) => (
            <Card key={f.title} className="flex gap-3 p-4">
              <div
                className="flex size-10 shrink-0 items-center justify-center rounded-lg"
                style={{
                  backgroundColor: 'var(--paper-100)',
                  color: f.color,
                  boxShadow: 'inset 0 0 0 1px var(--border-soft)'
                }}
              >
                <f.icon className="size-5" />
              </div>
              <div className="space-y-1">
                <div className="font-display text-[14px] font-medium tracking-tight text-[var(--ink-900)]">
                  {f.title}
                </div>
                <p className="font-sans text-[12px] leading-relaxed text-[var(--ink-500)]">
                  {f.text}
                </p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* LINKS — github do repo + criador */}
      <section className="space-y-4">
        <h3 className="font-display text-[13px] font-semibold tracking-[0.18em] text-[var(--ink-400)] uppercase">
          Onde encontrar
        </h3>
        <Card className="space-y-4 p-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <ExternalLink href={REPO_URL}>
              <Github className="size-4" />
              Repositório
            </ExternalLink>
            <ExternalLink href={`${REPO_URL}/issues`}>
              <ScrollText className="size-4" />
              Issues & sugestões
            </ExternalLink>
            <ExternalLink href={`${REPO_URL}/releases`}>
              <BookOpen className="size-4" />
              Releases
            </ExternalLink>
          </div>
          <div className="border-t border-[var(--border-soft)] pt-4">
            <p className="font-sans text-[12px] leading-relaxed text-[var(--ink-500)]">
              Feito por{' '}
              <ExternalLink href={AUTHOR_URL} className="inline">
                @LucasrsRodrigues
              </ExternalLink>{' '}
              com <Heart className="inline size-3 text-[var(--stamp-red)]" /> e muito Gemini
              free tier. PRs com novos adapters são a contribuição mais valiosa — o tutorial
              tá no README do repo.
            </p>
          </div>
        </Card>
      </section>

      {/* AVISO LEGAL — discreto mas presente */}
      <section className="space-y-3">
        <Card className="border-dashed bg-[var(--paper-50)] p-4">
          <p className="font-sans text-[11px] leading-relaxed text-[var(--ink-500)]">
            <strong className="font-medium text-[var(--ink-700)]">Uso pessoal.</strong>{' '}
            Este app é uma ferramenta de leitura offline. Respeite o copyright dos autores e
            os Termos de Uso dos sites de origem — não redistribua os EPUBs gerados. Apoiar o
            autor (quando possível) é o caminho ético.
          </p>
        </Card>
      </section>

      {/* COLOFON — versão, licença, agradecimentos */}
      <footer className="border-t border-[var(--border-soft)] pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <p className="font-sans text-[11px] tracking-wide text-[var(--ink-400)]">
            <span className="folio">v{__APP_VERSION__}</span> · MIT License · © 2026
            Lucas Rodrigues
          </p>
          <p className="font-sans text-[11px] tracking-wide text-[var(--ink-400)]">
            Construído com FastAPI · Electron · React · ebooklib
          </p>
        </div>
      </footer>
    </div>
  )
}
