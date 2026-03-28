# Install Paths

Этот файл фиксирует один канон путей, чтобы новый ИИ не путал `repo-local plugin`, `personal Codex install` и `home-compat` копирование.

## Канонические обозначения

- `<repo-root>` = корень этого репозитория
- `<plugin-root>` = `<repo-root>/plugins/yandex-direct-for-all`
- `<personal-codex-plugin-root>` = `${CODEX_HOME:-~/.codex}/plugins/yandex-direct-for-all`
- `<personal-claude-plugin-root>` = `~/.claude/plugins/yandex-direct-for-all`

## Режим 1. Repo-local plugin для Codex

Это главный и рекомендуемый путь для Codex.

Что уже есть в репозитории:
- `.agents/plugins/marketplace.json`
- plugin entry с `source.path = ./plugins/yandex-direct-for-all`

Что делать:
1. Оставить plugin внутри этого репозитория по пути `<plugin-root>`.
2. Убедиться, что Codex открыт в этом repo и видит `.agents/plugins/marketplace.json`.
3. Перезапустить Codex после изменения marketplace или plugin manifest.

Что НЕ делать:
- не запускать `install_codex_bundle.sh`, если задача только в том, чтобы Codex увидел repo-local plugin;
- не читать bundled skills из `~/.codex/skills/...`, если работаете в repo-local режиме.

## Режим 2. Personal Codex install

Нужен, если хотите поставить этот bundle в personal `~/.codex` вне текущего репозитория.

Запускать из `<repo-root>`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_codex_bundle.sh
```

Что делает скрипт:
- копирует весь plugin в `<personal-codex-plugin-root>`
- зеркалит `skills/*` в `${CODEX_HOME:-~/.codex}/skills/`
- зеркалит `mcp/*` в `${CODEX_HOME:-~/.codex}/mcp/`
- создаёт или обновляет `~/.agents/plugins/marketplace.json` с фактическим installed plugin path
- повторный запуск refresh-ит этот managed install in-place

После этого:
- canonical installed plugin root = `<personal-codex-plugin-root>`
- для Codex нужен restart

## Режим 3. Claude home-compat install

Нужен, если хотите использовать тот же bundle через `~/.claude`.

Запускать из `<repo-root>`:

```bash
bash ./plugins/yandex-direct-for-all/scripts/install_claude_bundle.sh
```

Что делает скрипт:
- сначала обновляет personal Codex install
- затем копирует весь plugin в `<personal-claude-plugin-root>`
- зеркалит `skills/*` в `${CLAUDE_HOME:-~/.claude}/skills/`
- зеркалит `mcp/*` в `${CLAUDE_HOME:-~/.claude}/mcp/`

## Какой path использовать внутри docs и skills

Во всех bundled `SKILL.md`, references и templates canonical runtime path теперь такой:

- `<plugin-root>/skills/...`
- `<plugin-root>/mcp/...`
- `<plugin-root>/scripts/...`

Это означает:
- в repo-local режиме `<plugin-root> = ./plugins/yandex-direct-for-all`
- в personal Codex install `<plugin-root> = ~/.codex/plugins/yandex-direct-for-all`
- в Claude home-compat `<plugin-root> = ~/.claude/plugins/yandex-direct-for-all`
