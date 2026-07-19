# Ревизия yandex-direct-for-all к текущему production-состоянию

Дата: 2026-05-16

Репозиторий: `nebelov/yandex-direct-for-all`

## Главный вывод

GitHub-версия сейчас описывает старый portable plugin bundle: локальный MCP для Яндекс.Директа, Wordstat/Search wrappers, Claude-install flow, универсальные collector-скрипты, Roistat/amocrm и старые skill-инструкции.

Текущая рабочая система другая: Codex-агент 24/7 в Docker, управление через Telegram, память как источник истины, Direct/Metrika через `yandex-performance-mcp`, write-операции только через preview/approve/write/readback, safe tools вместо raw Direct API.

Итог: GitHub нужно разделить на два слоя:

1. `production-orchestrator` - актуальные инструкции, Telegram contract, memory contract, MCP routing, Direct playbooks.
2. `legacy-portable-plugin` - старый bundle как архив/дев-утилита.

## Проверенные части GitHub-версии

- `.codex-plugin/plugin.json`
- `.mcp.json`
- `scripts/validate_bundle.sh`
- `scripts/list_data_collectors.sh`
- `scripts/install_codex_bundle.sh`
- `scripts/install_claude_bundle.sh`
- `scripts/start_yandex_user_auth.py`
- `scripts/preflight_yandex_user_token.py`
- `scripts/yandex_auth_common.py`
- `mcp/yandex-direct/server.py`
- `mcp/yandex-search/server.py`
- `mcp/yandex-wordstat/package.json`
- `docs/auth-model-matrix.md`
- `docs/install-paths.md`
- `docs/oauth-and-app-setup.md`
- `skills/yandex-performance-ops/SKILL.md`
- `.agents/plugins/marketplace.json`

## Что оставить

| Компонент | Решение | Причина |
|---|---|---|
| `docs/auth-model-matrix.md` | Оставить, переписать | OAuth-матрица полезна, но не должна быть главным runtime-контрактом. |
| `docs/oauth-and-app-setup.md` | Оставить, переписать | Полезно для первичной авторизации, но отделить от production flow. |
| `scripts/start_yandex_user_auth.py` | Оставить как optional utility | Нормальная утилита первичного OAuth. |
| `scripts/preflight_yandex_user_token.py` | Оставить как optional utility | Полезный read-only preflight. |
| `scripts/yandex_auth_common.py` | Оставить как helper | Использовать только для auth utility scripts. |
| `scripts/validate_bundle.sh` | Переписать | Идея валидации нужна, текущий список проверяет старый bundle. |
| `scripts/list_data_collectors.sh` | Заменить | Сейчас список collectors не отражает safe MCP routes. |
| `.codex-plugin/plugin.json` | Переписать | Должен описывать актуальный production ruleset. |

## Что удалить или перенести в legacy

| Компонент | Действие | Причина |
|---|---|---|
| `scripts/install_claude_bundle.sh` | Удалить из core или перенести в `legacy/claude/` | Production сейчас Codex/Telegram. |
| Ссылки на `.claude/CLAUDE.md` | Удалить | Неактуальный источник правил. |
| Старые model IDs | Удалить | В текущих правилах запрещено выдумывать/хардкодить непроверенные model IDs. |
| `mcp/yandex-direct/server.py` | Перенести в `legacy/local-mcp/` | Raw Direct MCP не должен быть default route. |
| `mcp/yandex-search/server.py` | Перенести в `legacy/local-mcp/` | Research-утилита, не runtime core. |
| `mcp/yandex-wordstat/` | Перенести в `legacy/optional/` | Wordstat может быть optional, но не обязательный runtime core. |
| Roistat/amocrm scripts and refs | Удалить из core или сделать optional | Сейчас не входят в основной режим работы. |
| `scripts/install_codex_bundle.sh` | Переписать | Нужен безопасный install/update с preview и backup. |

## Что добавить

- `AGENTS.md`
- `docs/current-runtime.md`
- `docs/telegram-bridge-contract.md`
- `docs/memory-contract.md`
- `docs/yandex-performance-mcp-routing.md`
- `docs/write-approval-contract.md`
- `docs/direct-strategy-playbook.md`
- `docs/product-gallery-playbook.md`
- `docs/keywordbids-autobudget-readback.md`
- `docs/sqr-negative-plan-contract.md`
- `docs/ad-rewrite-contract.md`
- `docs/growth-leaders-contract.md`
- `docs/hooks-and-scope-guard.md`
- `docs/production-limitations.md`
- `memory/lessons.md` template
- `memory/MEMORY.md` template

## Ключевые правила для новых инструкций

- Всегда отвечать на русском.
- Перед нетривиальным действием читать релевантный skill/preflight.
- Память является источником истины.
- Direct write: `Plan -> Approve -> Act -> Readback`.
- Telegram-входящие отвечать через `telegram.reply`.
- Для long scope после фактического выполнения использовать `close_scope`.
- Не использовать force/verify-bypass флаги и массовые операции без baseline snapshot.
- Не коммитить токены.
- Ошибки фиксировать в lessons/AP.
- Warning/error tool call не считать успехом.
- Не отправлять пользователю internal/local/permalink пути как deliverable.

## Новый docs/yandex-performance-mcp-routing.md

