# Completeness Audit - 2026-03-05

Цель ревизии: убедиться, что global-skill покрывает reusable-слой полностью, а client-specific слой не был ошибочно затёрт или смешан с глобальным.

## Проверенный scope

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

## Матрица покрытия

| Блок | Статус | Что сделано |
|---|---|---|
| Wordstat full-depth | OK | promoted scripts + mask methodology + manual-analysis guardrails |
| Search semantics workflow | OK | promoted scripts + templates + live readiness checks |
| Direct optimization workflow | OK | collect/apply/validate/change-tracker + diagnostic prompts |
| Roistat-first workflow | OK | safe file-based query + source-priority rules |
| Yandex Metrika | OK | promoted shell layer + generic local config contract |
| Media-plan | OK | promoted forecast engine + prompt |
| Competitor research | OK | generic workflow + prompt added |
| Skill revision discipline | OK | checklist + lessons registry added |
| Local overlay contract | OK | client context contract formalized |
| Client overlays for active projects | OK | `kartinium`, `siz`, `tenevoy` overlays added locally |

## Что было упущено до ревизии

1. Не было formal completeness audit.
2. Не было reusable lessons registry.
3. Не было generic competitor research слоя.
4. Не было generic Metrika config contract.
5. Не было явного overlay guardrail против analysis-скриптов.
6. Не было локальных overlay-файлов для трёх активных проектов.

## Что НЕ поднималось в global-skill намеренно

Эти вещи оставлены локально, потому что это не reusable-слой:

- локальные product catalog и brand axioms;
- project/board/column UUIDs;
- raw отчёты, campaign maps, landing routing;
- client-specific Roistat analyzers;
- любые analysis-скрипты, которые сами решают что target/negative/minus.

## Критерий полноты после ревизии

Навык считается полным в intended scope, если:

1. reusable методология и guardrails лежат глобально;
2. reusable scripts не содержат client hardcode и секреты;
3. все уникальные правила клиента лежат локально в overlay и/или локальных skill/docs;
4. manual-analysis constitution зафиксирована явно;
5. smoke-проверки entrypoints проходят.

## Остаточные ограничения

- global-skill не заменяет локальные product docs;
- overlay не должен использоваться как секрет-хранилище;
- competitor research по-прежнему требует ручного анализа материалов, а не auto-scoring;
- если появится новый reusable workflow, нужен отдельный post-cycle promotion.
