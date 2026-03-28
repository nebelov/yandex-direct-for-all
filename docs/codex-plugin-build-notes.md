# Codex Plugin Build Notes

Этот репозиторий собран как `repo-local` плагин для Codex по официальным страницам OpenAI:

- `https://developers.openai.com/codex/plugins`
- `https://developers.openai.com/codex/plugins/build`

Проверка выполнена `2026-03-28`.

## Что из official contract здесь соблюдено

- обязательный manifest лежит в `plugins/yandex-direct-for-all/.codex-plugin/plugin.json`
- repo marketplace лежит в `.agents/plugins/marketplace.json`
- `source.path` в marketplace = `./plugins/yandex-direct-for-all`
- все пути в manifest относительные и начинаются с `./`
- bundle использует официальный plugin layout:
  - `.codex-plugin/plugin.json`
  - `skills/`
  - `.mcp.json`
  - `assets/`

## Почему здесь нет `.app.json`

Official docs описывают `apps` как опциональный слой для app/connectors.

Этот пакет решает другую задачу:

- переносимый knowledge layer;
- локальные MCP servers;
- install/validate scripts;
- self-hosted reusable workflow для `Yandex Direct`, `Wordstat`, `Metrika`, `Roistat`.

Поэтому manifest здесь оставлен на официальном минимуме для такого сценария:

- `skills`
- `mcpServers`
- `interface`

Это инженерное решение для переносимости, а не отдельное правило OpenAI.

## Куда Codex будет его ставить

По official docs локальные плагины ставятся в cache вида:

- `~/.codex/plugins/cache/<marketplace>/<plugin>/local/`

Поэтому все файлы, важные для реального использования bundle, держатся внутри самого plugin-root:

- `plugins/yandex-direct-for-all/README.md`
- `plugins/yandex-direct-for-all/docs/*`
- `plugins/yandex-direct-for-all/examples/*`
- `plugins/yandex-direct-for-all/scripts/*`

## Практические правила для сопровождения

- не выносить runtime-важные docs/examples наружу из plugin-root
- если меняется manifest или marketplace, перезапускать Codex
- не менять `name` у plugin-folder, `plugin.json.name` и `marketplace.plugins[].name` независимо друг от друга
- сохранять `policy.installation`, `policy.authentication` и `category` в marketplace entry
