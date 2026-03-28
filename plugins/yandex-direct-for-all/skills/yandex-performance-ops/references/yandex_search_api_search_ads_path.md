# Официальный путь сбора поисковых рекламных объявлений Яндекса

Дата фиксации: `2026-03-13`

## Что подтверждено

Для поисковых рекламных объявлений Яндекса подтвержден официальный production-path через `Yandex Search API` в режиме `FORMAT_HTML`.

Это не браузерный обход и не `Firecrawl`.

## Каноническая схема

1. Источник запросов:
   - валидированная матрица `keyword x geo`;
   - либо live ключи из search-кампаний через `Direct API`.
2. Источник выдачи:
   - `POST https://searchapi.api.cloud.yandex.net/v2/web/search`
   - `responseFormat = FORMAT_HTML`
3. Что сохраняется:
   - raw JSON ответа Search API;
   - декодированный raw HTML выдачи;
   - извлеченные поисковые рекламные блоки;
   - таблица `query / region / domain / title / snippet / url / позиции`.

## Подтверждающие remote-источники

- `/Users/remote-mac/ads/tenevoy/claude/docs/WORDSTAT_AND_COMPETITORS_OFFICIAL_PATH_20260308.md`
- `/Users/remote-mac/ads/tenevoy/claude/docs/COMPETITOR_LAYER_LIVE_PROOF_20260308.md`
- `/Users/remote-mac/ads/tenevoy/direct-orchestrator/scripts/collector_competitor_scan.py`
- `/Users/remote-mac/ads/tenevoy/direct-orchestrator/scripts/local_competitor_scan.py`
- `/Users/remote-mac/ads/tenevoy/direct-orchestrator/scripts/local_competitor_scan_matrix.py`
- `/Users/remote-mac/ads/tenevoy/direct-orchestrator/tests/unit/test_competitors.py`

## Что именно доказано на Теневом

1. `collector.competitor.scan` уже работал в production workflow.
2. Источник запросов был:
   - `Direct API` -> активные `accepted/on` keywords search-кампаний.
3. Источник рекламной выдачи был:
   - `Yandex Search API` -> `FORMAT_HTML`.
4. Из HTML выделялись только поисковые рекламные блоки с признаком `Реклама`.
5. Несколько live runs подряд завершались повторяемо.

## Что считать закрытым

Закрыт именно слой:

- `Поиск Яндекса`
- `поисковые рекламные объявления`
- `официальный путь`

## Что не считать закрытым автоматически

Не считать автоматически закрытым:

- `РСЯ`
- сетевые объявления Яндекса вне поисковой выдачи
- любой browser-based обход Яндекса как рабочий production path

Для `РСЯ` нужен отдельный подтвержденный официальный источник.
