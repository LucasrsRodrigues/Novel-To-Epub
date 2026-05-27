# Contribuindo

Obrigado pelo interesse! O tipo de contribuição mais valiosa pra esse projeto
é **adapter de site novo** — a estrutura facilita: 1 arquivo, sem editar
registry, sem boilerplate.

## Setup rápido

```bash
git clone https://github.com/LucasrsRodrigues/Novel-To-Epub.git
cd Novel-To-Epub
make install-all     # cria venv + npm install
cp backend/.env.example backend/.env   # ajuste se quiser
make dev             # Electron hot-reload + backend juntos
```

Em outro terminal, pra debugar adapter isolado:

```bash
make download URL=... START=1 END=1 LOG=DEBUG
```

## Adicionar adapter de site novo

O fluxo está documentado em [README.md#como-adicionar-um-novo-site-adapter](README.md#como-adicionar-um-novo-site-adapter).
Resumindo:

1. **Crie** `backend/app/scraper/adapters/seu_site.py` herdando de `BaseAdapter`.
2. **Implemente** `fetch_novel(url) -> NovelMeta` e `fetch_chapter(ref) -> ChapterContent`.
3. **(Pegadinha PyInstaller)** adicione `from . import seu_site` em
   `backend/app/scraper/adapters/__init__.py`. Sem isso funciona em dev mas
   o `.app` empacotado não acha o adapter.
4. **Teste** com pelo menos 5 capítulos diferentes (início, meio, fim, um
   com nota do tradutor, um com imagem) usando `make download LOG=DEBUG`.

### Critérios de aceite pra adapter

- `make detect URL=<url da novel>` casa o adapter pelo domain
- `make download URL=<url> START=1 END=5` baixa, monta EPUB válido
- EPUB abre no Calibre/Kindle Previewer sem erro
- `fetch_novel` lida com TOC paginada se houver (ver
  [novellfull.py](backend/app/scraper/adapters/novellfull.py) como referência —
  paginação concorrente via `asyncio.Semaphore`)
- Se a paginação for cara (>20 páginas), reporta `self.on_meta_progress(done, total, label)`
  pra UI mostrar progresso real

## Antes de abrir PR

```bash
make typecheck         # tsc --noEmit no renderer
make lint              # ruff no backend
```

Commit message: padrão livre, mas seja específico. "fix novelbin chapter parser para conteúdo dentro de `<article>`" > "fix novelbin".

## Estrutura da PR

- **título** descritivo (50-60 chars)
- **descrição** com:
  - O que faz
  - Como testou (URL real + capítulos baixados)
  - Screenshots se mexer em UI
- **NÃO** inclua segredos / .env / dados pessoais

## Setup de desenvolvimento

- Python 3.10+ (testado em 3.14) com `pip` venv em `backend/.venv`
- Node 18+ com `npm` em `electron/node_modules`
- macOS / Linux nativo; Windows via WSL

## Cortar uma release (apenas mantenedor)

```bash
# 1. atualiza versao
$EDITOR electron/package.json    # bump "version"
$EDITOR CHANGELOG.md             # move [Unreleased] -> [X.Y.Z]

# 2. rebuild backend + .dmg
cd backend && .venv/bin/pyinstaller --clean --noconfirm novel-backend.spec
cd ../electron && npm run build:mac

# 3. tag + push
cd ..
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags

# 4. cria release no GitHub com .dmg
gh release create vX.Y.Z \
  --title "vX.Y.Z" \
  --notes-file <(awk '/^## \[X\.Y\.Z\]/,/^## \[/' CHANGELOG.md | head -n -1) \
  electron/dist/*.dmg

# 5. sha256 (incluir nas release notes)
shasum -a 256 electron/dist/*.dmg
```

## Código de conduta

Sem código de conduta formal por enquanto — mas: seja respeitoso, assuma
boa-fé, pergunte se algo não estiver claro. Discussão técnica > opinião
pessoal. Quem viola é convidado a sair.

## Licença

Ao contribuir você concorda em licenciar seu código sob [MIT](LICENSE).
