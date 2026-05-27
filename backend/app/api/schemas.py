"""Modelos Pydantic da API (entrada/saida)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


def _assume_utc(value: datetime | None) -> datetime | None:
    """SQLite armazena DateTime(timezone=True) mas retorna naive — assume UTC.
    Sem isso o JSON sai como '2026-05-26T23:57:00' (sem Z), e o JS interpreta
    como local time → relógio aparece deslocado pelo offset do usuário."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class DownloadRequest(BaseModel):
    url: str
    start: int = Field(1, ge=1)
    end: int | None = Field(None, ge=1)
    with_cover: bool = True
    translate_to: str | None = None  # ex: "pt-BR"; None = sem traducao
    # Titulo opcional do volume. Se setado, vira o titulo do EPUB e o nome do
    # arquivo. Ex: "Volume 1 — O Sistema Vampirico"
    volume_title: str | None = None
    # Gerar capa custom via IA (Gemini Flash Image) baseado no conteudo do range.
    ai_cover: bool = False


class TranslationFailure(BaseModel):
    chapter: int
    title: str
    reason: str  # mensagem da exception (inclui finish_reason/block_reason p/ Gemini)


class UsageSummary(BaseModel):
    total_usd: float
    total_ops: int
    chapters_translated: int
    covers_generated: int
    last_30d_usd: float
    last_7d_usd: float
    avg_per_chapter_usd: float


class UsageDay(BaseModel):
    day: str  # YYYY-MM-DD
    cost_usd: float
    ops: int


class UsageByNovel(BaseModel):
    novel_id: int | None
    novel_title: str
    total_usd: float
    ops: int
    chapters_translated: int
    covers_generated: int


class UsageByProvider(BaseModel):
    provider: str
    total_usd: float
    ops: int


class VolumePinInfo(BaseModel):
    novel_id: int
    novel_title: str
    volume_title: str | None
    language: str
    provider: str
    model: str
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _force_utc(cls, v):
        return _assume_utc(v) if isinstance(v, datetime) else v


class RecentUsageInfo(BaseModel):
    op: str
    provider: str | None
    model: str
    novel_id: int | None
    chapter_index: int | None
    cost_usd: float
    error_message: str | None  # None = sucesso; preenchido = falha
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _force_utc(cls, v):
        return _assume_utc(v) if isinstance(v, datetime) else v


class TranslationDebugStatus(BaseModel):
    """Diagnóstico do estado atual do sistema de tradução."""

    active_providers: list[str]  # têm key configurada
    inactive_providers: list[str]  # sem key
    cascade_order: list[str]
    pins: list[VolumePinInfo]
    recent_usage: list[RecentUsageInfo]


class ChapterSummary(BaseModel):
    """Linha resumida na lista do editor."""
    index: int
    title_en: str
    title_pt: str | None
    has_translation: bool
    translation_source: str | None  # "manual" | "gemini-..." | None


class ChapterDetail(BaseModel):
    """Conteudo completo de um cap (EN + traducao, se houver)."""
    index: int
    title_en: str
    html_en: str
    title_pt: str | None
    html_pt: str | None
    translation_source: str | None
    language: str | None


class ChapterTranslationUpdate(BaseModel):
    """Body do PUT — usuario editou a tradução."""
    title: str
    html: str
    language: str  # ex: "pt-BR"


class VolumeOut(BaseModel):
    """Volume EPUB ja gerado e persistido — fonte da verdade pra Biblioteca."""

    id: int
    novel_id: int
    volume_title: str | None
    start: int
    end: int | None
    with_cover: bool
    ai_cover: bool
    translate_to: str | None
    output_path: str
    translation_failed: int
    source_url: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _force_utc(cls, v):
        return _assume_utc(v) if isinstance(v, datetime) else v


class JobStatus(BaseModel):
    id: str
    url: str
    start: int
    end: int | None
    with_cover: bool
    translate_to: str | None
    volume_title: str | None
    ai_cover: bool
    status: str  # queued | running | done | error
    stage: str   # idle | download | translate | cover
    done: int
    total: int
    title: str | None  # titulo da novel (quando conhecido)
    current: str | None  # capitulo atual em progresso
    output_path: str | None
    error: str | None
    # Quantos capitulos a traducao falhou (mantidos em EN). 0 = perfeito.
    translation_failed: int
    # Detalhe por capitulo que falhou (mesmo length que translation_failed).
    # UI mostra num expand pra o usuario entender por que cada cap ficou em EN.
    translation_failures: list[TranslationFailure] = []
    # Id no SQLite do volume gerado (None enquanto job nao terminou). UI usa
    # pra chamar endpoints persistentes (sobrevive a restart do backend).
    volume_id: int | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _force_utc(cls, v):
        return _assume_utc(v) if isinstance(v, datetime) else v


class SiteInfo(BaseModel):
    name: str
    domains: list[str]


class VolumePreview(BaseModel):
    """Agrupamento de capítulos por volume detectado na novel.

    Permite UI mostrar "Volume 3 — caps 201-300" como opção pré-pronta
    no dropdown ao invés do user calcular start/end manualmente.
    """
    name: str  # ex: "Volume 1: Calamidade Vermelha"
    start: int
    end: int
    chapter_count: int


class NovelPreviewRequest(BaseModel):
    url: str


class NovelPreviewOut(BaseModel):
    """Snapshot da novel pra UI exibir antes da captura (sem custo de Gemini)."""
    title: str
    author: str | None
    cover_url: str | None
    description: str | None
    total_chapters: int
    volumes: list[VolumePreview]  # vazio se adapter nao detecta volumes


class NovelSummary(BaseModel):
    id: int
    source: str
    slug: str
    title: str
    author: str | None
    cover_url: str | None
    chapters: int


class NovelDetail(BaseModel):
    id: int
    source: str
    slug: str
    title: str
    author: str | None
    cover_url: str | None
    description: str | None
    source_url: str
    wiki_url: str | None
    wiki_status: str
    chapters: int


class SettingsOut(BaseModel):
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password_set: bool  # nunca expomos a senha
    smtp_use_tls: bool
    smtp_from: str | None
    kindle_email: str | None
    # --- Traducao ---
    gemini_api_key_set: bool  # nunca expomos a chave
    target_language: str
    translation_model: str
    # --- Cascade providers (mai 2026) ---
    groq_api_key_set: bool
    openrouter_api_key_set: bool
    cerebras_api_key_set: bool
    # Models por provider (None = default em factory.DEFAULT_MODELS)
    groq_model: str | None
    openrouter_model: str | None
    cerebras_model: str | None
    # Defaults pra UI mostrar como placeholder
    default_models: dict[str, str]
    cascade_order: list[str]  # ex: ["groq","openrouter","cerebras","gemini"]


class SettingsUpdate(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_from: str | None = None
    kindle_email: str | None = None
    gemini_api_key: str | None = None
    target_language: str | None = None
    translation_model: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    cerebras_api_key: str | None = None
    groq_model: str | None = None
    openrouter_model: str | None = None
    cerebras_model: str | None = None
    cascade_order: list[str] | None = None


class GlossaryEntryOut(BaseModel):
    term: str
    canonical_pt: str
    kind: str
    gender: str
    notes: str
    confidence: str
    first_seen_chapter: int | None
    source: str
