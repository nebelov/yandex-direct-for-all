# Task Playbook 09: Missing Phrases Growth

Когда использовать:
- поиск упущенных ключевых фраз;
- новые группы;
- новые кампании;
- routing expansion.

## Truth Layer

- official Wordstat path
- current routing map
- SQR discoveries
- competitor themes

## Что читать

- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Проверить, какой Wordstat path реально доступен клиенту.
2. Собрать raw wave официальным способом.
3. Сравнить с текущим campaign/routing map.
4. Обязательно построить `coverage matrix`:
   - `mask / cluster`
   - `wordstat demand`
   - `current explicit coverage`
   - `current incidental coverage`
   - `business / direct signal`
   - `recommendation tier`
5. Разделить слои:
   - `product-intent`
   - `solution-intent`
   - `variant-layer`
   - `boundary / out-of-scope`
6. Нельзя помечать кластер как `missing`, если уже есть одно из:
   - явный keyword/adgroup;
   - повторяемый live search coverage в SQR;
   - route-level signal в действующей кампании.
7. Ручным анализом разделить:
   - `extend_existing_group`
   - `new_exact_test_group`
   - `new_campaign_shell`
   - `copy_or_landing_angle`
   - `negative_boundary`
   - `no_action`
8. Новый campaign-shell предлагать только если нужен другой:
   - geo;
   - offer;
   - landing;
   - strategy;
   - budget isolation.
9. Если кластер уже ловится через working autotargeting, следующий шаг по умолчанию:
   - `exact/phrase extraction test`,
   а не новая кампания.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_growth_gap_matrix.tsv`
- `03_new_groups.tsv`
- `03_new_campaigns.tsv`
- `04_validation.md`
- `05_pre_apply_summary.md`

## Перед apply показать пользователю

- где просто расширение текущих групп;
- где нужен только `exact-test`, а не новая РК;
- где реально нужен новый campaign shell;
- какие кластеры уже покрыты и не должны называться `упущенными`;
- какой ожидается объём;
- какая уверенность у каждой гипотезы.
