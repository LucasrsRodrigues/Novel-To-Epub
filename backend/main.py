"""Entrypoint da CLI.

Uso:
    python main.py sites                         # lista adapters registrados
    python main.py detect <url>                  # mostra qual adapter atende a URL
    python main.py download --url <url> --start 1 --end 100 --output ./out
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from app.logging_conf import configure_logging
from app.orchestrator import download_to_epub
from app.scraper.registry import registry

app = typer.Typer(add_completion=False, help="Novel Scraper to EPUB")


@app.callback()
def _main() -> None:
    configure_logging()


@app.command()
def sites() -> None:
    """Lista os adapters de site registrados."""
    adapters = registry.adapters
    if not adapters:
        typer.echo("Nenhum adapter registrado ainda.")
        raise typer.Exit()
    for cls in adapters:
        typer.echo(f"- {cls.name}: {', '.join(cls.domains)}")


@app.command()
def detect(url: str) -> None:
    """Mostra qual adapter atende a URL informada."""
    for cls in registry.adapters:
        if cls.matches(url):
            typer.echo(f"{url} -> {cls.name}")
            raise typer.Exit()
    typer.secho(f"Nenhum adapter atende: {url}", fg=typer.colors.RED)
    raise typer.Exit(code=1)


@app.command()
def download(
    url: str = typer.Option(..., "--url", "-u", help="URL da pagina da novel"),
    start: int = typer.Option(1, "--start", "-s", min=1, help="Primeiro capitulo"),
    end: Optional[int] = typer.Option(
        None, "--end", "-e", help="Ultimo capitulo (padrao: ate o fim)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Diretorio de saida do .epub"
    ),
    no_cover: bool = typer.Option(False, "--no-cover", help="Nao incluir capa"),
    translate_to: Optional[str] = typer.Option(
        None, "--translate-to", "-t", help="Lingua de destino (ex: pt-BR). Omita p/ nao traduzir."
    ),
) -> None:
    """Baixa um intervalo de capitulos e gera um .epub (opcionalmente traduzido)."""
    columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ]
    with Progress(*columns) as prog:
        task = prog.add_task("preparando...", total=None)

        def on_progress(stage: str, done: int, total: int, title: str, from_cache: bool) -> None:
            tag = "cache" if from_cache else stage  # "cache" | "download" | "translate"
            prog.update(
                task,
                total=total,
                completed=done,
                description=f"[{tag}] {title[:45]}",
            )

        try:
            path = asyncio.run(
                download_to_epub(
                    url,
                    start=start,
                    end=end,
                    output_dir=output,
                    with_cover=not no_cover,
                    progress=on_progress,
                    translate_to=translate_to,
                )
            )
        except Exception as exc:
            typer.secho(f"Falhou: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    typer.secho(f"EPUB gerado: {path}", fg=typer.colors.GREEN)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host do servidor"),
    port: int = typer.Option(8000, "--port", "-p", help="Porta"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload (dev)"),
) -> None:
    """Sobe a API FastAPI (REST + WebSocket)."""
    import uvicorn
    import app.api.server  # noqa: F401  # garante que o bundler (PyInstaller) inclua o modulo

    uvicorn.run("app.api.server:app", host=host, port=port, reload=reload)


@app.command(name="translate-test")
def translate_test(
    url: str = typer.Option(..., "--url", "-u", help="URL da novel"),
    chapter: int = typer.Option(1, "--chapter", "-c", help="Indice do capitulo (1-based)"),
    target: str = typer.Option("pt-BR", "--target", help="Lingua de destino"),
) -> None:
    """Traduz UM capitulo (debug). Usa cache; salva no glossario."""
    import asyncio
    import os
    from slugify import slugify

    from app.db.cache import ChapterCache
    from app.db.settings_store import SettingsStore
    from app.scraper.http import HttpClient
    from app.scraper.registry import registry
    from app.translation.gemini_provider import GeminiProvider
    from app.translation.translator import Translator

    cfg = SettingsStore().get()
    api_key = os.environ.get("GEMINI_API_KEY") or cfg.get("gemini_api_key")
    if not api_key:
        typer.secho(
            "Configure GEMINI_API_KEY no env OU em /api/settings antes de traduzir.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    model = cfg.get("translation_model") or "gemini-2.5-flash"

    async def run() -> None:
        cache = ChapterCache()
        async with HttpClient(min_delay=0.3, max_delay=0.6) as client:
            adapter = registry.resolve(url, client)
            meta = await adapter.fetch_novel(url)
            slug = meta.slug or slugify(meta.title)
            novel_id = cache.upsert_novel(adapter.name, slug, meta)

            ref = next((r for r in meta.chapters if r.index == chapter), None)
            if ref is None:
                typer.secho(f"capitulo {chapter} fora do intervalo (1..{len(meta.chapters)})", fg=typer.colors.RED)
                raise typer.Exit(code=1)

            ch = cache.get_chapter(novel_id, chapter)
            if ch is None:
                ch = await adapter.fetch_chapter(ref)
                cache.save_chapter(novel_id, ch)

            provider = GeminiProvider(api_key=api_key, model=model)
            translator = Translator(provider=provider, target_language=target)
            translated_title, translated_html = await translator.translate(
                novel_id=novel_id,
                novel_title=meta.title,
                novel_slug=slug,
                chapter_index=chapter,
                chapter_title=ch.title,
                chapter_html=ch.html,
            )

        # mostra primeiros paragrafos lado-a-lado
        import re

        def first_ps(html: str, n: int = 3) -> list[str]:
            return [p[:180] for p in re.findall(r"<p>(.*?)</p>", html, re.S)[:n]]

        typer.echo(f"\n=== ORIGINAL ({ch.title}) ===")
        for p in first_ps(ch.html):
            typer.echo(f"  {p}")
        typer.echo(f"\n=== TRADUZIDO ({translated_title}) ===")
        for p in first_ps(translated_html):
            typer.echo(f"  {p}")

        from app.translation.glossary import GlossaryStore
        gloss = GlossaryStore().list_for_novel(novel_id)
        typer.echo(f"\n=== GLOSSARIO ({len(gloss)} entradas) ===")
        for e in gloss[:15]:
            extras = []
            if e.gender not in ("n/a", "unknown"):
                extras.append(e.gender)
            if e.notes:
                extras.append(e.notes[:50])
            tag = f" ({', '.join(extras)})" if extras else ""
            typer.echo(f"  [{e.kind:11}] {e.term:25} -> {e.canonical_pt}{tag} <{e.confidence}>")

    asyncio.run(run())


if __name__ == "__main__":
    app()
