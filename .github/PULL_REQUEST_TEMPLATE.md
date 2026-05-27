<!-- Obrigado pela PR! Preencha o que fizer sentido. -->

## O que esta PR faz

<!-- 1-2 parágrafos. Resolve issue #N? Adiciona feature X? -->

## Como testei

<!-- Pra adapter novo: URL real + cap início, meio, fim. Cole o output de
     `make download URL=... LOG=DEBUG` se ajudar. -->

- [ ] `make typecheck` passa
- [ ] `make lint` passa
- [ ] Testei manualmente o caminho feliz
- [ ] (Se UI) Screenshots inclusos abaixo

## Screenshots (se aplicável)

<!-- Arraste imagens aqui. Antes/depois ajuda. -->

## Checklist final

- [ ] Sem `console.log` / `print` esquecidos
- [ ] Sem segredos (.env, API keys) commitados
- [ ] Atualizei o [CHANGELOG.md](../CHANGELOG.md) seção `[Unreleased]`
- [ ] Adapter novo? Adicionei `from . import <nome>` em
      [adapters/__init__.py](../backend/app/scraper/adapters/__init__.py)
      (PyInstaller pitfall — sem isso o `.app` empacotado não acha)
