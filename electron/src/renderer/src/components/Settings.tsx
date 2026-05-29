import { useEffect, useState } from 'react'
import {
  Activity,
  ArrowDown,
  ArrowUp,
  CircleAlert,
  CircleCheck,
  Languages,
  Layers,
  Loader2,
  Mail,
  Palette,
  Save
} from 'lucide-react'
import { TranslationDiagnostic } from '@renderer/components/TranslationDiagnostic'
import { api, type SettingsUpdate } from '@renderer/lib/api'
import { COVER_STYLES } from '@renderer/lib/coverStyles'
import { Button } from '@renderer/components/ui/button'
import { Input } from '@renderer/components/ui/input'
import { Label } from '@renderer/components/ui/label'
import { Checkbox } from '@renderer/components/ui/checkbox'
import { Card } from '@renderer/components/ui/card'
import { Folio } from '@renderer/components/decorative/Folio'

function SectionHeader({
  icon: Icon,
  title,
  description
}: {
  icon: typeof Mail
  title: string
  description: string
}): React.JSX.Element {
  return (
    <div className="space-y-1.5">
      <h3 className="font-display flex items-center gap-2.5 text-xl font-medium tracking-tight">
        <Icon className="size-5 text-[var(--stamp-red)]" />
        {title}
      </h3>
      <p className="font-sans text-[13px] leading-relaxed text-[var(--ink-500)]">{description}</p>
    </div>
  )
}

const selectClasses = [
  'font-sans h-10 w-full rounded-xl border bg-[var(--paper-50)] px-4 text-sm',
  'border-[var(--border-medium)] text-[var(--ink-900)]',
  'shadow-[inset_0_1px_2px_rgba(80,50,20,0.05)]',
  'outline-none focus-visible:border-[var(--stamp-red)] focus-visible:bg-[var(--paper-100)] focus-visible:ring-2 focus-visible:ring-[var(--stamp-red)]/15'
].join(' ')

