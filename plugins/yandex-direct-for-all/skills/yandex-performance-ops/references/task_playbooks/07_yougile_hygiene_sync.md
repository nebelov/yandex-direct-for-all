# Task Playbook 07: YouGile Hygiene Sync

Когда использовать:
- чистка дублей;
- актуализация umbrella-task;
- вынос evidence bundle в workspace.

## Truth Layer

- current YouGile workspace
- текущая wave documentation
- текущий raw/review bundle

## Что читать

- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Найти umbrella-task или создать её.
2. Проверить active boards и legacy/archive отдельно.
3. Найти duplicates, tests, orphan items, stale monitoring.
4. На каждую задачу дать status:
   - keep/update
   - merge
   - archive/close
   - delete-safe-test-only
5. Протолкнуть key files в YouGile, не оставлять только локальные пути.
6. Если документ устарел, пометить `superseded`.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_duplicate_matrix.tsv`
- `04_validation.md`
- `05_pre_apply_summary.md`
- `06_yougile_handoff.md`

## Перед apply показать пользователю

- какие задачи будут объединены/закрыты/архивированы;
- какие monitoring tasks остаются;
- где живёт актуальная волна;
- что удаляется только как безопасный test noise.
