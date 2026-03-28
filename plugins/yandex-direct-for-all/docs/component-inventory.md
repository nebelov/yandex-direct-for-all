# Component Inventory

## Skills

| Компонент | Назначение |
|---|---|
| `skills/yandex-performance-ops` | day-2/day-N слой по `Direct`, `Wordstat`, `Metrika`, `Roistat`, `Search API` |
| `skills/yandex-direct-client-lifecycle` | intake, research, proposal, handoff |
| `skills/roistat-reports-api` | отчёты `Roistat` только через API |
| `skills/amocrm-api-control` | companion layer для `amoCRM -> Yandex Audiences / VK Ads` |

## Bundled MCP servers

| Компонент | Назначение | Runtime |
|---|---|---|
| `mcp/yandex-direct` | CRUD и чтение по `Yandex Direct API` | `python3` |
| `mcp/yandex-search` | `Yandex Search API` / SERP слой | `python3` |
| `mcp/yandex-wordstat` | `Wordstat` top requests, dynamics, regions, quota | `node` |

## Metrika layer

Отдельного MCP-сервера для `Metrika` в bundle нет.

Вместо этого bundled reusable path лежит в:

- `skills/yandex-performance-ops/scripts/metrika/common.sh`
- `skills/yandex-performance-ops/scripts/metrika/counters.sh`
- `skills/yandex-performance-ops/scripts/metrika/counter_info.sh`
- `skills/yandex-performance-ops/scripts/metrika/goals.sh`
- `skills/yandex-performance-ops/scripts/metrika/conversions.sh`
- `skills/yandex-performance-ops/scripts/metrika/traffic_summary.sh`
- `skills/yandex-performance-ops/scripts/metrika/utm_report.sh`
- `skills/yandex-performance-ops/scripts/metrika/search_engines.sh`

## Required env surface

- `YD_TOKEN`
- `YD_CLIENT_LOGIN`
- `YD_SANDBOX`
- `YD_OUTPUT_DIR`
- `YANDEX_OAUTH_CLIENT_ID`
- `YANDEX_OAUTH_CLIENT_SECRET`
- `YANDEX_OAUTH_REDIRECT_URI`
- `YANDEX_AUTH_OUTPUT_DIR`
- `YANDEX_DIRECT_OAUTH_CLIENT_ID`
- `YANDEX_DIRECT_OAUTH_CLIENT_SECRET`
- `YANDEX_METRIKA_OAUTH_CLIENT_ID`
- `YANDEX_METRIKA_OAUTH_CLIENT_SECRET`
- `YANDEX_AUDIENCE_OAUTH_CLIENT_ID`
- `YANDEX_AUDIENCE_OAUTH_CLIENT_SECRET`
- `YANDEX_WORDSTAT_TOKEN`
- `YANDEX_WORDSTAT_CLIENT_PATH`
- `SEARCH_API_KEY`
- `FOLDER_ID`
- `YANDEX_SEARCH_API_KEY`
- `YANDEX_SEARCH_FOLDER_ID`
- `YANDEX_METRIKA_TOKEN`
- `YANDEX_METRIKA_COUNTER_ID`
- `YANDEX_AUDIENCE_TOKEN`

Шаблон лежит в `../examples/yandex.env.example`.

## Что намеренно не bundled

- client-specific overlays
- board ids и campaign maps
- реальные токены и oauth файлы
- raw client reports
- анализаторы, которые принимают маркетинговые verdict-решения автоматически
