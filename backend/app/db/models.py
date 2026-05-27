"""Tabelas ORM do cache (SQLAlchemy 2.0).

Sao distintas das dataclasses de dominio em ``app/models.py``: aqui e
persistencia, la e o que circula entre as camadas.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Novel(Base):
    __tablename__ = "novels"
    __table_args__ = (UniqueConstraint("source", "slug", name="uq_novel_source_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # nome do adapter (ex: "novelbin")
    slug: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    # --- Wiki Fandom (Etapa 5c) ---
    wiki_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # unknown = ainda nao tentou; detected = achou; none = nao tem wiki
    wiki_status: Mapped[str] = mapped_column(String(20), default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="novel",
        cascade="all, delete-orphan",
        order_by="Chapter.index",
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_index", name="uq_chapter_novel_idx"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    # nome do atributo = "index" (alinha com o dominio); coluna evita a palavra reservada
    index: Mapped[int] = mapped_column("chapter_index", Integer)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    html: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    novel: Mapped["Novel"] = relationship(back_populates="chapters")


class AppSettings(Base):
    """Configuracoes editaveis (linha unica, id=1). Inclui credenciais SMTP + traducao."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # sempre 1
    # --- SMTP / Kindle ---
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kindle_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # --- Traducao (Etapa 5) ---
    gemini_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    translation_model: Mapped[str] = mapped_column(String(50), default="gemini-2.5-flash")
    # --- Cascade (mai 2026) ---
    groq_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    cerebras_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Model overrides — None = usa default em factory.DEFAULT_MODELS
    groq_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    openrouter_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cerebras_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # CSV de provider names em ordem de preferencia (free primeiro)
    cascade_order: Mapped[str] = mapped_column(
        String(200), default="groq,openrouter,cerebras,gemini"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Glossary(Base):
    """Glossario por novel: personagens (com genero!), lugares, habilidades, termos do mundo.

    O tradutor injeta isto no system prompt p/ manter consistencia atraves dos capitulos.
    """

    __tablename__ = "glossary"
    __table_args__ = (UniqueConstraint("novel_id", "term", name="uq_glossary_novel_term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(255))            # original (en)
    canonical_pt: Mapped[str] = mapped_column(String(255))    # traducao canonica
    kind: Mapped[str] = mapped_column(String(30))             # character|place|ability|system_term|other
    gender: Mapped[str] = mapped_column(String(20), default="n/a")  # male|female|non-binary|unknown|n/a
    notes: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(10), default="medium")  # high|medium|low
    first_seen_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="llm")  # llm|wiki|manual
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeneratedCover(Base):
    """Cache de capas geradas por IA (BLOB)."""

    __tablename__ = "generated_covers"
    __table_args__ = (
        UniqueConstraint("novel_id", "volume_title", name="uq_cover_novel_volume"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    # "" significa cover-padrao-da-novel (sem volume_title)
    volume_title: Mapped[str] = mapped_column(String(500), default="")
    image_data: Mapped[bytes] = mapped_column()
    mime_type: Mapped[str] = mapped_column(String(50), default="image/png")
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WikiLookup(Base):
    """Cache de consultas a wiki Fandom (uma busca por termo por novel)."""

    __tablename__ = "wiki_lookups"
    __table_args__ = (UniqueConstraint("novel_id", "term", name="uq_wiki_novel_term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    term: Mapped[str] = mapped_column(String(255))
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TranslatedChapter(Base):
    """Cache de tradicao: capitulo X novel X lingua. Re-gerar EPUB nao re-traduz."""

    __tablename__ = "translated_chapters"
    __table_args__ = (
        UniqueConstraint(
            "novel_id", "chapter_index", "language", name="uq_translated_chapter"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(10))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    html: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(50))
    glossary_size: Mapped[int] = mapped_column(Integer, default=0)
    translated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VolumeStyleProfile(Base):
    """Perfil de estilo do volume — extraído na 1ª tradução, passado nas próximas.

    Garante coisas como: "este volume usa travessão pra diálogo + 'você' (não 'tu')
    + tom informal jovem + traduz 'damn' como 'porra'". Quando cascade troca de
    modelo, novo provider é forçado a manter as MESMAS escolhas.
    """

    __tablename__ = "volume_style_profiles"
    __table_args__ = (
        UniqueConstraint(
            "novel_id", "volume_title", "language",
            name="uq_style_nvl_vol_lang",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    volume_title: Mapped[str] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(10))
    # JSON com voice_tone, dialog_marker, second_person, etc.
    profile_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VolumeTranslatorPin(Base):
    """Provider/modelo que traduziu o 1º cap de um volume — fixa pra consistência.

    Cascade respeita esse pin: tenta o provider pinado primeiro, só cai pro
    proximo se estiver em cooldown. Garante que volume inteiro fique com mesma
    "voz" de modelo (Llama 3.3 sente diferente de Qwen 72B, etc).
    """

    __tablename__ = "volume_translator_pins"
    __table_args__ = (
        UniqueConstraint("novel_id", "volume_title", "language", name="uq_pin_nvl_vol_lang"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    # "" pra volume sem titulo (igual cover_cache)
    volume_title: Mapped[str] = mapped_column(String(500), default="")
    language: Mapped[str] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(40))  # "gemini" | "groq" | ...
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GeminiUsage(Base):
    """Cada chamada paga ao Gemini (texto ou imagem). Base do dashboard de custos."""

    __tablename__ = "gemini_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int | None] = mapped_column(
        ForeignKey("novels.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # ex: "translate_chapter", "cover_brief", "cover_image"
    op: Mapped[str] = mapped_column(String(40), index=True)
    # Provider lógico: "gemini" | "groq" | "openrouter" | "cerebras" | etc.
    # Nullable pra retro-compat com registros antigos (inferido de model nas queries).
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(80))
    chapter_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Custo em USD calculado no momento via tabela em translation/pricing.py.
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    # Quando provider falhou no cascade: erro humano-legivel (HTTP status + body).
    # NULL = chamada bem sucedida. Permite ver no diagnostico POR QUE o Groq
    # caiu sem ter que olhar logs do backend.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class GeneratedVolume(Base):
    """Volume EPUB ja gerado e persistido em disco.

    Substitui a dependencia de jobs em memoria pra listar "volumes baixados" na
    biblioteca — jobs sao efemeros, mas o .epub fica no filesystem e o registro
    aqui. Chave unica por (novel_id, output_path) torna saves idempotentes
    (re-rodar o mesmo job sobrescreve o .epub e atualiza translation_failed).
    """

    __tablename__ = "generated_volumes"
    __table_args__ = (
        UniqueConstraint("novel_id", "output_path", name="uq_volume_novel_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_id: Mapped[int] = mapped_column(
        ForeignKey("novels.id", ondelete="CASCADE"), index=True
    )
    volume_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_chapter: Mapped[int] = mapped_column(Integer)
    end_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    with_cover: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    translate_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    output_path: Mapped[str] = mapped_column(Text)
    translation_failed: Mapped[int] = mapped_column(Integer, default=0)
    # Guardado pra facilitar volta pra requisitar (Continuar tradução etc) sem
    # ter que ir ao Novel.
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
