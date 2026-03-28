# Agent Template: Group Copy Alignment (Search)

Задача: проверить, что тексты объявлений соответствуют ключам конкретной группы, а не общей теме кампании.

## Вход
- `clusters/search_cluster_map*.tsv`
- `deploy/checks/group_ads_copy_audit*.tsv`

## Правила (строго)
1. Сравнивать на уровне `adgroup_name`.
2. В каждом тексте должны быть лексические маркеры темы группы.
3. Не допускаются кросс-групповые дубли текстов.
4. Для каждой группы должно быть 5 объявлений.

## Выход
TSV `group_copy_alignment_report.tsv`:
- `campaign_name`
- `adgroup_name`
- `ads_count`
- `has_group_markers` (`yes|no`)
- `cross_group_duplicate` (`yes|no`)
- `risk` (`low|medium|high`)
- `notes`

