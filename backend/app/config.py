"""Configuracoes da aplicacao.

Tudo pode ser sobrescrito por variaveis de ambiente com prefixo ``NOVEL_``
ou por um arquivo ``.env`` na raiz do backend. Ex: ``NOVEL_MIN_DELAY=2``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  (este arquivo vive em backend/app/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BACKEND_DIR / "data"

# User-Agent realista (Chrome em macOS) para nao parecer bot.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOVEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Rede / rate limit ---
    user_agent: str = DEFAULT_USER_AGENT
    min_delay: float = Field(1.0, ge=0, description="Delay minimo entre requests (s)")
    max_delay: float = Field(3.0, ge=0, description="Delay maximo entre requests (s)")
    request_timeout: float = Field(30.0, gt=0)
    max_retries: int = Field(3, ge=0)

    # --- Paths ---
    data_dir: Path = DEFAULT_DATA_DIR

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = False  # True = saida JSON (util quando virar servidor/servico)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cache.sqlite3"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "epubs"

    def ensure_dirs(self) -> None:
        """Cria os diretorios de dados se nao existirem."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