export function Settings(): React.JSX.Element {
  const [host, setHost] = useState('')
  const [port, setPort] = useState('587')
  const [user, setUser] = useState('')
  const [from, setFrom] = useState('')
  const [kindle, setKindle] = useState('')
  const [tls, setTls] = useState(true)
  const [password, setPassword] = useState('')
  const [pwSet, setPwSet] = useState(false)

  const [geminiKey, setGeminiKey] = useState('')
  const [geminiKeySet, setGeminiKeySet] = useState(false)
  const [targetLang, setTargetLang] = useState('pt-BR')
  const [model, setModel] = useState('gemini-2.5-flash')

  // Cascade providers
  const [groqKey, setGroqKey] = useState('')
  const [groqKeySet, setGroqKeySet] = useState(false)
  const [groqModel, setGroqModel] = useState('')
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [openrouterKeySet, setOpenrouterKeySet] = useState(false)
  const [openrouterModel, setOpenrouterModel] = useState('')
  const [cerebrasKey, setCerebrasKey] = useState('')
  const [cerebrasKeySet, setCerebrasKeySet] = useState(false)
  const [cerebrasModel, setCerebrasModel] = useState('')
  const [defaultModels, setDefaultModels] = useState<Record<string, string>>({
    groq: 'llama-3.3-70b-versatile',
    openrouter: 'qwen/qwen-2.5-72b-instruct:free',
    cerebras: 'gpt-oss-120b',
    gemini: 'gemini-2.5-flash'
  })
  const [cascadeOrder, setCascadeOrder] = useState<string[]>([
    'groq',
    'openrouter',
    'cerebras',
    'gemini'
  ])
  // Estilos de capa habilitados no dropdown (ids). Vazio = capa sempre automática.
  const [coverStyles, setCoverStyles] = useState<string[]>([])

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [showDiagnostic, setShowDiagnostic] = useState(false)

  useEffect(() => {
    api
      .getSettings()
      .then((cfg) => {
        setHost(cfg.smtp_host ?? '')
        setPort(String(cfg.smtp_port))
        setUser(cfg.smtp_user ?? '')
        setFrom(cfg.smtp_from ?? '')
        setKindle(cfg.kindle_email ?? '')
        setTls(cfg.smtp_use_tls)
        setPwSet(cfg.smtp_password_set)
        setGeminiKeySet(cfg.gemini_api_key_set)
        setTargetLang(cfg.target_language)
        setModel(cfg.translation_model)
        setGroqKeySet(cfg.groq_api_key_set)
        setOpenrouterKeySet(cfg.openrouter_api_key_set)
        setCerebrasKeySet(cfg.cerebras_api_key_set)
        setGroqModel(cfg.groq_model ?? '')
        setOpenrouterModel(cfg.openrouter_model ?? '')
        setCerebrasModel(cfg.cerebras_model ?? '')
        if (cfg.default_models) setDefaultModels(cfg.default_models)
        if (cfg.cascade_order && cfg.cascade_order.length > 0) {
          setCascadeOrder(cfg.cascade_order)
        }
        setCoverStyles(cfg.cover_styles_enabled ?? [])
      })
      .catch((err) => setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) }))
      .finally(() => setLoading(false))
  }, [])

  async function onSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault()
    setSaving(true)
    setMsg(null)
    const body: SettingsUpdate = {
      smtp_host: host || null,
      smtp_port: Number(port) || 587,
      smtp_user: user || null,
      smtp_from: from || null,
      kindle_email: kindle || null,
      smtp_use_tls: tls,
      target_language: targetLang,
      translation_model: model
    }
    if (password) body.smtp_password = password
    if (geminiKey) body.gemini_api_key = geminiKey
    if (groqKey) body.groq_api_key = groqKey
    if (openrouterKey) body.openrouter_api_key = openrouterKey
    if (cerebrasKey) body.cerebras_api_key = cerebrasKey
    // Models: string vazia = limpa override (volta pro default); valor = sobrescreve
    body.groq_model = groqModel.trim() || null
    body.openrouter_model = openrouterModel.trim() || null
    body.cerebras_model = cerebrasModel.trim() || null
    body.cascade_order = cascadeOrder
    body.cover_styles_enabled = coverStyles
    try {
      const cfg = await api.updateSettings(body)
      setPwSet(cfg.smtp_password_set)
      setPassword('')
      setGeminiKeySet(cfg.gemini_api_key_set)
      setGeminiKey('')
      setGroqKeySet(cfg.groq_api_key_set)
      setGroqKey('')
      setOpenrouterKeySet(cfg.openrouter_api_key_set)
      setOpenrouterKey('')
      setCerebrasKeySet(cfg.cerebras_api_key_set)
      setCerebrasKey('')
      if (cfg.cascade_order && cfg.cascade_order.length > 0) {
        setCascadeOrder(cfg.cascade_order)
      }
      setCoverStyles(cfg.cover_styles_enabled ?? [])
      setMsg({ ok: true, text: 'configurações salvas' })
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-[var(--ink-500)]">
        <Loader2 className="size-4 animate-spin" />
        <span className="font-sans text-sm">Carregando…</span>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      {showDiagnostic && <TranslationDiagnostic onClose={() => setShowDiagnostic(false)} />}
      <header className="space-y-3">
        <Folio n="v" />
        <h2 className="font-display text-[2.5rem] leading-none font-medium tracking-tight">
          Configurações
        </h2>
        <p className="font-sans max-w-md text-[15px] leading-relaxed text-[var(--ink-500)]">
          Credenciais e preferências locais. Tudo no SQLite, nada na nuvem.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-5">
        <Card>
          <SectionHeader
            icon={Mail}
            title="Envio pro Kindle (SMTP)"
            description="Use um servidor SMTP (ex: Gmail com senha de app). O e-mail do Kindle é o endereço @kindle.com, e o remetente precisa estar aprovado na Amazon."
          />

          <div className="grid grid-cols-1 gap-4 pt-2 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="host">Servidor SMTP</Label>
              <Input
                id="host"
                placeholder="smtp.gmail.com"
                value={host}
                onChange={(e) => setHost(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="port">Porta</Label>
              <Input
                id="port"
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="user">Usuário SMTP</Label>
              <Input
                id="user"
                placeholder="seu@gmail.com"
                value={user}
                onChange={(e) => setUser(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Senha SMTP</Label>
              <Input
                id="password"
                type="password"
                placeholder={pwSet ? '•••••••• (definida)' : 'senha de app'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="from">Remetente (From)</Label>
              <Input
                id="from"
                placeholder="seu@gmail.com"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kindle">E-mail do Kindle</Label>
              <Input
                id="kindle"
                placeholder="voce@kindle.com"
                value={kindle}
                onChange={(e) => setKindle(e.target.value)}
              />
            </div>
          </div>

          <label className="font-sans flex cursor-pointer items-center gap-3 pt-1 text-[14px] text-[var(--ink-700)]">
            <Checkbox checked={tls} onCheckedChange={(v) => setTls(v === true)} />
            Usar STARTTLS <span className="text-[var(--ink-400)]">(recomendado p/ porta 587)</span>
          </label>
        </Card>

        <Card>
          <SectionHeader
            icon={Languages}
            title="Tradução (Gemini)"
            description="API key gratuita em aistudio.google.com/apikey. Flash dá ~1500 requests/dia no free tier."
          />

          <div className="space-y-1.5 pt-2">
            <Label htmlFor="gemini-key">API Key</Label>
            <Input
              id="gemini-key"
              type="password"
              placeholder={geminiKeySet ? '•••••••• (definida)' : 'AIza…'}
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="target-lang">Idioma de destino</Label>
              <select
                id="target-lang"
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                className={selectClasses}
              >
                <option value="pt-BR">Português (BR)</option>
                <option value="pt-PT">Português (PT)</option>
                <option value="es">Espanhol</option>
                <option value="fr">Francês</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="model">Modelo</Label>
              <select
                id="model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className={selectClasses}
              >
                <option value="gemini-2.5-flash">Gemini 2.5 Flash (padrão)</option>
                <option value="gemini-2.5-flash-lite">Gemini 2.5 Flash Lite</option>
                <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
              </select>
            </div>
          </div>
        </Card>

        <Card>
          <SectionHeader
            icon={Layers}
            title="Cascade de providers (fallback automático)"
            description="Adiciona providers free. Em ordem: o 1º é tentado primeiro; se cair em rate-limit (429) ou 5xx, cai pro próximo. Mesmo volume fica pinado no provider que pegou (consistência de voz)."
          />

          <ProviderKeyRow
            label="Groq"
            provider="groq"
            url="https://console.groq.com/keys"
            note="Default: llama-3.3-70b-versatile (1000 req/dia gratis, ultra rápido)"
            keySet={groqKeySet}
            value={groqKey}
            onChange={setGroqKey}
            model={groqModel}
            onModelChange={setGroqModel}
            defaultModel={defaultModels.groq}
          />
          <ProviderKeyRow
            label="OpenRouter"
            provider="openrouter"
            url="https://openrouter.ai/keys"
            note="Default: Qwen 2.5 72B :free (200/dia, 1000 com $5 crédito)"
            keySet={openrouterKeySet}
            value={openrouterKey}
            onChange={setOpenrouterKey}
            model={openrouterModel}
            onModelChange={setOpenrouterModel}
            defaultModel={defaultModels.openrouter}
          />
          <ProviderKeyRow
            label="Cerebras"
            provider="cerebras"
            url="https://cloud.cerebras.ai/platform"
            note="Default: gpt-oss-120b (substituto do llama-3.3-70b que foi decomissionado)"
            keySet={cerebrasKeySet}
            value={cerebrasKey}
            onChange={setCerebrasKey}
            model={cerebrasModel}
            onModelChange={setCerebrasModel}
            defaultModel={defaultModels.cerebras}
          />

          <div className="pt-4">
            <Label>Ordem do cascade</Label>
            <p className="font-sans mt-1 text-[12px] text-[var(--ink-500)]">
              Arraste com as setas. Providers sem key são pulados automaticamente.
            </p>
            <ul className="mt-3 space-y-1.5">
              {cascadeOrder.map((p, i) => {
                const enabled =
                  (p === 'groq' && (groqKey || groqKeySet)) ||
                  (p === 'openrouter' && (openrouterKey || openrouterKeySet)) ||
                  (p === 'cerebras' && (cerebrasKey || cerebrasKeySet)) ||
                  (p === 'gemini' && (geminiKey || geminiKeySet))
                return (
                  <li
                    key={p}
                    className={[
                      'font-sans flex items-center gap-3 rounded-lg border px-3 py-2 text-[13px]',
                      'border-[var(--border-soft)]',
                      enabled ? 'bg-[var(--paper-100)]' : 'bg-[var(--paper-50)] opacity-50'
                    ].join(' ')}
                  >
                    <span className="folio w-6 text-[var(--ink-400)]">{i + 1}.</span>
                    <span className="flex-1 capitalize">{p}</span>
                    {!enabled && (
                      <span className="font-sans text-[10px] tracking-wide uppercase text-[var(--ink-400)]">
                        sem key
                      </span>
                    )}
                    <button
                      type="button"
                      disabled={i === 0}
                      onClick={() => {
                        const next = [...cascadeOrder]
                        ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                        setCascadeOrder(next)
                      }}
                      className="rounded p-1 text-[var(--ink-400)] hover:bg-[var(--paper-200)] hover:text-[var(--ink-700)] disabled:opacity-30"
                    >
                      <ArrowUp className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={i === cascadeOrder.length - 1}
                      onClick={() => {
                        const next = [...cascadeOrder]
                        ;[next[i + 1], next[i]] = [next[i], next[i + 1]]
                        setCascadeOrder(next)
                      }}
                      className="rounded p-1 text-[var(--ink-400)] hover:bg-[var(--paper-200)] hover:text-[var(--ink-700)] disabled:opacity-30"
                    >
                      <ArrowDown className="size-3.5" />
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>

          <div className="pt-3">
            <button
              type="button"
              onClick={() => setShowDiagnostic(true)}
              className="font-sans inline-flex items-center gap-1.5 text-[12px] text-[var(--stamp-red)] hover:underline"
            >
              <Activity className="size-3.5" /> Diagnóstico de tradução
            </button>
            <p className="font-sans mt-1 text-[11px] text-[var(--ink-500)]">
              Veja providers ativos, pins por volume e últimas chamadas — útil quando o cascade
              parece estar indo só pra 1 provider.
            </p>
          </div>
        </Card>

        <Card>
          <SectionHeader
            icon={Palette}
            title="Estilo de capa (IA)"
            description="Escolha os estilos de arte que aparecem ao gerar capa por IA. Nenhum marcado = a IA decide sozinha (automático). Marque vários pra escolher na hora; marque só um e o botão de capa já vai direto nele."
          />

          <div className="grid grid-cols-1 gap-x-4 gap-y-2 pt-2 sm:grid-cols-2">
            {COVER_STYLES.map((style) => {
              const checked = coverStyles.includes(style.id)
              return (
                <label
                  key={style.id}
                  className="font-sans flex cursor-pointer items-center gap-2.5 text-[13px] text-[var(--ink-700)]"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(v) =>
                      setCoverStyles((prev) =>
                        v === true ? [...prev, style.id] : prev.filter((id) => id !== style.id)
                      )
                    }
                  />
                  {style.label}
                </label>
              )
            })}
          </div>

          <p className="font-sans pt-3 text-[12px] text-[var(--ink-500)]">
            {coverStyles.length === 0
              ? 'Nenhum estilo fixo — toda capa nasce no modo automático.'
              : coverStyles.length === 1
                ? 'Um estilo marcado — o botão de capa usa ele direto, sem perguntar.'
                : `${coverStyles.length} estilos — o botão de capa abre um menu pra escolher.`}
          </p>
        </Card>

        <div className="flex items-center gap-4 pt-2">
          <Button type="submit" variant="default" size="lg" disabled={saving}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            Salvar configurações
          </Button>
          {msg && (
            <span
              className={
                msg.ok
                  ? 'font-sans inline-flex items-center gap-1.5 text-[13px] text-[var(--book-3)]'
                  : 'font-sans inline-flex items-center gap-1.5 text-[13px] text-[var(--ink-stamp)]'
              }
            >
              {msg.ok ? <CircleCheck className="size-4" /> : <CircleAlert className="size-4" />}
              {msg.text}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}

function ProviderKeyRow({
  label,
  provider,
  url,
  note,
  keySet,
  value,
  onChange,
  model,
  onModelChange,
  defaultModel
}: {
  label: string
  provider: string
  url: string
  note: string
  keySet: boolean
  value: string
  onChange: (s: string) => void
  model: string
  onModelChange: (s: string) => void
  defaultModel: string
}): React.JSX.Element {
  return (
    <div className="pt-3 first:pt-2">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={`key-${provider}`}>{label}</Label>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="font-sans text-[11px] text-[var(--stamp-red)] hover:underline"
        >
          pegar key →
        </a>
      </div>
      <Input
        id={`key-${provider}`}
        type="password"
        placeholder={keySet ? '•••••••• (definida)' : 'cole aqui'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5"
      />
      <p className="font-sans mt-1 text-[11px] text-[var(--ink-500)]">{note}</p>
      <details className="mt-2 group">
        <summary className="font-sans cursor-pointer text-[11px] text-[var(--ink-500)] hover:text-[var(--ink-700)]">
          ▸ modelo customizado (opcional)
        </summary>
        <Input
          id={`model-${provider}`}
          type="text"
          placeholder={defaultModel}
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          className="mt-1.5 font-mono text-[12px]"
        />
        <p className="font-sans mt-1 text-[10px] text-[var(--ink-400)]">
          Em branco = usa default <code className="font-mono">{defaultModel}</code>. Útil pra testar
          outro modelo ou quando default for descontinuado.
        </p>
      </details>
    </div>
  )
}
