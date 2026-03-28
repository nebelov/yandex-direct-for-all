# Component Inventory

## Что включено в bundle

### Skills

| Компонент | Назначение | Состав |
|---|---|---|
| `yandex-performance-ops` | day-2/day-N работа с `Direct`, `Wordstat`, `Metrika`, `Roistat` | `59` scripts + templates + references + schemas |
| `yandex-direct-client-lifecycle` | intake, research, proposal, handoff | `17` scripts + templates + references |
| `roistat-reports-api` | отчёты `Roistat` только через API | `3` scripts + references |
| `amocrm-api-control` | `amoCRM` OAuth/control + `Yandex Audiences` companion automation | `3` scripts + references |

### MCP servers

| Компонент | Назначение |
|---|---|
| `mcp/yandex-direct` | CRUD и чтение по `Yandex Direct API` |
| `mcp/yandex-search` | web search / AI search через `Yandex Search API` |
| `mcp/yandex-wordstat` | `Wordstat` top requests / dynamics / regions / regions tree / quota |

## Канонические источники

Сборка опирается на уже нормализованные global skills и их аудит полноты:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/source_inventory.md`
- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/completeness_audit_2026-03-05.md`

Ключевые upstream-источники, уже поднятые в global skill:

- `kartinium/.claude/skills/direct-search-semantics`
- `kartinium/.claude/skills/yandex-direct`
- `kartinium/.claude/skills/yandex-wordstat`
- `kartinium/.claude/skills/roistat-direct`
- `kartinium/.claude/skills/media-plan`
- `ads/siz/.claude/skills/direct-optimization`
- `ads/siz/.claude/skills/yandex-metrika`
- `ads/siz/.claude/skills/competitive-ads-extractor`
- `ads/siz/.claude/skills/ppc-data-analysis`
- `ads/tenevoy/.claude/skills/direct-optimization`
- `ads/tenevoy/.claude/skills/roistat-direct`

## Что сознательно не включено

Сюда намеренно не поднимались:

- client-specific product catalogs
- campaign maps и board IDs
- локальные overlays с секретами
- raw client reports
- analysis-скрипты, которые сами принимают бизнес-решения вместо ручного review

Причина: это не reusable слой, а перенос клиентской специфики.

## Зачем добавлен `amocrm-api-control`

Основной комплект Яндекса закрывается тремя skills:

- `yandex-performance-ops`
- `yandex-direct-client-lifecycle`
- `roistat-reports-api`

Но сценарии `CRM stage -> Yandex Audiences` уже присутствуют в вашем контуре работы. Чтобы их не потерять, в bundle включён `amocrm-api-control` как optional companion layer.
