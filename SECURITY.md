# Política de Segurança

## Como reportar

Achou uma vulnerabilidade? **Não abra issue público.**

Reporte de forma privada por:

1. **GitHub Security Advisories** (preferido) —
   [Reportar via Advisory](https://github.com/LucasrsRodrigues/Novel-To-Epub/security/advisories/new)
2. **Email** — abra a aba "Security" do repo se quiser canal alternativo.

Tente incluir:

- Descrição da vulnerabilidade
- Passos de reprodução
- Versão / commit afetado
- Impacto estimado

Vou responder em até **7 dias úteis** com confirmação. Pra patches
"normais", o release sai dentro de 30 dias. Críticos saem assim que houver
fix testado.

## Escopo

O que conta como vulnerabilidade neste projeto:

- **SSRF / RCE** no scraper (URLs que escapam do host-allowlist do adapter)
- **Exfiltração** de credenciais salvas no SQLite via prompt-injection no
  conteúdo de capítulos (afeta tradução IA)
- **Credential leakage** em logs, telemetria ou arquivos gerados (EPUB,
  capa, dump de uso)
- **Bypass** do isolamento Electron (preload sem `contextIsolation`,
  `nodeIntegration` indevido em renderers)
- **Auth bypass** em endpoints da API (atualmente sem auth — todos os
  endpoints assumem `127.0.0.1` only)

O que **não** é vulnerabilidade:

- "O scraper viola o ToS do site X" — é responsabilidade do usuário
  ([disclaimer](README.md#aviso-legal))
- Falhas só reproduzíveis com a porta `8000` exposta na internet (o backend
  é `127.0.0.1`-only por design)
- DoS por payload absurdamente grande (ex: novel com 100k capítulos) —
  conhecido, sem fix planejado

## Versões suportadas

| Versão | Status     |
|--------|------------|
| `1.x`  | ✅ Suportada |
| `< 1`  | ❌ Sem suporte |
