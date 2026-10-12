import { useState } from 'react'
import {
  ChevronDown,
  Download,
  FileEdit,
  Hammer,
  ImageIcon,
  Check,
  Languages,
  Loader2,
  Pencil,
  RefreshCw,
  Send,
  Trash2,
  X
} from 'lucide-react'
import { api, type VolumeOut } from '@renderer/lib/api'
import { COVER_STYLES } from '@renderer/lib/coverStyles'
import { Button } from '@renderer/components/ui/button'

export function PersistedVolumeRow({
  vol,
  novelId,
  targetLang,
  enabledStyles,
  defaultStyle,
  onVolumeUpdated,
  onVolumeDeleted,
  onOpenEditor
}: {
  vol: VolumeOut
  novelId: number
  targetLang: string
  enabledStyles: string[]
  defaultStyle: string | null
  onVolumeUpdated: (v: VolumeOut) => void
  onVolumeDeleted: (id: number) => void
  onOpenEditor: (vol: VolumeOut) => void
}): React.JSX.Element {
  const [sending, setSending] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(vol.volume_title ?? '')
  const [savingTitle, setSavingTitle] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [translatingNow, setTranslatingNow] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [coverMenuOpen, setCoverMenuOpen] = useState(false)
  // Estilos do menu, na ordem do catálogo (só os habilitados nas Configurações).
  const menuStyles = COVER_STYLES.filter((s) => enabledStyles.includes(s.id))
  void novelId // referenced no botão Editor via onOpenEditor; mantido pra futura expansão
  // Tradução incompleta = ainda tem caps em EN. Volume nao deve ser tratado
  // como "pronto" — esconde .epub/Kindle/Regerar capa e mostra Retraduzir.
  const incompleteTranslation = !!vol.translate_to && vol.translation_failed > 0
  // Volume sem tradução nenhuma → oferece "Traduzir" (substitui no lugar).
  const untranslated = !vol.translate_to

  async function sendKindle(): Promise<void> {
    setSending(true)
    setSendMsg(null)
    try {
      const res = await api.sendVolumeToKindle(vol.id)
      setSendMsg({ ok: true, text: `enviado para ${res.to}` })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSending(false)
    }
  }

  // Edita SO o título do volume: o backend re-compõe o texto sobre a arte da
  // capa já existente (sem IA, custo zero) e remonta o .epub. Sem re-baixar.
  async function saveTitle(): Promise<void> {
    const next = titleDraft.trim()
    if (!next || next === (vol.volume_title ?? '').trim()) {
      setEditingTitle(false)
      return
    }
    setSavingTitle(true)
    setSendMsg(null)
    try {
      const updated = await api.renameVolume(vol.id, next)
      onVolumeUpdated(updated)
      setEditingTitle(false)
      setSendMsg({
        ok: true,
        text: vol.ai_cover
          ? 'título atualizado — capa recomposta + EPUB remontado (sem custo)'
          : 'título atualizado — EPUB remontado (sem custo)'
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSavingTitle(false)
    }
  }

  async function regenerateCover(coverStyle?: string | null): Promise<void> {
    setCoverMenuOpen(false)
    setRegenerating(true)
    setSendMsg(null)
    try {
      await api.regenerateVolumeCover(vol.id, coverStyle ?? null)
      setSendMsg({
        ok: true,
        text: vol.ai_cover
          ? 'novo job criado — capa será regerada (~R$0,20)'
          : 'novo job criado — capa por IA será gerada (~R$0,20)'
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRegenerating(false)
    }
  }

  // Comportamento do botão de capa conforme estilos habilitados nas Configurações:
  // 0 = automático (IA decide); 1 = vai direto nele; 2+ = abre menu pra escolher.
  function onCoverButtonClick(): void {
    if (menuStyles.length >= 2) {
      setCoverMenuOpen((v) => !v)
    } else {
      regenerateCover(menuStyles[0]?.id ?? null)
    }
  }

  // Item 1: traduz um volume que foi baixado sem tradução. Re-usa os capítulos
  // já em cache (só roda o tradutor), e substitui o volume original no lugar
  // (replace_volume_id) pra não duplicar a edição na biblioteca.
  async function translateVolume(): Promise<void> {
    setTranslatingNow(true)
    setSendMsg(null)
    try {
      await api.createDownload({
        url: vol.source_url,
        start: vol.start,
        end: vol.end,
        with_cover: vol.with_cover,
        translate_to: targetLang,
        volume_title: vol.volume_title,
        ai_cover: vol.ai_cover,
        skip_chapters: vol.skip_chapters,
        replace_volume_id: vol.id
      })
      setSendMsg({
        ok: true,
        text: `tradução iniciada (${targetLang}) — acompanhe em Downloads; substitui esta edição ao terminar`
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setTranslatingNow(false)
    }
  }

  // Item 3: remove o volume (registro + .epub). Usado pra limpar duplicatas.
  async function removeVolume(): Promise<void> {
    setDeleting(true)
    setSendMsg(null)
    try {
      await api.deleteVolume(vol.id)
      onVolumeDeleted(vol.id)
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  async function rebuildEpub(): Promise<void> {
    setRebuilding(true)
    setSendMsg(null)
    try {
      const updated = await api.rebuildVolume(vol.id)
      onVolumeUpdated(updated)
      setSendMsg({ ok: true, text: 'EPUB recompilado (sem custo)' })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRebuilding(false)
    }
  }

  async function retryTranslation(): Promise<void> {
    setRetrying(true)
    setSendMsg(null)
    try {
      // Re-enqueue mesmo job (cache de traducao pula caps OK, so falhos batem
      // o Gemini de novo). Mesmo padrao do "Continuar tradução" em Downloads.
      await api.createDownload({
        url: vol.source_url,
        start: vol.start,
        end: vol.end,
        with_cover: vol.with_cover,
        translate_to: vol.translate_to,
        volume_title: vol.volume_title,
        ai_cover: vol.ai_cover,
        skip_chapters: vol.skip_chapters
      })
      setSendMsg({
        ok: true,
        text: `novo job criado — ${vol.translation_failed} caps serão retentados`
      })
    } catch (err) {
      setSendMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setRetrying(false)
    }
  }

  return (
    <li
      className={[
        'flex flex-col gap-3 rounded-xl border bg-[var(--paper-100)] px-4 py-3',
        'border-[var(--border-soft)]'
      ].join(' ')}
    >
      {/* Título + meta: linha própria, largura total — nunca é esmagado pelos botões. */}
      <div className="min-w-0">
        {editingTitle ? (
          <div className="flex items-center gap-1.5">
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void saveTitle()
                else if (e.key === 'Escape') setEditingTitle(false)
              }}
              disabled={savingTitle}
              placeholder="Título do volume"
              className="font-display min-w-0 flex-1 rounded-md border border-[var(--border-medium)] bg-[var(--paper-50)] px-2 py-1 text-[15px] font-medium leading-snug tracking-tight outline-none focus:border-[var(--stamp-red)]"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={saveTitle}
              disabled={savingTitle}
              title="Salvar título: recompõe a capa sobre a arte atual + remonta o EPUB (sem custo)"
            >
              {savingTitle ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setEditingTitle(false)}
              disabled={savingTitle}
              title="Cancelar"
            >
              <X className="size-3.5" />
            </Button>
          </div>
        ) : (
          <div className="group flex items-center gap-1.5">
            <span className="font-display min-w-0 truncate text-[15px] font-medium leading-snug tracking-tight">
              {vol.volume_title ?? `Capítulos ${vol.start}–${vol.end ?? '?'}`}
            </span>
            <button
              type="button"
              onClick={() => {
                setTitleDraft(vol.volume_title ?? '')
                setEditingTitle(true)
              }}
              title="Editar o título do volume (recompõe a capa sobre a arte atual + remonta o EPUB, sem gerar arte nova)"
              className="shrink-0 rounded p-0.5 text-[var(--ink-400)] opacity-0 transition hover:text-[var(--ink-700)] group-hover:opacity-100"
            >
              <Pencil className="size-3.5" />
            </button>
          </div>
        )}
        <div className="font-sans mt-0.5 text-[11px] tracking-wide text-[var(--ink-500)]">
          caps {vol.start}–{vol.end ?? '?'} · {vol.translate_to ?? 'original'}
          {vol.ai_cover && ' · capa IA'}
          {incompleteTranslation && (
            <span className="text-[var(--ink-stamp)]">
              {' '}
              · {vol.translation_failed} falharam tradução
            </span>
          )}
        </div>
      </div>

      {/* Ações: linha própria que quebra; Excluir isolado à direita. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {incompleteTranslation ? (
            // Tradução incompleta: Retraduzir (Gemini) OU Editar (manual). Esconde
            // .epub/Kindle/capa pra evitar leitor levar EPUB pensando que está ok.
            <>
              <Button size="sm" onClick={retryTranslation} disabled={retrying}>
                {retrying ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="size-3.5" />
                )}
                Retraduzir
              </Button>
              <Button variant="outline" size="sm" onClick={() => onOpenEditor(vol)}>
                <FileEdit className="size-3.5" /> Editar caps
              </Button>
            </>
          ) : (
            <>
              <Button asChild variant="outline" size="sm">
                <a href={api.volumeFileUrl(vol.id)} download>
                  <Download className="size-3.5" /> .epub
                </a>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={rebuildEpub}
                disabled={rebuilding}
                title="Re-monta o EPUB do cache atual (sem custo)"
              >
                {rebuilding ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Hammer className="size-3.5" />
                )}
                Recompilar
              </Button>
              {untranslated && (
                <Button size="sm" onClick={translateVolume} disabled={translatingNow}>
                  {translatingNow ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Languages className="size-3.5" />
                  )}
                  Traduzir
                </Button>
              )}
              <div className="relative">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onCoverButtonClick}
                  disabled={regenerating}
                  title={
                    vol.ai_cover
                      ? 'Gera uma nova capa por IA (~R$0,20)'
                      : 'Gera uma capa por IA pra este volume (~R$0,20)'
                  }
                >
                  {regenerating ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <ImageIcon className="size-3.5" />
                  )}
                  {vol.ai_cover ? 'Regerar capa' : 'Gerar capa'}
                  {menuStyles.length >= 2 && <ChevronDown className="size-3.5" />}
                </Button>

                {coverMenuOpen && menuStyles.length >= 2 && (
                  <>
                    {/* backdrop transparente: clique fora fecha o menu */}
                    <div className="fixed inset-0 z-40" onClick={() => setCoverMenuOpen(false)} />
                    <div
                      className={[
                        'absolute left-0 top-full z-50 mt-1 max-h-72 w-56 overflow-y-auto',
                        'rounded-xl border border-[var(--border-medium)] bg-[var(--paper-50)] py-1',
                        'shadow-[0_8px_24px_rgba(80,50,20,0.18)]'
                      ].join(' ')}
                    >
                      <button
                        type="button"
                        onClick={() => regenerateCover(null)}
                        className="font-sans block w-full px-3 py-1.5 text-left text-[13px] text-[var(--ink-700)] hover:bg-[var(--paper-200)]"
                      >
                        Automático <span className="text-[var(--ink-400)]">(IA decide)</span>
                      </button>
                      <div className="my-1 border-t border-[var(--border-soft)]" />
                      {menuStyles.map((style) => (
                        <button
                          key={style.id}
                          type="button"
                          onClick={() => regenerateCover(style.id)}
                          className="font-sans flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-[13px] text-[var(--ink-700)] hover:bg-[var(--paper-200)]"
                        >
                          {style.label}
                          {style.id === defaultStyle && (
                            <span className="text-[10px] tracking-wide text-[var(--stamp-red)]">
                              padrão
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <Button variant="outline" size="sm" onClick={sendKindle} disabled={sending}>
                {sending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Send className="size-3.5" />
                )}
                Kindle
              </Button>
            </>
          )}
        </div>

        {confirmDelete ? (
          <span className="flex items-center gap-1.5">
            <span className="font-sans text-[11px] text-[var(--ink-500)]">Excluir?</span>
            <Button variant="outline" size="sm" onClick={removeVolume} disabled={deleting}>
              {deleting ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
              Sim
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(false)}
              disabled={deleting}
            >
              Cancelar
            </Button>
          </span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmDelete(true)}
            title="Remove este volume (registro + arquivo .epub). Não apaga capítulos do cache."
            className="text-[var(--ink-stamp)]"
          >
            <Trash2 className="size-3.5" /> Excluir
          </Button>
        )}
      </div>

      {sendMsg && (
        <span
          className={[
            'font-sans text-[11px]',
            sendMsg.ok ? 'text-[var(--book-3)]' : 'text-[var(--ink-stamp)]'
          ].join(' ')}
        >
          {sendMsg.text}
        </span>
      )}
    </li>
  )
}
