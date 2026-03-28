# Task Playbook 10: Extra Control Layers

Когда использовать:
- когда пользователь спрашивает “что ещё упущено?”;
- когда нужен completeness-check сверх базовых 9 блоков.

## Какие слои проверить

- audience hygiene
- delivery blockers / moderation debt
- landing relevance
- analytics integrity
- structural drift
- skill / instruction drift
- naming integrity
- working-autotarget extraction loop
- boundary watchlist
- coverage validator health

## Что читать

- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Пробежать completeness-checklist.
2. Отдельно отметить блоки, которые не покрыты основным review.
3. Если блок требует отдельного collector-а, зафиксировать `missing_collector`.
4. Если блок требует отдельного validator-а, зафиксировать `missing_validator`.
5. Отдельно разделить:
   - `account gap`
   - `analytics gap`
   - `tooling / skill gap`
6. Если найден слой `working but opaque`, не маркировать его как `bad` без extraction-плана.
7. Если найден прошлый coverage drift, проверить, закрыт ли он validator-ом, а не только разовым фиксом.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_control_findings.tsv`
- `03_control_layers.md`
- `04_validation.md`
- `05_pre_apply_summary.md`

## Перед apply показать пользователю

- какие blind spots закрыты;
- какие остаются нерешёнными;
- какие gaps относятся уже не к аккаунту, а к самому skill stack;
- какие extra-layers влияют на решение сейчас, даже если это не "ещё одна правка в Директе".
