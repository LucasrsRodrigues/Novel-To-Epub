---
name: Pedido de adapter (site novo)
about: Quer suporte a um site que ainda não tem adapter? Comece por aqui.
title: '[ADAPTER] suporte a <nome do site>'
labels: 'adapter, help wanted'
assignees: ''
---

## Site

- Nome: <!-- ex: WebNovel -->
- Domínio: <!-- ex: webnovel.com -->
- Idioma do conteúdo: <!-- en / pt-BR / etc -->

## URL de exemplo

<!-- 1 URL de página de novel + 1 URL de capítulo. -->

- Novel: https://...
- Capítulo: https://...

## Características conhecidas

- [ ] Tem paginação na lista de capítulos
- [ ] Tem volumes nativos (úteis pro preview de volume)
- [ ] Cloudflare / JS challenge
- [ ] Conteúdo via XHR/AJAX (não SSR)
- [ ] Capítulos pagos / login required

## Outras notas

<!-- Pode incluir HTML snippet relevante, comportamento de anti-bot, etc. -->

---

> 💡 **Pra acelerar**: se você programa, considere abrir uma PR direto.
> O [CONTRIBUTING.md](../../CONTRIBUTING.md) tem o passo-a-passo e
> [novellfull.py](../../backend/app/scraper/adapters/novellfull.py) é um
> exemplo de adapter com paginação concorrente que pode servir de base.
