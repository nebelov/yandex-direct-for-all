# Data Collection Scripts

Этот файл отвечает на вопрос: где именно в bundle лежат скрипты для сбора и парсинга данных.

Ниже перечислены именно `collector/parsing`-слои. `apply`, `validation` и `report-only` сюда не включены, если они не участвуют в raw data collection.

## 1. Wordstat

### Основные collectors

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-performance-ops/scripts/wordstat_preflight.sh` | `bash` | preflight по Wordstat перед wave collection |
| `skills/yandex-performance-ops/scripts/wordstat_collect_wave.js` | `node` | основной wave collector для `Wordstat` |
| `skills/yandex-performance-ops/scripts/wordstat_tool.sh` | `bash` | helper-обёртка для `Wordstat` tool path |
| `skills/yandex-performance-ops/scripts/normalize_wordstat_regions.py` | `python3` | нормализация региональных данных Wordstat |

### Render/parsing helpers поверх raw

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-performance-ops/scripts/render_wordstat_wave.py` | `python3` | рендер raw wave в читаемый слой |
| `skills/yandex-performance-ops/scripts/render_wordstat_mask_demand.py` | `python3` | рендер спроса по маскам |
| `skills/yandex-performance-ops/scripts/render_wordstat_seasonality.py` | `python3` | рендер сезонности |
| `skills/yandex-performance-ops/scripts/render_wordstat_geo.py` | `python3` | рендер географии |

## 2. Yandex Direct

### Основные collectors

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-performance-ops/scripts/collect_all.py` | `python3` | account-wide raw collection по Direct/related layers |
| `skills/yandex-performance-ops/scripts/collect_operational_precheck.py` | `python3` | precheck и inventory collector перед operational work |
| `skills/yandex-performance-ops/scripts/fetch_sqr.sh` | `bash` | raw Search Query Report collector |
| `skills/yandex-performance-ops/scripts/audit_campaign_meta.py` | `python3` | сбор meta/state по кампаниям |
| `skills/yandex-performance-ops/scripts/audit_ad_delivery_failures.py` | `python3` | сбор failure-state по ad delivery |
| `skills/yandex-performance-ops/scripts/campaign_autotest.py` | `python3` | smoke/autotest по campaign setup |

## 3. Yandex Metrika

Metrika в этом bundle не отдельный MCP server, а набор reusable shell collectors:

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-performance-ops/scripts/metrika/counters.sh` | `bash` | список счётчиков |
| `skills/yandex-performance-ops/scripts/metrika/counter_info.sh` | `bash` | информация по счётчику |
| `skills/yandex-performance-ops/scripts/metrika/goals.sh` | `bash` | цели счётчика |
| `skills/yandex-performance-ops/scripts/metrika/conversions.sh` | `bash` | конверсии |
| `skills/yandex-performance-ops/scripts/metrika/traffic_summary.sh` | `bash` | summary по трафику |
| `skills/yandex-performance-ops/scripts/metrika/utm_report.sh` | `bash` | UTM-based отчёт |
| `skills/yandex-performance-ops/scripts/metrika/search_engines.sh` | `bash` | срез по поисковым системам |

## 4. Roistat

### Основные collectors

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-performance-ops/scripts/roistat_query.sh` | `bash` | канонический query path для raw API data |
| `skills/roistat-reports-api/scripts/build_roistat_report_pack.py` | `python3` | сбор standalone report pack через API |
| `skills/roistat-reports-api/scripts/sync_truth_layer_report.py` | `python3` | сбор/синхронизация truth-layer report |
| `skills/roistat-reports-api/scripts/save_roistat_report.py` | `python3` | сохранение/обновление saved report |

## 5. Yandex Search / SERP / Research

### Batch collectors

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py` | `python3` | batch-сбор organic SERP |
| `skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py` | `python3` | batch-сбор ad SERP |
| `skills/yandex-direct-client-lifecycle/scripts/firecrawl_scrape.py` | `python3` | page capture batch |
| `skills/yandex-direct-client-lifecycle/scripts/sitemap_probe_batch.py` | `python3` | sitemap discovery batch |
| `skills/yandex-direct-client-lifecycle/scripts/yandex_browser_serp_batch.py` | `python3` | browser-based fallback batch |

### Job/build/parsing helpers

| Скрипт | Runtime | Назначение |
|---|---|---|
| `skills/yandex-direct-client-lifecycle/scripts/build_serp_jobs_from_keyword_matrix.py` | `python3` | build job-spec для SERP collection |
| `skills/yandex-direct-client-lifecycle/scripts/build_domain_shortlist_from_serp.py` | `python3` | shortlist доменов после SERP raw |
| `skills/yandex-direct-client-lifecycle/scripts/build_followup_jobs_from_serp.py` | `python3` | build follow-up jobs для page capture/sitemap |
| `skills/yandex-direct-client-lifecycle/scripts/split_tsv_batch.py` | `python3` | chunking больших job tables |
| `skills/yandex-direct-client-lifecycle/scripts/merge_sitemap_batch_outputs.py` | `python3` | merge sitemap outputs |
| `skills/yandex-direct-client-lifecycle/scripts/render_serp_wave.py` | `python3` | render organic SERP raw |
| `skills/yandex-direct-client-lifecycle/scripts/render_ad_serp_wave.py` | `python3` | render ad SERP raw |
| `skills/yandex-direct-client-lifecycle/scripts/render_page_capture_inventory.py` | `python3` | render page capture inventory |
| `skills/yandex-direct-client-lifecycle/scripts/render_sitemap_candidates.py` | `python3` | render sitemap candidates |
| `skills/yandex-direct-client-lifecycle/scripts/verify_research_bundle.py` | `python3` | completeness-check собранного research bundle |

## 6. Быстрый доступ через top-level launchers

Чтобы не искать глубоко внутри `skills/*/scripts/`, в plugin-root вынесены launcher-скрипты:

| Launcher | Что запускает |
|---|---|
| `scripts/list_data_collectors.sh` | показывает все главные collector paths |
| `scripts/collect_wordstat_wave.sh` | `wordstat_collect_wave.js` |
| `scripts/collect_direct_bundle.sh` | `collect_all.py` |
| `scripts/collect_direct_sqr.sh` | `fetch_sqr.sh` |
| `scripts/collect_metrika.sh` | любой из `metrika/*.sh` |
| `scripts/collect_roistat.sh` | `roistat_query.sh` |
| `scripts/collect_organic_serp.sh` | `yandex_search_batch.py` |
| `scripts/collect_ad_serp.sh` | `yandex_search_ads_batch.py` |
| `scripts/collect_page_capture.sh` | `firecrawl_scrape.py` |
| `scripts/collect_sitemap.sh` | `sitemap_probe_batch.py` |

## 7. Практический вывод

Скрипты парсинга данных в bundle были и раньше, но они лежали внутри skill-папок.
Теперь bundle дополнительно даёт:

- явный inventory;
- быстрые launcher-скрипты;
- self-contained documentation внутри plugin-root.
