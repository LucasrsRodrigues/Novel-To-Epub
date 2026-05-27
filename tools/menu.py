#!/usr/bin/env python3
"""Menu interativo do epub_scrap.

Não duplica lógica — só dispara alvos do Makefile com argumentos coletados
via prompts. Rode com `make menu` (recomendado) ou diretamente:

    backend/.venv/bin/python tools/menu.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
except ImportError:
    print("rich não instalado. Rode: make install", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
console = Console()

# Estado da sessão (sobrevive entre ações do mesmo run, evita re-digitar URL)
state: dict[str, str] = {
    "url": "",
    "target": "pt-BR",
}


# ---------------------------------------------------------------------------
# Infra
# ---------------------------------------------------------------------------


@dataclass
class Option:
    label: str
    action: Callable[[], None]
    hint: str = ""


def run(*make_args: str) -> int:
    """Dispara `make <args>` a partir da raiz do projeto."""
    cmd = ["make", *make_args]
    console.rule(f"[dim]$ {' '.join(cmd)}[/]", style="dim")
    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        console.print("\n[yellow]interrompido[/]")
        return 130
    finally:
        console.rule(style="dim")


def header() -> None:
    console.clear()
    console.print(
        Panel.fit(
            "[bold cyan]epub_scrap[/]   [dim]·[/]   Novel → EPUB\n"
            "[dim italic]menu interativo[/]",
            border_style="cyan",
            padding=(0, 2),
        )
    )


def ask_url(label: str = "URL da novel") -> str | None:
    default = state["url"] or None
    url = Prompt.ask(f"[bold]{label}[/]", default=default)
    if not url or not url.strip():
        return None
    state["url"] = url.strip()
    return url.strip()


def pause() -> None:
    console.print("\n[dim](Enter para voltar ao menu)[/]", end="")
    try:
        input()
    except EOFError:
        pass


def show_menu(title: str, options: list[Option]) -> None:
    while True:
        header()
        console.print(f"\n[bold]{title}[/]\n")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column()
        table.add_column(style="dim italic")
        for i, opt in enumerate(options, 1):
            table.add_row(str(i), opt.label, opt.hint)
        table.add_row("0", "[dim]voltar[/]", "")
        console.print(table)

        if state["url"]:
            console.print(f"\n[dim]URL atual: {state['url']}[/]")

        raw = Prompt.ask("\n[bold cyan]›[/]", default="0").strip().lower()
        if raw in {"0", "q", ""}:
            return
        try:
            idx = int(raw) - 1
            if not (0 <= idx < len(options)):
                raise ValueError
        except ValueError:
            console.print("[red]opção inválida[/]")
            pause()
            continue

        options[idx].action()
        pause()


# ---------------------------------------------------------------------------
# Ações (cada uma dispara um alvo do Makefile)
# ---------------------------------------------------------------------------


def act_sites() -> None:
    run("sites")


def act_detect() -> None:
    url = ask_url()
    if url:
        run("detect", f"URL={url}")


def act_download() -> None:
    url = ask_url()
    if not url:
        return
    start = IntPrompt.ask("[bold]Capítulo inicial[/]", default=1)
    end_raw = Prompt.ask("[bold]Capítulo final[/] [dim](vazio = até o fim)[/]", default="")
    no_cover = Confirm.ask("Sem capa? [dim](mais rápido p/ testar adapter)[/]", default=True)
    debug = Confirm.ask("Logs em [bold]DEBUG[/]?", default=False)

    args = ["download", f"URL={url}", f"START={start}", f"NO_COVER={'1' if no_cover else '0'}"]
    if end_raw.strip():
        args.append(f"END={end_raw.strip()}")
    if debug:
        args.append("LOG=DEBUG")
    run(*args)


def act_translate_test() -> None:
    url = ask_url()
    if not url:
        return
    chapter = IntPrompt.ask("[bold]Índice do capítulo[/]", default=1)
    target = Prompt.ask("[bold]Idioma destino[/]", default=state["target"])
    state["target"] = target
    run("translate-test", f"URL={url}", f"CHAPTER={chapter}", f"TARGET={target}")


def act_serve() -> None:
    port = IntPrompt.ask("[bold]Porta[/]", default=8000)
    console.print("[dim]Ctrl+C para parar.[/]")
    run("serve", f"PORT={port}")


def act_shell() -> None:
    console.print("[dim]Saia com Ctrl+D.[/]")
    run("shell")


def act_dev() -> None:
    console.print("[dim]Ctrl+C para parar.[/]")
    run("dev")


def act_dev_web() -> None:
    console.print("[dim]Ctrl+C para parar.[/]")
    run("dev-web")


def act_build_electron() -> None:
    run("build-electron")


def act_build_mac() -> None:
    run("build-mac")


def act_typecheck() -> None:
    run("typecheck")


def act_lint() -> None:
    run("lint")


def act_install() -> None:
    run("install")


def act_install_electron() -> None:
    run("install-electron")


def act_install_all() -> None:
    run("install-all")


def act_clean_cache() -> None:
    if Confirm.ask("[red bold]Apagar cache SQLite + EPUBs gerados?[/]", default=False):
        run("clean-cache")


def act_clean_build() -> None:
    run("clean-build")


def act_clean_venv() -> None:
    if Confirm.ask("[red bold]Apagar venv? (precisa reinstalar depois)[/]", default=False):
        run("clean-venv")


# ---------------------------------------------------------------------------
# Sub-menus
# ---------------------------------------------------------------------------


def menu_backend() -> None:
    show_menu(
        "🐍  Backend (Python)",
        [
            Option("Listar adapters registrados", act_sites, "make sites"),
            Option("Detectar adapter para uma URL", act_detect, "make detect"),
            Option("Baixar capítulos → EPUB", act_download, "fluxo completo"),
            Option("Traduzir 1 capítulo (debug)", act_translate_test, "exige GEMINI_API_KEY"),
            Option("Subir API FastAPI", act_serve, "com --reload"),
            Option("Abrir REPL Python", act_shell, "venv + app importável"),
        ],
    )


def menu_frontend() -> None:
    show_menu(
        "⚡  Frontend (Electron)",
        [
            Option("Rodar Electron em dev", act_dev, "spawn do backend incluído"),
            Option("Rodar só o renderer no browser", act_dev_web, "sem Electron"),
            Option("Build de produção", act_build_electron, "typecheck + bundle"),
            Option("Empacotar .dmg/.app (macOS)", act_build_mac, ""),
            Option("Typecheck", act_typecheck, "node + web"),
            Option("Lint", act_lint, "eslint"),
        ],
    )


def menu_setup() -> None:
    show_menu(
        "🔧  Setup",
        [
            Option("Instalar backend (Python)", act_install, "cria venv + pip install"),
            Option("Instalar frontend (Electron)", act_install_electron, "npm install"),
            Option("Instalar tudo", act_install_all, ""),
        ],
    )


def menu_clean() -> None:
    show_menu(
        "🧹  Limpar",
        [
            Option("Apagar cache + EPUBs", act_clean_cache, "irreversível"),
            Option("Apagar builds (PyInstaller)", act_clean_build, ""),
            Option("Apagar venv", act_clean_venv, ""),
        ],
    )


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def main() -> None:
    main_options = [
        Option("Backend  (testar/desenvolver Python)", menu_backend, "adapter, download, API"),
        Option("Frontend (Electron)", menu_frontend, "app desktop"),
        Option("Setup   (instalar dependências)", menu_setup, "venv + npm"),
        Option("Limpar  (cache, builds, venv)", menu_clean, ""),
    ]

    while True:
        header()
        console.print("\n[bold]O que você quer fazer?[/]\n")
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column()
        table.add_column(style="dim italic")
        for i, opt in enumerate(main_options, 1):
            table.add_row(str(i), opt.label, opt.hint)
        table.add_row("0", "[dim]sair[/]", "")
        console.print(table)

        raw = Prompt.ask("\n[bold cyan]›[/]", default="0").strip().lower()
        if raw in {"0", "q", ""}:
            console.print("\n[dim]até logo 👋[/]\n")
            return
        try:
            idx = int(raw) - 1
            if not (0 <= idx < len(main_options)):
                raise ValueError
        except ValueError:
            console.print("[red]opção inválida[/]")
            pause()
            continue

        main_options[idx].action()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]até logo 👋[/]\n")
