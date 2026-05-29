"""Engine + sessao SQLAlchemy sobre SQLite.

Lazy: o engine so e criado no primeiro uso, ja com os diretorios de dados
garantidos e o enforcement de foreign keys ligado (SQLite nao liga por padrao).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings.ensure_dirs()
        _engine = create_engine(f"sqlite:///{settings.db_path}", future=True)
    return _engine


def init_db() -> None:
    """Cria as tabelas se nao existirem + migra colunas novas (idempotente)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)


# ALTER TABLE ADD COLUMN para tabelas que ja existem (create_all so cria tabelas novas).
# Lista de (tabela, coluna, DDL). Idempotente: pula colunas que ja existem.
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("app_settings", "gemini_api_key", "TEXT"),
    ("app_settings", "target_language", "VARCHAR(10) DEFAULT 'pt-BR'"),
    ("app_settings", "translation_model", "VARCHAR(50) DEFAULT 'gemini-2.5-flash'"),
    ("novels", "wiki_url", "TEXT"),
    ("novels", "wiki_status", "VARCHAR(20) DEFAULT 'unknown'"),
    ("novels", "default_cover_style", "VARCHAR(60)"),
    # Ancora de coesao da serie (paleta + luz) + estilo pra o qual foi construida.
    ("novels", "series_palette", "TEXT"),
    ("novels", "series_anchor_style", "VARCHAR(60)"),
    # Arte crua (sem texto) das capas — pra download "sem texto" e wallpapers.
    ("generated_covers", "image_data_raw", "BLOB"),
    # Cascade providers (mai 2026)
    ("app_settings", "groq_api_key", "TEXT"),
    ("app_settings", "openrouter_api_key", "TEXT"),
    ("app_settings", "cerebras_api_key", "TEXT"),
    ("app_settings", "cascade_order", "VARCHAR(200) DEFAULT 'groq,openrouter,cerebras,gemini'"),
    ("app_settings", "cover_styles_enabled", "VARCHAR(500) DEFAULT ''"),
    # Provider tracking pra breakdown no dashboard
    ("gemini_usage", "provider", "VARCHAR(40)"),
    # Erro humano-legivel quando provider falha no cascade
    ("gemini_usage", "error_message", "TEXT"),
    # Model overrides por provider
    ("app_settings", "groq_model", "VARCHAR(120)"),
    ("app_settings", "openrouter_model", "VARCHAR(120)"),
    ("app_settings", "cerebras_model", "VARCHAR(120)"),
]


def _migrate(engine: Engine) -> None:
    with engine.begin() as conn:
        for table, column, ddl in _PENDING_COLUMNS:
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def get_session() -> Session:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory()
