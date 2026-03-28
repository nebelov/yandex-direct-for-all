# Source Skill Contract

Новый lifecycle skill не является заменой исходных навыков.

Он обязан наследовать и применять их канон.

## Канонические источники

### 1. Wordstat

Source of truth:

1. `../../yandex-performance-ops/references/wordstat_collection_framework.md`
2. `../../yandex-performance-ops/SKILL.md`
3. текущие public collectors и templates из этого репозитория

Обязательные правила:

1. `СТРУКТУРА -> МАСКИ -> РЕВЬЮ МАСОК -> ПАРСИНГ СКРИПТОМ -> [полный успех] -> АНАЛИЗ -> ЧИСТКА -> ГРУППИРОВКА`
2. сначала `product map`, потом `01-masks-wave1.tsv`
3. `Wave 1` обязан начинаться с `L1` root-масок, где это семантически возможно; это обычно однословные маски
4. `Wave 2` добавляет уже двухсловные product/object masks
5. после составления `Wave 1` обязателен review масок как минимум по двум плоскостям:
   - web/source synonyms review
   - Wordstat associations review
6. `Wave 1` и `Wave 2` обязательны
7. парсинг только официальным API / MCP / reusable scripts
8. разовые one-off запросы вместо `wave collector` запрещены
9. `Wordstat` raw собирать через `scripts/wordstat_collect_wave.js` или эквивалентный официальный collector-path
10. `numPhrases=2000` обязателен для full-depth
11. анализ начинать только после completeness gate по raw bundle
12. analysis-скрипты для классификации ключей и минус-слов запрещены
13. после validated keyword matrix любой competitor collection идти цепочкой:
   - `organic SERP jobs`
   - `organic SERP raw`
   - `build_followup_jobs_from_serp.py`
   - `page-capture jobs`
   - `sitemap jobs`
   - только потом ручной анализ конкурентного слоя
13.1. до `page-capture` и `sitemap` нужно сначала собрать таблицу повторяемости доменов по подтвержденной выдаче, затем вручную утвердить укороченный список сильных доменов:
   - ориентир по умолчанию = `топ-15` повторяющихся доменов из реальной выдачи Яндекса;
   - builder и sitemap paths не должны массово тянуть сотни слабых доменов без ручного shortlist;
   - страницы статей, новостей, справочников и PDF нужно отсекать механическими URL-паттернами до follow-up сбора;
14. если `page-capture` или `sitemap` jobs большие, lifecycle skill обязан использовать chunk/merge utilities:
   - `split_tsv_batch.py`
   - параллельные batch workers
   - merge step скриптом, а не вручную
15. перед analysis-stage lifecycle skill обязан прогнать `verify_research_bundle.py`
16. verifier проверяет только комплектность артефактов и не заменяет ручной анализ качества

### 1.1. Яндекс-выдача

Обязательные правила:

1. поисковую выдачу Яндекса и рекламную выдачу Яндекса нельзя собирать браузерным скрейпингом как канонический путь;
2. для Яндекса разрешены только:
   - официальный API;
   - официальный экспорт;
   - подтвержденные выгрузки из интерфейса Яндекса;
3. браузерный collector не считать допустимым рабочим методом для Яндекс-выдачи;
4. для поисковых рекламных объявлений Яндекса подтвержден официальный путь через `Yandex Search API` в `FORMAT_HTML`;
5. этот путь не распространять автоматически на `РСЯ`;
6. если не подтвержден именно нужный рекламный слой, его помечать как `не закрыт`, а не заменять браузерным обходом.

### 2. Direct Semantics

Source of truth:

1. `../../yandex-performance-ops/SKILL.md`

Обязательные правила:

1. `ПАРСИНГ != АНАЛИЗ`
2. сначала access preflight и smoke-tests
3. Direct/Reports/Wordstat запускать готовыми collectors, не ручными curl-вызовами по одной сущности
4. analysis-этап не должен триггерить новые API-вызовы

### 3. Direct Campaign Layer

Source of truth:

1. `../../yandex-performance-ops/SKILL.md`

Обязательные правила:

1. `Direct` preflight обязателен до build/apply
2. все create/update/apply шаги только через канонический skill и его чеклисты
3. lifecycle skill не выдумывает собственный Direct apply workflow

## Что делает lifecycle skill

1. оркестрирует upstream-слой;
2. создает локальный knowledge/research scaffold;
3. приводит проект к каноническим артефактам source skills;
4. передает дальше в `yandex-performance-ops`.
