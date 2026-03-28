# Rule Source Map

Карта, где именно лежат ключевые правила в исходных skills.

## `yandex-performance-ops`

Основной файл:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/SKILL.md`

Ключевые зоны:

- `Источники данных и иерархия истины`
- `Жёсткие правила`
- блоки по `Wordstat`
- блоки по `manual gate`
- блоки по `live apply`
- блоки по `Audience`
- блоки по `collector-plane`

Особенно важные группы правил в этом файле:

- `ПАРСИНГ != АНАЛИЗ`
- scripts only mechanical layer
- no machine verdict
- `Wordstat` только официальный collector workflow
- `SERP/competitor` только через batch collectors
- `Direct` без UI login/password
- mandatory post-apply report
- `Audience token separation`
- `collector-plane` как отдельный слой

## `yandex-direct-client-lifecycle`

Основной файл:

- `plugins/yandex-direct-for-all/skills/yandex-direct-client-lifecycle/SKILL.md`

Особенно важные зоны:

- `Re-read Source Skills Before Wordstat/Direct Work`
- `Separate Collection From Analysis`
- канонические `job-spec -> collector` paths
- `Wordstat` rules for upstream research
- правила `Firecrawl`
- machine verification before analysis-stage

Ключевой смысл:

- upstream research не делается ручными one-off прогонами
- raw collection и analysis разделены
- source-skills имеют приоритет над lifecycle summary

## `source_inventory.md`

Файл:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/source_inventory.md`

Зачем нужен:

- показывает, из каких исходных skills был поднят reusable layer
- фиксирует, что намеренно оставлено локальным
- объясняет, что нельзя поднимать в global layer без sanitization

## `completeness_audit_2026-03-05.md`

Файл:

- `plugins/yandex-direct-for-all/skills/yandex-performance-ops/references/completeness_audit_2026-03-05.md`

Зачем нужен:

- подтверждает intended scope global skill
- фиксирует, что reusable methodology должна жить глобально
- отдельно фиксирует, что client-specific analyzers и client-specific docs не должны подменять global layer

## Как читать канон правильно

Если есть конфликт между:

1. кратким интеграционным пересказом
2. локальной project docs
3. source-skills

то верхний канон такой:

1. source-skills
2. глобальный `yandex-performance-ops`
3. lifecycle как upstream overlay
4. локальные project overlays
