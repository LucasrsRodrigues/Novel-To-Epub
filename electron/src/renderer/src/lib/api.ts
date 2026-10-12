// Cliente HTTP da API do backend (FastAPI).

function resolveBase(): string {
  // No Electron, o main injeta a URL (porta dinamica) via preload.
  const injected = typeof window !== 'undefined' ? window.api?.backendUrl : undefined
  if (injected) return injected
  // Fora do Electron (dev no browser): env ou padrao.
  return (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000'
}

const API_BASE = resolveBase()

// Token da API local (o main gera um a cada abertura). Vai no header X-Api-Token
// nas chamadas via http() e como ?token= nas URLs usadas direto em <img>,
// <a download>, fetch cru e WebSocket (que não mandam header). Vazio fora do
// Electron: o backend só exige token quando NOVEL_API_TOKEN está definido.
const API_TOKEN =
  (typeof window !== 'undefined' ? window.api?.apiToken : undefined) ||
  ((import.meta.env.VITE_API_TOKEN as string | undefined) ?? '')

function withToken(url: string): string {
  if (!API_TOKEN) return url
  return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(API_TOKEN)}`
}

export type JobStatusKind = 'queued' | 'running' | 'done' | 'error' | 'cancelled' | 'interrupted' // captura pendente re-hidratada após restart do backend

export interface TranslationFailure {
  chapter: number
  title: string
  reason: string // mensagem da exception (inclui finish_reason/block_reason p/ Gemini)
}

export interface DownloadFailure {
  chapter: number
  title: string
  reason: string // por que o cap não pôde ser baixado (404, DOM mudou, mirror quebrado)
}

export interface JobStatus {
  id: string
  url: string
  start: number
  end: number | null
  with_cover: boolean
  translate_to: string | null
  volume_title: string | null
  ai_cover: boolean
  status: JobStatusKind
  stage: string // idle | download | translate | cover
  done: number
  total: number
  title: string | null
  current: string | null
  output_path: string | null
  error: string | null
  translation_failed: number // caps que ficaram em EN (falha)
  translation_failures: TranslationFailure[] // detalhe por cap (preenchido qdo job termina)
  download_failed: number // caps que não puderam ser baixados (pulados, fora do EPUB)
  download_failures: DownloadFailure[] // detalhe por cap pulado (preenchido qdo job termina)
  cover_error: string | null // motivo da falha de capa por IA (None = ok/não pedida)
  volume_id: number | null // id do volume persistido (None enquanto job nao terminou)
  created_at: string
  updated_at: string
}

export interface DownloadRequest {
  url: string
  start?: number
  end?: number | null
  with_cover?: boolean
  translate_to?: string | null
  volume_title?: string | null
  ai_cover?: boolean
  // Id do estilo de arte da capa (ver lib/coverStyles). undefined/null = IA decide.
  cover_style?: string | null
  // Índices de capítulo a ignorar neste volume (ex: [1] pula o cap-lixo inicial).
  skip_chapters?: number[]
  // Recaptura mantendo a capa: reusa a capa já cacheada do volume (sem gerar).
  preserve_cover?: boolean
  // Quando setado, o volume com este id é removido (registro + .epub) assim que
  // o novo .epub nascer ok. Usado p/ "traduzir no lugar" (substitui o original).
  replace_volume_id?: number | null
}

export interface SiteInfo {
  name: string
  domains: string[]
}

export interface VolumePreview {
  name: string
  start: number
  end: number
  chapter_count: number
}

export interface NovelPreview {
  title: string
  author: string | null
  cover_url: string | null
  description: string | null
  total_chapters: number
  volumes: VolumePreview[] // [] se adapter não detecta volumes
  // Estilo de capa default da novel (se já capturada antes). null = nova/sem default.
  default_cover_style: string | null
}

export interface NovelSummary {
  id: number
  source: string
  slug: string
  title: string
  author: string | null
  cover_url: string | null
  chapters: number
}

export interface NovelDetail extends NovelSummary {
  description: string | null
  source_url: string
  wiki_url: string | null
  wiki_status: string
  default_cover_style: string | null
}

export interface AppSettingsView {
  smtp_host: string | null
  smtp_port: number
  smtp_user: string | null
  smtp_password_set: boolean
  smtp_use_tls: boolean
  smtp_from: string | null
  kindle_email: string | null
  gemini_api_key_set: boolean
  target_language: string
  translation_model: string
  groq_api_key_set: boolean
  openrouter_api_key_set: boolean
  cerebras_api_key_set: boolean
  groq_model: string | null
  openrouter_model: string | null
  cerebras_model: string | null
  default_models: Record<string, string>
  cascade_order: string[]
  cover_styles_enabled: string[]
  // Gemini via Vertex AI (consome crédito do Google Cloud)
  gemini_use_vertex: boolean
  gemini_vertex_project: string | null
  gemini_vertex_location: string
  gemini_vertex_credentials_set: boolean
}

export interface SettingsUpdate {
  smtp_host?: string | null
  smtp_port?: number
  smtp_user?: string | null
  smtp_password?: string | null
  smtp_use_tls?: boolean
  smtp_from?: string | null
  kindle_email?: string | null
  gemini_api_key?: string | null
  target_language?: string
  translation_model?: string
  groq_api_key?: string | null
  openrouter_api_key?: string | null
  cerebras_api_key?: string | null
  groq_model?: string | null
  openrouter_model?: string | null
  cerebras_model?: string | null
  cascade_order?: string[]
  cover_styles_enabled?: string[]
  // Gemini via Vertex AI
  gemini_use_vertex?: boolean
  gemini_vertex_project?: string | null
  gemini_vertex_location?: string | null
  gemini_vertex_credentials_path?: string | null
}

export type CoverKind = 'titled' | 'raw' | 'phone' | 'pc' | 'pc_hd'
export type WallpaperFmt = 'phone' | 'pc' | 'pc_hd'

export interface CoverOut {
  id: number
  novel_id: number
  volume_title: string | null
  mime_type: string
  has_raw: boolean
  cover_style: string | null // estilo de arte (id ou spec); null = automático/antiga
  native_aspects: string[] // ex: ["16:9"]
  created_at: string
}

export interface ChapterSummary {
  index: number
  title_en: string
  title_pt: string | null
  has_translation: boolean
  translation_source: string | null // 'manual' | 'gemini-...' | null
}

export interface ChapterDetail {
  index: number
  title_en: string
  html_en: string
  title_pt: string | null
  html_pt: string | null
  translation_source: string | null
  language: string | null
}

export interface Mirror {
  id: number
  novel_id: number
  source: string // nome do adapter (ex: "novelfull")
  source_url: string
  priority: number
}

export interface VolumeOut {
  id: number
  novel_id: number
  volume_title: string | null
  start: number
  end: number | null
  with_cover: boolean
  ai_cover: boolean
  translate_to: string | null
  output_path: string
  translation_failed: number
  skip_chapters: number[]
  source_url: string
  created_at: string
  updated_at: string
}

export interface UsageSummary {
  total_usd: number
  total_ops: number
  chapters_translated: number
  covers_generated: number
  last_30d_usd: number
  last_7d_usd: number
  avg_per_chapter_usd: number
}

export interface UsageDay {
  day: string
  cost_usd: number
  ops: number
}

export interface UsageByNovel {
  novel_id: number | null
  novel_title: string
  total_usd: number
  ops: number
  chapters_translated: number
  covers_generated: number
}

export interface UsageByProvider {
  provider: string
  total_usd: number
  ops: number
}

export interface VolumePinInfo {
  novel_id: number
  novel_title: string
  volume_title: string | null
  language: string
  provider: string
  model: string
  created_at: string
}

export interface RecentUsageInfo {
  op: string
  provider: string | null
  model: string
  novel_id: number | null
  chapter_index: number | null
  cost_usd: number
  error_message: string | null // null = sucesso; preenchido = falha do provider
  created_at: string
}

export interface TranslationDebugStatus {
  active_providers: string[]
  inactive_providers: string[]
  cascade_order: string[]
  pins: VolumePinInfo[]
  recent_usage: RecentUsageInfo[]
}

export interface GlossaryEntry {
  term: string
  canonical_pt: string
  kind: string
  gender: string
  notes: string
  confidence: string
  first_seen_chapter: number | null
  source: string
}

export interface GlossaryCleanupReport {
  novel_id: number
  total: number
  duplicates_removed: number
  common_words_ignored: number
  junk_ignored: number
  already_ignored: number
  remaining_active: number
  merges: { kept: string; removed: string[] }[]
  common_words: string[]
  junk: string[]
  applied: boolean
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(API_TOKEN ? { 'X-Api-Token': API_TOKEN } : {})
    },
    ...init
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // resposta sem corpo JSON
    }
    throw new Error(detail)
  }
  // Respostas sem corpo (204 No Content, ex: DELETE) ou vazias não são JSON —
  // tentar `res.json()` aí explode com "Unexpected end of JSON input".
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  base: API_BASE,
  health: () => http<{ status: string; version: string }>('/api/health'),
  sites: () => http<SiteInfo[]>('/api/sites'),
  previewNovel: (url: string) =>
    http<NovelPreview>('/api/preview-novel', { method: 'POST', body: JSON.stringify({ url }) }),
  createDownload: (req: DownloadRequest) =>
    http<JobStatus>('/api/downloads', { method: 'POST', body: JSON.stringify(req) }),
  listDownloads: () => http<JobStatus[]>('/api/downloads'),
  getDownload: (id: string) => http<JobStatus>(`/api/downloads/${id}`),
  cancelDownload: (id: string) =>
    http<JobStatus>(`/api/downloads/${id}/cancel`, { method: 'POST' }),
  resumeDownload: (id: string) =>
    http<JobStatus>(`/api/downloads/${id}/resume`, { method: 'POST' }),
  discardDownload: (id: string) => http<void>(`/api/downloads/${id}`, { method: 'DELETE' }),
  sendToKindle: (id: string) =>
    http<{ status: string; to: string }>(`/api/downloads/${id}/kindle`, { method: 'POST' }),
  regenerateCover: (id: string, coverStyle?: string | null) =>
    http<JobStatus>(`/api/downloads/${id}/regenerate-cover`, {
      method: 'POST',
      body: JSON.stringify({ cover_style: coverStyle ?? null })
    }),
  library: () => http<NovelSummary[]>('/api/library'),
  getNovelDetail: (novelId: number) => http<NovelDetail>(`/api/library/${novelId}`),
  getNovelVolumes: (novelId: number) => http<VolumeOut[]>(`/api/library/${novelId}/volumes`),
  getGlossary: (novelId: number) => http<GlossaryEntry[]>(`/api/library/${novelId}/glossary`),
  // Limpeza do glossário: sem apply só simula (relatório); com apply aplica.
  cleanGlossary: (novelId: number, apply: boolean) =>
    http<GlossaryCleanupReport>(`/api/library/${novelId}/glossary/clean?apply=${apply}`, {
      method: 'POST'
    }),
  listMirrors: (novelId: number) => http<Mirror[]>(`/api/library/${novelId}/mirrors`),
  addMirror: (novelId: number, url: string) =>
    http<Mirror>(`/api/library/${novelId}/mirrors`, {
      method: 'POST',
      body: JSON.stringify({ url })
    }),
  deleteMirror: (mirrorId: number) => http<void>(`/api/mirrors/${mirrorId}`, { method: 'DELETE' }),
  volumeFileUrl: (id: number) => withToken(`${API_BASE}/api/volumes/${id}/file`),
  allVolumesZipUrl: (novelId: number) =>
    withToken(`${API_BASE}/api/library/${novelId}/volumes.zip`),
  sendAllToKindle: (novelId: number) =>
    http<{
      to: string
      sent: number
      total: number
      results: { volume_id: number; title: string; ok: boolean; error?: string }[]
    }>(`/api/library/${novelId}/kindle-all`, { method: 'POST' }),
  // --- Galeria de capas ---
  listCovers: (novelId: number) => http<CoverOut[]>(`/api/library/${novelId}/covers`),
  coverFileUrl: (
    coverId: number,
    kind: CoverKind,
    opts: { native?: boolean; download?: boolean } = {}
  ): string => {
    const q = new URLSearchParams({ kind })
    if (opts.native) q.set('native', 'true')
    if (opts.download) q.set('download', 'true')
    return withToken(`${API_BASE}/api/covers/${coverId}/file?${q.toString()}`)
  },
  generateNativeWallpaper: (coverId: number, fmt: WallpaperFmt) =>
    http<CoverOut>(`/api/covers/${coverId}/native?fmt=${fmt}`, { method: 'POST' }),
  regenerateCoverArt: (coverId: number) =>
    http<CoverOut>(`/api/covers/${coverId}/regenerate-art`, { method: 'POST' }),
  sendVolumeToKindle: (id: number) =>
    http<{ status: string; to: string }>(`/api/volumes/${id}/kindle`, { method: 'POST' }),
  regenerateVolumeCover: (id: number, coverStyle?: string | null) =>
    http<JobStatus>(`/api/volumes/${id}/regenerate-cover`, {
      method: 'POST',
      body: JSON.stringify({ cover_style: coverStyle ?? null })
    }),
  regenerateAllCovers: (novelId: number, coverStyle?: string | null) =>
    http<JobStatus[]>(`/api/library/${novelId}/regenerate-all-covers`, {
      method: 'POST',
      body: JSON.stringify({ cover_style: coverStyle ?? null })
    }),
  deleteVolume: (id: number) => http<void>(`/api/volumes/${id}`, { method: 'DELETE' }),
  rebuildVolume: (id: number) => http<VolumeOut>(`/api/volumes/${id}/rebuild`, { method: 'POST' }),
  renameVolume: (id: number, volumeTitle: string) =>
    http<VolumeOut>(`/api/volumes/${id}/rename`, {
      method: 'POST',
      body: JSON.stringify({ volume_title: volumeTitle })
    }),
  listChapters: (
    novelId: number,
    opts: { language?: string; start?: number; end?: number } = {}
  ) => {
    const q = new URLSearchParams()
    if (opts.language) q.set('language', opts.language)
    if (opts.start != null) q.set('start', String(opts.start))
    if (opts.end != null) q.set('end', String(opts.end))
    const qs = q.toString() ? `?${q.toString()}` : ''
    return http<ChapterSummary[]>(`/api/library/${novelId}/chapters${qs}`)
  },
  getChapter: (novelId: number, idx: number, language?: string) => {
    const qs = language ? `?language=${encodeURIComponent(language)}` : ''
    return http<ChapterDetail>(`/api/library/${novelId}/chapters/${idx}${qs}`)
  },
  saveChapterTranslation: (
    novelId: number,
    idx: number,
    body: { title: string; html: string; language: string }
  ) =>
    http<ChapterDetail>(`/api/library/${novelId}/chapters/${idx}/translation`, {
      method: 'PUT',
      body: JSON.stringify(body)
    }),
  deleteChapterTranslation: (novelId: number, idx: number, language: string) =>
    http<void>(
      `/api/library/${novelId}/chapters/${idx}/translation?language=${encodeURIComponent(language)}`,
      {
        method: 'DELETE'
      }
    ),
  usageSummary: () => http<UsageSummary>('/api/usage/summary'),
  usageByDay: (days = 30) => http<UsageDay[]>(`/api/usage/by-day?days=${days}`),
  usageByNovel: () => http<UsageByNovel[]>('/api/usage/by-novel'),
  usageByProvider: () => http<UsageByProvider[]>('/api/usage/by-provider'),
  translationDebugStatus: () => http<TranslationDebugStatus>('/api/debug/translation-status'),
  resetVolumeTranslatorPin: (volumeId: number) =>
    http<void>(`/api/volumes/${volumeId}/translator-pin`, { method: 'DELETE' }),
  getSettings: () => http<AppSettingsView>('/api/settings'),
  updateSettings: (body: SettingsUpdate) =>
    http<AppSettingsView>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
  fileUrl: (id: string) => withToken(`${API_BASE}/api/downloads/${id}/file`)
}

export function wsUrl(): string {
  return withToken(API_BASE.replace(/^http/, 'ws') + '/ws/progress')
}
