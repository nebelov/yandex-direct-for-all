# Task Playbook 11: Pre-Apply Presentation

Этот playbook обязателен перед любыми live-правками.

Цель:
- показать пользователю изменения до apply;
- сделать это не prose-хаосом, а типовым decision-pack;
- сохранить формат, пригодный для будущего UI слоя.

## Что читать

- `references/task_playbooks/00_output_contract.md`
- `templates/pre_apply_presentation_template.md`

## Что обязательно показать

- proof of coverage по всем затронутым РК;
- что меняется;
- где меняется;
- почему меняется;
- на каком evidence строится решение;
- прогноз результата;
- уровень уверенности;
- риск;
- что относится к `server-ready no-moderation pack`;
- что относится к `creative wave`;
- что остаётся `monitor-only`.

## Формат презентации

Делать минимум два слоя:
- короткий `executive summary`
- типовая `decision table`
- оба слоя должны собираться из TSV/JSON артефактов, а не писаться вручную с нуля
- если в проекте уже есть generator вроде `build_decision_report.py`, использовать его как primary path
- если decision-report получается слишком длинным или сырым для человека, поверх него обязателен отдельный `00_EXECUTIVE_REPORT.html` как primary visual layer и `00_EXECUTIVE_REPORT.md` как fallback; visual html должен собираться генератором вроде `build_executive_html.py`, который использует не только decision table, но и подходящие source-layers для картинок/RSYA-breakdown

В decision table минимум поля:
- `change_id`
- `entity_type`
- `entity_id`
- `entity_name`
- `current_state`
- `proposed_state`
- `reason`
- `evidence_ref`
- `expected_effect`
- `confidence`
- `risk`
- `pack_type`
- `approval_needed`

## Правила прогноза

- Не обещать точный результат там, где есть только weak evidence.
- Прогноз всегда маркировать как:
  - `high-confidence operational`
  - `medium-confidence optimization`
  - `hypothesis-only`
- Отдельно писать горизонт ожидания эффекта:
  - `intraday`
  - `1-3d`
  - `7d+`

## Выход

- `05_pre_apply_summary.md`
- `05_pre_apply_decision_table.tsv`
- если проект использует расширенный structured bundle:
  - `00_EXECUTIVE_REPORT.html`
  - `00_EXECUTIVE_REPORT.md`
  - `00_EXECUTIVE_REPORT.json`
  - `13_decision_table.tsv`
  - `13_decision_report.json`
  - `13_decision_report.md`
- при mixed-wave review дополнительно:
  - `growth_acceleration_pack.md` или эквивалентный growth-блок в summary
  - coverage-блок по всем search/RSYA РК окна

Без этих двух файлов live apply не начинать.
