# Task Playbook 03: Creative Outliers Rotation

Когда использовать:
- поиск текстов-аутсайдеров;
- поиск изображений-аутсайдеров;
- подготовка новой creative wave.

## Truth Layer

- Direct ad performance
- current ad state
- Roistat leads/sales signal при наличии

Сначала delivery blockers, потом creative debt.

## Что читать

- `templates/ad_components_prompt.md`
- `references/ad_format_limits.md`
- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Найти broken / rejected / non-serving ads.
2. Отделить их от creative review.
3. Разобрать text signal отдельно от image signal.
4. Не смешивать group/context confounders с самим asset verdict.
5. Собрать replacement pack.
6. Прогнать `validate_ad_replacement_pack.py`.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_text_outliers.tsv`
- `03_image_outliers.tsv`
- `03_ad_replacement_pack.md`
- `04_validation.md`
- `05_pre_apply_summary.md`

## Перед apply показать пользователю

- какое текущее объявление проигрывает;
- на что оно заменяется;
- почему verdict именно text или image, а не всё сразу;
- какие лимиты/модерационные риски есть;
- это `creative wave`, а не `no-moderation pack`.