Этот документ должен заменить raw Direct MCP как default route.

Обязательные правила:

- account-scoped задачи сначала grounding через `yd_*`/`ym_*` read-only tools;
- стратегии: `yd_campaign_strategy_info`, `yd_campaign_strategy_apply_safe`, `yd_set_campaign_average_cpc_safe`, `yd_set_campaign_max_clicks_safe`;
- минус-фразы: `yd_negative_plan`, `yd_search_query_audit`, `yd_search_negatives_apply_safe`, `yd_negatives_apply_plan`, readback через `yd_negatives`;
- объявления: `yd_ad_rewrite_apply_safe`, `yd_ad_copy_repair_apply_safe`, `yd_fix_fresh_generic_ads_apply_safe`;
- growth/leaders: `yd_growth_leaders_apply_safe`, `yd_raise_bids_for_leaders_safe`;
- raw API fallback только если специализированного tool нет;
- paginated reports дочитывать полностью перед аудитом/рекомендациями.

## Сопоставление скриптов

| Скрипт/модуль | Что сделать |
|---|---|
| `scripts/validate_bundle.sh` | Переписать в `scripts/validate_repository.sh`: проверять `AGENTS.md`, docs contracts, memory examples, stale Claude refs, model IDs, secrets. |
| `scripts/list_data_collectors.sh` | Заменить на `scripts/list_tool_routes.sh`: Direct/Metrika task -> safe MCP route. |
| `scripts/install_codex_bundle.sh` | Переписать: preview, backup, no hidden global mutation. |
| `scripts/install_claude_bundle.sh` | Удалить из core или legacy. |
| `scripts/start_yandex_user_auth.py` | Оставить optional; добавить README, scopes, masking, no token logs. |
| `scripts/preflight_yandex_user_token.py` | Оставить optional; обновить API docs/version. |
| `scripts/yandex_auth_common.py` | Оставить helper. |
| `mcp/yandex-direct/server.py` | Legacy only. |
| `mcp/yandex-search/server.py` | Legacy/optional; заменить regex XML parse на structured XML parser, если оставлять. |
| `mcp/yandex-wordstat/*` | Optional, не core runtime. |
| `collect_*`, `audit_*`, `fetch_sqr.sh` | Переписать как MCP wrappers или удалить из core. |

## Минимальный план актуализации

### Phase 1 - актуальные правила

1. Добавить `AGENTS.md`.
2. Добавить `docs/current-runtime.md`.
3. Добавить `docs/telegram-bridge-contract.md`.
4. Добавить `docs/memory-contract.md`.
5. Добавить `docs/yandex-performance-mcp-routing.md`.
6. Добавить `docs/write-approval-contract.md`.

### Phase 2 - skills

Разбить `skills/yandex-performance-ops/SKILL.md` на:

- `telegram-direct-operator`;
- `direct-strategy-operator`;
- `direct-negative-operator`;
- `direct-ad-rewrite-operator`;
- `direct-growth-operator`;
- `memory-operator`.

Удалить Claude/model stale refs. В каждом skill указать default MCP route и forbidden raw fallback.

### Phase 3 - scripts

Переписать validation script, удалить или перенести в legacy Claude installer, сделать auth scripts optional, старые collectors заменить на route inventory или wrappers, которые не обходят safe tools.

### Phase 4 - legacy

Создать `legacy/portable-plugin-v0.2/` и перенести туда local MCP servers, Wordstat package, Yandex Search wrapper, old collectors, old installers.

## README нужно переписать так

1. Что это: production instructions/ruleset for Codex Yandex Direct operator.
2. Runtime: Telegram + basic-memory + yandex-performance-mcp.
3. Safety model: plan/approve/act/readback.
4. Main task routes: strategy changes, negatives, ads rewrite, growth leaders, Metrika checks, product campaigns/feed checks.
5. Memory workflow.
6. Legacy tools section.
7. Setup/auth utilities.
8. Validation.

## Нельзя переносить в актуальную версию без изменений

- `yd_api`/raw Direct как default route.
- `install_claude_bundle.sh`.
- Инструкции, где read-only analysis описывается как applied change.
- Write flows без explicit readback.
- Broad автоматическая минусовка без product-scope cross-check.
- Hardcoded/непроверенные model IDs.
- Shell-only critical workflows.
- Internal/local/permalink ссылки как deliverable для пользователя.

## Lessons/AP, которые нужно добавить

- `KeywordBids` warning при autobudget strategy не является успехом; после изменения ставки всегда читать readback.
- При ProductGallery campaign без показов сначала проверить strategy, budget, feed state, ad moderation, group eligibility, product gallery flags, затем bids.
- Local shell может падать из-за bwrap; MCP/basic-memory fallback должен быть documented.
- Для Telegram scope нельзя закрывать turn статусом/обещанием без фактических tool calls.
- Нельзя отправлять пользователю internal/local/permalink пути как результат; deliverable должен быть внешним PR/diff, вложением или текстом.

## Следующий практический шаг

Сделать отдельную ветку `self-edit/20260516-github-actualization-plan`, внести Phase 1 files and README rewrite, затем отправить внешний GitHub diff/PR на review. После подтверждения переносить legacy и переписывать scripts.
