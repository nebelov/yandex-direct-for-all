# Plugin Skills

Это не заглушка. В plugin bundled четыре полноценные skills-директории.

## Что входит

### `yandex-performance-ops`

Главный downstream/day-2/day-N skill.

Использовать для:

- `Yandex Direct` audit и optimisation
- `Wordstat` collection
- `Metrika`
- `Roistat`
- apply/readback/live-validation

Точка входа:

- `skills/yandex-performance-ops/SKILL.md`

### `yandex-direct-client-lifecycle`

Upstream/onboarding skill.

Использовать для:

- intake
- client knowledge base
- competitor research
- proposal
- handoff в `yandex-performance-ops`

Точка входа:

- `skills/yandex-direct-client-lifecycle/SKILL.md`

### `roistat-reports-api`

Отдельный skill для работы с `Roistat` через API без UI.

Точка входа:

- `skills/roistat-reports-api/SKILL.md`

### `amocrm-api-control`

Companion skill для `amoCRM OAuth/control` и CRM-driven automation.

Точка входа:

- `skills/amocrm-api-control/SKILL.md`

## Что читать первым

Если задача неизвестна:

1. `skills/yandex-performance-ops/SKILL.md`
2. `skills/yandex-direct-client-lifecycle/SKILL.md`
3. `docs/skill-index.md`

## Как bundle указывает на skills

Manifest плагина уже смотрит сюда:

- `.codex-plugin/plugin.json` -> `"skills": "./skills/"`

То есть именно эта папка и является canonical bundled skill-root.
