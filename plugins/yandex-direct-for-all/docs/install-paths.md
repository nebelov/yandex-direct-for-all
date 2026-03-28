# Install Paths

Этот файл фиксирует один канон путей для этого plugin-root.

## Канонические обозначения

- `<plugin-root>` = текущий plugin bundle
- repo-local пример: `./plugins/yandex-direct-for-all`
- personal Codex install пример: `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all`
- Claude home-compat пример: `${CLAUDE_HOME:-~/.claude}/plugins/yandex-direct-for-all`

## Режим 1. Repo-local plugin для Codex

Это главный путь для Codex.

Repo marketplace уже живёт в:

- `../../.agents/plugins/marketplace.json`

И plugin entry уже указывает на:

- `./plugins/yandex-direct-for-all`

Практически это значит:
- держите этот plugin внутри репозитория;
- перезапускайте Codex после изменения marketplace или manifest;
- не нужно копировать bundle в `~/.codex`, если вам нужен только repo-local plugin.

## Режим 2. Personal Codex install

Если нужен personal install вне текущего репозитория, запускать из `<repo-root>`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh
```

Скрипт:
- копирует весь plugin в `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all`
- зеркалит `skills/*` в `${CODEX_HOME:-~/.codex}/skills/`
- зеркалит `mcp/*` в `${CODEX_HOME:-~/.codex}/mcp/`
- создаёт или обновляет `~/.agents/plugins/marketplace.json` с фактическим installed plugin path
- повторный запуск refresh-ит этот managed install in-place

После этого canonical installed plugin root:

- `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all`

## Режим 3. Claude home-compat

Если нужен install в `~/.claude`, запускать из `<repo-root>`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_claude_bundle.sh
```

Скрипт:
- сначала обновляет personal Codex install
- затем копирует весь plugin в `${CLAUDE_HOME:-~/.claude}/plugins/yandex-direct-for-all`
- зеркалит `skills/*` и `mcp/*` в `${CLAUDE_HOME:-~/.claude}`

## Какой path считать каноном внутри bundle

Во всех bundled `SKILL.md`, references и templates canonical runtime path такой:

- `<plugin-root>/skills/...`
- `<plugin-root>/mcp/...`
- `<plugin-root>/scripts/...`

Не использовать как canonical docs-path:

- `~/.codex/skills/...`
- `~/.claude/skills/...`

Они могут существовать как зеркала совместимости, но больше не являются главным ориентиром для нового ИИ.
