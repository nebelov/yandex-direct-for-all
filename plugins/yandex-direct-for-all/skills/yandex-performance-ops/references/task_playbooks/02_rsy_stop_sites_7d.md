# Task Playbook 02: RSYA Stop Sites 7d

Когда использовать:
- weekly rotation `ExcludedSites`;
- поиск площадок на блокировку или ротацию по каждой РСЯ РК отдельно.

## Truth Layer

- Direct Reports API по `Placement`
- `Goals=[client_goal_id]`
- `AttributionModels=["LC"]`
- current `ExcludedSites`

Roistat здесь не источник domain-verdict.

## Что читать

- `templates/rsy_placements_prompt.md`
- `templates/validate_placements_prompt.md`
- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Определить только активные РСЯ кампании.
2. По каждой РК отдельно собрать placements raw.
3. Отдельно снять текущий `ExcludedSites`.
4. Если в проекте есть discovery script, сначала прогнать его по ПОЛНОМУ raw placements bundle, а не по заранее отфильтрованному short-list:
   - например `discover_rsya_junk_sites.py`
   - buckets обязательны:
     - `safe_ready`
     - `manual_review`
     - `anomaly_blocked`
     - `low_spend_watch`
5. Построить per-campaign verdict:
   - add
   - keep
   - rotate out
6. Domain-verdict строить только через метрики:
   - impressions / clicks / ctr / cost / avg cpc / goal conversions
   - явный app-trash / vpn / gaming inventory
   - raw-data anomalies
   - campaign intent: ретаргет, холодный RSYA, отдельный тестовый слой
7. Не использовать аргументы вида:
   - "похоже на нормальный сайт"
   - "это Yandex-owned"
   - "выглядит как контентный домен"
   без метрик и контекста кампании.
8. Обязательно показать proof of coverage по всем активным РСЯ РК окна, даже если auto-pack готовится не по каждой.
9. Safe-ready и manual-review держать раздельно.
10. `anomaly_blocked` и `low_spend_watch` держать отдельными слоями, не прятать их в prose.
11. Прогнать `validate_excluded_sites_pack.py`.
12. Собрать типовой decision-report из TSV/JSON, а не руками.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_excluded_sites_after_<cid>.json`
- `04_validation.md`
- `05_pre_apply_summary.md`
- `13_decision_table.tsv`
- `13_decision_report.md`

## Перед apply показать пользователю

- текущий список vs after-list;
- почему площадка попала в блок;
- какие именно waste-метрики это доказали;
- что просмотрены все активные РСЯ кампании окна;
- сколько площадок попало в `manual_review`, `anomaly_blocked`, `low_spend_watch`;
- какие площадки удаляются из старого stop-list;
- сколько занято слотов после ротации;
- прогноз: защита бюджета, чистка инвентаря, ожидаемый лаг эффекта.
