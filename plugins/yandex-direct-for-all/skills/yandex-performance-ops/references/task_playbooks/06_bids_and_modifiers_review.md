# Task Playbook 06: Bids And Modifiers Review

Когда использовать:
- review ставок;
- budgets;
- schedule;
- device/demo modifiers.

## Truth Layer

- Direct reports по campaign/adgroup/criteria
- Roistat conversions / sales
- Metrika только для device/demo/behavior context

## Что читать

- `templates/bids_prompt.md`
- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Собрать live criteria/adgroup/campaign layers.
2. Проверить объём и confidence.
3. Разделить решения на:
   - immediate apply
   - monitor-only
   - needs more data
4. Не делать aggressive moves при low-volume.
5. Отдельно валидировать bids, budgets, device-demo и schedule, чтобы блок не выпал молча.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_bids_candidates.tsv`
- `03_modifiers_candidates.tsv`
- `04_validation.md`
- `05_pre_apply_summary.md`

## Перед apply показать пользователю

- current -> proposed ставка или корректировка;
- причина изменения;
- прогноз эффекта;
- confidence и риск перегиба;
- rollback condition.
