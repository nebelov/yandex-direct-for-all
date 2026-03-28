# Codex Plugin Build Notes

Этот plugin-root собран по официальным страницам OpenAI:

- `https://developers.openai.com/codex/plugins`
- `https://developers.openai.com/codex/plugins/build`

Проверка выполнена `2026-03-28`.

## Contract

- обязательный entry point = `.codex-plugin/plugin.json`
- plugin folder предназначен для repo marketplace с путём `./plugins/yandex-direct-for-all`
- все manifest paths начинаются с `./`
- внутри `.codex-plugin/` лежит только `plugin.json`

## Почему bundle self-contained

Codex ставит локальные плагины в cache-копию, а не читает их напрямую из marketplace path.
Из-за этого runtime-важные файлы нельзя хранить снаружи plugin-root.

Поэтому внутри самого bundle лежат:

- `README.md`
- `docs/`
- `examples/`
- `scripts/`
- `skills/`
- `mcp/`

## Почему здесь только `skills` + `mcpServers`

Official docs допускают `apps`, но этот bundle не про connector/app distribution.

Его задача:

- перенести канонические skills;
- перенести локальные MCP servers;
- дать install/validate helpers;
- дать готовый entry point для повторного использования в других аккаунтах.

Поэтому поле `apps` сознательно опущено.

## Marketplace

Repo marketplace должен жить в:

- `../../.agents/plugins/marketplace.json`

В marketplace entry должны оставаться:

- `policy.installation`
- `policy.authentication`
- `category`

После изменения manifest или marketplace нужен restart Codex.
