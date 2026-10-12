"""Builder unico do genai.Client honrando o modo Vertex (settings/env).

Traducao E geracao de capa usam Gemini. Centralizar a criacao do client aqui
evita que um caminho fique no AI Studio (api_key) enquanto o outro vai pro Vertex
— foi exatamente o que causou o 401 UNAUTHENTICATED na capa depois que as keys do
AI Studio foram apagadas. Com Vertex ligado, AMBOS consomem o credito do GCP.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types

# Teto por chamada (traducao de capitulo longo com JSON estruturado ou geracao de
# imagem levam ~30-90s). Sem isso, uma conexao pendurada travava o worker unico
# — e com ele a fila inteira — indefinidamente.
GEMINI_TIMEOUT_S = 180


class GeminiTimeoutError(RuntimeError):
    """O Gemini nao respondeu dentro de ``GEMINI_TIMEOUT_S``."""


def vertex_cfg(cfg: dict) -> tuple[bool, str | None, str, str | None]:
    """Le a config do modo Vertex (env tem prioridade sobre o DB).

    Vertex usa service account (ou ADC), nao API key, e e faturado no billing do
    projeto GCP — e o jeito de consumir credito do Google Cloud.
    Retorna ``(use_vertex, project, location, credentials_path)``.
    """

    def _truthy(v: object) -> bool:
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    use = _truthy(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "")) or _truthy(
        cfg.get("gemini_use_vertex", "")
    )
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
        or cfg.get("gemini_vertex_project")
    )
    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or cfg.get("gemini_vertex_location")
        or "us-central1"
    )
    credentials_path = cfg.get("gemini_vertex_credentials_path") or None
    return use, project, location, credentials_path


def make_genai_client(
    *,
    use_vertex: bool,
    project: str | None = None,
    location: str = "us-central1",
    credentials_path: str | None = None,
    api_key: str | None = None,
) -> genai.Client:
    """Cria o ``genai.Client`` no modo certo.

    - Vertex: service account carregada explicitamente do JSON (nao depende da env
      GOOGLE_APPLICATION_CREDENTIALS -> funciona no app empacotado). Sem path, cai
      no ADC.
    - AI Studio: usa ``api_key``.
    """
    if use_vertex:
        if not project:
            raise ValueError(
                "Vertex habilitado mas sem project — configure gemini_vertex_project."
            )
        credentials = None
        if credentials_path:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
            http_options=_http_options(),
        )
    if not api_key:
        raise ValueError("Gemini sem API key (modo AI Studio).")
    return genai.Client(api_key=api_key, http_options=_http_options())


def _http_options() -> types.HttpOptions:
    return types.HttpOptions(timeout=GEMINI_TIMEOUT_S * 1000)  # SDK usa ms
