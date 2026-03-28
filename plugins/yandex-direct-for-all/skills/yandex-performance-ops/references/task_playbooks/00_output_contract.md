# Output Contract

Этот файл задаёт типовой output-bundle для всех operational задач.

Цель:
- чтобы результаты были сравнимы между волнами и клиентами;
- чтобы до live apply всегда существовал одинаковый pre-apply пакет;
- чтобы позже из этих файлов можно было собрать UI-страницу без перепридумывания структуры.

## Базовая структура

Для каждой волны и каждой задачи держать одинаковые слои:
- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_candidates.*`
- `04_validation.md`
- `05_pre_apply_summary.md`
- `06_yougile_handoff.md`
- если задача decision-heavy или mixed-wave:
  - `00_EXECUTIVE_REPORT.html`
  - `00_EXECUTIVE_REPORT.md`
  - `00_EXECUTIVE_REPORT.json`
  - `13_decision_table.tsv`
  - `13_decision_report.json`
  - `13_decision_report.md`
- если задача опирается на discovery scripts:
  - `review/generated/<task_name>/*`

## Что лежит в каждом файле

- `00_scope.md`
  - task id
  - период
  - точные даты
  - truth layer
  - что в scope и что out-of-scope
- `01_raw_index.md`
  - список raw-источников
  - время live-среза
  - ссылки на raw-файлы
- `02_findings.tsv`
  - нормализованные findings
  - минимум колонки: `entity_type`, `entity_id`, `entity_name`, `parent_entity_id`, `parent_entity_name`, `verdict`, `priority`, `confidence`, `evidence_ref`, `impact_hypothesis`, `status`
  - для growth/completeness задач добавлять ещё:
    - `current_coverage`
    - `recommendation_tier`
    - `proposed_target`
- `03_candidates.*`
  - task-specific кандидаты на изменения
  - формат зависит от домена: `tsv`, `json`, `md`
- `04_validation.md`
  - domain validator
  - coverage validator
  - apply-safety validator
- `05_pre_apply_summary.md`
  - короткая презентация для пользователя до любых правок
  - сначала proof of coverage по всем РК окна
  - потом current -> proposed -> why -> expected effect -> risk
  - по каждому изменению обязательно показывать:
    - `что есть сейчас`
    - `что предлагается изменить`
    - `на каком уровне` (`campaign` / `adgroup` / `ad` / `placement` / `keyword`)
    - `какой прогноз`
    - `где причинность доказана`, а где только `correlation-only`
  - если задача mixed-wave, обязательно выделять:
    - `что сдержать / починить`
    - `что усиливать / что добавлять для роста`
- `06_yougile_handoff.md`
  - что уходит в YouGile
  - какой следующий шаг разрешён
- `13_decision_table.tsv`
  - machine-friendly таблица решений для UI и повторного использования
  - минимум колонки:
    - `decision_area`
    - `lane`
    - `status`
    - `campaign_id`
    - `campaign_name`
    - `scope_name`
    - `entity_type`
    - `entity_key`
    - `current_state`
    - `proposed_change`
    - `expected_effect`
    - `risk`
    - `evidence_primary`
    - `source_file`
- `13_decision_report.json`
  - summary counts по buckets / status / area
- `13_decision_report.md`
  - короткий human-facing слой
  - не должен быть полным dump всех строк из decision table
- `00_EXECUTIVE_REPORT.md`
  - верхний наглядный отчёт для пользователя
  - должен отвечать на вопросы:
    - что уже закончено;
    - что реально предлагается менять сейчас;
    - что ушло в manual/blockers;
    - где слой роста, а не только урезание;
    - в какие файлы идти за глубиной
  - собирается автоматически из `13_decision_table.tsv` и summary json, а не пишется руками
- `00_EXECUTIVE_REPORT.json`
  - machine-friendly верхний summary слой для будущего UI
- `00_EXECUTIVE_REPORT.html`
  - primary visual artifact для пользователя
  - должен собираться из тех же structured данных, что и `.md/.json`
  - не должен требовать ручной верстки после каждой волны

## Общие правила

- Если задача не идёт к apply, `05_pre_apply_summary.md` всё равно создаётся как review-summary.
- Если блок только `monitor-only`, это должно быть видно в `02_findings.tsv` и `05_pre_apply_summary.md`.
- Для later UI generation опирайся на одинаковые поля, а не на свободный prose.
- В review и findings нельзя оставлять только ID без читаемого имени сущности.
- Если задача идёт через discovery scripts, markdown review должен рендериться из generated TSV/JSON, а не из hand-picked списков внутри самого `.md`.
- Если задача mixed-wave или decision-heavy, executive-report обязателен. Primary artifact = `00_EXECUTIVE_REPORT.html`; нельзя считать `13_decision_report.md` достаточной заменой верхнему user-facing summary.
