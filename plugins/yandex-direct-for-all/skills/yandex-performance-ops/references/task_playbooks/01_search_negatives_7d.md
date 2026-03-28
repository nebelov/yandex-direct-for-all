# Task Playbook 01: Search Negatives 7d

Когда использовать:
- еженедельный сбор новых минус-слов;
- поиск новых target-фраз;
- routing review по search queries.

## Truth Layer

- SQR raw из Direct Reports
- current negatives / routing / campaign structure
- Roistat как truth по лидам и продажам

## Что читать

- `templates/search_query_prompt.md`
- `templates/agent_negative_from_wave.md`
- `templates/validate_negatives_prompt.md`
- `references/task_playbooks/00_output_contract.md`

## Порядок

1. Зафиксировать окно и кампании.
2. Выгрузить SQR raw через `bash scripts/fetch_sqr.sh ...`.
3. Сохранить raw без mutate.
4. Если в проекте есть discovery script, сначала запустить его на полном raw:
   - например `discover_search_stop_words.py`
   - output обязан содержать buckets:
     - `safe_ready`
     - `manual_review`
     - `route_review`
     - `growth_review`
     - `uncovered_queries`
   - discovery обязан иметь защитный слой от ложных минус-слов:
     - product catalog / assortment guardrails
     - client-specific `protected_family_rules`
     - reject-layer для неэкшенабельных модификаторов вроде цены, цвета, размеров и других товарных спецификаций
5. Phrase-level evidence использовать только как сырьё.
6. Основной output строить как `single-token stop-word list` в одной форме, если слово safe на нужном scope.
7. Если safe-ready мало, это НЕ доказательство чистого поиска:
   - обязательно отдельно показать `route_review`
   - обязательно показать `uncovered_queries`
8. Если слово unsafe на уровне кампании, но safe на уровне adgroup, так и фиксировать scope.
9. Отдельно зафиксировать слова, которые нельзя минусить:
   - core product words
   - слова, которые режут target intent
   - product modifiers / application words / LED / door-window-slope layer, если они целевые для клиента
10. Обязательно показать proof of coverage:
   - все search-РК в окне
   - impressions / clicks / cost по каждой
   - сколько SQR rows реально проанализировано по каждой РК
11. Safe-ready и manual-review держать раздельно.
12. Growth-routes и routing leaks НЕ путать с минус-словами.
13. Если слово относится к соседнему товарному маршруту, оно должно уходить в `route_review` с готовой рекомендацией по структуре, а не оставаться подвешенным как `manual`.
14. Прогнать semantic validation.
15. Собрать типовой decision-report из TSV/JSON, а не писать summary с нуля.

## Типовой output-bundle

- `00_scope.md`
- `01_raw_index.md`
- `02_findings.tsv`
- `03_negative_stop_words.tsv`
- `03_target_additions.tsv`
- `04_validation.md`
- `05_pre_apply_summary.md`
- `13_decision_table.tsv`
- `13_decision_report.md`

## Перед apply показать пользователю

- какие stop-words предлагаются;
- на каком scope они будут применены;
- какие phrase-level evidence к ним привели;
- что просмотрены все search-РК окна, а не одна-две;
- сколько найдено `route_review`, `growth_review`, `uncovered_queries`;
- какие фразы предлагаются как новые targets;
- какие горячие фразы рискуют пострадать;
- прогноз экономии или очистки трафика;
- confidence по каждому изменению.
