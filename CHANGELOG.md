# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [1.0.13] — 2026-05-29

Release grande de **capas por IA**: foco em coleção coesa por série, galeria
pra baixar a arte, e regeneração leve.

### Added

- **Galeria de capas** no detalhe da novel — clique numa capa pra abrir um modal
  com preview grande e **download da arte** em vários formatos: capa com título
  (2:3), arte sem texto (2:3), wallpaper celular (1080×1920), PC (1920×1080) e
  PC alta (2560×1440). Wallpapers locais (grátis, via Pillow) + opção de gerar o
  wallpaper **nativo** no Gemini.
- **Seletor de estilo na Nova Captura** quando "capa por IA" está ligado, e o
  estilo escolhido vira o **padrão da novel** (pré-selecionado nas próximas).
- **Consistência de coleção por série**: estilo travado por novel + **âncora de
  paleta/luz** extraída da 1ª capa e aplicada às seguintes — volumes da mesma
  série saem coerentes. "Capturar mais capítulos" herda o estilo travado.
- **Botão "Regerar todas as capas"** na galeria — realinha a coleção inteira de
  uma vez (com confirmação de custo).
- **Aviso de falha de capa** no card de Downloads — antes a falha (rate-limit,
  403, etc.) sumia num log silencioso; agora aparece classificada com dica.

### Changed

- **Regerar capa não re-baixa nem re-traduz** — caminho leve "só capa" que usa o
  cache e recompila o EPUB (antes re-enfileirava um download completo, que
  re-tentava capítulos falhos e estourava rate-limit).
- **Estilo travado domina o prompt** e o título/nome da série **saem do prompt**
  do Gemini (entram só na tipografia sobreposta) — corrige a técnica não-aplicada
  em cenas complexas e o "texto-fantasma" que o modelo cravava nas capas.

## [1.0.12] — 2026-05-29

### Added

- **Estilos de arte para a capa por IA** — catálogo de 24 presets (Dark Fantasy,
  Anime Light Novel, Cyberpunk Neon, Art Deco Fantasy, Painterly, Minimalist
  Premium, Cel-Shading, Steampunk, Noir, entre outros) em
  [cover_styles.py](backend/app/image_gen/cover_styles.py). Cada estilo injeta uma
  direção de arte específica no prompt do Gemini Image e guia a cena do brief.
- **Curadoria de estilos nas Configurações** — novo card "Estilo de capa (IA)"
  com checkboxes pra escolher quais estilos aparecem no dropdown. Persistido em
  `cover_styles_enabled`.
- **Dropdown inteligente no botão de capa** ([NovelDetail.tsx](electron/src/renderer/src/components/NovelDetail.tsx)):
  nenhum estilo marcado → automático (IA decide); um marcado → vai direto nele;
  dois ou mais → menu pra escolher na hora (+ opção "Automático").

### Changed

- **`generate_or_cache_cover` aceita `cover_style`** — o estilo escolhido
  sobrescreve o `ART DIRECTION` do prompt; o modo automático mantém o
  comportamento anterior. O parâmetro flui por `DownloadRequest` → `Job` →
  `download_to_epub`, e os endpoints de regerar capa aceitam o estilo no corpo.

## [1.0.11] — 2026-05-27

### Added

- **Tela inicial (About)** acessível pelo clique no logo da sidebar — mostra
  features, links GitHub, créditos, disclaimer legal e versão.
- **Versão do app** no footer da sidebar (`v1.0.11`), com tooltip indicando
  status do backend.
- **Botão "Cancelar"** no card de Downloads (queued + running). Endpoint
  `POST /api/downloads/{id}/cancel` cancela a `asyncio.Task` em curso sem
  derrubar o worker.
- **Progresso da fase meta** durante `fetch_novel` — UI mostra "Buscando
  lista de capítulos · página X/Y" pra adapters que paginam TOC.
- **Adapter NovelFull** ([novellfull.py](backend/app/scraper/adapters/novellfull.py))
  finalizado: paginação concorrente (semáforo de 8) + progresso granular.
  ~130s → ~5.5s pra novel de 3295 caps / 66 páginas (~23× mais rápido).
- **`backend/.env.example`** com as 11 variáveis documentadas.
- **`.github/`** templates de issue (bug, feature, adapter) + PR + CI
  (`ruff` no backend + `tsc --noEmit` no renderer).
- **`SECURITY.md`** e **`CONTRIBUTING.md`** dedicados.
- **`docs/screenshots/`** com prints do app.
- **README.en.md** (versão enxuta em inglês).

### Changed

- **userData ancorado em `productName`** ([main/index.ts](electron/src/main/index.ts)):
  `app.setPath('userData', ...)` aponta pra `~/Library/Application Support/Novel to EPUB/`
  sem depender do `package.json:name`. Evita perda aparente de dados quando
  o nome do app muda entre versões.
- **Preview de novel** na NewCapture só dispara auto pra sites com volumes
  (NovelMania). Pra NovelBin/NovelFull mostra link "Pré-visualizar (opcional)".
- **`HttpClient.get_text(url, throttle=False)`** opcional pula o rate-limit
  global. Uso esperado: paginação de TOC (endpoints baratos). Caminho quente
  (`fetch_chapter`) continua serializado.
- **`Job.status`** aceita `cancelled`; **`Job.stage`** aceita `meta`.

### Fixed

- Job de NovelFull não fica mais aparentemente em loop — paginação roda em
  segundos, com feedback visual contínuo, e pode ser cancelada a qualquer
  momento.

## [1.0.10] — 2026-05-26

Initial public release.

### Added

- Backend Python (FastAPI + Typer CLI), padrão Strategy com auto-discovery
  de adapters.
- Adapters NovelBin (`novelbin.com`/`.me`/`.net`) e NovelMania
  (`novelmania.com.br`).
- Pipeline `download_to_epub` orquestrando scrape → cache → tradução opcional
  → geração de capa opcional → montagem do EPUB.
- API REST + WebSocket de progresso, JobManager assíncrono single-worker.
- Tradução com cascade de providers (Groq → OpenRouter → Cerebras → Gemini),
  glossário automático persistente, perfil de estilo por volume, pin de
  provider por volume.
- Capa IA via Gemini Image (brief textual + composição tipográfica com Pillow).
- Envio para Kindle por SMTP (Gmail/Outlook).
- Dashboard de custos por provider/dia/novel.
- App Electron desktop com tema cream/papel "Modern Paperback Library":
  Library, NewCapture, Downloads, Glossário, Editor de capítulos, Custos,
  Configurações, Diagnóstico de tradução.
- Empacotamento PyInstaller (one-folder) + electron-builder (`.dmg` macOS arm64).
- Menu interativo `make` pra novos usuários.
