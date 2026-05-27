# Makefile — epub_scrap (Novel → EPUB)
#
# Atalhos para rodar/testar o backend (Python) e o frontend (Electron) sem
# precisar ativar venv ou lembrar comandos longos.
#
# Veja os alvos disponíveis com:
#     make help
#
# Exemplos:
#     make install
#     make sites
#     make detect URL=https://novelbin.com/b/foo
#     make download URL=https://... START=1 END=3
#     make download URL=https://... START=1 END=1 LOG=DEBUG
#     make serve PORT=8001
#     make dev                       # Electron

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND   := backend
ELECTRON  := electron
VENV      := $(BACKEND)/.venv
PY        := $(abspath $(VENV)/bin/python)
PIP       := $(abspath $(VENV)/bin/pip)

# ---------------------------------------------------------------------------
# Variáveis customizáveis pela linha de comando
# (sobrescreva como `make download URL=https://... START=1 END=2`)
# ---------------------------------------------------------------------------

URL       ?=
START     ?= 1
END       ?=
OUT       ?= ./out
CHAPTER   ?= 1
TARGET    ?= pt-BR
HOST      ?= 127.0.0.1
PORT      ?= 8000
LOG       ?= INFO       # use LOG=DEBUG p/ ver tudo (httpx fica silenciado por padrão)
NO_COVER  ?= 1          # 1 = passa --no-cover (mais rápido p/ testar adapter)

# Exporta NOVEL_LOG_LEVEL p/ os comandos do backend (lido em app/config.py)
export NOVEL_LOG_LEVEL = $(LOG)

.DEFAULT_GOAL := menu

# ---------------------------------------------------------------------------
# Menu interativo (default ao rodar `make` sem args)
# ---------------------------------------------------------------------------

.PHONY: menu
menu: ## abre o menu interativo guiado (default)
	@test -x $(PY) || { echo "venv não encontrado. Rode: make install"; exit 1; }
	@$(PY) tools/menu.py

# ---------------------------------------------------------------------------
# Help (autogerado a partir de comentários "## ...")
# ---------------------------------------------------------------------------

.PHONY: help
help: ## mostra esta ajuda
	@echo "Alvos disponíveis:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Variáveis úteis: URL, START, END, OUT, CHAPTER, TARGET, HOST, PORT, LOG"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

$(VENV)/bin/python:
	python3 -m venv $(VENV)

.PHONY: venv
venv: $(VENV)/bin/python ## cria o venv se ainda não existir

.PHONY: install
install: venv ## instala/atualiza dependências do backend (Python)
	$(PIP) install -U pip
	$(PIP) install -r $(BACKEND)/requirements.txt

.PHONY: install-electron
install-electron: ## instala dependências do frontend (Electron)
	cd $(ELECTRON) && npm install

.PHONY: install-all
install-all: install install-electron ## instala backend + frontend

# ---------------------------------------------------------------------------
# Backend / CLI (Python)
# ---------------------------------------------------------------------------

.PHONY: sites
sites: ## lista adapters de site registrados
	cd $(BACKEND) && $(PY) main.py sites

.PHONY: detect
detect: ## detecta qual adapter atende URL=... (ex: make detect URL=https://...)
	@test -n "$(URL)" || { echo "uso: make detect URL=https://..."; exit 1; }
	cd $(BACKEND) && $(PY) main.py detect "$(URL)"

.PHONY: download
download: ## baixa intervalo: URL=... [START=1 END=N OUT=./out NO_COVER=1]
	@test -n "$(URL)" || { echo "uso: make download URL=https://... [START=1 END=2]"; exit 1; }
	cd $(BACKEND) && $(PY) main.py download \
		--url "$(URL)" \
		--start $(START) \
		$(if $(END),--end $(END),) \
		--output "$(OUT)" \
		$(if $(filter 1,$(NO_COVER)),--no-cover,)

.PHONY: translate-test
translate-test: ## traduz 1 capítulo: URL=... [CHAPTER=1 TARGET=pt-BR]
	@test -n "$(URL)" || { echo "uso: make translate-test URL=https://... [CHAPTER=1]"; exit 1; }
	cd $(BACKEND) && $(PY) main.py translate-test \
		--url "$(URL)" --chapter $(CHAPTER) --target "$(TARGET)"

.PHONY: serve
serve: ## sobe a API FastAPI em HOST:PORT (default 127.0.0.1:8000) com --reload
	cd $(BACKEND) && $(PY) main.py serve --host $(HOST) --port $(PORT) --reload

.PHONY: shell
shell: ## abre Python REPL com o venv ativo (app importável)
	cd $(BACKEND) && $(PY)

# ---------------------------------------------------------------------------
# Frontend / Electron
# ---------------------------------------------------------------------------

.PHONY: dev
dev: ## roda o app Electron em modo dev (spawn do backend incluído)
	cd $(ELECTRON) && npm run dev

.PHONY: dev-web
dev-web: ## roda só o renderer no browser (sem Electron)
	cd $(ELECTRON) && npm run dev:web

.PHONY: build-electron
build-electron: ## build de produção do Electron (typecheck + bundle)
	cd $(ELECTRON) && npm run build

.PHONY: build-mac
build-mac: ## empacota .dmg/.app para macOS
	cd $(ELECTRON) && npm run build:mac

.PHONY: typecheck
typecheck: ## typecheck do frontend (node + web)
	cd $(ELECTRON) && npm run typecheck

.PHONY: lint
lint: ## eslint no frontend
	cd $(ELECTRON) && npm run lint

# ---------------------------------------------------------------------------
# Limpeza
# ---------------------------------------------------------------------------

.PHONY: clean-cache
clean-cache: ## apaga cache SQLite e EPUBs gerados (irreversível)
	rm -f $(BACKEND)/data/cache.sqlite3
	rm -rf $(BACKEND)/data/epubs
	rm -rf $(OUT)

.PHONY: clean-build
clean-build: ## apaga artefatos de build do backend (PyInstaller)
	rm -rf $(BACKEND)/build $(BACKEND)/dist

.PHONY: clean-venv
clean-venv: ## apaga o venv (re-rode `make install` depois)
	rm -rf $(VENV)

.PHONY: clean
clean: clean-build ## limpa builds (mantém cache e venv)
