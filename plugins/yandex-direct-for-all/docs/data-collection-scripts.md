# Сбор данных

Основной порядок работы описан в `skills/yandex-direct-unified/SKILL.md`. Все команды чтения получают доступы только из защищённой среды или явно указанного закрытого файла; токены не передаются аргументами.

## Директ и Метрика

- `skills/yandex-performance-ops/scripts/collect_direct_cabinet_snapshot.py` — полный снимок кабинета;
- `skills/yandex-performance-ops/scripts/collect_direct_management_snapshot.py` — настройки управления;
- `skills/yandex-performance-ops/scripts/fetch_sqr_parallel.py` — поисковые запросы;
- `skills/yandex-performance-ops/scripts/collect_all.py` — раздельный итог по источникам;
- `scripts/collect_direct_bundle.sh`, `scripts/collect_direct_sqr.sh`, `scripts/collect_metrika.sh` — короткие обёртки.

Каждый постраничный результат сохраняет число страниц и объектов, признак завершения и контрольную сумму.

## Wordstat

- `mcp/yandex-wordstat/src/index.mjs` — штатные методы Wordstat второго поколения;
- `mcp/yandex-wordstat/scripts/wordstat_cloud_gateway_collect.py` — устойчивый сбор волн;
- `scripts/collect_wordstat_wave.sh` — короткая обёртка.

Операторы исходной маски не изменяются, ограничения запросов общие между процессами, подтверждённые результаты продолжаются после перезапуска.

## Выдача и страницы

- `skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py` — обычная выдача;
- `skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py` — рекламная выдача через официальный Search API с явным закрытым файлом доступа и пределом стоимости;
- `skills/yandex-direct-client-lifecycle/scripts/yandex_browser_serp_batch.py` — необязательный диагностический снимок с видимым признаком капчи; перед отдельным запуском установите `playwright` и его браузер по официальной инструкции Playwright;
- `skills/yandex-direct-client-lifecycle/scripts/firecrawl_scrape.py` — сохранение общедоступных страниц;
- `skills/yandex-direct-client-lifecycle/scripts/sitemap_probe_batch.py` — карты сайта;
- `scripts/collect_organic_serp.sh`, `scripts/collect_ad_serp.sh`, `scripts/collect_page_capture.sh`, `scripts/collect_sitemap.sh` — короткие обёртки.

Обычная выдача, рекламная выдача, страницы сайта и домены хранятся раздельно. Браузерный снимок не считается окончательной истиной.

## Проверка проекта

`skills/yandex-direct-client-lifecycle/scripts/verify_research_bundle.py` проверяет состав по `research-manifest.json`, поля реестров и недопустимое смешение домена с адресом конкретной страницы.
