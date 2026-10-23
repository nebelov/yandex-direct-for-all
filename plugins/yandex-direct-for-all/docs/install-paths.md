# Пути установки

Установщик управляет только перечисленными каталогами plugins/yandex-direct-for-all, skills отдельных навыков и mcp отдельных служб.

- Кодекс: ${CODEX_HOME:-$HOME/.codex}
- Клод: ${CLAUDE_HOME:-$HOME/.claude}

Без --apply выполняется только чтение и показ плана. При применении исходное состояние сохраняется в .ydfall-install/runs/RUN_ID. Если установленный файл изменён пользователем, обновление останавливается до записи.

Каталог Кодекса ~/.agents/plugins/marketplace.json обновляется только для записи yandex-direct-for-all; остальные записи сохраняются.

## Маркетплейсы

Claude Code ставит плагин целиком, серверы MCP поднимаются из `.mcp.json` плагина через `${CLAUDE_PLUGIN_ROOT}`:

    /plugin marketplace add nebelov/yandex-direct-for-all
    /plugin install yandex-direct-for-all@yandex-direct-for-all

Codex берёт маркетплейс из `.agents/plugins/marketplace.json`:

    codex plugin marketplace add nebelov/yandex-direct-for-all

## Регистрация MCP в Codex вручную

Если после ручной установки Codex не передаёт серверам переменные окружения, добавьте в `${CODEX_HOME:-$HOME/.codex}/config.toml` блоки с абсолютными путями (замените `/ABS` на путь к каталогу Codex):

    [mcp_servers.yandexDirect]
    command = "uv"
    args = ["run", "--frozen", "--project", "/ABS/mcp/yandex-direct", "python", "/ABS/mcp/yandex-direct/server.py", "stdio"]
    cwd = "/ABS/mcp/yandex-direct"
    env_vars = ["YANDEX_DIRECT_ACCESS_FILE", "YANDEX_DIRECT_ENVIRONMENT", "YANDEX_DIRECT_PRODUCTION_READ_TOKEN", "YANDEX_DIRECT_CLIENT_LOGIN"]

    [mcp_servers.yandexWordstat]
    command = "bash"
    args = ["/ABS/mcp/yandex-wordstat/start.sh"]
    env_vars = ["YANDEX_WORDSTAT_API_KEY", "YANDEX_WORDSTAT_FOLDER_ID"]
